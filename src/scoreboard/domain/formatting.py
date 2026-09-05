"""Pure display formatting for authoritative clock values (F-039, F-047).

This module is a *derived view* of stored time. It never rounds, mutates, or
writes back a stored value: callers format a materialized number of seconds and
display the result. Persistence uses the same functions so a checkpoint cadence
and an operator readout can never disagree about what "one displayed second"
means (P-003, P-004).

Every visible value rounds **upward**, so the board never understates the time
remaining (roadmap decision, September 4, 2026):

* Game clock: whole seconds while the rounded-tenths value is at least 60.0,
  then tenths. ``60.0`` and ``59.99`` both display ``1:00``; ``59.9`` displays
  ``59.9``; ``12:25.1`` displays ``12:26`` (F-039).
* Play clock: whole seconds until the rounded-tenths value is below 5.0, then
  tenths. ``5.0`` and ``4.99`` both display ``5``; ``4.9`` displays ``4.9``;
  ``4.01`` displays ``4.1`` (F-047).
* Event countdowns display ``M:SS`` whole seconds rounded up at every value
  (F-025, F-026).

All rounding runs through :func:`ceil_tenths`, which folds away binary
floating-point noise before rounding up. Without that guard ``4.9 * 10`` is
``49.000000000000007`` and would round up to a wrong ``5``.
"""

from __future__ import annotations

import math
from typing import Final

#: Tenths at or above which the game clock shows whole seconds (F-039).
GAME_CLOCK_TENTHS_THRESHOLD: Final[int] = 600

#: Tenths at or above which the play clock shows whole seconds (F-047).
PLAY_CLOCK_TENTHS_THRESHOLD: Final[int] = 50

#: Decimal places kept before rounding up. Ten significant sub-second digits are
#: far finer than any clock the operator can observe, and coarse enough to
#: absorb float representation error from monotonic arithmetic.
_FLOAT_GUARD_DIGITS: Final[int] = 6

#: Shown when a clock carries no value at all (a cleared play clock).
BLANK_DISPLAY: Final[str] = ""


class FormattingError(ValueError):
    """Raised when a value cannot be a number of seconds on a display."""


def _require_seconds(seconds: float) -> float:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise FormattingError("seconds must be a number")
    value = float(seconds)
    if value != value or value in (float("inf"), float("-inf")):
        raise FormattingError("seconds must be finite")
    if value < 0.0:
        raise FormattingError("seconds must not be negative")
    return value


def ceil_tenths(seconds: float) -> int:
    """Return the number of whole tenths at or above ``seconds``.

    This is the one rounding primitive in the module. It rounds the tenths
    count to :data:`_FLOAT_GUARD_DIGITS` first so representation error cannot
    push an exact tenth across a boundary.
    """

    return math.ceil(round(_require_seconds(seconds) * 10.0, _FLOAT_GUARD_DIGITS))


def ceil_seconds(seconds: float) -> int:
    """Return the whole displayed second at or above ``seconds``.

    Derived from :func:`ceil_tenths` so a value that already rounded up to a
    tenth boundary cannot round up a second time.
    """

    tenths = ceil_tenths(seconds)
    return -(-tenths // 10)


def displayed_second(seconds: float) -> int:
    """The checkpoint cadence key for P-003.

    Persistence writes a new clock checkpoint whenever this value changes, which
    guarantees a checkpoint at least once per displayed second while a clock
    runs, without writing ten times a second during a tenths readout.
    """

    return ceil_seconds(seconds)


def _tenths_display(tenths: int) -> str:
    return f"{tenths // 10}.{tenths % 10}"


def _minutes_display(total_seconds: int) -> str:
    minutes, remainder = divmod(total_seconds, 60)
    return f"{minutes}:{remainder:02d}"


def format_game_clock(seconds: float) -> str:
    """Format the game clock: ``M:SS`` above a minute, then ``S.T`` (F-039)."""

    tenths = ceil_tenths(seconds)
    if tenths >= GAME_CLOCK_TENTHS_THRESHOLD:
        return _minutes_display(-(-tenths // 10))
    return _tenths_display(tenths)


def format_play_clock(seconds: float, *, blank_at_zero: bool = False) -> str:
    """Format the play clock: whole seconds, then ``S.T`` below 5.0 (F-047).

    ``blank_at_zero`` renders a cleared play clock as an empty area rather than
    ``0``; an *expired* play clock stays visible at ``0.0`` and must not use it
    (F-045, F-050).
    """

    tenths = ceil_tenths(seconds)
    if blank_at_zero and tenths == 0:
        return BLANK_DISPLAY
    if tenths >= PLAY_CLOCK_TENTHS_THRESHOLD:
        return str(-(-tenths // 10))
    return _tenths_display(tenths)


def format_event_countdown(seconds: float) -> str:
    """Format a pregame or interval countdown as rounded-up ``M:SS``."""

    return _minutes_display(ceil_seconds(seconds))


__all__ = [
    "BLANK_DISPLAY",
    "GAME_CLOCK_TENTHS_THRESHOLD",
    "PLAY_CLOCK_TENTHS_THRESHOLD",
    "FormattingError",
    "ceil_seconds",
    "ceil_tenths",
    "displayed_second",
    "format_event_countdown",
    "format_game_clock",
    "format_play_clock",
]
