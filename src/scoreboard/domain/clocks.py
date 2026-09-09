"""Authoritative game-clock logic based on injected monotonic time."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Callable, Final

from scoreboard.domain.formatting import ceil_seconds
from scoreboard.domain.state import (
    MAX_GAME_CLOCK_SECONDS,
    MAX_PLAY_CLOCK_SECONDS,
    MAX_STATUS_CLOCK_SECONDS,
    ClockValue,
    GameState,
    StateValidationError,
)

DEFAULT_QUARTER_LENGTH_SECONDS: Final[float] = MAX_GAME_CLOCK_SECONDS
PLAY_CLOCK_PRESETS: Final[tuple[float, ...]] = (25.0, 40.0)

#: F3's crowd-facing status countdown offers a short, medium, and long
#: stoppage timer -- 30 seconds for a quick administrative pause, 60 for a
#: standard timeout (the ``TIMEOUT`` crowd button's one-press preset), and 90
#: for a longer injury/delay stoppage. Deliberately not the play clock's own
#: 25/40 presets: this is a different, independent clock (see StatusCountdown
#: below and .scratch/f3-i4/DESIGN.md).
STATUS_CLOCK_PRESETS: Final[tuple[float, ...]] = (30.0, 60.0, 90.0)

#: The displayed second at which the halftime countdown's label turns from
#: ``HALFTIME`` to ``WARMUP`` (F-026). A default since September 9, 2026:
#: ``GameRules.warmup_seconds`` is what a running game uses.
WARMUP_THRESHOLD_SECONDS: Final[float] = 3 * 60.0


def event_phase_for(
    phase: str, seconds: float, *, warmup_threshold: float = WARMUP_THRESHOLD_SECONDS
) -> str:
    """The phase label an interval countdown shows at ``seconds`` remaining.

    Pure and derived, so the label flips from ``HALFTIME`` to ``WARMUP`` at
    the threshold while the countdown runs, without an operator command and
    without a new state revision. It reads the *displayed* second, so the
    change lands exactly between a shown ``3:01`` and a shown ``3:00`` for the
    shipped 3:00 threshold (F-026). A threshold of ``0`` never shows WARMUP.

    ``PREGAME`` is returned unchanged: the pregame countdown has one phase.
    Since September 9, 2026 the countdown in question is the game clock
    itself while the quarter is ``PRE`` or ``HALF``; there is no separate
    interval engine any more.
    """

    if phase == "PREGAME":
        return "PREGAME"
    if warmup_threshold <= 0.0:
        return "HALFTIME"
    return "WARMUP" if ceil_seconds(seconds) <= warmup_threshold else "HALFTIME"


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


def _validate_status_preset(seconds: float) -> float:
    """A sibling of :func:`_validate_preset` for the status clock.

    Kept separate rather than widening the play clock's validator: the two
    clocks' accepted values are unrelated facts that happen to both be
    "seconds," and a future change to one set must never silently affect the
    other. Since September 9, 2026 the crowd TIMEOUT button loads the
    operator's configured timeout length (``GameRules.timeout_seconds``), so
    this accepts any whole number of seconds the clock can hold rather than
    only the three shipped presets, which remain the suggested values.
    """

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


@dataclass(frozen=True, slots=True)
class StatusCountdown:
    """Immutable stoppage-timer engine for F3's crowd-facing status countdown.

    Modelled directly on :class:`PlayClock`: the same frozen dataclass, the
    same monotonic-deadline math, the same ``revision`` bookkeeping. It is
    deliberately independent of the game and play clocks -- no method here
    reads or returns either -- and it deliberately has no ``correct`` and no
    ``reset``: the operator reloads a preset instead of editing this one's
    current time or restoring a remembered value (.scratch/f3-i4/DESIGN.md).
    """

    value: ClockValue = ClockValue(0.0, False, MAX_STATUS_CLOCK_SECONDS)
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
    ) -> "StatusCountdown":
        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
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

    def start(self, *, now: float | None = None) -> "StatusCountdown":
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

    def stop(self, *, now: float | None = None) -> "StatusCountdown":
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

    def load_preset(self, seconds: float, *, now: float | None = None) -> "StatusCountdown":
        """Load a 30/60/90-second preset while stopped; a separate Start counts down."""

        preset = _validate_status_preset(seconds)
        _coerce_now(now, self.monotonic_clock)
        next_value = ClockValue(
            seconds=preset,
            running=False,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None,
            started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def clear(self, *, now: float | None = None) -> "StatusCountdown":
        """Deliberately stop and blank the countdown (no preset remains loaded)."""

        _coerce_now(now, self.monotonic_clock)
        next_value = ClockValue(
            seconds=0.0,
            running=False,
            maximum_seconds=self.maximum_seconds,
            deadline_monotonic=None,
            started_at_monotonic=None,
        )
        return replace(self, value=next_value, revision=self.revision + 1)

    def expire(self, *, now: float | None = None) -> "StatusCountdown":
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
        return state.evolve(status_clock=self.to_clock_value())

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


def clear_play_clock_on_game_clock_stop(
    play_clock: "PlayClock",
    *,
    game_clock_is_running: bool,
    now: float | None = None,
) -> "PlayClock":
    """Clear a running play clock after the game clock has stopped.

    The caller owns transition detection: a STOP issued while the game clock
    was already stopped must not clear an otherwise independent play clock.
    Keeping this helper to plain state facts means ``PlayClock`` never reaches
    into ``GameClock`` internals.
    """

    if not isinstance(play_clock, PlayClock):
        raise TypeError("play_clock must be a PlayClock")
    if game_clock_is_running or not play_clock.current_value(now).running:
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
    "STATUS_CLOCK_PRESETS",
    "WARMUP_THRESHOLD_SECONDS",
    "GameClock",
    "PlayClock",
    "StatusCountdown",
    "clear_play_clock",
    "clear_play_clock_on_game_clock_start",
    "clear_play_clock_on_game_clock_stop",
    "event_phase_for",
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
