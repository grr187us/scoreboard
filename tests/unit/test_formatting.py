"""Boundary tests for the pure clock display formatter (F-039, F-047).

Every case uses an exact literal value; nothing sleeps and nothing reads a
clock. The documented boundaries come from `docs/MVP_REQUIREMENTS.md` sections
4.4 and 4.5.
"""

import unittest

from scoreboard.domain.formatting import (
    FormattingError,
    ceil_seconds,
    ceil_tenths,
    displayed_second,
    format_event_countdown,
    format_game_clock,
    format_play_clock,
)


class GameClockDisplayTests(unittest.TestCase):
    """F-039: whole seconds down to a rounded 60.0, then tenths, always up."""

    def test_documented_boundaries(self) -> None:
        cases = [
            (60.0, "1:00"),
            (59.99, "1:00"),
            (59.9, "59.9"),
            (12 * 60 + 25.1, "12:26"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_game_clock(seconds), expected)

    def test_values_between_the_boundaries_hold_one_minute(self) -> None:
        for seconds in (59.91, 59.95, 59.999):
            with self.subTest(seconds=seconds):
                self.assertEqual(format_game_clock(seconds), "1:00")

    def test_tenths_below_one_minute_round_upward(self) -> None:
        cases = [
            (59.89, "59.9"),
            (59.81, "59.9"),
            (30.04, "30.1"),
            (30.0, "30.0"),
            (0.01, "0.1"),
            (0.0, "0.0"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_game_clock(seconds), expected)

    def test_whole_minutes_and_zero_padding(self) -> None:
        cases = [
            (12 * 60.0, "12:00"),
            (11 * 60 + 59.0, "11:59"),
            (10 * 60 + 5.0, "10:05"),
            (60.01, "1:01"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_game_clock(seconds), expected)

    def test_the_display_never_understates_remaining_time(self) -> None:
        for hundredths in range(0, 6001):
            seconds = hundredths / 100.0
            with self.subTest(seconds=seconds):
                self.assertGreaterEqual(ceil_tenths(seconds) / 10.0, seconds)


class PlayClockDisplayTests(unittest.TestCase):
    """F-047: whole seconds until a rounded 5.0, then tenths, always up."""

    def test_documented_boundaries(self) -> None:
        cases = [
            (5.0, "5"),
            (4.99, "5"),
            (4.9, "4.9"),
            (4.01, "4.1"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_play_clock(seconds), expected)

    def test_presets_and_expiry(self) -> None:
        cases = [
            (40.0, "40"),
            (25.0, "25"),
            (24.2, "25"),
            (5.01, "6"),
            (0.05, "0.1"),
            (0.0, "0.0"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_play_clock(seconds), expected)

    def test_a_cleared_play_clock_can_render_blank_but_an_expired_one_does_not(self) -> None:
        self.assertEqual(format_play_clock(0.0, blank_at_zero=True), "")
        self.assertEqual(format_play_clock(0.0), "0.0")


class EventCountdownDisplayTests(unittest.TestCase):
    """F-025/F-026 boundaries for the pregame and interval countdowns."""

    def test_documented_boundaries(self) -> None:
        cases = [
            (30 * 60.0, "30:00"),
            (15 * 60.0, "15:00"),
            (181.0, "3:01"),
            (180.0, "3:00"),
            (179.9, "3:00"),
            (0.0, "0:00"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_event_countdown(seconds), expected)


class RoundingPrimitiveTests(unittest.TestCase):
    """Float noise must never push an exact tenth across a boundary."""

    def test_exact_tenths_do_not_round_up_again(self) -> None:
        for tenths in range(0, 7201):
            seconds = tenths / 10.0
            with self.subTest(tenths=tenths):
                self.assertEqual(ceil_tenths(seconds), tenths)

    def test_ceil_seconds_derives_from_the_tenths_value(self) -> None:
        self.assertEqual(ceil_seconds(59.99), 60)
        self.assertEqual(ceil_seconds(59.9), 60)
        self.assertEqual(ceil_seconds(59.0), 59)
        self.assertEqual(ceil_seconds(0.0), 0)

    def test_displayed_second_is_the_checkpoint_cadence_key(self) -> None:
        self.assertEqual(displayed_second(12.0), 12)
        self.assertEqual(displayed_second(11.9), 12)
        self.assertEqual(displayed_second(11.0), 11)

    def test_invalid_values_are_rejected_rather_than_rendered(self) -> None:
        for value in (-0.1, float("nan"), float("inf"), "12", None, True):
            with self.subTest(value=value):
                with self.assertRaises(FormattingError):
                    format_game_clock(value)


if __name__ == "__main__":
    unittest.main()
