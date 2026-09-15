"""Table-driven tests for scoreboard.domain.soccer.shootout (spec section 3.2).

Covers: a 5-kicker early decision, sudden victory (decided beyond the initial round), first
kicker either side, and that a correction/removal changes the tally the pure functions see.
"""

from __future__ import annotations

import unittest

from scoreboard.domain.soccer.shootout import (
    current_round,
    in_sudden_death,
    is_decided,
    next_kicker,
    winner,
)
from scoreboard.domain.soccer.state import ShootoutKick


def _build(sequence: list[tuple[str, bool]]) -> tuple[ShootoutKick, ...]:
    """Build a kicks tuple from an ordered (team, made) sequence, per-team round numbers."""

    counts = {"home": 0, "away": 0}
    kicks = []
    for team, made in sequence:
        counts[team] += 1
        kicks.append(ShootoutKick(team, counts[team], None, made))
    return tuple(kicks)


class ShootoutMatrixTests(unittest.TestCase):
    """Table-driven matrix: each row is (description, sequence, expected_decided, expected_winner)."""

    CASES = (
        (
            "full five rounds, home leads outright",
            [
                ("home", True), ("away", False),
                ("home", True), ("away", False),
                ("home", True), ("away", True),
                ("home", False), ("away", False),
                ("home", False), ("away", False),
            ],
            True,
            "home",
        ),
        (
            "decided early within the first five (away cannot catch up)",
            [
                ("home", True), ("away", False),
                ("home", True), ("away", False),
                ("home", True), ("away", False),
            ],
            True,
            "home",
        ),
        (
            "not yet decided mid-round",
            [
                ("home", True), ("away", False),
                ("home", True), ("away", False),
                ("home", True),
            ],
            False,
            None,
        ),
        (
            "tied after the full initial round -> sudden death, undecided",
            [
                ("home", True), ("away", True),
                ("home", False), ("away", False),
                ("home", True), ("away", True),
                ("home", False), ("away", False),
                ("home", True), ("away", True),
            ],
            False,
            None,
        ),
        (
            "sudden death round decides it",
            [
                ("home", True), ("away", True),
                ("home", False), ("away", False),
                ("home", True), ("away", True),
                ("home", False), ("away", False),
                ("home", True), ("away", True),
                ("home", True), ("away", False),
            ],
            True,
            "home",
        ),
        (
            "away wins outright in the initial round",
            [
                ("away", True), ("home", False),
                ("away", True), ("home", False),
                ("away", True), ("home", True),
                ("away", False), ("home", False),
                ("away", False), ("home", False),
            ],
            True,
            "away",
        ),
    )

    def test_matrix(self) -> None:
        for description, sequence, expected_decided, expected_winner in self.CASES:
            with self.subTest(description):
                kicks = _build(sequence)
                self.assertEqual(is_decided(kicks, 5), expected_decided)
                self.assertEqual(winner(kicks, 5), expected_winner)


class FirstKickerEitherSideTests(unittest.TestCase):
    def test_home_kicks_first(self) -> None:
        self.assertEqual(next_kicker((), "home", 5), "home")

    def test_away_kicks_first(self) -> None:
        self.assertEqual(next_kicker((), "away", 5), "away")

    def test_no_first_kicker_set_yet(self) -> None:
        self.assertIsNone(next_kicker((), None, 5))

    def test_alternation_after_each_kick(self) -> None:
        kicks = _build([("away", True)])
        self.assertEqual(next_kicker(kicks, "away", 5), "home")
        kicks = _build([("away", True), ("home", False)])
        self.assertEqual(next_kicker(kicks, "away", 5), "away")


class CurrentRoundAndSuddenDeathTests(unittest.TestCase):
    def test_current_round_before_any_kicks(self) -> None:
        self.assertEqual(current_round((), 5), 1)

    def test_current_round_advances_by_the_leading_side(self) -> None:
        kicks = _build([("home", True), ("away", True), ("home", False)])
        self.assertEqual(current_round(kicks, 5), 2)

    def test_in_sudden_death_only_after_both_sides_finish_the_initial_round(self) -> None:
        kicks = _build([("home", True)] * 4 + [("away", True)] * 4)
        self.assertFalse(in_sudden_death(kicks, 5))
        kicks_full = _build([("home", True)] * 5 + [("away", True)] * 5)
        self.assertTrue(in_sudden_death(kicks_full, 5))


class CorrectionAndRemovalTests(unittest.TestCase):
    """A correction or removal changes the tally the pure functions see -- exercised the way
    the service applies it: rebuild the tuple with one element replaced or dropped."""

    def test_correcting_a_kick_can_flip_the_decision(self) -> None:
        kicks = _build(
            [
                ("home", True), ("away", False),
                ("home", True), ("away", False),
                ("home", True), ("away", False),
            ]
        )
        self.assertEqual(winner(kicks, 5), "home")
        # Correct the third home kick (index 4) from made to missed.
        corrected = list(kicks)
        target = corrected[4]
        corrected[4] = ShootoutKick(target.team, target.round, target.kicker_number, False)
        corrected = tuple(corrected)
        self.assertFalse(is_decided(corrected, 5))

    def test_removing_the_last_kick_can_undecide_it(self) -> None:
        kicks = _build(
            [
                ("home", True), ("away", False),
                ("home", True), ("away", False),
                ("home", True), ("away", False),
            ]
        )
        self.assertTrue(is_decided(kicks, 5))
        without_last = kicks[:-1]
        self.assertFalse(is_decided(without_last, 5))


if __name__ == "__main__":
    unittest.main()
