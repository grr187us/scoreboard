"""Unit tests for scoreboard.domain.soccer.formatting."""

from __future__ import annotations

import unittest

from scoreboard.domain.soccer.formatting import (
    BLANK_DISPLAY,
    format_cards,
    format_period,
    format_period_short,
    format_shootout_dots,
    format_soccer_clock,
    format_stat,
)
from scoreboard.domain.soccer.state import ShootoutKick


class FormatPeriodTests(unittest.TestCase):
    def test_every_period_has_a_display(self) -> None:
        self.assertEqual(format_period("1st"), "1st Half")
        self.assertEqual(format_period("HALF"), "Halftime")
        self.assertEqual(format_period("2nd"), "2nd Half")
        self.assertEqual(format_period("OT1"), "OT 1")
        self.assertEqual(format_period("OT2"), "OT 2")
        self.assertEqual(format_period("SHOOTOUT"), "Shootout")
        self.assertEqual(format_period("FINAL"), "Final")
        self.assertEqual(format_period("PRE"), "Pregame")

    def test_short_form(self) -> None:
        self.assertEqual(format_period_short("1st"), "1ST")
        self.assertEqual(format_period_short("FINAL"), "FINAL")


class FormatSoccerClockTests(unittest.TestCase):
    def test_down_direction_shows_remaining(self) -> None:
        self.assertEqual(format_soccer_clock(90.0, "down", 2400.0), "1:30")

    def test_up_direction_shows_elapsed(self) -> None:
        # 2400 max, 90 remaining -> 2310 elapsed -> 38:30
        self.assertEqual(format_soccer_clock(90.0, "up", 2400.0), "38:30")

    def test_up_direction_at_zero_remaining_shows_full_length(self) -> None:
        self.assertEqual(format_soccer_clock(0.0, "up", 60.0), "1:00")


class FormatStatTests(unittest.TestCase):
    def test_known_stats(self) -> None:
        self.assertEqual(format_stat("shots", 4), "S 4")
        self.assertEqual(format_stat("saves", 2), "SV 2")
        self.assertEqual(format_stat("corners", 3), "COR 3")
        self.assertEqual(format_stat("fouls", 1), "F 1")


class FormatCardsTests(unittest.TestCase):
    def test_blank_at_zero(self) -> None:
        self.assertEqual(format_cards(0, 0), BLANK_DISPLAY)

    def test_non_zero(self) -> None:
        self.assertEqual(format_cards(2, 0), "Y 2 · R 0")


class FormatShootoutDotsTests(unittest.TestCase):
    def test_blank_with_no_kicks(self) -> None:
        self.assertEqual(format_shootout_dots((), "home"), BLANK_DISPLAY)

    def test_dots_in_order(self) -> None:
        kicks = (
            ShootoutKick("home", 1, 1, True),
            ShootoutKick("away", 1, 1, True),
            ShootoutKick("home", 2, 2, False),
        )
        self.assertEqual(format_shootout_dots(kicks, "home"), "● ○")
        self.assertEqual(format_shootout_dots(kicks, "away"), "●")


if __name__ == "__main__":
    unittest.main()
