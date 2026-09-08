"""The presentation layout schema: strict validation, and a safe fallback.

Two rules run through every test here. **Nothing invalid is accepted quietly**
-- a bad coordinate, colour, or font size is an explicit error naming the
widget in words an operator can act on. And **nothing invalid can stop the
board** -- every load path returns a usable layout rather than raising, because
a damaged presentation file must never be the reason a scoreboard will not
start.

v2 (schema section 1) adds a whole-board ``background``, ten style properties
on every widget, and a list of freestanding ``elements`` (text/image/box).
Those additions get their own test classes below; the v1 classes above them
are updated only where the v1 widget shape itself grew new keys.
"""

from __future__ import annotations

import base64
import json
import struct
import unittest
import zlib
from unittest import mock

import scoreboard.presentation.layout as layout_module

from scoreboard.domain.formatting import (
    format_distance,
    format_down,
    format_possession,
    format_timeouts,
)
from scoreboard.presentation.layout import (
    DEFAULT_LAYOUT_NAME,
    ELEMENT_TYPES,
    EVENT_SCREEN_IDS,
    EVENT_WIDGET_GROUP_ORDER,
    EVENT_WIDGET_IDS,
    FONT_FAMILIES,
    FONT_FAMILY_LABELS,
    IMAGE_FITS,
    LAYOUT_SCHEMA_VERSION,
    MAX_ELEMENTS,
    MAX_FONT_SCALE,
    MAX_IMAGE_BYTES,
    MAX_SAFE_INSET,
    MAX_TEXT_LENGTH,
    MAX_TOTAL_IMAGE_BYTES,
    MIN_FONT_SCALE,
    MIN_SAFE_SPAN,
    MIN_WIDGET_HEIGHT,
    MIN_WIDGET_WIDTH,
    OPTIONAL_WIDGET_IDS,
    SCREEN_IDS,
    SCREEN_KINDS,
    SCREEN_LABELS,
    TEXT_EFFECTS,
    TEXT_TRANSFORMS,
    WIDGET_FIELDS,
    WIDGET_GROUPS,
    WIDGET_GROUP_ORDER,
    WIDGET_IDS,
    WIDGET_LABELS,
    WIDGET_TEXTS,
    clamp_layout,
    default_layout,
    default_screen,
    default_screen_widget,
    default_widget,
    element_label,
    limits,
    load_layout,
    preset_descriptors,
    reset_widget,
    screen_descriptors,
    screen_preset_descriptors,
    supported_widget_ids,
    validate_layout,
    validate_layout_name,
    widget_descriptors,
)

#: The v1 geometry/style widget properties (unchanged since v1).
WIDGET_GEOMETRY_PROPERTIES = frozenset({
    "id", "visible", "x", "y", "width", "height", "font_scale", "color",
    "text_align", "vertical_align", "font_weight", "z_index",
})
#: The ten v2 style properties every widget (and text element) now carries.
WIDGET_STYLE_PROPERTIES = frozenset({
    "font_family", "letter_spacing", "text_transform", "text_effect",
    "background", "background_opacity", "border_color", "border_width",
    "corner_radius", "corner_cut", "cut_corners", "padding",
})
WIDGET_PROPERTIES = WIDGET_GEOMETRY_PROPERTIES | WIDGET_STYLE_PROPERTIES | {"display_format", "fit_text"}

#: A hand-built valid PNG, GIF, and JPEG-magic payload for exercising image
#: validation for real rather than mocking base64 decoding away.
def _make_png_data_uri() -> str:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw_scanline = b"\x00" + b"\xff\x00\x00"  # filter byte + one RGB pixel
    idat = zlib.compress(raw_scanline)
    png_bytes = signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def _make_gif_data_uri() -> str:
    # A minimal, syntactically-plausible-enough GIF87a header. Only the
    # magic bytes are checked, so a hand-built header is enough.
    gif_bytes = b"GIF87a" + b"\x01\x00\x01\x00\x80\x00\x00" + b"\x00" * 10
    return "data:image/gif;base64," + base64.b64encode(gif_bytes).decode("ascii")


_PNG_DATA_URI = _make_png_data_uri()
_GIF_DATA_URI = _make_gif_data_uri()


def with_widget(**changes) -> dict:
    """The default layout with one widget's properties replaced."""

    widget_id = changes.pop("widget_id")
    document = json.loads(json.dumps(default_layout()))
    document["widgets"][widget_id].update(changes)
    return document


def with_elements(*elements: dict) -> dict:
    """The default layout with the given raw element entries."""

    document = json.loads(json.dumps(default_layout()))
    document["elements"] = list(elements)
    return document


def codes(validation) -> set[str]:
    return {issue.code for issue in validation.errors}


def warning_codes(validation) -> set[str]:
    return {issue.code for issue in validation.warnings}


class DefaultLayoutTests(unittest.TestCase):
    def test_it_is_complete_versioned_and_json_compatible(self) -> None:
        document = default_layout()

        self.assertEqual(document["schema_version"], LAYOUT_SCHEMA_VERSION)
        self.assertEqual(document["name"], DEFAULT_LAYOUT_NAME)
        self.assertEqual(document["background"], {"color": "#000000"})
        self.assertEqual(document["elements"], [])
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

    def test_only_the_style_keys_are_new_every_v1_geometry_value_is_unchanged(self) -> None:
        """v2's built-in default must render pixel-identical to v1 (spec 1.1):
        same geometry, Arial, no backgrounds, no effects -- only the ten new
        style keys, all at their neutral defaults, are added.
        """

        widgets = default_layout()["widgets"]
        # The exact v1 geometry/style values, transcribed independently of the
        # implementation so a regression in the source data is still caught.
        expected_v1 = {
            "home_name": {"visible": True, "x": 0.040, "y": 0.040, "width": 0.380, "height": 0.118,
                          "font_scale": 0.028, "color": "#FFFFFF", "text_align": "center",
                          "vertical_align": "middle", "font_weight": 700, "z_index": 0},
            "home_score": {"visible": True, "x": 0.040, "y": 0.164, "width": 0.380, "height": 0.242,
                           "font_scale": 0.112, "color": "#FFFFFF", "text_align": "center",
                           "vertical_align": "middle", "font_weight": 700, "z_index": 0},
            "possession": {"visible": True, "x": 0.430, "y": 0.071, "width": 0.140, "height": 0.056,
                           "font_scale": 0.026, "color": "#57E6A4", "text_align": "center",
                           "vertical_align": "middle", "font_weight": 700, "z_index": 0},
            "away_name": {"visible": True, "x": 0.580, "y": 0.040, "width": 0.380, "height": 0.118,
                          "font_scale": 0.028, "color": "#FFFFFF", "text_align": "center",
                          "vertical_align": "middle", "font_weight": 700, "z_index": 0},
            "away_score": {"visible": True, "x": 0.580, "y": 0.164, "width": 0.380, "height": 0.242,
                           "font_scale": 0.112, "color": "#FFFFFF", "text_align": "center",
                           "vertical_align": "middle", "font_weight": 700, "z_index": 0},
            "game_clock_label": {"visible": False, "x": 0.400, "y": 0.412, "width": 0.200, "height": 0.052,
                                  "font_scale": 0.024, "color": "#CFCFCF", "text_align": "center",
                                  "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "game_clock_value": {"visible": True, "x": 0.040, "y": 0.470, "width": 0.920, "height": 0.200,
                                  "font_scale": 0.093, "color": "#FFFFFF", "text_align": "center",
                                  "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "quarter": {"visible": True, "x": 0.040, "y": 0.699, "width": 0.440, "height": 0.126,
                        "font_scale": 0.058, "color": "#FFFFFF", "text_align": "center",
                        "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "down": {"visible": True, "x": 0.110, "y": 0.875, "width": 0.150, "height": 0.059,
                     "font_scale": 0.027, "color": "#CFCFCF", "text_align": "right",
                     "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "distance": {"visible": True, "x": 0.272, "y": 0.875, "width": 0.150, "height": 0.059,
                         "font_scale": 0.027, "color": "#CFCFCF", "text_align": "left",
                         "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "play_clock_label": {"visible": True, "x": 0.500, "y": 0.733, "width": 0.210, "height": 0.059,
                                  "font_scale": 0.027, "color": "#FFFFFF", "text_align": "right",
                                  "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "play_clock_value": {"visible": True, "x": 0.718, "y": 0.678, "width": 0.242, "height": 0.168,
                                  "font_scale": 0.078, "color": "#FFFFFF", "text_align": "left",
                                  "vertical_align": "middle", "font_weight": 700, "z_index": 0},
            "ball_on": {"visible": True, "x": 0.480, "y": 0.854, "width": 0.480, "height": 0.101,
                        "font_scale": 0.024, "color": "#CFCFCF", "text_align": "center",
                        "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "home_timeouts": {"visible": False, "x": 0.040, "y": 0.412, "width": 0.200, "height": 0.052,
                               "font_scale": 0.024, "color": "#CFCFCF", "text_align": "left",
                               "vertical_align": "middle", "font_weight": 400, "z_index": 0},
            "away_timeouts": {"visible": False, "x": 0.760, "y": 0.412, "width": 0.200, "height": 0.052,
                               "font_scale": 0.024, "color": "#CFCFCF", "text_align": "right",
                               "vertical_align": "middle", "font_weight": 400, "z_index": 0},
        }
        expected_style_defaults = {
            "font_family": "arial", "letter_spacing": 0.0, "text_transform": "none",
            "text_effect": "none", "background": None, "background_opacity": 1.0,
            "border_color": None, "border_width": 0.0, "corner_radius": 0.0,
            "corner_cut": 0.0, "cut_corners": "all", "padding": 0.0,
        }
        # F3 (crowd-facing game-state messages) adds status_message/
        # status_clock at the end of WIDGET_IDS -- new v3 widgets, not part
        # of the "renders pixel-identical to v1" claim this test pins, so
        # they are the only ids expected to be outside expected_v1's set.
        self.assertEqual(set(WIDGET_IDS) - set(expected_v1), {"status_message", "status_clock"})
        for widget_id, geometry in expected_v1.items():
            widget = widgets[widget_id]
            for key, value in geometry.items():
                self.assertEqual(widget[key], value, f"{widget_id}.{key}")
            for key, value in expected_style_defaults.items():
                self.assertEqual(widget[key], value, f"{widget_id}.{key}")


class StatusWidgetDefaultGeometryTests(unittest.TestCase):
    """F3 (crowd-facing game-state messages): status_message/status_clock's
    default rectangles must be visible out of the box, and disjoint -- not
    merely under the serious-overlap threshold, but truly zero-intersection
    -- from every other default widget's rectangle, including the three
    ``visible: False`` ones (home_timeouts, game_clock_label, away_timeouts)
    that share their y-band, so an operator who later turns those three on
    never gets a surprise overlap error. This is the arithmetic proof behind
    `.scratch/f3-i4/DESIGN.md`'s Part 1 presentation section, pinned as a
    test rather than left as a comment someone could invalidate by editing
    one number.
    """

    @staticmethod
    def _rect(widget: dict) -> tuple[float, float, float, float]:
        return (widget["x"], widget["y"], widget["x"] + widget["width"], widget["y"] + widget["height"])

    def test_both_are_visible_and_bound_to_the_status_block(self) -> None:
        widgets = default_layout()["widgets"]
        for widget_id in ("status_message", "status_clock"):
            self.assertTrue(widgets[widget_id]["visible"], widget_id)
        self.assertEqual(WIDGET_FIELDS["status_message"], "status.display")
        self.assertEqual(WIDGET_FIELDS["status_clock"], "status.clock_display")

    def test_rectangles_are_disjoint_from_every_other_default_widget(self) -> None:
        widgets = default_layout()["widgets"]
        new_ids = ("status_message", "status_clock")
        for new_id in new_ids:
            new_x0, new_y0, new_x1, new_y1 = self._rect(widgets[new_id])
            for other_id, other in widgets.items():
                if other_id in new_ids:
                    continue
                ox0, oy0, ox1, oy1 = self._rect(other)
                overlap_width = min(new_x1, ox1) - max(new_x0, ox0)
                overlap_height = min(new_y1, oy1) - max(new_y0, oy0)
                # A merely *touching* edge (zero-width or zero-height
                # intersection) is fine and expected -- both new widgets sit
                # in the free gaps beside game_clock_label -- only a positive
                # area on both axes is a real overlap.
                self.assertFalse(
                    overlap_width > 1e-9 and overlap_height > 1e-9,
                    f"{new_id} overlaps {other_id}",
                )

    def test_the_default_layout_validates_clean_with_both_status_widgets_visible(self) -> None:
        validation = validate_layout(default_layout())

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertEqual(validation.warnings, ())
        self.assertTrue(validation.layout["widgets"]["status_message"]["visible"])
        self.assertTrue(validation.layout["widgets"]["status_clock"]["visible"])


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

    def test_every_widget_belongs_to_exactly_one_known_group(self) -> None:
        self.assertEqual(set(WIDGET_GROUPS), set(WIDGET_IDS))
        self.assertEqual(set(WIDGET_GROUPS.values()), set(WIDGET_GROUP_ORDER))
        self.assertEqual(list(WIDGET_GROUP_ORDER), ["Teams", "Clocks", "Field", "Status"])
        expected = {
            "Teams": {"home_name", "home_score", "possession", "away_name", "away_score"},
            "Clocks": {"game_clock_label", "game_clock_value", "play_clock_label",
                       "play_clock_value", "quarter"},
            "Field": {"down", "distance", "ball_on", "home_timeouts", "away_timeouts"},
            # F3 (crowd-facing game-state messages): the crowd message and
            # its countdown get their own rail group rather than joining
            # "Field" or "Clocks" -- neither is a football-field concept or a
            # game clock, and lumping them in would bury the two controls an
            # operator is most likely to reach for mid-stoppage.
            "Status": {"status_message", "status_clock"},
        }
        for group, widget_ids in expected.items():
            actual = {wid for wid, g in WIDGET_GROUPS.items() if g == group}
            self.assertEqual(actual, widget_ids, group)

    def test_descriptors_and_limits_are_json_compatible_and_complete(self) -> None:
        descriptors = widget_descriptors()
        self.assertEqual([d["id"] for d in descriptors], list(WIDGET_IDS))
        for descriptor in descriptors:
            self.assertEqual(descriptor["label"], WIDGET_LABELS[descriptor["id"]])
            self.assertEqual(descriptor["group"], WIDGET_GROUPS[descriptor["id"]])
            self.assertEqual(set(descriptor["default"]), WIDGET_PROPERTIES)
        payload = {"widgets": descriptors, "limits": limits()}
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        for key in ("min_widget_width", "min_widget_height", "min_font_scale",
                    "max_font_scale", "font_weights", "text_alignments",
                    "vertical_alignments", "schema_version",
                    "min_letter_spacing", "max_letter_spacing", "max_border_width",
                    "max_corner_radius", "cut_corner_sides", "max_padding", "min_opacity", "max_elements",
                    "min_box_thickness",
                    "max_text_length", "max_text_lines", "max_image_bytes",
                    "max_total_image_bytes", "font_families", "text_transforms",
                    "text_effects", "image_fits", "element_types", "widget_groups"):
            self.assertIn(key, limits())

    def test_status_widgets_are_exposed_under_the_status_group(self) -> None:
        """F3: the layout editor's rail is built entirely from
        widget_descriptors() (spec section 8) -- no hard-coded widget list --
        so simply appearing here, tagged "Status", is what makes both new
        widgets show up in the editor with no editor-side change at all.
        """

        by_id = {d["id"]: d for d in widget_descriptors()}
        for widget_id in ("status_message", "status_clock"):
            self.assertIn(widget_id, by_id)
            self.assertEqual(by_id[widget_id]["group"], "Status")
            self.assertTrue(by_id[widget_id]["optional"])
            self.assertIsNone(by_id[widget_id]["static_text"])
        self.assertIn("Status", limits()["widget_groups"])

    def test_font_family_labels_cover_exactly_the_declared_families(self) -> None:
        self.assertEqual(set(FONT_FAMILY_LABELS), set(FONT_FAMILIES))
        reported = {entry["id"]: entry["label"] for entry in limits()["font_families"]}
        self.assertEqual(reported, FONT_FAMILY_LABELS)
        self.assertEqual(list(reported), list(FONT_FAMILIES))


class SchemaVersionTests(unittest.TestCase):
    def test_a_missing_or_wrong_version_is_refused(self) -> None:
        for version in (None, 0, "1", True, 1.0, 4, "2", 2.0):
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

    def test_a_version_1_document_upgrades_with_exactly_one_warning(self) -> None:
        document = default_layout()
        document["schema_version"] = 1

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertEqual(len(validation.warnings), 1)
        self.assertEqual(validation.warnings[0].code, "SCHEMA_UPGRADED")
        self.assertEqual(validation.layout["schema_version"], LAYOUT_SCHEMA_VERSION)

    def test_a_version_2_document_upgrades_with_exactly_one_warning(self) -> None:
        """v3 section 1: a v1 *or* v2 document is accepted, upgraded, and gets
        exactly the one SCHEMA_UPGRADED warning -- never also MISSING_SCREENS,
        because the upgrade warning already told the operator everything new
        (including the two event screens) was filled in.
        """

        document = default_layout()
        document["schema_version"] = 2

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertEqual(len(validation.warnings), 1)
        self.assertEqual(validation.warnings[0].code, "SCHEMA_UPGRADED")
        self.assertEqual(validation.layout["schema_version"], LAYOUT_SCHEMA_VERSION)
        self.assertEqual(set(validation.layout["screens"]), {"pregame", "halftime"})

    def test_a_version_1_document_gets_every_new_property_filled_from_default(self) -> None:
        # A genuine v1 shape: no background, no elements, v1-only widget keys.
        # A real v1 file never had a background section either, so this also
        # legitimately reports MISSING_BACKGROUND alongside the upgrade
        # warning -- both are "filled from default" in exactly the same way.
        document = {
            "schema_version": 1,
            "name": "Old layout",
            "safe_area": {"top": 0.04, "right": 0.04, "bottom": 0.04, "left": 0.04},
            "widgets": {
                widget_id: {
                    key: value for key, value in default_widget(widget_id).items()
                    if key in WIDGET_GEOMETRY_PROPERTIES
                }
                for widget_id in WIDGET_IDS
            },
        }

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        self.assertEqual({i.code for i in validation.warnings}, {"SCHEMA_UPGRADED", "MISSING_BACKGROUND"})
        self.assertEqual(validation.layout["background"], {"color": "#000000"})
        self.assertEqual(validation.layout["elements"], [])
        for widget_id, widget in validation.layout["widgets"].items():
            self.assertEqual(set(widget), WIDGET_PROPERTIES, widget_id)


class ScreenTests(unittest.TestCase):
    """Schema v3 (spec section 1): the pre-game and halftime screens."""

    def test_a_v3_document_without_screens_is_filled_with_a_warning(self) -> None:
        document = default_layout()
        del document["screens"]

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("MISSING_SCREENS", warning_codes(validation))
        self.assertEqual(validation.layout["screens"]["pregame"], default_screen("pregame"))
        self.assertEqual(validation.layout["screens"]["halftime"], default_screen("halftime"))

    def test_a_bad_screen_is_an_error_with_the_screen_label_prefix(self) -> None:
        document = default_layout()
        document["screens"]["halftime"] = "not a screen"

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("SCREEN", codes(validation))
        bad_issue = next(i for i in validation.errors if i.code == "SCREEN")
        self.assertEqual(bad_issue.screen, "halftime")
        self.assertTrue(bad_issue.message.startswith("Halftime: "), bad_issue.message)

    def test_an_unknown_screen_key_is_a_warning(self) -> None:
        document = default_layout()
        document["screens"]["overtime"] = default_screen("pregame")

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("UNKNOWN_SCREEN", warning_codes(validation))
        self.assertNotIn("overtime", validation.layout["screens"])

    def test_a_single_missing_screen_is_filled_with_a_warning(self) -> None:
        document = default_layout()
        del document["screens"]["pregame"]

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("MISSING_SCREEN", warning_codes(validation))
        self.assertEqual(validation.layout["screens"]["pregame"], default_screen("pregame"))

    def test_game_screen_issues_are_unprefixed_and_tagged_game(self) -> None:
        document = with_widget(widget_id="quarter", color="not-a-color")

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        color_issue = next(i for i in validation.errors if i.code == "COLOR")
        self.assertEqual(color_issue.screen, "game")
        self.assertFalse(color_issue.message.startswith("Pre-game:"))
        self.assertFalse(color_issue.message.startswith("Halftime:"))

    def test_element_ids_are_unique_per_screen_but_may_repeat_across_screens(self) -> None:
        document = default_layout()
        document["screens"]["pregame"]["elements"] = [
            {"id": "box_1", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            {"id": "box_1", "type": "box", "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
        ]

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        bad_issue = next(i for i in validation.errors if i.code == "ELEMENT_ID")
        self.assertEqual(bad_issue.screen, "pregame")

        # The same id on two *different* screens is fine.
        ok_document = default_layout()
        ok_document["screens"]["pregame"]["elements"] = [
            {"id": "box_1", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        ok_document["screens"]["halftime"]["elements"] = [
            {"id": "box_1", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        ok_validation = validate_layout(ok_document)
        self.assertTrue(ok_validation.ok, [i.message for i in ok_validation.errors])

    def test_max_elements_is_enforced_per_screen(self) -> None:
        document = default_layout()
        document["screens"]["halftime"]["elements"] = [
            {"id": f"box_{i}", "type": "box", "x": 0.01, "y": 0.01, "width": 0.02, "height": 0.02}
            for i in range(MAX_ELEMENTS + 1)
        ]

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        bad_issue = next(i for i in validation.errors if i.code == "MAX_ELEMENTS")
        self.assertEqual(bad_issue.screen, "halftime")

        # The game screen and the other event screen are unaffected: exactly
        # the cap on one screen is still fine everywhere else.
        at_cap = default_layout()
        at_cap["screens"]["pregame"]["elements"] = [
            {"id": f"box_{i}", "type": "box", "x": 0.01, "y": 0.01, "width": 0.02, "height": 0.02}
            for i in range(MAX_ELEMENTS)
        ]
        self.assertTrue(validate_layout(at_cap).ok)

    def test_clamp_layout_repairs_a_pregame_widget(self) -> None:
        document = default_layout()
        document["screens"]["pregame"]["widgets"]["event_clock"]["x"] = 1.9

        repaired, issues = clamp_layout(document)

        widget = repaired["screens"]["pregame"]["widgets"]["event_clock"]
        safe = repaired["screens"]["pregame"]["safe_area"]
        self.assertLessEqual(widget["x"] + widget["width"], 1 - safe["right"] + 1e-9)
        self.assertTrue(
            any(i.screen == "pregame" and i.widget_id == "event_clock" for i in issues), issues
        )
        self.assertTrue(all(i.severity == "warning" for i in issues))

    def test_reset_widget_on_the_halftime_screen(self) -> None:
        document = default_layout()
        document["screens"]["halftime"]["widgets"]["event_clock"]["color"] = "#123456"
        document["screens"]["pregame"]["widgets"]["event_clock"]["color"] = "#654321"

        restored = reset_widget(document, "event_clock", screen="halftime")

        self.assertEqual(
            restored["screens"]["halftime"]["widgets"]["event_clock"],
            default_screen_widget("halftime", "event_clock"),
        )
        # The other screen, and the game screen, are untouched.
        self.assertEqual(restored["screens"]["pregame"]["widgets"]["event_clock"]["color"], "#654321")

    def test_reset_widget_with_an_unknown_screen_or_widget_is_a_no_op(self) -> None:
        document = default_layout()

        self.assertEqual(reset_widget(document, "event_clock", screen="overtime"), load_layout(document)[0])
        self.assertEqual(reset_widget(document, "nope", screen="halftime"), load_layout(document)[0])

    def test_screen_descriptors_shape(self) -> None:
        descriptors = screen_descriptors()

        self.assertEqual([d["id"] for d in descriptors], list(SCREEN_IDS))
        for descriptor in descriptors:
            self.assertEqual(descriptor["label"], SCREEN_LABELS[descriptor["id"]])
            self.assertEqual(descriptor["kind"], SCREEN_KINDS[descriptor["id"]])
            self.assertTrue(descriptor["widgets"])
            for widget in descriptor["widgets"]:
                self.assertIn("id", widget)
                self.assertIn("label", widget)
                self.assertIn("default", widget)

        pregame = next(d for d in descriptors if d["id"] == "pregame")
        halftime = next(d for d in descriptors if d["id"] == "halftime")
        self.assertEqual([w["id"] for w in pregame["widgets"]], list(EVENT_WIDGET_IDS))
        self.assertEqual(pregame["widget_groups"], list(EVENT_WIDGET_GROUP_ORDER))
        pregame_defaults = {w["id"]: w["default"] for w in pregame["widgets"]}
        halftime_defaults = {w["id"]: w["default"] for w in halftime["widgets"]}
        # Phase and warmup differ in visibility between the two screens, so
        # each screen's descriptor must carry its *own* default, not borrow
        # the other screen's.
        self.assertFalse(pregame_defaults["event_phase"]["visible"])
        self.assertTrue(halftime_defaults["event_phase"]["visible"])

    def test_screen_preset_descriptors_are_valid_with_zero_warnings_and_unique_ids(self) -> None:
        by_screen = screen_preset_descriptors()

        self.assertEqual(set(by_screen), set(EVENT_SCREEN_IDS))
        self.assertEqual(len(by_screen["pregame"]), 6)
        self.assertEqual(len(by_screen["halftime"]), 6)
        self.assertEqual(
            [p["id"] for p in by_screen["pregame"]],
            ["pregame_classic", "pregame_matchup", "pregame_broadcast", "pregame_tigers",
             "pregame_stadium", "pregame_grid"],
        )
        self.assertEqual(
            [p["id"] for p in by_screen["halftime"]],
            ["halftime_classic", "halftime_score_first", "halftime_broadcast", "halftime_tigers",
             "halftime_stadium", "halftime_grid"],
        )

        game_preset_ids = {p["id"] for p in preset_descriptors()}
        all_ids = set(game_preset_ids)
        for screen_id, presets in by_screen.items():
            for preset in presets:
                with self.subTest(preset=preset["id"]):
                    self.assertNotIn(preset["id"], all_ids, "preset ids must be globally unique")
                    all_ids.add(preset["id"])

                    document = default_layout()
                    document["screens"][screen_id] = preset["screen"]
                    validation = validate_layout(document)
                    self.assertTrue(validation.ok, [i.message for i in validation.errors])
                    self.assertEqual(validation.warnings, (), preset["id"])

    def test_limits_reports_the_screens_and_event_widget_groups(self) -> None:
        reported = limits()

        self.assertEqual(
            reported["screens"],
            [{"id": s, "label": SCREEN_LABELS[s], "kind": SCREEN_KINDS[s]} for s in SCREEN_IDS],
        )
        self.assertEqual(reported["event_widget_groups"], list(EVENT_WIDGET_GROUP_ORDER))
        self.assertEqual(json.loads(json.dumps(reported, allow_nan=False)), reported)


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


class WidgetV2StyleTests(unittest.TestCase):
    """The ten new widget style properties (spec section 1.3)."""

    def test_the_defaults_reproduce_v1_exactly(self) -> None:
        for widget_id in WIDGET_IDS:
            widget = default_widget(widget_id)
            self.assertEqual(widget["font_family"], "arial")
            self.assertEqual(widget["letter_spacing"], 0.0)
            self.assertEqual(widget["text_transform"], "none")
            self.assertEqual(widget["text_effect"], "none")
            self.assertIsNone(widget["background"])
            self.assertEqual(widget["background_opacity"], 1.0)
            self.assertIsNone(widget["border_color"])
            self.assertEqual(widget["border_width"], 0.0)
            self.assertEqual(widget["corner_radius"], 0.0)
            self.assertEqual(widget["corner_cut"], 0.0)
            self.assertEqual(widget["cut_corners"], "all")
            self.assertEqual(widget["padding"], 0.0)

    def test_valid_style_values_are_accepted_and_normalised(self) -> None:
        validation = validate_layout(with_widget(
            widget_id="quarter", font_family="bahnschrift", letter_spacing=0.05,
            text_transform="uppercase", text_effect="shadow", background="#abc",
            background_opacity=0.5, border_color="#123456", border_width=0.01,
            corner_radius=0.02, corner_cut=0.015, cut_corners="top", padding=0.01,
        ))

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        widget = validation.layout["widgets"]["quarter"]
        self.assertEqual(widget["corner_cut"], 0.015)
        self.assertEqual(widget["cut_corners"], "top")
        self.assertEqual(widget["font_family"], "bahnschrift")
        self.assertEqual(widget["text_transform"], "uppercase")
        self.assertEqual(widget["text_effect"], "shadow")
        self.assertEqual(widget["background"], "#AABBCC")
        self.assertEqual(widget["border_color"], "#123456")

    def test_a_null_background_and_border_color_are_accepted(self) -> None:
        validation = validate_layout(with_widget(
            widget_id="quarter", background=None, border_color=None,
        ))

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        widget = validation.layout["widgets"]["quarter"]
        self.assertIsNone(widget["background"])
        self.assertIsNone(widget["border_color"])

    def test_invalid_style_values_are_refused_with_the_right_code(self) -> None:
        cases = [
            ("font_family", "papyrus", "FONT_FAMILY"),
            ("font_family", None, "FONT_FAMILY"),
            ("letter_spacing", -0.5, "LETTER_SPACING"),
            ("letter_spacing", 1.0, "LETTER_SPACING"),
            ("letter_spacing", "wide", "LETTER_SPACING"),
            ("text_transform", "smallcaps", "TEXT_TRANSFORM"),
            ("text_effect", "glow", "TEXT_EFFECT"),
            ("background", "not-a-color", "BACKGROUND"),
            ("background", 5, "BACKGROUND"),
            ("background_opacity", -0.1, "BACKGROUND_OPACITY"),
            ("background_opacity", 1.1, "BACKGROUND_OPACITY"),
            ("background_opacity", "opaque", "BACKGROUND_OPACITY"),
            ("border_color", "nope", "BORDER_COLOR"),
            ("border_width", -0.01, "BORDER_WIDTH"),
            ("border_width", 0.5, "BORDER_WIDTH"),
            ("corner_radius", -0.01, "CORNER_RADIUS"),
            ("corner_radius", 0.5, "CORNER_RADIUS"),
            ("corner_cut", -0.01, "CORNER_CUT"),
            ("corner_cut", 0.5, "CORNER_CUT"),
            ("cut_corners", "diagonal", "CUT_CORNERS"),
            ("cut_corners", 3, "CUT_CORNERS"),
            ("padding", -0.01, "PADDING"),
            ("padding", 0.5, "PADDING"),
        ]
        for prop, value, code in cases:
            with self.subTest(prop=prop, value=value):
                validation = validate_layout(with_widget(widget_id="quarter", **{prop: value}))
                self.assertFalse(validation.ok)
                self.assertIn(code, codes(validation))
                messages = " ".join(issue.message for issue in validation.errors)
                self.assertIn(WIDGET_LABELS["quarter"], messages)

    def test_an_unknown_widget_property_is_still_just_a_warning(self) -> None:
        """The new properties must not shrink what already-tolerated inputs
        are allowed to look like: a genuinely unknown key is still dropped
        with a warning, not treated as a style error.
        """

        validation = validate_layout(with_widget(widget_id="quarter", sparkle=True))

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("UNKNOWN_PROPERTY", warning_codes(validation))


class BackgroundTests(unittest.TestCase):
    def test_the_default_background_is_black(self) -> None:
        self.assertEqual(default_layout()["background"], {"color": "#000000"})

    def test_a_missing_background_defaults_with_a_warning(self) -> None:
        document = default_layout()
        del document["background"]

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("MISSING_BACKGROUND", warning_codes(validation))
        self.assertEqual(validation.layout["background"], {"color": "#000000"})

    def test_a_valid_background_colour_is_normalised(self) -> None:
        document = default_layout()
        document["background"] = {"color": "#abc"}

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(validation.warnings, ())
        self.assertEqual(validation.layout["background"], {"color": "#AABBCC"})

    def test_a_malformed_background_is_refused(self) -> None:
        for value in ([], "black", 4, True):
            with self.subTest(value=value):
                document = default_layout()
                document["background"] = value
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("BACKGROUND", codes(validation))

    def test_an_invalid_background_colour_is_refused(self) -> None:
        document = default_layout()
        document["background"] = {"color": "not-a-color"}

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("BACKGROUND", codes(validation))


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

    def test_an_element_never_collides_with_a_widget_or_another_element(self) -> None:
        """Elements are never overlap-checked (spec 1.4): a panel behind the
        scores, sized to match them exactly, is the whole point.
        """

        home_score = default_layout()["widgets"]["home_score"]
        document = with_elements(
            {"id": "panel_1", "type": "box", "x": home_score["x"], "y": home_score["y"],
             "width": home_score["width"], "height": home_score["height"]},
            {"id": "panel_2", "type": "box", "x": home_score["x"], "y": home_score["y"],
             "width": home_score["width"], "height": home_score["height"]},
        )

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
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

    def test_a_pre_f3_v3_layout_missing_both_status_widgets_loads_with_warnings_not_errors(self) -> None:
        """F3 (crowd-facing game-state messages) is an additive registry
        change (spec/DESIGN.md Part 1): LAYOUT_SCHEMA_VERSION stays 3, and a
        v3 layout saved before status_message/status_clock existed is simply
        "missing two widgets", which MISSING_WIDGET already treats as a
        warning to fill from the default -- never an error that would reject
        an operator's whole saved layout over a field that did not exist yet.
        """

        document = default_layout()
        del document["widgets"]["status_message"]
        del document["widgets"]["status_clock"]

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [issue.message for issue in validation.errors])
        warning_codes_by_widget = {
            issue.widget_id for issue in validation.warnings if issue.code == "MISSING_WIDGET"
        }
        self.assertEqual(warning_codes_by_widget, {"status_message", "status_clock"})
        self.assertEqual(validation.layout["widgets"]["status_message"], default_widget("status_message"))
        self.assertEqual(validation.layout["widgets"]["status_clock"], default_widget("status_clock"))
        self.assertTrue(validation.layout["widgets"]["status_message"]["visible"])
        self.assertTrue(validation.layout["widgets"]["status_clock"]["visible"])

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

    def test_it_repairs_element_geometry_the_same_way(self) -> None:
        document = with_elements(
            {"id": "text_1", "type": "text", "text": "HI", "x": 1.5, "y": -0.2,
             "width": 0.3, "height": 0.1},
            {"id": "box_1", "type": "box", "x": 1.5, "y": -0.2, "width": 0.3, "height": 0.1},
        )

        repaired, _issues = clamp_layout(document)

        safe = repaired["safe_area"]
        text_element = next(e for e in repaired["elements"] if e["id"] == "text_1")
        box_element = next(e for e in repaired["elements"] if e["id"] == "box_1")
        self.assertGreaterEqual(text_element["x"], safe["left"] - 1e-9)
        self.assertLessEqual(text_element["x"] + text_element["width"], 1 - safe["right"] + 1e-9)
        self.assertGreaterEqual(box_element["x"], -1e-9)
        self.assertLessEqual(box_element["x"] + box_element["width"], 1 + 1e-9)
        self.assertTrue(validate_layout(repaired).ok, [i.message for i in validate_layout(repaired).errors])

    def test_it_drops_an_element_with_no_usable_id_or_type(self) -> None:
        document = with_elements(
            {"type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            {"id": "box_1", "type": "not-a-type", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            {"id": "Bad-ID", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            {"id": "box_2", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        )

        repaired, _ = clamp_layout(document)

        self.assertEqual([e["id"] for e in repaired["elements"]], ["box_2"])

    def test_it_truncates_to_the_element_cap(self) -> None:
        document = with_elements(*[
            {"id": f"box_{i}", "type": "box", "x": 0.01, "y": 0.01, "width": 0.05, "height": 0.05}
            for i in range(MAX_ELEMENTS + 5)
        ])

        repaired, _ = clamp_layout(document)

        self.assertLessEqual(len(repaired["elements"]), MAX_ELEMENTS)


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

    def test_the_status_widgets_hide_on_an_absent_or_empty_value_and_show_otherwise(self) -> None:
        """F3 (crowd-facing game-state messages): status_message/status_clock
        are optional (OPTIONAL_WIDGET_IDS) precisely so the renderer hides
        them the instant their bound value is missing or empty -- which is
        the only thing keeping a crowd message off the wall before an
        operator ever raises one (see DESIGN.md's "Deliberate limits").
        `format_game_status`/`format_status_clock` return "" for "nothing to
        say", never raise, so the "field absent entirely" and "field present
        but empty" cases both have to hide -- this proves both.
        """

        # No "status" block at all -- the state before the other half of F3
        # adds it, and also a stored view model from before this feature.
        self.assertNotIn("status_message", set(supported_widget_ids({})))
        self.assertNotIn("status_clock", set(supported_widget_ids({})))

        # A "status" block present, but with nothing to show right now.
        cleared_model = {"status": {"label": None, "display": "", "clock_display": ""}}
        supported = set(supported_widget_ids(cleared_model))
        self.assertNotIn("status_message", supported)
        self.assertNotIn("status_clock", supported)

        # A raised message with its countdown running: both show.
        active_model = {"status": {"label": "TIMEOUT", "display": "TIMEOUT", "clock_display": "0:45"}}
        supported = set(supported_widget_ids(active_model))
        self.assertIn("status_message", supported)
        self.assertIn("status_clock", supported)


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


class ElementBasicTests(unittest.TestCase):
    """Section 1.4: elements are a list, missing is fine, wrong shape is not."""

    def test_missing_elements_is_fine_and_produces_no_warning(self) -> None:
        document = default_layout()
        del document["elements"]

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertEqual(validation.warnings, ())
        self.assertEqual(validation.layout["elements"], [])

    def test_elements_that_is_not_a_list_is_refused(self) -> None:
        for value in ({}, "text", 4, None):
            with self.subTest(value=value):
                document = default_layout()
                document["elements"] = value
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("ELEMENTS", codes(validation))

    def test_more_than_the_element_cap_is_refused(self) -> None:
        document = with_elements(*[
            {"id": f"box_{i}", "type": "box", "x": 0.01, "y": 0.01, "width": 0.05, "height": 0.05}
            for i in range(MAX_ELEMENTS + 1)
        ])

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("MAX_ELEMENTS", codes(validation))

    def test_exactly_the_element_cap_is_accepted(self) -> None:
        document = with_elements(*[
            {"id": f"box_{i}", "type": "box", "x": 0.01, "y": 0.01, "width": 0.03, "height": 0.03}
            for i in range(MAX_ELEMENTS)
        ])

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])

    def test_a_valid_box_element_round_trips(self) -> None:
        document = with_elements({
            "id": "backdrop", "type": "box", "x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0,
            "background": "#101820", "corner_radius": 0.01,
        })

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        element = validation.layout["elements"][0]
        self.assertEqual(element["id"], "backdrop")
        self.assertEqual(element["type"], "box")
        self.assertEqual(element["background"], "#101820")
        self.assertEqual(element["visible"], True)

    def test_element_ids_must_match_the_pattern(self) -> None:
        for bad_id in ("Box1", "1box", "box-1", "", "a" * 41, "box 1"):
            with self.subTest(bad_id=bad_id):
                document = with_elements({"id": bad_id, "type": "box", "x": 0.1, "y": 0.1,
                                          "width": 0.1, "height": 0.1})
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("ELEMENT_ID", codes(validation))

    def test_an_element_id_cannot_collide_with_a_widget_id(self) -> None:
        document = with_elements({"id": "home_score", "type": "box", "x": 0.1, "y": 0.1,
                                  "width": 0.1, "height": 0.1})

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("ELEMENT_ID", codes(validation))

    def test_duplicate_element_ids_are_refused(self) -> None:
        document = with_elements(
            {"id": "box_1", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
            {"id": "box_1", "type": "box", "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
        )

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("ELEMENT_ID", codes(validation))

    def test_an_unknown_element_type_is_refused(self) -> None:
        document = with_elements({"id": "thing_1", "type": "video", "x": 0.1, "y": 0.1,
                                  "width": 0.1, "height": 0.1})

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("ELEMENT_TYPE", codes(validation))

    def test_an_unknown_element_property_is_a_warning_naming_the_element(self) -> None:
        document = with_elements({"id": "box_1", "type": "box", "x": 0.1, "y": 0.1,
                                  "width": 0.1, "height": 0.1, "sparkle": True})

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        self.assertIn("UNKNOWN_PROPERTY", warning_codes(validation))
        messages = " ".join(i.message for i in validation.warnings)
        self.assertIn(element_label({"type": "box", "id": "box_1"}), messages)

    def test_element_opacity_is_validated(self) -> None:
        for value in (0.0, -0.1, 1.1, "opaque", None):
            with self.subTest(value=value):
                document = with_elements({"id": "box_1", "type": "box", "x": 0.1, "y": 0.1,
                                          "width": 0.1, "height": 0.1, "opacity": value})
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("OPACITY", codes(validation))

        document = with_elements({"id": "box_1", "type": "box", "x": 0.1, "y": 0.1,
                                  "width": 0.1, "height": 0.1, "opacity": 0.05})
        self.assertTrue(validate_layout(document).ok)


class ElementPlacementTests(unittest.TestCase):
    def test_a_text_element_must_sit_inside_the_safe_area(self) -> None:
        document = with_elements({"id": "text_1", "type": "text", "text": "HI",
                                  "x": 0.0, "y": 0.5, "width": 0.2, "height": 0.1})

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("OUTSIDE_SAFE_AREA", codes(validation))

    def test_an_image_or_box_may_cross_the_safe_area_but_not_the_canvas(self) -> None:
        # A full-bleed backdrop: outside the safe area, still inside the canvas.
        document = with_elements({"id": "backdrop", "type": "box", "x": 0.0, "y": 0.0,
                                  "width": 1.0, "height": 1.0})

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])

    def test_an_image_or_box_outside_the_canvas_is_refused(self) -> None:
        # x/y themselves are still bounded to 0..1 like a widget's (that is
        # what the COORDINATE check catches); OUTSIDE_CANVAS is specifically
        # about x+width / y+height running past the far edge.
        for change in ({"x": 0.9, "width": 0.3}, {"y": 0.9, "height": 0.3}):
            with self.subTest(change=change):
                element = {"id": "box_1", "type": "box", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}
                element.update(change)
                document = with_elements(element)
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("OUTSIDE_CANVAS", codes(validation))


class TextElementTests(unittest.TestCase):
    def test_a_valid_text_element_round_trips_with_its_defaults(self) -> None:
        document = with_elements({"id": "text_1", "type": "text", "text": "HOMECOMING",
                                  "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1})

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        element = validation.layout["elements"][0]
        self.assertEqual(element["text"], "HOMECOMING")
        self.assertEqual(element["color"], "#FFFFFF")
        self.assertEqual(element["font_scale"], 0.03)
        self.assertEqual(element["font_weight"], 700)
        self.assertEqual(element["font_family"], "arial")
        self.assertEqual(element["padding"], 0.0)

    def test_text_is_trimmed_and_length_checked(self) -> None:
        for value in ("", "   ", "x" * 121, 5, None, True):
            with self.subTest(value=value):
                document = with_elements({"id": "text_1", "type": "text", "text": value,
                                          "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1})
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("TEXT", codes(validation))

        exactly_max = with_elements({"id": "text_1", "type": "text", "text": "x" * MAX_TEXT_LENGTH,
                                     "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1})
        self.assertTrue(validate_layout(exactly_max).ok)

    def test_text_allows_up_to_three_line_breaks(self) -> None:
        ok_text = "a\nb\nc\nd"
        too_many = "a\nb\nc\nd\ne"
        ok_document = with_elements({"id": "text_1", "type": "text", "text": ok_text,
                                     "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2})
        bad_document = with_elements({"id": "text_1", "type": "text", "text": too_many,
                                      "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.2})

        self.assertTrue(validate_layout(ok_document).ok)
        bad_validation = validate_layout(bad_document)
        self.assertFalse(bad_validation.ok)
        self.assertIn("TEXT", codes(bad_validation))

    def test_control_characters_other_than_newline_are_refused(self) -> None:
        document = with_elements({"id": "text_1", "type": "text", "text": "bad\ttab",
                                  "x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1})

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("TEXT", codes(validation))

    def test_text_style_properties_reuse_the_widget_ranges(self) -> None:
        document = with_elements({
            "id": "text_1", "type": "text", "text": "HI", "x": 0.1, "y": 0.1,
            "width": 0.3, "height": 0.1, "font_family": "not-a-font",
        })

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("FONT_FAMILY", codes(validation))


class ImageElementTests(unittest.TestCase):
    def test_a_valid_png_data_uri_is_accepted(self) -> None:
        document = with_elements({"id": "image_1", "type": "image", "src": _PNG_DATA_URI,
                                  "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])
        element = validation.layout["elements"][0]
        self.assertEqual(element["src"], _PNG_DATA_URI)
        self.assertEqual(element["fit"], "contain")

    def test_a_valid_gif_data_uri_is_accepted(self) -> None:
        document = with_elements({"id": "image_1", "type": "image", "src": _GIF_DATA_URI,
                                  "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})

        validation = validate_layout(document)

        self.assertTrue(validation.ok, [i.message for i in validation.errors])

    def test_src_must_be_a_recognised_data_uri(self) -> None:
        for value in (
            "not-a-uri",
            "data:image/png;base64,not-valid-base64!!!",
            "data:text/plain;base64," + base64.b64encode(b"hello").decode(),
            5,
            None,
        ):
            with self.subTest(value=value):
                document = with_elements({"id": "image_1", "type": "image", "src": value,
                                          "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("IMAGE_SRC", codes(validation))

    def test_wrong_magic_bytes_are_refused_even_with_correct_encoding(self) -> None:
        """The declared media type in the URI must match the actual bytes --
        exercising the real base64 decode and magic-byte check, not a stub.
        """

        fake_png = base64.b64encode(b"NOT A REAL PNG PAYLOAD AT ALL").decode()
        document = with_elements({"id": "image_1", "type": "image",
                                  "src": f"data:image/png;base64,{fake_png}",
                                  "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})

        validation = validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("IMAGE_SRC", codes(validation))

    def test_an_oversize_image_is_refused_via_the_patched_limit(self) -> None:
        """Exercise the real per-image byte cap without building a 2 MB
        string: patch the module constant the check reads instead.
        """

        import scoreboard.presentation.layout as layout_module

        document = with_elements({"id": "image_1", "type": "image", "src": _PNG_DATA_URI,
                                  "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})

        with mock.patch.object(layout_module, "MAX_IMAGE_BYTES", 10):
            validation = layout_module.validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("IMAGE_TOO_LARGE", codes(validation))
        # Unpatched, the same tiny real PNG is well under the real cap.
        self.assertTrue(validate_layout(document).ok)

    def test_the_total_image_budget_is_enforced_via_the_patched_limit(self) -> None:
        import scoreboard.presentation.layout as layout_module

        document = with_elements(
            {"id": "image_1", "type": "image", "src": _PNG_DATA_URI,
             "x": 0.05, "y": 0.05, "width": 0.1, "height": 0.1},
            {"id": "image_2", "type": "image", "src": _GIF_DATA_URI,
             "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
        )

        with mock.patch.object(layout_module, "MAX_TOTAL_IMAGE_BYTES", 10):
            validation = layout_module.validate_layout(document)

        self.assertFalse(validation.ok)
        self.assertIn("IMAGES_TOO_LARGE", codes(validation))

    def test_fit_is_validated(self) -> None:
        for value in ("stretch", "", None, 5):
            with self.subTest(value=value):
                document = with_elements({"id": "image_1", "type": "image", "src": _PNG_DATA_URI,
                                          "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2,
                                          "fit": value})
                validation = validate_layout(document)
                self.assertFalse(validation.ok)
                self.assertIn("IMAGE_FIT", codes(validation))

        for value in IMAGE_FITS:
            document = with_elements({"id": "image_1", "type": "image", "src": _PNG_DATA_URI,
                                      "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2,
                                      "fit": value})
            self.assertTrue(validate_layout(document).ok, value)


class ElementLabelTests(unittest.TestCase):
    def test_it_names_each_element_type_the_way_an_operator_reads_it(self) -> None:
        self.assertEqual(element_label({"type": "text", "id": "t1", "text": "HOMECOMING"}),
                         'Text "HOMECOMING"')
        self.assertEqual(element_label({"type": "image", "id": "logo_1"}), "Image logo_1")
        self.assertEqual(element_label({"type": "box", "id": "panel_1"}), "Box panel_1")

    def test_element_constants_are_internally_consistent(self) -> None:
        self.assertEqual(set(ELEMENT_TYPES), {"text", "image", "box"})
        self.assertEqual(set(TEXT_TRANSFORMS), {"none", "uppercase"})
        self.assertEqual(set(TEXT_EFFECTS), {"none", "shadow", "outline"})
        self.assertEqual(set(IMAGE_FITS), {"contain", "cover", "fill"})


class ClampElementIdIsolationTests(unittest.TestCase):
    def test_a_valid_element_alongside_widgets_never_raises(self) -> None:
        for payload in (None, [], "text", {"elements": "no"}, {"elements": [1, 2, "x"]}):
            with self.subTest(payload=payload):
                repaired, _ = clamp_layout(payload)
                self.assertIn("elements", repaired)
                self.assertTrue(validate_layout(repaired).ok)


class PresetTests(unittest.TestCase):
    def test_every_preset_validates_clean_with_unique_ids(self) -> None:
        presets = preset_descriptors()

        self.assertEqual(len(presets), 6)
        self.assertEqual(
            [p["id"] for p in presets],
            ["classic", "broadcast", "big_score", "tigers", "stadium", "grid"],
        )
        seen_ids = set()
        for preset in presets:
            with self.subTest(preset=preset["id"]):
                for key in ("id", "name", "description", "layout"):
                    self.assertIn(key, preset)
                self.assertNotIn(preset["id"], seen_ids)
                seen_ids.add(preset["id"])

                validation = validate_layout(preset["layout"])
                self.assertTrue(validation.ok, [i.message for i in validation.errors])
                self.assertEqual(validation.warnings, (), preset["id"])
                self.assertEqual(preset["layout"]["name"], preset["name"])

    def test_every_preset_keeps_all_fifteen_widgets(self) -> None:
        for preset in preset_descriptors():
            with self.subTest(preset=preset["id"]):
                self.assertEqual(set(preset["layout"]["widgets"]), set(WIDGET_IDS))

    def test_the_classic_preset_is_exactly_the_default_layout(self) -> None:
        classic = next(p for p in preset_descriptors() if p["id"] == "classic")
        self.assertEqual(classic["layout"], default_layout("Classic"))

    def test_element_ids_are_unique_within_each_preset(self) -> None:
        for preset in preset_descriptors():
            with self.subTest(preset=preset["id"]):
                ids = [e["id"] for e in preset["layout"]["elements"]]
                self.assertEqual(len(ids), len(set(ids)))

    def test_each_preset_carries_its_matching_screens(self) -> None:
        """spec v3 section 1.4: classic keeps the default screens; broadcast,
        big_score, and tigers each carry the corresponding screen presets.
        """

        by_screen = screen_preset_descriptors()
        presets = {p["id"]: p["layout"] for p in preset_descriptors()}

        self.assertEqual(presets["classic"]["screens"]["pregame"], default_screen("pregame"))
        self.assertEqual(presets["classic"]["screens"]["halftime"], default_screen("halftime"))

        pregame_by_id = {p["id"]: p["screen"] for p in by_screen["pregame"]}
        halftime_by_id = {p["id"]: p["screen"] for p in by_screen["halftime"]}

        self.assertEqual(presets["broadcast"]["screens"]["pregame"], pregame_by_id["pregame_broadcast"])
        self.assertEqual(presets["broadcast"]["screens"]["halftime"], halftime_by_id["halftime_broadcast"])
        self.assertEqual(presets["big_score"]["screens"]["pregame"], pregame_by_id["pregame_matchup"])
        self.assertEqual(presets["big_score"]["screens"]["halftime"], halftime_by_id["halftime_score_first"])
        self.assertEqual(presets["tigers"]["screens"]["pregame"], pregame_by_id["pregame_tigers"])
        self.assertEqual(presets["tigers"]["screens"]["halftime"], halftime_by_id["halftime_tigers"])
        self.assertEqual(presets["stadium"]["screens"]["pregame"], pregame_by_id["pregame_stadium"])
        self.assertEqual(presets["stadium"]["screens"]["halftime"], halftime_by_id["halftime_stadium"])
        self.assertEqual(presets["grid"]["screens"]["pregame"], pregame_by_id["pregame_grid"])
        self.assertEqual(presets["grid"]["screens"]["halftime"], halftime_by_id["halftime_grid"])

    def test_the_tigers_preset_uses_the_brand_baseline_colours(self) -> None:
        tigers = next(p for p in preset_descriptors() if p["id"] == "tigers")
        layout = tigers["layout"]
        self.assertEqual(layout["background"]["color"], "#071B3A")
        self.assertEqual(layout["widgets"]["home_name"]["font_family"], "bahnschrift")
        self.assertEqual(layout["widgets"]["home_name"]["text_transform"], "uppercase")
        self.assertEqual(layout["widgets"]["possession"]["color"], "#FFB703")
        element_colors = {e["id"]: e.get("background") for e in layout["elements"]}
        self.assertIn("#C8242B", element_colors.values())
        self.assertIn("#0D2B5A", element_colors.values())


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


class ReviewHardeningTests(unittest.TestCase):
    """Bounds added after the v2 review: messages, decode work, and narrated
    element repairs.
    """

    def test_a_label_never_carries_more_than_a_line_of_raw_text(self) -> None:
        label = element_label({"type": "text", "id": "t1", "text": "X" * 10_000})

        self.assertLess(len(label), 60)
        self.assertTrue(label.endswith("\u2026\""))

    def test_an_image_that_cannot_fit_is_refused_before_it_is_decoded(self) -> None:
        document = default_layout()
        document["elements"] = [{
            "id": "img_1", "type": "image", "x": 0.0, "y": 0.0, "width": 0.2, "height": 0.2,
            "src": "data:image/png;base64," + "A" * 400,
        }]
        with mock.patch.object(layout_module, "MAX_IMAGE_BYTES", 10):
            with mock.patch.object(layout_module.base64, "b64decode") as decode:
                validation = validate_layout(document)

        self.assertIn("IMAGE_TOO_LARGE", codes(validation))
        decode.assert_not_called()

    def test_a_surplus_element_list_is_not_validated_past_the_limit(self) -> None:
        document = default_layout()
        document["elements"] = [
            {"id": f"box_{index}", "type": "box", "x": 0.0, "y": 0.0, "width": 0.1, "height": 0.1}
            for index in range(layout_module.MAX_ELEMENTS + 5)
        ]
        validation = validate_layout(document)

        self.assertIn("MAX_ELEMENTS", codes(validation))
        self.assertEqual({issue.code for issue in validation.errors}, {"MAX_ELEMENTS"})

    def test_fitting_an_element_says_what_it_moved(self) -> None:
        document = default_layout()
        document["elements"] = [{
            "id": "text_1", "type": "text", "text": "HELLO", "x": 0.95, "y": 0.5,
            "width": 0.2, "height": 0.1,
        }]
        repaired, issues = clamp_layout(document)

        self.assertEqual(repaired["elements"][0]["x"], 0.76)
        messages = [issue.message for issue in issues]
        self.assertTrue(any('Text "HELLO"' in message and "x was moved" in message for message in messages),
                        messages)
        self.assertTrue(all(issue.severity == "warning" for issue in issues))
