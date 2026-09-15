"""Host object owning soccer cutscene playback: what is playing, and when it
ends.

Mirrors :mod:`scoreboard.host.cutscenes` (football; frozen) for spec section
7. The one contract change from football (spec section 7, ``design_draft.md``
section 6, owner choice F): :meth:`SoccerCutsceneDirector.trigger` takes a
required ``team`` argument (``"home"``/``"away"``) because a GOAL is never
"nobody's" the way a football penalty is -- the operator's bridge
(``SoccerBridge``, agent B) calls ``director.trigger(event, team)``.

Same lock-ordering rule football's director keeps (the "director/tick
lock-ordering trap" this codebase's memory notes name): the spectator view
and the layouts are read *before* :attr:`SoccerCutsceneDirector._lock` is
taken, because the 10 Hz tick already holds the bridge's command lock when it
calls :meth:`state` to fill every operator view -- reading the view under
this object's own lock would order the two locks both ways and one collision
would hang both windows for the rest of the game.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

from scoreboard.infrastructure import soccer_cutscene_packs as cutscene_packs
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.presentation import soccer_cutscenes as cutscenes_module

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a circular import
    from scoreboard.host.soccer_bridge import SoccerBridge


class SoccerCutsceneLink:
    """Mirrors football's ``CutsceneLink``. Overridden by the soccer window
    host at wiring time (agent B). Left alone, opening the window reports a
    plain-language "unavailable" message, and a publish/end is a silent
    no-op.
    """

    def open_window(self) -> dict[str, str]:
        return {"message": "The soccer Cutscenes window is unavailable."}

    def publish(self, program: dict[str, Any]) -> None:
        return None

    def end(self, play_id: int) -> None:
        return None


def _default_schedule(delay_seconds: float, callback: Callable[[], None]) -> threading.Timer:
    timer = threading.Timer(max(0.0, delay_seconds), callback)
    timer.daemon = True
    timer.start()
    return timer


class SoccerCutsceneDirector:
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

        self.link: SoccerCutsceneLink = SoccerCutsceneLink()

        self._lock = threading.Lock()
        self._play_id = 0
        self._current: dict[str, Any] | None = None
        self._timer: Any = None

        cutscene_packs.ensure_packs_directory(self._paths)
        self._library = cutscene_packs.library(self._paths)
        self._note_library_issues()

    # --- Library -------------------------------------------------------

    def _note_library_issues(self) -> None:
        for event in cutscenes_module.SOCCER_CUTSCENE_EVENTS:
            _pack, fell_back = self._library.resolve(event)
            if fell_back:
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
        # No injected reader and no football-style broadcast preset to fall
        # back on here (soccer's own presentation layout is agent D's, and
        # this module must not import it to avoid a layering cycle) -- an
        # empty, but still usable, layout document.
        return {"schema_version": 3, "name": "Cutscene", "widgets": {}, "screens": {}}

    def _resolve_view(self) -> dict[str, Any]:
        if self._read_spectator_view is None:
            return {}
        try:
            view = self._read_spectator_view()
        except Exception:  # noqa: BLE001 - a broken view read must never break a trigger
            return {}
        return view if isinstance(view, dict) else {}

    def _resolve_board_layout(self) -> dict[str, Any] | None:
        if self._read_board_layout is None:
            return None
        try:
            board_layout = self._read_board_layout()
        except Exception as exc:  # noqa: BLE001 - a broken read must never break a trigger
            self._diagnostics.unhandled_error(context="soccer_cutscene_board_layout", error=exc)
            return None
        return board_layout if isinstance(board_layout, dict) else None

    # --- The JavaScript-facing API ------------------------------------------

    def state(self) -> dict[str, Any]:
        """Everything the soccer Cutscenes window needs to render itself."""

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
            "auto_trigger": cutscene_packs.read_auto_trigger(self._paths),
        }

    def set_auto_trigger(self, event: Any, enabled: Any) -> dict[str, Any]:
        """Persist whether ``event`` plays automatically (spec section 7's
        "Play GOAL automatically" switch, default on). Never raises.
        """

        if event not in cutscenes_module.SOCCER_CUTSCENE_EVENTS:
            result = self.state()
            result["ok"] = False
            result["message"] = f"Unknown cutscene event: {event!r}."
            return result

        auto_trigger = cutscene_packs.read_auto_trigger(self._paths)
        auto_trigger[event] = bool(enabled)
        if not cutscene_packs.write_auto_trigger(self._paths, auto_trigger):
            result = self.state()
            result["ok"] = False
            result["message"] = "The automatic-play setting could not be saved to disk."
            return result

        result = self.state()
        result["ok"] = True
        result["message"] = "Automatic-play setting saved."
        return result

    def trigger(self, event: Any, team: Any) -> dict[str, Any]:
        """Play ``event`` for ``team``, replacing anything already playing.

        Never raises. ``team`` must be ``"home"`` or ``"away"`` -- an
        unrecognised value is rejected the same way an unknown event is,
        rather than silently defaulting, so a caller's bug surfaces at the
        bridge instead of celebrating the wrong side.
        """

        if event not in cutscenes_module.SOCCER_CUTSCENE_EVENTS:
            return {"ok": False, "message": f"Unknown cutscene event: {event!r}."}
        if team not in ("home", "away"):
            return {"ok": False, "message": f"team must be 'home' or 'away'; got {team!r}."}

        # Read outside this object's lock -- see the module docstring.
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
                team=team,
            )
            started_at = self._monotonic()
            self._current = {"program": program, "started_at": started_at, "pack_name": pack["name"]}
            self._timer = None

        if previous is not None:
            self._diagnostics.note("CUTSCENE_REPLACED", play_id=previous["program"]["play_id"])

        try:
            self.link.publish(program)
        except Exception as exc:  # noqa: BLE001 - a publish must never fail the trigger (R-002)
            self._diagnostics.unhandled_error(context="soccer_cutscene_publish", error=exc)

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
            self._diagnostics.unhandled_error(context="soccer_cutscene_end", error=exc)
        self._diagnostics.note("CUTSCENE_CANCELLED", play_id=play_id)
        return {"ok": True, "message": "Cutscene cancelled."}

    def _expire(self, play_id: int) -> None:
        with self._lock:
            if self._current is None or self._play_id != play_id:
                return
            self._current = None
            self._timer = None
        try:
            self.link.end(play_id)
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="soccer_cutscene_end", error=exc)
        self._diagnostics.note("CUTSCENE_ENDED", play_id=play_id)

    def status(self) -> dict[str, Any] | None:
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
        with self._lock:
            current = self._current
        if current is None:
            return None
        program = copy.deepcopy(current["program"])
        elapsed_seconds = max(0.0, self._monotonic() - current["started_at"])
        program["elapsed_ms"] = round(elapsed_seconds * 1000)
        return program

    def rescan(self) -> dict[str, Any]:
        self._reload()
        result = self.state()
        result["message"] = "Rescanned the cutscenes folder."
        return result

    def select_pack(self, event: Any, pack_id: Any) -> dict[str, Any]:
        if event not in cutscenes_module.SOCCER_CUTSCENE_EVENTS:
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

    def auto_trigger_enabled(self, event: Any) -> bool:
        """Whether ``event`` should fire automatically (agent B's bridge
        calls this after an accepted ``add_goal`` before it calls
        :meth:`trigger`). Defaults to on, and to on for an unknown event
        rather than raising -- the switch is advisory, never a gate that can
        crash a scoring play.
        """

        if event not in cutscenes_module.SOCCER_CUTSCENE_EVENTS:
            return True
        return cutscene_packs.read_auto_trigger(self._paths).get(event, True)

    def open_folder(self) -> dict[str, Any]:
        opener = self._folder_opener
        if opener is None:
            from scoreboard.host.bridge import _open_in_explorer

            opener = _open_in_explorer
        try:
            opener(self._paths.cutscenes)
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="soccer_cutscene_open_folder", error=exc)
            return {"ok": False, "message": "Could not open the cutscenes folder."}
        return {"ok": True, "message": "Opened the cutscenes folder."}

    def shutdown(self) -> None:
        with self._lock:
            timer = self._timer
            self._timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # noqa: BLE001
                pass


class SoccerCutscenesBridge:
    """The soccer Cutscenes window's deliberately small JSON API. No
    ``command``. Mirrors football's ``CutscenesBridge``, plus the required
    ``team`` argument on :meth:`trigger`.
    """

    def __init__(self, director: SoccerCutsceneDirector, operator: "SoccerBridge") -> None:
        self._director = director
        self._operator = operator

    def get_snapshot(self) -> dict[str, Any]:
        return self._operator.get_snapshot()

    def state(self) -> dict[str, Any]:
        return self._director.state()

    def trigger(self, event: Any, team: Any) -> dict[str, Any]:
        return self._director.trigger(event, team)

    def cancel(self) -> dict[str, Any]:
        return self._director.cancel()

    def rescan(self) -> dict[str, Any]:
        return self._director.rescan()

    def select_pack(self, event: Any, pack_id: Any) -> dict[str, Any]:
        return self._director.select_pack(event, pack_id)

    def set_auto_trigger(self, event: Any, enabled: Any) -> dict[str, Any]:
        return self._director.set_auto_trigger(event, enabled)

    def open_folder(self) -> dict[str, Any]:
        return self._director.open_folder()


__all__ = [
    "SoccerCutsceneDirector",
    "SoccerCutsceneLink",
    "SoccerCutscenesBridge",
]
