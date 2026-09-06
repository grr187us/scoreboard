"""The operator strip's "LAST: ..." line must read as plain language (U-008).

A finalized Field Assistant action is one composite undo entry whose old and
new values are whole state groups. Before this test existed the strip
rendered them as two Python dicts, which told an operator nothing at a
glance. These tests pin the human reading instead.
"""

from __future__ import annotations

import unittest

from scoreboard.host.bridge import ScoreboardBridge

from tests.integration.support import TemporaryDataDirectoryTest


class LastActionLabelCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.bridge = ScoreboardBridge(self.service, self.store)
        self.bridge.command("set_quarter", {"label": "1st", "confirmed": True}, self.service.revision)

    def finalize(self, kind: str, payload: dict) -> dict:
        result = self.bridge.finalize_field_action(
            {"kind": kind, "payload": payload}, self.service.revision
        )
        self.assertTrue(result["accepted"], result["error"])
        return result

    def label(self, result: dict) -> str:
        label = result["view"]["last_action"]["label"]
        # Never a repr of a dict or a Python literal on the strip.
        self.assertNotIn("{", label)
        self.assertNotIn("'", label)
        self.assertNotIn("None", label)
        return label


class FieldAssistantLastActionTests(LastActionLabelCase):
    def test_a_started_series_reads_as_the_resulting_situation(self) -> None:
        result = self.finalize(
            "start_series",
            {"offense": "home", "ball_absolute": 25, "first_quarter_home_direction": 1},
        )

        self.assertEqual(
            self.label(result),
            "Field assistant: Start 1st & 10 · HOME ball, 1st & 10 at HOME 25",
        )

    def test_a_touchdown_names_the_scorer_and_the_new_score(self) -> None:
        self.finalize(
            "start_series",
            {"offense": "away", "ball_absolute": 87, "first_quarter_home_direction": 1},
        )

        result = self.finalize("touchdown", {"scoring_team": "away", "add_score": True})

        label = self.label(result)
        self.assertTrue(label.startswith("Field assistant: Touchdown: +6 for AWAY"), label)
        self.assertIn("HOME 0 – AWAY 6", label)
        # After a score there is no live series, so no down-and-distance or
        # spot is claimed for the next play.
        self.assertNotIn(" at ", label)
        self.assertNotIn("&", label)

    def test_manual_score_labels_are_unchanged(self) -> None:
        result = self.bridge.command("add_score", {"team": "home", "points": 3}, self.service.revision)

        self.assertEqual(result["view"]["last_action"]["label"], "HOME score 0 → 3")


if __name__ == "__main__":
    unittest.main()
