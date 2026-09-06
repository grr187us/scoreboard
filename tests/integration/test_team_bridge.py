"""Saved teams through the operator bridge (audit item F4, spec section 3.4).

The library is a laptop preference, never game state: the three host actions
advance no revision, submit no command, and write no action-history row.
Applying a saved team is the ordinary ``set_team_name`` command, so every
existing rule about it (pregame only, F-010 length, undo, history) applies
unchanged. What the bridge adds is the *identity* -- short name and colours --
attached to each side of every view by looking up the current name.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.host.bridge import ScoreboardBridge
from scoreboard.host.teams import TeamPresets
from scoreboard.infrastructure.persistence import GameStore, read_action_history
from tests.integration.support import FakeMonotonic, TemporaryDataDirectoryTest
from scoreboard.application.recovery import start_new_game


class TeamBridgeTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.monotonic = FakeMonotonic()
        self.service = start_new_game(monotonic_clock=self.monotonic)
        self.store = GameStore.open(self.paths)
        self.addCleanup(self.store.close)
        self.store.begin_session(self.service.state)
        self.teams = TeamPresets(self.paths)
        self.published: list[dict] = []
        self.bridge = ScoreboardBridge(
            self.service, self.store, teams=self.teams, on_accepted=self.published.append
        )

    def send(self, name: str, args: dict | None = None) -> dict:
        return self.bridge.command(name, args or {}, self.service.revision)


class HostActionTests(TeamBridgeTestCase):
    def test_saving_and_deleting_touch_no_game_state(self) -> None:
        before_revision = self.service.revision
        before_rows = len(read_action_history(self.paths.database))

        saved = self.bridge.save_team({"name": "Eagles", "short_name": "EAG", "primary": "#1f4e9a"})
        self.assertTrue(saved["ok"], saved)
        self.assertEqual(saved["message"], "Saved team Eagles.")
        self.assertEqual([team["name"] for team in saved["teams"]], ["Eagles"])
        self.assertEqual(saved["teams"][0]["primary"], "#1F4E9A")

        deleted = self.bridge.delete_team("eagles")
        self.assertTrue(deleted["ok"], deleted)
        self.assertEqual(deleted["teams"], [])

        self.assertEqual(self.service.revision, before_revision)
        self.assertEqual(len(read_action_history(self.paths.database)), before_rows)
        self.assertEqual(self.published, [])
        document = json.loads(self.paths.teams.read_text(encoding="utf-8"))
        self.assertEqual(document["teams"], [])

    def test_a_refused_save_reports_and_changes_nothing(self) -> None:
        result = self.bridge.save_team({"name": "", "primary": "#zzzzzz"})

        self.assertFalse(result["ok"])
        self.assertTrue(result["message"])
        self.assertEqual(result["teams"], [])
        self.assertFalse(self.paths.teams.exists())

    def test_teams_reports_the_current_identity_of_each_side(self) -> None:
        self.bridge.save_team({"name": "Eagles", "short_name": "EAG"})
        payload = self.bridge.teams()
        self.assertEqual(payload["current"], {"home": None, "away": None})

        result = self.send("set_team_name", {"team": "home", "name": "eagles"})
        self.assertTrue(result["accepted"], result)

        payload = self.bridge.teams()
        self.assertEqual(payload["current"]["home"]["short_name"], "EAG")
        self.assertIsNone(payload["current"]["away"])


class IdentityInViewsTests(TeamBridgeTestCase):
    def test_every_view_carries_the_identity_or_null(self) -> None:
        self.bridge.save_team({"name": "Tigers", "short_name": "TIG", "secondary": "#000000"})
        self.send("set_team_name", {"team": "away", "name": "Tigers"})

        operator = self.bridge.get_snapshot()
        spectator = self.bridge.spectator_snapshot()
        for view in (operator, spectator):
            self.assertIsNone(view["teams"]["home"]["identity"])
            self.assertEqual(
                view["teams"]["away"]["identity"],
                {"name": "Tigers", "short_name": "TIG", "primary": "#FFFFFF", "secondary": "#000000"},
            )
        # The command's own result view carries it too, so the page renders the
        # stripe from the same round trip that changed the name.
        self.assertEqual(self.published[-1]["teams"]["away"]["identity"]["short_name"], "TIG")

    def test_deleting_a_team_clears_its_identity_without_touching_the_name(self) -> None:
        self.bridge.save_team({"name": "Tigers"})
        self.send("set_team_name", {"team": "away", "name": "Tigers"})
        revision = self.service.revision

        self.bridge.delete_team("Tigers")

        view = self.bridge.get_snapshot()
        self.assertEqual(view["teams"]["away"]["name"], "Tigers")
        self.assertIsNone(view["teams"]["away"]["identity"])
        self.assertEqual(view["revision"], revision)

    def test_a_bridge_without_a_library_still_answers_plainly(self) -> None:
        bridge = ScoreboardBridge(self.service, self.store)

        self.assertIsNone(bridge.get_snapshot()["teams"]["home"]["identity"])
        payload = bridge.teams()
        self.assertEqual(payload["teams"], [])
        self.assertEqual(payload["current"], {"home": None, "away": None})
        self.assertFalse(bridge.save_team({"name": "Eagles"})["ok"])
        self.assertFalse(bridge.delete_team("Eagles")["ok"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
