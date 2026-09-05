"""The one process that owns the game, its storage, and both windows.

Task 1 proved that one pywebview process can host two windows. This module now
puts a real scoreboard behind them:

* the single-instance lock is taken before anything else, so two copies can
  never write the same database (R-004);
* startup inspects what survived an interruption and *offers* a choice; nothing
  auto-resumes (P-005);
* one :class:`~scoreboard.application.service.ScoreboardService` and one
  :class:`~scoreboard.infrastructure.persistence.GameStore` are shared by both
  windows through the narrow bridge;
* a refresh loop pushes formatted view models to the windows and checkpoints a
  running clock once per displayed second (P-003).

The window-free parts are separated from the webview parts on purpose:
:class:`ScoreboardApplication` can be built, driven, and shut down in a test
without opening a window, which is what the Task 7 contract tests do.

Closing the spectator window stops no clock and closes no operator window
(D-005), and a spectator rendering failure is caught at the push boundary so it
cannot reach the state engine (R-002).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

import webview

from scoreboard.application.recovery import (
    RecoveryReport,
    RecoverySource,
    inspect_recovery,
    resume_recovered_game,
    start_new_game,
)
from scoreboard.application.service import ScoreboardService
from scoreboard.domain.state import APP_VERSION
from scoreboard.host.bridge import (
    DisplayLink,
    ScoreboardBridge,
    SpectatorBridge,
    spectator_view_model,
)
from scoreboard.host.startup import StartupBridge
from scoreboard.host.displays import enumerate_displays, selected_screen
from scoreboard.infrastructure.diagnostics import Diagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths, resolve_paths
from scoreboard.infrastructure.persistence import GameStore, InstanceLock

VIEWS = Path(__file__).resolve().parent.parent / "views"

#: Four refreshes a second: fast enough that a tenths readout never looks
#: frozen, slow enough that the checkpoint policy still writes once per
#: displayed second rather than once per frame.
REFRESH_INTERVAL_SECONDS: float = 0.25


def view_url(name: str) -> str:
    """The bundled page for one window. Nothing is fetched from a network."""

    return (VIEWS / name / "index.html").as_uri()


class ScoreboardApplication:
    """Owns the game, its storage, and the health of the spectator window."""

    def __init__(
        self,
        paths: ScoreboardPaths | None = None,
        *,
        monotonic_clock: Callable[[], float] | None = None,
        diagnostics: Diagnostics | None = None,
        acquire_lock: bool = True,
    ) -> None:
        self.paths = (resolve_paths() if paths is None else paths).ensure()
        self.diagnostics = (
            Diagnostics(self.paths) if diagnostics is None else diagnostics
        )
        self._monotonic = monotonic_clock
        self._lock: InstanceLock | None = None
        if acquire_lock:
            try:
                self._lock = InstanceLock(self.paths.lock).acquire()
            except Exception as exc:  # noqa: BLE001 - reported, then re-raised
                self.diagnostics.instance_refused(reason=str(exc))
                raise
        self.diagnostics.startup(app_version=APP_VERSION)

        self.report: RecoveryReport = inspect_recovery(
            self.paths, diagnostics=self.diagnostics
        )
        self.service: ScoreboardService | None = None
        self.store: GameStore | None = None
        self.bridge: ScoreboardBridge | None = None
        self.display = DisplayLink()
        self._push: Callable[[str, dict[str, Any]], None] | None = None
        self._command_lock = threading.RLock()
        self._stopping = threading.Event()
        self._refresh: threading.Thread | None = None

    # --- The operator's startup choice (P-005) ------------------------------

    @property
    def can_resume(self) -> bool:
        return self.report.can_resume

    def recovery_payload(self) -> dict[str, Any]:
        """The JSON-compatible recovery report the operator chooses from."""

        payload = self.report.to_dict()
        payload["view"] = (None if self.report.state is None
                           else spectator_view_model(self.report.state))
        return payload

    def resume(self) -> ScoreboardBridge:
        """Continue the recovered game, with every clock stopped."""

        service = resume_recovered_game(self.report, monotonic_clock=self._monotonic)
        return self._begin(service, resume_game_id=self.report.game_id)

    def start_new(self) -> ScoreboardBridge:
        """Begin a clean game. Nothing already on disk is deleted."""

        service = start_new_game(monotonic_clock=self._monotonic)
        return self._begin(service, resume_game_id=None)

    def _begin(
        self, service: ScoreboardService, *, resume_game_id: int | None
    ) -> ScoreboardBridge:
        store = GameStore.open(
            self.paths,
            diagnostics=self.diagnostics,
            using_backup=self.report.source is RecoverySource.BACKUP,
        )
        store.begin_session(service.state, resume_game_id=resume_game_id)
        self.service = service
        self.store = store
        self.display.reopen = self.reopen_spectator  # type: ignore[method-assign]
        self.bridge = ScoreboardBridge(
            service,
            store,
            display=self.display,
            diagnostics=self.diagnostics,
            lock=self._command_lock,
        )
        return self.bridge

    # --- Refresh loop -------------------------------------------------------

    def tick(self, now: float | None = None) -> dict[str, Any] | None:
        """One refresh: checkpoint if the displayed second changed, then push."""

        if self.bridge is None:
            return None
        view = self.bridge.tick(now)
        self._publish(view)
        return view

    def start_refresh(self, interval: float = REFRESH_INTERVAL_SECONDS) -> None:
        if self._refresh is not None:
            return
        self._stopping.clear()

        def loop() -> None:
            while not self._stopping.wait(interval):
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001 - a repaint must not end the game
                    self.diagnostics.unhandled_error(context="refresh", error=exc)

        self._refresh = threading.Thread(target=loop, name="scoreboard-refresh", daemon=True)
        self._refresh.start()

    def stop_refresh(self) -> None:
        self._stopping.set()
        thread, self._refresh = self._refresh, None
        if thread is not None:
            thread.join(timeout=2.0)

    # --- Publishing to the windows -----------------------------------------

    def set_publisher(self, push: Callable[[str, dict[str, Any]], None] | None) -> None:
        """Install the function that delivers a view model to one window."""

        self._push = push

    def _publish(self, operator_view: dict[str, Any]) -> None:
        if self._push is None or self.bridge is None:
            return
        try:
            self._push("operator", operator_view)
        except Exception as exc:  # noqa: BLE001
            self.diagnostics.unhandled_error(context="operator_push", error=exc)
        try:
            self._push("spectator", self.bridge.spectator_snapshot())
        except Exception as exc:  # noqa: BLE001
            # A spectator that cannot render is a display problem, not a game
            # problem: report it, mark the display, and keep the clocks running.
            self.diagnostics.unhandled_error(context="spectator_push", error=exc)
            self.bridge.display_closed(f"The display stopped responding: {exc}")

    # --- Spectator health ---------------------------------------------------

    def reopen_spectator(self) -> Any:
        """Replaced by :class:`WindowHost`; alone this opens no window."""

        return self.display.status

    def spectator_opened(self, target: str | None = None) -> None:
        if self.bridge is not None:
            self._publish(self.bridge.display_opened(target))

    def spectator_closed(self, detail: str = "The spectator window is closed.") -> None:
        # Clocks keep running and the operator stays open (D-005).
        if self.bridge is not None:
            self._publish(self.bridge.display_closed(detail))

    # --- Shutdown -----------------------------------------------------------

    def shutdown(self, reason: str = "clean") -> None:
        self.stop_refresh()
        if self.bridge is not None:
            try:
                self.bridge.shutdown()
            except Exception as exc:  # noqa: BLE001
                self.diagnostics.unhandled_error(context="shutdown_save", error=exc)
        if self.store is not None:
            self.store.close()
        self.diagnostics.shutdown(reason=reason)
        self.diagnostics.close()
        if self._lock is not None:
            self._lock.release()
            self._lock = None


class RecoveryChoiceRequired(RuntimeError):
    """A recoverable game exists and the operator has not chosen what to do.

    Raised instead of quietly resuming or quietly replacing the game. The
    report travels with the error so the caller can show what was found.
    """

    def __init__(self, report: RecoveryReport) -> None:
        super().__init__(report.message)
        self.report = report


class WindowHost:
    """Creates and replaces the two webview windows for one application."""

    def __init__(
        self,
        application: ScoreboardApplication,
        *,
        initial_display_index: int = 1,
        auto_close_after_seconds: float | None = None,
    ) -> None:
        if auto_close_after_seconds is not None and auto_close_after_seconds <= 0:
            raise ValueError("--auto-close-after-seconds must be greater than zero")
        self.application = application
        self.initial_display_index = initial_display_index
        self.auto_close_after_seconds = auto_close_after_seconds
        self.startup_window: webview.Window | None = None
        self.operator_window: webview.Window | None = None
        self.spectator_window: webview.Window | None = None
        self.status = "STARTING"
        self._lock = threading.RLock()
        application.set_publisher(self._push)
        application.reopen_spectator = self.reopen_spectator  # type: ignore[method-assign]
        application.display.reopen = self.reopen_spectator  # type: ignore[method-assign]

    # --- Lifecycle ----------------------------------------------------------

    def run(self, startup_choice: str | None = None, *, interactive: bool = False) -> None:
        """Offer recovery in interactive launches; retain the headless guard."""
        needs_choice = self.application.report.source is not RecoverySource.NONE
        if needs_choice and startup_choice is None:
            if not interactive:
                raise RecoveryChoiceRequired(self.application.report)
            self.startup_window = webview.create_window(
                "Recover scoreboard", url=view_url("startup"),
                js_api=StartupBridge(self.application.recovery_payload, self._choose_startup),
                width=800, height=650, min_size=(600, 500),
            )
        else:
            self._choose_startup(startup_choice or "new")
        try:
            if self.auto_close_after_seconds is None:
                webview.start()
            else:
                webview.start(self._close_after_delay, (self.auto_close_after_seconds,))
        finally:
            self.application.shutdown()

    def _choose_startup(self, choice: str) -> None:
        with self._lock:
            if self.application.bridge is not None:
                return  # Double clicks cannot create a second session or window.
            if choice not in ("resume", "new"):
                raise ValueError("Choose Resume recovered game or Start new game")
            bridge = self.application.resume() if choice == "resume" else self.application.start_new()
            self.operator_window = webview.create_window(
                "Scoreboard control", url=view_url("operator"), js_api=bridge,
                width=1180, height=720, min_size=(1024, 600),
            )
            self.operator_window.events.loaded += self._operator_loaded
            self.operator_window.events.closing += self._operator_closing
            startup, self.startup_window = self.startup_window, None
        if startup is not None:
            startup.destroy()

    def _close_after_delay(self, seconds: float) -> None:
        threading.Event().wait(seconds)
        window = self.operator_window or self.startup_window
        if window is not None:
            window.destroy()

    def _operator_loaded(self) -> None:
        self.open_spectator(self.initial_display_index)
        self.application.start_refresh()

    def _operator_closing(self) -> None:
        with self._lock:
            self.status = "SHUTTING DOWN"
            spectator = self.spectator_window
            self.spectator_window = None
        self.application.stop_refresh()
        if spectator is not None:
            spectator.destroy()

    # --- Windows ------------------------------------------------------------

    def displays(self) -> list[dict[str, Any]]:
        return [
            {"index": display.index, "label": display.label}
            for display in enumerate_displays(list(webview.screens))
        ]

    def open_spectator(self, display_index: int) -> dict[str, str]:
        """Open a borderless fullscreen spectator window on one display."""

        screens = list(webview.screens)
        screen = selected_screen(screens, display_index)
        if screen is None:
            message = f"DISPLAY NOT FOUND: Display {display_index + 1}"
            self.application.spectator_closed(message)
            return self._set_status(message)

        with self._lock:
            previous, self.spectator_window = self.spectator_window, None
        if previous is not None:
            previous.destroy()

        spectator = webview.create_window(
            "Scoreboard display",
            url=view_url("spectator"),
            js_api=SpectatorBridge(self._spectator_snapshot),
            screen=screen,
            fullscreen=True,
            frameless=True,
            resizable=False,
            focus=False,
        )
        if spectator is None:
            self.application.spectator_closed("The display window could not be created.")
            return self._set_status("DISPLAY CLOSED: spectator window could not be created")
        spectator.events.closed += self._spectator_closed
        with self._lock:
            self.spectator_window = spectator

        target = f"Display {display_index + 1}"
        self.application.spectator_opened(target)
        return self._set_status(f"DISPLAY OPEN: {target} (fullscreen)")

    def reopen_spectator(self) -> dict[str, str]:
        """One-click recovery from the operator's health strip (D-005)."""

        return self.open_spectator(self.initial_display_index)

    def toggle_spectator_fullscreen(self) -> dict[str, str]:
        with self._lock:
            spectator = self.spectator_window
        if spectator is None:
            return self._set_status("DISPLAY CLOSED: Select a display and reopen it")
        spectator.toggle_fullscreen()
        return self._set_status("DISPLAY OPEN: fullscreen toggled")

    def _spectator_closed(self, window: webview.Window) -> None:
        with self._lock:
            if self.spectator_window is not window:
                # A late close event from a window that has already been
                # replaced must not clear the new one.
                return
            self.spectator_window = None
        # Clocks and the operator continue; only the health strip changes.
        self.application.spectator_closed()
        self._set_status("DISPLAY CLOSED: Select a display and reopen it")

    # --- Publishing ---------------------------------------------------------

    def _spectator_snapshot(self) -> dict[str, Any]:
        if self.application.bridge is None:
            return {}
        return self.application.bridge.spectator_snapshot()

    def _push(self, window_name: str, view: dict[str, Any]) -> None:
        with self._lock:
            window = (
                self.operator_window
                if window_name == "operator"
                else self.spectator_window
            )
        if window is None or not window.events.loaded.is_set():
            return
        window.evaluate_js(f"window.applyView && window.applyView({_json(view)})")

    def _set_status(self, message: str) -> dict[str, str]:
        with self._lock:
            self.status = message
        return {"message": message}


def _json(payload: dict[str, Any]) -> str:
    # allow_nan=False so a malformed number becomes a visible error here rather
    # than invalid JavaScript inside the window.
    return json.dumps(payload, allow_nan=False)


__all__ = [
    "REFRESH_INTERVAL_SECONDS",
    "RecoveryChoiceRequired",
    "ScoreboardApplication",
    "WindowHost",
    "view_url",
]
