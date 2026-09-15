"""Pure display formatting for soccer clock and match values (spec sections 3.3, domain_draft.md 6).

Reuses football's pure numeric formatters directly (they are sport-agnostic functions of a
float): ``ceil_seconds``, ``format_game_clock``, ``BLANK_DISPLAY``, ``FormattingError``,
``format_game_status``, ``format_status_clock``.
"""

from __future__ import annotations

from typing import Final

from scoreboard.domain.formatting import (
    BLANK_DISPLAY,
    FormattingError,
    ceil_seconds,
    format_game_clock,
    format_game_status,
    format_status_clock,
)
from scoreboard.domain.soccer.state import ShootoutKick

PERIOD_DISPLAY: Final[dict[str, str]] = {
    "PRE": "Pregame",
    "1st": "1st Half",
    "HALF": "Halftime",
    "2nd": "2nd Half",
    "OT1": "OT 1",
    "OT2": "OT 2",
    "SHOOTOUT": "Shootout",
    "FINAL": "Final",
}

PERIOD_DISPLAY_SHORT: Final[dict[str, str]] = {
    "PRE": "PRE",
    "1st": "1ST",
    "HALF": "HALF",
    "2nd": "2ND",
    "OT1": "OT1",
    "OT2": "OT2",
    "SHOOTOUT": "SHOOT",
    "FINAL": "FINAL",
}

STAT_LABELS: Final[dict[str, str]] = {
    "shots": "S",
    "saves": "SV",
    "corners": "COR",
    "fouls": "F",
}


def format_period(period: str) -> str:
    """``"1st Half"``, ``"Halftime"``, etc. (spec section 3.3)."""

    return PERIOD_DISPLAY.get(period, period)


def format_period_short(period: str) -> str:
    """``"1ST"``, ``"HALF"``, etc."""

    return PERIOD_DISPLAY_SHORT.get(period, period)


def format_soccer_clock(value: float, direction: str, maximum: float) -> str:
    """Format the game clock, honouring ``SoccerRules.clock_direction``.

    Countdown is always the authoritative engine value (spec section 4); ``"up"`` is purely a
    display transform: elapsed = maximum - remaining.
    """

    if direction == "up":
        return format_game_clock(max(0.0, float(maximum) - float(value)))
    return format_game_clock(value)


def format_stat(name: str, value: int) -> str:
    """``format_stat("shots", 4) -> "S 4"`` (mirrors football's ``"TO 3"`` convention)."""

    label = STAT_LABELS.get(name, name.upper())
    return f"{label} {value}"


def format_cards(yellow: int, red: int) -> str:
    """``""`` at 0/0, else ``"Y 2 · R 0"``."""

    if yellow == 0 and red == 0:
        return BLANK_DISPLAY
    return f"Y {yellow} · R {red}"


def format_shootout_dots(kicks: tuple[ShootoutKick, ...], team: str) -> str:
    """``"● ○ ●"`` for one side, chronological."""

    side = [k for k in kicks if k.team == team]
    if not side:
        return BLANK_DISPLAY
    return " ".join("●" if k.made else "○" for k in side)


__all__ = [
    "BLANK_DISPLAY",
    "PERIOD_DISPLAY",
    "PERIOD_DISPLAY_SHORT",
    "STAT_LABELS",
    "FormattingError",
    "ceil_seconds",
    "format_cards",
    "format_game_clock",
    "format_game_status",
    "format_period",
    "format_period_short",
    "format_shootout_dots",
    "format_soccer_clock",
    "format_stat",
    "format_status_clock",
]
