"""``cutscene_packs``: scanning the packs folder and the selection file.

Mirrors ``test_layout_persistence.py``/``test_team_library.py``'s style and
the "never touch ``config.json``/``layouts.json``/``teams.json``/
``scoreboard.db``" boundary every preference file in this codebase respects.
A missing ``cutscenes`` folder is the ordinary state before an operator has
dropped anything in, not damage; a folder that fails to parse is one skipped
pack (with an issue recorded) while its siblings still load.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.infrastructure import cutscene_packs as packs
from scoreboard.infrastructure.cutscene_packs import _is_reserved_pack_folder_name

from tests.integration.support import TemporaryDataDirectoryTest


def _write_manifest(folder, payload) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


class EnsurePacksDirectoryTests(TemporaryDataDirectoryTest):
    def test_creates_the_folder_and_a_readme(self) -> None:
        packs.ensure_packs_directory(self.paths)

        self.assertTrue(self.paths.cutscenes.is_dir())
        readme = self.paths.cutscenes / packs.PACK_README_FILENAME
        self.assertTrue(readme.is_file())
        self.assertIn("manifest.json", readme.read_text(encoding="utf-8"))

    def test_never_overwrites_an_existing_readme(self) -> None:
        packs.ensure_packs_directory(self.paths)
        readme = self.paths.cutscenes / packs.PACK_README_FILENAME
        readme.write_text("an operator's own notes", encoding="utf-8")

        packs.ensure_packs_directory(self.paths)

        self.assertEqual(readme.read_text(encoding="utf-8"), "an operator's own notes")


class ScanPacksTests(TemporaryDataDirectoryTest):
    def test_a_missing_cutscenes_directory_is_not_an_error(self) -> None:
        result = packs.scan_packs(self.paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(result.issues, ())

    def test_a_good_pack_is_scanned_and_normalized(self) -> None:
        folder = self.paths.cutscenes / "roar"
        _write_manifest(
            folder,
            {
                "schema_version": 1,
                "name": "Roar",
                "event": "touchdown",
                "duration_seconds": 8,
                "intro": "claw_scratch",
                "scene": {"type": "builtin", "id": "touchdown"},
            },
        )

        result = packs.scan_packs(self.paths)

        self.assertEqual(len(result.packs), 1)
        pack = result.packs[0]
        self.assertEqual(pack["id"], "roar")
        self.assertEqual(pack["name"], "Roar")
        self.assertEqual(pack["event"], "touchdown")
        self.assertFalse(pack["builtin"])
        self.assertEqual(pack["duration_seconds"], 8.0)
        self.assertEqual(pack["folder"], str(folder))
        self.assertIsNone(pack["media_url"])
        self.assertEqual(result.issues, ())

    def test_a_media_pack_gets_a_file_uri_media_url(self) -> None:
        folder = self.paths.cutscenes / "video_pack"
        _write_manifest(
            folder,
            {
                "schema_version": 1,
                "name": "Video pack",
                "event": "touchdown",
                "scene": {"type": "video", "src": "clip.webm", "fit": "cover"},
            },
        )
        (folder / "clip.webm").write_bytes(b"not a real video")

        result = packs.scan_packs(self.paths)

        self.assertEqual(len(result.packs), 1)
        media_url = result.packs[0]["media_url"]
        self.assertTrue(media_url.startswith("file:///"))
        self.assertTrue(media_url.endswith("clip.webm"))

    def test_a_folder_with_no_manifest_is_silently_ignored(self) -> None:
        (self.paths.cutscenes / "empty_folder").mkdir(parents=True)

        result = packs.scan_packs(self.paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(result.issues, ())

    def test_invalid_json_is_skipped_with_a_manifest_json_issue(self) -> None:
        folder = self.paths.cutscenes / "broken"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text("not json at all", encoding="utf-8")

        result = packs.scan_packs(self.paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0]["pack_id"], "broken")
        self.assertEqual(result.issues[0]["code"], "MANIFEST_JSON")

    def test_a_manifest_error_is_skipped_but_its_issue_is_recorded(self) -> None:
        folder = self.paths.cutscenes / "bad_event"
        _write_manifest(
            folder,
            {
                "schema_version": 1, "name": "Bad", "event": "field_goal",
                "scene": {"type": "builtin", "id": "touchdown"},
            },
        )

        result = packs.scan_packs(self.paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0]["pack_id"], "bad_event")
        self.assertEqual(result.issues[0]["code"], "MANIFEST_EVENT")

    def test_a_manifest_warning_still_includes_the_pack(self) -> None:
        folder = self.paths.cutscenes / "long_one"
        _write_manifest(
            folder,
            {
                "schema_version": 1, "name": "Long one", "event": "touchdown",
                "duration_seconds": 999,
                "scene": {"type": "builtin", "id": "touchdown"},
            },
        )

        result = packs.scan_packs(self.paths)

        self.assertEqual(len(result.packs), 1)
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0]["code"], "DURATION_CLAMPED")
        self.assertEqual(result.issues[0]["pack_id"], "long_one")

    def test_a_good_and_a_bad_folder_side_by_side_only_drops_the_bad_one(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "good",
            {"schema_version": 1, "name": "Good", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )
        folder = self.paths.cutscenes / "bad"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text("{broken", encoding="utf-8")

        result = packs.scan_packs(self.paths)

        self.assertEqual([pack["id"] for pack in result.packs], ["good"])
        self.assertEqual(len(result.issues), 1)

    def test_packs_are_sorted_by_event_then_name_then_id(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "b_pack",
            {"schema_version": 1, "name": "Zeta", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )
        _write_manifest(
            self.paths.cutscenes / "a_pack",
            {"schema_version": 1, "name": "Alpha", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )
        _write_manifest(
            self.paths.cutscenes / "c_pack",
            {"schema_version": 1, "name": "First", "event": "first_down", "scene": {"type": "builtin", "id": "first_down"}},
        )

        result = packs.scan_packs(self.paths)

        self.assertEqual([pack["id"] for pack in result.packs], ["c_pack", "a_pack", "b_pack"])

    def test_a_media_src_naming_a_missing_file_is_a_media_error(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "missing_media",
            {
                "schema_version": 1, "name": "Missing", "event": "touchdown",
                "scene": {"type": "video", "src": "nowhere.webm", "fit": "cover"},
            },
        )

        result = packs.scan_packs(self.paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(result.issues[0]["code"], "MANIFEST_MEDIA")

    def test_scanning_never_touches_other_preference_or_game_files(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "good",
            {"schema_version": 1, "name": "Good", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )

        packs.scan_packs(self.paths)
        packs.write_selection(self.paths, {"touchdown": "good"})

        for path in (self.paths.config, self.paths.layouts, self.paths.teams, self.paths.database):
            self.assertFalse(path.exists(), f"{path.name} must not be created by cutscene work")


class ReservedFolderNameTests(unittest.TestCase):
    """Direct coverage of the folder-name rule: a colon-prefixed name cannot
    even be created on Windows (":" is not a legal filename character
    there), so the on-disk scan cannot exercise that half of the rule on
    this platform -- this proves the pure check itself instead.
    """

    def test_a_builtin_prefixed_name_is_reserved(self) -> None:
        self.assertTrue(_is_reserved_pack_folder_name("builtin:evil"))
        self.assertTrue(_is_reserved_pack_folder_name("builtin:touchdown"))

    def test_a_name_containing_a_path_separator_is_reserved(self) -> None:
        self.assertTrue(_is_reserved_pack_folder_name("a/b"))
        self.assertTrue(_is_reserved_pack_folder_name("a\\b"))

    def test_an_ordinary_name_is_not_reserved(self) -> None:
        self.assertFalse(_is_reserved_pack_folder_name("my_touchdown_pack"))


class SelectionRoundTripTests(TemporaryDataDirectoryTest):
    def test_missing_file_yields_empty_selection(self) -> None:
        self.assertEqual(packs.read_selection(self.paths), {})

    def test_round_trip(self) -> None:
        ok = packs.write_selection(self.paths, {"touchdown": "roar", "first_down": "hustle"})

        self.assertTrue(ok)
        self.assertEqual(
            packs.read_selection(self.paths), {"touchdown": "roar", "first_down": "hustle"}
        )

    def test_write_is_atomic_the_temp_file_does_not_survive(self) -> None:
        packs.write_selection(self.paths, {"touchdown": "roar"})

        temporary = self.paths.cutscene_selection.with_suffix(".json.tmp")
        self.assertFalse(temporary.exists())

    def test_bad_json_yields_empty_selection(self) -> None:
        self.paths.cutscene_selection.write_text("not json", encoding="utf-8")

        self.assertEqual(packs.read_selection(self.paths), {})

    def test_wrong_schema_version_yields_empty_selection(self) -> None:
        self.paths.cutscene_selection.write_text(
            json.dumps({"schema_version": 2, "selected": {"touchdown": "roar"}}), encoding="utf-8"
        )

        self.assertEqual(packs.read_selection(self.paths), {})

    def test_a_non_string_value_drops_only_that_key(self) -> None:
        self.paths.cutscene_selection.write_text(
            json.dumps(
                {"schema_version": 1, "selected": {"touchdown": "roar", "first_down": 5}}
            ),
            encoding="utf-8",
        )

        self.assertEqual(packs.read_selection(self.paths), {"touchdown": "roar"})

    def test_an_unknown_event_key_is_dropped(self) -> None:
        self.paths.cutscene_selection.write_text(
            json.dumps(
                {"schema_version": 1, "selected": {"touchdown": "roar", "field_goal": "x"}}
            ),
            encoding="utf-8",
        )

        self.assertEqual(packs.read_selection(self.paths), {"touchdown": "roar"})

    def test_selected_missing_or_wrong_shape_yields_empty(self) -> None:
        self.paths.cutscene_selection.write_text(
            json.dumps({"schema_version": 1}), encoding="utf-8"
        )
        self.assertEqual(packs.read_selection(self.paths), {})

        self.paths.cutscene_selection.write_text(
            json.dumps({"schema_version": 1, "selected": "not a dict"}), encoding="utf-8"
        )
        self.assertEqual(packs.read_selection(self.paths), {})

    def test_writing_never_touches_other_preference_or_game_files(self) -> None:
        packs.write_selection(self.paths, {"touchdown": "roar"})

        for path in (self.paths.config, self.paths.layouts, self.paths.teams, self.paths.database):
            self.assertFalse(path.exists(), f"{path.name} must not be created by cutscene work")


class LibraryResolveTests(TemporaryDataDirectoryTest):
    def test_with_no_selection_every_event_resolves_to_its_builtin(self) -> None:
        library = packs.library(self.paths)

        for event in ("first_down", "touchdown"):
            pack, fell_back = library.resolve(event)
            self.assertEqual(pack["id"], f"builtin:{event}")
            self.assertFalse(fell_back)

    def test_library_lists_builtins_first_then_scanned_packs(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "roar",
            {"schema_version": 1, "name": "Roar", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )

        library = packs.library(self.paths)

        ids = [pack["id"] for pack in library.packs]
        self.assertEqual(ids[0], "builtin:first_down")
        self.assertEqual(ids[1], "builtin:touchdown")
        self.assertIn("roar", ids[2:])

    def test_a_selection_naming_a_real_pack_resolves_to_it(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "roar",
            {"schema_version": 1, "name": "Roar", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )
        packs.write_selection(self.paths, {"touchdown": "roar"})

        library = packs.library(self.paths)
        pack, fell_back = library.resolve("touchdown")

        self.assertEqual(pack["id"], "roar")
        self.assertFalse(fell_back)

    def test_a_selection_naming_a_missing_pack_falls_back_to_builtin(self) -> None:
        packs.write_selection(self.paths, {"touchdown": "nonexistent"})

        library = packs.library(self.paths)
        pack, fell_back = library.resolve("touchdown")

        self.assertEqual(pack["id"], "builtin:touchdown")
        self.assertTrue(fell_back)

    def test_a_selection_naming_a_pack_for_a_different_event_falls_back(self) -> None:
        _write_manifest(
            self.paths.cutscenes / "roar",
            {"schema_version": 1, "name": "Roar", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}},
        )
        # A hand-edited selection file could point "first_down" at a pack
        # that is actually registered for "touchdown".
        packs.write_selection(self.paths, {"first_down": "roar"})

        library = packs.library(self.paths)
        pack, fell_back = library.resolve("first_down")

        self.assertEqual(pack["id"], "builtin:first_down")
        self.assertTrue(fell_back)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
