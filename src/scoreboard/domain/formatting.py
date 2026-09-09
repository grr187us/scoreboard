"""Pure display formatting for authoritative clock and football-state values.

This module is a *derived view* of stored values (F-039, F-047). It never
rounds, mutates, or writes back a stored value: callers format an already
materialized value and display the result. Persistence uses the same clock
functions so a checkpoint cadence and an operator readout can never disagree
about what "one displayed second" means (P-003, P-004). The down/distance and
field-position helpers below are the same kind of derived view for the
expanded football state: Python renders the human-readable text once, so the
operator readout and the spectator board can never disagree about it either.

Every visible value rounds **upward**, so the board never understates the time
remaining (roadmap decision, September 4, 2026; whole-seconds-only revision,
September 7, 2026):

* Game clock: whole seconds always, shown as ``M:SS`` even below a minute
  (``0:30``, not ``30``). ``60.0``, ``59.99``, and ``59.9`` all display
  ``1:00`` (any fractional remainder rounds up to the next whole second, so
  the board never shows a number lower than what truly remains); ``59.0``
  displays ``0:59``; ``12:25.1`` displays ``12:26`` (F-039).
* Play clock: whole seconds always, same rounding. ``5.0``, ``4.99``, and
  ``4.9`` all display ``5``; ``4.0`` displays ``4`` (F-047).
* Event countdowns display ``M:SS`` whole seconds rounded up at every value
  (F-025, F-026).

Football clocks read in whole seconds; tenths are a basketball convention and
are no longer shown at any precision on either clock.

All rounding runs through :func:`ceil_tenths`, which folds away binary
floating-point noise before rounding up. Without that guard ``4.9 * 10`` is
``49.000000000000007`` and would round up to a wrong ``5``.
"""

from __future__ import annotations

import math
from typing import Final

from scoreboard.domain.state import MAX_TIMEOUTS

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


def _minutes_display(total_seconds: int) -> str:
    minutes, remainder = divmod(total_seconds, 60)
    return f"{minutes}:{remainder:02d}"


def format_game_clock(seconds: float) -> str:
    """Format the game clock as rounded-up whole-second ``M:SS`` (F-039).

    Football clocks read in whole seconds only; tenths are a basketball
    convention this board does not use.
    """

    return _minutes_display(ceil_seconds(seconds))


def format_play_clock(seconds: float, *, blank_at_zero: bool = False) -> str:
    """Format the play clock as rounded-up whole seconds (F-047).

    ``blank_at_zero`` renders a cleared play clock as an empty area rather than
    ``0``; an *expired* play clock stays visible at ``0`` and must not use it
    (F-045, F-050).
    """

    whole_seconds = ceil_seconds(seconds)
    if blank_at_zero and whole_seconds == 0:
        return BLANK_DISPLAY
    return str(whole_seconds)


def format_event_countdown(seconds: float) -> str:
    """Format a pregame or interval countdown as rounded-up ``M:SS``."""

    return _minutes_display(ceil_seconds(seconds))


def format_game_status(label: str | None) -> str:
    """The crowd-facing status word (F3), or blank when nothing is raised.

    The wall shows the word only -- never a team name, see
    .scratch/f3-i4/DESIGN.md -- so this is a pass-through, not a composition;
    it never raises for an in-range label, matching every other formatter in
    this module.
    """

    return BLANK_DISPLAY if label is None else label


def format_status_clock(seconds: float, *, blank_at_zero: bool) -> str:
    """Format F3's status countdown as rounded-up ``M:SS``.

    Rounds the same way :func:`format_game_clock` does -- through
    :func:`ceil_tenths` -- so a running countdown never displays a value the
    operator has not reached yet. ``blank_at_zero`` renders a cleared
    countdown as an empty area; a countdown that expired naturally stays
    visible at ``0:00`` (the wall keeps showing the message and the clock
    together until the operator clears them, see the design's deliberate
    limits) and must not pass this as ``True``.
    """

    if blank_at_zero and ceil_tenths(seconds) == 0:
        return BLANK_DISPLAY
    return _minutes_display(ceil_seconds(seconds))


#: Ordinal words for downs 1-4. There is no NFHS-style "5th down" to format.
_DOWN_ORDINALS: Final[dict[int, str]] = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

#: Shown for ``distance == 0``: the line to gain is the goal line itself, so a
#: literal "& 0" would read as a typo rather than a goal-to-go situation.
GOAL_TO_GO_DISPLAY: Final[str] = "Goal"


def format_down_and_distance(down: int | None, distance: int | None) -> str:
    """Format e.g. ``"3rd & 7"`` or ``"4th & Goal"``; blank when not set.

    Either value being ``None`` (not yet set, or deliberately cleared by the
    operator) blanks the whole display rather than showing a partial reading
    like ``"3rd & —"``: a half-known down-and-distance is not a situation an
    operator asked to display.
    """

    if down is None or distance is None:
        return BLANK_DISPLAY
    ordinal = _DOWN_ORDINALS.get(down)
    if ordinal is None:
        raise FormattingError(f"down must be 1-4, got {down!r}")
    if distance < 0:
        raise FormattingError("distance must not be negative")
    to_go = GOAL_TO_GO_DISPLAY if distance == 0 else str(distance)
    return f"{ordinal} & {to_go}"


#: Presentation-layout widgets (spec section 4.5) show down, distance,
#: possession, and timeouts each in their own box rather than combined into a
#: single string, so each needs its own tolerant, never-raising formatter. The
#: authoritative operator readout keeps using :func:`format_down_and_distance`
#: unchanged; these are additional views of the same stored values, not a
#: replacement for it.


def format_down(down: int | None) -> str:
    """``"1st"``/``"2nd"``/``"3rd"``/``"4th"``, or blank when not set."""

    if down is None:
        return BLANK_DISPLAY
    return _DOWN_ORDINALS.get(down, BLANK_DISPLAY)


def format_distance(distance: int | None) -> str:
    """``"& 7"``, ``"& Goal"`` (distance ``0``), or blank when not set.

    The ampersand lives with the distance so an adjacent ``down`` and
    ``distance`` widget pair reads "3rd & 7" exactly as the combined line does
    today.
    """

    if distance is None or distance < 0:
        return BLANK_DISPLAY
    to_go = GOAL_TO_GO_DISPLAY if distance == 0 else str(distance)
    return f"& {to_go}"


def format_possession(possession: str | None) -> str:
    """``"◀ BALL"`` for home, ``"BALL ▶"`` for away, blank for neither."""

    if possession == "home":
        return "◀ BALL"
    if possession == "away":
        return "BALL ▶"
    return BLANK_DISPLAY


def format_distance_value(distance: int | None) -> str:
    """Standalone yards to go, without the combined readout's ampersand."""
    if distance is None or distance < 0:
        return BLANK_DISPLAY
    return GOAL_TO_GO_DISPLAY if distance == 0 else str(distance)


def format_timeout_dots(remaining: int | None, *, total: int = MAX_TIMEOUTS) -> str:
    """One filled/hollow circle per allowed timeout; unknown is not zero.

    ``total`` is the league's timeouts per half (``GameRules``); the shipped
    three when the caller has no rules in hand.
    """
    if isinstance(remaining, bool) or not isinstance(remaining, int) or not 0 <= remaining <= total:
        return BLANK_DISPLAY
    return " ".join("●" if index < remaining else "○" for index in range(total))


def format_timeouts(remaining: int | None) -> str:
    """``"TO 3"``, or blank when unknown. Never invents a maximum."""

    if remaining is None or isinstance(remaining, bool) or not isinstance(remaining, int):
        return BLANK_DISPLAY
    if remaining < 0:
        return BLANK_DISPLAY
    return f"TO {remaining}"


def format_ball_on(team: str, yard_line: int, team_name: str) -> str:
    """Format field position as e.g. ``"TIGERS 35"``, or ``"50"`` at midfield.

    ``yard_line`` is counted from ``team``'s own goal line (see
    :class:`~scoreboard.domain.state.BallSpot`). Midfield is the same physical
    point regardless of which team's side it is counted from, so the team name
    is dropped there rather than printed with an arbitrary side attached.
    """

    if team not in ("home", "away"):
        raise FormattingError(f"team must be 'home' or 'away', got {team!r}")
    if not 0 <= yard_line <= 50:
        raise FormattingError("yard_line must be between 0 and 50")
    if yard_line == 50:
        return "50"
    return f"{team_name} {yard_line}"


__all__ = [
    "BLANK_DISPLAY",
    "GOAL_TO_GO_DISPLAY",
    "FormattingError",
    "ceil_seconds",
    "ceil_tenths",
    "displayed_second",
    "format_ball_on",
    "format_distance",
    "format_distance_value",
    "format_down",
    "format_down_and_distance",
    "format_event_countdown",
    "format_game_clock",
    "format_game_status",
    "format_play_clock",
    "format_possession",
    "format_status_clock",
    "format_timeouts",
    "format_timeout_dots",
]
