"""Mirrors ``tests/unit/test_layout_schema.py`` for
``scoreboard.presentation.soccer_layout`` (spec section 5.1/5.2, D-owned).

Also the Python<->JS mirror test for ``views/shared/board.js``'s new
``SOCCER_*`` literals (spec section 2.3), following the same pattern
``tests/integration/test_spectator_layout_render.py`` uses for football's.
"""
from __future__ import annotations

import unittest

from scoreboard.presentation import layout as football_layout
from scoreboard.presentation import soccer_layout as sl
from tests.integration.test_spectator_layout_render import BOARD_JS, _extract_js_literal


class SoccerWidgetRegistryTests(unittest.TestCase):
    def test_widget_ids_are_a_fresh_tuple_disjoint_in_spelling_from_footballs_own(self):
        self.assertEqual(len(sl.SOCCER_WIDGET_IDS), len(set(sl.SOCCER_WIDGET_IDS)))
        self.assertEqual(len(sl.SOCCER_WIDGET_IDS), 23)

    def test_every_widget_has_a_label_field_entry_and_group(self):
        for widget_id in sl.SOCCER_WIDGET_IDS:
            self.assertIn(widget_id, sl.SOCCER_WIDGET_LABELS)
            self.assertIn(widget_id, sl.SOCCER_WIDGET_FIELDS)
            self.assertIn(widget_id, sl.SOCCER_WIDGET_GROUPS)
            self.assertIn(sl.SOCCER_WIDGET_GROUPS[widget_id], sl.SOCCER_WIDGET_GROUP_ORDER)

    def test_optional_widget_ids_are_a_subset(self):
        self.assertTrue(sl.SOCCER_OPTIONAL_WIDGET_IDS.issubset(set(sl.SOCCER_WIDGET_IDS)))

    def test_final_hidden_widget_ids_are_only_the_game_clock(self):
        self.assertEqual(sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS, ("game_clock_label", "game_clock_value"))
        self.assertTrue(set(sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS).issubset(sl.SOCCER_WIDGET_IDS))
        self.assertEqual(sl.hidden_element_prefixes(), sl.SOCCER_FINAL_HIDDEN_ELEMENT_PREFIXES)

    def test_period_offers_a_standard_and_short_format(self):
        self.assertIn("period", sl.SOCCER_WIDGET_FORMAT_FIELDS)
        self.assertEqual(sl.SOCCER_WIDGET_FORMAT_FIELDS["period"], {"short": "period_display_short"})
        formats = [d for d in sl.soccer_widget_descriptors() if d["id"] == "period"][0]["formats"]
        self.assertEqual([f["id"] for f in formats], ["default", "short"])


class DefaultSoccerLayoutTests(unittest.TestCase):
    def test_default_layout_is_soccer_grid_and_validates_clean(self):
        layout = sl.default_soccer_layout()
        self.assertEqual(layout["name"], "Default")
        result = sl.validate_soccer_layout(layout)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, ())

    def test_default_layout_always_visible_widgets_are_pairwise_disjoint(self):
        layout = sl.default_soccer_layout()
        visible = [
            (wid, w) for wid, w in layout["widgets"].items() if w["visible"]
        ]

        def overlap(a, b):
            ax0, ay0 = a["x"], a["y"]
            ax1, ay1 = ax0 + a["width"], ay0 + a["height"]
            bx0, by0 = b["x"], b["y"]
            bx1, by1 = bx0 + b["width"], by0 + b["height"]
            ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
            iy = max(0.0, min(ay1, by1) - max(ay0, by0))
            return ix * iy > 0.0

        for i, (id_a, a) in enumerate(visible):
            for id_b, b in visible[i + 1:]:
                self.assertFalse(overlap(a, b), f"{id_a} overlaps {id_b}")

    def test_default_layout_pregame_and_halftime_reuse_footballs_event_registry(self):
        layout = sl.default_soccer_layout()
        for screen_id in ("pregame", "halftime"):
            screen = layout["screens"][screen_id]
            self.assertEqual(set(screen["widgets"]), set(football_layout.EVENT_WIDGET_IDS))
            result = football_layout._validate_screen(screen, screen_id)
            self.assertEqual(result[1], [], result[1])  # no errors

    def test_reset_and_default_widget_agree(self):
        for widget_id in sl.SOCCER_WIDGET_IDS:
            layout = sl.default_soccer_layout()
            layout["widgets"][widget_id]["x"] = 0.999
            reset = sl.reset_soccer_widget(layout, widget_id)
            self.assertEqual(reset["widgets"][widget_id], sl.default_soccer_widget(widget_id))


class ValidateSoccerLayoutTests(unittest.TestCase):
    def test_rejects_non_object(self):
        result = sl.validate_soccer_layout("nope")
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0].code, "NOT_AN_OBJECT")

    def test_missing_widget_is_filled_with_a_warning(self):
        layout = sl.default_soccer_layout()
        del layout["widgets"]["period"]
        result = sl.validate_soccer_layout(layout)
        self.assertTrue(result.ok)
        self.assertEqual([w.code for w in result.warnings], ["MISSING_WIDGET"])
        self.assertEqual(result.layout["widgets"]["period"], sl.default_soccer_widget("period"))

    def test_unknown_widget_is_a_warning_and_is_dropped(self):
        layout = sl.default_soccer_layout()
        layout["widgets"]["quarter"] = {"id": "quarter"}
        result = sl.validate_soccer_layout(layout)
        self.assertTrue(result.ok)
        self.assertIn("UNKNOWN_WIDGET", [w.code for w in result.warnings])
        self.assertNotIn("quarter", result.layout["widgets"])

    def test_out_of_range_coordinate_is_an_error(self):
        layout = sl.default_soccer_layout()
        layout["widgets"]["home_score"]["x"] = 5.0
        result = sl.validate_soccer_layout(layout)
        self.assertFalse(result.ok)
        self.assertIn("COORDINATE", [e.code for e in result.errors])

    def test_serious_overlap_is_an_error(self):
        layout = sl.default_soccer_layout()
        layout["widgets"]["away_name"]["x"] = layout["widgets"]["home_name"]["x"]
        layout["widgets"]["away_name"]["y"] = layout["widgets"]["home_name"]["y"]
        result = sl.validate_soccer_layout(layout)
        self.assertFalse(result.ok)
        self.assertIn("OVERLAP", [e.code for e in result.errors])

    def test_missing_screens_key_falls_back_to_footballs_own_default_event_screens(self):
        layout = sl.default_soccer_layout()
        del layout["screens"]
        result = sl.validate_soccer_layout(layout)
        self.assertTrue(result.ok)
        self.assertIn("MISSING_SCREENS", [w.code for w in result.warnings])
        self.assertEqual(result.layout["screens"]["pregame"], football_layout.default_screen("pregame"))
        self.assertEqual(result.layout["screens"]["halftime"], football_layout.default_screen("halftime"))

    def test_period_short_format_is_accepted_and_default_is_standard(self):
        layout = sl.default_soccer_layout()
        self.assertEqual(layout["widgets"]["period"]["display_format"], "default")
        layout["widgets"]["period"]["display_format"] = "short"
        result = sl.validate_soccer_layout(layout)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.layout["widgets"]["period"]["display_format"], "short")

    def test_an_unsupported_format_on_another_widget_is_rejected(self):
        layout = sl.default_soccer_layout()
        layout["widgets"]["home_score"]["display_format"] = "ordinal"
        result = sl.validate_soccer_layout(layout)
        self.assertFalse(result.ok)
        self.assertIn("DISPLAY_FORMAT", [e.code for e in result.errors])

    def test_a_football_only_widget_id_is_not_part_of_the_soccer_registry(self):
        self.assertNotIn("quarter", sl.SOCCER_WIDGET_IDS)
        self.assertNotIn("down", sl.SOCCER_WIDGET_IDS)
        self.assertNotIn("play_clock_value", sl.SOCCER_WIDGET_IDS)


class ClampSoccerLayoutTests(unittest.TestCase):
    def test_clamp_never_raises_on_garbage(self):
        layout, issues = sl.clamp_soccer_layout("garbage")
        self.assertEqual(sl.validate_soccer_layout(layout).ok, True)

    def test_clamp_moves_an_out_of_range_widget_inside_the_safe_area(self):
        layout, issues = sl.clamp_soccer_layout({"widgets": {"home_score": {"x": 9.0}}})
        self.assertLessEqual(layout["widgets"]["home_score"]["x"], 1.0)
        self.assertTrue(any(i.code == "OUTSIDE_SAFE_AREA" for i in issues))

    def test_clamp_never_touches_colour_or_visibility(self):
        layout, _issues = sl.clamp_soccer_layout({
            "widgets": {"home_score": {"color": "#123456", "visible": False}}
        })
        self.assertEqual(layout["widgets"]["home_score"]["color"], "#123456")
        self.assertFalse(layout["widgets"]["home_score"]["visible"])


class SoccerPresetTests(unittest.TestCase):
    def test_every_preset_validates_with_zero_warnings(self):
        presets = sl.soccer_preset_descriptors()
        ids = [p["id"] for p in presets]
        self.assertEqual(ids, ["grid", "broadcast", "classic"])
        for preset in presets:
            result = sl.validate_soccer_layout(preset["layout"])
            self.assertTrue(result.ok, (preset["id"], result.errors))
            self.assertEqual(result.warnings, (), preset["id"])

    def test_screen_preset_descriptors_are_footballs_own_unchanged(self):
        self.assertEqual(sl.soccer_screen_preset_descriptors(), football_layout.screen_preset_descriptors())

    def test_screen_descriptors_list_game_then_pregame_then_halftime(self):
        descriptors = sl.soccer_screen_descriptors()
        self.assertEqual([d["id"] for d in descriptors], ["game", "pregame", "halftime"])
        self.assertEqual(descriptors[0]["kind"], "soccer")
        self.assertEqual(descriptors[1]["kind"], "event")
        self.assertEqual(descriptors[2]["kind"], "event")


class SoccerLimitsAndSupportTests(unittest.TestCase):
    def test_limits_include_soccer_screens_and_widget_groups(self):
        limits = sl.soccer_limits()
        self.assertEqual([s["id"] for s in limits["screens"]], ["game", "pregame", "halftime"])
        self.assertEqual(limits["widget_groups"], list(sl.SOCCER_WIDGET_GROUP_ORDER))

    def test_supported_widget_ids_hides_absent_fields_but_keeps_static_labels(self):
        model = {"teams": {"home": {"name": "EAGLES", "score": 1}, "away": {"name": "TIGERS", "score": 0}}}
        supported = sl.supported_widget_ids(model)
        self.assertIn("home_name", supported)
        self.assertIn("game_clock_label", supported)  # static label, always "supported"
        self.assertNotIn("period", supported)  # field absent from this partial model


class BoardJsSoccerMirrorTests(unittest.TestCase):
    """The board.js <-> Python contract for the new SOCCER_* literals."""

    def setUp(self):
        self.source = BOARD_JS.read_text(encoding="utf-8")

    def test_soccer_widget_ids_match_python_exactly_including_order(self):
        extracted = _extract_js_literal(self.source, "SOCCER_WIDGET_IDS")
        self.assertEqual(extracted, list(sl.SOCCER_WIDGET_IDS))

    def test_soccer_widget_fields_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "SOCCER_WIDGET_FIELDS")
        self.assertEqual(extracted, sl.SOCCER_WIDGET_FIELDS)

    def test_soccer_widget_texts_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "SOCCER_WIDGET_TEXTS")
        self.assertEqual(extracted, sl.SOCCER_WIDGET_TEXTS)

    def test_soccer_optional_widget_ids_match_python_as_a_set(self):
        extracted = _extract_js_literal(self.source, "SOCCER_OPTIONAL_WIDGET_IDS")
        self.assertEqual(set(extracted), set(sl.SOCCER_OPTIONAL_WIDGET_IDS))

    def test_soccer_widget_format_fields_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "SOCCER_WIDGET_FORMAT_FIELDS")
        self.assertEqual(extracted, sl.SOCCER_WIDGET_FORMAT_FIELDS)

    def test_soccer_default_layout_matches_python_default_layout_minus_screens(self):
        extracted = _extract_js_literal(self.source, "SOCCER_DEFAULT_LAYOUT")
        expected = sl.default_soccer_layout()
        expected.pop("screens")
        self.assertNotIn("screens", extracted, "SOCCER_DEFAULT_LAYOUT must not itself carry \"screens\"")
        self.assertEqual(extracted, expected)

    def test_registry_for_kind_and_build_accept_soccer(self):
        self.assertIn("kind === 'soccer'", self.source)
        self.assertIn("REGISTRIES.soccer", self.source)

    def test_the_hidden_widgets_gates_include_soccer(self):
        self.assertIn("boardRoot.dataset.boardKind === 'soccer'", self.source)


if __name__ == "__main__":
    unittest.main()
