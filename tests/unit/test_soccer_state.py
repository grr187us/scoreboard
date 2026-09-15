"""Unit tests for scoreboard.domain.soccer.state (mirrors tests/unit/test_state.py)."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from scoreboard.domain.soccer.state import (
    CARD_KINDS,
    INTERVAL_PERIOD_LABELS,
    LIVE_PERIOD_LABELS,
    MAX_CARD_PLAYER_NUMBER,
    MAX_SOCCER_SCORE,
    MAX_STAT_VALUE,
    PERIOD_LABELS,
    SOCCER_STATUS_LABELS,
    STAT_NAMES,
    CardEvent,
    ClockValue,
    ShootoutKick,
    SoccerState,
    StateValidationError,
    default_state,
    lifecycle_for_period,
)


class SoccerStateTests(unittest.TestCase):
    def test_default_is_stopped_pregame_baseline(self) -> None:
        state = default_state()

        self.assertEqual(state.home_name, "HOME")
        self.assertEqual(state.away_name, "AWAY")
        self.assertEqual((state.home_score, state.away_score), (0, 0))
        self.assertEqual(state.period, "PRE")
        self.assertEqual(state.lifecycle, "PRE_GAME")
        self.assertFalse(state.game_clock.running)
        self.assertEqual(state.cards, ())
        self.assertEqual(state.shootout_kicks, ())
        self.assertIsNone(state.shootout_winner)
        self.assertIsNone(state.game_status)

    def test_state_is_frozen(self) -> None:
        state = default_state()
        with self.assertRaises(FrozenInstanceError):
            state.home_score = 5  # type: ignore[misc]

    def test_evolve_advances_revision_and_rejects_unknown_field(self) -> None:
        state = default_state()
        next_state = state.evolve(home_score=1)
        self.assertEqual(next_state.revision, state.revision + 1)
        self.assertEqual(next_state.home_score, 1)
        with self.assertRaises(StateValidationError):
            state.evolve(nonexistent_field=1)
        with self.assertRaises(StateValidationError):
            state.evolve(revision=99)

    def test_period_labels_and_partitions(self) -> None:
        self.assertEqual(
            PERIOD_LABELS, ("PRE", "1st", "HALF", "2nd", "OT1", "OT2", "SHOOTOUT", "FINAL")
        )
        self.assertEqual(LIVE_PERIOD_LABELS, frozenset({"1st", "2nd", "OT1", "OT2"}))
        self.assertEqual(INTERVAL_PERIOD_LABELS, frozenset({"PRE", "HALF"}))

    def test_invalid_period_rejected(self) -> None:
        with self.assertRaises(StateValidationError):
            SoccerState(period="3rd")

    def test_score_bounds(self) -> None:
        SoccerState(home_score=MAX_SOCCER_SCORE)
        with self.assertRaises(StateValidationError):
            SoccerState(home_score=MAX_SOCCER_SCORE + 1)
        with self.assertRaises(StateValidationError):
            SoccerState(away_score=-1)

    def test_stat_bounds(self) -> None:
        SoccerState(home_shots=MAX_STAT_VALUE)
        with self.assertRaises(StateValidationError):
            SoccerState(home_fouls=MAX_STAT_VALUE + 1)

    def test_lifecycle_for_period(self) -> None:
        self.assertEqual(lifecycle_for_period("PRE"), "PRE_GAME")
        self.assertEqual(lifecycle_for_period("HALF"), "HALFTIME")
        self.assertEqual(lifecycle_for_period("FINAL"), "FINAL")
        self.assertEqual(lifecycle_for_period("1st"), "IN_PROGRESS")
        self.assertEqual(lifecycle_for_period("OT1"), "IN_PROGRESS")


class CardEventTests(unittest.TestCase):
    def test_valid_card(self) -> None:
        card = CardEvent(team="home", kind="yellow", player_number=10, period="1st", clock_display="32:14")
        self.assertEqual(card.kind, "yellow")

    def test_kind_must_be_known(self) -> None:
        with self.assertRaises(StateValidationError):
            CardEvent(team="home", kind="blue", player_number=None, period="1st", clock_display="0:00")

    def test_player_number_optional_and_bounded(self) -> None:
        CardEvent(team="home", kind="red", player_number=None, period="1st", clock_display="0:00")
        with self.assertRaises(StateValidationError):
            CardEvent(team="home", kind="red", player_number=100, period="1st", clock_display="0:00")

    def test_card_kinds_constant(self) -> None:
        self.assertEqual(CARD_KINDS, ("yellow", "red"))
        self.assertEqual(MAX_CARD_PLAYER_NUMBER, 99)

    def test_derived_card_counts(self) -> None:
        state = SoccerState(
            cards=(
                CardEvent("home", "yellow", 1, "1st", "10:00"),
                CardEvent("home", "yellow", 2, "1st", "9:00"),
                CardEvent("home", "red", 2, "1st", "8:00"),
                CardEvent("away", "yellow", 3, "1st", "7:00"),
            )
        )
        self.assertEqual(state.home_yellow, 2)
        self.assertEqual(state.home_red, 1)
        self.assertEqual(state.away_yellow, 1)
        self.assertEqual(state.away_red, 0)


class ShootoutKickTests(unittest.TestCase):
    def test_valid_kick(self) -> None:
        kick = ShootoutKick(team="home", round=1, kicker_number=7, made=True)
        self.assertTrue(kick.made)

    def test_round_must_be_at_least_one(self) -> None:
        with self.assertRaises(StateValidationError):
            ShootoutKick(team="home", round=0, kicker_number=None, made=True)

    def test_derived_shootout_tallies(self) -> None:
        state = SoccerState(
            period="SHOOTOUT",
            shootout_kicks=(
                ShootoutKick("home", 1, 1, True),
                ShootoutKick("away", 1, 1, False),
                ShootoutKick("home", 2, 2, True),
            ),
        )
        self.assertEqual(state.shootout_home_made, 2)
        self.assertEqual(state.shootout_away_made, 0)


class SoccerStatusTests(unittest.TestCase):
    def test_status_labels(self) -> None:
        self.assertEqual(SOCCER_STATUS_LABELS, ("INJURY", "DELAY", "WEATHER"))

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(StateValidationError):
            SoccerState(game_status="TIMEOUT")

    def test_stat_names(self) -> None:
        self.assertEqual(STAT_NAMES, ("shots", "saves", "corners", "fouls"))


if __name__ == "__main__":
    unittest.main()
