"""``teams.json``: it survives a restart, and it can never stop one.

The saved-team library follows the same contract as ``config.json``
(``infrastructure/config.py``) and ``layouts.json``
(``infrastructure/layouts.py``): **a preference file may never stop the
scoreboard from starting.** Missing, empty, truncated, hand-edited, or written
by a future build all read as "no teams saved", and the built-in empty
library takes over. The one thing that must never happen is losing a good
team to a bad save, so a rejected save leaves the stored file byte-for-byte
intact.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.domain.state import MAX_TEAM_NAME_LENGTH
from scoreboard.infrastructure.teams import (
    DEFAULT_PRIMARY,
    DEFAULT_SECONDARY,
    MAX_SHORT_NAME_LENGTH,
    MAX_STORED_TEAMS,
    TEAM_LIBRARY_SCHEMA_VERSION,
    TeamIssue,
    TeamLibrary,
    TeamPreset,
    default_library,
    delete_team,
    derive_short_name,
    read_library,
    save_team,
    validate_team,
    write_library,
)

from tests.integration.support import TemporaryDataDirectoryTest


class TeamLibraryTestCase(TemporaryDataDirectoryTest):
    def assert_untouched_game_files(self) -> None:
        """The team library lives beside the game, never inside it."""

        for path in (self.paths.config, self.paths.backup, self.paths.layouts):
            self.assertFalse(path.exists(), f"{path.name} must not be created by team work")
        self.assertFalse(self.paths.database.exists() and self.paths.database.stat().st_size == 0)


class RoundTripTests(TeamLibraryTestCase):
    def test_a_saved_team_survives_a_restart(self) -> None:
        library, issue = save_team(
            self.paths, {"name": "Eagles", "short_name": "EAG", "primary": "#1F4E9A"}
        )
        self.assertIsNone(issue)
        self.assertEqual(len(library.teams), 1)

        # A completely fresh read, as the next launch would perform.
        reloaded = read_library(self.paths)

        self.assertFalse(reloaded.fell_back)
        team = reloaded.find("Eagles")
        self.assertIsNotNone(team)
        assert team is not None
        self.assertEqual(team.short_name, "EAG")
        self.assertEqual(team.primary, "#1F4E9A")
        self.assertEqual(team.secondary, DEFAULT_SECONDARY)
        self.assert_untouched_game_files()

    def test_the_stored_file_is_versioned_and_json(self) -> None:
        save_team(self.paths, {"name": "Eagles"})

        payload = json.loads(self.paths.teams.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], TEAM_LIBRARY_SCHEMA_VERSION)
        self.assertEqual([team["name"] for team in payload["teams"]], ["Eagles"])

    def test_an_atomic_write_leaves_no_temporary_file(self) -> None:
        save_team(self.paths, {"name": "Eagles"})

        leftovers = [
            p.name for p in self.paths.root.iterdir()
            if p.suffix == ".tmp" or p.name.endswith(".json.tmp")
        ]
        self.assertEqual(leftovers, [])

    def test_a_failed_write_is_reported_rather_than_raised(self) -> None:
        # A directory where the file should be: the write cannot succeed, and
        # this is a button an operator may press during a game.
        self.paths.teams.mkdir(parents=True, exist_ok=True)

        self.assertFalse(write_library(self.paths, default_library()))


class MalformedFileTests(TeamLibraryTestCase):
    def test_every_damaged_shape_reads_as_nothing_stored(self) -> None:
        cases = {
            "absent": None,
            "empty": "",
            "not json": "{ this is not JSON",
            "a json array": "[]",
            "a json string": '"teams"',
            "no teams key": '{"schema_version": 1}',
            "teams not a list": '{"schema_version": 1, "teams": {}}',
            "newer schema": '{"schema_version": 99, "teams": []}',
            "schema not a number": '{"schema_version": "1", "teams": []}',
        }
        for label, contents in cases.items():
            with self.subTest(case=label):
                if contents is None:
                    self.paths.teams.unlink(missing_ok=True)
                else:
                    self.paths.teams.write_text(contents, encoding="utf-8")

                library = read_library(self.paths)

                self.assertEqual(library.teams, ())

    def test_a_newer_file_is_left_on_disk_rather_than_overwritten(self) -> None:
        """Returning to the newer build must not have lost the operator's work."""

        future = json.dumps({"schema_version": 99, "teams": []})
        self.paths.teams.write_text(future, encoding="utf-8")

        library = read_library(self.paths)

        self.assertTrue(library.fell_back)
        self.assertTrue(library.issues)
        self.assertEqual(self.paths.teams.read_text(encoding="utf-8"), future)

    def test_a_newer_file_refuses_a_write(self) -> None:
        future = json.dumps({"schema_version": 99, "teams": []})
        self.paths.teams.write_text(future, encoding="utf-8")

        self.assertFalse(write_library(self.paths, default_library()))
        self.assertEqual(self.paths.teams.read_text(encoding="utf-8"), future)

    def test_reading_a_damaged_file_creates_nothing(self) -> None:
        self.paths.teams.write_text("broken", encoding="utf-8")

        read_library(self.paths)

        self.assert_untouched_game_files()

    def test_one_bad_entry_is_dropped_while_siblings_load(self) -> None:
        self.paths.teams.write_text(json.dumps({
            "schema_version": TEAM_LIBRARY_SCHEMA_VERSION,
            "teams": [
                {"name": "Eagles"},
                {"name": ""},  # invalid: blank name
                {"name": "Hawks", "primary": "not-a-color"},  # invalid color
            ],
        }), encoding="utf-8")

        library = read_library(self.paths)

        self.assertEqual({team.name for team in library.teams}, {"Eagles"})
        self.assertFalse(library.fell_back)
        self.assertEqual(len(library.issues), 2)
        self.assertEqual({issue.code for issue in library.issues}, {"TEAM_DROPPED"})

    def test_every_entry_invalid_falls_back_completely(self) -> None:
        self.paths.teams.write_text(json.dumps({
            "schema_version": TEAM_LIBRARY_SCHEMA_VERSION,
            "teams": [{"name": ""}, {"name": "x" * 30}],
        }), encoding="utf-8")

        library = read_library(self.paths)

        self.assertTrue(library.fell_back)
        self.assertEqual(library.teams, ())
        self.assertTrue(library.issues)

    def test_a_later_duplicate_stored_entry_is_dropped(self) -> None:
        self.paths.teams.write_text(json.dumps({
            "schema_version": TEAM_LIBRARY_SCHEMA_VERSION,
            "teams": [
                {"name": "Eagles", "primary": "#111111"},
                {"name": "eagles ", "primary": "#222222"},
            ],
        }), encoding="utf-8")

        library = read_library(self.paths)

        self.assertEqual(len(library.teams), 1)
        team = library.find("Eagles")
        assert team is not None
        self.assertEqual(team.primary, "#111111")
        self.assertEqual({issue.code for issue in library.issues}, {"DUPLICATE"})

    def test_unknown_keys_are_ignored_on_read(self) -> None:
        self.paths.teams.write_text(json.dumps({
            "schema_version": TEAM_LIBRARY_SCHEMA_VERSION,
            "teams": [{"name": "Eagles", "mascot": "bird", "logo": "eagle.png"}],
        }), encoding="utf-8")

        library = read_library(self.paths)

        team = library.find("Eagles")
        assert team is not None
        self.assertEqual(team.to_dict(), {
            "name": "Eagles",
            "short_name": "EAGL",
            "primary": DEFAULT_PRIMARY,
            "secondary": DEFAULT_SECONDARY,
        })

    def test_unknown_keys_are_dropped_on_write(self) -> None:
        save_team(self.paths, {"name": "Eagles", "mascot": "bird"})

        payload = json.loads(self.paths.teams.read_text(encoding="utf-8"))

        self.assertEqual(set(payload["teams"][0].keys()), {"name", "short_name", "primary", "secondary"})


class SaveTeamTests(TeamLibraryTestCase):
    def test_saving_replaces_by_name_case_insensitively(self) -> None:
        save_team(self.paths, {"name": "Eagles", "primary": "#111111"})
        library, issue = save_team(self.paths, {"name": "eagles ", "primary": "#222222"})

        self.assertIsNone(issue)
        self.assertEqual(len(library.teams), 1)
        team = library.find("EAGLES")
        assert team is not None
        self.assertEqual(team.name, "eagles")
        self.assertEqual(team.primary, "#222222")

    def test_a_rejected_save_leaves_the_stored_file_byte_identical(self) -> None:
        save_team(self.paths, {"name": "Eagles"})
        before = self.paths.teams.read_bytes()

        library, issue = save_team(self.paths, {"name": ""})

        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "INVALID_NAME")
        self.assertEqual(self.paths.teams.read_bytes(), before)
        self.assertEqual(len(library.teams), 1)

    def test_invalid_names_are_refused(self) -> None:
        for bad_name in ("", "   ", "A" * (MAX_TEAM_NAME_LENGTH + 1), None, 7):
            with self.subTest(name=bad_name):
                _, issue = save_team(self.paths, {"name": bad_name})
                self.assertIsNotNone(issue)
                self.assertEqual(issue.code, "INVALID_NAME")

    def test_invalid_short_names_are_refused(self) -> None:
        _, issue = save_team(self.paths, {"name": "Eagles", "short_name": "TOOLONG"})
        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "INVALID_SHORT_NAME")

        _, issue = save_team(self.paths, {"name": "Eagles", "short_name": 7})
        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "INVALID_SHORT_NAME")

    def test_invalid_colors_are_refused(self) -> None:
        for bad_color in ("blue", "#ABC", "#GGGGGG", "111111", 7):
            with self.subTest(color=bad_color):
                _, issue = save_team(self.paths, {"name": "Eagles", "primary": bad_color})
                self.assertIsNotNone(issue)
                self.assertEqual(issue.code, "INVALID_COLOR")

    def test_colors_are_normalized_to_uppercase(self) -> None:
        library, issue = save_team(
            self.paths, {"name": "Eagles", "primary": "#1f4e9a", "secondary": "#ffffff"}
        )
        self.assertIsNone(issue)
        team = library.find("Eagles")
        assert team is not None
        self.assertEqual(team.primary, "#1F4E9A")
        self.assertEqual(team.secondary, "#FFFFFF")

    def test_short_name_is_derived_when_absent_or_blank(self) -> None:
        self.assertEqual(derive_short_name("Eagles"), "EAGL")
        self.assertEqual(derive_short_name("New York Jets"), "NEWY")
        self.assertEqual(derive_short_name("St Ana"), "STAN")

        library, _ = save_team(self.paths, {"name": "Eagles", "short_name": "  "})
        team = library.find("Eagles")
        assert team is not None
        self.assertEqual(team.short_name, "EAGL")

    def test_the_stored_count_is_bounded(self) -> None:
        for index in range(MAX_STORED_TEAMS):
            save_team(self.paths, {"name": f"Team {index}"})

        library, issue = save_team(self.paths, {"name": "One too many"})

        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "TOO_MANY_TEAMS")
        self.assertEqual(len(library.teams), MAX_STORED_TEAMS)

    def test_replacing_an_existing_team_does_not_count_against_the_cap(self) -> None:
        for index in range(MAX_STORED_TEAMS):
            save_team(self.paths, {"name": f"Team {index}"})

        library, issue = save_team(self.paths, {"name": "Team 0", "primary": "#ABCDEF"})

        self.assertIsNone(issue)
        self.assertEqual(len(library.teams), MAX_STORED_TEAMS)
        team = library.find("Team 0")
        assert team is not None
        self.assertEqual(team.primary, "#ABCDEF")

    def test_a_failed_save_write_is_reported_and_leaves_the_file_untouched(self) -> None:
        save_team(self.paths, {"name": "Eagles"})
        before = self.paths.teams.read_bytes()

        temporary = self.paths.teams.with_suffix(".json.tmp")
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            library, issue = save_team(self.paths, {"name": "Hawks"})

            self.assertIsNotNone(issue)
            self.assertEqual(issue.code, "WRITE_FAILED")
            self.assertEqual(self.paths.teams.read_bytes(), before)
            self.assertEqual(len(library.teams), 1)
        finally:
            temporary.rmdir()


class DeleteTeamTests(TeamLibraryTestCase):
    def test_a_stored_team_can_be_deleted(self) -> None:
        save_team(self.paths, {"name": "Eagles"})
        save_team(self.paths, {"name": "Hawks"})

        library, issue = delete_team(self.paths, "eagles")

        self.assertIsNone(issue)
        self.assertIsNone(library.find("Eagles"))
        self.assertIsNotNone(library.find("Hawks"))
        self.assertIsNone(read_library(self.paths).find("Eagles"))

    def test_deleting_an_unknown_name_is_refused(self) -> None:
        save_team(self.paths, {"name": "Eagles"})
        before = self.paths.teams.read_bytes()

        library, issue = delete_team(self.paths, "Nowhere")

        self.assertIsNotNone(issue)
        self.assertEqual(issue.code, "NOT_FOUND")
        self.assertEqual(self.paths.teams.read_bytes(), before)

    def test_deleting_an_invalid_name_is_refused(self) -> None:
        for bad_name in ("", "   ", None, 7):
            with self.subTest(name=bad_name):
                _, issue = delete_team(self.paths, bad_name)
                self.assertIsNotNone(issue)
                self.assertEqual(issue.code, "NOT_FOUND")


class ValidateTeamTests(unittest.TestCase):
    def test_a_minimal_valid_payload_uses_every_default(self) -> None:
        result = validate_team({"name": "Eagles"})

        self.assertIsInstance(result, TeamPreset)
        assert isinstance(result, TeamPreset)
        self.assertEqual(result.name, "Eagles")
        self.assertEqual(result.short_name, "EAGL")
        self.assertEqual(result.primary, DEFAULT_PRIMARY)
        self.assertEqual(result.secondary, DEFAULT_SECONDARY)

    def test_a_non_object_payload_is_refused(self) -> None:
        for payload in (None, "Eagles", 7, ["Eagles"]):
            with self.subTest(payload=payload):
                result = validate_team(payload)
                self.assertIsInstance(result, TeamIssue)
                assert isinstance(result, TeamIssue)
                self.assertEqual(result.code, "NOT_AN_OBJECT")

    def test_name_is_trimmed(self) -> None:
        result = validate_team({"name": "  Eagles  "})
        self.assertIsInstance(result, TeamPreset)
        assert isinstance(result, TeamPreset)
        self.assertEqual(result.name, "Eagles")


class LibraryValueTests(unittest.TestCase):
    def test_find_is_case_insensitive_and_trims(self) -> None:
        library = TeamLibrary(teams=(TeamPreset("Eagles", "EAGL", "#FFFFFF", "#111111"),))

        self.assertIsNotNone(library.find("eagles"))
        self.assertIsNotNone(library.find("  EAGLES  "))
        self.assertIsNone(library.find("Hawks"))
        self.assertIsNone(library.find(None))
        self.assertIsNone(library.find(""))

    def test_sorted_orders_by_name_case_insensitively(self) -> None:
        library = TeamLibrary(teams=(
            TeamPreset("zulu", "ZULU", "#FFFFFF", "#111111"),
            TeamPreset("Alpha", "ALPH", "#FFFFFF", "#111111"),
        ))

        self.assertEqual([team.name for team in library.sorted()], ["Alpha", "zulu"])

    def test_the_default_library_is_empty_and_json_compatible(self) -> None:
        library = default_library()

        self.assertEqual(library.teams, ())
        payload = library.to_dict()
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
