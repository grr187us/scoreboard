"""Authoritative soccer clock logic based on injected monotonic time.

Mirrors ``scoreboard.domain.clocks`` (``GameClock``, ``StatusCountdown``). A second, parallel
implementation rather than a generalization: football's engines ``isinstance``-check
``GameState`` in ``from_state``/``apply_to_state``, so they cannot run against ``SoccerState``
without either loosening that check or duplicating the ~150-line countdown engine. Duplicating
is the documented decision (``.scratch/soccer-mode/domain_draft.md`` section 0.1) -- zero risk
to football's clock test suite. Soccer has no play clock, so there is no ``SoccerPlayClock``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Callable, Final

from scoreboard.domain.formatting import ceil_seconds
from scoreboard.domain.soccer.state import (
    MAX_STATUS_CLOCK_SECONDS,
    ClockValue,
    SoccerState,
    StateValidationError,
)

#: Soccer only ever loads WEATHER's configured seconds (``SoccerRules.weather_seconds``), so
#: this tuple is not consulted by the service; kept for symmetry with football's module.
STATUS_CLOCK_PRESETS: Final[tuple[float, ...]] = (300.0, 600.0, 1800.0)

#: The displayed second at which the halftime countdown's label turns from HALFTIME to WARMUP.
WARMUP_THRESHOLD_SECONDS: Final[float] = 3 * 60.0


def event_phase_for(
    phase: str, seconds: float, *, warmup_threshold: float = WARMUP_THRESHOLD_SECONDS
) -> str:
    """The phase label an interval countdown shows at ``seconds`` remaining."""

    if phase == "PREGAME":
        return "PREGAME"
    if warmup_threshold <= 0.0:
        return "HALFTIME"
    return "WARMUP" if ceil_seconds(seconds) <= warmup_threshold else "HALFTIME"


def _coerce_now(now: float | None, monotonic_clock: Callable[[], float] | None) -> float:
    if now is not None:
        value = float(now)
    elif monotonic_clock is not None:
        value = float(monotonic_clock())
    else:
        value = float(time.monotonic())
    if value != value or value in (float("inf"), float("-inf")):
        raise StateValidationError("monotonic time must be finite")
    return value


def _validate_status_preset(seconds: float) -> float:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise StateValidationError("status clock preset must be a number")
    numeric = float(seconds)
    if numeric != numeric or numeric != int(numeric):
        raise StateValidationError("status clock preset must be whole seconds")
    if not 1.0 <= numeric <= MAX_STATUS_CLOCK_SECONDS:
        raise StateValidationError(
            f"status clock preset must be between 1 and {MAX_STATUS_CLOCK_SECONDS:g} seconds"
        )
    return numeric


def _validate_remaining(value: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateValidationError("remaining seconds must be a number")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise StateValidationError("remaining seconds must be finite")
    if not 0.0 <= numeric <= maximum:
        raise StateValidationError(f"remaining seconds must be between 0 and {maximum:g} seconds")
    return numeric


@dataclass(frozen=True, slots=True)
class SoccerGameClock:
    """Immutable countdown engine driven by monotonic time, retyped to ``SoccerState``."""

    value: ClockValue = ClockValue(2400.0, False, 2400.0)
    monotonic_clock: Callable[[], float] = field(default_factory=lambda: time.monotonic, repr=False)
    revision: int = 0

    def __post_init__(self) -> None:
        if self.value.maximum_seconds <= 0:
            raise StateValidationError("clock maximum_seconds must be positive")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise StateValidationError("clock revision must be a non-negative integer")
        if not callable(self.monotonic_clock):
            raise StateValidationError("monotonic_clock must be callable")

    @classmethod
    def from_state(
        cls, state: SoccerState, *, monotonic_clock: Callable[[], float] | None = None
    ) -> "SoccerGameClock":
        if not isinstance(state, SoccerState):
            raise TypeError("state must be a SoccerState")
        clock = state.game_clock
        return cls(
            value=ClockValue(
                seconds=clock.seconds,
                running=clock.running,
                maximum_seconds=clock.maximum_seconds,
                deadline_monotonic=clock.deadline_monotonic,
                started_at_monotonic=clock.started_at_monotonic,
            ),
            monotonic_clock=(time.monotonic if monotonic_clock is None else monotonic_clock),
        )

    @property
    def seconds(self) -> float:
        return self.remaining_at()

    @property
    def running(self) -> bool:
        return self.value.running

    @property
    def maximum_seconds(self) -> float:
        return self.value.maximum_seconds

    @property
    def expired(self) -> bool:
        return self.remaining_at() <= 0.0

    def current_value(self, now: float | None = None) -> ClockValue:
        current_now = _coerce_now(now, self.monotonic_clock)
        if not self.value.running or self.value.deadline_monotonic is None:
            return ClockValue(
                seconds=max(0.0, min(self.maximum_seconds, float(self.value.seconds))),
                running=False if self.value.seconds <= 0.0 else self.value.running,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        remaining = max(0.0, min(self.maximum_seconds, self.value.deadline_monotonic - current_now))
        if remaining <= 0.0:
            return ClockValue(
                seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None, started_at_monotonic=None,
            )
        return ClockValue(
            seconds=remaining, running=True, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=self.value.deadline_monotonic,
            started_at_monotonic=self.value.started_at_monotonic,
        )

    def remaining_at(self, now: float | None = None) -> float:
        return self.current_value(now).seconds

    def start(self, *, now: float | None = None) -> "SoccerGameClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining, running=True, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=current_now + remaining, started_at_monotonic=current_now,
        )
        if remaining <= 0.0:
            next_value = ClockValue(
                seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None, started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def stop(self, *, now: float | None = None) -> "SoccerGameClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if not self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining, running=False, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None, started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def reset(self) -> "SoccerGameClock":
        return replace(
            self,
            value=ClockValue(
                seconds=self.maximum_seconds, running=False, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None, started_at_monotonic=None,
            ),
            revision=self.revision + 1,
        )

    def correct(
        self,
        seconds: float | None = None,
        *,
        delta: float | None = None,
        target: float | None = None,
        now: float | None = None,
    ) -> "SoccerGameClock":
        if seconds is None and delta is None and target is None:
            raise StateValidationError("provide target seconds or a delta")
        current_now = _coerce_now(now, self.monotonic_clock)
        current_remaining = self.remaining_at(current_now)
        if target is not None:
            new_remaining = _validate_remaining(target, self.maximum_seconds)
        elif delta is not None:
            new_remaining = _validate_remaining(current_remaining + float(delta), self.maximum_seconds)
        else:
            new_remaining = _validate_remaining(seconds, self.maximum_seconds)

        if self.value.running:
            next_value = ClockValue(
                seconds=new_remaining, running=True, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=current_now + new_remaining, started_at_monotonic=current_now,
            )
        else:
            next_value = ClockValue(
                seconds=new_remaining, running=False, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None, started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def expire(self, *, now: float | None = None) -> "SoccerGameClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.remaining_at(current_now) <= 0.0:
            if self.value.running:
                return replace(
                    self,
                    value=ClockValue(
                        seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
                        deadline_monotonic=None, started_at_monotonic=None,
                    ),
                    revision=self.revision + 1,
                )
            return self
        return self.stop(now=current_now)

    def apply_to_state(self, state: SoccerState) -> SoccerState:
        if not isinstance(state, SoccerState):
            raise TypeError("state must be a SoccerState")
        return state.evolve(game_clock=self.to_clock_value())

    def to_clock_value(self, *, now: float | None = None) -> ClockValue:
        return self.current_value(now)


@dataclass(frozen=True, slots=True)
class SoccerStatusCountdown:
    """Immutable stoppage-timer engine for the crowd status countdown (WEATHER)."""

    value: ClockValue = ClockValue(0.0, False, MAX_STATUS_CLOCK_SECONDS)
    monotonic_clock: Callable[[], float] = field(default_factory=lambda: time.monotonic, repr=False)
    revision: int = 0

    def __post_init__(self) -> None:
        if self.value.maximum_seconds <= 0:
            raise StateValidationError("clock maximum_seconds must be positive")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise StateValidationError("clock revision must be a non-negative integer")
        if not callable(self.monotonic_clock):
            raise StateValidationError("monotonic_clock must be callable")

    @classmethod
    def from_state(
        cls, state: SoccerState, *, monotonic_clock: Callable[[], float] | None = None
    ) -> "SoccerStatusCountdown":
        if not isinstance(state, SoccerState):
            raise TypeError("state must be a SoccerState")
        clock = state.status_clock
        return cls(
            value=ClockValue(
                seconds=clock.seconds,
                running=clock.running,
                maximum_seconds=clock.maximum_seconds,
                deadline_monotonic=clock.deadline_monotonic,
                started_at_monotonic=clock.started_at_monotonic,
            ),
            monotonic_clock=(time.monotonic if monotonic_clock is None else monotonic_clock),
        )

    @property
    def seconds(self) -> float:
        return self.remaining_at()

    @property
    def running(self) -> bool:
        return self.value.running

    @property
    def maximum_seconds(self) -> float:
        return self.value.maximum_seconds

    @property
    def expired(self) -> bool:
        return self.remaining_at() <= 0.0

    def current_value(self, now: float | None = None) -> ClockValue:
        current_now = _coerce_now(now, self.monotonic_clock)
        if not self.value.running or self.value.deadline_monotonic is None:
            return ClockValue(
                seconds=max(0.0, min(self.maximum_seconds, float(self.value.seconds))),
                running=False if self.value.seconds <= 0.0 else self.value.running,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        remaining = max(0.0, min(self.maximum_seconds, self.value.deadline_monotonic - current_now))
        if remaining <= 0.0:
            return ClockValue(
                seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None, started_at_monotonic=None,
            )
        return ClockValue(
            seconds=remaining, running=True, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=self.value.deadline_monotonic,
            started_at_monotonic=self.value.started_at_monotonic,
        )

    def remaining_at(self, now: float | None = None) -> float:
        return self.current_value(now).seconds

    def start(self, *, now: float | None = None) -> "SoccerStatusCountdown":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining, running=True, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=current_now + remaining, started_at_monotonic=current_now,
        )
        if remaining <= 0.0:
            next_value = ClockValue(
                seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None, started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def stop(self, *, now: float | None = None) -> "SoccerStatusCountdown":
        current_now = _coerce_now(now, self.monotonic_clock)
        if not self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining, running=False, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None, started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def load_preset(self, seconds: float, *, now: float | None = None) -> "SoccerStatusCountdown":
        preset = _validate_status_preset(seconds)
        _coerce_now(now, self.monotonic_clock)
        next_value = ClockValue(
            seconds=preset, running=False, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None, started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def clear(self, *, now: float | None = None) -> "SoccerStatusCountdown":
        _coerce_now(now, self.monotonic_clock)
        next_value = ClockValue(
            seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None, started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def expire(self, *, now: float | None = None) -> "SoccerStatusCountdown":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.remaining_at(current_now) <= 0.0:
            if self.value.running:
                return replace(
                    self,
                    value=ClockValue(
                        seconds=0.0, running=False, maximum_seconds=self.maximum_seconds,
                        deadline_monotonic=None, started_at_monotonic=None,
                    ),
                    revision=self.revision + 1,
                )
            return self
        return self.stop(now=current_now)

    def apply_to_state(self, state: SoccerState) -> SoccerState:
        if not isinstance(state, SoccerState):
            raise TypeError("state must be a SoccerState")
        return state.evolve(status_clock=self.to_clock_value())

    def to_clock_value(self, *, now: float | None = None) -> ClockValue:
        return self.current_value(now)


__all__ = [
    "STATUS_CLOCK_PRESETS",
    "WARMUP_THRESHOLD_SECONDS",
    "SoccerGameClock",
    "SoccerStatusCountdown",
    "event_phase_for",
]
