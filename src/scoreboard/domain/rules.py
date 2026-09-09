"""The game's timing rules: period lengths, interval countdowns, timeouts.

Added September 9, 2026. Before this, every length was a module constant --
12:00 quarters, a 30:00 kickoff countdown, a 15:00 halftime with its warmup
label at 3:00, a 1:00 charged timeout, three timeouts a half -- and the
operator had no way to change any of them short of editing Python. Leagues
differ (youth quarters run 8 or 10 minutes; a JV halftime is 10), so these
are now one validated value object the operator edits from the Setup drawer.

Rules are *not* game state. They advance no revision and are not part of a
snapshot: they live in ``config.json`` with the other laptop preferences
(``infrastructure.config``), and the service consults them at the moments a
length is loaded -- New Game, a quarter change, the crowd TIMEOUT button --
never retroactively. Changing the quarter length in the middle of the 2nd
quarter does nothing to the clock that is already running; it applies when
the 3rd is loaded.

Everything is whole seconds. ``from_payload`` is the airlock for values that
came from the operator page or from disk: it rejects rather than repairs,
because a rule the operator did not ask for is worse than a message.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Final, Mapping

from scoreboard.domain.state import (
    MAX_GAME_CLOCK_MAXIMUM_SECONDS,
    MAX_STATUS_CLOCK_SECONDS,
    MAX_TIMEOUTS,
    MAX_TIMEOUTS_CAP,
    MAX_GAME_CLOCK_SECONDS,
    MAX_PREGAME_CLOCK_SECONDS,
    StateValidationError,
)

#: The shipped halftime length and the displayed second at which its label
#: turns from HALFTIME to WARMUP (F-026). Both are now defaults, not limits.
DEFAULT_HALFTIME_SECONDS: Final[float] = 15 * 60.0
DEFAULT_WARMUP_SECONDS: Final[float] = 3 * 60.0
#: The crowd TIMEOUT button's one-press countdown (F3).
DEFAULT_TIMEOUT_SECONDS: Final[float] = 60.0

#: Every rule the Setup drawer edits, in the order it shows them, with the
#: plain-language label Python owns (the page copies it, never composes it).
RULE_FIELDS: Final[tuple[tuple[str, str, str], ...]] = (
    ("quarter_seconds", "Quarter length", "clock"),
    ("overtime_seconds", "Overtime length", "clock"),
    ("pregame_seconds", "Pregame countdown", "clock"),
    ("halftime_seconds", "Halftime countdown", "clock"),
    ("warmup_seconds", "Warmup label at", "clock"),
    ("timeout_seconds", "Timeout countdown", "seconds"),
    ("timeouts_per_half", "Timeouts per half", "count"),
)


class RulesError(ValueError):
    """A rule value the operator asked for is outside what the board can run."""


def _whole_seconds(value: Any, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RulesError(f"{label} must be a number of seconds.")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise RulesError(f"{label} must be a finite number of seconds.")
    if numeric != int(numeric):
        raise RulesError(f"{label} must be whole seconds.")
    if not minimum <= numeric <= maximum:
        raise RulesError(
            f"{label} must be between {_clock(minimum)} and {_clock(maximum)}."
        )
    return numeric


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


@dataclass(frozen=True, slots=True)
class GameRules:
    """Every configurable length, in whole seconds, plus timeouts per half."""

    quarter_seconds: float = MAX_GAME_CLOCK_SECONDS
    overtime_seconds: float = MAX_GAME_CLOCK_SECONDS
    pregame_seconds: float = MAX_PREGAME_CLOCK_SECONDS
    halftime_seconds: float = DEFAULT_HALFTIME_SECONDS
    warmup_seconds: float = DEFAULT_WARMUP_SECONDS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    timeouts_per_half: int = MAX_TIMEOUTS

    def __post_init__(self) -> None:
        for name, label in (
            ("quarter_seconds", "Quarter length"),
            ("overtime_seconds", "Overtime length"),
            ("pregame_seconds", "Pregame countdown"),
            ("halftime_seconds", "Halftime countdown"),
        ):
            object.__setattr__(
                self, name,
                _whole_seconds(getattr(self, name), label, minimum=60.0,
                               maximum=MAX_GAME_CLOCK_MAXIMUM_SECONDS),
            )
        # 0 turns the WARMUP label off; it can never be the whole halftime,
        # or HALFTIME would never be shown at all.
        object.__setattr__(
            self, "warmup_seconds",
            _whole_seconds(self.warmup_seconds, "Warmup label", minimum=0.0,
                           maximum=self.halftime_seconds - 1.0),
        )
        object.__setattr__(
            self, "timeout_seconds",
            _whole_seconds(self.timeout_seconds, "Timeout countdown", minimum=1.0,
                           maximum=MAX_STATUS_CLOCK_SECONDS),
        )
        count = self.timeouts_per_half
        if isinstance(count, bool) or not isinstance(count, int):
            if isinstance(count, float) and count == int(count):
                count = int(count)
            else:
                raise RulesError("Timeouts per half must be a whole number.")
        if not 1 <= count <= MAX_TIMEOUTS_CAP:
            raise RulesError(f"Timeouts per half must be between 1 and {MAX_TIMEOUTS_CAP}.")
        object.__setattr__(self, "timeouts_per_half", count)

    # --- What a quarter loads -------------------------------------------

    def period_seconds(self, quarter: str) -> float | None:
        """The stopped length the game clock loads on entering ``quarter``.

        ``PRE`` and ``HALF`` are the two interval countdowns; the four
        regulation quarters and overtime are playing periods; ``FINAL`` has
        no playable time, so it is ``None``.
        """

        if quarter == "PRE":
            return self.pregame_seconds
        if quarter == "HALF":
            return self.halftime_seconds
        if quarter == "OT":
            return self.overtime_seconds
        if quarter in ("1st", "2nd", "3rd", "4th"):
            return self.quarter_seconds
        return None

    # --- JSON boundary ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_payload(cls, payload: Any) -> "GameRules":
        """Build rules from an operator page's or ``config.json``'s object.

        Unknown keys are ignored (an older build may not know a newer rule);
        a missing key keeps the shipped default; a present-but-wrong value
        raises :class:`RulesError` with the sentence the operator should see.
        """

        if not isinstance(payload, Mapping):
            raise RulesError("Rules must be an object of named values.")
        known = {field.name for field in fields(cls)}
        changes = {key: value for key, value in payload.items() if key in known}
        try:
            return cls(**changes)
        except StateValidationError as exc:  # pragma: no cover - defensive
            raise RulesError(str(exc)) from exc

    def with_changes(self, **changes: Any) -> "GameRules":
        return replace(self, **changes)


def default_rules() -> GameRules:
    return GameRules()


__all__ = [
    "DEFAULT_HALFTIME_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_WARMUP_SECONDS",
    "RULE_FIELDS",
    "GameRules",
    "RulesError",
    "default_rules",
]
