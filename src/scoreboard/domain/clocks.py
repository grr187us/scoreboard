"""Authoritative game-clock logic based on injected monotonic time."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Callable, Final

from scoreboard.domain.state import (
    MAX_GAME_CLOCK_SECONDS,
    MAX_PLAY_CLOCK_SECONDS,
    ClockValue,
    GameState,
    StateValidationError,
)

DEFAULT_QUARTER_LENGTH_SECONDS: Final[float] = MAX_GAME_CLOCK_SECONDS
PLAY_CLOCK_PRESETS: Final[tuple[float, ...]] = (25.0, 40.0)


def _coerce_now(
    now: float | None,
    monotonic_clock: Callable[[], float] | None,
) -> float:
    if now is not None:
        value = float(now)
    elif monotonic_clock is not None:
        value = float(monotonic_clock())
    else:
        value = float(time.monotonic())
    if value != value or value in (float("inf"), float("-inf")):
        raise StateValidationError("monotonic time must be finite")
    return value


def _validate_preset(seconds: float) -> float:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise StateValidationError("play clock preset must be a number")
    numeric = float(seconds)
    if numeric not in PLAY_CLOCK_PRESETS:
        raise StateValidationError(
            f"play clock preset must be one of {PLAY_CLOCK_PRESETS!r}"
        )
    return numeric


def _validate_remaining(value: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateValidationError("remaining seconds must be a number")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise StateValidationError("remaining seconds must be finite")
    if not 0.0 <= numeric <= maximum:
        raise StateValidationError(
            f"remaining seconds must be between 0 and {maximum:g} seconds"
        )
    return numeric


@dataclass(frozen=True, slots=True)
class GameClock:
    """Immutable countdown engine driven by monotonic time."""

    value: ClockValue = ClockValue(MAX_GAME_CLOCK_SECONDS)
    monotonic_clock: Callable[[], float] = field(
        default_factory=lambda: time.monotonic,
        repr=False,
    )
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
        cls,
        state: GameState,
        *,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> "GameClock":
        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
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
                seconds=0.0,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        return ClockValue(
            seconds=remaining,
            running=True,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=self.value.deadline_monotonic,
            started_at_monotonic=self.value.started_at_monotonic,
        )

    def remaining_at(self, now: float | None = None) -> float:
        return self.current_value(now).seconds

    def start(self, *, now: float | None = None) -> "GameClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining,
            running=True,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=current_now + remaining,
            started_at_monotonic=current_now,
        )
        if remaining <= 0.0:
            next_value = ClockValue(
                seconds=0.0,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def stop(self, *, now: float | None = None) -> "GameClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if not self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining,
            running=False,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None,
            started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def reset(self) -> "GameClock":
        return replace(
            self,
            value=ClockValue(
                seconds=self.maximum_seconds,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
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
    ) -> "GameClock":
        if seconds is None and delta is None and target is None:
            raise StateValidationError("provide target seconds or a delta")
        current_now = _coerce_now(now, self.monotonic_clock)
        current_remaining = self.remaining_at(current_now)
        if target is not None:
            new_remaining = _validate_remaining(target, self.maximum_seconds)
        elif delta is not None:
            new_remaining = _validate_remaining(
                current_remaining + float(delta),
                self.maximum_seconds,
            )
        else:
            new_remaining = _validate_remaining(seconds, self.maximum_seconds)

        if self.value.running:
            next_value = ClockValue(
                seconds=new_remaining,
                running=True,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=current_now + new_remaining,
                started_at_monotonic=current_now,
            )
        else:
            next_value = ClockValue(
                seconds=new_remaining,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def expire(self, *, now: float | None = None) -> "GameClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.remaining_at(current_now) <= 0.0:
            if self.value.running:
                return replace(
                    self,
                    value=ClockValue(
                        seconds=0.0,
                        running=False,
                        maximum_seconds=self.maximum_seconds,
                        deadline_monotonic=None,
                        started_at_monotonic=None,
                    ),
                    revision=self.revision + 1,
                )
            return self
        return self.stop(now=current_now)

    def apply_to_state(self, state: GameState) -> GameState:
        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
        return state.evolve(game_clock=self.to_clock_value())

    def to_clock_value(self, *, now: float | None = None) -> ClockValue:
        return self.current_value(now)


@dataclass(frozen=True, slots=True)
class PlayClock:
    """Immutable 25/40-second countdown engine driven by monotonic time.

    ``preset_seconds`` remembers the last loaded preset so ``reset`` can
    restore it; it is engine-only bookkeeping and is not part of the
    persisted ``ClockValue`` contract.
    """

    value: ClockValue = ClockValue(0.0, False, MAX_PLAY_CLOCK_SECONDS)
    preset_seconds: float = 0.0
    monotonic_clock: Callable[[], float] = field(
        default_factory=lambda: time.monotonic,
        repr=False,
    )
    revision: int = 0

    def __post_init__(self) -> None:
        if self.value.maximum_seconds <= 0:
            raise StateValidationError("clock maximum_seconds must be positive")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise StateValidationError("clock revision must be a non-negative integer")
        if not callable(self.monotonic_clock):
            raise StateValidationError("monotonic_clock must be callable")
        object.__setattr__(
            self,
            "preset_seconds",
            _validate_remaining(self.preset_seconds, self.value.maximum_seconds),
        )

    @classmethod
    def from_state(
        cls,
        state: GameState,
        *,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> "PlayClock":
        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
        clock = state.play_clock
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
                seconds=0.0,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        return ClockValue(
            seconds=remaining,
            running=True,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=self.value.deadline_monotonic,
            started_at_monotonic=self.value.started_at_monotonic,
        )

    def remaining_at(self, now: float | None = None) -> float:
        return self.current_value(now).seconds

    def start(self, *, now: float | None = None) -> "PlayClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining,
            running=True,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=current_now + remaining,
            started_at_monotonic=current_now,
        )
        if remaining <= 0.0:
            next_value = ClockValue(
                seconds=0.0,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def stop(self, *, now: float | None = None) -> "PlayClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if not self.value.running:
            return self
        remaining = self.remaining_at(current_now)
        next_value = ClockValue(
            seconds=remaining,
            running=False,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None,
            started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def load_preset(self, seconds: float, *, now: float | None = None) -> "PlayClock":
        """Load a 25/40-second preset while stopped; a separate Start counts down."""

        preset = _validate_preset(seconds)
        _coerce_now(now, self.monotonic_clock)
        next_value = ClockValue(
            seconds=preset,
            running=False,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None,
            started_at_monotonic=None,
        )
        return replace(self, value=next_value, preset_seconds=preset, revision=self.revision + 1)

    def clear(self, *, now: float | None = None) -> "PlayClock":
        """Deliberately stop and blank the play clock (no preset remains loaded)."""

        _coerce_now(now, self.monotonic_clock)
        next_value = ClockValue(
            seconds=0.0,
            running=False,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None,
            started_at_monotonic=None,
        )
        return replace(self, value=next_value, preset_seconds=0.0, revision=self.revision + 1)

    def reset(self) -> "PlayClock":
        """Restore the configured preset (or blank, if none) while stopped."""

        return replace(
            self,
            value=ClockValue(
                seconds=self.preset_seconds,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
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
    ) -> "PlayClock":
        if seconds is None and delta is None and target is None:
            raise StateValidationError("provide target seconds or a delta")
        current_now = _coerce_now(now, self.monotonic_clock)
        current_remaining = self.remaining_at(current_now)
        if target is not None:
            new_remaining = _validate_remaining(target, self.maximum_seconds)
        elif delta is not None:
            new_remaining = _validate_remaining(
                current_remaining + float(delta),
                self.maximum_seconds,
            )
        else:
            new_remaining = _validate_remaining(seconds, self.maximum_seconds)

        if self.value.running:
            next_value = ClockValue(
                seconds=new_remaining,
                running=True,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=current_now + new_remaining,
                started_at_monotonic=current_now,
            )
        else:
            next_value = ClockValue(
                seconds=new_remaining,
                running=False,
                maximum_seconds=self.maximum_seconds,
                deadline_monotonic=None,
                started_at_monotonic=None,
            )
        return replace(self, value=next_value, revision=self.revision + 1)

    def expire(self, *, now: float | None = None) -> "PlayClock":
        current_now = _coerce_now(now, self.monotonic_clock)
        if self.remaining_at(current_now) <= 0.0:
            if self.value.running:
                return replace(
                    self,
                    value=ClockValue(
                        seconds=0.0,
                        running=False,
                        maximum_seconds=self.maximum_seconds,
                        deadline_monotonic=None,
                        started_at_monotonic=None,
                    ),
                    revision=self.revision + 1,
                )
            return self
        return self.stop(now=current_now)

    def apply_to_state(self, state: GameState) -> GameState:
        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
        return state.evolve(play_clock=self.to_clock_value())

    def to_clock_value(self, *, now: float | None = None) -> ClockValue:
        return self.current_value(now)


def clear_play_clock_on_game_clock_start(
    play_clock: "PlayClock",
    *,
    game_clock_was_running: bool,
    now: float | None = None,
) -> "PlayClock":
    """Apply the documented coupling: a stopped-to-running game clock clears the play clock.

    This takes the game clock's prior running state as a plain boolean rather than a
    ``GameClock`` instance, so the play-clock engine never re-implements or reaches into
    game-clock logic. A redundant Start on an already-running game clock has no effect here.
    """

    if not isinstance(play_clock, PlayClock):
        raise TypeError("play_clock must be a PlayClock")
    if game_clock_was_running:
        return play_clock
    return play_clock.clear(now=now)


def start_game_clock(
    clock: GameClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> GameClock | GameState:
    active = clock if clock is not None else GameClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.start(now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def stop_game_clock(
    clock: GameClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> GameClock | GameState:
    active = clock if clock is not None else GameClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.stop(now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def reset_game_clock(
    clock: GameClock | None = None,
    *,
    state: GameState | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> GameClock | GameState:
    active = clock if clock is not None else GameClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.reset()
    if state is not None:
        return result.apply_to_state(state)
    return result


def correct_game_clock(
    clock: GameClock | None = None,
    *,
    state: GameState | None = None,
    seconds: float | None = None,
    delta: float | None = None,
    target: float | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> GameClock | GameState:
    active = clock if clock is not None else GameClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.correct(seconds=seconds, delta=delta, target=target, now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def remaining_game_clock(
    clock: GameClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> float:
    active = clock if clock is not None else GameClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    return active.remaining_at(now)


def start_play_clock(
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> PlayClock | GameState:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.start(now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def stop_play_clock(
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> PlayClock | GameState:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.stop(now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def load_play_clock_preset(
    seconds: float,
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> PlayClock | GameState:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.load_preset(seconds, now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def clear_play_clock(
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> PlayClock | GameState:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.clear(now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def reset_play_clock(
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> PlayClock | GameState:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.reset()
    if state is not None:
        return result.apply_to_state(state)
    return result


def correct_play_clock(
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    seconds: float | None = None,
    delta: float | None = None,
    target: float | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> PlayClock | GameState:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    result = active.correct(seconds=seconds, delta=delta, target=target, now=now)
    if state is not None:
        return result.apply_to_state(state)
    return result


def remaining_play_clock(
    clock: PlayClock | None = None,
    *,
    state: GameState | None = None,
    now: float | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> float:
    active = clock if clock is not None else PlayClock.from_state(state or GameState(), monotonic_clock=monotonic_clock)
    return active.remaining_at(now)


__all__ = [
    "DEFAULT_QUARTER_LENGTH_SECONDS",
    "PLAY_CLOCK_PRESETS",
    "GameClock",
    "PlayClock",
    "clear_play_clock",
    "clear_play_clock_on_game_clock_start",
    "correct_game_clock",
    "correct_play_clock",
    "load_play_clock_preset",
    "remaining_game_clock",
    "remaining_play_clock",
    "reset_game_clock",
    "reset_play_clock",
    "start_game_clock",
    "start_play_clock",
    "stop_game_clock",
    "stop_play_clock",
]
