"""``soccer_cutscene_packs``: scanning the packs folder and the selection
file. Mirrors ``tests/integration/test_cutscene_packs.py`` (football;
frozen). ``self.paths`` is the root; every call here goes through
``self.paths.for_sport("soccer")`` so the on-disk location is
``<root>/soccer/cutscenes/`` and ``<root>/soccer/cutscenes.json``, never the
football root's own ``cutscenes/`` folder.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.infrastructure import soccer_cutscene_packs as packs
from scoreboard.infrastructure.soccer_cutscene_packs import _is_reserved_pack_folder_name
from scoreboard.presentation.soccer_cutscenes import SOCCER_CUTSCENE_EVENTS

from tests.integration.support import TemporaryDataDirectoryTest


def _write_manifest(folder, payload) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


class SoccerCutscenePacksTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.soccer_paths = self.paths.for_sport("soccer")


class PathIsolationTests(SoccerCutscenePacksTestCase):
    def test_soccer_cutscenes_live_under_the_soccer_subfolder(self) -> None:
        self.assertEqual(self.soccer_paths.cutscenes, self.paths.root / "soccer" / "cutscenes")
        self.assertEqual(self.soccer_paths.cutscene_selection, self.paths.root / "soccer" / "cutscenes.json")

    def test_scanning_never_touches_the_football_root(self) -> None:
        packs.ensure_packs_directory(self.soccer_paths)
        _write_manifest(
            self.soccer_paths.cutscenes / "roar",
            {"schema_version": 1, "name": "Roar", "event": "goal", "scene": {"type": "builtin", "id": "goal"}},
        )
        packs.scan_packs(self.soccer_paths)
        packs.write_selection(self.soccer_paths, {"goal": "roar"})

        # ``self.paths.ensure()`` (in setUp) already creates the football
        # root's own empty ``cutscenes/`` folder; soccer's scan must not put
        # anything inside it, and must never touch the football selection
        # file or any other preference/game file at the root.
        self.assertEqual(list(self.paths.cutscenes.iterdir()), [])
        self.assertFalse(self.paths.cutscene_selection.exists())
        for path in (self.paths.config, self.paths.layouts, self.paths.teams, self.paths.database):
            self.assertFalse(path.exists())


class EnsurePacksDirectoryTests(SoccerCutscenePacksTestCase):
    def test_creates_the_folder_and_a_readme(self) -> None:
        packs.ensure_packs_directory(self.soccer_paths)

        self.assertTrue(self.soccer_paths.cutscenes.is_dir())
        readme = self.soccer_paths.cutscenes / packs.PACK_README_FILENAME
        self.assertTrue(readme.is_file())
        self.assertIn("manifest.json", readme.read_text(encoding="utf-8"))
        self.assertIn('"goal"', readme.read_text(encoding="utf-8"))

    def test_never_overwrites_an_existing_readme(self) -> None:
        packs.ensure_packs_directory(self.soccer_paths)
        readme = self.soccer_paths.cutscenes / packs.PACK_README_FILENAME
        readme.write_text("an operator's own notes", encoding="utf-8")

        packs.ensure_packs_directory(self.soccer_paths)

        self.assertEqual(readme.read_text(encoding="utf-8"), "an operator's own notes")


class ScanPacksTests(SoccerCutscenePacksTestCase):
    def test_a_missing_cutscenes_directory_is_not_an_error(self) -> None:
        result = packs.scan_packs(self.soccer_paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(result.issues, ())

    def test_a_good_pack_is_scanned_and_normalized(self) -> None:
        folder = self.soccer_paths.cutscenes / "roar"
        _write_manifest(
            folder,
            {
                "schema_version": 1, "name": "Roar", "event": "goal",
                "duration_seconds": 5, "intro": "none",
                "scene": {"type": "builtin", "id": "goal"},
            },
        )

        result = packs.scan_packs(self.soccer_paths)

        self.assertEqual(len(result.packs), 1)
        pack = result.packs[0]
        self.assertEqual(pack["id"], "roar")
        self.assertEqual(pack["event"], "goal")
        self.assertFalse(pack["builtin"])
        self.assertEqual(pack["duration_seconds"], 5.0)
        self.assertEqual(result.issues, ())

    def test_a_media_pack_gets_a_file_uri_media_url(self) -> None:
        folder = self.soccer_paths.cutscenes / "video_pack"
        _write_manifest(
            folder,
            {"schema_version": 1, "name": "Video pack", "event": "goal",
             "scene": {"type": "video", "src": "clip.webm", "fit": "cover"}},
        )
        (folder / "clip.webm").write_bytes(b"not a real video")

        result = packs.scan_packs(self.soccer_paths)

        media_url = result.packs[0]["media_url"]
        self.assertTrue(media_url.startswith("file:///"))
        self.assertTrue(media_url.endswith("clip.webm"))

    def test_an_unknown_event_is_a_manifest_error(self) -> None:
        folder = self.soccer_paths.cutscenes / "bad_event"
        _write_manifest(
            folder,
            {"schema_version": 1, "name": "Bad", "event": "own_goal",
             "scene": {"type": "builtin", "id": "goal"}},
        )

        result = packs.scan_packs(self.soccer_paths)

        self.assertEqual(result.packs, ())
        self.assertEqual(result.issues[0]["code"], "MANIFEST_EVENT")

    def test_a_good_and_a_bad_folder_side_by_side_only_drops_the_bad_one(self) -> None:
        _write_manifest(
            self.soccer_paths.cutscenes / "good",
            {"schema_version": 1, "name": "Good", "event": "goal", "scene": {"type": "builtin", "id": "goal"}},
        )
        folder = self.soccer_paths.cutscenes / "bad"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text("{broken", encoding="utf-8")

        result = packs.scan_packs(self.soccer_paths)

        self.assertEqual([pack["id"] for pack in result.packs], ["good"])
        self.assertEqual(len(result.issues), 1)


class ReservedFolderNameTests(unittest.TestCase):
    def test_a_builtin_prefixed_name_is_reserved(self) -> None:
        self.assertTrue(_is_reserved_pack_folder_name("builtin:evil"))

    def test_a_name_containing_a_path_separator_is_reserved(self) -> None:
        self.assertTrue(_is_reserved_pack_folder_name("a/b"))
        self.assertTrue(_is_reserved_pack_folder_name("a\\b"))

    def test_an_ordinary_name_is_not_reserved(self) -> None:
        self.assertFalse(_is_reserved_pack_folder_name("my_goal_pack"))


class SelectionRoundTripTests(SoccerCutscenePacksTestCase):
    def test_missing_file_yields_empty_selection(self) -> None:
        self.assertEqual(packs.read_selection(self.soccer_paths), {})

    def test_round_trip(self) -> None:
        ok = packs.write_selection(self.soccer_paths, {"goal": "roar"})

        self.assertTrue(ok)
        self.assertEqual(packs.read_selection(self.soccer_paths), {"goal": "roar"})

    def test_write_is_atomic_the_temp_file_does_not_survive(self) -> None:
        packs.write_selection(self.soccer_paths, {"goal": "roar"})

        temporary = self.soccer_paths.cutscene_selection.with_suffix(".json.tmp")
        self.assertFalse(temporary.exists())

    def test_bad_json_yields_empty_selection(self) -> None:
        self.soccer_paths.cutscene_selection.parent.mkdir(parents=True, exist_ok=True)
        self.soccer_paths.cutscene_selection.write_text("not json", encoding="utf-8")

        self.assertEqual(packs.read_selection(self.soccer_paths), {})

    def test_an_unknown_event_key_is_dropped(self) -> None:
        self.soccer_paths.cutscene_selection.parent.mkdir(parents=True, exist_ok=True)
        self.soccer_paths.cutscene_selection.write_text(
            json.dumps({"schema_version": 1, "selected": {"goal": "roar", "own_goal": "x"}}),
            encoding="utf-8",
        )

        self.assertEqual(packs.read_selection(self.soccer_paths), {"goal": "roar"})


class AutoTriggerTests(SoccerCutscenePacksTestCase):
    def test_default_is_on_for_every_event(self) -> None:
        self.assertEqual(packs.read_auto_trigger(self.soccer_paths), {"goal": True})

    def test_round_trip(self) -> None:
        ok = packs.write_auto_trigger(self.soccer_paths, {"goal": False})

        self.assertTrue(ok)
        self.assertEqual(packs.read_auto_trigger(self.soccer_paths), {"goal": False})

    def test_writing_a_selection_preserves_an_existing_auto_trigger_setting(self) -> None:
        packs.write_auto_trigger(self.soccer_paths, {"goal": False})

        packs.write_selection(self.soccer_paths, {"goal": "roar"})

        self.assertEqual(packs.read_auto_trigger(self.soccer_paths), {"goal": False})
        self.assertEqual(packs.read_selection(self.soccer_paths), {"goal": "roar"})

    def test_writing_auto_trigger_preserves_an_existing_selection(self) -> None:
        packs.write_selection(self.soccer_paths, {"goal": "roar"})

        packs.write_auto_trigger(self.soccer_paths, {"goal": False})

        self.assertEqual(packs.read_selection(self.soccer_paths), {"goal": "roar"})

    def test_malformed_file_yields_the_default(self) -> None:
        self.soccer_paths.cutscene_selection.parent.mkdir(parents=True, exist_ok=True)
        self.soccer_paths.cutscene_selection.write_text("not json", encoding="utf-8")

        self.assertEqual(packs.read_auto_trigger(self.soccer_paths), {"goal": True})


class LibraryResolveTests(SoccerCutscenePacksTestCase):
    def test_with_no_selection_every_event_resolves_to_its_builtin(self) -> None:
        library = packs.library(self.soccer_paths)

        for event in SOCCER_CUTSCENE_EVENTS:
            with self.subTest(event=event):
                pack, fell_back = library.resolve(event)
                self.assertEqual(pack["id"], f"builtin:{event}")
                self.assertFalse(fell_back)

    def test_a_selection_naming_a_real_pack_resolves_to_it(self) -> None:
        _write_manifest(
            self.soccer_paths.cutscenes / "roar",
            {"schema_version": 1, "name": "Roar", "event": "goal", "scene": {"type": "builtin", "id": "goal"}},
        )
        packs.write_selection(self.soccer_paths, {"goal": "roar"})

        library = packs.library(self.soccer_paths)
        pack, fell_back = library.resolve("goal")

        self.assertEqual(pack["id"], "roar")
        self.assertFalse(fell_back)

    def test_a_selection_naming_a_missing_pack_falls_back_to_builtin(self) -> None:
        packs.write_selection(self.soccer_paths, {"goal": "nonexistent"})

        library = packs.library(self.soccer_paths)
        pack, fell_back = library.resolve("goal")

        self.assertEqual(pack["id"], "builtin:goal")
        self.assertTrue(fell_back)

    def test_library_lists_builtins_first_then_scanned_packs(self) -> None:
        _write_manifest(
            self.soccer_paths.cutscenes / "roar",
            {"schema_version": 1, "name": "Roar", "event": "goal", "scene": {"type": "builtin", "id": "goal"}},
        )

        library = packs.library(self.soccer_paths)

        self.assertEqual(library.packs[0]["id"], "builtin:goal")
        self.assertIn("roar", [p["id"] for p in library.packs])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
