"""``TeamPresets``: the saved-team library as the bridge/view model needs it.

Team identity is not game state (spec F4 section 3.1): this class only reads,
saves, and deletes the library a shortcut is drawn from, and looks up the
identity matching the game's *current* team name. It is a host concern
exactly like ``PresentationLayouts`` (``tests/integration/test_layout_bridge.py``):
no revision, no command, no action-history row, and it never touches
``config.json``, ``layouts.json``, or ``scoreboard.db``.
"""

from __future__ import annotations

import unittest

from scoreboard.host.teams import TeamPresets
from scoreboard.infrastructure.diagnostics import Diagnostics
from scoreboard.infrastructure.teams import DEFAULT_PRIMARY, DEFAULT_SECONDARY, save_team

from tests.integration.support import TemporaryDataDirectoryTest


class TeamPresetsTestCase(TemporaryDataDirectoryTest):
    def make_diagnostics(self) -> Diagnostics:
        diagnostics = Diagnostics(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(diagnostics.close)
        return diagnostics

    def log_text(self) -> str:
        return self.paths.log_file.read_text(encoding="utf-8")

    def assert_untouched_game_files(self) -> None:
        for path in (self.paths.config, self.paths.backup, self.paths.layouts):
            self.assertFalse(path.exists(), f"{path.name} must not be created by team work")


class StateAndIdentityTests(TeamPresetsTestCase):
    def test_a_fresh_library_has_no_teams_and_is_not_an_error(self) -> None:
        presets = TeamPresets(self.paths)

        state = presets.state()

        self.assertEqual(state["teams"], [])
        self.assertEqual(state["issues"], [])
        self.assertTrue(state["fell_back"])
        self.assert_untouched_game_files()

    def test_identity_finds_a_saved_team_case_insensitively(self) -> None:
        save_team(self.paths, {"name": "Eagles", "short_name": "EAG", "primary": "#1F4E9A"})
        presets = TeamPresets(self.paths)

        identity = presets.identity("  eagles ")

        self.assertEqual(identity, {
            "name": "Eagles", "short_name": "EAG", "primary": "#1F4E9A", "secondary": DEFAULT_SECONDARY,
        })

    def test_identity_is_none_for_an_unknown_or_blank_name(self) -> None:
        presets = TeamPresets(self.paths)

        self.assertIsNone(presets.identity("Nobody"))
        self.assertIsNone(presets.identity(""))
        self.assertIsNone(presets.identity(None))

    def test_identities_looks_up_both_sides_independently(self) -> None:
        save_team(self.paths, {"name": "Eagles"})
        save_team(self.paths, {"name": "Hawks"})
        presets = TeamPresets(self.paths)

        result = presets.identities("Eagles", "Nobody")

        self.assertIsNotNone(result["home"])
        assert result["home"] is not None
        self.assertEqual(result["home"]["name"], "Eagles")
        self.assertIsNone(result["away"])

    def test_state_lists_teams_sorted_by_name(self) -> None:
        save_team(self.paths, {"name": "Zulu"})
        save_team(self.paths, {"name": "Alpha"})
        presets = TeamPresets(self.paths)

        names = [team["name"] for team in presets.state()["teams"]]

        self.assertEqual(names, ["Alpha", "Zulu"])


class SaveAndDeleteTests(TeamPresetsTestCase):
    def test_saving_a_new_team_reports_saved_and_notes_it(self) -> None:
        diagnostics = self.make_diagnostics()
        presets = TeamPresets(self.paths, diagnostics=diagnostics)

        result = presets.save({"name": "Eagles", "primary": "#1F4E9A"})
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Saved team Eagles.")
        self.assertEqual([t["name"] for t in result["teams"]], ["Eagles"])
        self.assertIn("TEAM_PRESET_SAVED", self.log_text())
        self.assertIn("name=Eagles", self.log_text())
        # The identity is visible immediately, without re-reading the file.
        self.assertIsNotNone(presets.identity("Eagles"))

    def test_saving_an_existing_team_reports_updated(self) -> None:
        presets = TeamPresets(self.paths)
        presets.save({"name": "Eagles", "primary": "#111111"})

        result = presets.save({"name": "eagles ", "primary": "#222222"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Updated team eagles.")
        identity = presets.identity("Eagles")
        assert identity is not None
        self.assertEqual(identity["primary"], "#222222")

    def test_a_refused_save_reports_ok_false_with_the_issue_message_and_notes_it(self) -> None:
        diagnostics = self.make_diagnostics()
        presets = TeamPresets(self.paths, diagnostics=diagnostics)

        result = presets.save({"name": ""})
        diagnostics.flush()

        self.assertFalse(result["ok"])
        self.assertTrue(result["message"])
        self.assertEqual(result["teams"], [])
        self.assertIn("TEAM_PRESET_REFUSED", self.log_text())
        self.assertIn("code=INVALID_NAME", self.log_text())

    def test_a_refused_save_keeps_the_old_in_memory_library(self) -> None:
        presets = TeamPresets(self.paths)
        presets.save({"name": "Eagles"})

        presets.save({"name": "x" * 40})

        self.assertIsNotNone(presets.identity("Eagles"))
        self.assertEqual(len(presets.state()["teams"]), 1)

    def test_a_library_file_that_fails_to_write_returns_ok_false_and_keeps_the_library(self) -> None:
        presets = TeamPresets(self.paths)
        presets.save({"name": "Eagles"})

        temporary = self.paths.teams.with_suffix(".json.tmp")
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            result = presets.save({"name": "Hawks"})

            self.assertFalse(result["ok"])
            self.assertIsNone(presets.identity("Hawks"))
            self.assertIsNotNone(presets.identity("Eagles"))
            self.assertEqual(len(presets.state()["teams"]), 1)
        finally:
            temporary.rmdir()

    def test_deleting_a_team_reports_deleted_and_notes_it(self) -> None:
        diagnostics = self.make_diagnostics()
        presets = TeamPresets(self.paths, diagnostics=diagnostics)
        presets.save({"name": "Eagles"})

        result = presets.delete("Eagles")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Deleted team Eagles.")
        self.assertEqual(result["teams"], [])
        self.assertIsNone(presets.identity("Eagles"))
        self.assertIn("TEAM_PRESET_DELETED", self.log_text())

    def test_deleting_an_unknown_team_is_refused_and_noted(self) -> None:
        diagnostics = self.make_diagnostics()
        presets = TeamPresets(self.paths, diagnostics=diagnostics)

        result = presets.delete("Nowhere")
        diagnostics.flush()

        self.assertFalse(result["ok"])
        self.assertTrue(result["message"])
        self.assertIn("TEAM_PRESET_REFUSED", self.log_text())
        self.assertIn("code=NOT_FOUND", self.log_text())

    def test_saves_and_deletes_never_touch_other_preference_or_game_files(self) -> None:
        presets = TeamPresets(self.paths)
        presets.save({"name": "Eagles"})
        presets.save({"name": "Hawks"})
        presets.delete("Eagles")

        self.assert_untouched_game_files()


class FellBackNoticeTests(TeamPresetsTestCase):
    def test_a_damaged_file_is_noted_at_construction(self) -> None:
        self.paths.teams.write_text("not json", encoding="utf-8")
        diagnostics = self.make_diagnostics()

        TeamPresets(self.paths, diagnostics=diagnostics)
        diagnostics.flush()

        self.assertIn("TEAM_LIBRARY_FELL_BACK", self.log_text())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
