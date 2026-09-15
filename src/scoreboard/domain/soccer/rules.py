"""Soccer's timing and gameplay rules (spec section 8, domain_draft.md section 2).

Mirrors ``scoreboard.domain.rules``. Not game state: lives in soccer's own ``config.json``
(``<root>/soccer/config.json``, section ``"rules"``) and is consulted only at the moment a
length loads -- New Game, a period change, the WEATHER crowd button -- never retroactively.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Any, Final, Mapping

from scoreboard.domain.soccer.state import MAX_STATUS_CLOCK_SECONDS, StateValidationError

if TYPE_CHECKING:
    from scoreboard.infrastructure.paths import ScoreboardPaths


class RulesError(ValueError):
    """A rule value the operator asked for is outside what the board can run."""


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _whole_seconds(value: Any, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RulesError(f"{label} must be a number of seconds.")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise RulesError(f"{label} must be a finite number of seconds.")
    if numeric != int(numeric):
        raise RulesError(f"{label} must be whole seconds.")
    if not minimum <= numeric <= maximum:
        raise RulesError(f"{label} must be between {_clock(minimum)} and {_clock(maximum)}.")
    return numeric


def _whole_count(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float) and value == int(value):
            value = int(value)
        else:
            raise RulesError(f"{label} must be a whole number.")
    if not minimum <= value <= maximum:
        raise RulesError(f"{label} must be between {minimum} and {maximum}.")
    return value


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise RulesError(f"{label} must be true or false.")
    return value


def _choice(value: Any, label: str, options: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in options:
        raise RulesError(f"{label} must be one of: " + ", ".join(options) + ".")
    return value


MERCY_APPLIES_CHOICES: Final[tuple[str, ...]] = ("halftime_and_second_half", "any_time", "off")
CLOCK_DIRECTION_CHOICES: Final[tuple[str, ...]] = ("down", "up")

#: The Setup drawer rows, in display order. ``kind`` is one of clock/count/toggle/choice/note.
#: The ``"note"`` row has no corresponding dataclass field -- consumers special-case it and skip
#: ``getattr()`` (see ``.scratch/soccer-mode/api_domain.md``).
SOCCER_RULE_FIELDS: Final[tuple[tuple[str, str, str], ...]] = (
    ("half_seconds", "Half length", "clock"),
    ("halftime_seconds", "Halftime countdown", "clock"),
    ("warmup_seconds", "Warmup label at", "clock"),
    ("pregame_seconds", "Pregame countdown", "clock"),
    ("overtime_periods", "Overtime periods", "count"),
    ("overtime_seconds", "Overtime period length", "clock"),
    ("golden_goal", "Golden goal ends overtime", "toggle"),
    ("shootout_enabled", "Kicks from the mark after overtime", "toggle"),
    ("shootout_initial_kickers", "Shootout kickers", "count"),
    ("shootout_credit_goal", "Add one goal to the shootout winner", "toggle"),
    ("mercy_differential", "Mercy-rule goal differential", "count"),
    ("mercy_applies", "Mercy rule applies", "choice"),
    ("stop_clock_on_goal", "Stop the clock when a goal is recorded", "toggle"),
    ("clock_direction", "Game clock counts", "choice"),
    ("weather_seconds", "WEATHER countdown", "clock"),
    (
        "late_sub_note",
        "Stop the clock for a leading team's substitution in the last 5:00 (NFHS 7-4-3)",
        "note",
    ),
)


@dataclass(frozen=True, slots=True)
class SoccerRules:
    """Every configurable soccer rule value (spec section 8)."""

    half_seconds: float = 40 * 60.0
    halftime_seconds: float = 10 * 60.0
    warmup_seconds: float = 3 * 60.0
    pregame_seconds: float = 30 * 60.0
    overtime_periods: int = 2
    overtime_seconds: float = 10 * 60.0
    golden_goal: bool = False
    shootout_enabled: bool = False
    shootout_initial_kickers: int = 5
    shootout_credit_goal: bool = True
    mercy_differential: int = 9
    mercy_applies: str = "halftime_and_second_half"
    stop_clock_on_goal: bool = True
    clock_direction: str = "down"
    weather_seconds: float = 30 * 60.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "half_seconds",
            _whole_seconds(self.half_seconds, "Half length", minimum=5 * 60.0, maximum=60 * 60.0),
        )
        object.__setattr__(
            self, "halftime_seconds",
            _whole_seconds(self.halftime_seconds, "Halftime countdown", minimum=60.0, maximum=60 * 60.0),
        )
        object.__setattr__(
            self, "warmup_seconds",
            _whole_seconds(self.warmup_seconds, "Warmup label", minimum=0.0,
                           maximum=max(0.0, self.halftime_seconds - 1.0) or self.halftime_seconds),
        )
        object.__setattr__(
            self, "pregame_seconds",
            _whole_seconds(self.pregame_seconds, "Pregame countdown", minimum=60.0, maximum=60 * 60.0),
        )
        object.__setattr__(
            self, "overtime_periods",
            _whole_count(self.overtime_periods, "Overtime periods", minimum=0, maximum=2),
        )
        object.__setattr__(
            self, "overtime_seconds",
            _whole_seconds(self.overtime_seconds, "Overtime period length", minimum=60.0, maximum=20 * 60.0),
        )
        object.__setattr__(self, "golden_goal", _bool(self.golden_goal, "Golden goal"))
        object.__setattr__(self, "shootout_enabled", _bool(self.shootout_enabled, "Shootout after overtime"))
        object.__setattr__(
            self, "shootout_initial_kickers",
            _whole_count(self.shootout_initial_kickers, "Shootout kickers", minimum=1, maximum=11),
        )
        object.__setattr__(
            self, "shootout_credit_goal",
            _bool(self.shootout_credit_goal, "Credit shootout winner a goal"),
        )
        object.__setattr__(
            self, "mercy_differential",
            _whole_count(self.mercy_differential, "Mercy-rule goal differential", minimum=0, maximum=20),
        )
        object.__setattr__(
            self, "mercy_applies",
            _choice(self.mercy_applies, "Mercy rule applies", MERCY_APPLIES_CHOICES),
        )
        object.__setattr__(
            self, "stop_clock_on_goal", _bool(self.stop_clock_on_goal, "Stop clock automatically on a goal"),
        )
        object.__setattr__(
            self, "clock_direction",
            _choice(self.clock_direction, "Game clock direction", CLOCK_DIRECTION_CHOICES),
        )
        object.__setattr__(
            self, "weather_seconds",
            _whole_seconds(self.weather_seconds, "WEATHER countdown", minimum=1.0, maximum=MAX_STATUS_CLOCK_SECONDS),
        )

    def period_seconds(self, period: str) -> float | None:
        """The stopped length the game clock loads on entering ``period``."""

        if period == "PRE":
            return self.pregame_seconds
        if period == "HALF":
            return self.halftime_seconds
        if period in ("OT1", "OT2"):
            return self.overtime_seconds
        if period in ("1st", "2nd"):
            return self.half_seconds
        return None

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_payload(cls, payload: Any) -> "SoccerRules":
        if not isinstance(payload, Mapping):
            raise RulesError("Rules must be an object of named values.")
        known = {field.name for field in fields(cls)}
        changes = {key: value for key, value in payload.items() if key in known}
        try:
            return cls(**changes)
        except StateValidationError as exc:  # pragma: no cover - defensive
            raise RulesError(str(exc)) from exc

    def with_changes(self, **changes: Any) -> "SoccerRules":
        return replace(self, **changes)


def default_soccer_rules() -> SoccerRules:
    return SoccerRules()


def soccer_rules_from_mapping(raw: Mapping[str, Any]) -> SoccerRules:
    return SoccerRules.from_payload(raw)


def soccer_rules_to_mapping(rules: SoccerRules) -> dict[str, Any]:
    return rules.to_dict()


def read_soccer_rules(paths: "ScoreboardPaths") -> SoccerRules:
    """The stored soccer timing rules, or the shipped defaults."""

    from scoreboard.infrastructure.config import RULES_SECTION, read_section

    section = read_section(paths, RULES_SECTION)
    if not isinstance(section, dict):
        return default_soccer_rules()
    try:
        return SoccerRules.from_payload(section)
    except RulesError:
        return default_soccer_rules()


def write_soccer_rules(paths: "ScoreboardPaths", rules: SoccerRules) -> bool:
    """Store the soccer timing rules, keeping every other section intact."""

    from scoreboard.infrastructure.config import RULES_SECTION, write_section

    return write_section(paths, RULES_SECTION, rules.to_dict())


__all__ = [
    "CLOCK_DIRECTION_CHOICES",
    "MERCY_APPLIES_CHOICES",
    "SOCCER_RULE_FIELDS",
    "RulesError",
    "SoccerRules",
    "default_soccer_rules",
    "read_soccer_rules",
    "soccer_rules_from_mapping",
    "soccer_rules_to_mapping",
    "write_soccer_rules",
]
