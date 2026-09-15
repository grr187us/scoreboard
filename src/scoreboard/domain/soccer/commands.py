"""Command, result, and pure validation types for the soccer command service.

Mirrors ``scoreboard.domain.commands``. Deliberately pure: no state, no clock, no filesystem.
Own ``SoccerCommandType`` enum, own error codes -- a football test that iterates football's
``CommandType`` must never see a soccer member (spec/IMPLEMENTERS.md interface contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Mapping

from scoreboard.domain.soccer.state import (
    CARD_KINDS,
    MAX_CARD_PLAYER_NUMBER,
    MAX_SOCCER_SCORE,
    MAX_STATUS_CLOCK_SECONDS,
    PERIOD_LABELS,
    SOCCER_STATUS_LABELS,
    STAT_NAMES,
    TEAM_SIDES,
)

PREGAME_LIFECYCLES: Final[tuple[str, ...]] = ("PRE_GAME",)


class SoccerCommandType(str, Enum):
    """Every mutation the soccer command service accepts (spec section 3.2)."""

    SET_TEAM_NAME = "set_team_name"
    ADD_GOAL = "add_goal"
    CORRECT_GOAL = "correct_goal"
    SET_SCORE = "set_score"
    UNDO = "undo"
    PERIOD_FORWARD = "period_forward"
    PERIOD_BACK = "period_back"
    SET_PERIOD = "set_period"
    NEW_GAME = "new_game"
    END_GAME = "end_game"
    GAME_CLOCK_START = "game_clock_start"
    GAME_CLOCK_STOP = "game_clock_stop"
    GAME_CLOCK_RESET = "game_clock_reset"
    GAME_CLOCK_CORRECT = "game_clock_correct"
    ADD_STAT = "add_stat"
    SET_STAT = "set_stat"
    ADD_CARD = "add_card"
    REMOVE_CARD = "remove_card"
    SET_SHOOTOUT_FIRST_KICKER = "set_shootout_first_kicker"
    SHOOTOUT_KICK = "shootout_kick"
    SHOOTOUT_CORRECT_KICK = "shootout_correct_kick"
    SHOOTOUT_REMOVE_LAST = "shootout_remove_last"
    FINISH_SHOOTOUT = "finish_shootout"
    SET_GAME_STATUS = "set_game_status"
    CLEAR_GAME_STATUS = "clear_game_status"
    STATUS_CLOCK_START = "status_clock_start"
    STATUS_CLOCK_STOP = "status_clock_stop"


# --- Error codes -------------------------------------------------------------

INVALID_COMMAND: Final[str] = "INVALID_COMMAND"
INVALID_TEAM: Final[str] = "INVALID_TEAM"
INVALID_TEAM_NAME: Final[str] = "INVALID_TEAM_NAME"
TEAM_NAME_NOT_ALLOWED: Final[str] = "TEAM_NAME_NOT_ALLOWED"
INVALID_SCORE_TARGET: Final[str] = "INVALID_SCORE_TARGET"
SCORE_ABOVE_MAXIMUM: Final[str] = "SCORE_ABOVE_MAXIMUM"
SCORE_BELOW_ZERO: Final[str] = "SCORE_BELOW_ZERO"
GOAL_NOT_ALLOWED: Final[str] = "GOAL_NOT_ALLOWED"
INVALID_GOAL_PLAYER: Final[str] = "INVALID_GOAL_PLAYER"
INVALID_PERIOD: Final[str] = "INVALID_PERIOD"
PERIOD_OUT_OF_RANGE: Final[str] = "PERIOD_OUT_OF_RANGE"
CONFIRMATION_REQUIRED: Final[str] = "CONFIRMATION_REQUIRED"
NOTHING_TO_UNDO: Final[str] = "NOTHING_TO_UNDO"
NOT_UNDOABLE: Final[str] = "NOT_UNDOABLE"
INVALID_CLOCK_TIME: Final[str] = "INVALID_CLOCK_TIME"
STALE_REVISION: Final[str] = "STALE_REVISION"
INVALID_STAT: Final[str] = "INVALID_STAT"
INVALID_STAT_VALUE: Final[str] = "INVALID_STAT_VALUE"
INVALID_STAT_STEP: Final[str] = "INVALID_STAT_STEP"
INVALID_CARD_KIND: Final[str] = "INVALID_CARD_KIND"
INVALID_CARD_PLAYER: Final[str] = "INVALID_CARD_PLAYER"
INVALID_CARD_INDEX: Final[str] = "INVALID_CARD_INDEX"
INVALID_SHOOTOUT_TEAM: Final[str] = "INVALID_SHOOTOUT_TEAM"
INVALID_SHOOTOUT_KICK: Final[str] = "INVALID_SHOOTOUT_KICK"
INVALID_SHOOTOUT_INDEX: Final[str] = "INVALID_SHOOTOUT_INDEX"
SHOOTOUT_NOT_DECIDED: Final[str] = "SHOOTOUT_NOT_DECIDED"
SHOOTOUT_WINNER_MISMATCH: Final[str] = "SHOOTOUT_WINNER_MISMATCH"
SHOOTOUT_NOT_ACTIVE: Final[str] = "SHOOTOUT_NOT_ACTIVE"
INVALID_GAME_STATUS: Final[str] = "INVALID_GAME_STATUS"
INVALID_STATUS_CLOCK_PRESET: Final[str] = "INVALID_STATUS_CLOCK_PRESET"

MAX_UNDO_DEPTH: Final[int] = 20

SOCCER_UNDOABLE_COMMANDS: Final[frozenset[SoccerCommandType]] = frozenset(
    {
        SoccerCommandType.ADD_GOAL,
        SoccerCommandType.CORRECT_GOAL,
        SoccerCommandType.SET_SCORE,
        SoccerCommandType.PERIOD_FORWARD,
        SoccerCommandType.PERIOD_BACK,
        SoccerCommandType.SET_PERIOD,
        SoccerCommandType.ADD_STAT,
        SoccerCommandType.SET_STAT,
        SoccerCommandType.ADD_CARD,
        SoccerCommandType.REMOVE_CARD,
        SoccerCommandType.SET_SHOOTOUT_FIRST_KICKER,
        SoccerCommandType.SHOOTOUT_KICK,
        SoccerCommandType.SHOOTOUT_CORRECT_KICK,
        SoccerCommandType.SHOOTOUT_REMOVE_LAST,
    }
)

#: Commands that are never undoable and always clear the stack (barriers). Crowd-status and
#: clock commands, and set_team_name, are in NEITHER set (F3-style exemption).
SOCCER_NON_UNDOABLE_COMMANDS: Final[frozenset[SoccerCommandType]] = frozenset(
    {
        SoccerCommandType.NEW_GAME,
        SoccerCommandType.END_GAME,
        SoccerCommandType.UNDO,
        SoccerCommandType.FINISH_SHOOTOUT,
    }
)

#: Every command's allowed argument keys, for ``build_soccer_command``'s airlock.
SOCCER_ALLOWED_ARGUMENTS: Final[dict[SoccerCommandType, frozenset[str]]] = {
    SoccerCommandType.SET_TEAM_NAME: frozenset({"team", "name"}),
    SoccerCommandType.ADD_GOAL: frozenset({"team", "player"}),
    SoccerCommandType.CORRECT_GOAL: frozenset({"team"}),
    SoccerCommandType.SET_SCORE: frozenset({"team", "value"}),
    SoccerCommandType.UNDO: frozenset(),
    SoccerCommandType.PERIOD_FORWARD: frozenset({"confirmed"}),
    SoccerCommandType.PERIOD_BACK: frozenset({"confirmed"}),
    SoccerCommandType.SET_PERIOD: frozenset({"label", "confirmed"}),
    SoccerCommandType.NEW_GAME: frozenset({"confirmed"}),
    SoccerCommandType.END_GAME: frozenset(),
    SoccerCommandType.GAME_CLOCK_START: frozenset(),
    SoccerCommandType.GAME_CLOCK_STOP: frozenset(),
    SoccerCommandType.GAME_CLOCK_RESET: frozenset(),
    SoccerCommandType.GAME_CLOCK_CORRECT: frozenset({"seconds"}),
    SoccerCommandType.ADD_STAT: frozenset({"team", "stat", "step"}),
    SoccerCommandType.SET_STAT: frozenset({"team", "stat", "value"}),
    SoccerCommandType.ADD_CARD: frozenset({"team", "kind", "player"}),
    SoccerCommandType.REMOVE_CARD: frozenset({"team", "index"}),
    SoccerCommandType.SET_SHOOTOUT_FIRST_KICKER: frozenset({"team"}),
    SoccerCommandType.SHOOTOUT_KICK: frozenset({"team", "made", "player"}),
    SoccerCommandType.SHOOTOUT_CORRECT_KICK: frozenset({"index", "made"}),
    SoccerCommandType.SHOOTOUT_REMOVE_LAST: frozenset(),
    SoccerCommandType.FINISH_SHOOTOUT: frozenset({"winner"}),
    SoccerCommandType.SET_GAME_STATUS: frozenset({"label", "seconds"}),
    SoccerCommandType.CLEAR_GAME_STATUS: frozenset(),
    SoccerCommandType.STATUS_CLOCK_START: frozenset(),
    SoccerCommandType.STATUS_CLOCK_STOP: frozenset(),
}

_TEAM_COMMANDS: Final[frozenset[SoccerCommandType]] = frozenset(
    {
        SoccerCommandType.SET_TEAM_NAME,
        SoccerCommandType.ADD_GOAL,
        SoccerCommandType.CORRECT_GOAL,
        SoccerCommandType.SET_SCORE,
        SoccerCommandType.ADD_STAT,
        SoccerCommandType.SET_STAT,
        SoccerCommandType.ADD_CARD,
        SoccerCommandType.REMOVE_CARD,
        SoccerCommandType.SET_SHOOTOUT_FIRST_KICKER,
        SoccerCommandType.SHOOTOUT_KICK,
    }
)


@dataclass(frozen=True, slots=True)
class SoccerCommandError:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise TypeError("error code must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise TypeError("error message must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SoccerCommand:
    """One request submitted to the soccer command service."""

    type: SoccerCommandType
    team: str | None = None
    name: str | None = None
    value: int | None = None
    player: int | None = None
    label: str | None = None
    seconds: float | None = None
    stat: str | None = None
    step: int | None = None
    kind: str | None = None
    made: bool | None = None
    index: int | None = None
    winner: str | None = None
    confirmed: bool = False
    source: str = "operator"
    expected_revision: int | None = None


@dataclass(frozen=True, slots=True)
class SoccerEventIntent:
    command: SoccerCommandType
    field: str
    old_value: Any
    new_value: Any
    team: str | None = None
    source: str = "operator"


@dataclass(frozen=True, slots=True)
class SoccerUndoEntry:
    command: SoccerCommandType
    field: str
    old_value: Any
    new_value: Any
    team: str | None = None
    old_values: Mapping[str, Any] | None = None
    new_values: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SoccerCommandResult:
    accepted: bool
    state: Any
    snapshot: dict[str, Any]
    event: SoccerEventIntent | None = None
    error: SoccerCommandError | None = None
    confirmation_required: bool = False
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


def validate_soccer_command(command: SoccerCommand) -> SoccerCommandError | None:
    """Check a request's shape without consulting any state."""

    if not isinstance(command, SoccerCommand):
        raise TypeError("command must be a SoccerCommand")
    if not isinstance(command.type, SoccerCommandType):
        return SoccerCommandError(INVALID_COMMAND, f"Unknown command: {command.type!r}.")
    if command.expected_revision is not None and not _is_int(command.expected_revision):
        return SoccerCommandError(INVALID_COMMAND, "Expected revision must be a whole number.")
    if not isinstance(command.confirmed, bool):
        return SoccerCommandError(INVALID_COMMAND, "Confirmation flag must be true or false.")

    if command.type in _TEAM_COMMANDS and command.team not in TEAM_SIDES:
        return SoccerCommandError(INVALID_TEAM, f"Choose the home or away team; got {command.team!r}.")

    if command.type is SoccerCommandType.SET_TEAM_NAME and not isinstance(command.name, str):
        return SoccerCommandError(INVALID_TEAM_NAME, "A team name must be text.")

    if command.type is SoccerCommandType.ADD_GOAL and command.player is not None:
        if not _is_int(command.player) or not 0 <= command.player <= MAX_CARD_PLAYER_NUMBER:
            return SoccerCommandError(
                INVALID_GOAL_PLAYER, f"Player number must be 0 to {MAX_CARD_PLAYER_NUMBER}, or cleared."
            )

    if command.type is SoccerCommandType.SET_SCORE:
        if not _is_int(command.value):
            return SoccerCommandError(INVALID_SCORE_TARGET, "Direct score entry needs a whole-number target.")
        if command.value < 0:
            return SoccerCommandError(INVALID_SCORE_TARGET, "A score cannot be set below 0.")
        if command.value > MAX_SOCCER_SCORE:
            return SoccerCommandError(
                SCORE_ABOVE_MAXIMUM,
                f"The board supports scores from 0 to {MAX_SOCCER_SCORE}; {command.value} is out of range.",
            )

    if command.type is SoccerCommandType.SET_PERIOD and command.label not in PERIOD_LABELS:
        return SoccerCommandError(
            INVALID_PERIOD,
            f"{command.label!r} is not a period label. Choose one of: " + ", ".join(PERIOD_LABELS) + ".",
        )

    if command.type is SoccerCommandType.GAME_CLOCK_CORRECT:
        if not _is_number(command.seconds):
            return SoccerCommandError(INVALID_CLOCK_TIME, "A clock correction needs a number of seconds.")
        numeric = float(command.seconds)
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            return SoccerCommandError(INVALID_CLOCK_TIME, "A clock correction must be a finite time.")
        if numeric < 0:
            return SoccerCommandError(INVALID_CLOCK_TIME, "A clock cannot be corrected below 0:00.")

    if command.type in (SoccerCommandType.ADD_STAT, SoccerCommandType.SET_STAT):
        if command.stat not in STAT_NAMES:
            return SoccerCommandError(
                INVALID_STAT, f"{command.stat!r} is not a stat. Choose one of: " + ", ".join(STAT_NAMES) + "."
            )
    if command.type is SoccerCommandType.ADD_STAT:
        if not _is_int(command.step) or command.step not in (1, -1):
            return SoccerCommandError(INVALID_STAT_STEP, "A stat step is +1 or -1.")
    if command.type is SoccerCommandType.SET_STAT:
        if not _is_int(command.value) or not 0 <= command.value <= 99:
            return SoccerCommandError(INVALID_STAT_VALUE, "A stat value must be between 0 and 99.")

    if command.type is SoccerCommandType.ADD_CARD:
        if command.kind not in CARD_KINDS:
            return SoccerCommandError(
                INVALID_CARD_KIND, f"{command.kind!r} is not a card kind. Choose one of: " + ", ".join(CARD_KINDS) + "."
            )
        if command.player is not None and (
            not _is_int(command.player) or not 0 <= command.player <= MAX_CARD_PLAYER_NUMBER
        ):
            return SoccerCommandError(
                INVALID_CARD_PLAYER, f"Player number must be 0 to {MAX_CARD_PLAYER_NUMBER}, or cleared."
            )

    if command.type is SoccerCommandType.REMOVE_CARD:
        if not _is_int(command.index) or command.index < 0:
            return SoccerCommandError(INVALID_CARD_INDEX, "A card index must be a non-negative whole number.")

    if command.type is SoccerCommandType.SET_SHOOTOUT_FIRST_KICKER:
        if command.team not in TEAM_SIDES:
            return SoccerCommandError(INVALID_SHOOTOUT_TEAM, "Choose the home or away team to kick first.")

    if command.type is SoccerCommandType.SHOOTOUT_KICK:
        if not isinstance(command.made, bool):
            return SoccerCommandError(INVALID_SHOOTOUT_KICK, "A shootout kick needs made true or false.")
        if command.player is not None and (
            not _is_int(command.player) or not 0 <= command.player <= MAX_CARD_PLAYER_NUMBER
        ):
            return SoccerCommandError(
                INVALID_SHOOTOUT_KICK, f"Kicker number must be 0 to {MAX_CARD_PLAYER_NUMBER}, or cleared."
            )

    if command.type is SoccerCommandType.SHOOTOUT_CORRECT_KICK:
        if not _is_int(command.index) or command.index < 0:
            return SoccerCommandError(INVALID_SHOOTOUT_INDEX, "A shootout kick index must be a non-negative whole number.")
        if not isinstance(command.made, bool):
            return SoccerCommandError(INVALID_SHOOTOUT_KICK, "A shootout kick correction needs made true or false.")

    if command.type is SoccerCommandType.FINISH_SHOOTOUT:
        if command.winner is not None and command.winner not in TEAM_SIDES:
            return SoccerCommandError(INVALID_SHOOTOUT_TEAM, "The shootout winner must be 'home' or 'away'.")

    if command.type is SoccerCommandType.SET_GAME_STATUS:
        if command.label not in SOCCER_STATUS_LABELS:
            return SoccerCommandError(
                INVALID_GAME_STATUS,
                f"{command.label!r} is not a crowd status. Choose one of: " + ", ".join(SOCCER_STATUS_LABELS) + ".",
            )
        if command.seconds is not None and (
            not _is_number(command.seconds)
            or float(command.seconds) != int(float(command.seconds))
            or not 1 <= float(command.seconds) <= MAX_STATUS_CLOCK_SECONDS
        ):
            return SoccerCommandError(
                INVALID_STATUS_CLOCK_PRESET,
                f"The status countdown loads a whole number of seconds, from 1 to {MAX_STATUS_CLOCK_SECONDS:g}.",
            )

    return None


def build_soccer_command(
    name: str,
    args: Mapping[str, Any],
    expected_revision: int | None,
    *,
    source: str = "operator",
) -> SoccerCommand | SoccerCommandError:
    """The airlock: turn a bridge-level request into a validated ``SoccerCommand``.

    Mirrors ``host.bridge.build_command``. Rejects an unknown command name or a disallowed
    argument key before any :class:`SoccerCommand` is constructed.
    """

    try:
        command_type = SoccerCommandType(name)
    except ValueError:
        return SoccerCommandError(INVALID_COMMAND, f"Unknown command: {name!r}.")
    allowed = SOCCER_ALLOWED_ARGUMENTS[command_type]
    unknown = set(args) - allowed - {"confirmed"}
    if unknown:
        return SoccerCommandError(
            INVALID_COMMAND, f"{name} does not accept: " + ", ".join(sorted(unknown)) + "."
        )
    command = SoccerCommand(
        type=command_type,
        team=args.get("team"),
        name=args.get("name"),
        value=args.get("value"),
        player=args.get("player"),
        label=args.get("label"),
        seconds=args.get("seconds"),
        stat=args.get("stat"),
        step=args.get("step"),
        kind=args.get("kind"),
        made=args.get("made"),
        index=args.get("index"),
        winner=args.get("winner"),
        confirmed=bool(args.get("confirmed", False)),
        source=source,
        expected_revision=expected_revision,
    )
    shape_error = validate_soccer_command(command)
    if shape_error is not None:
        return shape_error
    return command


# --- Factory helpers -----------------------------------------------------------


def set_team_name(team: str, name: str, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SET_TEAM_NAME, team=team, name=name, source=source)


def add_goal(team: str, *, player: int | None = None, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.ADD_GOAL, team=team, player=player, source=source)


def correct_goal(team: str, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.CORRECT_GOAL, team=team, source=source)


def set_score(team: str, value: int, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SET_SCORE, team=team, value=value, source=source)


def undo(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.UNDO, source=source)


def period_forward(*, confirmed: bool = False, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.PERIOD_FORWARD, confirmed=confirmed, source=source)


def period_back(*, confirmed: bool = False, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.PERIOD_BACK, confirmed=confirmed, source=source)


def set_period(label: str, *, confirmed: bool = False, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SET_PERIOD, label=label, confirmed=confirmed, source=source)


def new_game(*, confirmed: bool = False, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.NEW_GAME, confirmed=confirmed, source=source)


def end_game(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.END_GAME, source=source)


def game_clock_start(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.GAME_CLOCK_START, source=source)


def game_clock_stop(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.GAME_CLOCK_STOP, source=source)


def game_clock_reset(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.GAME_CLOCK_RESET, source=source)


def game_clock_correct(seconds: float, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.GAME_CLOCK_CORRECT, seconds=seconds, source=source)


def add_stat(team: str, stat: str, step: int, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.ADD_STAT, team=team, stat=stat, step=step, source=source)


def set_stat(team: str, stat: str, value: int, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SET_STAT, team=team, stat=stat, value=value, source=source)


def add_card(team: str, kind: str, *, player: int | None = None, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.ADD_CARD, team=team, kind=kind, player=player, source=source)


def remove_card(team: str, index: int, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.REMOVE_CARD, team=team, index=index, source=source)


def set_shootout_first_kicker(team: str, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SET_SHOOTOUT_FIRST_KICKER, team=team, source=source)


def shootout_kick(
    team: str, made: bool, *, player: int | None = None, source: str = "operator"
) -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SHOOTOUT_KICK, team=team, made=made, player=player, source=source)


def shootout_correct_kick(index: int, made: bool, *, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SHOOTOUT_CORRECT_KICK, index=index, made=made, source=source)


def shootout_remove_last(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SHOOTOUT_REMOVE_LAST, source=source)


def finish_shootout(*, winner: str | None = None, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.FINISH_SHOOTOUT, winner=winner, source=source)


def set_game_status(label: str, *, seconds: float | None = None, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.SET_GAME_STATUS, label=label, seconds=seconds, source=source)


def clear_game_status(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.CLEAR_GAME_STATUS, source=source)


def status_clock_start(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.STATUS_CLOCK_START, source=source)


def status_clock_stop(*, source: str = "operator") -> SoccerCommand:
    return SoccerCommand(SoccerCommandType.STATUS_CLOCK_STOP, source=source)


__all__ = [
    "CONFIRMATION_REQUIRED",
    "GOAL_NOT_ALLOWED",
    "INVALID_CARD_INDEX",
    "INVALID_CARD_KIND",
    "INVALID_CARD_PLAYER",
    "INVALID_CLOCK_TIME",
    "INVALID_COMMAND",
    "INVALID_GAME_STATUS",
    "INVALID_GOAL_PLAYER",
    "INVALID_PERIOD",
    "INVALID_SCORE_TARGET",
    "INVALID_SHOOTOUT_INDEX",
    "INVALID_SHOOTOUT_KICK",
    "INVALID_SHOOTOUT_TEAM",
    "INVALID_STATUS_CLOCK_PRESET",
    "INVALID_STAT",
    "INVALID_STAT_STEP",
    "INVALID_STAT_VALUE",
    "INVALID_TEAM",
    "INVALID_TEAM_NAME",
    "MAX_UNDO_DEPTH",
    "NOTHING_TO_UNDO",
    "NOT_UNDOABLE",
    "PERIOD_OUT_OF_RANGE",
    "PREGAME_LIFECYCLES",
    "SCORE_ABOVE_MAXIMUM",
    "SCORE_BELOW_ZERO",
    "SHOOTOUT_NOT_ACTIVE",
    "SHOOTOUT_NOT_DECIDED",
    "SHOOTOUT_WINNER_MISMATCH",
    "SOCCER_ALLOWED_ARGUMENTS",
    "SOCCER_NON_UNDOABLE_COMMANDS",
    "SOCCER_UNDOABLE_COMMANDS",
    "STALE_REVISION",
    "TEAM_NAME_NOT_ALLOWED",
    "SoccerCommand",
    "SoccerCommandError",
    "SoccerCommandResult",
    "SoccerCommandType",
    "SoccerEventIntent",
    "SoccerUndoEntry",
    "add_card",
    "add_goal",
    "add_stat",
    "build_soccer_command",
    "clear_game_status",
    "correct_goal",
    "end_game",
    "finish_shootout",
    "game_clock_correct",
    "game_clock_reset",
    "game_clock_start",
    "game_clock_stop",
    "new_game",
    "period_back",
    "period_forward",
    "remove_card",
    "set_game_status",
    "set_period",
    "set_score",
    "set_shootout_first_kicker",
    "set_stat",
    "set_team_name",
    "shootout_correct_kick",
    "shootout_kick",
    "shootout_remove_last",
    "status_clock_start",
    "status_clock_stop",
    "undo",
    "validate_soccer_command",
]
