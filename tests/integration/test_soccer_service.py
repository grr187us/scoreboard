"""Integration tests for scoreboard.application.soccer_service.

Mirrors tests/unit/test_commands.py + tests/integration flavour for football's service. Covers
goal/period/card/shootout/status flows, mercy flag, stop_clock_on_goal on/off, and golden goal.
"""

from __future__ import annotations

import unittest

from scoreboard.application.soccer_service import SoccerService, initial_soccer_state
from scoreboard.domain.soccer.commands import (
    GOAL_NOT_ALLOWED,
    SCORE_BELOW_ZERO,
    SHOOTOUT_NOT_DECIDED,
    SHOOTOUT_WINNER_MISMATCH,
    add_card,
    add_goal,
    add_stat,
    correct_goal,
    end_game,
    finish_shootout,
    new_game,
    period_forward,
    remove_card,
    set_period,
    set_score,
    set_shootout_first_kicker,
    set_stat,
    set_team_name,
    shootout_correct_kick,
    shootout_kick,
    shootout_remove_last,
    undo,
)
from scoreboard.domain.soccer.rules import SoccerRules


class FakeMonotonic:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_service(**kwargs) -> SoccerService:
    kwargs.setdefault("monotonic_clock", FakeMonotonic())
    return SoccerService(**kwargs)


class TeamNameTests(unittest.TestCase):
    def test_set_team_name_only_pregame(self) -> None:
        service = make_service()
        result = service.submit(set_team_name("home", "Eagles"))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.home_name, "Eagles")

        service.submit(set_period("1st", confirmed=True))
        blocked = service.submit(set_team_name("away", "Tigers"))
        self.assertFalse(blocked.accepted)


class AddGoalTests(unittest.TestCase):
    def test_goal_refused_outside_live_periods(self) -> None:
        service = make_service()
        result = service.submit(add_goal("home"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, GOAL_NOT_ALLOWED)

    def test_goal_accepted_in_a_live_period(self) -> None:
        service = make_service()
        service.submit(set_period("1st", confirmed=True))
        result = service.submit(add_goal("home"))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.home_score, 1)

    def test_correct_goal_below_zero_rejected(self) -> None:
        service = make_service()
        service.submit(set_period("1st", confirmed=True))
        result = service.submit(correct_goal("home"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, SCORE_BELOW_ZERO)

    def test_set_score_direct(self) -> None:
        service = make_service()
        result = service.submit(set_score("away", 5))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.away_score, 5)


class StopClockOnGoalTests(unittest.TestCase):
    def test_clock_stops_on_goal_when_rule_is_on(self) -> None:
        service = make_service(rules=SoccerRules(stop_clock_on_goal=True))
        service.submit(set_period("1st", confirmed=True))
        from scoreboard.domain.soccer.commands import game_clock_start

        service.submit(game_clock_start())
        self.assertTrue(service.game_clock.running)
        result = service.submit(add_goal("home"))
        self.assertTrue(result.accepted)
        self.assertFalse(service.game_clock.running)

    def test_clock_keeps_running_on_goal_when_rule_is_off(self) -> None:
        service = make_service(rules=SoccerRules(stop_clock_on_goal=False))
        service.submit(set_period("1st", confirmed=True))
        from scoreboard.domain.soccer.commands import game_clock_start

        service.submit(game_clock_start())
        service.submit(add_goal("home"))
        self.assertTrue(service.game_clock.running)

    def test_undo_after_goal_restores_only_the_score(self) -> None:
        service = make_service(rules=SoccerRules(stop_clock_on_goal=True))
        service.submit(set_period("1st", confirmed=True))
        from scoreboard.domain.soccer.commands import game_clock_start

        service.submit(game_clock_start())
        service.submit(add_goal("home"))
        self.assertFalse(service.game_clock.running)
        result = service.submit(undo())
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.home_score, 0)
        # the clock stays stopped -- restarting is the operator's decision
        self.assertFalse(service.game_clock.running)


class PeriodTests(unittest.TestCase):
    def test_period_forward_requires_confirmation(self) -> None:
        service = make_service()
        result = service.submit(period_forward())
        self.assertFalse(result.accepted)
        self.assertTrue(result.confirmation_required)

    def test_period_forward_loads_fresh_length_and_clears_undo(self) -> None:
        service = make_service()
        service.submit(set_score("home", 1))
        result = service.submit(period_forward(confirmed=True))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.period, "1st")
        self.assertEqual(service.state.game_clock.seconds, service.rules.half_seconds)
        self.assertIsNone(service.undo_entry)

    def test_period_decision_pending_after_natural_expiry_in_2nd(self) -> None:
        service = make_service()
        service.submit(set_period("2nd", confirmed=True))
        from scoreboard.domain.soccer.commands import game_clock_start

        service.submit(game_clock_start())
        service.monotonic_clock.advance(service.rules.half_seconds + 1)
        service.observe_tick()
        decision = service.period_decision()
        self.assertTrue(decision["pending"])
        self.assertEqual(decision["period"], "2nd")

    def test_period_decision_offers_overtime_when_configured(self) -> None:
        service = make_service(rules=SoccerRules(overtime_periods=2, shootout_enabled=True))
        service.submit(set_period("2nd", confirmed=True))
        from scoreboard.domain.soccer.commands import game_clock_start

        service.submit(game_clock_start())
        service.monotonic_clock.advance(service.rules.half_seconds + 1)
        service.observe_tick()
        decision = service.period_decision()
        labels = [c["label"] for c in decision["choices"]]
        self.assertIn("Overtime 1", labels)
        self.assertIn("Final", labels)
        self.assertIn("Keep", labels)

    def test_period_decision_offers_shootout_when_no_overtime(self) -> None:
        service = make_service(rules=SoccerRules(overtime_periods=0, shootout_enabled=True))
        service.submit(set_period("2nd", confirmed=True))
        from scoreboard.domain.soccer.commands import game_clock_start

        service.submit(game_clock_start())
        service.monotonic_clock.advance(service.rules.half_seconds + 1)
        service.observe_tick()
        decision = service.period_decision()
        labels = [c["label"] for c in decision["choices"]]
        self.assertIn("Shootout", labels)

    def test_golden_goal_raises_period_decision_immediately(self) -> None:
        service = make_service(rules=SoccerRules(overtime_periods=2, golden_goal=True))
        service.submit(set_period("OT1", confirmed=True))
        result = service.submit(add_goal("home"))
        self.assertTrue(result.accepted)
        self.assertTrue(service.period_decision()["pending"])


class StatTests(unittest.TestCase):
    def test_add_stat_and_set_stat(self) -> None:
        service = make_service()
        result = service.submit(add_stat("home", "shots", 1))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.home_shots, 1)
        result = service.submit(set_stat("home", "shots", 6))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.home_shots, 6)
        undo_result = service.submit(undo())
        self.assertTrue(undo_result.accepted)
        self.assertEqual(service.state.home_shots, 1)


class CardTests(unittest.TestCase):
    def test_add_and_remove_card_restores_whole_tuple(self) -> None:
        service = make_service()
        service.submit(set_period("1st", confirmed=True))
        service.submit(add_card("away", "yellow", player=10))
        self.assertEqual(len(service.state.cards), 1)
        card = service.state.cards[0]
        self.assertEqual(card.period, "1st")
        result = service.submit(undo())
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.cards, ())

    def test_remove_card_by_index(self) -> None:
        service = make_service()
        service.submit(add_card("home", "yellow", player=1))
        service.submit(add_card("home", "red", player=2))
        result = service.submit(remove_card("home", 0))
        self.assertTrue(result.accepted)
        self.assertEqual(len(service.state.cards), 1)
        self.assertEqual(service.state.cards[0].kind, "red")


class ShootoutTests(unittest.TestCase):
    def _play_to_decided(self, service: SoccerService) -> None:
        service.submit(set_period("SHOOTOUT", confirmed=True))
        service.submit(set_shootout_first_kicker("home"))
        for team, made in (
            ("home", True), ("away", False),
            ("home", True), ("away", False),
            ("home", True), ("away", False),
        ):
            service.submit(shootout_kick(team, made))

    def test_finish_shootout_requires_decided(self) -> None:
        service = make_service()
        service.submit(set_period("SHOOTOUT", confirmed=True))
        service.submit(set_shootout_first_kicker("home"))
        service.submit(shootout_kick("home", True))
        result = service.submit(finish_shootout())
        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, SHOOTOUT_NOT_DECIDED)

    def test_finish_shootout_with_credit_goal(self) -> None:
        service = make_service(rules=SoccerRules(shootout_credit_goal=True))
        self._play_to_decided(service)
        result = service.submit(finish_shootout(winner="home"))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.shootout_winner, "home")
        self.assertEqual(service.state.period, "FINAL")
        self.assertEqual(service.state.lifecycle, "FINAL")
        self.assertEqual(service.state.home_score, 1)

    def test_finish_shootout_without_credit_goal(self) -> None:
        service = make_service(rules=SoccerRules(shootout_credit_goal=False))
        self._play_to_decided(service)
        result = service.submit(finish_shootout(winner="home"))
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.home_score, 0)

    def test_finish_shootout_rejects_mismatched_winner(self) -> None:
        service = make_service()
        self._play_to_decided(service)
        result = service.submit(finish_shootout(winner="away"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, SHOOTOUT_WINNER_MISMATCH)

    def test_shootout_correct_and_remove_last(self) -> None:
        service = make_service()
        service.submit(set_period("SHOOTOUT", confirmed=True))
        service.submit(set_shootout_first_kicker("home"))
        service.submit(shootout_kick("home", True))
        service.submit(shootout_kick("away", False))
        result = service.submit(shootout_correct_kick(1, True))
        self.assertTrue(result.accepted)
        self.assertTrue(service.state.shootout_kicks[1].made)
        result = service.submit(shootout_remove_last())
        self.assertTrue(result.accepted)
        self.assertEqual(len(service.state.shootout_kicks), 1)


class MercyRuleTests(unittest.TestCase):
    def test_mercy_off(self) -> None:
        service = make_service(rules=SoccerRules(mercy_applies="off", mercy_differential=9))
        service.submit(set_score("home", 10))
        self.assertFalse(service.mercy_reached)

    def test_mercy_any_time(self) -> None:
        service = make_service(rules=SoccerRules(mercy_applies="any_time", mercy_differential=9))
        service.submit(set_period("1st", confirmed=True))
        service.submit(set_score("home", 9))
        self.assertTrue(service.mercy_reached)

    def test_mercy_halftime_and_second_half_not_in_first_half(self) -> None:
        service = make_service(
            rules=SoccerRules(mercy_applies="halftime_and_second_half", mercy_differential=9)
        )
        service.submit(set_period("1st", confirmed=True))
        service.submit(set_score("home", 9))
        self.assertFalse(service.mercy_reached)

    def test_mercy_halftime_and_second_half_at_half(self) -> None:
        service = make_service(
            rules=SoccerRules(mercy_applies="halftime_and_second_half", mercy_differential=9)
        )
        service.submit(set_score("home", 9))
        service.submit(set_period("HALF", confirmed=True))
        self.assertTrue(service.mercy_reached)

    def test_mercy_halftime_and_second_half_in_second_half(self) -> None:
        service = make_service(
            rules=SoccerRules(mercy_applies="halftime_and_second_half", mercy_differential=9)
        )
        service.submit(set_score("home", 9))
        service.submit(set_period("2nd", confirmed=True))
        self.assertTrue(service.mercy_reached)

    def test_mercy_never_automatic(self) -> None:
        service = make_service(rules=SoccerRules(mercy_applies="any_time", mercy_differential=9))
        service.submit(set_period("1st", confirmed=True))
        service.submit(set_score("home", 9))
        self.assertTrue(service.mercy_reached)
        self.assertEqual(service.state.lifecycle, "IN_PROGRESS")


class GameLifecycleTests(unittest.TestCase):
    def test_new_game_and_end_game_are_never_on_the_undo_stack(self) -> None:
        service = make_service()
        service.submit(set_score("home", 3))
        result = service.submit(new_game(confirmed=True))
        self.assertTrue(result.accepted)
        self.assertIsNone(service.undo_entry)
        result = service.submit(end_game())
        self.assertTrue(result.accepted)
        self.assertEqual(service.state.lifecycle, "FINAL")
        self.assertIsNone(service.undo_entry)

    def test_set_game_status_and_clear_are_not_undoable(self) -> None:
        from scoreboard.domain.soccer.commands import clear_game_status, set_game_status

        service = make_service()
        service.submit(set_score("home", 1))
        service.submit(set_game_status("WEATHER", seconds=1800))
        self.assertEqual(service.state.game_status, "WEATHER")
        self.assertTrue(service.status_clock.running)
        # the score's undo entry must still be there -- crowd status is exempt
        undo_result = service.submit(undo())
        self.assertTrue(undo_result.accepted)
        self.assertEqual(service.state.home_score, 0)
        service.submit(clear_game_status())
        self.assertIsNone(service.state.game_status)


if __name__ == "__main__":
    unittest.main()
