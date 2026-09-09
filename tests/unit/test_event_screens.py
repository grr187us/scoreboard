"""The Broadcast Welcome event screens and the schema that draws them.

Event-screens spec (``.scratch/event-screens/spec.md``) section 2: the
built-in pre-game and halftime defaults become the "Broadcast Welcome"
screens, "Kickoff Clock" and "Fifty Yard Line" join the screen presets, and
the layout engine gains a bundled condensed face, validated gradient fills,
bounded animations, rotation, vertical text, a dashed border style, a
``bleed`` flag, a bundled crest, and a ``ticker`` element. Everything here
is presentation-only and every new property has a default, so a v3 document
saved before any of it existed still validates with no warning.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.host.bridge import SpectatorBridge
from scoreboard.host.layout_bridge import LayoutLink
from scoreboard.presentation import layout as layout_module
from scoreboard.presentation.layout import (
    ANIMATION_MIN_SECONDS,
    ANIMATION_PRESETS,
    BLEED_MAX,
    BLEED_MAX_SIZE,
    BLEED_MIN,
    BORDER_STYLES,
    BUNDLED_IMAGES,
    BUNDLED_IMAGE_LABELS,
    ELEMENT_TYPES,
    EVENT_SCREEN_IDS,
    EVENT_WIDGET_IDS,
    FILL_KINDS,
    FONT_FAMILIES,
    FONT_FAMILY_LABELS,
    MAX_ANIMATION_SECONDS,
    MAX_ELEMENTS,
    MAX_FILL_STOPS,
    MAX_ROTATE_DEGREES,
    MAX_TICKER_LINES,
    MAX_TICKER_LINE_LENGTH,
    MIN_FILL_STOPS,
    ORIENTATIONS,
    TICKER_MODES,
    TICKER_SEPARATOR,
    TICKER_SPEED_RANGE,
    clamp_layout,
    default_layout,
    default_screen,
    default_screen_widget,
    element_label,
    limits,
    load_layout,
    preset_descriptors,
    screen_preset_descriptors,
    validate_layout,
)

#: Minimum type on these screens (spec section 1); never go below it.
MIN_EVENT_FONT_SCALE = 0.0188
SAFE = 0.04

#: Ids the browser suite targets (spec section 2.8), per preset id.
REQUIRED_ELEMENT_IDS = {
    "pregame_welcome": {"ticker", "light_sweep", "top_glow", "crest", "crest_plate",
                        "opponent_slot", "opponent_caption"},
    "halftime_welcome": {"ticker", "light_sweep", "top_glow"},
    "pregame_kickoff_clock": {"ticker", "crest", "crest_plate", "opponent_slot", "opponent_caption",
                              "home_bar", "away_bar"},
    "halftime_kickoff_clock": {"ticker", "crest", "crest_plate", "opponent_slot", "opponent_caption",
                               "home_bar", "away_bar"},
    "pregame_fifty": {"ticker", "yard_lines", "crest", "crest_plate", "opponent_slot", "opponent_caption"},
    "halftime_fifty": {"ticker", "yard_lines"},
}


def screen_presets() -> dict[str, dict]:
    return {
        preset["id"]: preset
        for presets in screen_preset_descriptors().values()
        for preset in presets
    }


def with_element(screen_id: str = "pregame", **element) -> dict:
    """A default document with one extra element on an event screen."""

    document = default_layout()
    document["screens"][screen_id]["elements"].append(element)
    return document


def with_widget(screen_id: str = "pregame", widget_id: str = "event_title", **changes) -> dict:
    document = default_layout()
    document["screens"][screen_id]["widgets"][widget_id].update(changes)
    return document


def box(**extra) -> dict:
    element = {"id": "probe", "type": "box", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2,
               "background": "#123456"}
    element.update(extra)
    return element


def text(**extra) -> dict:
    element = {"id": "probe", "type": "text", "text": "PROBE", "x": 0.1, "y": 0.1,
               "width": 0.2, "height": 0.1, "font_scale": 0.03}
    element.update(extra)
    return element


def image(**extra) -> dict:
    element = {"id": "probe", "type": "image", "src": "asset:tigers-crest", "x": 0.1, "y": 0.1,
               "width": 0.2, "height": 0.2}
    element.update(extra)
    return element


def ticker(**extra) -> dict:
    element = {"id": "probe", "type": "ticker", "lines": ["ONE", "TWO"], "x": 0.0, "y": 0.5,
               "width": 1.0, "height": 0.1}
    element.update(extra)
    return element


def error_codes(validation) -> set[str]:
    return {issue.code for issue in validation.errors}


def warning_codes(validation) -> set[str]:
    return {issue.code for issue in validation.warnings}


def probe(document: dict, screen_id: str = "pregame") -> dict:
    """The normalized ``probe`` element of a document that must validate."""

    validation = validate_layout(document)
    assert validation.ok, [i.message for i in validation.errors]
    return next(e for e in validation.layout["screens"][screen_id]["elements"] if e["id"] == "probe")


class ConstantsTests(unittest.TestCase):
    """Spec section 2.1: the exact names every agent hard-codes."""

    def test_element_types_and_fonts(self) -> None:
        self.assertEqual(ELEMENT_TYPES, ("text", "image", "box", "ticker"))
        families = list(FONT_FAMILIES)
        self.assertEqual(families.index("barlow_condensed"), families.index("bahnschrift_condensed") + 1)
        self.assertEqual(families.index("graduate"), families.index("varsity") + 1)
        self.assertEqual(FONT_FAMILIES["barlow_condensed"],
                         "'Barlow Condensed', 'Bahnschrift Condensed', Bahnschrift, Impact, sans-serif")
        self.assertEqual(FONT_FAMILIES["graduate"], "Graduate, Impact, 'Arial Black', sans-serif")
        self.assertEqual(FONT_FAMILY_LABELS["barlow_condensed"], "Barlow Condensed (bundled)")
        self.assertEqual(FONT_FAMILY_LABELS["graduate"], "Graduate (bundled)")
        self.assertEqual(set(FONT_FAMILY_LABELS), set(FONT_FAMILIES))

    def test_animation_fill_and_geometry_constants(self) -> None:
        self.assertEqual(ANIMATION_PRESETS, ("none", "sweep", "drift", "scroll_x", "marquee", "blink_soft"))
        self.assertEqual(ANIMATION_MIN_SECONDS,
                         {"sweep": 8.0, "drift": 6.0, "scroll_x": 10.0, "marquee": 20.0, "blink_soft": 1.0})
        self.assertEqual(MAX_ANIMATION_SECONDS, 120.0)
        self.assertEqual(FILL_KINDS, ("linear", "radial", "stripes"))
        self.assertEqual((MIN_FILL_STOPS, MAX_FILL_STOPS), (2, 4))
        self.assertEqual(BORDER_STYLES, ("solid", "dashed"))
        self.assertEqual(ORIENTATIONS, ("horizontal", "vertical", "vertical_flipped"))
        self.assertEqual(MAX_ROTATE_DEGREES, 180.0)
        self.assertEqual((BLEED_MIN, BLEED_MAX, BLEED_MAX_SIZE), (-0.5, 1.5, 2.0))

    def test_ticker_and_asset_constants(self) -> None:
        self.assertEqual(TICKER_MODES, ("scroll", "rotate"))
        self.assertEqual((MAX_TICKER_LINES, MAX_TICKER_LINE_LENGTH), (8, 80))
        self.assertEqual(TICKER_SPEED_RANGE, {"scroll": (20.0, 120.0), "rotate": (3.0, 60.0)})
        self.assertEqual(TICKER_SEPARATOR, "  •  ")
        self.assertEqual(BUNDLED_IMAGES, {"tigers-crest": "shared/img/tigers-crest.png"})
        self.assertEqual(BUNDLED_IMAGE_LABELS, {"tigers-crest": "TMSA Tigers crest"})

    def test_every_new_constant_is_exported(self) -> None:
        for name in ("ANIMATION_PRESETS", "ANIMATION_MIN_SECONDS", "MAX_ANIMATION_SECONDS", "FILL_KINDS",
                     "MIN_FILL_STOPS", "MAX_FILL_STOPS", "BORDER_STYLES", "ORIENTATIONS",
                     "MAX_ROTATE_DEGREES", "BLEED_MIN", "BLEED_MAX", "BLEED_MAX_SIZE", "TICKER_MODES",
                     "MAX_TICKER_LINES", "MAX_TICKER_LINE_LENGTH", "TICKER_SPEED_RANGE",
                     "TICKER_SEPARATOR", "BUNDLED_IMAGES", "BUNDLED_IMAGE_LABELS"):
            self.assertIn(name, layout_module.__all__, name)

    def test_limits_reports_every_new_key_json_safely(self) -> None:
        reported = limits()
        self.assertEqual(reported["animation_presets"], list(ANIMATION_PRESETS))
        self.assertEqual(reported["animation_min_seconds"], ANIMATION_MIN_SECONDS)
        self.assertEqual(reported["max_animation_seconds"], MAX_ANIMATION_SECONDS)
        self.assertEqual(reported["fill_kinds"], list(FILL_KINDS))
        self.assertEqual(reported["max_fill_stops"], MAX_FILL_STOPS)
        self.assertEqual(reported["border_styles"], list(BORDER_STYLES))
        self.assertEqual(reported["orientations"], list(ORIENTATIONS))
        self.assertEqual(reported["max_rotate_degrees"], MAX_ROTATE_DEGREES)
        self.assertEqual((reported["bleed_min"], reported["bleed_max"], reported["bleed_max_size"]),
                         (BLEED_MIN, BLEED_MAX, BLEED_MAX_SIZE))
        self.assertEqual(reported["ticker_modes"], list(TICKER_MODES))
        self.assertEqual(reported["max_ticker_lines"], MAX_TICKER_LINES)
        self.assertEqual(reported["max_ticker_line_length"], MAX_TICKER_LINE_LENGTH)
        self.assertEqual(reported["ticker_speed_range"], {"scroll": [20.0, 120.0], "rotate": [3.0, 60.0]})
        self.assertEqual(reported["bundled_images"],
                         [{"id": "tigers-crest", "label": "TMSA Tigers crest", "path": "shared/img/tigers-crest.png"}])
        self.assertEqual(json.loads(json.dumps(reported, allow_nan=False)), reported)


class DefaultScreensTests(unittest.TestCase):
    """Spec section 2.8 / acceptance 1: the defaults are the Welcome screens."""

    def test_the_defaults_are_the_welcome_presets_and_validate_with_zero_warnings(self) -> None:
        presets = screen_presets()
        for screen_id in EVENT_SCREEN_IDS:
            with self.subTest(screen=screen_id):
                screen = default_screen(screen_id)
                self.assertEqual(screen, presets[f"{screen_id}_welcome"]["screen"])
                self.assertEqual(screen["background"], {"color": "#071B3A"})
                self.assertTrue(screen["elements"], "the default screen is no longer bare")
                document = default_layout()
                validation = validate_layout(document)
                self.assertTrue(validation.ok, [i.message for i in validation.errors])
                self.assertEqual(validation.warnings, ())
                self.assertEqual(validation.layout, document, "the default must equal its own validation")

    def test_default_screen_widget_returns_the_welcome_widget(self) -> None:
        for screen_id in EVENT_SCREEN_IDS:
            screen = default_screen(screen_id)
            for widget_id in EVENT_WIDGET_IDS:
                self.assertEqual(default_screen_widget(screen_id, widget_id), screen["widgets"][widget_id])
        # The numerals are Graduate at 700 with the colon blink; the title is
        # amber Barlow Condensed (spec 2.8 pinned type).
        clock = default_screen_widget("pregame", "event_clock")
        self.assertEqual(clock["font_family"], "graduate")
        self.assertEqual(clock["font_weight"], 700)
        self.assertEqual(clock["animation"], {"preset": "blink_soft", "duration_seconds": 1.0})
        self.assertTrue(clock["fit_text"])
        self.assertEqual(default_screen_widget("pregame", "event_title")["font_family"], "barlow_condensed")
        # Pre-game hides the score; halftime shows everything.
        self.assertFalse(default_screen_widget("pregame", "home_score")["visible"])
        self.assertFalse(default_screen_widget("pregame", "event_phase")["visible"])
        self.assertTrue(default_screen_widget("halftime", "home_score")["visible"])
        self.assertTrue(default_screen_widget("halftime", "warmup")["visible"])

    def test_default_screen_widget_copies_are_independent(self) -> None:
        first = default_screen_widget("pregame", "event_clock")
        first["animation"]["duration_seconds"] = 99.0
        self.assertEqual(default_screen_widget("pregame", "event_clock")["animation"]["duration_seconds"], 1.0)

    def test_a_document_without_screens_gets_the_welcome_screens(self) -> None:
        document = default_layout()
        document.pop("screens")
        loaded, issues = load_layout(document)
        self.assertEqual({i.code for i in issues}, {"MISSING_SCREENS"})
        self.assertEqual(loaded["screens"]["pregame"], default_screen("pregame"))
        self.assertEqual(loaded["screens"]["halftime"], default_screen("halftime"))

    def test_the_game_preset_named_classic_carries_the_welcome_screens(self) -> None:
        classic = next(p for p in preset_descriptors() if p["id"] == "classic")
        self.assertEqual(classic["layout"]["screens"]["pregame"], default_screen("pregame"))


class ScreenPresetTests(unittest.TestCase):
    """Every one of the 18 presets validates clean, with the pinned ids."""

    def test_all_eighteen_presets_validate_with_zero_warnings_and_unique_ids(self) -> None:
        by_screen = screen_preset_descriptors()
        self.assertEqual(sum(len(p) for p in by_screen.values()), 18)
        for screen_id, presets in by_screen.items():
            for preset in presets:
                with self.subTest(preset=preset["id"]):
                    document = default_layout()
                    document["screens"][screen_id] = preset["screen"]
                    validation = validate_layout(document)
                    self.assertTrue(validation.ok, [i.message for i in validation.errors])
                    self.assertEqual(validation.warnings, ())
                    ids = [e["id"] for e in preset["screen"]["elements"]]
                    self.assertEqual(len(ids), len(set(ids)), "element ids must be unique")
                    self.assertLessEqual(len(ids), MAX_ELEMENTS)
                    self.assertTrue(set(ids).isdisjoint(EVENT_WIDGET_IDS))

    def test_the_pinned_names_and_descriptions(self) -> None:
        presets = screen_presets()
        for screen_id in EVENT_SCREEN_IDS:
            self.assertEqual(presets[f"{screen_id}_welcome"]["name"], "Broadcast Welcome")
            self.assertEqual(presets[f"{screen_id}_kickoff_clock"]["name"], "Kickoff Clock")
            self.assertEqual(presets[f"{screen_id}_fifty"]["name"], "Fifty Yard Line")
            self.assertEqual(presets[f"{screen_id}_classic"]["name"], "Classic")
            self.assertEqual(
                presets[f"{screen_id}_welcome"]["description"],
                "The built-in default: a broadcast-style welcome with the countdown, matchup "
                "and an announcement ticker.",
            )
            self.assertEqual(presets[f"{screen_id}_kickoff_clock"]["description"],
                             "Numeral-first: the countdown fills the board over rotated team bars.")
            self.assertEqual(presets[f"{screen_id}_fifty"]["description"],
                             "A scrolling field with end-zone bands and a framed countdown.")
            self.assertEqual(presets[f"{screen_id}_classic"]["description"],
                             "The original centred countdown arrangement.")

    def test_the_classic_preset_is_the_original_bare_screen(self) -> None:
        presets = screen_presets()
        for screen_id in EVENT_SCREEN_IDS:
            classic = presets[f"{screen_id}_classic"]["screen"]
            self.assertEqual(classic["background"], {"color": "#000000"})
            self.assertEqual(classic["elements"], [])
            clock = classic["widgets"]["event_clock"]
            self.assertEqual((clock["x"], clock["y"], clock["width"], clock["height"], clock["font_scale"]),
                             (0.10, 0.26, 0.80, 0.32, 0.140))
            self.assertEqual(clock["font_family"], "arial")
            self.assertFalse(clock["fit_text"])
            self.assertIsNone(clock["animation"])
            self.assertEqual(classic["widgets"]["event_phase"]["visible"], screen_id == "halftime")
        # The older presets still build on Classic, not on the new default.
        for preset_id in ("pregame_matchup", "pregame_broadcast", "pregame_tigers",
                          "halftime_score_first", "halftime_broadcast", "halftime_tigers"):
            self.assertEqual(presets[preset_id]["screen"]["widgets"]["event_title"]["font_family"], "arial",
                             preset_id)

    def test_the_browser_suite_ids_exist_where_the_screen_has_the_feature(self) -> None:
        presets = screen_presets()
        for preset_id, required in REQUIRED_ELEMENT_IDS.items():
            elements = {e["id"]: e for e in presets[preset_id]["screen"]["elements"]}
            with self.subTest(preset=preset_id):
                self.assertTrue(required <= set(elements), required - set(elements))
                self.assertEqual(elements["ticker"]["type"], "ticker")
                if "crest" in required:
                    self.assertEqual(elements["crest"]["type"], "image")
                    self.assertEqual(elements["crest"]["src"], "asset:tigers-crest")
                    self.assertEqual(elements["crest"]["fit"], "contain")
                    self.assertEqual(elements["crest_plate"]["background"], "#FFFFFF")
                if "opponent_slot" in required:
                    slot = elements["opponent_slot"]
                    self.assertEqual(slot["border_style"], "dashed")
                    self.assertEqual(slot["border_color"], "#DDE7F4")
                    self.assertEqual(slot["fill"]["kind"], "stripes")
                    caption = elements["opponent_caption"]
                    self.assertEqual(caption["text"], "OPPONENT\nLOGO")
                    self.assertEqual(caption["font_family"], "consolas")
                    self.assertEqual(caption["font_scale"], 0.0188)
                if "light_sweep" in required:
                    self.assertEqual(elements["light_sweep"]["animation"]["preset"], "sweep")
                    self.assertTrue(elements["light_sweep"]["bleed"])
                if "yard_lines" in required:
                    self.assertEqual(elements["yard_lines"]["animation"]["preset"], "scroll_x")
                    self.assertEqual(elements["yard_lines"]["fill"]["kind"], "stripes")
                    self.assertTrue(elements["yard_lines"]["bleed"])
                if "home_bar" in required:
                    for bar_id in ("home_bar", "away_bar"):
                        self.assertEqual(elements[bar_id]["type"], "box")

    def test_the_announcement_defaults(self) -> None:
        presets = screen_presets()
        pregame = presets["pregame_welcome"]["screen"]
        halftime = presets["halftime_welcome"]["screen"]
        pregame_ticker = next(e for e in pregame["elements"] if e["id"] == "ticker")
        halftime_ticker = next(e for e in halftime["elements"] if e["id"] == "ticker")
        self.assertEqual(pregame_ticker["lines"], [
            "WELCOME TO TIGER STADIUM", "SENIOR NIGHT — HONORING THE CLASS OF 2027",
            "CONCESSIONS OPEN BEHIND THE HOME STANDS", "NATIONAL ANTHEM AT 6:55", "SCIENCE · WISDOM · PEACE",
        ])
        self.assertEqual(halftime_ticker["lines"], [
            "SENIOR NIGHT — HONORING THE CLASS OF 2027", "TIGER BAND TAKES THE FIELD",
            "50/50 RAFFLE DRAWING AT THE START OF THE 3RD", "SCIENCE · WISDOM · PEACE",
        ])
        for line in pregame_ticker["lines"] + halftime_ticker["lines"]:
            self.assertLess(len(line), 60)
        for element in (pregame_ticker, halftime_ticker):
            self.assertEqual((element["x"], element["y"], element["width"], element["height"]),
                             (0.0, 0.89, 1.0, 0.10))
            self.assertEqual(element["vertical_align"], "middle")
            self.assertEqual(element["mode"], "scroll")
            self.assertEqual(element["speed_seconds"], 30.0)

    def test_every_glyph_is_inside_the_safe_area_at_the_minimum_size_or_larger(self) -> None:
        """Text and widgets inside the 4 % inset; nothing below 0.0188."""

        for preset_id, preset in screen_presets().items():
            screen = preset["screen"]
            with self.subTest(preset=preset_id):
                textual = [w for w in screen["widgets"].values()]
                textual += [e for e in screen["elements"] if e["type"] in ("text", "ticker")]
                for item in textual:
                    label = item.get("id")
                    if item.get("type") == "ticker":
                        # A ticker is bounded by the canvas; its ink is kept
                        # above the safe line by the middle alignment.
                        self.assertGreaterEqual(item["font_scale"], MIN_EVENT_FONT_SCALE, label)
                        continue
                    self.assertGreaterEqual(item["x"], SAFE - 1e-9, label)
                    self.assertGreaterEqual(item["y"], SAFE - 1e-9, label)
                    self.assertLessEqual(item["x"] + item["width"], 1 - SAFE + 1e-9, label)
                    self.assertLessEqual(item["y"] + item["height"], 1 - SAFE + 1e-9, label)
                    if preset_id.endswith(("_welcome", "_kickoff_clock", "_fifty")):
                        self.assertGreaterEqual(item["font_scale"], MIN_EVENT_FONT_SCALE, label)

    def test_the_new_screens_use_the_pinned_faces(self) -> None:
        presets = screen_presets()
        for preset_id in ("pregame_welcome", "halftime_welcome", "pregame_kickoff_clock",
                          "halftime_kickoff_clock", "pregame_fifty", "halftime_fifty"):
            screen = presets[preset_id]["screen"]
            with self.subTest(preset=preset_id):
                for widget_id in ("event_clock", "home_score", "away_score"):
                    self.assertEqual(screen["widgets"][widget_id]["font_family"], "graduate", widget_id)
                    self.assertEqual(screen["widgets"][widget_id]["font_weight"], 700)
                    self.assertTrue(screen["widgets"][widget_id]["fit_text"])
                for widget_id in ("event_title", "event_phase", "home_name", "away_name", "warmup"):
                    self.assertEqual(screen["widgets"][widget_id]["font_family"], "barlow_condensed", widget_id)
                self.assertEqual(screen["widgets"]["event_clock"]["animation"]["preset"], "blink_soft")
                for element in screen["elements"]:
                    self.assertNotEqual(element.get("font_family"), "varsity", element["id"])

    def test_no_stored_colour_is_anything_but_hex(self) -> None:
        for preset_id, preset in screen_presets().items():
            for element in preset["screen"]["elements"]:
                fill = element.get("fill")
                if not fill:
                    continue
                for stop in fill.get("stops", []):
                    self.assertRegex(stop["color"], r"^#[0-9A-F]{6}$", preset_id)
                if "color" in fill:
                    self.assertRegex(fill["color"], r"^#[0-9A-F]{6}$", preset_id)


class BorderStyleTests(unittest.TestCase):
    def test_default_valid_and_invalid_on_widgets_and_every_element_type(self) -> None:
        self.assertEqual(probe(with_element(**box()))["border_style"], "solid")
        self.assertEqual(probe(with_element(**box(border_style="dashed")))["border_style"], "dashed")
        self.assertEqual(probe(with_element(**text(border_style="dashed")))["border_style"], "dashed")
        self.assertEqual(probe(with_element(**image(border_style="dashed")))["border_style"], "dashed")
        self.assertEqual(probe(with_element(**ticker(border_style="dashed")))["border_style"], "dashed")
        validation = validate_layout(with_widget(border_style="dashed"))
        self.assertTrue(validation.ok)
        self.assertEqual(validation.layout["screens"]["pregame"]["widgets"]["event_title"]["border_style"], "dashed")
        self.assertEqual(validate_layout(default_layout()).layout["widgets"]["quarter"]["border_style"], "solid")
        for bad in ("dotted", 1, None, True):
            with self.subTest(value=bad):
                self.assertIn("BORDER_STYLE", error_codes(validate_layout(with_element(**box(border_style=bad)))))
                self.assertIn("BORDER_STYLE", error_codes(validate_layout(with_widget(border_style=bad))))


class AnimationTests(unittest.TestCase):
    def test_absent_null_and_none_normalize_to_null(self) -> None:
        self.assertIsNone(probe(with_element(**box()))["animation"])
        self.assertIsNone(probe(with_element(**box(animation=None)))["animation"])
        self.assertIsNone(probe(with_element(**box(animation={"preset": "none", "duration_seconds": 1})))["animation"])
        self.assertIsNone(validate_layout(default_layout()).layout["widgets"]["quarter"]["animation"])

    def test_a_valid_animation_keeps_exactly_two_keys_rounded(self) -> None:
        animation = {"preset": "sweep", "duration_seconds": 11.123456, "extra": "dropped"}
        self.assertEqual(probe(with_element(**box(animation=animation)))["animation"],
                         {"preset": "sweep", "duration_seconds": 11.1235})
        self.assertEqual(probe(with_element(**text(animation={"preset": "drift", "duration_seconds": 6})))["animation"],
                         {"preset": "drift", "duration_seconds": 6.0})
        self.assertEqual(probe(with_element(**image(animation={"preset": "drift", "duration_seconds": 6})))["animation"],
                         {"preset": "drift", "duration_seconds": 6.0})
        validation = validate_layout(with_widget(animation={"preset": "blink_soft", "duration_seconds": 1}))
        self.assertTrue(validation.ok)
        self.assertEqual(validation.layout["screens"]["pregame"]["widgets"]["event_title"]["animation"],
                         {"preset": "blink_soft", "duration_seconds": 1.0})

    def test_the_bounds_are_the_preset_minimum_and_the_global_maximum(self) -> None:
        for preset, minimum in ANIMATION_MIN_SECONDS.items():
            with self.subTest(preset=preset):
                ok = validate_layout(with_element(**box(animation={"preset": preset, "duration_seconds": minimum})))
                self.assertTrue(ok.ok, [i.message for i in ok.errors])
                top = validate_layout(with_element(**box(animation={"preset": preset, "duration_seconds": MAX_ANIMATION_SECONDS})))
                self.assertTrue(top.ok)
                too_fast = validate_layout(with_element(**box(animation={"preset": preset, "duration_seconds": minimum - 0.01})))
                self.assertEqual(error_codes(too_fast), {"ANIMATION"})
                too_slow = validate_layout(with_element(**box(animation={"preset": preset, "duration_seconds": MAX_ANIMATION_SECONDS + 1})))
                self.assertEqual(error_codes(too_slow), {"ANIMATION"})

    def test_any_other_shape_is_an_error(self) -> None:
        for bad in ("sweep", 3, True, [], {"preset": "spin", "duration_seconds": 10},
                    {"preset": "sweep"}, {"preset": "sweep", "duration_seconds": "10"},
                    {"preset": "sweep", "duration_seconds": float("nan")}, {"duration_seconds": 10}):
            with self.subTest(value=bad):
                self.assertEqual(error_codes(validate_layout(with_element(**box(animation=bad)))), {"ANIMATION"})
                self.assertEqual(error_codes(validate_layout(with_widget(animation=bad))), {"ANIMATION"})

    def test_a_ticker_may_not_animate(self) -> None:
        validation = validate_layout(with_element(**ticker(animation={"preset": "sweep", "duration_seconds": 10})))
        self.assertTrue(validation.ok)
        self.assertEqual(warning_codes(validation), {"UNKNOWN_PROPERTY"})


class OrientationAndRotationTests(unittest.TestCase):
    def test_orientation_on_widgets_and_text(self) -> None:
        self.assertEqual(probe(with_element(**text()))["orientation"], "horizontal")
        for orientation in ORIENTATIONS:
            self.assertEqual(probe(with_element(**text(orientation=orientation)))["orientation"], orientation)
            validation = validate_layout(with_widget(orientation=orientation))
            self.assertTrue(validation.ok)
            self.assertEqual(validation.layout["screens"]["pregame"]["widgets"]["event_title"]["orientation"], orientation)
        self.assertEqual(validate_layout(default_layout()).layout["widgets"]["quarter"]["orientation"], "horizontal")
        for bad in ("sideways", 90, None):
            self.assertEqual(error_codes(validate_layout(with_element(**text(orientation=bad)))), {"ORIENTATION"})
            self.assertEqual(error_codes(validate_layout(with_widget(orientation=bad))), {"ORIENTATION"})
        # Not a box or image property.
        self.assertEqual(warning_codes(validate_layout(with_element(**box(orientation="vertical")))), {"UNKNOWN_PROPERTY"})
        self.assertEqual(warning_codes(validate_layout(with_element(**image(orientation="vertical")))), {"UNKNOWN_PROPERTY"})

    def test_rotate_degrees_on_text_image_and_box(self) -> None:
        for make in (text, image, box):
            with self.subTest(kind=make.__name__):
                self.assertEqual(probe(with_element(**make()))["rotate_degrees"], 0.0)
                self.assertEqual(probe(with_element(**make(rotate_degrees=-13)))["rotate_degrees"], -13.0)
                self.assertEqual(probe(with_element(**make(rotate_degrees=12.34567)))["rotate_degrees"], 12.3457)
                self.assertEqual(probe(with_element(**make(rotate_degrees=MAX_ROTATE_DEGREES)))["rotate_degrees"], 180.0)
                for bad in (181, -180.5, "13", True, float("inf")):
                    self.assertEqual(error_codes(validate_layout(with_element(**make(rotate_degrees=bad)))), {"ROTATE"}, bad)
        self.assertEqual(warning_codes(validate_layout(with_element(**ticker(rotate_degrees=5)))), {"UNKNOWN_PROPERTY"})
        self.assertEqual(warning_codes(validate_layout(with_widget(rotate_degrees=5))), {"UNKNOWN_PROPERTY"})


class FillTests(unittest.TestCase):
    def test_absent_is_null_and_background_still_validates(self) -> None:
        self.assertIsNone(probe(with_element(**box()))["fill"])
        self.assertIsNone(probe(with_element(**box(fill=None)))["fill"])
        self.assertIn("BACKGROUND", error_codes(validate_layout(with_element(**box(
            background="red", fill={"kind": "linear", "angle": 90, "stops": [
                {"color": "#fff", "opacity": 0, "at": 0}, {"color": "#fff", "opacity": 1, "at": 1}]})))))

    def test_linear_radial_and_stripes_normalize_to_numbers_and_hex(self) -> None:
        linear = probe(with_element(**box(fill={"kind": "linear", "angle": 90.00001, "stops": [
            {"color": "#fff", "opacity": 0, "at": 0}, {"color": "#abc", "at": 0.5}, {"color": "#FFFFFF", "opacity": 0.06, "at": 1}]})))["fill"]
        self.assertEqual(linear, {"kind": "linear", "angle": 90.0, "stops": [
            {"color": "#FFFFFF", "opacity": 0.0, "at": 0.0},
            {"color": "#AABBCC", "opacity": 1.0, "at": 0.5},
            {"color": "#FFFFFF", "opacity": 0.06, "at": 1.0}]})
        radial = probe(with_element(**box(fill={"kind": "radial", "center_x": 0.5, "center_y": 0, "radius_x": 0.6,
                                                 "radius_y": 1, "stops": [{"color": "#2c62ab", "opacity": 0.5, "at": 0},
                                                                          {"color": "#2c62ab", "opacity": 0, "at": 0.72}]})))["fill"]
        self.assertEqual(radial, {"kind": "radial", "center_x": 0.5, "center_y": 0.0, "radius_x": 0.6, "radius_y": 1.0,
                                  "stops": [{"color": "#2C62AB", "opacity": 0.5, "at": 0.0},
                                            {"color": "#2C62AB", "opacity": 0.0, "at": 0.72}]})
        stripes = probe(with_element(**box(fill={"kind": "stripes", "angle": 45, "color": "#dde7f4", "opacity": 0.14,
                                                  "on": 0.002, "off": 0.008, "junk": 1})))["fill"]
        self.assertEqual(stripes, {"kind": "stripes", "angle": 45.0, "color": "#DDE7F4", "opacity": 0.14, "on": 0.002, "off": 0.008})

    def test_every_out_of_range_shape_is_a_single_fill_error(self) -> None:
        two_stops = [{"color": "#fff", "opacity": 1, "at": 0}, {"color": "#000", "opacity": 1, "at": 1}]
        bad_fills = [
            "linear", 3, [], {"kind": "conic"}, {"kind": "linear", "angle": 361, "stops": two_stops},
            {"kind": "linear", "angle": -1, "stops": two_stops},
            {"kind": "linear", "angle": 0, "stops": two_stops[:1]},
            {"kind": "linear", "angle": 0, "stops": two_stops * 3},
            {"kind": "linear", "angle": 0, "stops": [{"color": "white", "opacity": 1, "at": 0}, two_stops[1]]},
            {"kind": "linear", "angle": 0, "stops": [{"color": "#fff", "opacity": 2, "at": 0}, two_stops[1]]},
            {"kind": "linear", "angle": 0, "stops": [{"color": "#fff", "opacity": 1, "at": 0.9}, {"color": "#000", "opacity": 1, "at": 0.1}]},
            {"kind": "linear", "angle": 0, "stops": [{"color": "#fff", "opacity": 1}, two_stops[1]]},
            {"kind": "radial", "center_x": 1.5, "center_y": 0, "radius_x": 1, "radius_y": 1, "stops": two_stops},
            {"kind": "radial", "center_x": 0.5, "center_y": 0, "radius_x": 0.01, "radius_y": 1, "stops": two_stops},
            {"kind": "radial", "center_x": 0.5, "center_y": 0, "radius_x": 1, "radius_y": 2.5, "stops": two_stops},
            {"kind": "radial", "center_y": 0, "radius_x": 1, "radius_y": 1, "stops": two_stops},
            {"kind": "stripes", "angle": 90, "color": "#fff", "opacity": 1, "on": 0.0005, "off": 0.1},
            {"kind": "stripes", "angle": 90, "color": "#fff", "opacity": 1, "on": 0.6, "off": 0.1},
            {"kind": "stripes", "angle": 90, "color": "#fff", "opacity": 1, "on": 0.1, "off": 1.1},
            {"kind": "stripes", "angle": 90, "color": "rgba(1,2,3,.4)", "opacity": 1, "on": 0.1, "off": 0.1},
            {"kind": "stripes", "angle": 90, "color": "#fff", "opacity": True, "on": 0.1, "off": 0.1},
        ]
        for bad in bad_fills:
            with self.subTest(value=bad):
                self.assertEqual(error_codes(validate_layout(with_element(**box(fill=bad)))), {"FILL"})

    def test_fill_is_a_box_property_only(self) -> None:
        fill = {"kind": "linear", "angle": 0, "stops": [{"color": "#fff", "opacity": 1, "at": 0}, {"color": "#000", "opacity": 1, "at": 1}]}
        for make in (text, image, ticker):
            self.assertEqual(warning_codes(validate_layout(with_element(**make(fill=fill)))), {"UNKNOWN_PROPERTY"})
        self.assertEqual(warning_codes(validate_layout(with_widget(fill=fill))), {"UNKNOWN_PROPERTY"})


class BleedTests(unittest.TestCase):
    def test_default_false_keeps_the_canvas_rule(self) -> None:
        self.assertFalse(probe(with_element(**box()))["bleed"])
        # A negative coordinate is out of range outright when bleed is off.
        self.assertIn("COORDINATE", error_codes(validate_layout(with_element(**box(x=-0.01)))))
        self.assertIn("DIMENSION", error_codes(validate_layout(with_element(**box(height=1.6)))))
        self.assertIn("OUTSIDE_CANVAS", error_codes(validate_layout(with_element(**box(bleed=False, y=0.9, height=0.2)))))

    def test_a_bleed_box_may_overhang_within_the_widened_bounds(self) -> None:
        bar = probe(with_element(**box(bleed=True, x=-0.01, y=-0.30, width=0.07, height=1.60)))
        self.assertEqual((bar["x"], bar["y"], bar["width"], bar["height"], bar["bleed"]), (-0.01, -0.3, 0.07, 1.6, True))
        edge = probe(with_element(**box(bleed=True, x=BLEED_MIN, y=BLEED_MIN, width=BLEED_MAX_SIZE, height=BLEED_MAX_SIZE)))
        self.assertEqual(edge["x"], BLEED_MIN)
        loop = probe(with_element(**box(bleed=True, x=0, y=0, width=1.125, height=1)))
        self.assertEqual(loop["width"], 1.125)
        far = probe(with_element(**box(bleed=True, x=0.9, y=0.9, width=0.6, height=0.6)))
        self.assertEqual(far["x"] + far["width"], 1.5)

    def test_a_bleed_box_must_still_touch_the_canvas_and_stay_within_the_limits(self) -> None:
        for geometry in ({"x": 1.0, "width": 0.3}, {"x": -0.5, "width": 0.5}, {"y": 1.0, "height": 0.3},
                         {"y": -0.5, "height": 0.5}):
            with self.subTest(geometry=geometry):
                validation = validate_layout(with_element(**box(bleed=True, **geometry)))
                self.assertEqual(error_codes(validation), {"OUTSIDE_CANVAS"})
        self.assertIn("COORDINATE", error_codes(validate_layout(with_element(**box(bleed=True, x=-0.51)))))
        self.assertIn("COORDINATE", error_codes(validate_layout(with_element(**box(bleed=True, x=1.51, width=0.1)))))
        self.assertIn("DIMENSION", error_codes(validate_layout(with_element(**box(bleed=True, width=2.01)))))

    def test_bleed_must_be_a_bool_and_is_a_box_property_only(self) -> None:
        for bad in ("yes", 1, None):
            self.assertIn("BLEED", error_codes(validate_layout(with_element(**box(bleed=bad)))), bad)
        for make in (text, image, ticker):
            self.assertEqual(warning_codes(validate_layout(with_element(**make(bleed=True)))), {"UNKNOWN_PROPERTY"})

    def test_clamp_keeps_a_bleed_box_overhanging_and_keeps_the_new_properties(self) -> None:
        document = with_element(**box(bleed=True, x=-0.4, y=-0.3, width=0.5, height=1.6, rotate_degrees=13,
                                      animation={"preset": "drift", "duration_seconds": 9},
                                      fill={"kind": "linear", "angle": 90, "stops": [
                                          {"color": "#fff", "opacity": 0, "at": 0}, {"color": "#fff", "opacity": 1, "at": 1}]}))
        repaired, issues = clamp_layout(document)
        element = next(e for e in repaired["screens"]["pregame"]["elements"] if e["id"] == "probe")
        self.assertEqual((element["x"], element["y"], element["width"], element["height"]), (-0.4, -0.3, 0.5, 1.6))
        self.assertEqual(element["rotate_degrees"], 13)
        self.assertEqual(element["animation"]["preset"], "drift")
        self.assertEqual(element["fill"]["kind"], "linear")
        self.assertTrue(element["bleed"])
        self.assertEqual(issues, ())
        self.assertTrue(validate_layout(repaired).ok)
        # Dragged entirely off the canvas, it is pulled back to touch it, not inside it.
        gone, _ = clamp_layout(with_element(**box(bleed=True, x=1.4, y=0, width=0.5, height=0.5)))
        element = next(e for e in gone["screens"]["pregame"]["elements"] if e["id"] == "probe")
        self.assertLess(element["x"], 1.0)
        self.assertTrue(validate_layout(gone).ok, [i.message for i in validate_layout(gone).errors])
        # A plain box is still confined to the canvas by clamp.
        plain, _ = clamp_layout(with_element(**box(x=-0.4, width=0.5)))
        self.assertEqual(next(e for e in plain["screens"]["pregame"]["elements"] if e["id"] == "probe")["x"], 0.0)


class FitTextOnTextElementsTests(unittest.TestCase):
    def test_default_valid_invalid(self) -> None:
        self.assertFalse(probe(with_element(**text()))["fit_text"])
        self.assertTrue(probe(with_element(**text(fit_text=True)))["fit_text"])
        for bad in ("yes", 1, None):
            self.assertEqual(error_codes(validate_layout(with_element(**text(fit_text=bad)))), {"FIT_TEXT"})
        for make in (box, image, ticker):
            self.assertEqual(warning_codes(validate_layout(with_element(**make(fit_text=True)))), {"UNKNOWN_PROPERTY"})

    def test_a_widget_without_fit_text_takes_its_screen_default(self) -> None:
        document = default_layout()
        for widget in document["screens"]["pregame"]["widgets"].values():
            widget.pop("fit_text")
        for widget in document["widgets"].values():
            widget.pop("fit_text")
        validation = validate_layout(document)
        self.assertTrue(validation.ok)
        self.assertEqual(validation.warnings, ())
        self.assertEqual(validation.layout, default_layout())


class TickerTests(unittest.TestCase):
    def test_a_minimal_ticker_gets_the_text_defaults_and_scrolls_at_30(self) -> None:
        element = probe(with_element(**ticker()))
        self.assertEqual(element["type"], "ticker")
        self.assertEqual(element["lines"], ["ONE", "TWO"])
        self.assertEqual(element["mode"], "scroll")
        self.assertEqual(element["speed_seconds"], 30.0)
        self.assertEqual(element["color"], "#FFFFFF")
        self.assertEqual(element["font_scale"], 0.03)
        self.assertEqual(element["font_weight"], 700)
        self.assertEqual(element["font_family"], "arial")
        self.assertEqual(element["text_align"], "center")
        self.assertEqual(element["vertical_align"], "middle")
        self.assertEqual(element["border_style"], "solid")
        self.assertEqual(element["padding"], 0.0)
        for absent in ("animation", "orientation", "rotate_degrees", "fill", "bleed", "text", "fit_text"):
            self.assertNotIn(absent, element)
        self.assertEqual(probe(with_element(**ticker(mode="rotate")))["speed_seconds"], 5.0)

    def test_lines_are_trimmed_and_bounded(self) -> None:
        self.assertEqual(probe(with_element(**ticker(lines=["  A  ", "B" * MAX_TICKER_LINE_LENGTH])))["lines"],
                         ["A", "B" * MAX_TICKER_LINE_LENGTH])
        self.assertTrue(validate_layout(with_element(**ticker(lines=["X"] * MAX_TICKER_LINES))).ok)
        for bad in (None, [], "ONE", ["X"] * (MAX_TICKER_LINES + 1), ["B" * (MAX_TICKER_LINE_LENGTH + 1)],
                    ["   "], [""], ["ONE", 2], ["ONE\nTWO"], ["TAB\tHERE"]):
            with self.subTest(value=bad):
                document = with_element(**ticker())
                document["screens"]["pregame"]["elements"][-1]["lines"] = bad
                self.assertEqual(error_codes(validate_layout(document)), {"TICKER_LINES"})

    def test_mode_and_speed_ranges(self) -> None:
        for mode in TICKER_MODES:
            low, high = TICKER_SPEED_RANGE[mode]
            self.assertEqual(probe(with_element(**ticker(mode=mode, speed_seconds=low)))["speed_seconds"], low)
            self.assertEqual(probe(with_element(**ticker(mode=mode, speed_seconds=high)))["speed_seconds"], high)
            self.assertEqual(probe(with_element(**ticker(mode=mode, speed_seconds=low + 0.123456)))["speed_seconds"],
                             round(low + 0.123456, 4))
            for bad in (low - 0.01, high + 0.01, "30", True, float("nan")):
                self.assertEqual(error_codes(validate_layout(with_element(**ticker(mode=mode, speed_seconds=bad)))),
                                 {"TICKER_SPEED"}, (mode, bad))
        for bad in ("bounce", 1, None):
            self.assertEqual(error_codes(validate_layout(with_element(**ticker(mode=bad)))), {"TICKER_MODE"})
        # 5 s is legal for rotate but too fast for scroll.
        self.assertTrue(validate_layout(with_element(**ticker(mode="rotate", speed_seconds=5))).ok)
        self.assertEqual(error_codes(validate_layout(with_element(**ticker(mode="scroll", speed_seconds=5)))), {"TICKER_SPEED"})

    def test_bounds_are_the_canvas_with_the_widget_minimum_size(self) -> None:
        self.assertTrue(validate_layout(with_element(**ticker(x=0, y=0.9, width=1, height=0.1))).ok)
        self.assertIn("OUTSIDE_CANVAS", error_codes(validate_layout(with_element(**ticker(x=0, y=0.95, width=1, height=0.1)))))
        self.assertIn("MIN_DIMENSION", error_codes(validate_layout(with_element(**ticker(height=0.01)))))
        # A ticker may sit in the safe-area margin (a box may; text may not).
        self.assertTrue(validate_layout(with_element(**ticker(x=0, y=0, width=0.5, height=0.03))).ok)

    def test_the_label_names_the_first_line(self) -> None:
        self.assertEqual(element_label({"type": "ticker", "id": "t", "lines": ["WELCOME TO TIGER STADIUM TONIGHT"]}),
                         'Ticker "WELCOME TO TIGER STADIU…"')
        self.assertEqual(element_label({"type": "ticker", "id": "t", "lines": ["HELLO"]}), 'Ticker "HELLO"')
        self.assertEqual(element_label({"type": "ticker", "id": "t", "lines": "nope"}), 'Ticker ""')
        self.assertEqual(element_label({"type": "ticker", "id": "t"}), 'Ticker ""')
        validation = validate_layout(with_element(**ticker(lines=["GO TIGERS"], speed_seconds=1)))
        self.assertIn('Ticker "GO TIGERS"', validation.errors[0].message)

    def test_a_ticker_style_is_validated_like_text(self) -> None:
        self.assertIn("COLOR", error_codes(validate_layout(with_element(**ticker(color="blue")))))
        self.assertIn("FONT_FAMILY", error_codes(validate_layout(with_element(**ticker(font_family="comic")))))
        self.assertIn("FONT_SCALE", error_codes(validate_layout(with_element(**ticker(font_scale=0.5)))))
        self.assertIn("LETTER_SPACING", error_codes(validate_layout(with_element(**ticker(letter_spacing=0.5)))))


class AssetSourceTests(unittest.TestCase):
    def test_a_bundled_asset_is_accepted_and_costs_no_bytes(self) -> None:
        element = probe(with_element(**image()))
        self.assertEqual(element["src"], "asset:tigers-crest")
        self.assertEqual(element["fit"], "contain")
        # Forty crests together are still zero bytes against the 6 MB budget.
        document = default_layout()
        document["screens"]["pregame"]["elements"] = [
            dict(image(), id=f"crest_{i}", x=0.0, y=0.0, width=0.05, height=0.05) for i in range(MAX_ELEMENTS - 16)
        ]
        validation = validate_layout(document)
        self.assertTrue(validation.ok, [i.message for i in validation.errors])

    def test_an_unknown_or_malformed_asset_key_is_refused(self) -> None:
        for src in ("asset:unknown", "asset:", "asset:Tigers-Crest", "asset:../secret", "asset:tigers-crest.png",
                    "asset:" + "a" * 41):
            with self.subTest(src=src):
                validation = validate_layout(with_element(**image(src=src)))
                self.assertEqual(error_codes(validation), {"IMAGE_SRC"})
                self.assertIn("is not a bundled image", validation.errors[0].message)

    def test_data_uris_behave_exactly_as_before(self) -> None:
        self.assertEqual(error_codes(validate_layout(with_element(**image(src="https://example.com/x.png")))), {"IMAGE_SRC"})
        self.assertEqual(error_codes(validate_layout(with_element(**image(src="data:image/png;base64,####")))), {"IMAGE_SRC"})
        self.assertEqual(error_codes(validate_layout(with_element(**image(src=None)))), {"IMAGE_SRC"})


class ClampPassthroughTests(unittest.TestCase):
    def test_every_new_widget_property_survives_a_clamp(self) -> None:
        document = with_widget(x=-0.5, border_style="dashed", orientation="vertical", fit_text=False,
                               animation={"preset": "blink_soft", "duration_seconds": 2})
        repaired, issues = clamp_layout(document)
        widget = repaired["screens"]["pregame"]["widgets"]["event_title"]
        self.assertEqual(widget["x"], 0.04)
        self.assertEqual(widget["border_style"], "dashed")
        self.assertEqual(widget["orientation"], "vertical")
        self.assertFalse(widget["fit_text"])
        self.assertEqual(widget["animation"], {"preset": "blink_soft", "duration_seconds": 2})
        self.assertEqual({i.code for i in issues}, {"OUTSIDE_SAFE_AREA"})
        self.assertTrue(validate_layout(repaired).ok)

    def test_a_display_format_survives_a_clamp_on_the_game_screen(self) -> None:
        document = default_layout()
        document["widgets"]["quarter"].update({"display_format": "ordinal", "x": 2.0})
        repaired, _ = clamp_layout(document)
        self.assertEqual(repaired["widgets"]["quarter"]["display_format"], "ordinal")

    def test_ticker_properties_survive_a_clamp(self) -> None:
        repaired, _ = clamp_layout(with_element(**ticker(y=0.95, height=0.1, mode="rotate", speed_seconds=7)))
        element = next(e for e in repaired["screens"]["pregame"]["elements"] if e["id"] == "probe")
        self.assertEqual((element["y"], element["height"]), (0.9, 0.1))
        self.assertEqual((element["lines"], element["mode"], element["speed_seconds"]), (["ONE", "TWO"], "rotate", 7))
        self.assertTrue(validate_layout(repaired).ok)


class OlderDocumentTests(unittest.TestCase):
    """Acceptance 7: an operator's saved v3 layout keeps its own screens."""

    def strip_new_keys(self, screen: dict) -> dict:
        for widget in screen["widgets"].values():
            for key in ("border_style", "animation", "orientation"):
                widget.pop(key, None)
        return screen

    def test_a_v3_document_from_before_these_properties_loads_clean_and_keeps_its_screens(self) -> None:
        document = default_layout()
        for widget in document["widgets"].values():
            for key in ("border_style", "animation", "orientation"):
                widget.pop(key)
        document["screens"] = {
            screen_id: self.strip_new_keys(layout_module._classic_event_screen(screen_id))
            for screen_id in EVENT_SCREEN_IDS
        }
        document["screens"]["pregame"]["elements"] = [
            {"id": "note", "type": "text", "text": "GO TIGERS", "x": 0.3, "y": 0.6, "width": 0.4, "height": 0.08},
            {"id": "bar", "type": "box", "x": 0.0, "y": 0.95, "width": 1.0, "height": 0.05, "background": "#C8242B"},
        ]
        before = json.loads(json.dumps(document))

        loaded, issues = load_layout(document)

        self.assertEqual(issues, ())
        self.assertEqual(document, before, "loading must not mutate the caller's document")
        pregame = loaded["screens"]["pregame"]
        self.assertEqual(pregame["background"], {"color": "#000000"})
        self.assertEqual([e["id"] for e in pregame["elements"]], ["note", "bar"])
        self.assertNotIn("ticker", [e["id"] for e in pregame["elements"]])
        clock = pregame["widgets"]["event_clock"]
        self.assertEqual((clock["x"], clock["y"], clock["font_scale"]), (0.10, 0.26, 0.140))
        self.assertEqual(clock["font_family"], "arial")
        # Every new property took its default; nothing rendered differently.
        for widget in list(pregame["widgets"].values()) + list(loaded["widgets"].values()):
            self.assertEqual(widget["border_style"], "solid")
            self.assertIsNone(widget["animation"])
            self.assertEqual(widget["orientation"], "horizontal")
        note, bar = pregame["elements"]
        self.assertEqual((note["fit_text"], note["animation"], note["orientation"], note["rotate_degrees"]),
                         (False, None, "horizontal", 0.0))
        self.assertEqual((bar["fill"], bar["animation"], bar["rotate_degrees"], bar["bleed"]), (None, None, 0.0, False))
        self.assertEqual(loaded["screens"]["halftime"]["widgets"]["event_phase"]["visible"], True)

    def test_a_v2_document_upgrades_onto_the_welcome_screens(self) -> None:
        document = default_layout()
        document["schema_version"] = 2
        document.pop("screens")
        loaded, issues = load_layout(document)
        self.assertEqual({i.code for i in issues}, {"SCHEMA_UPGRADED"})
        self.assertEqual(loaded["screens"], default_layout()["screens"])


class MotionSwitchPureTests(unittest.TestCase):
    """The JS-independent parts of the motion switch (spec section 2.9)."""

    def test_the_bare_link_publishes_nothing_and_never_raises(self) -> None:
        self.assertIsNone(LayoutLink().publish_motion(True))
        self.assertIsNone(LayoutLink().publish_motion(False))

    def test_a_spectator_bridge_defaults_to_motion_on(self) -> None:
        self.assertIs(SpectatorBridge(lambda: {}).get_motion(), True)
        self.assertIs(SpectatorBridge(lambda: {}, read_motion=lambda: False).get_motion(), False)
        self.assertIs(SpectatorBridge(lambda: {}, read_motion=lambda: 0).get_motion(), False)
        self.assertEqual(json.dumps(SpectatorBridge(lambda: {}).get_motion()), "true")
        self.assertFalse(hasattr(SpectatorBridge(lambda: {}), "set_motion"))


if __name__ == "__main__":
    unittest.main()
