"""The soccer cutscene schema: pack-manifest validation and the program it
builds. Mirrors ``tests/unit/test_cutscene_schema.py`` (football; frozen).

The one behaviour football's file does not exercise: GOAL is never
"nobody's". :func:`build_program` requires a keyword-only ``team`` and reads
the scoring team's name straight from the live spectator view (not a fixed
school identity), and the theme carries ``home_primary``/``away_primary``
keyed to the saved team identity, with a fixed navy/red fallback.

Pure module: no file I/O, no clock, no window.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from scoreboard.presentation.soccer_cutscenes import (
    BUILTIN_SCENE_IDS,
    DEFAULT_DURATION_SECONDS,
    EVENT_DEFAULT_INTRO,
    EVENT_HEADLINES,
    EVENT_LABELS,
    FALLBACK_AWAY_PRIMARY,
    FALLBACK_HOME_PRIMARY,
    FIT_MODES,
    INTRO_DURATION_MS,
    INTRO_IDS,
    MANIFEST_SCHEMA_VERSION,
    MAX_DURATION_SECONDS,
    MEDIA_EXTENSIONS,
    MIN_DURATION_SECONDS,
    SCENE_TYPES,
    SOCCER_CUTSCENE_EVENTS,
    SOCCER_OUTRO_DURATION_MS,
    STAGE,
    THEME,
    build_program,
    builtin_pack,
    builtin_pack_id,
    event_descriptors,
    normalize_pack,
    validate_manifest,
)


def _good_manifest(**overrides: object) -> dict:
    manifest = {
        "schema_version": 1,
        "name": "Goal -- net ripple",
        "event": "goal",
        "duration_seconds": 7,
        "intro": "none",
        "scene": {"type": "video", "src": "goal.webm", "fit": "cover", "loop": False},
    }
    manifest.update(overrides)
    return manifest


class ValidManifestTests(unittest.TestCase):
    def test_a_complete_valid_manifest_normalizes_with_every_field_filled(self) -> None:
        result = validate_manifest(_good_manifest(), files={"goal.webm"})

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())
        self.assertEqual(
            result.manifest,
            {
                "schema_version": 1,
                "name": "Goal -- net ripple",
                "event": "goal",
                "duration_seconds": 7,
                "intro": "none",
                "scene": {"type": "video", "src": "goal.webm", "fit": "cover", "loop": False},
            },
        )

    def test_missing_optional_fields_take_the_documented_defaults(self) -> None:
        payload = {
            "schema_version": 1,
            "name": "Minimal",
            "event": "goal",
            "scene": {"type": "builtin", "id": "goal"},
        }

        result = validate_manifest(payload, files=set())

        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["duration_seconds"], DEFAULT_DURATION_SECONDS["goal"])
        self.assertEqual(result.manifest["intro"], "none")
        self.assertEqual(result.manifest["scene"], {"type": "builtin", "id": "goal"})

    def test_unknown_top_level_keys_are_ignored_without_a_warning(self) -> None:
        payload = _good_manifest(future_field="something new")

        result = validate_manifest(payload, files={"goal.webm"})

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())
        self.assertNotIn("future_field", result.manifest)


class ManifestErrorCodeTests(unittest.TestCase):
    def _first_error_code(self, payload: object, files: object = frozenset()) -> str:
        result = validate_manifest(payload, files=files)
        self.assertFalse(result.ok)
        errors = [issue for issue in result.issues if issue.severity == "error"]
        self.assertTrue(errors, "expected at least one error issue")
        return errors[0].code

    def test_a_non_object_payload_is_rejected(self) -> None:
        self.assertEqual(self._first_error_code("not a manifest"), "MANIFEST_SCHEMA")
        self.assertEqual(self._first_error_code(None), "MANIFEST_SCHEMA")

    def test_manifest_event_errors(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(event="own_goal"), files={"goal.webm"}),
            "MANIFEST_EVENT",
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(event=None), files={"goal.webm"}), "MANIFEST_EVENT"
        )

    def test_manifest_duration_out_of_range_is_a_warning_and_clamps(self) -> None:
        low = validate_manifest(_good_manifest(duration_seconds=0.5), files={"goal.webm"})
        self.assertTrue(low.ok)
        self.assertEqual(low.manifest["duration_seconds"], MIN_DURATION_SECONDS)
        self.assertEqual(low.issues[0].code, "DURATION_CLAMPED")

        high = validate_manifest(_good_manifest(duration_seconds=999), files={"goal.webm"})
        self.assertEqual(high.manifest["duration_seconds"], MAX_DURATION_SECONDS)

    def test_manifest_intro_errors_and_default(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(intro="fade"), files={"goal.webm"}), "MANIFEST_INTRO"
        )
        payload = _good_manifest()
        del payload["intro"]
        result = validate_manifest(payload, files={"goal.webm"})
        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["intro"], "none")

    def test_manifest_builtin_scene_id_must_be_a_known_builtin(self) -> None:
        self.assertEqual(
            self._first_error_code(
                _good_manifest(scene={"type": "builtin", "id": "own_goal"}), files={"goal.webm"}
            ),
            "MANIFEST_SCENE",
        )

    def test_manifest_media_src_rejects_separators_and_dotdot(self) -> None:
        for bad_src in ("../evil.webm", "sub/dir.webm", "", None):
            with self.subTest(bad_src=bad_src):
                payload = _good_manifest(scene={"type": "video", "src": bad_src, "fit": "cover"})
                self.assertEqual(self._first_error_code(payload, files={"goal.webm"}), "MANIFEST_MEDIA")

    def test_manifest_media_file_must_be_present_in_the_pack_folder(self) -> None:
        payload = _good_manifest(scene={"type": "video", "src": "missing.webm", "fit": "cover"})
        self.assertEqual(self._first_error_code(payload, files=set()), "MANIFEST_MEDIA")


class BuiltinPackTests(unittest.TestCase):
    def test_builtin_pack_shape_for_every_event(self) -> None:
        for event in SOCCER_CUTSCENE_EVENTS:
            with self.subTest(event=event):
                pack = builtin_pack(event)
                self.assertEqual(
                    set(pack),
                    {"id", "name", "event", "builtin", "duration_seconds", "intro", "scene", "folder", "media_url"},
                )
                self.assertEqual(pack["id"], builtin_pack_id(event))
                self.assertTrue(pack["builtin"])
                self.assertEqual(pack["duration_seconds"], DEFAULT_DURATION_SECONDS[event])
                self.assertEqual(pack["intro"], EVENT_DEFAULT_INTRO[event])
                self.assertEqual(pack["scene"], {"type": "builtin", "id": BUILTIN_SCENE_IDS[event]})
                self.assertIsNone(pack["folder"])
                self.assertIsNone(pack["media_url"])

    def test_normalize_pack_carries_folder_and_media_url(self) -> None:
        manifest = validate_manifest(_good_manifest(), files={"goal.webm"}).manifest
        pack = normalize_pack("my_pack", manifest, folder="/tmp/my_pack", media_url="file:///tmp/my_pack/goal.webm")

        self.assertEqual(pack["id"], "my_pack")
        self.assertFalse(pack["builtin"])
        self.assertEqual(pack["media_url"], "file:///tmp/my_pack/goal.webm")


class BuildProgramTests(unittest.TestCase):
    def _layout(self) -> dict:
        return {"schema_version": 3, "name": "Broadcast bar", "widgets": {"quarter": {}}, "screens": {}}

    def test_shape_matches_the_football_program_keys(self) -> None:
        pack = builtin_pack("goal")
        view = {"teams": {"home": {"name": "Eagles", "score": 1}, "away": {"name": "Hawks", "score": 0}}}

        program = build_program(
            play_id=3, event="goal", pack=pack, spectator_view=view, layout=self._layout(), team="home",
        )

        self.assertEqual(
            set(program),
            {
                "schema_version", "play_id", "event", "label", "team", "pack_id", "duration_ms",
                "intro", "outro_ms", "stage", "layout", "scene", "theme", "texts",
            },
        )
        self.assertEqual(program["schema_version"], MANIFEST_SCHEMA_VERSION)
        self.assertEqual(program["play_id"], 3)
        self.assertEqual(program["event"], "goal")
        self.assertEqual(program["label"], "Goal")
        self.assertEqual(program["team"], "home")
        self.assertEqual(program["pack_id"], "builtin:goal")
        self.assertEqual(program["duration_ms"], 7000)
        self.assertEqual(program["intro"], {"id": "none", "duration_ms": 0})
        self.assertEqual(program["outro_ms"], SOCCER_OUTRO_DURATION_MS)
        self.assertEqual(program["outro_ms"], 600)
        self.assertEqual(program["stage"], STAGE)
        self.assertEqual(program["scene"], {"type": "builtin", "id": "goal"})
        self.assertEqual(
            program["texts"], {"headline": "GOAL", "subline": "EAGLES", "team_name": "Eagles"}
        )
        self.assertEqual(program["layout"]["name"], "Cutscene")

    def test_team_is_required_and_keyword_only(self) -> None:
        with self.assertRaises(TypeError):
            build_program(  # type: ignore[call-arg]
                play_id=1, event="goal", pack=builtin_pack("goal"),
                spectator_view={}, layout=self._layout(),
            )
        with self.assertRaises(TypeError):
            build_program(  # type: ignore[misc]
                1, "goal", builtin_pack("goal"), {}, self._layout(), None, "home",
            )

    def test_away_team_reads_the_away_name_and_never_says_home(self) -> None:
        view = {"teams": {"home": {"name": "Eagles"}, "away": {"name": "Hawks"}}}

        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view=view, layout=self._layout(), team="away",
        )

        self.assertEqual(program["team"], "away")
        self.assertEqual(program["texts"]["team_name"], "Hawks")
        self.assertEqual(program["texts"]["subline"], "HAWKS")
        self.assertNotIn("EAGLES", program["texts"].values())

    def test_missing_view_never_raises_and_uses_empty_text(self) -> None:
        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view={}, layout=self._layout(), team="home",
        )

        self.assertEqual(program["texts"]["team_name"], "")
        self.assertEqual(program["texts"]["subline"], "")

    def test_an_unrecognised_team_falls_back_to_home_rather_than_raising(self) -> None:
        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view={}, layout=self._layout(), team="referee",
        )

        self.assertEqual(program["team"], "home")

    def test_theme_carries_the_fixed_navy_red_fallback_by_default(self) -> None:
        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view={}, layout=self._layout(), team="home",
        )

        self.assertEqual(program["theme"]["home_primary"], FALLBACK_HOME_PRIMARY)
        self.assertEqual(program["theme"]["away_primary"], FALLBACK_AWAY_PRIMARY)
        for key in THEME:
            self.assertEqual(program["theme"][key], THEME[key])

    def test_theme_prefers_the_saved_team_identity_when_present(self) -> None:
        view = {
            "teams": {
                "home": {"name": "Eagles", "primary": "#00AACC"},
                "away": {"name": "Hawks", "primary": "#DD1144"},
            }
        }

        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view=view, layout=self._layout(), team="home",
        )

        self.assertEqual(program["theme"]["home_primary"], "#00AACC")
        self.assertEqual(program["theme"]["away_primary"], "#DD1144")

    def test_layout_is_deep_copied_and_renamed_not_mutated(self) -> None:
        original_layout = self._layout()

        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view={}, layout=original_layout, team="home",
        )
        program["layout"]["widgets"]["quarter"]["mutated"] = True

        self.assertEqual(original_layout["name"], "Broadcast bar")
        self.assertNotIn("mutated", original_layout["widgets"]["quarter"])

    def test_neither_layout_input_is_mutated_with_a_board_layout(self) -> None:
        geometry_layout = self._layout()
        board_layout = {
            "schema_version": 3, "name": "Grid",
            "widgets": {"quarter": {"color": "#FFB703", "font_family": "varsity"}},
            "screens": {},
        }
        geometry_copy = copy.deepcopy(geometry_layout)
        board_copy = copy.deepcopy(board_layout)

        program = build_program(
            play_id=1, event="goal", pack=builtin_pack("goal"),
            spectator_view={}, layout=geometry_layout, board_layout=board_layout, team="home",
        )

        self.assertEqual(geometry_layout, geometry_copy)
        self.assertEqual(board_layout, board_copy)
        self.assertEqual(program["layout"]["widgets"]["quarter"]["color"], "#FFB703")
        self.assertTrue(program["layout"]["widgets"]["quarter"]["fit_text"])

    def test_media_pack_scene_carries_a_builtin_fallback(self) -> None:
        pack = {
            "id": "my_pack", "name": "Custom", "event": "goal", "builtin": False,
            "duration_seconds": 7.0, "intro": "none",
            "scene": {"type": "video", "src": "goal.webm", "fit": "cover", "loop": False},
            "folder": "/tmp/my_pack", "media_url": "file:///tmp/my_pack/goal.webm",
        }

        program = build_program(
            play_id=1, event="goal", pack=pack, spectator_view={}, layout=self._layout(), team="home",
        )

        self.assertEqual(
            program["scene"],
            {
                "type": "video", "src": "file:///tmp/my_pack/goal.webm", "fit": "cover",
                "loop": False, "fallback": {"type": "builtin", "id": "goal"},
            },
        )


class EventDescriptorTests(unittest.TestCase):
    def test_one_descriptor_per_event_in_order(self) -> None:
        descriptors = event_descriptors()

        self.assertEqual([d["id"] for d in descriptors], list(SOCCER_CUTSCENE_EVENTS))
        for descriptor in descriptors:
            event = descriptor["id"]
            self.assertEqual(descriptor["label"], EVENT_LABELS[event])
            self.assertEqual(descriptor["headline"], EVENT_HEADLINES[event])
            self.assertEqual(descriptor["default_duration_seconds"], DEFAULT_DURATION_SECONDS[event])
            self.assertEqual(descriptor["builtin_pack_id"], builtin_pack_id(event))
            # Unlike football's descriptors, there is no fixed "team" here --
            # a GOAL's side is a runtime choice, never a property of the event.
            self.assertNotIn("team", descriptor)


class ConstantSanityTests(unittest.TestCase):
    def test_events_and_reused_football_constants(self) -> None:
        self.assertEqual(SOCCER_CUTSCENE_EVENTS, ("goal",))
        self.assertEqual(SCENE_TYPES, ("builtin", "video", "image"))
        self.assertEqual(FIT_MODES, ("cover", "contain"))
        self.assertEqual(MANIFEST_SCHEMA_VERSION, 1)
        self.assertEqual(SOCCER_OUTRO_DURATION_MS, 600)
        self.assertEqual(MIN_DURATION_SECONDS, 2.0)
        self.assertEqual(MAX_DURATION_SECONDS, 30.0)
        self.assertEqual(STAGE, {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.70})
        self.assertIn("claw_scratch", INTRO_IDS)
        self.assertIn("none", INTRO_IDS)
        self.assertEqual(
            MEDIA_EXTENSIONS,
            {"video": (".webm", ".mp4"), "image": (".png", ".gif", ".jpg", ".jpeg", ".webp", ".apng")},
        )

    def test_per_event_tables_cover_exactly_the_events(self) -> None:
        for table_name, table in (
            ("EVENT_LABELS", EVENT_LABELS),
            ("EVENT_HEADLINES", EVENT_HEADLINES),
            ("EVENT_DEFAULT_INTRO", EVENT_DEFAULT_INTRO),
            ("DEFAULT_DURATION_SECONDS", DEFAULT_DURATION_SECONDS),
            ("BUILTIN_SCENE_IDS", BUILTIN_SCENE_IDS),
        ):
            with self.subTest(table=table_name):
                self.assertEqual(tuple(table), SOCCER_CUTSCENE_EVENTS)

    def test_the_goal_values_other_agents_hard_code(self) -> None:
        self.assertEqual(EVENT_HEADLINES["goal"], "GOAL")
        self.assertEqual(DEFAULT_DURATION_SECONDS["goal"], 7.0)
        self.assertEqual(EVENT_DEFAULT_INTRO["goal"], "none")
        self.assertEqual(INTRO_DURATION_MS.get("none"), 0)
        self.assertEqual(BUILTIN_SCENE_IDS["goal"], "goal")
        self.assertEqual(FALLBACK_HOME_PRIMARY, "#08439A")
        self.assertEqual(FALLBACK_AWAY_PRIMARY, "#A50021")

    def test_there_is_no_fixed_event_team_table(self) -> None:
        # Football's EVENT_TEAM/CUTSCENE_TEAM_NAME are a football-only
        # concept -- a GOAL's side is always a runtime argument.
        import scoreboard.presentation.soccer_cutscenes as module

        self.assertFalse(hasattr(module, "EVENT_TEAM"))
        self.assertFalse(hasattr(module, "CUTSCENE_TEAM_NAME"))


class BuiltinSceneRegistryMirrorTests(unittest.TestCase):
    """Mirrors football's cross-language contract test: the soccer scene
    registry must register a factory for every soccer built-in scene id,
    scanning only ``views/soccer_spectator/cutscenes/`` -- never football's
    frozen ``views/spectator/cutscenes/`` folder, so that folder's own
    "exactly five football ids" contract test stays untouched.
    """

    def _registrations(self) -> str:
        folder = (
            Path(__file__).resolve().parents[2]
            / "src" / "scoreboard" / "views" / "soccer_spectator" / "cutscenes"
        )
        self.assertTrue(folder.is_dir(), f"expected {folder} to exist")
        scene_files = sorted(folder.glob("*.js"))
        self.assertTrue(scene_files, f"expected at least one scene file under {folder}")
        return "\n".join(path.read_text(encoding="utf-8") for path in scene_files)

    def test_the_scene_files_register_every_soccer_scene_id(self) -> None:
        text = self._registrations()

        self.assertEqual(len(BUILTIN_SCENE_IDS), 1)
        for scene_id in BUILTIN_SCENE_IDS.values():
            with self.subTest(scene_id=scene_id):
                self.assertIn(f"register('{scene_id}'", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
