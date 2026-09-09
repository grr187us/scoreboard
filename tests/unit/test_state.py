from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from scoreboard.application.snapshots import (
    json_to_state,
    snapshot_to_state,
    snapshot_to_json,
    state_to_snapshot,
)
from scoreboard.domain.state import (
    APP_VERSION,
    MAX_DISTANCE,
    MAX_SCORE,
    MAX_STATUS_CLOCK_SECONDS,
    MAX_TIMEOUTS,
    MAX_TIMEOUTS_CAP,
    MAX_YARD_LINE,
    BallSpot,
    ClockValue,
    GameState,
    StateValidationError,
    default_state,
)


class StateTests(unittest.TestCase):
    def test_default_is_stopped_pregame_baseline(self) -> None:
        state = default_state()

        self.assertEqual(state.home_name, "HOME")
        self.assertEqual(state.away_name, "AWAY")
        self.assertEqual((state.home_score, state.away_score), (0, 0))
        self.assertEqual(state.quarter, "PRE")
        self.assertEqual(state.lifecycle, "PRE_GAME")
        self.assertEqual(state.game_clock.seconds, 1800)
        self.assertFalse(state.game_clock.running)
        self.assertEqual(state.game_clock.maximum_seconds, 1800)
        self.assertEqual(state.revision, 0)

    def test_valid_evolve_is_immutable_and_increments_revision(self) -> None:
        original = default_state()
        updated = original.evolve(home_name="Tigers", home_score=6)

        self.assertEqual(original.home_name, "HOME")
        self.assertEqual(original.home_score, 0)
        self.assertEqual(updated.home_name, "Tigers")
        self.assertEqual(updated.home_score, 6)
        self.assertEqual(updated.revision, 1)
        with self.assertRaises(FrozenInstanceError):
            original.home_score = 1  # type: ignore[misc]

    def test_invalid_evolve_leaves_original_unchanged(self) -> None:
        original = default_state()

        with self.assertRaises(StateValidationError):
            original.evolve(home_score=MAX_SCORE + 1)
        self.assertEqual(original.home_score, 0)
        self.assertEqual(original.revision, 0)

    def test_invalid_names_scores_labels_and_versions_are_rejected(self) -> None:
        invalid_changes = (
            {"home_name": " "},
            {"away_name": "x" * 25},
            {"home_score": -1},
            {"away_score": MAX_SCORE + 1},
            {"quarter": "3Q"},
            {"lifecycle": "BROKEN"},
            {"schema_version": 2},
            {"revision": -1},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(StateValidationError):
                default_state().evolve(**changes)

    def test_clock_values_are_validated(self) -> None:
        with self.assertRaises(StateValidationError):
            ClockValue(-1)
        with self.assertRaises(StateValidationError):
            ClockValue(41, maximum_seconds=40)
        with self.assertRaises(StateValidationError):
            ClockValue(1, running="yes")  # type: ignore[arg-type]

    def test_snapshot_is_json_compatible_and_round_trips(self) -> None:
        state = default_state().evolve(
            home_name="Tigers",
            away_name="Bulldogs",
            home_score=14,
            quarter="1st",
            lifecycle="IN_PROGRESS",
            game_clock=ClockValue(701.25),
        )

        payload = state_to_snapshot(state)
        encoded = json.dumps(payload)
        restored = json_to_state(encoded)

        self.assertEqual(restored, state)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["app_version"], APP_VERSION)
        self.assertEqual(payload["state_revision"], 1)
        self.assertEqual(snapshot_to_state(payload), state)
        self.assertIn('"state_revision":1', snapshot_to_json(state))

    def test_snapshot_validation_rejects_invalid_metadata(self) -> None:
        payload = state_to_snapshot(default_state())
        payload["schema_version"] = 99

        with self.assertRaises(StateValidationError):
            snapshot_to_state(payload)

        payload = state_to_snapshot(default_state())
        payload["app_version"] = ""
        with self.assertRaises(StateValidationError):
            snapshot_to_state(payload)

    def test_a_snapshot_from_another_application_version_still_loads(self) -> None:
        """Only the schema gates compatibility; the build number is provenance.

        A game saved before an update must still be recoverable afterwards,
        because a mid-game restart is exactly when an update is most likely to
        have happened (P-004, P-006).
        """

        payload = state_to_snapshot(default_state())
        payload["app_version"] = "9.9.9"

        restored = snapshot_to_state(payload)

        self.assertEqual(restored.app_version, "9.9.9")
        self.assertEqual(restored.home_score, 0)

    def test_snapshot_is_detached_from_state(self) -> None:
        payload = state_to_snapshot(default_state())
        payload["teams"]["home"]["name"] = "Changed"

        self.assertEqual(default_state().home_name, "HOME")

    def test_default_football_state_is_not_applicable(self) -> None:
        state = default_state()

        self.assertIsNone(state.down)
        self.assertIsNone(state.distance)
        self.assertIsNone(state.possession)
        self.assertEqual(state.ball_on, BallSpot("home", 50))
        self.assertEqual(state.home_timeouts, MAX_TIMEOUTS)
        self.assertEqual(state.away_timeouts, MAX_TIMEOUTS)

    def test_football_fields_accept_valid_values(self) -> None:
        updated = default_state().evolve(
            down=3,
            distance=0,
            possession="away",
            ball_on=BallSpot("away", MAX_YARD_LINE),
            home_timeouts=0,
            away_timeouts=MAX_TIMEOUTS,
        )

        self.assertEqual(updated.down, 3)
        self.assertEqual(updated.distance, 0)
        self.assertEqual(updated.possession, "away")
        self.assertEqual(updated.ball_on.yard_line, MAX_YARD_LINE)
        self.assertEqual(updated.home_timeouts, 0)

    def test_down_distance_and_timeouts_can_be_cleared_or_null(self) -> None:
        state = default_state().evolve(down=2, distance=5, possession="home")

        cleared = state.evolve(down=None, distance=None, possession=None)

        self.assertIsNone(cleared.down)
        self.assertIsNone(cleared.distance)
        self.assertIsNone(cleared.possession)

    def test_invalid_football_fields_are_rejected(self) -> None:
        invalid_changes = (
            {"down": 0},
            {"down": 5},
            {"down": 1.5},
            {"distance": -1},
            {"distance": MAX_DISTANCE + 1},
            {"possession": "visitor"},
            {"home_timeouts": -1},
            {"away_timeouts": MAX_TIMEOUTS_CAP + 1},
            {"ball_on": "home"},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(StateValidationError):
                default_state().evolve(**changes)

    def test_crowd_status_fields_default_to_unset_and_cleared(self) -> None:
        state = default_state()

        self.assertIsNone(state.game_status)
        self.assertTrue(state.status_clock_cleared)
        self.assertAlmostEqual(state.status_clock.seconds, 0.0)
        self.assertFalse(state.status_clock.running)
        self.assertEqual(state.status_clock.maximum_seconds, MAX_STATUS_CLOCK_SECONDS)

    def test_invalid_crowd_status_fields_are_rejected(self) -> None:
        invalid_changes = (
            {"game_status": "SACK"},
            {"status_clock_cleared": "yes"},
            {"status_clock": ClockValue(0.0, False, 40.0)},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(StateValidationError):
                default_state().evolve(**changes)

    def test_ball_spot_validates_its_own_fields(self) -> None:
        BallSpot("home", 0)
        BallSpot("away", MAX_YARD_LINE)

        with self.assertRaises(StateValidationError):
            BallSpot("visitor", 10)
        with self.assertRaises(StateValidationError):
            BallSpot("home", -1)
        with self.assertRaises(StateValidationError):
            BallSpot("home", MAX_YARD_LINE + 1)

    def test_football_snapshot_round_trips(self) -> None:
        state = default_state().evolve(
            down=4,
            distance=0,
            possession="home",
            ball_on=BallSpot("away", 12),
            home_timeouts=1,
            away_timeouts=2,
        )

        payload = state_to_snapshot(state)
        restored = json_to_state(json.dumps(payload))

        self.assertEqual(restored, state)
        self.assertEqual(
            payload["football"],
            {
                "down": 4,
                "distance": 0,
                "possession": "home",
                "ball_on": {"team": "away", "yard_line": 12},
                "timeouts": {"home": 1, "away": 2},
            },
        )

    def test_a_pre_football_expansion_snapshot_still_loads(self) -> None:
        """P-004/P-006: a snapshot without a "football" key predates this field
        set and must still load with the same defaults default_state() carries.
        """

        payload = state_to_snapshot(default_state())
        del payload["football"]

        restored = snapshot_to_state(payload)

        self.assertEqual(restored, default_state())

    def test_assistant_series_state_is_additive_and_round_trips(self) -> None:
        state = default_state().evolve(
            assistant_first_quarter_home_direction=1,
            assistant_line_to_gain=63,
        )

        payload = state_to_snapshot(state)

        self.assertEqual(
            payload["assistant"],
            {"first_quarter_home_direction": 1, "line_to_gain": 63},
        )
        self.assertEqual(json_to_state(json.dumps(payload)), state)

    def test_old_snapshot_without_assistant_state_recovers_safe_setup_defaults(self) -> None:
        payload = state_to_snapshot(default_state())
        del payload["assistant"]

        restored = snapshot_to_state(payload)

        self.assertIsNone(restored.assistant_first_quarter_home_direction)
        self.assertIsNone(restored.assistant_line_to_gain)

    def test_scoring_transition_can_clear_ball_status(self) -> None:
        state = default_state().evolve(ball_on=None)

        self.assertIsNone(state_to_snapshot(state)["football"]["ball_on"])
        self.assertEqual(snapshot_to_state(state_to_snapshot(state)), state)

    def test_crowd_status_snapshot_round_trips(self) -> None:
        """F3: the status block round-trips through JSON like every other field."""

        state = default_state().evolve(
            game_status="TIMEOUT",
            status_clock=ClockValue(45.0, True, MAX_STATUS_CLOCK_SECONDS),
            status_clock_cleared=False,
        )

        payload = state_to_snapshot(state)
        restored = json_to_state(json.dumps(payload))

        self.assertEqual(
            payload["status"],
            {
                "label": "TIMEOUT",
                "clock": {"seconds": 45.0, "running": True},
                "clock_cleared": False,
            },
        )
        self.assertEqual(restored, state)
        self.assertEqual(snapshot_to_state(payload), state)

    def test_a_pre_status_expansion_snapshot_still_loads(self) -> None:
        """P-004/P-006: a snapshot without a "status" key predates F3 and must
        still load with the same defaults default_state() carries.
        """

        payload = state_to_snapshot(default_state())
        del payload["status"]

        restored = snapshot_to_state(payload)

        self.assertEqual(restored, default_state())
        self.assertIsNone(restored.game_status)
        self.assertTrue(restored.status_clock_cleared)
        self.assertAlmostEqual(restored.status_clock.seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
