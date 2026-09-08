"""Host object owning cutscene playback: what is playing, and when it ends.

Cutscenes are a host concern, exactly like the presentation layout and the
saved teams (see ``host/layout_bridge.py``'s docstring for the fuller
argument): no :class:`~scoreboard.domain.commands.Command`, no revision, no
history row, nothing in ``scoreboard.db``. This module owns *when* a
cutscene is playing and *what* was published; it never decides what the
spectator page actually draws -- :mod:`scoreboard.presentation.cutscenes`
builds the program, and ``cutscene.js`` interprets it.

:class:`CutsceneLink` mirrors :class:`~scoreboard.host.layout_bridge.
LayoutLink`: a tiny seam :class:`~scoreboard.host.app.WindowHost` replaces
individual methods on at wiring time, so every test in this module runs
without a webview. A ``publish``/``end`` failure must never reach the game
(R-002): both are wrapped in ``try``/``except`` and logged through
:class:`~scoreboard.infrastructure.diagnostics.Diagnostics` rather than
propagated -- the wall may simply not show the cutscene, but the timer that
ends it still runs.

Playback state (``_current``, ``_timer``, ``_play_id``) is guarded by a lock
so the ten-per-second view-build thread and a trigger/cancel/expire can never
observe a half-updated state; publishing and scheduling deliberately happen
*outside* that lock (spec section 4), because a slow or blocked webview push
must never hold up anything else reading ``status()``.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from scoreboard.infrastructure import cutscene_packs
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.presentation import cutscenes as cutscenes_module
from scoreboard.presentation import layout as layout_module

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a circular import
    from scoreboard.host.bridge import ScoreboardBridge


class CutsceneLink:
    """Mirrors LayoutLink. Overridden by WindowHost at wiring time.

    Left alone -- what every test that does not care about the window
    uses -- opening the window reports a plain-language "unavailable"
    message, and a publish/end is a silent no-op.
    """

    def open_window(self) -> dict[str, str]:
        return {"message": "The Cutscenes window is unavailable."}

    def publish(self, program: dict[str, Any]) -> None:
        return None

    def end(self, play_id: int) -> None:
        return None


def _default_schedule(delay_seconds: float, callback: Callable[[], None]) -> threading.Timer:
    """The production scheduler: a daemon ``threading.Timer``, already started."""

    timer = threading.Timer(max(0.0, delay_seconds), callback)
    timer.daemon = True
    timer.start()
    return timer


class CutsceneDirector:
    """Owns playback state, the pack library, and the end-of-play timer."""

    def __init__(
        self,
        paths: ScoreboardPaths,
        *,
        diagnostics: Diagnostics | None = None,
        monotonic: Callable[[], float] | None = None,
        schedule: Callable[[float, Callable[[], None]], Any] | None = None,
        read_spectator_view: Callable[[], dict[str, Any]] | None = None,
        read_layout: Callable[[], dict[str, Any]] | None = None,
        read_board_layout: Callable[[], dict[str, Any]] | None = None,
        folder_opener: Callable[[Any], None] | None = None,
    ) -> None:
        self._paths = paths
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        self._monotonic = time.monotonic if monotonic is None else monotonic
        self._schedule = _default_schedule if schedule is None else schedule
        self._read_spectator_view = read_spectator_view
        self._read_layout = read_layout
        self._read_board_layout = read_board_layout
        self._folder_opener = folder_opener

        #: Public; replaced (or monkey-patched method by method) by
        #: :class:`~scoreboard.host.app.WindowHost` at wiring time.
        self.link: CutsceneLink = CutsceneLink()

        self._lock = threading.Lock()
        self._play_id = 0
        # {"program": dict, "started_at": float, "pack_name": str} or None.
        self._current: dict[str, Any] | None = None
        self._timer: Any = None

        cutscene_packs.ensure_packs_directory(self._paths)
        self._library = cutscene_packs.library(self._paths)
        self._note_library_issues()

    # --- Library -------------------------------------------------------

    def _note_library_issues(self) -> None:
        for event in cutscenes_module.CUTSCENE_EVENTS:
            _pack, fell_back = self._library.resolve(event)
            if fell_back:
                # Diagnostics.note()'s own first parameter is named "event"
                # (the log line's event-type name), so the cutscene event id
                # is logged as "cutscene_event" here and in CUTSCENE_STARTED
                # below to avoid colliding with it.
                self._diagnostics.note("CUTSCENE_SELECTION_FELL_BACK", cutscene_event=event)
        for issue in self._library.issues:
            self._diagnostics.note(
                "CUTSCENE_PACK_REJECTED",
                pack_id=issue.get("pack_id"),
                code=issue.get("code"),
                message=issue.get("message"),
            )

    def _reload(self) -> None:
        self._library = cutscene_packs.library(self._paths)
        self._note_library_issues()

    def _resolve_layout(self) -> dict[str, Any]:
        if self._read_layout is not None:
            return self._read_layout()
        return next(
            preset["layout"]
            for preset in layout_module.preset_descriptors()
            if preset["id"] == "broadcast"
        )

    def _resolve_view(self) -> dict[str, Any]:
        if self._read_spectator_view is None:
            return {}
        try:
            view = self._read_spectator_view()
        except Exception:  # noqa: BLE001 - a broken view read must never break a trigger
            return {}
        return view if isinstance(view, dict) else {}

    def _resolve_board_layout(self) -> dict[str, Any] | None:
        """The operator's active layout, the style source for the program's
        widgets (:func:`~scoreboard.presentation.cutscenes.build_program`).

        ``None`` when no reader was wired (behaviour is then unchanged: the
        program uses only the Broadcast bar's own look). A raising reader is
        contained exactly like :meth:`_resolve_view`: it must never break a
        trigger, so the failure is only noted and the program falls back to
        the Broadcast bar's look for this one play.
        """

        if self._read_board_layout is None:
            return None
        try:
            board_layout = self._read_board_layout()
        except Exception as exc:  # noqa: BLE001 - a broken read must never break a trigger
            self._diagnostics.unhandled_error(context="cutscene_board_layout", error=exc)
            return None
        return board_layout if isinstance(board_layout, dict) else None

    # --- The JavaScript-facing API ------------------------------------------

    def state(self) -> dict[str, Any]:
        """Everything the Cutscenes window needs to render itself."""

        with self._lock:
            library = self._library
            current = self._current
            play_id = self._play_id
        events = []
        for descriptor in cutscenes_module.event_descriptors():
            pack, fell_back = library.resolve(descriptor["id"])
            events.append(
                {
                    **descriptor,
                    "selected_pack_id": pack["id"],
                    "selected_pack_name": pack["name"],
                    "fell_back": fell_back,
                }
            )
        return {
            "events": events,
            "packs": list(library.packs),
            "issues": list(library.issues),
            "folder": str(self._paths.cutscenes),
            "playing": self._status_locked(current, play_id),
        }

    def trigger(self, event: Any) -> dict[str, Any]:
        """Play ``event``, replacing anything already playing. Never raises.

        There is no ``team`` argument: a cutscene is always the home team's
        (or, for a penalty, nobody's) -- see
        :data:`~scoreboard.presentation.cutscenes.EVENT_TEAM`.
        """

        if event not in cutscenes_module.CUTSCENE_EVENTS:
            return {"ok": False, "message": f"Unknown cutscene event: {event!r}."}

        # Read the spectator view *before* taking this object's lock. The
        # read goes through the bridge, which takes the command lock, and the
        # 10 Hz tick already holds that lock when it calls ``status()`` here
        # to fill every operator view. Holding this lock across the read
        # would order the two locks both ways, and one collision between a
        # trigger and a tick would hang both windows for the rest of the
        # game. The view can be a tick stale. The current branded copy is
        # fixed as Tigers, but keeping this read outside the lock preserves
        # the program-builder seam without reintroducing the lock inversion.
        spectator_view = self._resolve_view()
        layout = self._resolve_layout()
        board_layout = self._resolve_board_layout()
        with self._lock:
            previous = self._current
            if self._timer is not None:
                try:
                    self._timer.cancel()
                except Exception:  # noqa: BLE001 - a stale timer handle must never break a trigger
                    pass
            self._play_id += 1
            play_id = self._play_id
            pack, _fell_back = self._library.resolve(event)
            program = cutscenes_module.build_program(
                play_id=play_id,
                event=event,
                pack=pack,
                spectator_view=spectator_view,
                layout=layout,
                board_layout=board_layout,
            )
            started_at = self._monotonic()
            self._current = {"program": program, "started_at": started_at, "pack_name": pack["name"]}
            self._timer = None

        if previous is not None:
            self._diagnostics.note("CUTSCENE_REPLACED", play_id=previous["program"]["play_id"])

        try:
            self.link.publish(program)
        except Exception as exc:  # noqa: BLE001 - a publish must never fail the trigger (R-002)
            self._diagnostics.unhandled_error(context="cutscene_publish", error=exc)

        duration_seconds = program["duration_ms"] / 1000.0
        timer = self._schedule(duration_seconds, lambda: self._expire(play_id))
        with self._lock:
            if self._play_id == play_id:
                self._timer = timer

        self._diagnostics.note(
            "CUTSCENE_STARTED",
            play_id=play_id,
            cutscene_event=event,
            pack=pack["id"],
            team=program["team"],
            duration_ms=program["duration_ms"],
        )
        return {
            "ok": True,
            "message": f"Playing {program['label']} ({duration_seconds:.0f} s).",
            "play_id": play_id,
            "status": self.status(),
        }

    def cancel(self) -> dict[str, Any]:
        """End whatever is playing now. Never raises."""

        with self._lock:
            current = self._current
            if current is None:
                return {"ok": False, "message": "No cutscene is playing."}
            play_id = self._play_id
            timer = self._timer
            self._current = None
            self._timer = None

        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.link.end(play_id)
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="cutscene_end", error=exc)
        self._diagnostics.note("CUTSCENE_CANCELLED", play_id=play_id)
        return {"ok": True, "message": "Cutscene cancelled."}

    def _expire(self, play_id: int) -> None:
        """Timer callback: end ``play_id`` unless it has already been
        replaced or cancelled (a stale timer firing late is ignored).
        """

        with self._lock:
            if self._current is None or self._play_id != play_id:
                return
            self._current = None
            self._timer = None
        try:
            self.link.end(play_id)
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="cutscene_end", error=exc)
        self._diagnostics.note("CUTSCENE_ENDED", play_id=play_id)

    def status(self) -> dict[str, Any] | None:
        """``None`` when idle, else the countdown Python computed."""

        with self._lock:
            current = self._current
            play_id = self._play_id
        return self._status_locked(current, play_id)

    def _status_locked(self, current: dict[str, Any] | None, play_id: int) -> dict[str, Any] | None:
        if current is None:
            return None
        program = current["program"]
        elapsed_seconds = max(0.0, self._monotonic() - current["started_at"])
        elapsed_ms = round(elapsed_seconds * 1000)
        remaining_ms = max(0, program["duration_ms"] - elapsed_ms)
        remaining_seconds = remaining_ms / 1000.0
        return {
            "play_id": program["play_id"],
            "event": program["event"],
            "label": program["label"],
            "team": program["team"],
            "pack_id": program["pack_id"],
            "pack_name": current["pack_name"],
            "duration_ms": program["duration_ms"],
            "elapsed_ms": elapsed_ms,
            "remaining_ms": remaining_ms,
            "remaining_display": f"{remaining_seconds:.1f}s",
        }

    def current_program(self) -> dict[str, Any] | None:
        """The program while playing, with ``elapsed_ms`` filled in for a
        spectator page that (re)loads mid-cutscene.
        """

        with self._lock:
            current = self._current
        if current is None:
            return None
        program = copy.deepcopy(current["program"])
        elapsed_seconds = max(0.0, self._monotonic() - current["started_at"])
        program["elapsed_ms"] = round(elapsed_seconds * 1000)
        return program

    def rescan(self) -> dict[str, Any]:
        """Reload the pack library from disk. Restart is never needed."""

        self._reload()
        result = self.state()
        result["message"] = "Rescanned the cutscenes folder."
        return result

    def select_pack(self, event: Any, pack_id: Any) -> dict[str, Any]:
        """Persist which pack plays for ``event``.

        A failed write keeps the previous in-memory selection and says so
        -- the library is only reloaded once the write has succeeded.
        """

        if event not in cutscenes_module.CUTSCENE_EVENTS:
            result = self.state()
            result["ok"] = False
            result["message"] = f"Unknown cutscene event: {event!r}."
            return result
        if not isinstance(pack_id, str) or not pack_id:
            result = self.state()
            result["ok"] = False
            result["message"] = "A pack id must be given."
            return result

        with self._lock:
            selection = dict(self._library.selection)
        selection[event] = pack_id

        if not cutscene_packs.write_selection(self._paths, selection):
            result = self.state()
            result["ok"] = False
            result["message"] = "The pack selection could not be saved to disk."
            return result

        self._reload()
        result = self.state()
        result["ok"] = True
        result["message"] = "Pack selection saved."
        return result

    def open_folder(self) -> dict[str, Any]:
        """Show the ``cutscenes`` folder in Explorer. Never raises."""

        opener = self._folder_opener
        if opener is None:
            # Imported lazily: scoreboard.host.bridge imports nothing from
            # this module, but this module must not import it back at
            # module-import time either (a circular import).
            from scoreboard.host.bridge import _open_in_explorer

            opener = _open_in_explorer
        try:
            opener(self._paths.cutscenes)
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="cutscene_open_folder", error=exc)
            return {"ok": False, "message": "Could not open the cutscenes folder."}
        return {"ok": True, "message": "Opened the cutscenes folder."}

    def shutdown(self) -> None:
        """Cancel any pending timer. Publishes nothing -- the window, if
        any, is about to close along with the rest of the application.
        """

        with self._lock:
            timer = self._timer
            self._timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # noqa: BLE001
                pass


class CutscenesBridge:
    """The Cutscenes window's deliberately small JSON API. No ``command``.

    Every state-changing call forwards straight to a
    :class:`CutsceneDirector`; ``get_snapshot`` is the one read of live
    operator state (team names, the cutscenes badge), read-only, exactly like
    :class:`~scoreboard.host.bridge.FieldAssistantBridge`.
    """

    def __init__(self, director: CutsceneDirector, operator: "ScoreboardBridge") -> None:
        self._director = director
        self._operator = operator

    def get_snapshot(self) -> dict[str, Any]:
        return self._operator.get_snapshot()

    def state(self) -> dict[str, Any]:
        return self._director.state()

    def trigger(self, event: Any) -> dict[str, Any]:
        return self._director.trigger(event)

    def cancel(self) -> dict[str, Any]:
        return self._director.cancel()

    def rescan(self) -> dict[str, Any]:
        return self._director.rescan()

    def select_pack(self, event: Any, pack_id: Any) -> dict[str, Any]:
        return self._director.select_pack(event, pack_id)

    def open_folder(self) -> dict[str, Any]:
        return self._director.open_folder()


__all__ = [
    "CutsceneDirector",
    "CutsceneLink",
    "CutscenesBridge",
]
