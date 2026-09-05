"""Focused FA-01 through FA-16 coverage for the pure field assistant."""

from __future__ import annotations

import unittest

from scoreboard.domain.field_assistant import (
    FieldAction,
    FieldAssistantContext,
    FieldAssistantValidationError,
    SeriesState,
    absolute_from_ball_spot,
    apply_penalty,
    ball_spot_from_absolute,
    calculate_field_action,
    direction_for,
    home_goal_side,
    penalty_enforcement_spot,
    preview_field_goal,
    preview_incomplete_pass,
    preview_kickoff,
    preview_normal_play,
    preview_safety,
    preview_touchdown,
    preview_try,
    preview_turnover,
    start_series,
)
from scoreboard.domain.state import BallSpot


def setup_context(
    *, quarter: str = "1st", offense: str = "home", spot: int = 25, down: int = 1,
    first_direction: int = 1, line_to_gain: int | None = None,
) -> FieldAssistantContext:
    default_line_to_gain = min(100, spot + 10) if offense == "home" else max(0, spot - 10)
    return FieldAssistantContext(
        quarter=quarter, possession=offense, ball_on=ball_spot_from_absolute(spot), down=down,
        distance=10, series=SeriesState(
            first_direction,
            line_to_gain if line_to_gain is not None else default_line_to_gain,
        ),
    )


class FieldAssistantRuleTests(unittest.TestCase):
    def test_fa_01_coordinate_round_trip_and_midfield_normalization(self) -> None:
        for spot in (BallSpot("home", 0), BallSpot("home", 25), BallSpot("home", 50), BallSpot("away", 0), BallSpot("away", 25), BallSpot("away", 50)):
            with self.subTest(spot=spot):
                self.assertEqual(absolute_from_ball_spot(ball_spot_from_absolute(absolute_from_ball_spot(spot))), absolute_from_ball_spot(spot))
        self.assertEqual(ball_spot_from_absolute(50), BallSpot("home", 50))

    def test_fa_02_direction_is_fixed_per_team_while_goal_side_alternates(self) -> None:
        quarters = ("1st", "2nd", "3rd", "4th")
        for first_direction in (1, -1):
            with self.subTest(first_direction=first_direction):
                self.assertEqual(
                    [direction_for(first_direction, quarter, "home") for quarter in quarters], [1, 1, 1, 1]
                )
                self.assertEqual(
                    [direction_for(first_direction, quarter, "away") for quarter in quarters], [-1, -1, -1, -1]
                )
        self.assertEqual(
            [home_goal_side(1, quarter) for quarter in quarters], ["left", "right", "left", "right"]
        )
        self.assertEqual(
            [home_goal_side(-1, quarter) for quarter in quarters], ["right", "left", "right", "left"]
        )
        self.assertIsNone(home_goal_side(None, "1st"))
        self.assertIsNone(home_goal_side(1, "OT"))
        with self.assertRaises(FieldAssistantValidationError):
            direction_for(1, "OT", "home")

    def test_fa_03_series_start_sets_ten_or_goal_to_go(self) -> None:
        direction = SeriesState(1, None)
        for spot, expected_line, expected_distance in ((50, 60, 10), (25, 35, 10), (90, 100, 0), (95, 100, 0)):
            with self.subTest(spot=spot):
                result = start_series(FieldAssistantContext("1st", None, BallSpot(), None, None, direction), "home", spot)
                self.assertEqual((result.series.line_to_gain, result.distance, result.down), (expected_line, expected_distance, 1))

    def test_fa_04_normal_play_short_of_line_advances_one_down(self) -> None:
        result = preview_normal_play(setup_context(spot=25), 31)
        self.assertEqual((absolute_from_ball_spot(result.ball_on), result.down, result.distance, result.series.line_to_gain), (31, 2, 4, 35))

    def test_fa_05_reaching_line_starts_a_new_series(self) -> None:
        exact = preview_normal_play(setup_context(spot=25), 35)
        beyond = preview_normal_play(setup_context(spot=25), 42)
        self.assertEqual((exact.down, exact.distance, exact.series.line_to_gain), (1, 10, 45))
        self.assertEqual((beyond.down, beyond.distance, beyond.series.line_to_gain), (1, 10, 52))
        goal = preview_normal_play(setup_context(spot=80), 90)
        self.assertEqual((goal.down, goal.distance, goal.series.line_to_gain), (1, 0, 100))

    def test_fa_06_loss_increases_distance_but_stays_valid(self) -> None:
        result = preview_normal_play(setup_context(spot=25), 18)
        self.assertEqual((result.down, result.distance, absolute_from_ball_spot(result.ball_on)), (2, 17, 18))

    def test_fa_07_incomplete_retains_spot_line_and_advances_down(self) -> None:
        for down in (1, 2, 3):
            with self.subTest(down=down):
                context = setup_context(down=down, spot=25)
                result = preview_incomplete_pass(context)
                self.assertEqual((absolute_from_ball_spot(result.ball_on), result.series.line_to_gain, result.down), (25, 35, down + 1))

    def test_fa_08_fourth_down_miss_proposes_not_silently_turns_over(self) -> None:
        result = preview_normal_play(setup_context(down=4, spot=25), 30)
        self.assertTrue(result.requires_explicit_turnover)
        self.assertEqual((result.possession, result.down, result.classification), ("home", 4, "turnover_on_downs_proposed"))

    def test_fa_09_goal_line_scrimmage_requires_explicit_transition(self) -> None:
        for final_spot in (0, 100):
            with self.subTest(final_spot=final_spot), self.assertRaises(FieldAssistantValidationError):
                preview_normal_play(setup_context(spot=25), final_spot)

    def test_fa_10_penalty_shortcuts_clamp_and_name_benefit(self) -> None:
        home = setup_context(spot=97)
        away = setup_context(offense="away", spot=3, first_direction=1)
        for yards in (-15, -10, -5, 5, 10, 15):
            with self.subTest(yards=yards):
                spot, label = penalty_enforcement_spot(home, yards)
                self.assertTrue(0 <= spot <= 100)
                self.assertIn("benefits", label)
                self.assertTrue(0 <= penalty_enforcement_spot(away, yards)[0] <= 100)

    def test_fa_11_penalty_outcomes_follow_the_selected_consequence(self) -> None:
        context = setup_context(spot=25, down=2)
        repeat = apply_penalty(context, 20, "repeat_down")
        counted = apply_penalty(context, 20, "count_down")
        automatic = apply_penalty(context, 20, "automatic_first")
        no_play = apply_penalty(context, 20, "no_play")
        underlying = preview_normal_play(context, 30)
        declined = apply_penalty(context, 20, "decline", underlying_result=underlying)
        self.assertEqual((repeat.down, repeat.series.line_to_gain), (2, 35))
        self.assertEqual((counted.down, counted.series.line_to_gain), (3, 35))
        self.assertEqual((automatic.down, automatic.series.line_to_gain), (1, 30))
        self.assertEqual((no_play.down, no_play.classification), (2, "no_play"))
        self.assertIs(declined, underlying)

    def test_fa_12_explicit_turnover_starts_new_series_in_new_direction(self) -> None:
        result = preview_turnover(setup_context(spot=30, down=4), "away", 30)
        self.assertEqual((result.possession, result.down, result.series.line_to_gain, result.distance), ("away", 1, 20, 10))

    def test_fa_13_touchdown_optional_score_and_field_clear(self) -> None:
        added = preview_touchdown("home")
        already = preview_touchdown("home", add_score=False)
        self.assertEqual((added.score_delta_home, added.score_delta_away, added.ball_on, added.down), (6, 0, None, None))
        self.assertEqual(already.score_delta_home, 0)
        self.assertIn("try", added.follow_up.lower())

    def test_fa_14_try_supports_one_two_or_no_points(self) -> None:
        self.assertEqual([preview_try("away", points).score_delta_away for points in (0, 1, 2)], [0, 1, 2])
        self.assertIn("kickoff", preview_try("away", 1).follow_up.lower())

    def test_fa_15_field_goal_and_safety_are_explicit(self) -> None:
        field_goal = preview_field_goal("away")
        safety = preview_safety("home")
        self.assertEqual((field_goal.score_delta_away, field_goal.ball_on), (3, None))
        self.assertEqual((safety.score_delta_home, safety.possession), (2, None))
        self.assertIn("free kick", safety.follow_up.lower())

    def test_fa_16_kickoff_starts_receiving_series_at_confirmed_spot(self) -> None:
        context = FieldAssistantContext("2nd", None, BallSpot(), None, None, SeriesState(1, None))
        touchback = preview_kickoff(context, "away", 80)
        return_end = preview_kickoff(context, "home", 25)
        self.assertEqual((touchback.possession, absolute_from_ball_spot(touchback.ball_on), touchback.down, touchback.distance), ("away", 80, 1, 10))
        self.assertEqual((return_end.possession, absolute_from_ball_spot(return_end.ball_on), return_end.down, return_end.distance), ("home", 25, 1, 10))

    def test_fa_17_second_quarter_home_and_away_advance_toward_their_own_goal(self) -> None:
        home_context = setup_context(quarter="2nd", offense="home", spot=25, line_to_gain=35)
        home_result = preview_normal_play(home_context, 31)
        self.assertEqual(
            (home_result.ball_on, home_result.down, home_result.distance, home_result.series.line_to_gain),
            (BallSpot("home", 31), 2, 4, 35),
        )

        away_context = setup_context(quarter="2nd", offense="away", spot=75, line_to_gain=65)
        away_result = preview_normal_play(away_context, 69)
        self.assertEqual(
            (away_result.ball_on, away_result.down, away_result.distance, away_result.series.line_to_gain),
            (BallSpot("away", 31), 2, 4, 65),
        )

    def test_fa_18_second_quarter_series_start_and_kickoff_set_correct_line_to_gain(self) -> None:
        home_series = SeriesState(1, None)
        home_context = FieldAssistantContext("2nd", None, BallSpot(), None, None, home_series)
        home_start = start_series(home_context, "home", 25)
        self.assertEqual(home_start.series.line_to_gain, 35)

        away_context = FieldAssistantContext("2nd", None, BallSpot(), None, None, home_series)
        away_start = start_series(away_context, "away", 75)
        self.assertEqual(away_start.series.line_to_gain, 65)

        kickoff = preview_kickoff(home_context, "home", 25)
        self.assertEqual(kickoff.series.line_to_gain, 35)

    def test_dispatcher_uses_bridge_neutral_action_envelope(self) -> None:
        result = calculate_field_action(setup_context(), FieldAction("normal_play", {"final_absolute": 30}))
        self.assertEqual((result.down, result.distance), (2, 5))
        with self.assertRaises(FieldAssistantValidationError):
            calculate_field_action(setup_context(), FieldAction("normal_play", {}))


if __name__ == "__main__":
    unittest.main()
