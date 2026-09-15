"""Immutable, validated authoritative soccer scoreboard state.

Mirrors ``scoreboard.domain.state`` (spec section 3.1, ``.scratch/soccer-mode/domain_draft.md``
section 1). Football is frozen; this is a parallel module, not a subclass -- see
``domain_draft.md`` section 0.1 for why the clock engine (``domain.soccer.clocks``) is a
second copy rather than a generalization of football's.

Deliberately reused *by import* from ``scoreboard.domain.state`` (not copied): ``ClockValue``,
``TEAM_SIDES``, ``MAX_TEAM_NAME_LENGTH``, ``setup_prompt_detail``. Everything else -- including
the ``StateValidationError`` exception type -- is soccer's own, so a soccer test asserting the
exception type is never coupled to football's module.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Final

from scoreboard.domain.state import (
    MAX_TEAM_NAME_LENGTH,
    TEAM_SIDES,
    ClockValue,
    setup_prompt_detail,
)

SOCCER_SCHEMA_VERSION: Final[int] = 1
APP_VERSION: Final[str] = "0.1.0"
MAX_SOCCER_SCORE: Final[int] = 99
DEFAULT_HOME_NAME: Final[str] = "HOME"
DEFAULT_AWAY_NAME: Final[str] = "AWAY"

#: Every period label in play order. Fixed regardless of ``SoccerRules.overtime_periods`` /
#: ``shootout_enabled`` -- a manual correction (``set_period``) can always reach any label, the
#: same way football's ``set_quarter("OT")`` always works. Only the *automatic* period-decision
#: prompt (``application.soccer_service``) filters what is offered at natural expiry.
PERIOD_LABELS: Final[tuple[str, ...]] = (
    "PRE",
    "1st",
    "HALF",
    "2nd",
    "OT1",
    "OT2",
    "SHOOTOUT",
    "FINAL",
)
LIVE_PERIODS: Final[tuple[str, ...]] = ("1st", "2nd", "OT1", "OT2")
LIVE_PERIOD_LABELS: Final[frozenset[str]] = frozenset(LIVE_PERIODS)
INTERVAL_PERIODS: Final[tuple[str, ...]] = ("PRE", "HALF")
INTERVAL_PERIOD_LABELS: Final[frozenset[str]] = frozenset(INTERVAL_PERIODS)
LIFECYCLE_LABELS: Final[tuple[str, ...]] = ("PRE_GAME", "IN_PROGRESS", "HALFTIME", "FINAL")

STAT_NAMES: Final[tuple[str, ...]] = ("shots", "saves", "corners", "fouls")
MAX_STAT_VALUE: Final[int] = 99

CARD_KINDS: Final[tuple[str, ...]] = ("yellow", "red")
MAX_CARD_PLAYER_NUMBER: Final[int] = 99

#: Spec section 3.1 -- three crowd words only (domain_draft.md's five-label draft is
#: superseded; the spec wins where they differ, per IMPLEMENTERS.md).
SOCCER_STATUS_LABELS: Final[tuple[str, ...]] = ("INJURY", "DELAY", "WEATHER")
#: The NCHSAA lightning wait is 30 minutes (spec section 3.1/8): the crowd status countdown's
#: ceiling is bounded by the longest crowd wait a WEATHER hold can need, not football's 5:00.
MAX_STATUS_CLOCK_SECONDS: Final[float] = 1800.0

MAX_GAME_CLOCK_MAXIMUM_SECONDS: Final[float] = 60 * 60
MAX_PREGAME_CLOCK_SECONDS: Final[float] = 30 * 60

MIN_SHOOTOUT_ROUND: Final[int] = 1
DEFAULT_INITIAL_KICKERS: Final[int] = 5


def lifecycle_for_period(label: str) -> str:
    """The lifecycle a period label implies, mirroring football's quarter->lifecycle mapping."""

    return {"PRE": "PRE_GAME", "HALF": "HALFTIME", "FINAL": "FINAL"}.get(label, "IN_PROGRESS")


class StateValidationError(ValueError):
    """Raised when a soccer state value or snapshot violates the domain contract.

    Deliberately not football's ``scoreboard.domain.state.StateValidationError`` -- see the
    module docstring.
    """


def _require_version(schema_version: int, app_version: str) -> None:
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise StateValidationError("schema_version must be an integer")
    if schema_version != SOCCER_SCHEMA_VERSION:
        raise StateValidationError(
            f"unsupported schema_version {schema_version!r}; expected {SOCCER_SCHEMA_VERSION}"
        )
    if not isinstance(app_version, str) or not app_version.strip():
        raise StateValidationError("app_version must be a non-empty string")


def _require_revision(revision: int) -> None:
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise StateValidationError("revision must be a non-negative integer")


def _require_name(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise StateValidationError(f"{field_name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise StateValidationError(f"{field_name} must not be empty")
    if len(trimmed) > MAX_TEAM_NAME_LENGTH:
        raise StateValidationError(
            f"{field_name} must be at most {MAX_TEAM_NAME_LENGTH} characters"
        )
    return trimmed


def _require_score(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateValidationError(f"{field_name} must be an integer")
    if not 0 <= value <= MAX_SOCCER_SCORE:
        raise StateValidationError(f"{field_name} must be between 0 and {MAX_SOCCER_SCORE}")
    return value


def _require_stat(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateValidationError(f"{field_name} must be an integer")
    if not 0 <= value <= MAX_STAT_VALUE:
        raise StateValidationError(f"{field_name} must be between 0 and {MAX_STAT_VALUE}")
    return value


def _require_optional_player_number(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise StateValidationError(f"{field_name} must be a whole number or null")
    if not 0 <= value <= MAX_CARD_PLAYER_NUMBER:
        raise StateValidationError(
            f"{field_name} must be between 0 and {MAX_CARD_PLAYER_NUMBER}, or null"
        )
    return value


def _require_optional_team_side(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if value not in TEAM_SIDES:
        raise StateValidationError(f"{field_name} must be 'home', 'away', or null")
    return value


@dataclass(frozen=True, slots=True)
class CardEvent:
    """One yellow or red card, captured at the moment it was shown.

    ``clock_display`` is captured text, not a recomputed value: a later game-clock correction
    must never retroactively rewrite a card's historical display (mirrors football's
    ``UndoEntry`` capturing plain values rather than references; see domain_draft.md section 1.2).
    """

    team: str
    kind: str
    player_number: int | None
    period: str
    clock_display: str

    def __post_init__(self) -> None:
        if self.team not in TEAM_SIDES:
            raise StateValidationError("card team must be 'home' or 'away'")
        if self.kind not in CARD_KINDS:
            raise StateValidationError(f"card kind must be one of {CARD_KINDS!r}")
        object.__setattr__(
            self,
            "player_number",
            _require_optional_player_number(self.player_number, "card player_number"),
        )
        if self.period not in PERIOD_LABELS:
            raise StateValidationError(f"invalid card period label: {self.period!r}")
        if not isinstance(self.clock_display, str) or not self.clock_display:
            raise StateValidationError("card clock_display must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ShootoutKick:
    """One kick from the mark."""

    team: str
    round: int
    kicker_number: int | None
    made: bool

    def __post_init__(self) -> None:
        if self.team not in TEAM_SIDES:
            raise StateValidationError("shootout kick team must be 'home' or 'away'")
        if isinstance(self.round, bool) or not isinstance(self.round, int) or self.round < MIN_SHOOTOUT_ROUND:
            raise StateValidationError(f"shootout round must be an integer >= {MIN_SHOOTOUT_ROUND}")
        object.__setattr__(
            self,
            "kicker_number",
            _require_optional_player_number(self.kicker_number, "shootout kicker_number"),
        )
        if not isinstance(self.made, bool):
            raise StateValidationError("shootout kick 'made' must be a boolean")


@dataclass(frozen=True, slots=True)
class SoccerState:
    """Complete authoritative soccer state at one revision."""

    schema_version: int = SOCCER_SCHEMA_VERSION
    app_version: str = APP_VERSION
    revision: int = 0

    home_name: str = DEFAULT_HOME_NAME
    away_name: str = DEFAULT_AWAY_NAME
    home_score: int = 0
    away_score: int = 0

    period: str = "PRE"
    lifecycle: str = "PRE_GAME"

    game_clock: ClockValue = ClockValue(
        MAX_PREGAME_CLOCK_SECONDS, False, MAX_PREGAME_CLOCK_SECONDS
    )

    home_shots: int = 0
    away_shots: int = 0
    home_saves: int = 0
    away_saves: int = 0
    home_corners: int = 0
    away_corners: int = 0
    home_fouls: int = 0
    away_fouls: int = 0

    cards: tuple[CardEvent, ...] = ()

    shootout_first_kicker: str | None = None
    shootout_kicks: tuple[ShootoutKick, ...] = ()
    shootout_winner: str | None = None

    game_status: str | None = None
    status_clock: ClockValue = ClockValue(0.0, False, MAX_STATUS_CLOCK_SECONDS)
    status_clock_cleared: bool = True

    def __post_init__(self) -> None:
        _require_version(self.schema_version, self.app_version)
        _require_revision(self.revision)
        object.__setattr__(self, "home_name", _require_name(self.home_name, "home_name"))
        object.__setattr__(self, "away_name", _require_name(self.away_name, "away_name"))
        object.__setattr__(self, "home_score", _require_score(self.home_score, "home_score"))
        object.__setattr__(self, "away_score", _require_score(self.away_score, "away_score"))
        if self.period not in PERIOD_LABELS:
            raise StateValidationError(f"invalid period label: {self.period!r}")
        if self.lifecycle not in LIFECYCLE_LABELS:
            raise StateValidationError(f"invalid lifecycle label: {self.lifecycle!r}")
        if not isinstance(self.game_clock, ClockValue):
            raise StateValidationError("game_clock must be a ClockValue")
        if not 0 < self.game_clock.maximum_seconds <= MAX_GAME_CLOCK_MAXIMUM_SECONDS:
            raise StateValidationError("game_clock has an invalid maximum")
        for name in (
            "home_shots", "away_shots", "home_saves", "away_saves",
            "home_corners", "away_corners", "home_fouls", "away_fouls",
        ):
            object.__setattr__(self, name, _require_stat(getattr(self, name), name))
        if not isinstance(self.cards, tuple) or not all(isinstance(c, CardEvent) for c in self.cards):
            raise StateValidationError("cards must be a tuple of CardEvent")
        object.__setattr__(
            self,
            "shootout_first_kicker",
            _require_optional_team_side(self.shootout_first_kicker, "shootout_first_kicker"),
        )
        if not isinstance(self.shootout_kicks, tuple) or not all(
            isinstance(k, ShootoutKick) for k in self.shootout_kicks
        ):
            raise StateValidationError("shootout_kicks must be a tuple of ShootoutKick")
        object.__setattr__(
            self, "shootout_winner", _require_optional_team_side(self.shootout_winner, "shootout_winner")
        )
        if self.game_status is not None and self.game_status not in SOCCER_STATUS_LABELS:
            raise StateValidationError(f"invalid game_status label: {self.game_status!r}")
        if not isinstance(self.status_clock, ClockValue):
            raise StateValidationError("status_clock must be a ClockValue")
        if self.status_clock.maximum_seconds != MAX_STATUS_CLOCK_SECONDS:
            raise StateValidationError("status_clock has an invalid maximum")
        if not isinstance(self.status_clock_cleared, bool):
            raise StateValidationError("status_clock_cleared must be boolean")

    # --- Derived properties (card and shootout tallies are never stored) ---

    @property
    def home_yellow(self) -> int:
        return sum(1 for c in self.cards if c.team == "home" and c.kind == "yellow")

    @property
    def home_red(self) -> int:
        return sum(1 for c in self.cards if c.team == "home" and c.kind == "red")

    @property
    def away_yellow(self) -> int:
        return sum(1 for c in self.cards if c.team == "away" and c.kind == "yellow")

    @property
    def away_red(self) -> int:
        return sum(1 for c in self.cards if c.team == "away" and c.kind == "red")

    @property
    def shootout_home_made(self) -> int:
        return sum(1 for k in self.shootout_kicks if k.team == "home" and k.made)

    @property
    def shootout_away_made(self) -> int:
        return sum(1 for k in self.shootout_kicks if k.team == "away" and k.made)

    @property
    def state_revision(self) -> int:
        return self.revision

    @property
    def home_team_name(self) -> str:
        return self.home_name

    @property
    def away_team_name(self) -> str:
        return self.away_name

    def evolve(self, **changes: Any) -> "SoccerState":
        """Return a validated next state and advance the revision by one."""

        allowed = {field.name for field in fields(self)}
        unknown = set(changes) - allowed
        if unknown:
            raise StateValidationError(f"unknown state field(s): {sorted(unknown)}")
        if "revision" in changes:
            raise StateValidationError("revision is advanced by accepted transitions")
        changes["revision"] = self.revision + 1
        return replace(self, **changes)


def default_state() -> SoccerState:
    """Return the documented stopped pregame baseline."""

    return SoccerState()


__all__ = [
    "APP_VERSION",
    "CARD_KINDS",
    "DEFAULT_AWAY_NAME",
    "DEFAULT_HOME_NAME",
    "DEFAULT_INITIAL_KICKERS",
    "INTERVAL_PERIODS",
    "INTERVAL_PERIOD_LABELS",
    "LIFECYCLE_LABELS",
    "LIVE_PERIODS",
    "LIVE_PERIOD_LABELS",
    "MAX_CARD_PLAYER_NUMBER",
    "MAX_GAME_CLOCK_MAXIMUM_SECONDS",
    "MAX_PREGAME_CLOCK_SECONDS",
    "MAX_SOCCER_SCORE",
    "MAX_STATUS_CLOCK_SECONDS",
    "MAX_STAT_VALUE",
    "MAX_TEAM_NAME_LENGTH",
    "MIN_SHOOTOUT_ROUND",
    "PERIOD_LABELS",
    "SOCCER_SCHEMA_VERSION",
    "SOCCER_STATUS_LABELS",
    "STAT_NAMES",
    "TEAM_SIDES",
    "CardEvent",
    "ClockValue",
    "ShootoutKick",
    "SoccerState",
    "StateValidationError",
    "default_state",
    "lifecycle_for_period",
    "setup_prompt_detail",
]
