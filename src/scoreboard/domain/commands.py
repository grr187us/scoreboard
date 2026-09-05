"""Command, result, and pure validation types for the scoreboard command service.

This module is deliberately pure. It holds no state, reads no clock, and touches
no filesystem, persistence, or user interface. It describes *what* an operator
asked for and *how a request is shaped*; ``scoreboard.application.service`` owns
the authoritative :class:`~scoreboard.domain.state.GameState` and is the only
component permitted to advance a state revision.

Requirement coverage: F-001 through F-004, F-010 through F-017, and F-020
through F-024. Down/distance, timeouts, possession, statistics, and the
pregame/interval event countdowns are intentionally absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

from scoreboard.domain.clocks import PLAY_CLOCK_PRESETS, SELECTABLE_EVENT_PHASES
from scoreboard.domain.state import (
    MAX_DISTANCE,
    MAX_DOWN,
    MAX_SCORE,
    MAX_TIMEOUTS,
    MAX_YARD_LINE,
    MIN_DOWN,
    QUARTER_LABELS,
)

#: Documented scoring buttons: ``+1`` conversion, ``+2`` conversion/safety,
#: ``+3`` field goal, ``+6`` touchdown (F-012). The correction path uses the
#: same magnitudes as ``-1``/``-2``/``-3``/``-6`` (F-015).
SCORE_INCREMENTS: Final[tuple[int, ...]] = (1, 2, 3, 6)

#: Team selectors accepted by team-scoped commands.
TEAMS: Final[tuple[str, ...]] = ("home", "away")

#: Lifecycle labels in which team names may still be edited (F-010).
PREGAME_LIFECYCLES: Final[tuple[str, ...]] = ("PRE_GAME",)


class CommandType(str, Enum):
    """Every mutation the Task 5 command service accepts."""

    SET_TEAM_NAME = "set_team_name"
    ADD_SCORE = "add_score"
    CORRECT_SCORE = "correct_score"
    SET_SCORE = "set_score"
    UNDO = "undo"
    QUARTER_FORWARD = "quarter_forward"
    QUARTER_BACK = "quarter_back"
    SET_QUARTER = "set_quarter"
    NEW_GAME = "new_game"
    END_GAME = "end_game"
    GAME_CLOCK_START = "game_clock_start"
    GAME_CLOCK_STOP = "game_clock_stop"
    GAME_CLOCK_RESET = "game_clock_reset"
    GAME_CLOCK_CORRECT = "game_clock_correct"
    PLAY_CLOCK_PRESET = "play_clock_preset"
    PLAY_CLOCK_PRESET_START = "play_clock_preset_start"
    PLAY_CLOCK_START = "play_clock_start"
    PLAY_CLOCK_STOP = "play_clock_stop"
    PLAY_CLOCK_CLEAR = "play_clock_clear"
    PLAY_CLOCK_RESET = "play_clock_reset"
    PLAY_CLOCK_CORRECT = "play_clock_correct"
    EVENT_COUNTDOWN_SELECT = "event_countdown_select"
    EVENT_COUNTDOWN_START = "event_countdown_start"
    EVENT_COUNTDOWN_STOP = "event_countdown_stop"
    EVENT_COUNTDOWN_RESET = "event_countdown_reset"
    EVENT_COUNTDOWN_CORRECT = "event_countdown_correct"
    #: Expanded football state (deferred from Task 5; see
    #: docs/PHASE_2_BACKLOG.md "Deferred scoreboard fields"): down, distance,
    #: possession, ball-on field position, and timeouts remaining.
    SET_DOWN = "set_down"
    SET_DISTANCE = "set_distance"
    SET_POSSESSION = "set_possession"
    SET_BALL_ON = "set_ball_on"
    TIMEOUT_USED = "timeout_used"
    TIMEOUT_CORRECT = "timeout_correct"
    SET_TIMEOUTS = "set_timeouts"


# --- Error codes -----------------------------------------------------------
# Codes are stable identifiers for callers; messages are plain language for an
# operator. Expected validation failures are returned, never raised (U-007).

INVALID_COMMAND: Final[str] = "INVALID_COMMAND"
INVALID_TEAM: Final[str] = "INVALID_TEAM"
INVALID_TEAM_NAME: Final[str] = "INVALID_TEAM_NAME"
TEAM_NAME_NOT_ALLOWED: Final[str] = "TEAM_NAME_NOT_ALLOWED"
INVALID_SCORE_DELTA: Final[str] = "INVALID_SCORE_DELTA"
INVALID_SCORE_TARGET: Final[str] = "INVALID_SCORE_TARGET"
SCORE_BELOW_ZERO: Final[str] = "SCORE_BELOW_ZERO"
SCORE_ABOVE_MAXIMUM: Final[str] = "SCORE_ABOVE_MAXIMUM"
INVALID_QUARTER: Final[str] = "INVALID_QUARTER"
QUARTER_OUT_OF_RANGE: Final[str] = "QUARTER_OUT_OF_RANGE"
CONFIRMATION_REQUIRED: Final[str] = "CONFIRMATION_REQUIRED"
NOTHING_TO_UNDO: Final[str] = "NOTHING_TO_UNDO"
NOT_UNDOABLE: Final[str] = "NOT_UNDOABLE"
INVALID_CLOCK_TIME: Final[str] = "INVALID_CLOCK_TIME"
INVALID_PLAY_CLOCK_PRESET: Final[str] = "INVALID_PLAY_CLOCK_PRESET"
INVALID_EVENT_PHASE: Final[str] = "INVALID_EVENT_PHASE"
STALE_REVISION: Final[str] = "STALE_REVISION"
INVALID_DOWN: Final[str] = "INVALID_DOWN"
INVALID_DISTANCE: Final[str] = "INVALID_DISTANCE"
INVALID_POSSESSION: Final[str] = "INVALID_POSSESSION"
INVALID_BALL_ON: Final[str] = "INVALID_BALL_ON"
INVALID_TIMEOUT_DELTA: Final[str] = "INVALID_TIMEOUT_DELTA"
INVALID_TIMEOUT_TARGET: Final[str] = "INVALID_TIMEOUT_TARGET"
TIMEOUT_BELOW_ZERO: Final[str] = "TIMEOUT_BELOW_ZERO"
TIMEOUT_ABOVE_MAXIMUM: Final[str] = "TIMEOUT_ABOVE_MAXIMUM"

#: A timeout correction is +1 or -1 only, mirroring how a single mis-click is
#: corrected elsewhere; a larger swing should be a direct Set instead.
TIMEOUT_CORRECTION_MAGNITUDE: Final[int] = 1

#: Commands whose effect a single Undo can reverse (F-014).
UNDOABLE_COMMANDS: Final[frozenset[CommandType]] = frozenset(
    {
        CommandType.ADD_SCORE,
        CommandType.CORRECT_SCORE,
        CommandType.SET_SCORE,
        CommandType.QUARTER_FORWARD,
        CommandType.QUARTER_BACK,
        CommandType.SET_QUARTER,
        CommandType.SET_DOWN,
        CommandType.SET_DISTANCE,
        CommandType.SET_POSSESSION,
        CommandType.SET_BALL_ON,
        CommandType.TIMEOUT_USED,
        CommandType.TIMEOUT_CORRECT,
        CommandType.SET_TIMEOUTS,
    }
)

#: Commands that are never undoable. A quarter change committed *through the
#: running-clock confirmation step* also joins this group at runtime, because
#: reversing it could not restore the clocks that confirmation stopped.
NON_UNDOABLE_COMMANDS: Final[frozenset[CommandType]] = frozenset(
    {
        CommandType.NEW_GAME,
        CommandType.END_GAME,
        CommandType.UNDO,
    }
)

_TEAM_COMMANDS: Final[frozenset[CommandType]] = frozenset(
    {
        CommandType.SET_TEAM_NAME,
        CommandType.ADD_SCORE,
        CommandType.CORRECT_SCORE,
        CommandType.SET_SCORE,
        CommandType.SET_BALL_ON,
        CommandType.TIMEOUT_USED,
        CommandType.TIMEOUT_CORRECT,
        CommandType.SET_TIMEOUTS,
    }
)


@dataclass(frozen=True, slots=True)
class CommandError:
    """A rejected request: a stable code plus a plain-language message."""

    code: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise TypeError("error code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise TypeError("error message must be a non-empty string")


@dataclass(frozen=True, slots=True)
class Command:
    """One request submitted to the command service.

    Only the fields a given command type needs are populated; the rest stay
    ``None``. Prefer the module-level factory helpers over building this
    directly.
    """

    type: CommandType
    team: str | None = None
    points: int | None = None
    value: int | None = None
    label: str | None = None
    name: str | None = None
    seconds: float | None = None
    confirmed: bool = False
    source: str = "operator"
    expected_revision: int | None = None


@dataclass(frozen=True, slots=True)
class EventIntent:
    """What an accepted command did, for a future durable logger to consume.

    Task 5 only *returns* this; Task 6 owns writing it anywhere (F-002, F-013).
    """

    command: CommandType
    field: str
    old_value: Any
    new_value: Any
    team: str | None = None
    source: str = "operator"


@dataclass(frozen=True, slots=True)
class UndoEntry:
    """The single most recent reversible transition, held in memory only."""

    command: CommandType
    field: str
    old_value: Any
    new_value: Any
    team: str | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The complete outcome of one submitted command.

    ``state``/``snapshot`` are always populated: the new authoritative state for
    an accepted command, and the unchanged current state for a rejected one.
    """

    accepted: bool
    state: Any
    snapshot: dict[str, Any]
    event: EventIntent | None = None
    error: CommandError | None = None
    confirmation_required: bool = False
    #: Presentation metadata for a server-required confirmation.  It is
    #: descriptive only: Python still validates the resubmitted command.
    confirmation: dict[str, str] | None = None

    @property
    def revision(self) -> int:
        return self.state.revision

    @property
    def error_code(self) -> str | None:
        return None if self.error is None else self.error.code


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _is_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)


def validate_command(command: Command) -> CommandError | None:
    """Check a request's shape without consulting any state.

    Returns ``None`` when the request is well formed. State-dependent rules
    (score bounds, quarter position, lifecycle, undo eligibility) belong to the
    service, which is the only component that knows the current state.
    """

    if not isinstance(command, Command):
        raise TypeError("command must be a Command")
    if not isinstance(command.type, CommandType):
        return CommandError(INVALID_COMMAND, f"Unknown command: {command.type!r}.")
    if command.expected_revision is not None and not _is_int(command.expected_revision):
        return CommandError(INVALID_COMMAND, "Expected revision must be a whole number.")
    if not isinstance(command.confirmed, bool):
        return CommandError(INVALID_COMMAND, "Confirmation flag must be true or false.")

    if command.type in _TEAM_COMMANDS and command.team not in TEAMS:
        return CommandError(
            INVALID_TEAM, f"Choose the home or away team; got {command.team!r}."
        )

    if command.type is CommandType.SET_TEAM_NAME and not isinstance(command.name, str):
        return CommandError(INVALID_TEAM_NAME, "A team name must be text.")

    if command.type in (CommandType.ADD_SCORE, CommandType.CORRECT_SCORE):
        if not _is_int(command.points):
            return CommandError(
                INVALID_SCORE_DELTA, "A scoring command needs a whole number of points."
            )
        if command.type is CommandType.ADD_SCORE and command.points not in SCORE_INCREMENTS:
            return CommandError(
                INVALID_SCORE_DELTA,
                "Scoring supports only +1, +2, +3, and +6.",
            )
        if (
            command.type is CommandType.CORRECT_SCORE
            and abs(command.points) not in SCORE_INCREMENTS
        ):
            return CommandError(
                INVALID_SCORE_DELTA,
                "Corrections support only -1, -2, -3, and -6.",
            )

    if command.type is CommandType.SET_SCORE:
        if not _is_int(command.value):
            return CommandError(
                INVALID_SCORE_TARGET,
                "Direct score entry needs an explicit whole-number target.",
            )
        if command.value < 0:
            return CommandError(INVALID_SCORE_TARGET, "A score cannot be set below 0.")
        if command.value > MAX_SCORE:
            return CommandError(
                SCORE_ABOVE_MAXIMUM,
                f"The board supports scores from 0 to {MAX_SCORE}; "
                f"{command.value} is out of range.",
            )

    if command.type is CommandType.SET_QUARTER and command.label not in QUARTER_LABELS:
        return CommandError(
            INVALID_QUARTER,
            f"{command.label!r} is not a quarter label. Choose one of: "
            + ", ".join(QUARTER_LABELS)
            + ".",
        )

    if command.type in (CommandType.PLAY_CLOCK_PRESET, CommandType.PLAY_CLOCK_PRESET_START):
        if not _is_number(command.seconds) or float(command.seconds) not in PLAY_CLOCK_PRESETS:
            return CommandError(
                INVALID_PLAY_CLOCK_PRESET,
                "The play clock loads only the 25-second or 40-second preset.",
            )

    if command.type is CommandType.EVENT_COUNTDOWN_SELECT:
        if command.label not in SELECTABLE_EVENT_PHASES:
            return CommandError(
                INVALID_EVENT_PHASE,
                "Choose the pregame or the halftime countdown; got "
                f"{command.label!r}. WARMUP is part of the halftime countdown "
                "and is not selected separately.",
            )

    if command.type in (
        CommandType.GAME_CLOCK_CORRECT,
        CommandType.PLAY_CLOCK_CORRECT,
        CommandType.EVENT_COUNTDOWN_CORRECT,
    ):
        if not _is_number(command.seconds):
            return CommandError(
                INVALID_CLOCK_TIME, "A clock correction needs a number of seconds."
            )
        numeric = float(command.seconds)
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            return CommandError(INVALID_CLOCK_TIME, "A clock correction must be a finite time.")
        if numeric < 0:
            return CommandError(INVALID_CLOCK_TIME, "A clock cannot be corrected below 0:00.")

    if command.type is CommandType.SET_DOWN and command.value is not None:
        if not _is_int(command.value) or not MIN_DOWN <= command.value <= MAX_DOWN:
            return CommandError(
                INVALID_DOWN,
                f"Down must be {MIN_DOWN}st through {MAX_DOWN}th, or cleared.",
            )

    if command.type is CommandType.SET_DISTANCE and command.value is not None:
        if not _is_int(command.value) or not 0 <= command.value <= MAX_DISTANCE:
            return CommandError(
                INVALID_DISTANCE,
                f"Distance to go must be between 0 and {MAX_DISTANCE} yards, or cleared.",
            )

    if command.type is CommandType.SET_POSSESSION and command.team is not None:
        if command.team not in TEAMS:
            return CommandError(
                INVALID_POSSESSION,
                f"Choose the home team, the away team, or clear possession; got {command.team!r}.",
            )

    if command.type is CommandType.SET_BALL_ON:
        if not _is_int(command.value) or not 0 <= command.value <= MAX_YARD_LINE:
            return CommandError(
                INVALID_BALL_ON,
                f"The yard line must be between 0 and {MAX_YARD_LINE}.",
            )

    if command.type is CommandType.TIMEOUT_CORRECT:
        if not _is_int(command.points) or abs(command.points) != TIMEOUT_CORRECTION_MAGNITUDE:
            return CommandError(
                INVALID_TIMEOUT_DELTA, "A timeout correction is +1 or -1."
            )

    if command.type is CommandType.SET_TIMEOUTS:
        if not _is_int(command.value) or not 0 <= command.value <= MAX_TIMEOUTS:
            return CommandError(
                INVALID_TIMEOUT_TARGET,
                f"Timeouts remaining must be between 0 and {MAX_TIMEOUTS}.",
            )

    return None


# --- Factory helpers -------------------------------------------------------


def set_team_name(team: str, name: str, *, source: str = "operator") -> Command:
    return Command(CommandType.SET_TEAM_NAME, team=team, name=name, source=source)


def add_score(team: str, points: int, *, source: str = "operator") -> Command:
    return Command(CommandType.ADD_SCORE, team=team, points=points, source=source)


def correct_score(team: str, points: int, *, source: str = "operator") -> Command:
    """Build a -1/-2/-3/-6 correction; accepts the magnitude or a negative."""

    return Command(CommandType.CORRECT_SCORE, team=team, points=points, source=source)


def set_score(team: str, value: int, *, source: str = "operator") -> Command:
    return Command(CommandType.SET_SCORE, team=team, value=value, source=source)


def undo(*, source: str = "operator") -> Command:
    return Command(CommandType.UNDO, source=source)


def quarter_forward(*, confirmed: bool = False, source: str = "operator") -> Command:
    return Command(CommandType.QUARTER_FORWARD, confirmed=confirmed, source=source)


def quarter_back(*, confirmed: bool = False, source: str = "operator") -> Command:
    return Command(CommandType.QUARTER_BACK, confirmed=confirmed, source=source)


def set_quarter(label: str, *, confirmed: bool = False, source: str = "operator") -> Command:
    return Command(CommandType.SET_QUARTER, label=label, confirmed=confirmed, source=source)


def new_game(*, confirmed: bool = False, source: str = "operator") -> Command:
    return Command(CommandType.NEW_GAME, confirmed=confirmed, source=source)


def end_game(*, source: str = "operator") -> Command:
    return Command(CommandType.END_GAME, source=source)


def game_clock_start(*, source: str = "operator") -> Command:
    return Command(CommandType.GAME_CLOCK_START, source=source)


def game_clock_stop(*, source: str = "operator") -> Command:
    return Command(CommandType.GAME_CLOCK_STOP, source=source)


def game_clock_reset(*, source: str = "operator") -> Command:
    return Command(CommandType.GAME_CLOCK_RESET, source=source)


def game_clock_correct(seconds: float, *, source: str = "operator") -> Command:
    return Command(CommandType.GAME_CLOCK_CORRECT, seconds=seconds, source=source)


def play_clock_preset(seconds: float, *, source: str = "operator") -> Command:
    return Command(CommandType.PLAY_CLOCK_PRESET, seconds=seconds, source=source)


def play_clock_preset_start(seconds: float, *, source: str = "operator") -> Command:
    """Load a documented play-clock preset and begin counting down atomically."""

    return Command(CommandType.PLAY_CLOCK_PRESET_START, seconds=seconds, source=source)


def play_clock_start(*, source: str = "operator") -> Command:
    return Command(CommandType.PLAY_CLOCK_START, source=source)


def play_clock_stop(*, source: str = "operator") -> Command:
    return Command(CommandType.PLAY_CLOCK_STOP, source=source)


def play_clock_clear(*, source: str = "operator") -> Command:
    return Command(CommandType.PLAY_CLOCK_CLEAR, source=source)


def play_clock_reset(*, source: str = "operator") -> Command:
    return Command(CommandType.PLAY_CLOCK_RESET, source=source)


def play_clock_correct(seconds: float, *, source: str = "operator") -> Command:
    return Command(CommandType.PLAY_CLOCK_CORRECT, seconds=seconds, source=source)


def event_countdown_select(label: str, *, source: str = "operator") -> Command:
    """Load the 30:00 pregame or 15:00 interval countdown while stopped."""

    return Command(CommandType.EVENT_COUNTDOWN_SELECT, label=label, source=source)


def event_countdown_start(*, source: str = "operator") -> Command:
    return Command(CommandType.EVENT_COUNTDOWN_START, source=source)


def event_countdown_stop(*, source: str = "operator") -> Command:
    return Command(CommandType.EVENT_COUNTDOWN_STOP, source=source)


def event_countdown_reset(*, source: str = "operator") -> Command:
    return Command(CommandType.EVENT_COUNTDOWN_RESET, source=source)


def event_countdown_correct(seconds: float, *, source: str = "operator") -> Command:
    """Edit Current Time; the service stops the countdown before applying."""

    return Command(CommandType.EVENT_COUNTDOWN_CORRECT, seconds=seconds, source=source)


def set_down(down: int | None, *, source: str = "operator") -> Command:
    """Direct-select 1st through 4th down, or clear it with ``down=None``."""

    return Command(CommandType.SET_DOWN, value=down, source=source)


def set_distance(distance: int | None, *, source: str = "operator") -> Command:
    """Set yards to go (``0`` displays as Goal), or clear with ``distance=None``."""

    return Command(CommandType.SET_DISTANCE, value=distance, source=source)


def set_possession(team: str | None, *, source: str = "operator") -> Command:
    """Set which team has the ball, or clear it with ``team=None``."""

    return Command(CommandType.SET_POSSESSION, team=team, source=source)


def set_ball_on(team: str, yard_line: int, *, source: str = "operator") -> Command:
    """Set field position: ``yard_line`` yards from ``team``'s own goal line."""

    return Command(CommandType.SET_BALL_ON, team=team, value=yard_line, source=source)


def timeout_used(team: str, *, source: str = "operator") -> Command:
    """Record that ``team`` used a timeout, decrementing its count by one."""

    return Command(CommandType.TIMEOUT_USED, team=team, source=source)


def timeout_correct(team: str, points: int, *, source: str = "operator") -> Command:
    """Correct a timeout mis-count by +1 or -1."""

    return Command(CommandType.TIMEOUT_CORRECT, team=team, points=points, source=source)


def set_timeouts(team: str, value: int, *, source: str = "operator") -> Command:
    """Directly set ``team``'s timeouts remaining (0 to :data:`MAX_TIMEOUTS`)."""

    return Command(CommandType.SET_TIMEOUTS, team=team, value=value, source=source)


__all__ = [
    "CONFIRMATION_REQUIRED",
    "INVALID_BALL_ON",
    "INVALID_CLOCK_TIME",
    "INVALID_COMMAND",
    "INVALID_DISTANCE",
    "INVALID_DOWN",
    "INVALID_EVENT_PHASE",
    "INVALID_PLAY_CLOCK_PRESET",
    "INVALID_POSSESSION",
    "INVALID_QUARTER",
    "INVALID_SCORE_DELTA",
    "INVALID_SCORE_TARGET",
    "INVALID_TEAM",
    "INVALID_TEAM_NAME",
    "INVALID_TIMEOUT_DELTA",
    "INVALID_TIMEOUT_TARGET",
    "MAX_SCORE",
    "NON_UNDOABLE_COMMANDS",
    "NOTHING_TO_UNDO",
    "NOT_UNDOABLE",
    "PREGAME_LIFECYCLES",
    "QUARTER_OUT_OF_RANGE",
    "SCORE_ABOVE_MAXIMUM",
    "SCORE_BELOW_ZERO",
    "SCORE_INCREMENTS",
    "STALE_REVISION",
    "TEAMS",
    "TEAM_NAME_NOT_ALLOWED",
    "TIMEOUT_ABOVE_MAXIMUM",
    "TIMEOUT_BELOW_ZERO",
    "TIMEOUT_CORRECTION_MAGNITUDE",
    "UNDOABLE_COMMANDS",
    "Command",
    "CommandError",
    "CommandResult",
    "CommandType",
    "EventIntent",
    "UndoEntry",
    "add_score",
    "correct_score",
    "end_game",
    "event_countdown_correct",
    "event_countdown_reset",
    "event_countdown_select",
    "event_countdown_start",
    "event_countdown_stop",
    "game_clock_correct",
    "game_clock_reset",
    "game_clock_start",
    "game_clock_stop",
    "new_game",
    "play_clock_clear",
    "play_clock_correct",
    "play_clock_preset",
    "play_clock_preset_start",
    "play_clock_reset",
    "play_clock_start",
    "play_clock_stop",
    "quarter_back",
    "quarter_forward",
    "set_ball_on",
    "set_distance",
    "set_down",
    "set_possession",
    "set_quarter",
    "set_score",
    "set_team_name",
    "set_timeouts",
    "timeout_correct",
    "timeout_used",
    "undo",
    "validate_command",
]
