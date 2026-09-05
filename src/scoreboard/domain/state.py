"""Immutable, validated authoritative scoreboard state.

This module deliberately contains no timing source or side effects. Clock values
are represented as data; a later clock component may update them through the
same immutable state transition boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Final


SCHEMA_VERSION: Final[int] = 1
APP_VERSION: Final[str] = "0.1.0"
MAX_TEAM_NAME_LENGTH: Final[int] = 24
MAX_SCORE: Final[int] = 199
MAX_GAME_CLOCK_SECONDS: Final[float] = 12 * 60
MAX_PLAY_CLOCK_SECONDS: Final[float] = 40
MAX_EVENT_COUNTDOWN_SECONDS: Final[float] = 30 * 60

QUARTER_LABELS: Final[tuple[str, ...]] = (
    "PRE",
    "1st",
    "2nd",
    "HALF",
    "3rd",
    "4th",
    "OT",
    "FINAL",
)
#: Labels for quarters in which the game clock has a live game-time meaning.
LIVE_QUARTER_LABELS: Final[frozenset[str]] = frozenset({"1st", "2nd", "3rd", "4th", "OT"})
LIFECYCLE_LABELS: Final[tuple[str, ...]] = (
    "PRE_GAME",
    "IN_PROGRESS",
    "HALFTIME",
    "FINAL",
)
EVENT_PHASE_LABELS: Final[tuple[str, ...]] = ("PREGAME", "HALFTIME", "WARMUP")


class StateValidationError(ValueError):
    """Raised when a state value or snapshot violates the domain contract."""


def _require_version(schema_version: int, app_version: str) -> None:
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise StateValidationError("schema_version must be an integer")
    if schema_version != SCHEMA_VERSION:
        raise StateValidationError(
            f"unsupported schema_version {schema_version!r}; expected {SCHEMA_VERSION}"
        )
    if not isinstance(app_version, str) or not app_version.strip():
        raise StateValidationError("app_version must be a non-empty string")
    # app_version is provenance, not a compatibility gate. Only schema_version
    # decides whether a stored game can be read. Gating on the application
    # version would make every saved game unrecoverable the moment the build
    # number changes, which is exactly when a mid-game restart is most likely
    # (P-004, P-006, W-006).


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
    if not 0 <= value <= MAX_SCORE:
        raise StateValidationError(
            f"{field_name} must be between 0 and {MAX_SCORE}"
        )
    return value


def _require_seconds(value: float, field_name: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateValidationError(f"{field_name} must be a number of seconds")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise StateValidationError(f"{field_name} must be finite")
    if not 0 <= result <= maximum:
        raise StateValidationError(
            f"{field_name} must be between 0 and {maximum:g} seconds"
        )
    return result


@dataclass(frozen=True, slots=True)
class ClockValue:
    """A materialized countdown value and its monotonic anchors."""

    seconds: float
    running: bool = False
    maximum_seconds: float = MAX_GAME_CLOCK_SECONDS
    deadline_monotonic: float | None = None
    started_at_monotonic: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.running, bool):
            raise StateValidationError("clock running must be a boolean")
        object.__setattr__(
            self,
            "seconds",
            _require_seconds(self.seconds, "clock seconds", self.maximum_seconds),
        )
        if self.maximum_seconds <= 0:
            raise StateValidationError("clock maximum_seconds must be positive")
        for field_name, value in (
            ("deadline_monotonic", self.deadline_monotonic),
            ("started_at_monotonic", self.started_at_monotonic),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StateValidationError(f"{field_name} must be a number of seconds")
            result = float(value)
            if result != result or result in (float("inf"), float("-inf")):
                raise StateValidationError(f"{field_name} must be finite")
            object.__setattr__(self, field_name, result)


@dataclass(frozen=True, slots=True)
class GameState:
    """Complete authoritative state at one revision."""

    schema_version: int = SCHEMA_VERSION
    app_version: str = APP_VERSION
    revision: int = 0
    home_name: str = "HOME"
    away_name: str = "AWAY"
    home_score: int = 0
    away_score: int = 0
    quarter: str = "PRE"
    lifecycle: str = "PRE_GAME"
    game_clock: ClockValue = ClockValue(MAX_GAME_CLOCK_SECONDS)
    play_clock: ClockValue = ClockValue(0.0, False, MAX_PLAY_CLOCK_SECONDS)
    event_countdown: ClockValue = ClockValue(
        MAX_EVENT_COUNTDOWN_SECONDS, False, MAX_EVENT_COUNTDOWN_SECONDS
    )
    event_phase: str = "PREGAME"

    play_clock_cleared: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.play_clock_cleared, bool):
            raise StateValidationError("play_clock_cleared must be boolean")
        _require_version(self.schema_version, self.app_version)
        _require_revision(self.revision)
        object.__setattr__(self, "home_name", _require_name(self.home_name, "home_name"))
        object.__setattr__(self, "away_name", _require_name(self.away_name, "away_name"))
        object.__setattr__(self, "home_score", _require_score(self.home_score, "home_score"))
        object.__setattr__(self, "away_score", _require_score(self.away_score, "away_score"))
        if self.quarter not in QUARTER_LABELS:
            raise StateValidationError(f"invalid quarter label: {self.quarter!r}")
        if self.lifecycle not in LIFECYCLE_LABELS:
            raise StateValidationError(f"invalid lifecycle label: {self.lifecycle!r}")
        if self.event_phase not in EVENT_PHASE_LABELS:
            raise StateValidationError(f"invalid event phase: {self.event_phase!r}")
        if not isinstance(self.game_clock, ClockValue):
            raise StateValidationError("game_clock must be a ClockValue")
        if self.game_clock.maximum_seconds != MAX_GAME_CLOCK_SECONDS:
            raise StateValidationError("game_clock has an invalid maximum")
        if not isinstance(self.play_clock, ClockValue):
            raise StateValidationError("play_clock must be a ClockValue")
        if self.play_clock.maximum_seconds != MAX_PLAY_CLOCK_SECONDS:
            raise StateValidationError("play_clock has an invalid maximum")
        if not isinstance(self.event_countdown, ClockValue):
            raise StateValidationError("event_countdown must be a ClockValue")
        if self.event_countdown.maximum_seconds != MAX_EVENT_COUNTDOWN_SECONDS:
            raise StateValidationError("event_countdown has an invalid maximum")

    @property
    def state_revision(self) -> int:
        """Compatibility name for consumers that call the field a state revision."""

        return self.revision

    @property
    def home_team_name(self) -> str:
        return self.home_name

    @property
    def away_team_name(self) -> str:
        return self.away_name

    def evolve(self, **changes: Any) -> "GameState":
        """Return a validated next state and advance the revision by one.

        The current object is never changed. Invalid changes raise
        ``StateValidationError`` before a replacement can be returned.
        """

        allowed = {field.name for field in fields(self)}
        unknown = set(changes) - allowed
        if unknown:
            raise StateValidationError(f"unknown state field(s): {sorted(unknown)}")
        if "revision" in changes:
            raise StateValidationError("revision is advanced by accepted transitions")
        changes["revision"] = self.revision + 1
        return replace(self, **changes)


def default_state() -> GameState:
    """Return the documented stopped pregame baseline."""

    return GameState()
