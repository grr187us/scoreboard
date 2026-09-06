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

Task 10 added the display half of that promise. The spectator window is placed
on a *remembered display* rather than a list position, the host looks
periodically for that display appearing or disappearing, and none of it can
touch the game: selecting, reopening, losing, and forgetting a display all
advance no revision and write nothing to the game database. When the saved
display is missing, nothing is opened and the operator is asked -- a fullscreen
board that lands on top of the controls during a game is the one outcome worth
refusing outright (D-002, D-006).
"""

from __future__ import annotations

import json
import sys
import threading
import time
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
    FieldAssistantBridge,
    ScoreboardBridge,
    SpectatorBridge,
    spectator_view_model,
)
from scoreboard.host.layout_bridge import LayoutEditorBridge, PresentationLayouts
from scoreboard.host.startup import StartupBridge
from scoreboard.host.displays import (
    MATCH_CHOSEN,
    MATCH_DEFAULT,
    MATCH_INDEX,
    MATCH_NONE,
    RECOGNISED_MATCHES,
    DisplayMatch,
    DisplayPreference,
    DisplayTarget,
    DisplayWatch,
    default_target,
    enumerate_displays,
    find_by_key,
    match_preference,
    preference_from_dict,
    selected_screen,
)
from scoreboard.infrastructure import config
from scoreboard.infrastructure.diagnostics import Diagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths, resolve_paths
from scoreboard.infrastructure.persistence import GameStore, InstanceLock

def _views_directory() -> Path:
    """Where the bundled pages live, in a checkout and in a frozen build.

    PyInstaller unpacks bundled data under ``sys._MEIPASS`` rather than beside
    the source file, so resolving relative to ``__file__`` alone would find
    nothing in a packaged application. Both layouts keep the same
    ``scoreboard/views`` shape, so only the root differs (W-003, W-006).
    """

    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "scoreboard" / "views"
    return Path(__file__).resolve().parent.parent / "views"


VIEWS = _views_directory()

#: Ten refreshes a second lets a tenths readout present every descending digit.
#: The checkpoint policy remains keyed to displayed seconds, not refreshes.
REFRESH_INTERVAL_SECONDS: float = 0.1

#: A faithful, side-by-side 16:9 spectator preview for practice. This is not
#: the fullscreen production display and is deliberately not configurable.
TEST_SPECTATOR_WIDTH: int = 640
TEST_SPECTATOR_HEIGHT: int = 360

#: How often the host looks at the list of connected displays. Windows offers
#: no event pywebview passes on, so noticing an unplugged LED wall means
#: asking. Two seconds is fast enough that the operator learns about it during
#: the same dead ball, and slow enough that it is one Windows call per eight
#: refreshes rather than one per refresh.
DISPLAY_WATCH_INTERVAL_SECONDS: float = 2.0


def windows_device_names() -> list[str | None]:
    """Best-effort Windows device names, in ``webview.screens`` order.

    pywebview's ``Screen`` carries geometry and a scale but not the device
    name, and a name is the sturdiest half of a display identity: it survives
    the resolution change that a stadium processor can produce on its own.
    pywebview builds its own list from ``WinForms.Screen.AllScreens`` in that
    enumeration's order, so asking the same source in the same way produces a
    list that lines up position for position. ``available_displays`` still
    refuses to use the names unless the two lists are the same length, because
    a name attached to the wrong monitor would be worse than no name at all.

    Every failure returns an empty list. pythonnet is a pinned dependency that
    already ships in the package, but this is an *enhancement* to the identity,
    never a requirement for it: with no names at all, matching falls back to
    geometry and the scoreboard behaves exactly as well as it did a moment
    before.
    """

    try:
        import clr  # noqa: F401 - importing clr is what makes System available

        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Screen as WinFormsScreen  # type: ignore

        return [str(screen.DeviceName) for screen in WinFormsScreen.AllScreens]
    except Exception:  # noqa: BLE001 - an optional identity, never a blocker
        return []


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
        # Created before any game exists, exactly like ``self.display``: the
        # presentation layout is a host concern, not game state, so it must
        # survive across a recovered/new-game choice untouched (spec 6.2).
        self.layouts = PresentationLayouts(self.paths, diagnostics=self.diagnostics)
        self._push: Callable[[str, dict[str, Any]], None] | None = None
        # WindowHost owns this optional surface.  Keeping the predicate here
        # means normal two-window application tests do not receive a third
        # publication, while an open helper sees every complete revision.
        self._field_assistant_active: Callable[[], bool] | None = None
        self._display_watch: Callable[[], None] | None = None
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
            on_accepted=self._publish,
            layouts=self.layouts,
        )
        return self.bridge

    # --- Refresh loop -------------------------------------------------------

    def tick(self, now: float | None = None) -> dict[str, Any] | None:
        """One refresh: checkpoint if the displayed second changed, then push."""

        if self.bridge is None:
            return None
        with self._command_lock:
            self._watch_displays()
            view = self.bridge.tick(now)
            self._publish(view)
            return view

    def set_display_watch(self, watch: Callable[[], None] | None) -> None:
        """Install the host's periodic check for a display appearing or going.

        Separated so the window-free application can be driven in a test with a
        fake screen list, which is the only way a second display can be
        unplugged on a development host that has one.
        """

        self._display_watch = watch

    def _watch_displays(self) -> None:
        if self._display_watch is None:
            return
        try:
            self._display_watch()
        except Exception as exc:  # noqa: BLE001 - looking at monitors must not
            # end a game. If Windows will not tell us what is connected, the
            # scoreboard keeps running and the operator keeps their controls.
            #
            # The watch is then switched off for the rest of the session rather
            # than retried: it samples twice a second at most, and a permanent
            # fault would otherwise fill the log for the whole game. The cost
            # is that a later disconnect is no longer announced on its own --
            # the operator's display list still reads live, and the failure is
            # in the log with the reason.
            self.diagnostics.unhandled_error(context="display_watch", error=exc)
            self._display_watch = None

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

    def set_field_assistant_active(self, active: Callable[[], bool] | None) -> None:
        """Tell publishing whether the optional helper window is open."""

        self._field_assistant_active = active

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
        if self._field_assistant_active is not None and self._field_assistant_active():
            try:
                # Same complete operator snapshot the primary controls get;
                # the helper compares its base revision and visibly marks an
                # outstanding draft stale instead of merging it.
                self._push("field_assistant", operator_view)
            except Exception as exc:  # noqa: BLE001 - optional window only
                self.diagnostics.unhandled_error(context="field_assistant_push", error=exc)

    # --- Spectator health ---------------------------------------------------

    def reopen_spectator(self) -> Any:
        """Replaced by :class:`WindowHost`; alone this opens no window."""

        return self.display.status

    def spectator_opened(self, target: str | None = None) -> None:
        if self.bridge is not None:
            self._publish(self.bridge.display_opened(target))

    def spectator_closed(
        self,
        detail: str = "The spectator window is closed.",
        *,
        needs_selection: bool = False,
    ) -> None:
        # Clocks keep running and the operator stays open (D-005).
        # ``needs_selection`` distinguishes "closed, one click reopens it" from
        # "the display is gone, and only you can say which one to use now".
        if self.bridge is not None:
            self._publish(
                self.bridge.display_closed(detail, needs_selection=needs_selection)
            )

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
        initial_display_index: int | None = None,
        auto_close_after_seconds: float | None = None,
        read_screens: Callable[[], list[Any]] | None = None,
        read_device_names: Callable[[], list[str | None]] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        if auto_close_after_seconds is not None and auto_close_after_seconds <= 0:
            raise ValueError("--auto-close-after-seconds must be greater than zero")
        self.application = application
        #: An explicit ``--display-index``. ``None`` means "use the saved
        #: display", which is the normal path; the index remains for a
        #: technician who needs to force one from a terminal.
        self.initial_display_index = initial_display_index
        self.auto_close_after_seconds = auto_close_after_seconds
        self.startup_window: webview.Window | None = None
        self.operator_window: webview.Window | None = None
        self.spectator_window: webview.Window | None = None
        # A practice-only window. It has no display-selection or health role.
        self.test_window: webview.Window | None = None
        # The presentation layout editor. Like the test window, it has no
        # display-selection or health role and no path to a game command.
        self.layout_window: webview.Window | None = None
        # A similarly sized, deliberately opened operational aid.  It has no
        # display-selection role and no authority over the game.
        self.field_assistant_window: webview.Window | None = None
        self.status = "STARTING"
        self._lock = threading.RLock()
        # Injected so every display behaviour below can be exercised without a
        # window and without a second monitor. Production reads pywebview.
        self._read_screens = read_screens or (lambda: list(webview.screens))
        self._read_device_names = read_device_names or windows_device_names
        self._current: DisplayTarget | None = None
        self._watch = DisplayWatch(
            self.available_displays,
            monotonic=monotonic or time.monotonic,
            interval=DISPLAY_WATCH_INTERVAL_SECONDS,
        )
        application.set_publisher(self._push)
        application.set_display_watch(self.check_displays)
        application.reopen_spectator = self.reopen_spectator  # type: ignore[method-assign]
        application.display.reopen = self.reopen_spectator  # type: ignore[method-assign]
        application.display.list_displays = self.list_displays  # type: ignore[method-assign]
        application.display.select = self.select_display  # type: ignore[method-assign]
        application.display.forget = self.forget_display  # type: ignore[method-assign]
        application.display.open_test_window = self.open_test_window  # type: ignore[method-assign]
        application.layouts.link.open_editor = self.open_layout_editor  # type: ignore[method-assign]
        application.layouts.link.publish = self.publish_layout  # type: ignore[method-assign]
        application.set_field_assistant_active(
            lambda: self.field_assistant_window is not None
        )

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
            bridge.set_field_assistant_opener(self.open_field_assistant)
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
        # Opening the spectator window is the one startup step that asks
        # Windows a question -- "what displays are there?" -- and WinForms'
        # Screen.AllScreens is known to throw intermittently while a monitor
        # or dock is settling. Before this guard, that exception escaped here
        # and the line below never ran: start_refresh() has exactly one
        # caller, so the 10 Hz tick loop (and with it every checkpoint and
        # every clock repaint between button presses) was dead for the life of
        # the process, with nothing in the log to say so. The display is
        # something the operator can fix from the health strip; a refresh loop
        # that never started is not.
        try:
            self.open_spectator(self.initial_display_index)
        except Exception as exc:  # noqa: BLE001 - a display problem must not stop the clock
            self.application.diagnostics.unhandled_error(
                context="open_spectator_at_startup", error=exc
            )
            self.application.spectator_closed(
                "DISPLAY NOT OPENED: the displays could not be read at startup. "
                "Use Reopen Display or pick a display.",
                needs_selection=True,
            )
        self.application.start_refresh()

    def _operator_closing(self) -> None:
        with self._lock:
            self.status = "SHUTTING DOWN"
            spectator = self.spectator_window
            test_window = self.test_window
            layout_window = self.layout_window
            field_assistant_window = self.field_assistant_window
            self.spectator_window = None
            self.test_window = None
            self.layout_window = None
            self.field_assistant_window = None
        self.application.stop_refresh()
        if spectator is not None:
            spectator.destroy()
        if test_window is not None:
            test_window.destroy()
        if layout_window is not None:
            layout_window.destroy()
        if field_assistant_window is not None:
            field_assistant_window.destroy()

    # --- Windows ------------------------------------------------------------

    def available_displays(self) -> list[DisplayTarget]:
        """Every display Windows is reporting right now, with its identity."""

        screens = list(self._read_screens())
        names: list[str | None] = []
        try:
            read = list(self._read_device_names())
        except Exception:  # noqa: BLE001 - an optional identity, never a blocker
            read = []
        # Only trust the names when the two enumerations agree on how many
        # displays there are. A name on the wrong monitor is worse than none.
        if len(read) == len(screens):
            names = list(read)
        return enumerate_displays(screens, names or None)

    # --- The remembered display ---------------------------------------------

    def saved_display(self) -> DisplayPreference | None:
        """The display the operator chose, or ``None``.

        A preference that cannot be read is not an error worth reporting to the
        operator mid-game: it reads as "nothing saved", the scoreboard starts,
        and one click sets it again (see ``infrastructure.config``).
        """

        return preference_from_dict(
            config.read_section(self.application.paths, config.DISPLAY_SECTION)
        )

    def remember_display(self, target: DisplayTarget) -> None:
        """Store ``target`` as the display to look for next time."""

        preference = target.as_preference()
        stored = config.write_section(
            self.application.paths, config.DISPLAY_SECTION, preference.to_dict()
        )
        if not stored:
            # Worth a log line and nothing more. The window is already open on
            # the right screen; only the memory of it failed.
            self.application.diagnostics.note(
                "DISPLAY_PREFERENCE_NOT_SAVED", target=preference.label
            )

    def forget_display(self) -> dict[str, str]:
        """Forget the saved display. The open window is deliberately untouched."""

        config.write_section(self.application.paths, config.DISPLAY_SECTION, None)
        self.application.diagnostics.note("DISPLAY_PREFERENCE_CLEARED")
        return {"message": "The saved display was forgotten."}

    def resolve_target(
        self, *, key: Any = None, index: int | None = None
    ) -> DisplayMatch:
        """Decide which display a request means, without opening anything.

        Precedence: an explicit choice from the operator view, then an explicit
        ``--display-index``, then the saved display, then -- only when nothing
        has ever been saved -- the first non-primary display. There is no
        fallback past that point: an unresolved request reports
        ``DISPLAY NOT FOUND`` rather than covering the operator's screen
        (D-002).
        """

        displays = self.available_displays()

        if key is not None:
            target = find_by_key(key, displays)
            if target is None:
                return DisplayMatch(
                    None,
                    MATCH_NONE,
                    "DISPLAY NOT FOUND: that display is no longer connected. "
                    "Choose another one.",
                )
            return DisplayMatch(target, MATCH_CHOSEN, f"Using {target.description}.")

        if index is not None:
            if not 0 <= index < len(displays):
                return DisplayMatch(
                    None, MATCH_NONE, f"DISPLAY NOT FOUND: Display {index + 1}"
                )
            chosen = displays[index]
            return DisplayMatch(chosen, MATCH_INDEX, f"Using {chosen.description}.")

        preference = self.saved_display()
        if preference is not None:
            return match_preference(preference, displays)

        fallback = default_target(displays)
        if fallback is None:
            return DisplayMatch(
                None,
                MATCH_NONE,
                (
                    "No second display is connected, so the spectator board was "
                    "not opened over your controls. Connect the display and "
                    "choose it, or choose this screen deliberately."
                ),
            )
        return DisplayMatch(
            fallback,
            MATCH_DEFAULT,
            f"No display saved yet; using {fallback.description}.",
        )

    # --- Opening the spectator window ---------------------------------------

    def open_spectator(
        self,
        display_index: int | None = None,
        *,
        key: Any = None,
        remember: bool = False,
    ) -> dict[str, str]:
        """Open a borderless fullscreen spectator window on one display.

        ``remember`` is true only when the operator picked this display, which
        is the one thing that re-points the saved display. A match that found
        the *same* display refreshes what is stored about it, so a resolution
        change is recorded, but it can never turn the preference into a
        different monitor.
        """

        match = self.resolve_target(key=key, index=display_index)
        if match.target is None:
            self.application.spectator_closed(match.message, needs_selection=True)
            return self._set_status(match.message)
        target = match.target

        with self._lock:
            previous, self.spectator_window = self.spectator_window, None
        if previous is not None:
            previous.destroy()

        screen = selected_screen(list(self._read_screens()), target.index)
        if screen is None:
            message = (
                "DISPLAY NOT FOUND: that display disappeared while it was being "
                "opened. The game is unaffected; choose a display."
            )
            self.application.spectator_closed(message, needs_selection=True)
            return self._set_status(message)

        spectator = webview.create_window(
            "Scoreboard display",
            url=view_url("spectator"),
            js_api=SpectatorBridge(
                self._spectator_snapshot, read_layout=self.application.layouts.current_layout
            ),
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
            self._current = target

        # Remember on an explicit choice, and refresh the record whenever the
        # saved display was recognised -- same display, current geometry.
        if remember or match.how in RECOGNISED_MATCHES:
            self.remember_display(target)

        self.application.spectator_opened(target.description)
        # The page also pulls its own layout on load (get_layout()), but
        # pushing it here means a spectator opened mid-game shows the right
        # layout immediately rather than waiting on the next save (spec 6.2).
        self.publish_layout(self.application.layouts.current_layout())
        self.application.diagnostics.note(
            "DISPLAY_SELECTED", target=target.description, how=match.how
        )
        return self._set_status(f"DISPLAY OPEN: {target.label} (fullscreen)")

    def reopen_spectator(self) -> dict[str, str]:
        """One-click recovery from the operator's health strip (D-005).

        It reopens on the saved display when that display is present. When it
        is not, nothing is opened and the status says the operator has to
        choose -- which is the point: this button must never be the thing that
        puts the spectator board on top of the controls.
        """

        return self.open_spectator(self.initial_display_index)

    def select_display(self, key: Any) -> dict[str, str]:
        """The operator picked a display. Open it there and remember it."""

        return self.open_spectator(key=key, remember=True)

    def open_test_window(self) -> dict[str, str]:
        """Open a fixed-size spectator preview for side-by-side practice.

        This window is neither fullscreen nor tied to a Windows display. It
        intentionally bypasses display selection, saved preferences, and the
        production spectator health lifecycle.
        """

        with self._lock:
            previous, self.test_window = self.test_window, None
        if previous is not None:
            previous.destroy()

        test_window = webview.create_window(
            "Scoreboard display (test)",
            url=view_url("spectator"),
            js_api=SpectatorBridge(
                self._spectator_snapshot, read_layout=self.application.layouts.current_layout
            ),
            width=TEST_SPECTATOR_WIDTH,
            height=TEST_SPECTATOR_HEIGHT,
            frameless=False,
            resizable=False,
        )
        if test_window is None:
            raise RuntimeError("The test spectator window could not be created.")
        test_window.events.closed += self._test_window_closed
        with self._lock:
            self.test_window = test_window
        return {"message": "Test spectator window opened."}

    def open_layout_editor(self) -> dict[str, str]:
        """Open the presentation layout editor window.

        Like :meth:`open_test_window`, this bypasses display selection and
        saved preferences entirely, and it advances no revision. The editor's
        ``js_api`` is :class:`~scoreboard.host.layout_bridge.LayoutEditorBridge`,
        which reads the live spectator snapshot and the layout library but has
        no path to a game command.
        """

        with self._lock:
            previous, self.layout_window = self.layout_window, None
        if previous is not None:
            previous.destroy()

        layout_window = webview.create_window(
            "Presentation layout",
            url=view_url("layout"),
            js_api=LayoutEditorBridge(self.application.layouts, self._spectator_snapshot),
            width=1220,
            height=780,
            min_size=(980, 620),
        )
        if layout_window is None:
            raise RuntimeError("The layout editor window could not be created.")
        layout_window.events.closed += self._layout_window_closed
        with self._lock:
            self.layout_window = layout_window
        return {"message": "Presentation layout editor opened."}

    def open_field_assistant(self) -> dict[str, str]:
        """Open (or deliberately replace) the optional Field Assistant.

        A helper close/failure must never stop clocks, close the operator, or
        change persistence.  Replacing the window reads from the same bridge,
        so its load request always receives the latest complete snapshot.
        """

        bridge = self.application.bridge
        if bridge is None:
            return {"message": "Start or recover a game before opening Field Assistant."}
        with self._lock:
            previous, self.field_assistant_window = self.field_assistant_window, None
        if previous is not None:
            try:
                previous.destroy()
            except Exception as exc:  # noqa: BLE001 - prior helper is optional
                self.application.diagnostics.unhandled_error(
                    context="destroy_field_assistant", error=exc
                )
        window = webview.create_window(
            "Field Assistant",
            url=view_url("field_assistant"),
            js_api=FieldAssistantBridge(bridge),
            width=1180,
            height=720,
            min_size=(1024, 600),
        )
        if window is None:
            return {"message": "The Field Assistant window could not be created."}
        window.events.closed += self._field_assistant_closed
        with self._lock:
            self.field_assistant_window = window
        return {"message": "Field Assistant opened with the latest field status."}

    def _field_assistant_closed(self, window: webview.Window) -> None:
        """Forget a manually closed helper without disturbing the game."""

        with self._lock:
            if self.field_assistant_window is window:
                self.field_assistant_window = None

    def publish_layout(self, layout: dict[str, Any]) -> None:
        """Push a changed presentation layout to every open board.

        Called whenever :class:`~scoreboard.host.layout_bridge.PresentationLayouts`
        saves, selects, or resets a layout, and once right after the spectator
        window opens. This changes no game state: a rendering failure in any
        one window is logged and the others are unaffected (R-002).
        """

        with self._lock:
            spectator = self.spectator_window
            test_window = self.test_window
            layout_window = self.layout_window
        script = f"window.applyLayout && window.applyLayout({_json(layout)})"
        for window, context in (
            (spectator, "spectator_layout_push"),
            (test_window, "test_spectator_layout_push"),
            (layout_window, "layout_editor_layout_push"),
        ):
            if window is not None and window.events.loaded.is_set():
                try:
                    window.evaluate_js(script)
                except Exception as exc:  # noqa: BLE001 - a layout push must not stop the game
                    self.application.diagnostics.unhandled_error(context=context, error=exc)

    def _layout_window_closed(self, window: webview.Window) -> None:
        """Forget a manually closed editor window without affecting the board."""

        with self._lock:
            if self.layout_window is window:
                self.layout_window = None

    def list_displays(self) -> dict[str, Any]:
        """What the operator's display panel renders. Opens and moves nothing."""

        displays = self.available_displays()
        preference = self.saved_display()
        match = match_preference(preference, displays)
        with self._lock:
            current = self._current
        return {
            "displays": [display.to_dict() for display in displays],
            "saved": None if preference is None else preference.to_dict(),
            "saved_label": None if preference is None else preference.label,
            "match": match.to_dict(),
            "current_key": None if current is None else current.key,
        }

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

    def _test_window_closed(self, window: webview.Window) -> None:
        """Forget a manually closed practice window without affecting the board."""

        with self._lock:
            if self.test_window is window:
                self.test_window = None

    # --- Noticing a display that came or went (D-006) -----------------------

    def check_displays(self) -> None:
        """Report a display appearing or disappearing. Moves nothing.

        Called from the refresh loop at a bounded cadence. If the display the
        spectator window is on has gone, the health strip says so and the
        operator is told they have to choose one; the clocks, the commands, and
        persistence are all untouched, because a monitor is not game state
        (D-006, R-002).
        """

        displays = self._watch.poll()
        if displays is None:
            return
        keys = {display.key for display in displays}
        with self._lock:
            current = self._current
            window = self.spectator_window

        if current is not None and current.key not in keys:
            message = (
                f"DISPLAY NOT FOUND: {current.label} is no longer connected. "
                "The game is still running and still saving. Reconnect it and "
                "choose it again when you are ready."
            )
            with self._lock:
                self._current = None
                self.spectator_window = None
            if window is not None:
                try:
                    window.destroy()
                except Exception as exc:  # noqa: BLE001
                    self.application.diagnostics.unhandled_error(
                        context="destroy_lost_spectator", error=exc
                    )
            self.application.spectator_closed(message, needs_selection=True)
            self._set_status(message)
            return

        # A display came back, or a different one appeared. Say so and stop
        # there: reopening is the operator's decision, never ours (D-006).
        preference = self.saved_display()
        match = match_preference(preference, displays)
        if match.found and self.application.display.status.needs_selection:
            self.application.spectator_closed(
                f"{match.message} Use Reopen Display when you are ready.",
                needs_selection=False,
            )
            self._set_status(f"DISPLAY CLOSED: {match.message}")

    # --- Publishing ---------------------------------------------------------

    def _spectator_snapshot(self) -> dict[str, Any]:
        if self.application.bridge is None:
            return {}
        return self.application.bridge.spectator_snapshot()

    def _push(self, window_name: str, view: dict[str, Any]) -> None:
        with self._lock:
            if window_name == "operator":
                operator = self.operator_window
                spectator = None
                test_window = None
                field_assistant = None
            elif window_name == "field_assistant":
                operator = None
                spectator = None
                test_window = None
                field_assistant = self.field_assistant_window
            else:
                operator = None
                spectator = self.spectator_window
                test_window = self.test_window
                field_assistant = None
        script = f"window.applyView && window.applyView({_json(view)})"
        if operator is not None and operator.events.loaded.is_set():
            operator.evaluate_js(script)
        if spectator is not None and spectator.events.loaded.is_set():
            spectator.evaluate_js(script)
        if test_window is not None and test_window.events.loaded.is_set():
            try:
                test_window.evaluate_js(script)
            except Exception as exc:  # noqa: BLE001 - practice aid only
                self.application.diagnostics.unhandled_error(
                    context="test_spectator_push", error=exc
                )
                with self._lock:
                    if self.test_window is test_window:
                        self.test_window = None
                try:
                    test_window.destroy()
                except Exception as destroy_exc:  # noqa: BLE001 - best effort only
                    self.application.diagnostics.unhandled_error(
                        context="destroy_test_spectator", error=destroy_exc
                    )
        if field_assistant is not None and field_assistant.events.loaded.is_set():
            try:
                field_assistant.evaluate_js(script)
            except Exception as exc:  # noqa: BLE001 - helper failure is isolated
                self.application.diagnostics.unhandled_error(
                    context="field_assistant_push", error=exc
                )
                with self._lock:
                    if self.field_assistant_window is field_assistant:
                        self.field_assistant_window = None
                try:
                    field_assistant.destroy()
                except Exception as destroy_exc:  # noqa: BLE001
                    self.application.diagnostics.unhandled_error(
                        context="destroy_field_assistant", error=destroy_exc
                    )

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
    "TEST_SPECTATOR_HEIGHT",
    "TEST_SPECTATOR_WIDTH",
    "RecoveryChoiceRequired",
    "ScoreboardApplication",
    "WindowHost",
    "view_url",
]
