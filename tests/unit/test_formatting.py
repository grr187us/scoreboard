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
    format_ball_on,
    format_down_and_distance,
    format_event_countdown,
    format_game_clock,
    format_game_status,
    format_play_clock,
    format_status_clock,
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


class GameStatusDisplayTests(unittest.TestCase):
    """F3: the crowd-facing status word is a pass-through, blank when unset."""

    def test_every_label_passes_through_unchanged(self) -> None:
        for label in ("FLAG", "TIMEOUT", "INJURY", "DELAY"):
            with self.subTest(label=label):
                self.assertEqual(format_game_status(label), label)

    def test_none_blanks_the_display(self) -> None:
        self.assertEqual(format_game_status(None), "")


class StatusClockDisplayTests(unittest.TestCase):
    """F3: rounded-up M:SS, same rounding rule as format_game_clock."""

    def test_documented_boundaries(self) -> None:
        cases = [
            (90.0, "1:30"),
            (60.0, "1:00"),
            (30.0, "0:30"),
            (0.01, "0:01"),
            (0.0, "0:00"),
        ]
        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_status_clock(seconds, blank_at_zero=False), expected)

    def test_rounds_up_like_the_game_clock(self) -> None:
        # A running countdown must never show a value the operator has not
        # reached yet: 59.9 still reads "1:00" until it truly reaches 59.
        self.assertEqual(format_status_clock(59.9, blank_at_zero=False), "1:00")
        self.assertEqual(format_status_clock(59.0, blank_at_zero=False), "0:59")

    def test_blank_when_cleared(self) -> None:
        self.assertEqual(format_status_clock(0.0, blank_at_zero=True), "")

    def test_zero_after_natural_expiry_is_not_blank(self) -> None:
        # A countdown that ran itself down to zero stays visible at "0:00";
        # only clear_game_status blanks it (blank_at_zero=False here mirrors
        # status_clock_cleared staying False on natural expiry).
        self.assertEqual(format_status_clock(0.0, blank_at_zero=False), "0:00")

    def test_blank_at_zero_does_not_blank_a_nonzero_value(self) -> None:
        self.assertEqual(format_status_clock(0.01, blank_at_zero=True), "0:01")


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


class DownAndDistanceDisplayTests(unittest.TestCase):
    """Deferred scoreboard fields: down/distance rendering."""

    def test_every_down_with_an_ordinary_distance(self) -> None:
        cases = [(1, 10, "1st & 10"), (2, 1, "2nd & 1"), (3, 99, "3rd & 99"), (4, 7, "4th & 7")]
        for down, distance, expected in cases:
            with self.subTest(down=down, distance=distance):
                self.assertEqual(format_down_and_distance(down, distance), expected)

    def test_zero_distance_displays_as_goal(self) -> None:
        self.assertEqual(format_down_and_distance(1, 0), "1st & Goal")

    def test_either_value_being_none_blanks_the_whole_display(self) -> None:
        self.assertEqual(format_down_and_distance(None, 7), "")
        self.assertEqual(format_down_and_distance(3, None), "")
        self.assertEqual(format_down_and_distance(None, None), "")

    def test_an_out_of_range_down_is_rejected(self) -> None:
        with self.assertRaises(FormattingError):
            format_down_and_distance(5, 3)
        with self.assertRaises(FormattingError):
            format_down_and_distance(0, 3)


class BallOnDisplayTests(unittest.TestCase):
    """Deferred scoreboard fields: field-position rendering."""

    def test_a_teams_own_side_is_named(self) -> None:
        self.assertEqual(format_ball_on("home", 35, "TIGERS"), "TIGERS 35")
        self.assertEqual(format_ball_on("away", 1, "EAGLES"), "EAGLES 1")

    def test_midfield_drops_the_team_name(self) -> None:
        # 50 is the same physical yard line regardless of which team's goal
        # line it is counted from, so no side is attached to it.
        self.assertEqual(format_ball_on("home", 50, "TIGERS"), "50")
        self.assertEqual(format_ball_on("away", 50, "EAGLES"), "50")

    def test_the_goal_line_itself_is_zero(self) -> None:
        self.assertEqual(format_ball_on("home", 0, "TIGERS"), "TIGERS 0")

    def test_invalid_team_or_yard_line_is_rejected(self) -> None:
        with self.assertRaises(FormattingError):
            format_ball_on("visitor", 35, "TIGERS")
        with self.assertRaises(FormattingError):
            format_ball_on("home", 51, "TIGERS")
        with self.assertRaises(FormattingError):
            format_ball_on("home", -1, "TIGERS")


if __name__ == "__main__":
    unittest.main()
