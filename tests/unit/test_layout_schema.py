"""The presentation layout schema: strict validation, and a safe fallback.

Two rules run through every test here. **Nothing invalid is accepted quietly**
-- a bad coordinate, colour, or font size is an explicit error naming the
widget in words an operator can act on. And **nothing invalid can stop the
board** -- every load path returns a usable layout rather than raising, because
a damaged presentation file must never be the reason a scoreboard will not
start.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.domain.formatting import (
    format_distance,
    format_down,
    format_possession,
    format_timeouts,
)
from scoreboard.presentation.layout import (
    DEFAULT_LAYOUT_NAME,
    LAYOUT_SCHEMA_VERSION,
    MAX_FONT_SCALE,
    MAX_SAFE_INSET,
    MIN_FONT_SCALE,
    MIN_SAFE_SPAN,
    MIN_WIDGET_HEIGHT,
    MIN_WIDGET_WIDTH,
    OPTIONAL_WIDGET_IDS,
    WIDGET_FIELDS,
    WIDGET_IDS,
    WIDGET_LABELS,
    WIDGET_TEXTS,
    clamp_layout,
    default_layout,
    default_widget,
    limits,
    load_layout,
    reset_widget,
    supported_widget_ids,
    validate_layout,
    validate_layout_name,
    widget_descriptors,
)

WIDGET_PROPERTIES = frozenset({
    "id", "visible", "x", "y", "width", "height", "font_scale", "color",
    "text_align", "vertical_align", "font_weight", "z_index",
})


def with_widget(**changes) -> dict:
    """The default layout with one widget's properties replaced."""

    widget_id = changes.pop("widget_id")
    document = json.loads(json.dumps(default_layout()))
    document["widgets"][widget_id].update(changes)
    return document


def codes(validation) -> set[str]:
    return {issue.code for issue in validation.errors}


class DefaultLayoutTests(unittest.TestCase):
    def test_it_is_complete_versioned_and_json_compatible(self) -> None:
        document = default_layout()

        self.assertEqual(document["schema_version"], LAYOUT_SCHEMA_VERSION)
        self.assertEqual(document["name"], DEFAULT_LAYOUT_NAME)
        self.assertEqual(tuple(document["widgets"]), WIDGET_IDS)
        for widget_id, widget in document["widgets"].items():
            self.assertEqual(set(widget), WIDGET_PROPERTIES, widget_id)
            self.assertEqual(widget["id"], widget_id)
        self.assertEqual(json.loads(json.dumps(document, allow_nan=False)), document)

    def test_it_validates_with_no_errors_and_no_warnings(self) -> None:
        validation = validate_layout(default_layout())

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertEqual(validation.errors, ())
        self.assertEqual(validation.warnings, ())

    def test_every_widget_sits_inside_the_safe_area(self) -> None:
        document = default_layout()
        safe = document["safe_area"]
        for widget_id, widget in document["widgets"].items():
            self.assertGreaterEqual(widget["x"], safe["left"] - 1e-9, widget_id)
            self.assertGreaterEqual(widget["y"], safe["top"] - 1e-9, widget_id)
            self.assertLessEqual(widget["x"] + widget["width"], 1 - safe["right"] + 1e-9, widget_id)
            self.assertLessEqual(widget["y"] + widget["height"], 1 - safe["bottom"] + 1e-9, widget_id)

    def test_no_two_visible_widgets_overlap(self) -> None:
        document = default_layout()
        visible = [w for w in document["widgets"].values() if w["visible"]]
        for index, first in enumerate(visible):
            for second in visible[index + 1:]:
                horizontal = (min(first["x"] + first["width"], second["x"] + second["width"])
                              - max(first["x"], second["x"]))
                vertical = (min(first["y"] + first["height"], second["y"] + second["height"])
                            - max(first["y"], second["y"]))
                self.assertFalse(horizontal > 1e-9 and vertical > 1e-9,
                                 f"{first['id']} overlaps {second['id']}")

    def test_the_clock_label_and_timeout_widgets_are_hidden_by_default(self) -> None:
        """The default reproduces today's board, which draws none of these."""

        widgets = default_layout()["widgets"]
        for widget_id in ("game_clock_label", "home_timeouts", "away_timeouts"):
            self.assertFalse(widgets[widget_id]["visible"], widget_id)
        for widget_id in ("home_name", "home_score", "game_clock_value", "quarter",
                          "play_clock_label", "play_clock_value"):
            self.assertTrue(widgets[widget_id]["visible"], widget_id)

    def test_the_label_and_value_of_each_clock_are_separate_widgets(self) -> None:
        widgets = default_layout()["widgets"]
        for label, value in (("game_clock_label", "game_clock_value"),
                             ("play_clock_label", "play_clock_value")):
            self.assertIn(label, widgets)
            self.assertIn(value, widgets)
            self.assertIsNone(WIDGET_FIELDS[label], "a label draws no authoritative value")
            self.assertIsNotNone(WIDGET_FIELDS[value])


class WidgetMetadataTests(unittest.TestCase):
    def test_labels_and_fields_cover_exactly_the_declared_widgets(self) -> None:
        self.assertEqual(set(WIDGET_LABELS), set(WIDGET_IDS))
        self.assertEqual(set(WIDGET_FIELDS), set(WIDGET_IDS))
        self.assertTrue(set(OPTIONAL_WIDGET_IDS).issubset(set(WIDGET_IDS)))

    def test_static_text_exists_for_exactly_the_widgets_with_no_field(self) -> None:
        static = {wid for wid, field in WIDGET_FIELDS.items() if field is None}
        self.assertEqual(set(WIDGET_TEXTS), static)
        for text in WIDGET_TEXTS.values():
            self.assertTrue(text.strip())

    def test_descriptors_and_limits_are_json_compatible_and_complete(self) -> None:
        descriptors = widget_descriptors()
        self.assertEqual([d["id"] for d in descriptors], list(WIDGET_IDS))
        for descriptor in descriptors:
            self.assertEqual(descriptor["label"], WIDGET_LABELS[descriptor["id"]])
            self.assertEqual(set(descriptor["default"]), WIDGET_PROPERTIES)
        payload = {"widgets": descriptors, "limits": limits()}
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        for key in ("min_widget_width", "min_widget_height", "min_font_scale",
                    "max_font_scale", "font_weights", "text_alignments",
                    "vertical_alignments", "schema_version"):
            self.assertIn(key, limits())


class SchemaVersionTests(unittest.TestCase):
    def test_a_missing_or_wrong_version_is_refused(self) -> None:
        for version in (None, 0, 2, "1", True, 1.0):
            document = default_layout()
            if version is None:
                document.pop("schema_version")
            else:
                document["schema_version"] = version
            with self.subTest(version=version):
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("SCHEMA_VERSION", codes(validation))

    def test_a_payload_that_is_not_an_object_is_refused(self) -> None:
        for payload in (None, [], "text", 3, True):
            with self.subTest(payload=payload):
                validation = validate_layout(payload)
                self.assertFalse(validation.ok)
                self.assertIn("NOT_AN_OBJECT", codes(validation))


class CoordinateAndDimensionTests(unittest.TestCase):
    def test_invalid_coordinates_are_refused(self) -> None:
        for value in (-0.1, 1.2, "x", None, True, float("nan"), float("inf")):
            with self.subTest(value=value):
                validation = validate_layout(with_widget(widget_id="quarter", x=value))
                self.assertFalse(validation.ok)
                self.assertTrue({"COORDINATE", "OUTSIDE_SAFE_AREA"} & codes(validation))

    def test_invalid_dimensions_are_refused(self) -> None:
        for value in (0, -0.5, 1.5, "wide", None, True):
            with self.subTest(value=value):
                validation = validate_layout(with_widget(widget_id="quarter", width=value))
                self.assertFalse(validation.ok)
                self.assertTrue(
                    {"DIMENSION", "MIN_DIMENSION", "OUTSIDE_SAFE_AREA"} & codes(validation))

    def test_a_dimension_below_the_readable_minimum_is_refused(self) -> None:
        narrow = validate_layout(with_widget(widget_id="quarter", width=MIN_WIDGET_WIDTH / 2))
        short = validate_layout(with_widget(widget_id="quarter", height=MIN_WIDGET_HEIGHT / 2))

        self.assertFalse(narrow.ok)
        self.assertFalse(short.ok)
        self.assertIn("MIN_DIMENSION", codes(narrow))
        self.assertIn("MIN_DIMENSION", codes(short))

    def test_each_safe_area_edge_is_enforced_and_names_the_widget(self) -> None:
        cases = {
            "left": {"x": 0.0},
            "top": {"y": 0.0},
            "right": {"x": 0.90, "width": 0.20},
            "bottom": {"y": 0.95, "height": 0.10},
        }
        for edge, change in cases.items():
            with self.subTest(edge=edge):
                validation = validate_layout(with_widget(widget_id="ball_on", **change))
                self.assertFalse(validation.ok)
                self.assertIn("OUTSIDE_SAFE_AREA", codes(validation))
                messages = " ".join(issue.message for issue in validation.errors)
                self.assertIn(WIDGET_LABELS["ball_on"], messages)


class StyleTests(unittest.TestCase):
    def test_invalid_colours_are_refused(self) -> None:
        for value in ("red", "#GGGGGG", "#12345", "rgb(1,2,3)", 12, None, "", "#12345678"):
            with self.subTest(value=value):
                validation = validate_layout(with_widget(widget_id="quarter", color=value))
                self.assertFalse(validation.ok)
                self.assertIn("COLOR", codes(validation))

    def test_a_short_colour_is_normalised_to_six_uppercase_digits(self) -> None:
        validation = validate_layout(with_widget(widget_id="quarter", color="#fab"))

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(validation.layout["widgets"]["quarter"]["color"], "#FFAABB")

    def test_invalid_font_scales_are_refused(self) -> None:
        for value in (0, -0.1, MAX_FONT_SCALE * 2, MIN_FONT_SCALE / 2, "big", None, True):
            with self.subTest(value=value):
                validation = validate_layout(with_widget(widget_id="quarter", font_scale=value))
                self.assertFalse(validation.ok)
                self.assertIn("FONT_SCALE", codes(validation))

    def test_invalid_enumerated_properties_are_refused(self) -> None:
        cases = [
            ("font_weight", 450, "FONT_WEIGHT"),
            ("font_weight", "bold", "FONT_WEIGHT"),
            ("text_align", "justify", "TEXT_ALIGN"),
            ("vertical_align", "centre", "VERTICAL_ALIGN"),
            ("z_index", -1, "Z_INDEX"),
            ("z_index", 1.5, "Z_INDEX"),
            ("visible", "yes", "VISIBLE"),
        ]
        for prop, value, code in cases:
            with self.subTest(prop=prop, value=value):
                validation = validate_layout(with_widget(widget_id="quarter", **{prop: value}))
                self.assertFalse(validation.ok)
                self.assertIn(code, codes(validation))


class SafeAreaSettingTests(unittest.TestCase):
    def test_an_inset_outside_its_sensible_range_is_refused(self) -> None:
        for inset in (-0.01, MAX_SAFE_INSET + 0.01, "4%", None, True):
            with self.subTest(inset=inset):
                document = default_layout()
                document["safe_area"]["top"] = inset
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("SAFE_AREA", codes(validation))

    def test_the_inset_ceiling_alone_guarantees_a_usable_canvas(self) -> None:
        """A layout can never remove the whole board.

        Two independent rules protect this: every inset is capped at
        ``MAX_SAFE_INSET``, and the remaining span must still be at least
        ``MIN_SAFE_SPAN``. The cap is the stronger of the two, so the span rule
        is a backstop rather than the thing doing the work -- asserted here so
        that raising the cap later cannot quietly make an unusable canvas
        reachable.
        """

        widest = default_layout()
        for side in ("top", "right", "bottom", "left"):
            widest["safe_area"][side] = MAX_SAFE_INSET

        self.assertGreaterEqual(1 - 2 * MAX_SAFE_INSET, MIN_SAFE_SPAN)
        # The insets are legal, so any failure here is about the widgets no
        # longer fitting, never about the canvas being unusable.
        self.assertNotIn("SAFE_AREA_SPAN", codes(validate_layout(widest)))

    def test_a_span_below_the_minimum_is_refused_when_it_can_be_reached(self) -> None:
        document = default_layout()
        document["safe_area"]["left"] = MAX_SAFE_INSET + 0.30
        document["safe_area"]["right"] = MAX_SAFE_INSET + 0.30

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        # The per-inset ceiling catches it first, which is the point: an
        # unusable canvas is unreachable through two separate rules.
        self.assertIn("SAFE_AREA", codes(validation))

    def test_a_safe_area_that_cannot_be_read_at_all_is_refused(self) -> None:
        for value in ([], "4%", 4, True):
            with self.subTest(value=value):
                document = default_layout()
                document["safe_area"] = value
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("SAFE_AREA", codes(validation))

    def test_an_absent_or_partial_safe_area_defaults_but_never_silently(self) -> None:
        """Filling an edge changes where every widget may sit, so it is said."""

        absent = default_layout()
        absent.pop("safe_area")
        partial = default_layout()
        partial["safe_area"] = {"top": 0.04}
        explicit_none = default_layout()
        explicit_none["safe_area"] = None

        for label, document in (("absent", absent), ("partial", partial),
                                ("null", explicit_none)):
            with self.subTest(case=label):
                validation = validate_layout(document)
                self.assertTrue(validation.ok, [i.message for i in validation.errors])
                self.assertIn("SAFE_AREA", {i.code for i in validation.warnings})
                self.assertEqual(validation.layout["safe_area"],
                                 {"top": 0.04, "right": 0.04, "bottom": 0.04, "left": 0.04})


class OverlapTests(unittest.TestCase):
    def test_a_serious_overlap_is_an_error_naming_both_widgets(self) -> None:
        # Put the quarter directly on top of the game clock.
        clock = default_layout()["widgets"]["game_clock_value"]
        document = with_widget(widget_id="quarter", x=clock["x"], y=clock["y"],
                               width=clock["width"], height=clock["height"])

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("OVERLAP", codes(validation))
        messages = " ".join(issue.message for issue in validation.errors)
        self.assertIn(WIDGET_LABELS["quarter"], messages)
        self.assertIn(WIDGET_LABELS["game_clock_value"], messages)

    def test_a_hidden_widget_never_collides_with_anything(self) -> None:
        clock = default_layout()["widgets"]["game_clock_value"]
        document = with_widget(widget_id="quarter", visible=False, x=clock["x"], y=clock["y"],
                               width=clock["width"], height=clock["height"])

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertEqual(validation.warnings, ())


class MergeAndFallbackTests(unittest.TestCase):
    def test_an_unknown_widget_is_dropped_with_a_warning(self) -> None:
        document = default_layout()
        document["widgets"]["scoreboard_mascot"] = default_widget("quarter")

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertIn("UNKNOWN_WIDGET", {issue.code for issue in validation.warnings})
        self.assertNotIn("scoreboard_mascot", validation.layout["widgets"])

    def test_an_unknown_property_is_dropped_with_a_warning(self) -> None:
        document = with_widget(widget_id="quarter", italic=True)

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertIn("UNKNOWN_PROPERTY", {issue.code for issue in validation.warnings})
        self.assertNotIn("italic", validation.layout["widgets"]["quarter"])

    def test_a_missing_widget_is_filled_from_the_default_with_a_warning(self) -> None:
        document = default_layout()
        del document["widgets"]["ball_on"]

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertIn("MISSING_WIDGET", {issue.code for issue in validation.warnings})
        self.assertEqual(validation.layout["widgets"]["ball_on"], default_widget("ball_on"))

    def test_load_never_raises_and_falls_back_to_the_built_in_default(self) -> None:
        broken = with_widget(widget_id="quarter", x="nonsense")
        for payload in (None, [], "text", 3, {}, {"schema_version": 9}, broken):
            with self.subTest(payload=payload):
                document, issues = load_layout(payload)
                self.assertEqual(document, default_layout())
                self.assertTrue(issues)

    def test_load_keeps_a_valid_layout_and_reports_only_warnings(self) -> None:
        document, issues = load_layout(with_widget(widget_id="quarter", color="#abc"))

        self.assertEqual(document["widgets"]["quarter"]["color"], "#AABBCC")
        self.assertTrue(all(issue.severity == "warning" for issue in issues))


class ClampTests(unittest.TestCase):
    def test_it_repairs_an_out_of_range_layout_and_reports_each_adjustment(self) -> None:
        document = with_widget(widget_id="ball_on", x=1.4, y=-0.3, font_scale=MAX_FONT_SCALE * 3)

        repaired, issues = clamp_layout(document)

        self.assertTrue(issues)
        self.assertTrue(all(issue.severity == "warning" for issue in issues))
        # Clamping repairs ranges, deliberately not overlaps: moving somebody
        # else's widget to resolve a collision is a decision only the operator
        # should make. Every clamped value is back inside the safe area.
        widget = repaired["widgets"]["ball_on"]
        safe = repaired["safe_area"]
        self.assertGreaterEqual(widget["x"], safe["left"] - 1e-9)
        self.assertGreaterEqual(widget["y"], safe["top"] - 1e-9)
        self.assertLessEqual(widget["x"] + widget["width"], 1 - safe["right"] + 1e-9)
        self.assertLessEqual(widget["y"] + widget["height"], 1 - safe["bottom"] + 1e-9)
        self.assertLessEqual(widget["font_scale"], MAX_FONT_SCALE)
        self.assertNotIn("OUTSIDE_SAFE_AREA", codes(validate_layout(repaired)))
        self.assertNotIn("FONT_SCALE", codes(validate_layout(repaired)))

    def test_it_never_raises_on_garbage(self) -> None:
        for payload in (None, [], "text", {"widgets": "no"}):
            with self.subTest(payload=payload):
                repaired, _ = clamp_layout(payload)
                self.assertEqual(tuple(repaired["widgets"]), WIDGET_IDS)
                self.assertTrue(validate_layout(repaired).ok)


class ResetTests(unittest.TestCase):
    def test_it_restores_one_widget_and_leaves_the_others_alone(self) -> None:
        document = with_widget(widget_id="quarter", x=0.06, color="#123456")
        document["widgets"]["ball_on"]["color"] = "#654321"

        restored = reset_widget(document, "quarter")

        self.assertEqual(restored["widgets"]["quarter"], default_widget("quarter"))
        self.assertEqual(restored["widgets"]["ball_on"]["color"], "#654321")


class SupportedWidgetTests(unittest.TestCase):
    def test_an_empty_view_model_supports_only_the_static_labels(self) -> None:
        supported = supported_widget_ids({})

        self.assertEqual(set(supported), set(WIDGET_TEXTS))

    def test_an_absent_optional_field_makes_only_that_widget_unsupported(self) -> None:
        model = {
            "teams": {"home": {"name": "EAGLES", "score": 7},
                      "away": {"name": "TIGERS", "score": 3}},
            "quarter_display": "2nd Quarter",
            "clocks": {"game": {"display": "12:00"}, "play": {"display": "25"}},
            "football": {"down_display": "", "distance_display": "& 7",
                         "possession_display": "◀ BALL", "ball_on_display": "AWAY 35",
                         "home_timeouts_display": "TO 3", "away_timeouts_display": "TO 2"},
        }

        supported = set(supported_widget_ids(model))

        self.assertNotIn("down", supported)
        self.assertIn("distance", supported)
        self.assertIn("home_score", supported)
        self.assertIn("play_clock_label", supported)


class LayoutNameTests(unittest.TestCase):
    def test_a_usable_name_is_accepted(self) -> None:
        for name in ("Default", "Night game", "A" * 40):
            with self.subTest(name=name):
                self.assertIsNone(validate_layout_name(name))

    def test_an_unusable_name_is_refused(self) -> None:
        for name in ("", "   ", "A" * 41, None, 7, True, "bad\x00name", "line\nbreak"):
            with self.subTest(name=name):
                issue = validate_layout_name(name)
                self.assertIsNotNone(issue)
                self.assertEqual(issue.code, "LAYOUT_NAME")


class FootballFormatterTests(unittest.TestCase):
    """Each widget draws a string Python produced; JavaScript derives nothing."""

    def test_down(self) -> None:
        self.assertEqual(format_down(None), "")
        for value, expected in ((1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th")):
            self.assertEqual(format_down(value), expected)

    def test_distance(self) -> None:
        self.assertEqual(format_distance(None), "")
        self.assertEqual(format_distance(0), "& Goal")
        self.assertEqual(format_distance(1), "& 1")
        self.assertEqual(format_distance(99), "& 99")

    def test_possession(self) -> None:
        self.assertEqual(format_possession(None), "")
        self.assertEqual(format_possession("home"), "◀ BALL")
        self.assertEqual(format_possession("away"), "BALL ▶")

    def test_timeouts(self) -> None:
        self.assertEqual(format_timeouts(None), "")
        self.assertEqual(format_timeouts(0), "TO 0")
        self.assertEqual(format_timeouts(3), "TO 3")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
