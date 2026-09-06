"""Contract test: board.js's data literals must equal the Python schema.

This is the "one source of truth" guarantee (spec section 7.5): `board.js`
declares WIDGET_IDS/WIDGET_FIELDS/WIDGET_TEXTS/OPTIONAL_WIDGET_IDS/
DEFAULT_LAYOUT as strict JSON literals so this test can lift them straight out
of the source text with a regex and compare them, with no browser involved,
against `scoreboard.presentation.layout`'s matching constants. If a future
edit lets the two drift, this test -- not a human re-reading two files -- is
what catches it.

This also checks the same house rules the browser suite checks on the
spectator page (no operator controls, no forbidden JS tokens), and that every
`WIDGET_FIELDS` path actually resolves to something in a real, fully
populated `spectator_view_model()` snapshot.
"""

from __future__ import annotations

import json
import re
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.presentation import layout

VIEWS_ROOT = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
BOARD_JS = VIEWS_ROOT / "shared" / "board.js"
SPECTATOR_JS = VIEWS_ROOT / "spectator" / "spectator.js"
SPECTATOR_HTML = VIEWS_ROOT / "spectator" / "index.html"

#: Forbidden tokens per spec section 7.4/7.5: JavaScript never derives a
#: displayed value, and never touches authoritative state.
_FORBIDDEN_TOKENS = (
    "Math.", "toFixed", "parseInt", "parseFloat", "setInterval",
    "revision++", "api.command",
)


def _extract_js_literal(source: str, name: str) -> Any:
    """Pull the strict-JSON value out of ``var NAME = <json>;`` in ``source``."""

    # The declarations look like ``var NAME = <json literal>;`` -- lift the
    # text between the first ``=`` after the name and the matching top-level
    # ``;`` that ends the statement.
    match = re.search(r"\bvar\s+" + re.escape(name) + r"\s*=\s*", source)
    if match is None:
        raise AssertionError(f"{name} is not declared with `var {name} = ...;` in board.js")
    start = match.end()
    depth = 0
    end = None
    for index in range(start, len(source)):
        char = source[index]
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
        elif char == ";" and depth == 0:
            end = index
            break
    if end is None:
        raise AssertionError(f"Could not find the end of the {name} literal in board.js")
    literal_text = source[start:end]
    return json.loads(literal_text)


class BoardJsDataContractTests(unittest.TestCase):
    """`board.js`'s five data constants must equal the Python schema exactly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = BOARD_JS.read_text(encoding="utf-8")

    def test_widget_ids_match_python_exactly_including_order(self):
        extracted = _extract_js_literal(self.source, "WIDGET_IDS")
        self.assertEqual(extracted, list(layout.WIDGET_IDS))

    def test_widget_fields_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "WIDGET_FIELDS")
        self.assertEqual(extracted, dict(layout.WIDGET_FIELDS))

    def test_widget_texts_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "WIDGET_TEXTS")
        self.assertEqual(extracted, dict(layout.WIDGET_TEXTS))

    def test_optional_widget_ids_match_python_as_a_set(self):
        # The JS side is a JSON array (JSON has no set type); the Python side
        # is a frozenset. Order carries no meaning for either, so compare as
        # sets, matching how OPTIONAL_WIDGET_IDS is actually used.
        extracted = _extract_js_literal(self.source, "OPTIONAL_WIDGET_IDS")
        self.assertEqual(set(extracted), set(layout.OPTIONAL_WIDGET_IDS))

    def test_default_layout_matches_python_default_layout(self):
        # DEFAULT_LAYOUT's own literal deliberately omits "screens" (schema
        # v3, spec section 2): it is assigned from the separately declared
        # DEFAULT_SCREENS literal right after DEFAULT_LAYOUT's closing `;` so
        # both stay pure JSON on their own. Merge them back together the same
        # way board.js does before comparing against the full Python document.
        extracted = _extract_js_literal(self.source, "DEFAULT_LAYOUT")
        screens = _extract_js_literal(self.source, "DEFAULT_SCREENS")
        self.assertNotIn("screens", extracted, "DEFAULT_LAYOUT's own literal must not itself carry \"screens\"")
        merged = dict(extracted)
        merged["screens"] = screens
        self.assertEqual(merged, layout.default_layout())

    def test_font_families_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "FONT_FAMILIES")
        self.assertEqual(extracted, dict(layout.FONT_FAMILIES))

    def test_event_widget_ids_match_python_exactly_including_order(self):
        extracted = _extract_js_literal(self.source, "EVENT_WIDGET_IDS")
        self.assertEqual(extracted, list(layout.EVENT_WIDGET_IDS))

    def test_event_widget_fields_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "EVENT_WIDGET_FIELDS")
        self.assertEqual(extracted, dict(layout.EVENT_WIDGET_FIELDS))

    def test_event_widget_texts_match_python_exactly(self):
        extracted = _extract_js_literal(self.source, "EVENT_WIDGET_TEXTS")
        self.assertEqual(extracted, dict(layout.EVENT_WIDGET_TEXTS))

    def test_event_optional_widget_ids_match_python_as_a_set(self):
        extracted = _extract_js_literal(self.source, "EVENT_OPTIONAL_WIDGET_IDS")
        self.assertEqual(sorted(extracted), sorted(layout.EVENT_OPTIONAL_WIDGET_IDS))

    def test_default_screens_match_python_default_layout_screens(self):
        extracted = _extract_js_literal(self.source, "DEFAULT_SCREENS")
        self.assertEqual(extracted, layout.default_layout()["screens"])


class SpectatorHouseRulesTests(unittest.TestCase):
    """The renderer stays presentation-only: no controls, no derived values."""

    def test_spectator_page_has_no_operator_controls(self):
        html = SPECTATOR_HTML.read_text(encoding="utf-8")
        for forbidden in ("<button", "<input", "<dialog", "data-command", "data-action"):
            self.assertNotIn(forbidden, html)

    def test_board_js_and_spectator_js_contain_no_forbidden_tokens(self):
        for path in (BOARD_JS, SPECTATOR_JS):
            source = path.read_text(encoding="utf-8")
            for forbidden in _FORBIDDEN_TOKENS:
                self.assertNotIn(forbidden, source, f"{forbidden!r} found in {path.name}")


class BoardJsRendersFreeElementsTests(unittest.TestCase):
    """v2 source-level checks: board.js knows how to place free elements, and
    no editing affordance from the layout editor has leaked into the shared
    renderer that also draws the spectator's LED wall (spec section 3)."""

    def test_board_js_contains_the_v2_element_markers(self):
        source = BOARD_JS.read_text(encoding="utf-8")
        for marker in ("data-item", "data-board-root", "data-element", "element-image"):
            self.assertIn(marker, source, f"{marker!r} not found in board.js")

    def test_board_js_and_board_css_contain_no_editing_affordance(self):
        board_js = BOARD_JS.read_text(encoding="utf-8").lower()
        board_css = (VIEWS_ROOT / "shared" / "board.css").read_text(encoding="utf-8").lower()
        for forbidden in ("handle", "guide", "drag", "resize"):
            self.assertNotIn(forbidden, board_js, f"{forbidden!r} found in board.js")
            self.assertNotIn(forbidden, board_css, f"{forbidden!r} found in board.css")


def _resolve_dotted_path(model: dict, path: str):
    node = model
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class WidgetFieldsResolveInARealViewModelTests(unittest.TestCase):
    """Every data-driven WIDGET_FIELDS path must resolve to real data.

    Built from a *fully populated* GameState -- every down/distance/
    possession/ball-on/timeouts value set to something other than the
    all-empty pregame defaults -- so this exercises the fields Agent B adds
    to ``_football_view`` (down_display, distance_display,
    possession_display, home_timeouts_display, away_timeouts_display),
    alongside the ones that already existed (ball_on_display, the clock and
    team fields).
    """

    def test_every_widget_field_resolves_to_a_non_none_value(self):
        state = GameState(
            lifecycle="IN_PROGRESS",
            quarter="3rd",
            home_name="TIGERS",
            away_name="EAGLES",
            home_score=14,
            away_score=7,
            game_clock=ClockValue(400.0, True, 720.0),
            play_clock=ClockValue(25.0, False, 40.0),
            play_clock_cleared=False,
            down=3,
            distance=7,
            possession="home",
            ball_on=BallSpot(team="away", yard_line=35),
            home_timeouts=2,
            away_timeouts=1,
        )
        model = spectator_view_model(state)

        for widget_id in layout.WIDGET_IDS:
            field = layout.WIDGET_FIELDS[widget_id]
            if field is None:
                # A static label: its text comes from WIDGET_TEXTS, not the
                # model, and WIDGET_TEXTS is checked by the JS/Python
                # contract test above.
                self.assertIn(widget_id, layout.WIDGET_TEXTS)
                continue
            value = _resolve_dotted_path(model, field)
            self.assertIsNotNone(
                value, f"{widget_id}'s field {field!r} resolved to None in a fully populated model"
            )


if __name__ == "__main__":
    unittest.main()


class EventBoardScoreTests(unittest.TestCase):
    """Pregame and halftime keep the score on the wall.

    Until September 5, 2026 the countdown board was hand-written HTML that
    carried only the phase, title, clock, and warmup note, so for a whole
    halftime the stadium's one scoreboard showed no score. Schema v3 (spec
    `.scratch/presentation-screens/spec.md` section 1.1/2) turns the
    countdown board into its own widget board -- the "event" registry --
    with home_name/home_score/away_name/away_score widgets bound to the same
    view-model paths the old markup bound. This pins that registry mapping,
    and pins that the spectator HTML no longer hand-writes any of this
    markup itself: board.js builds #event-board the same way it builds
    #game-board.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.js_source = BOARD_JS.read_text(encoding="utf-8")
        html = (VIEWS_ROOT / "spectator" / "index.html").read_text(encoding="utf-8")
        start = html.index('<section id="event-board"')
        end = html.index("</section>", start)
        cls.event_board_markup = html[start:end]

    def test_the_event_registry_binds_both_names_and_both_scores(self) -> None:
        event_widget_ids = _extract_js_literal(self.js_source, "EVENT_WIDGET_IDS")
        event_widget_fields = _extract_js_literal(self.js_source, "EVENT_WIDGET_FIELDS")
        for widget_id, field in (
            ("home_name", "teams.home.name"), ("home_score", "teams.home.score"),
            ("away_name", "teams.away.name"), ("away_score", "teams.away.score"),
        ):
            self.assertIn(widget_id, event_widget_ids)
            self.assertEqual(event_widget_fields[widget_id], field)

    def test_the_spectator_html_no_longer_hand_writes_the_event_board(self) -> None:
        # The section is empty markup filled in by board.js/spectator.js at
        # runtime, exactly like #game-board -- no more hand-written <p>
        # markup or data-field spans, and no inline script.
        self.assertNotIn("data-field", self.event_board_markup)
        self.assertNotIn("<p", self.event_board_markup)
        self.assertNotIn("<span", self.event_board_markup)
        self.assertNotIn("<script", self.event_board_markup)
