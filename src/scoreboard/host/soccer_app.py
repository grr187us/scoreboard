"""Soccer's application host object: mirrors ``host/app.py``'s
``ScoreboardApplication`` (spec section 2.2/2.3; signatures per
``.scratch/soccer-mode/api_domain.md``).

``SoccerApplication`` is a parallel class, not a subclass: football's
``ScoreboardApplication`` is frozen (spec 2.4), and there is nothing left to
inherit from it once every constructed collaborator (service, store, bridge,
rules, cutscenes) is soccer's own. It owns the soccer game, its storage under
``<root>/soccer/`` and the health of the spectator window exactly the way
``ScoreboardApplication`` owns football's, and exposes the identical public
surface (``can_resume``, ``recovery_payload``, ``resume``, ``start_new``,
``tick``, ``set_publisher``, ``set_field_assistant_active``,
``set_cutscenes_active``, ``set_display_watch``, ``start_refresh``,
``stop_refresh``, ``display``, ``layouts``, ``teams``, ``rules``,
``cutscenes``, ``shutdown``, ``reopen_spectator``, ``close_spectator``,
``spectator_opened``/``closed``, ``profile``) so ``WindowHost`` drives either
application identically -- the only "if sport" decision anywhere in the
feature lives in ``host/app.py``'s ``SportProfile`` lookups (spec 2.3).

``paths`` passed to the constructor is the **root** ``ScoreboardPaths``
(``resolve_paths()``'s object, the same one ``ScoreboardApplication`` takes).
``self.paths`` is that root's ``for_sport("soccer")`` -- everything soccer
owns lives under ``<root>/soccer/`` -- while ``self.root_paths`` keeps the
original root object, because ``teams.json`` (spec F4) is shared with
football and must never move under the soccer subfolder (see
``ScoreboardPaths.for_sport``'s docstring).

Agents D (presentation), F (cutscenes), and G (field assistant) build the
soccer layout registry, cutscene director, and field-assistant bridge as
separate modules; each is imported lazily below with a football/plain
fallback so this module works before those land. ``# TODO(integrator):``
marks each fallback for removal once every agent's module exists.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from scoreboard.application.recovery import RecoverySource
from scoreboard.application.soccer_recovery import (
    inspect_soccer_recovery,
    resume_recovered_soccer_game,
    start_new_soccer_game,
)
from scoreboard.application.soccer_service import SoccerService
from scoreboard.domain.soccer.rules import read_soccer_rules, write_soccer_rules, SoccerRules
from scoreboard.host.app import SportProfile, _PublishBatch
from scoreboard.host.bridge import DisplayLink
from scoreboard.host.hotkeys import HotkeyBinding
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.host.soccer_bridge import SoccerBridge, soccer_spectator_view_model
from scoreboard.host.soccer_hotkeys import SOCCER_HOTKEY_TABLE
from scoreboard.host.teams import TeamPresets
from scoreboard.infrastructure.diagnostics import Diagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths, resolve_paths
from scoreboard.infrastructure.persistence import InstanceLock
from scoreboard.infrastructure.soccer_store import SoccerGameStore

try:  # pragma: no cover - agent D's module; present once phase 4 lands
    from scoreboard.presentation import soccer_layout as _soccer_layout_module
except ImportError:  # pragma: no cover
    # TODO(integrator): remove this fallback once presentation/soccer_layout.py exists.
    _soccer_layout_module = None  # type: ignore[assignment]

try:  # pragma: no cover - agent F's module; present once phase 5 lands
    from scoreboard.host.soccer_cutscenes import (
        SoccerCutsceneDirector,
        SoccerCutscenesBridge,
    )
except ImportError:  # pragma: no cover

    # TODO(integrator): remove this fallback once host/soccer_cutscenes.py exists.
    SoccerCutsceneDirector = None  # type: ignore[assignment,misc]

    class SoccerCutscenesBridge:  # type: ignore[no-redef]
        """Placeholder until agent F's real bridge lands. Read-only, unavailable."""

        def __init__(self, director: Any, operator: Any) -> None:
            self._operator = operator

        def get_snapshot(self) -> dict[str, Any]:
            return self._operator.get_snapshot()

try:  # pragma: no cover - agent G's module; present once phase 6 lands
    from scoreboard.host.soccer_field_assistant import SoccerFieldAssistantBridge
except ImportError:  # pragma: no cover

    # TODO(integrator): remove this fallback once host/soccer_field_assistant.py exists.
    class SoccerFieldAssistantBridge:  # type: ignore[no-redef]
        """Placeholder until agent G's real bridge lands. Read-only, unavailable."""

        def __init__(self, operator: Any) -> None:
            self._operator = operator

        def get_snapshot(self) -> dict[str, Any]:
            return self._operator.get_snapshot()


#: Soccer's profile (spec 2.3): its own operator/startup/spectator/field
#: assistant/cutscenes views, its own bridges, and F21/F22 only.
SOCCER_PROFILE: SportProfile = SportProfile(
    sport="soccer",
    operator_view="soccer_operator",
    startup_view="soccer_startup",
    spectator_view="soccer_spectator",
    field_assistant_view="soccer_field_assistant",
    cutscenes_view="soccer_cutscenes",
    field_assistant_bridge=SoccerFieldAssistantBridge,
    cutscenes_bridge=SoccerCutscenesBridge,
    hotkey_table=SOCCER_HOTKEY_TABLE,
    layout_view="soccer_layout",
)


class SoccerApplication:
    """Owns the soccer game, its storage, and the health of its spectator window."""

    def __init__(
        self,
        paths: ScoreboardPaths | None = None,
        *,
        monotonic_clock: Callable[[], float] | None = None,
        diagnostics: Diagnostics | None = None,
        acquire_lock: bool = True,
    ) -> None:
        #: The root paths (shared with football; holds ``teams.json``).
        self.root_paths = (resolve_paths() if paths is None else paths).ensure()
        #: Everything soccer owns lives under ``<root>/soccer/``.
        self.paths = self.root_paths.for_sport("soccer").ensure()
        self.profile: SportProfile = SOCCER_PROFILE
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
        self.diagnostics.startup(app_version="soccer-0.1.0")

        self.report = inspect_soccer_recovery(self.paths, diagnostics=self.diagnostics)
        self.service: SoccerService | None = None
        self.store: SoccerGameStore | None = None
        self.bridge: SoccerBridge | None = None
        # DisplayLink is sport-agnostic by construction (host/bridge.py); a
        # soccer session gets its own instance, exactly like football's.
        self.display = DisplayLink()
        try:
            self.layouts = PresentationLayouts(
                self.paths, diagnostics=self.diagnostics, layout_module=_soccer_layout_module
            )
        except AttributeError:
            # TODO(integrator): remove this fallback once
            # presentation/soccer_layout.py exposes the full schema contract
            # infrastructure/layouts.py expects (agent D, still in progress).
            self.layouts = PresentationLayouts(self.paths, diagnostics=self.diagnostics)
        # Shared with football (spec F4): saved teams live at the root, not
        # under <root>/soccer/.
        self.teams = TeamPresets(self.root_paths, diagnostics=self.diagnostics)
        self.rules: SoccerRules = read_soccer_rules(self.paths)
        if SoccerCutsceneDirector is None:  # pragma: no cover - agent F not finished yet
            self.cutscenes: Any = None
        else:
            self.cutscenes = SoccerCutsceneDirector(
                self.paths,
                diagnostics=self.diagnostics,
                monotonic=self._monotonic,
                read_spectator_view=self._read_spectator_view,
                read_board_layout=self.layouts.current_layout,
            )
        self._push: Callable[[str, dict[str, Any]], None] | None = None
        self._field_assistant_active: Callable[[], bool] | None = None
        self._cutscenes_active: Callable[[], bool] | None = None
        self._display_watch: Callable[[], None] | None = None
        self._command_lock = threading.RLock()
        self._stopping = threading.Event()
        self._refresh: threading.Thread | None = None
        self._publish_seq = 0
        self._publish_lock = threading.Lock()
        self._last_delivered_key: tuple[int, int] | None = None

    # --- The operator's startup choice --------------------------------------

    @property
    def can_resume(self) -> bool:
        return self.report.can_resume

    def recovery_payload(self) -> dict[str, Any]:
        """The JSON-compatible recovery report the operator chooses from."""

        payload = self.report.to_dict()
        payload["view"] = (
            None if self.report.state is None
            else soccer_spectator_view_model(self.report.state, rules=self.rules)
        )
        return payload

    def resume(self) -> SoccerBridge:
        """Continue the recovered game, with every clock stopped."""

        service = resume_recovered_soccer_game(
            self.report, monotonic_clock=self._monotonic, rules=self.rules
        )
        return self._begin(service, resume_game_id=self.report.game_id)

    def start_new(self) -> SoccerBridge:
        """Begin a clean game. Nothing already on disk is deleted."""

        service = start_new_soccer_game(monotonic_clock=self._monotonic, rules=self.rules)
        return self._begin(service, resume_game_id=None)

    def _begin(
        self, service: SoccerService, *, resume_game_id: int | None
    ) -> SoccerBridge:
        store = SoccerGameStore.open(
            self.paths,
            diagnostics=self.diagnostics,
            using_backup=self.report.source is RecoverySource.BACKUP,
        )
        store.begin_session(service.state, resume_game_id=resume_game_id)
        self.service = service
        self.store = store
        self.display.reopen = self.reopen_spectator  # type: ignore[method-assign]
        self.display.close = self.close_spectator  # type: ignore[method-assign]
        self.bridge = SoccerBridge(
            service,
            store,
            display=self.display,
            diagnostics=self.diagnostics,
            lock=self._command_lock,
            on_accepted=self._publish,
            layouts=self.layouts,
            teams=self.teams,
            cutscenes=self.cutscenes,
            rules_writer=self._write_rules,
        )
        return self.bridge

    def _write_rules(self, rules: SoccerRules) -> bool:
        self.rules = rules
        return write_soccer_rules(self.paths, rules)

    def _read_spectator_view(self) -> dict[str, Any]:
        if self.bridge is None:
            return {}
        return self.bridge.spectator_snapshot()

    # --- Refresh loop --------------------------------------------------------

    def tick(self, now: float | None = None) -> dict[str, Any] | None:
        if self.bridge is None:
            return None
        with self._command_lock:
            self._watch_displays()
            view = self.bridge.tick(now)
            batch = self._snapshot(view)
        self._deliver(batch)
        return view

    def set_display_watch(self, watch: Callable[[], None] | None) -> None:
        self._display_watch = watch

    def _watch_displays(self) -> None:
        if self._display_watch is None:
            return
        try:
            self._display_watch()
        except Exception as exc:  # noqa: BLE001 - a display fault must not end a game
            self.diagnostics.unhandled_error(context="display_watch", error=exc)
            self._display_watch = None

    def start_refresh(self, interval: float = 0.1) -> None:
        if self._refresh is not None:
            return
        self._stopping.clear()

        def loop() -> None:
            while not self._stopping.wait(interval):
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001 - a repaint must not end the game
                    self.diagnostics.unhandled_error(context="refresh", error=exc)

        self._refresh = threading.Thread(target=loop, name="soccer-refresh", daemon=True)
        self._refresh.start()

    def stop_refresh(self) -> None:
        self._stopping.set()
        thread, self._refresh = self._refresh, None
        if thread is not None:
            thread.join(timeout=2.0)

    # --- Publishing to the windows -------------------------------------------

    def set_publisher(self, push: Callable[[str, dict[str, Any]], None] | None) -> None:
        self._push = push

    def set_field_assistant_active(self, active: Callable[[], bool] | None) -> None:
        self._field_assistant_active = active

    def set_cutscenes_active(self, active: Callable[[], bool] | None) -> None:
        self._cutscenes_active = active

    def _publish(self, operator_view: dict[str, Any]) -> None:
        if self.bridge is None:
            return
        batch = self._snapshot(operator_view)
        self._deliver(batch)

    def _snapshot(self, operator_view: dict[str, Any]) -> _PublishBatch:
        with self._command_lock:
            self._publish_seq += 1
            spectator_view = (
                {} if self.bridge is None else self.bridge.spectator_snapshot()
            )
            revision = (
                operator_view.get("revision", 0)
                if isinstance(operator_view, dict)
                else 0
            )
            return _PublishBatch(self._publish_seq, revision, operator_view, spectator_view)

    def _deliver(self, batch: _PublishBatch) -> None:
        if self._push is None or self.bridge is None:
            return
        with self._publish_lock:
            key = (batch.revision, batch.seq)
            if self._last_delivered_key is not None and key < self._last_delivered_key:
                return
            self._last_delivered_key = key
        try:
            self._push("operator", batch.operator_view)
        except Exception as exc:  # noqa: BLE001
            self.diagnostics.unhandled_error(context="operator_push", error=exc)
        try:
            self._push("spectator", batch.spectator_view)
        except Exception as exc:  # noqa: BLE001
            self.diagnostics.unhandled_error(context="spectator_push", error=exc)
            self.bridge.display_closed(f"The display stopped responding: {exc}")
        if self._field_assistant_active is not None and self._field_assistant_active():
            try:
                self._push("field_assistant", batch.operator_view)
            except Exception as exc:  # noqa: BLE001
                self.diagnostics.unhandled_error(context="field_assistant_push", error=exc)
        if self._cutscenes_active is not None and self._cutscenes_active():
            try:
                self._push("cutscenes", batch.operator_view)
            except Exception as exc:  # noqa: BLE001
                self.diagnostics.unhandled_error(context="cutscenes_push", error=exc)

    # --- Spectator health ------------------------------------------------------

    def reopen_spectator(self) -> Any:
        return self.display.status

    def close_spectator(self) -> Any:
        return self.display.status

    def spectator_opened(self, target: str | None = None) -> None:
        if self.bridge is not None:
            self._publish(self.bridge.display_opened(target))

    def spectator_closed(
        self, detail: str = "The spectator window is closed.", *, needs_selection: bool = False,
    ) -> None:
        if self.bridge is not None:
            self._publish(
                self.bridge.display_closed(detail, needs_selection=needs_selection)
            )

    # --- Shutdown ---------------------------------------------------------------

    def shutdown(self, reason: str = "clean") -> None:
        self.stop_refresh()
        if self.bridge is not None:
            try:
                self.bridge.shutdown()
            except Exception as exc:  # noqa: BLE001
                self.diagnostics.unhandled_error(context="shutdown_save", error=exc)
        if self.cutscenes is not None:
            try:
                self.cutscenes.shutdown()
            except Exception as exc:  # noqa: BLE001 - shutdown must never raise
                self.diagnostics.unhandled_error(context="cutscenes_shutdown", error=exc)
        if self.store is not None:
            self.store.close()
        self.diagnostics.shutdown(reason=reason)
        self.diagnostics.close()
        if self._lock is not None:
            self._lock.release()
            self._lock = None


__all__ = ["SOCCER_PROFILE", "SoccerApplication"]
