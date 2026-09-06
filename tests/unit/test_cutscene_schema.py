"""The cutscene schema: pack-manifest validation and the program it builds.

Two rules run through every test here, the same ones ``test_layout_schema.py``
pins for the presentation layout. **Nothing invalid is accepted quietly** --
an unknown event, a media file not actually in the pack folder, or an
out-of-range duration produces an explicit, coded issue. And **nothing
invalid can crash a trigger** -- :func:`validate_manifest` always returns a
usable, normalized manifest, and :func:`build_program` never raises even
when the spectator view is empty or a team's identity is missing.

This module is pure: no file I/O, no clock, no window. The "does a real pack
folder scan correctly" behavior lives in
``tests/integration/test_cutscene_packs.py``; the "does playback state
advance correctly" behavior lives in
``tests/integration/test_cutscene_director.py``.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scoreboard.presentation.cutscenes import (
    BUILTIN_PACK_PREFIX,
    BUILTIN_SCENE_IDS,
    CUTSCENE_EVENTS,
    DEFAULT_DURATION_SECONDS,
    EVENT_DEFAULT_TEAM,
    EVENT_HEADLINES,
    EVENT_LABELS,
    FIT_MODES,
    INTRO_DURATION_MS,
    INTRO_IDS,
    MANIFEST_SCHEMA_VERSION,
    MAX_DURATION_SECONDS,
    MEDIA_EXTENSIONS,
    MIN_DURATION_SECONDS,
    OUTRO_DURATION_MS,
    SCENE_TYPES,
    STAGE,
    TEAM_SIDES,
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
        "name": "Touchdown -- roar",
        "event": "touchdown",
        "duration_seconds": 10,
        "intro": "claw_scratch",
        "scene": {"type": "video", "src": "touchdown.webm", "fit": "cover", "loop": False},
    }
    manifest.update(overrides)
    return manifest


class ValidManifestTests(unittest.TestCase):
    def test_a_complete_valid_manifest_normalizes_with_every_field_filled(self) -> None:
        result = validate_manifest(_good_manifest(), files={"touchdown.webm"})

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())
        self.assertEqual(
            result.manifest,
            {
                "schema_version": 1,
                "name": "Touchdown -- roar",
                "event": "touchdown",
                "duration_seconds": 10,
                "intro": "claw_scratch",
                "scene": {"type": "video", "src": "touchdown.webm", "fit": "cover", "loop": False},
            },
        )

    def test_missing_optional_fields_take_the_documented_defaults(self) -> None:
        payload = {
            "schema_version": 1,
            "name": "Minimal",
            "event": "first_down",
            "scene": {"type": "builtin", "id": "first_down"},
        }

        result = validate_manifest(payload, files=set())

        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["duration_seconds"], DEFAULT_DURATION_SECONDS["first_down"])
        self.assertEqual(result.manifest["intro"], "claw_scratch")
        self.assertEqual(result.manifest["scene"], {"type": "builtin", "id": "first_down"})

    def test_unknown_top_level_keys_are_ignored_without_a_warning(self) -> None:
        payload = _good_manifest(future_field="something new")

        result = validate_manifest(payload, files={"touchdown.webm"})

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())
        self.assertNotIn("future_field", result.manifest)

    def test_an_image_scene_never_carries_a_loop_key(self) -> None:
        payload = _good_manifest(
            scene={"type": "image", "src": "poster.png", "fit": "contain"}
        )

        result = validate_manifest(payload, files={"poster.png"})

        self.assertTrue(result.ok)
        self.assertNotIn("loop", result.manifest["scene"])


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
        self.assertEqual(self._first_error_code([1, 2, 3]), "MANIFEST_SCHEMA")

    def test_manifest_schema_wrong_version(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(schema_version=2), files={"touchdown.webm"}),
            "MANIFEST_SCHEMA",
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(schema_version=None), files={"touchdown.webm"}),
            "MANIFEST_SCHEMA",
        )

    def test_manifest_name_errors(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(name=""), files={"touchdown.webm"}), "MANIFEST_NAME"
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(name="   "), files={"touchdown.webm"}), "MANIFEST_NAME"
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(name="x" * 65), files={"touchdown.webm"}),
            "MANIFEST_NAME",
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(name=42), files={"touchdown.webm"}), "MANIFEST_NAME"
        )

    def test_manifest_name_accepts_exactly_64_characters_after_strip(self) -> None:
        result = validate_manifest(
            _good_manifest(name=" " + "x" * 64 + " "), files={"touchdown.webm"}
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["name"], "x" * 64)

    def test_manifest_event_errors(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(event="field_goal"), files={"touchdown.webm"}),
            "MANIFEST_EVENT",
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(event=None), files={"touchdown.webm"}),
            "MANIFEST_EVENT",
        )

    def test_manifest_duration_non_number_is_an_error(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(duration_seconds="ten"), files={"touchdown.webm"}),
            "MANIFEST_DURATION",
        )
        self.assertEqual(
            self._first_error_code(_good_manifest(duration_seconds=True), files={"touchdown.webm"}),
            "MANIFEST_DURATION",
        )

    def test_manifest_duration_out_of_range_is_a_warning_and_clamps(self) -> None:
        low = validate_manifest(_good_manifest(duration_seconds=0.5), files={"touchdown.webm"})
        self.assertTrue(low.ok)
        self.assertEqual(low.manifest["duration_seconds"], MIN_DURATION_SECONDS)
        self.assertEqual(low.issues[0].code, "DURATION_CLAMPED")
        self.assertEqual(low.issues[0].severity, "warning")

        high = validate_manifest(_good_manifest(duration_seconds=999), files={"touchdown.webm"})
        self.assertTrue(high.ok)
        self.assertEqual(high.manifest["duration_seconds"], MAX_DURATION_SECONDS)
        self.assertEqual(high.issues[0].code, "DURATION_CLAMPED")

    def test_manifest_duration_missing_uses_the_event_default(self) -> None:
        payload = _good_manifest()
        del payload["duration_seconds"]

        result = validate_manifest(payload, files={"touchdown.webm"})

        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["duration_seconds"], DEFAULT_DURATION_SECONDS["touchdown"])

    def test_manifest_intro_errors_and_default(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(intro="fade"), files={"touchdown.webm"}),
            "MANIFEST_INTRO",
        )
        payload = _good_manifest()
        del payload["intro"]
        result = validate_manifest(payload, files={"touchdown.webm"})
        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["intro"], "claw_scratch")

    def test_manifest_scene_must_be_an_object(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(scene="video"), files={"touchdown.webm"}),
            "MANIFEST_SCENE",
        )

    def test_manifest_scene_type_must_be_known(self) -> None:
        self.assertEqual(
            self._first_error_code(_good_manifest(scene={"type": "audio"}), files={"touchdown.webm"}),
            "MANIFEST_SCENE",
        )

    def test_manifest_builtin_scene_id_must_be_a_known_builtin(self) -> None:
        self.assertEqual(
            self._first_error_code(
                _good_manifest(scene={"type": "builtin", "id": "field_goal"}),
                files={"touchdown.webm"},
            ),
            "MANIFEST_SCENE",
        )

    def test_manifest_media_src_rejects_separators_and_dotdot(self) -> None:
        for bad_src in ("../evil.webm", "sub/dir.webm", "sub\\dir.webm", "", 5, None):
            with self.subTest(bad_src=bad_src):
                payload = _good_manifest(scene={"type": "video", "src": bad_src, "fit": "cover"})
                self.assertEqual(self._first_error_code(payload, files={"touchdown.webm"}), "MANIFEST_MEDIA")

    def test_manifest_media_extension_must_match_the_scene_type(self) -> None:
        payload = _good_manifest(scene={"type": "video", "src": "touchdown.png", "fit": "cover"})
        self.assertEqual(self._first_error_code(payload, files={"touchdown.png"}), "MANIFEST_MEDIA")

    def test_manifest_media_extension_check_is_case_insensitive(self) -> None:
        payload = _good_manifest(scene={"type": "video", "src": "touchdown.WEBM", "fit": "cover"})
        result = validate_manifest(payload, files={"touchdown.WEBM"})
        self.assertTrue(result.ok)

    def test_manifest_media_file_must_be_present_in_the_pack_folder(self) -> None:
        payload = _good_manifest(scene={"type": "video", "src": "missing.webm", "fit": "cover"})
        self.assertEqual(self._first_error_code(payload, files=set()), "MANIFEST_MEDIA")

    def test_manifest_scene_fit_defaults_and_rejects_bad_values(self) -> None:
        payload = _good_manifest(scene={"type": "video", "src": "touchdown.webm"})
        result = validate_manifest(payload, files={"touchdown.webm"})
        self.assertTrue(result.ok)
        self.assertEqual(result.manifest["scene"]["fit"], "cover")

        bad = _good_manifest(scene={"type": "video", "src": "touchdown.webm", "fit": "zoom"})
        bad_result = validate_manifest(bad, files={"touchdown.webm"})
        # An unrecognized fit is an error, same as an unrecognized
        # text_align in the presentation layout -- but the normalized
        # manifest still substitutes the default rather than discarding the
        # rest of an otherwise-usable media scene.
        self.assertFalse(bad_result.ok)
        self.assertEqual(bad_result.manifest["scene"]["fit"], "cover")

    def test_manifest_scene_loop_defaults_false_and_must_be_boolean(self) -> None:
        payload = _good_manifest(scene={"type": "video", "src": "touchdown.webm"})
        result = validate_manifest(payload, files={"touchdown.webm"})
        self.assertFalse(result.manifest["scene"]["loop"])

        bad = _good_manifest(scene={"type": "video", "src": "touchdown.webm", "loop": "yes"})
        bad_result = validate_manifest(bad, files={"touchdown.webm"})
        self.assertFalse(bad_result.ok)
        self.assertFalse(bad_result.manifest["scene"]["loop"])


class BuiltinPackTests(unittest.TestCase):
    def test_builtin_pack_shape_for_every_event(self) -> None:
        for event in CUTSCENE_EVENTS:
            with self.subTest(event=event):
                pack = builtin_pack(event)
                self.assertEqual(
                    set(pack),
                    {"id", "name", "event", "builtin", "duration_seconds", "intro", "scene", "folder", "media_url"},
                )
                self.assertEqual(pack["id"], f"{BUILTIN_PACK_PREFIX}{event}")
                self.assertEqual(pack["id"], builtin_pack_id(event))
                self.assertTrue(pack["builtin"])
                self.assertEqual(pack["event"], event)
                self.assertEqual(pack["duration_seconds"], DEFAULT_DURATION_SECONDS[event])
                self.assertEqual(pack["intro"], "claw_scratch")
                self.assertEqual(pack["scene"], {"type": "builtin", "id": BUILTIN_SCENE_IDS[event]})
                self.assertIsNone(pack["folder"])
                self.assertIsNone(pack["media_url"])

    def test_normalize_pack_carries_folder_and_media_url(self) -> None:
        manifest = validate_manifest(
            _good_manifest(), files={"touchdown.webm"}
        ).manifest
        pack = normalize_pack("my_pack", manifest, folder="/tmp/my_pack", media_url="file:///tmp/my_pack/touchdown.webm")

        self.assertEqual(pack["id"], "my_pack")
        self.assertFalse(pack["builtin"])
        self.assertEqual(pack["folder"], "/tmp/my_pack")
        self.assertEqual(pack["media_url"], "file:///tmp/my_pack/touchdown.webm")
        self.assertEqual(pack["name"], manifest["name"])
        self.assertEqual(pack["scene"], manifest["scene"])


class BuildProgramTests(unittest.TestCase):
    def _layout(self) -> dict:
        return {"schema_version": 3, "name": "Broadcast bar", "widgets": {"quarter": {}}, "screens": {}}

    def test_shape_matches_the_spec_example_for_a_builtin_touchdown(self) -> None:
        pack = builtin_pack("touchdown")
        view = {
            "teams": {"home": {"name": "Tigers", "score": 14}},
            "football": {"possession": "home"},
        }

        program = build_program(
            play_id=3, event="touchdown", pack=pack, team="home",
            spectator_view=view, layout=self._layout(),
        )

        self.assertEqual(program["schema_version"], MANIFEST_SCHEMA_VERSION)
        self.assertEqual(program["play_id"], 3)
        self.assertEqual(program["event"], "touchdown")
        self.assertEqual(program["label"], "Touchdown")
        self.assertEqual(program["team"], "home")
        self.assertEqual(program["pack_id"], "builtin:touchdown")
        self.assertEqual(program["duration_ms"], 10000)
        self.assertEqual(program["intro"], {"id": "claw_scratch", "duration_ms": 1400})
        self.assertEqual(program["outro_ms"], OUTRO_DURATION_MS)
        self.assertEqual(program["stage"], STAGE)
        self.assertEqual(program["scene"], {"type": "builtin", "id": "touchdown"})
        self.assertEqual(program["theme"], THEME)
        self.assertEqual(
            program["texts"],
            {"headline": "TOUCHDOWN", "subline": "TIGERS", "team_name": "Tigers", "score": "14"},
        )
        self.assertEqual(program["layout"]["name"], "Cutscene")

    def test_intro_and_outro_are_inside_duration_never_added(self) -> None:
        pack = builtin_pack("first_down")
        program = build_program(
            play_id=1, event="first_down", pack=pack, team="home",
            spectator_view={}, layout=self._layout(),
        )

        self.assertEqual(program["duration_ms"], round(DEFAULT_DURATION_SECONDS["first_down"] * 1000))
        self.assertLessEqual(program["intro"]["duration_ms"], program["duration_ms"])
        self.assertLessEqual(program["outro_ms"], program["duration_ms"])

    def test_layout_is_deep_copied_and_renamed_not_mutated(self) -> None:
        original_layout = self._layout()
        pack = builtin_pack("touchdown")

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team="home",
            spectator_view={}, layout=original_layout,
        )
        program["layout"]["widgets"]["quarter"]["mutated"] = True

        self.assertEqual(original_layout["name"], "Broadcast bar")
        self.assertNotIn("mutated", original_layout["widgets"]["quarter"])

    def test_team_none_resolves_through_possession_for_first_down(self) -> None:
        pack = builtin_pack("first_down")
        view = {
            "teams": {"away": {"name": "Hawks", "score": 7}},
            "football": {"possession": "away"},
        }

        program = build_program(
            play_id=1, event="first_down", pack=pack, team=None,
            spectator_view=view, layout=self._layout(),
        )

        self.assertEqual(program["team"], "away")
        self.assertEqual(program["texts"]["team_name"], "Hawks")

    def test_team_none_falls_back_to_home_when_possession_is_absent_or_none(self) -> None:
        pack = builtin_pack("first_down")

        program_absent = build_program(
            play_id=1, event="first_down", pack=pack, team=None,
            spectator_view={}, layout=self._layout(),
        )
        self.assertEqual(program_absent["team"], "home")

        program_none = build_program(
            play_id=1, event="first_down", pack=pack, team=None,
            spectator_view={"football": {"possession": None}}, layout=self._layout(),
        )
        self.assertEqual(program_none["team"], "home")

    def test_team_none_for_touchdown_always_defaults_to_home(self) -> None:
        pack = builtin_pack("touchdown")
        view = {"football": {"possession": "away"}}

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team=None,
            spectator_view=view, layout=self._layout(),
        )

        self.assertEqual(program["team"], "home")

    def test_explicit_team_overrides_the_default(self) -> None:
        pack = builtin_pack("touchdown")

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team="away",
            spectator_view={"football": {"possession": "home"}}, layout=self._layout(),
        )

        self.assertEqual(program["team"], "away")

    def test_empty_team_name_is_used_as_given_not_substituted(self) -> None:
        pack = builtin_pack("touchdown")
        view = {"teams": {"home": {"name": "", "score": 0}}}

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team="home",
            spectator_view=view, layout=self._layout(),
        )

        self.assertEqual(program["texts"]["team_name"], "")
        self.assertEqual(program["texts"]["subline"], "")
        self.assertNotIn("TIGERS", program["texts"].values())

    def test_missing_view_never_raises_and_uses_safe_defaults(self) -> None:
        pack = builtin_pack("touchdown")

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team=None,
            spectator_view={}, layout=self._layout(),
        )

        self.assertEqual(program["team"], "home")
        self.assertEqual(program["texts"]["team_name"], "")
        self.assertEqual(program["texts"]["score"], "0")

    def test_media_pack_scene_carries_a_builtin_fallback(self) -> None:
        pack = {
            "id": "my_pack", "name": "Custom", "event": "touchdown", "builtin": False,
            "duration_seconds": 10.0, "intro": "claw_scratch",
            "scene": {"type": "video", "src": "touchdown.webm", "fit": "cover", "loop": False},
            "folder": "/tmp/my_pack", "media_url": "file:///tmp/my_pack/touchdown.webm",
        }

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team="home",
            spectator_view={}, layout=self._layout(),
        )

        self.assertEqual(
            program["scene"],
            {
                "type": "video",
                "src": "file:///tmp/my_pack/touchdown.webm",
                "fit": "cover",
                "loop": False,
                "fallback": {"type": "builtin", "id": "touchdown"},
            },
        )

    def test_image_media_scene_omits_loop(self) -> None:
        pack = {
            "id": "my_pack", "name": "Custom", "event": "touchdown", "builtin": False,
            "duration_seconds": 10.0, "intro": "claw_scratch",
            "scene": {"type": "image", "src": "poster.png", "fit": "contain"},
            "folder": "/tmp/my_pack", "media_url": "file:///tmp/my_pack/poster.png",
        }

        program = build_program(
            play_id=1, event="touchdown", pack=pack, team="home",
            spectator_view={}, layout=self._layout(),
        )

        self.assertNotIn("loop", program["scene"])
        self.assertEqual(program["scene"]["type"], "image")
        self.assertEqual(program["scene"]["fallback"], {"type": "builtin", "id": "touchdown"})


class EventDescriptorTests(unittest.TestCase):
    def test_one_descriptor_per_event_in_order(self) -> None:
        descriptors = event_descriptors()

        self.assertEqual([d["id"] for d in descriptors], list(CUTSCENE_EVENTS))
        for descriptor in descriptors:
            event = descriptor["id"]
            self.assertEqual(descriptor["label"], EVENT_LABELS[event])
            self.assertEqual(descriptor["headline"], EVENT_HEADLINES[event])
            self.assertEqual(descriptor["default_team"], EVENT_DEFAULT_TEAM[event])
            self.assertEqual(descriptor["default_duration_seconds"], DEFAULT_DURATION_SECONDS[event])
            self.assertEqual(descriptor["builtin_pack_id"], builtin_pack_id(event))


class ConstantSanityTests(unittest.TestCase):
    """A light net over the exact-name/value contract other agents build on."""

    def test_events_and_sides(self) -> None:
        self.assertEqual(CUTSCENE_EVENTS, ("first_down", "touchdown"))
        self.assertEqual(TEAM_SIDES, ("home", "away"))
        self.assertEqual(INTRO_IDS, ("claw_scratch", "none"))
        self.assertEqual(SCENE_TYPES, ("builtin", "video", "image"))
        self.assertEqual(FIT_MODES, ("cover", "contain"))
        self.assertEqual(BUILTIN_PACK_PREFIX, "builtin:")
        self.assertEqual(MANIFEST_SCHEMA_VERSION, 1)
        self.assertEqual(OUTRO_DURATION_MS, 600)
        self.assertEqual(MIN_DURATION_SECONDS, 2.0)
        self.assertEqual(MAX_DURATION_SECONDS, 30.0)
        self.assertEqual(STAGE, {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.70})
        self.assertEqual(INTRO_DURATION_MS, {"claw_scratch": 1400, "none": 0})
        self.assertEqual(
            MEDIA_EXTENSIONS,
            {"video": (".webm", ".mp4"), "image": (".png", ".gif", ".jpg", ".jpeg", ".webp", ".apng")},
        )


class BuiltinSceneRegistryMirrorTests(unittest.TestCase):
    """Mirrors spec section 2.6's cross-language contract test: the
    JavaScript scene registry must register a factory for the intro and for
    every built-in scene id this module defines, using the exact literal
    string Python already committed to. A grep, not a JS interpreter --
    this file has no JavaScript runtime available to it.
    """

    def test_builtin_js_registers_the_intro_and_every_scene_id(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src" / "scoreboard" / "views" / "spectator" / "cutscenes" / "builtin.js"
        )
        self.assertTrue(path.is_file(), f"expected {path} to exist")
        text = path.read_text(encoding="utf-8")

        self.assertIn("register('claw_scratch'", text)
        for scene_id in BUILTIN_SCENE_IDS.values():
            with self.subTest(scene_id=scene_id):
                self.assertIn(f"register('{scene_id}'", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
