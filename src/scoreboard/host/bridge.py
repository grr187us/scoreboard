"""The narrow JavaScript-to-Python boundary (ARCHITECTURE.md section 8).

The operator bridge exposes deliberately few methods:

* ``command(name, args, expected_revision)`` -- build a
  :class:`~scoreboard.domain.commands.Command`, submit it to
  :class:`~scoreboard.application.service.ScoreboardService`, persist the
  result through Task 6, and return a JSON-compatible dictionary;
* ``get_snapshot()`` -- return the same dictionary without changing anything;
* ``reopen_display()`` -- ask the host to recreate the spectator window, which
  changes no game state (D-005).

The spectator bridge exposes ``get_snapshot()`` and nothing that mutates.

No domain object crosses this boundary. Every value returned here is a
``str``, ``int``, ``float``, ``bool``, ``None``, ``list``, or ``dict``, so the
payload survives the webview's JSON transport unchanged.

JavaScript stores only ephemeral view state -- an open drawer, focus, unsent
form text. It never computes a score, a clock, or a revision: it renders the
view model it is given. Every displayed clock string is produced here by
:mod:`scoreboard.domain.formatting`, so the operator readout and the persisted
checkpoint can never disagree about what is on the board.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Final

from scoreboard.application.service import ScoreboardService
from scoreboard.domain.clocks import SELECTABLE_EVENT_PHASES, event_phase_for
from scoreboard.domain.commands import (
    Command,
    CommandError,
    CommandResult,
    CommandType,
    UndoEntry,
    validate_command,
)
from scoreboard.domain.formatting import (
    format_event_countdown,
    format_game_clock,
    format_play_clock,
)
from scoreboard.domain.state import GameState, QUARTER_LABELS, SCHEMA_VERSION
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.persistence import GameStore, PersistenceStatus

#: The two local input adapters share every command and retain their source.
OPERATOR_MOUSE_SOURCE: Final[str] = "operator-mouse"
OPERATOR_KEYBOARD_SOURCE: Final[str] = "operator-keyboard"

#: Returned when JavaScript asks for something that is not a command at all.
#: This never reaches the service: an unknown name is not a game event.
UNKNOWN_COMMAND: Final[str] = "UNKNOWN_COMMAND"
INVALID_ARGUMENTS: Final[str] = "INVALID_ARGUMENTS"

#: The arguments each command accepts from a view. Anything else is refused
#: before a Command is built, so a typo in JavaScript cannot become a mutation.
_ALLOWED_ARGUMENTS: Final[dict[CommandType, frozenset[str]]] = {
    CommandType.SET_TEAM_NAME: frozenset({"team", "name"}),
    CommandType.ADD_SCORE: frozenset({"team", "points"}),
    CommandType.CORRECT_SCORE: frozenset({"team", "points"}),
    CommandType.SET_SCORE: frozenset({"team", "value"}),
    CommandType.UNDO: frozenset(),
    CommandType.QUARTER_FORWARD: frozenset(),
    CommandType.QUARTER_BACK: frozenset(),
    CommandType.SET_QUARTER: frozenset({"label"}),
    CommandType.NEW_GAME: frozenset(),
    CommandType.END_GAME: frozenset(),
    CommandType.GAME_CLOCK_START: frozenset(),
    CommandType.GAME_CLOCK_STOP: frozenset(),
    CommandType.GAME_CLOCK_RESET: frozenset(),
    CommandType.GAME_CLOCK_CORRECT: frozenset({"seconds"}),
    CommandType.PLAY_CLOCK_PRESET: frozenset({"seconds"}),
    CommandType.PLAY_CLOCK_START: frozenset(),
    CommandType.PLAY_CLOCK_STOP: frozenset(),
    CommandType.PLAY_CLOCK_CLEAR: frozenset(),
    CommandType.PLAY_CLOCK_RESET: frozenset(),
    CommandType.PLAY_CLOCK_CORRECT: frozenset({"seconds"}),
    CommandType.EVENT_COUNTDOWN_SELECT: frozenset({"label"}),
    CommandType.EVENT_COUNTDOWN_START: frozenset(),
    CommandType.EVENT_COUNTDOWN_STOP: frozenset(),
    CommandType.EVENT_COUNTDOWN_RESET: frozenset(),
    CommandType.EVENT_COUNTDOWN_CORRECT: frozenset({"seconds"}),
}

_NUMERIC_ARGUMENTS: Final[frozenset[str]] = frozenset({"points", "value", "seconds"})
_TEXT_ARGUMENTS: Final[frozenset[str]] = frozenset({"team", "label", "name"})


# --- Display health ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisplayStatus:
    """What the health strip says about the spectator window (U-005, D-005)."""

    open: bool
    target: str | None = None
    detail: str | None = None

    @property
    def label(self) -> str:
        return "DISPLAY OPEN" if self.open else "DISPLAY CLOSED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": self.open,
            "label": self.label,
            "target": self.target,
            "detail": self.detail,
            # A closed display is recoverable in one click and never stops a
            # clock or closes the operator (D-005).
            "can_reopen": not self.open,
        }


class DisplayLink:
    """The host's spectator window, as the bridge needs to see it.

    Keeping this tiny means the bridge can be tested without a webview, and a
    spectator rendering failure has no path to the state engine (R-002).
    """

    def __init__(self) -> None:
        self._status = DisplayStatus(open=False, detail="Not opened yet.")

    @property
    def status(self) -> DisplayStatus:
        return self._status

    def mark_open(self, target: str | None = None) -> DisplayStatus:
        self._status = DisplayStatus(open=True, target=target)
        return self._status

    def mark_closed(self, detail: str = "The spectator window is closed.") -> DisplayStatus:
        self._status = DisplayStatus(open=False, target=self._status.target, detail=detail)
        return self._status

    def reopen(self) -> DisplayStatus:
        """Overridden by the host. On its own this link opens no window."""

        return self._status


# --- Command translation ----------------------------------------------------


def build_command(
    name: Any,
    args: Any = None,
    expected_revision: Any = None,
    *,
    source: str = OPERATOR_MOUSE_SOURCE,
    confirmed: bool = False,
) -> Command | CommandError:
    """Translate a JSON request into a validated ``Command``.

    This is the airlock. A name that is not a command, an argument a command
    does not take, or a value of the wrong type is refused here and never
    reaches the service, so JavaScript cannot invent a mutation.
    """

    if not isinstance(name, str):
        return CommandError(UNKNOWN_COMMAND, "A command name must be text.")
    try:
        command_type = CommandType(name)
    except ValueError:
        return CommandError(UNKNOWN_COMMAND, f"{name!r} is not a control on this board.")

    if args is None:
        args = {}
    if not isinstance(args, dict):
        return CommandError(INVALID_ARGUMENTS, "Command arguments must be a dictionary.")

    allowed = _ALLOWED_ARGUMENTS[command_type]
    source = args.get("source", source)
    if source not in (OPERATOR_MOUSE_SOURCE, OPERATOR_KEYBOARD_SOURCE):
        return CommandError(INVALID_ARGUMENTS, "Unknown operator input source.")
    supplied = {key: value for key, value in args.items() if key not in ("confirmed", "source")}
    unexpected = set(supplied) - allowed
    if unexpected:
        return CommandError(
            INVALID_ARGUMENTS,
            f"{name} does not take {', '.join(sorted(unexpected))}.",
        )

    fields: dict[str, Any] = {}
    for key, value in supplied.items():
        if key in _NUMERIC_ARGUMENTS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return CommandError(
                    INVALID_ARGUMENTS,
                    f"Enter a number for {key}." if value is None
                    else f"{key} must be a number; got {value!r}.",
                )
            numeric = float(value)
            # An empty or malformed field can arrive as NaN or an infinity.
            # Refuse it here: it is not a number, and it would not survive JSON.
            if numeric != numeric or numeric in (float("inf"), float("-inf")):
                return CommandError(INVALID_ARGUMENTS, f"Enter a whole number for {key}.")
            if key in ("points", "value"):
                if numeric != int(numeric):
                    return CommandError(
                        INVALID_ARGUMENTS, f"{key} must be a whole number; got {value!r}."
                    )
                fields[key] = int(numeric)
            else:
                fields[key] = numeric
        elif key in _TEXT_ARGUMENTS:
            if not isinstance(value, str):
                return CommandError(
                    INVALID_ARGUMENTS, f"{key} must be text; got {value!r}."
                )
            fields[key] = value
        else:  # pragma: no cover - _ALLOWED_ARGUMENTS covers every key
            return CommandError(INVALID_ARGUMENTS, f"{key} is not a supported argument.")

    requested_confirmation = args.get("confirmed", confirmed)
    if not isinstance(requested_confirmation, bool):
        return CommandError(INVALID_ARGUMENTS, "Confirmation must be true or false.")

    if expected_revision is not None:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            return CommandError(
                INVALID_ARGUMENTS, "The expected revision must be a whole number."
            )

    command = Command(
        type=command_type,
        confirmed=requested_confirmation,
        source=source,
        expected_revision=expected_revision,
        **fields,
    )
    shape_error = validate_command(command)
    if shape_error is not None:
        return shape_error
    return command


# --- View model -------------------------------------------------------------


def _clock_view(seconds: float, running: bool, display: str) -> dict[str, Any]:
    return {
        "seconds": seconds,
        "running": running,
        "display": display,
        # Text, not colour: the operator must be able to read the state
        # (UX_AND_LAYOUT.md section 2, U-002).
        "status": "RUNNING" if running else "STOPPED",
    }


def _last_action_view(entry: UndoEntry | None) -> dict[str, Any] | None:
    """The previous reversible command and whether Undo can reverse it (U-008)."""

    if entry is None:
        return None
    if entry.field.endswith("_score"):
        subject = f"{(entry.team or '').upper()} score"
    elif entry.field == "quarter":
        subject = "Quarter"
    else:
        subject = entry.field.replace("_", " ").capitalize()
    return {
        "command": entry.command.value,
        "team": entry.team,
        "field": entry.field,
        "old_value": entry.old_value,
        "new_value": entry.new_value,
        "label": f"{subject} {entry.old_value} → {entry.new_value}",
    }


def spectator_view_model(state: GameState) -> dict[str, Any]:
    """Everything the spectator window renders. It requests nothing else."""

    countdown_phase = event_phase_for(state.event_phase, state.event_countdown.seconds)
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": state.revision,
        "teams": {
            "home": {"name": state.home_name, "score": state.home_score},
            "away": {"name": state.away_name, "score": state.away_score},
        },
        "quarter": state.quarter,
        "lifecycle": state.lifecycle,
        "clocks": {
            "game": _clock_view(
                state.game_clock.seconds,
                state.game_clock.running,
                format_game_clock(state.game_clock.seconds),
            ),
            "play": _clock_view(
                state.play_clock.seconds,
                state.play_clock.running,
                # A cleared play clock is a blank area, not a zero (F-048).
                format_play_clock(
                    state.play_clock.seconds,
                    blank_at_zero=state.play_clock_cleared,
                ),
            ),
            "event": {
                **_clock_view(
                    state.event_countdown.seconds,
                    state.event_countdown.running,
                    format_event_countdown(state.event_countdown.seconds),
                ),
                "phase": countdown_phase,
                "title": "KICKOFF IN" if countdown_phase == "PREGAME" else "UNTIL SECOND HALF",
                # Shown only during HALFTIME, per the confirmed presentation.
                "warmup_follows": "3:00" if countdown_phase == "HALFTIME" else None,
            },
        },
    }


def operator_view_model(
    service: ScoreboardService,
    *,
    persistence: PersistenceStatus,
    display: DisplayStatus,
    now: float | None = None,
) -> dict[str, Any]:
    """Everything the operator window renders, including health and last action."""

    state = service.materialized_state(now)
    model = spectator_view_model(state)
    model["quarter_labels"] = list(QUARTER_LABELS)
    model["event_phases"] = list(SELECTABLE_EVENT_PHASES)
    model["play_clock_presets"] = [25, 40]
    model["last_action"] = _last_action_view(service.undo_entry)
    model["can_undo"] = service.undo_entry is not None
    model["health"] = {
        "revision": state.revision,
        "display": display.to_dict(),
        "persistence": persistence.to_dict(),
    }
    return model


# --- Bridges ----------------------------------------------------------------


class SpectatorBridge:
    """Read-only. There is deliberately no method here that changes anything."""

    def __init__(self, read_snapshot: Callable[[], dict[str, Any]]) -> None:
        self._read_snapshot = read_snapshot

    def get_snapshot(self) -> dict[str, Any]:
        return self._read_snapshot()


class ScoreboardBridge:
    """The operator's only path to authoritative state.

    Every control routes through :meth:`command`. The bridge submits to the
    service, persists the result through Task 6, and returns the complete view
    model so the page re-renders from authority even after a rejection.
    """

    def __init__(
        self,
        service: ScoreboardService,
        store: GameStore,
        *,
        display: DisplayLink | None = None,
        diagnostics: Diagnostics | None = None,
        lock: threading.RLock | None = None,
        on_accepted: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._service = service
        self._store = store
        self._display = DisplayLink() if display is None else display
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        # One lock serialises commands against the display-refresh tick, so a
        # checkpoint can never read a half-applied command.
        self._lock = threading.RLock() if lock is None else lock
        self._on_accepted = on_accepted

    # --- The JavaScript API ------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """The current view model. Reads nothing into the game and changes nothing."""

        with self._lock:
            return self._view()

    def command(
        self,
        name: Any,
        args: Any = None,
        expected_revision: Any = None,
    ) -> dict[str, Any]:
        """Submit one operator command and return its complete result."""

        with self._lock:
            built = build_command(name, args, expected_revision)
            if isinstance(built, CommandError):
                # Refused before the service saw it: nothing changed, and there
                # is no accepted command to persist.
                self._diagnostics.command_rejected(
                    command=str(name), code=built.code, message=built.message,
                    source=OPERATOR_MOUSE_SOURCE,
                )
                return self._result_payload(accepted=False, error=built)

            result = self._service.submit(built)
            self._store.record_command(built, result)
            if result.accepted and self._on_accepted is not None:
                self._on_accepted(self._view())
            return self._result_payload(
                accepted=result.accepted,
                error=result.error,
                confirmation_required=result.confirmation_required,
                result=result,
            )

    def reopen_display(self) -> dict[str, Any]:
        """Recreate the spectator window. This changes no game state (D-005)."""

        with self._lock:
            try:
                self._display.reopen()
            except Exception as exc:  # noqa: BLE001 - a display must never stop the game
                # A spectator failure is reported and survived; the clocks and
                # the operator keep running (R-002).
                self._diagnostics.unhandled_error(context="reopen_display", error=exc)
                self._display.mark_closed(f"The display could not be reopened: {exc}")
            return self._view()

    # --- Host-side hooks ----------------------------------------------------

    def tick(self, now: float | None = None) -> dict[str, Any]:
        """Refresh the display and checkpoint a running clock (P-003).

        Called by the host's refresh loop. It never submits a command, so a
        repaint can neither advance a revision nor write an action-history row.
        """

        with self._lock:
            state = self._service.materialized_state(now)
            try:
                self._store.checkpoint(state)
            except Exception as exc:  # noqa: BLE001 - saving must not stop a clock
                self._diagnostics.persistence_failure(operation="checkpoint", error=str(exc))
            return self._view(now)

    def display_opened(self, target: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._display.mark_open(target)
            self._diagnostics.display_opened(target=target or "unknown")
            return self._view()

    def display_closed(self, detail: str = "The spectator window is closed.") -> dict[str, Any]:
        with self._lock:
            self._display.mark_closed(detail)
            self._diagnostics.display_closed(reason=detail)
            return self._view()

    def spectator_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return spectator_view_model(self._service.materialized_state())

    def shutdown(self) -> dict[str, Any]:
        """Save at clean shutdown and report the final persistence status."""

        with self._lock:
            self._store.record_shutdown(self._service.materialized_state())
            return self._view()

    @property
    def service(self) -> ScoreboardService:
        return self._service

    @property
    def display(self) -> DisplayLink:
        return self._display

    # --- Internals ----------------------------------------------------------

    def _view(self, now: float | None = None) -> dict[str, Any]:
        return operator_view_model(
            self._service,
            persistence=self._store.status,
            display=self._display.status,
            now=now,
        )

    def _result_payload(
        self,
        *,
        accepted: bool,
        error: CommandError | None,
        confirmation_required: bool = False,
        result: CommandResult | None = None,
    ) -> dict[str, Any]:
        return {
            "accepted": accepted,
            # A first submit of a dangerous command changes nothing and asks
            # for confirmation; the view resubmits the same command with
            # confirmed=true (F-022, F-023, U-004).
            "confirmation_required": confirmation_required,
            "error": None
            if error is None
            else {"code": error.code, "message": error.message},
            "event": None
            if result is None or result.event is None
            else {
                "command": result.event.command.value,
                "field": result.event.field,
                "team": result.event.team,
                "old_value": result.event.old_value,
                "new_value": result.event.new_value,
            },
            "view": self._view(),
        }


__all__ = [
    "INVALID_ARGUMENTS",
    "OPERATOR_MOUSE_SOURCE",
    "OPERATOR_KEYBOARD_SOURCE",
    "UNKNOWN_COMMAND",
    "DisplayLink",
    "DisplayStatus",
    "ScoreboardBridge",
    "SpectatorBridge",
    "build_command",
    "operator_view_model",
    "spectator_view_model",
]
