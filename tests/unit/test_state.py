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
    MAX_SCORE,
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
        self.assertEqual(state.game_clock.seconds, 720)
        self.assertFalse(state.game_clock.running)
        self.assertEqual(state.event_countdown.seconds, 1800)
        self.assertEqual(state.event_phase, "PREGAME")
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
            {"event_phase": "BREAK"},
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


if __name__ == "__main__":
    unittest.main()
