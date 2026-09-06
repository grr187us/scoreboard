"""``layouts.json``: it survives a restart, and it can never stop one.

The layout library follows the same contract as ``config.json``
(``infrastructure/config.py``): **a presentation file may never stop the
scoreboard from starting.** Missing, empty, truncated, hand-edited, or written
by a future build all read as "nothing usable stored", and the built-in default
takes over. The one thing that must never happen is losing a good layout to a
bad save, so a rejected save leaves the stored file byte-for-byte intact.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.infrastructure.layouts import (
    LAYOUT_LIBRARY_SCHEMA_VERSION,
    MAX_LAYOUT_NAME_LENGTH,
    MAX_STORED_LAYOUTS,
    LayoutLibrary,
    default_library,
    delete_layout,
    duplicate_layout,
    read_library,
    rename_layout,
    reset_library,
    save_layout,
    select_layout,
    write_library,
)
from scoreboard.presentation.layout import (
    DEFAULT_LAYOUT_NAME,
    LAYOUT_SCHEMA_VERSION,
    default_layout,
)

from tests.integration.support import TemporaryDataDirectoryTest


def customised(**changes) -> dict:
    document = json.loads(json.dumps(default_layout()))
    document["widgets"]["quarter"].update(changes)
    return document


class LayoutLibraryTestCase(TemporaryDataDirectoryTest):
    def assert_untouched_game_files(self) -> None:
        """The layout library lives beside the game, never inside it."""

        self.assertFalse(self.paths.database.exists() and self.paths.database.stat().st_size == 0)
        for path in (self.paths.config, self.paths.backup):
            self.assertFalse(path.exists(), f"{path.name} must not be created by layout work")


class RoundTripTests(LayoutLibraryTestCase):
    def test_a_saved_layout_survives_a_restart(self) -> None:
        library, validation = save_layout(self.paths, "Default", customised(x=0.06))
        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertTrue(library.layouts)

        # A completely fresh read, as the next launch would perform.
        reloaded = read_library(self.paths)

        self.assertFalse(reloaded.fell_back)
        self.assertAlmostEqual(reloaded.active_layout()["widgets"]["quarter"]["x"], 0.06)
        self.assert_untouched_game_files()

    def test_the_stored_file_is_versioned_and_json(self) -> None:
        save_layout(self.paths, "Default", default_layout())

        payload = json.loads(self.paths.layouts.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], LAYOUT_LIBRARY_SCHEMA_VERSION)
        self.assertEqual(payload["active"], DEFAULT_LAYOUT_NAME)
        self.assertIn(DEFAULT_LAYOUT_NAME, payload["layouts"])

    def test_an_atomic_write_leaves_no_temporary_file(self) -> None:
        save_layout(self.paths, "Default", default_layout())

        leftovers = [p.name for p in self.paths.root.iterdir() if p.suffix == ".tmp"
                     or p.name.endswith(".json.tmp")]
        self.assertEqual(leftovers, [])

    def test_a_failed_write_is_reported_rather_than_raised(self) -> None:
        # A directory where the file should be: the write cannot succeed, and
        # this is a button an operator may press during a game.
        self.paths.layouts.mkdir(parents=True, exist_ok=True)

        self.assertFalse(write_library(self.paths, default_library()))


class MalformedFileTests(LayoutLibraryTestCase):
    def test_every_damaged_shape_reads_as_nothing_stored(self) -> None:
        cases = {
            "absent": None,
            "empty": "",
            "not json": "{ this is not JSON",
            "a json array": "[]",
            "a json string": '"layout"',
            "no layouts key": '{"schema_version": 1, "active": "Default"}',
            "layouts not an object": '{"schema_version": 1, "active": "D", "layouts": []}',
            "newer schema": '{"schema_version": 99, "active": "D", "layouts": {}}',
            "schema not a number": '{"schema_version": "1", "active": "D", "layouts": {}}',
        }
        for label, contents in cases.items():
            with self.subTest(case=label):
                if contents is None:
                    self.paths.layouts.unlink(missing_ok=True)
                else:
                    self.paths.layouts.write_text(contents, encoding="utf-8")

                library = read_library(self.paths)

                self.assertTrue(library.fell_back, label)
                self.assertEqual(library.active_layout(), default_layout())
                self.assertEqual(library.active, DEFAULT_LAYOUT_NAME)

    def test_an_active_name_that_is_not_stored_falls_back(self) -> None:
        self.paths.layouts.write_text(json.dumps({
            "schema_version": LAYOUT_LIBRARY_SCHEMA_VERSION,
            "active": "Missing",
            "layouts": {DEFAULT_LAYOUT_NAME: default_layout()},
        }), encoding="utf-8")

        library = read_library(self.paths)

        self.assertEqual(library.active_layout(), default_layout())
        self.assertTrue(library.issues)

    def test_one_invalid_stored_layout_does_not_lose_the_valid_ones(self) -> None:
        broken = json.loads(json.dumps(default_layout()))
        broken["widgets"]["quarter"]["x"] = "nonsense"
        self.paths.layouts.write_text(json.dumps({
            "schema_version": LAYOUT_LIBRARY_SCHEMA_VERSION,
            "active": DEFAULT_LAYOUT_NAME,
            "layouts": {DEFAULT_LAYOUT_NAME: customised(x=0.06), "Broken": broken},
        }), encoding="utf-8")

        library = read_library(self.paths)

        self.assertAlmostEqual(library.active_layout()["widgets"]["quarter"]["x"], 0.06)
        self.assertNotIn("Broken", library.layouts)
        self.assertTrue(library.issues)

    def test_a_newer_file_is_left_on_disk_rather_than_overwritten(self) -> None:
        """Returning to the newer build must not have lost the operator's work."""

        future = json.dumps({"schema_version": 99, "active": "D", "layouts": {}})
        self.paths.layouts.write_text(future, encoding="utf-8")

        library = read_library(self.paths)

        self.assertTrue(library.fell_back)
        self.assertEqual(self.paths.layouts.read_text(encoding="utf-8"), future)

    def test_reading_a_damaged_file_creates_nothing(self) -> None:
        self.paths.layouts.write_text("broken", encoding="utf-8")

        read_library(self.paths)

        self.assert_untouched_game_files()


class RejectedSaveTests(LayoutLibraryTestCase):
    def test_a_rejected_save_leaves_the_stored_file_byte_identical(self) -> None:
        save_layout(self.paths, "Default", customised(x=0.06))
        before = self.paths.layouts.read_bytes()

        invalid = json.loads(json.dumps(default_layout()))
        invalid["widgets"]["ball_on"]["y"] = 0.93  # past the bottom safe-area edge
        library, validation = save_layout(self.paths, "Default", invalid)

        self.assertFalse(validation.ok)
        self.assertEqual(self.paths.layouts.read_bytes(), before)
        self.assertAlmostEqual(library.active_layout()["widgets"]["quarter"]["x"], 0.06)

    def test_a_rejected_name_writes_nothing(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        before = self.paths.layouts.read_bytes()

        for name in ("", "   ", "A" * (MAX_LAYOUT_NAME_LENGTH + 1), None, 7, "bad\x00name"):
            with self.subTest(name=name):
                _, validation = save_layout(self.paths, name, default_layout())
                self.assertFalse(validation.ok)
                self.assertEqual(self.paths.layouts.read_bytes(), before)


class NamedLayoutTests(LayoutLibraryTestCase):
    def test_several_layouts_can_be_stored_selected_and_deleted(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", customised(color="#FFAA00"))
        library, validation = select_layout(self.paths, "Night")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(library.active, "Night")
        self.assertEqual(read_library(self.paths).active, "Night")
        self.assertEqual(read_library(self.paths).active_layout()["widgets"]["quarter"]["color"],
                         "#FFAA00")

        library, validation = delete_layout(self.paths, "Night")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertNotIn("Night", library.layouts)
        # Deleting the active layout must leave a usable one selected.
        self.assertEqual(library.active, DEFAULT_LAYOUT_NAME)
        self.assertEqual(read_library(self.paths).active_layout(), default_layout())

    def test_the_default_layout_can_be_customised_but_not_deleted(self) -> None:
        _, saved = save_layout(self.paths, DEFAULT_LAYOUT_NAME, customised(x=0.06))
        self.assertTrue(saved.ok)

        _, validation = delete_layout(self.paths, DEFAULT_LAYOUT_NAME)

        self.assertFalse(validation.ok)
        # A dedicated code, not a generic name complaint: the name is fine,
        # it is the built-in default that may not be removed.
        self.assertEqual({i.code for i in validation.errors}, {"DEFAULT_PROTECTED"})
        self.assertIn(DEFAULT_LAYOUT_NAME, read_library(self.paths).layouts)

    def test_selecting_or_deleting_an_unknown_name_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())

        for action in (select_layout, delete_layout):
            with self.subTest(action=action.__name__):
                _, validation = action(self.paths, "Nowhere")
                self.assertFalse(validation.ok)

    def test_the_stored_count_is_bounded(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        for index in range(MAX_STORED_LAYOUTS + 5):
            save_layout(self.paths, f"Layout {index}", default_layout())

        library = read_library(self.paths)

        self.assertLessEqual(len(library.layouts), MAX_STORED_LAYOUTS)
        self.assertIn(DEFAULT_LAYOUT_NAME, library.layouts)

    def test_names_are_listed_with_the_default_first(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Zulu", default_layout())
        save_layout(self.paths, "Alpha", default_layout())

        names = read_library(self.paths).names()

        self.assertEqual(names[0], DEFAULT_LAYOUT_NAME)
        self.assertEqual(sorted(names[1:]), names[1:])

    def test_reset_restores_only_the_built_in_default(self) -> None:
        save_layout(self.paths, "Default", customised(x=0.06))
        save_layout(self.paths, "Night", customised(color="#FFAA00"))

        library = reset_library(self.paths)

        self.assertEqual(library.layouts, {DEFAULT_LAYOUT_NAME: default_layout()})
        self.assertEqual(library.active, DEFAULT_LAYOUT_NAME)
        self.assertEqual(read_library(self.paths).active_layout(), default_layout())


class RenameLayoutTests(LayoutLibraryTestCase):
    def test_a_stored_layout_can_be_renamed(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", customised(color="#FFAA00"))

        library, validation = rename_layout(self.paths, "Night", "Evening")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertNotIn("Night", library.layouts)
        self.assertIn("Evening", library.layouts)
        # The renamed layout's own name field is updated, not just the key.
        self.assertEqual(library.layouts["Evening"]["name"], "Evening")
        self.assertEqual(library.layouts["Evening"]["schema_version"], LAYOUT_SCHEMA_VERSION)
        self.assertEqual(
            library.layouts["Evening"]["widgets"]["quarter"]["color"], "#FFAA00"
        )
        reloaded = read_library(self.paths)
        self.assertIn("Evening", reloaded.layouts)
        self.assertNotIn("Night", reloaded.layouts)

    def test_renaming_the_active_layout_keeps_it_active(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        select_layout(self.paths, "Night")

        library, validation = rename_layout(self.paths, "Night", "Evening")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(library.active, "Evening")
        self.assertEqual(read_library(self.paths).active, "Evening")

    def test_renaming_a_layout_that_is_not_active_leaves_the_active_one_alone(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        select_layout(self.paths, "Default")

        library, validation = rename_layout(self.paths, "Night", "Evening")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(library.active, DEFAULT_LAYOUT_NAME)

    def test_the_default_layout_cannot_be_renamed(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        before = self.paths.layouts.read_bytes()

        library, validation = rename_layout(self.paths, DEFAULT_LAYOUT_NAME, "Something Else")

        self.assertFalse(validation.ok)
        self.assertEqual({i.code for i in validation.errors}, {"DEFAULT_PROTECTED"})
        self.assertEqual(self.paths.layouts.read_bytes(), before)
        self.assertIn(DEFAULT_LAYOUT_NAME, read_library(self.paths).layouts)

    def test_renaming_an_unknown_layout_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        before = self.paths.layouts.read_bytes()

        library, validation = rename_layout(self.paths, "Nowhere", "Somewhere")

        self.assertFalse(validation.ok)
        self.assertEqual({i.code for i in validation.errors}, {"LAYOUT_NOT_FOUND"})
        self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_renaming_to_an_existing_name_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        save_layout(self.paths, "Morning", default_layout())
        before = self.paths.layouts.read_bytes()

        library, validation = rename_layout(self.paths, "Night", "Morning")

        self.assertFalse(validation.ok)
        self.assertEqual({i.code for i in validation.errors}, {"LAYOUT_EXISTS"})
        self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_renaming_to_an_invalid_name_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        before = self.paths.layouts.read_bytes()

        for bad_name in ("", "   ", "A" * (MAX_LAYOUT_NAME_LENGTH + 1), None, 7, "bad\x00name"):
            with self.subTest(new=bad_name):
                _, validation = rename_layout(self.paths, "Night", bad_name)
                self.assertFalse(validation.ok)
                self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_renaming_from_an_invalid_name_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        before = self.paths.layouts.read_bytes()

        for bad_name in ("", "   ", None, 7):
            with self.subTest(old=bad_name):
                _, validation = rename_layout(self.paths, bad_name, "Anything")
                self.assertFalse(validation.ok)
                self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_a_failed_rename_write_is_reported_and_leaves_the_file_untouched(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        before = self.paths.layouts.read_bytes()

        # Block the atomic write's temp file with a directory of the same name.
        temporary = self.paths.layouts.with_suffix(".json.tmp")
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            library, validation = rename_layout(self.paths, "Night", "Evening")

            self.assertFalse(validation.ok)
            self.assertEqual({i.code for i in validation.errors}, {"WRITE_FAILED"})
            self.assertEqual(self.paths.layouts.read_bytes(), before)
            self.assertIn("Night", library.layouts)
        finally:
            temporary.rmdir()


class DuplicateLayoutTests(LayoutLibraryTestCase):
    def test_a_stored_layout_can_be_duplicated(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", customised(color="#FFAA00"))

        library, validation = duplicate_layout(self.paths, "Night", "Night copy")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("Night", library.layouts)
        self.assertIn("Night copy", library.layouts)
        self.assertEqual(library.layouts["Night copy"]["name"], "Night copy")
        self.assertEqual(library.layouts["Night copy"]["schema_version"], LAYOUT_SCHEMA_VERSION)
        self.assertEqual(
            library.layouts["Night copy"]["widgets"]["quarter"]["color"], "#FFAA00"
        )
        reloaded = read_library(self.paths)
        self.assertIn("Night", reloaded.layouts)
        self.assertIn("Night copy", reloaded.layouts)

    def test_duplicating_makes_the_copy_active(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        select_layout(self.paths, "Default")

        library, validation = duplicate_layout(self.paths, "Night", "Night copy")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(library.active, "Night copy")
        self.assertEqual(read_library(self.paths).active, "Night copy")

    def test_the_default_layout_can_be_duplicated(self) -> None:
        save_layout(self.paths, DEFAULT_LAYOUT_NAME, default_layout())

        library, validation = duplicate_layout(self.paths, DEFAULT_LAYOUT_NAME, "Default copy")

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn(DEFAULT_LAYOUT_NAME, library.layouts)
        self.assertIn("Default copy", library.layouts)

    def test_duplicating_an_unknown_layout_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        before = self.paths.layouts.read_bytes()

        library, validation = duplicate_layout(self.paths, "Nowhere", "Somewhere")

        self.assertFalse(validation.ok)
        self.assertEqual({i.code for i in validation.errors}, {"LAYOUT_NOT_FOUND"})
        self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_duplicating_to_an_existing_name_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        before = self.paths.layouts.read_bytes()

        library, validation = duplicate_layout(self.paths, "Night", DEFAULT_LAYOUT_NAME)

        self.assertFalse(validation.ok)
        self.assertEqual({i.code for i in validation.errors}, {"LAYOUT_EXISTS"})
        self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_duplicating_to_an_invalid_name_is_refused(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        before = self.paths.layouts.read_bytes()

        for bad_name in ("", "   ", "A" * (MAX_LAYOUT_NAME_LENGTH + 1), None, 7, "bad\x00name"):
            with self.subTest(new=bad_name):
                _, validation = duplicate_layout(self.paths, "Default", bad_name)
                self.assertFalse(validation.ok)
                self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_the_stored_count_is_bounded_on_duplicate(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        for index in range(MAX_STORED_LAYOUTS - 1):
            save_layout(self.paths, f"Layout {index}", default_layout())
        before = self.paths.layouts.read_bytes()
        library = read_library(self.paths)
        self.assertEqual(len(library.layouts), MAX_STORED_LAYOUTS)

        _, validation = duplicate_layout(self.paths, "Default", "One too many")

        self.assertFalse(validation.ok)
        self.assertEqual({i.code for i in validation.errors}, {"MAX_STORED_LAYOUTS"})
        self.assertEqual(self.paths.layouts.read_bytes(), before)

    def test_a_failed_duplicate_write_is_reported_and_leaves_the_file_untouched(self) -> None:
        save_layout(self.paths, "Default", default_layout())
        save_layout(self.paths, "Night", default_layout())
        before = self.paths.layouts.read_bytes()

        temporary = self.paths.layouts.with_suffix(".json.tmp")
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            library, validation = duplicate_layout(self.paths, "Night", "Night copy")

            self.assertFalse(validation.ok)
            self.assertEqual({i.code for i in validation.errors}, {"WRITE_FAILED"})
            self.assertEqual(self.paths.layouts.read_bytes(), before)
            self.assertNotIn("Night copy", library.layouts)
        finally:
            temporary.rmdir()


class LibraryValueTests(unittest.TestCase):
    def test_the_default_library_is_usable_and_json_compatible(self) -> None:
        library = default_library()

        self.assertIsInstance(library, LayoutLibrary)
        self.assertEqual(library.active_layout(), default_layout())
        payload = library.to_dict()
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
