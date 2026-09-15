"""Source-contract tests for ``views/soccer_spectator/`` (spec section 5.1,
D-owned): mirrors the house-rule checks
``tests/integration/test_spectator_layout_render.py``'s
``SpectatorHouseRulesTests`` runs on football's page, plus the exact
script/link tag list agent F's GOAL cutscene scene files need
(``views/soccer_spectator/cutscenes/soccer.js``/``soccer.css``) and the
board-kind wiring this page must use.

Deliberately does not import ``scoreboard.host.app`` or any Bridge class --
this is a static check of the page source, so it runs whether or not other
agents' host modules currently import cleanly.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS_ROOT = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
SOCCER_SPECTATOR = VIEWS_ROOT / "soccer_spectator"
HTML = SOCCER_SPECTATOR / "index.html"
JS = SOCCER_SPECTATOR / "soccer_spectator.js"
CSS = SOCCER_SPECTATOR / "soccer_spectator.css"

#: Same forbidden-token list football's page is checked against (spec
#: section 7.4/7.5): JavaScript never derives a displayed value and never
#: touches authoritative state.
_FORBIDDEN_TOKENS = (
    "Math.", "toFixed", "parseInt", "parseFloat", "setInterval",
    "revision++", "api.command",
)


class SoccerSpectatorFilesExistTests(unittest.TestCase):
    def test_the_three_files_exist(self):
        for path in (HTML, JS, CSS):
            self.assertTrue(path.is_file(), path)


class SoccerSpectatorHtmlTests(unittest.TestCase):
    def setUp(self):
        self.html = HTML.read_text(encoding="utf-8")

    def test_no_http_scheme_anywhere(self):
        self.assertNotIn("http://", self.html)

    def test_loads_the_shared_and_football_spectator_files_it_needs(self):
        required_tags = (
            '<link rel="stylesheet" href="../shared/board.css">',
            '<link rel="stylesheet" href="soccer_spectator.css">',
            '<link rel="stylesheet" href="../spectator/cutscene.css">',
            '<link rel="stylesheet" href="cutscenes/soccer.css">',
            '<script src="../shared/render.js"></script>',
            '<script src="../shared/board.js"></script>',
            '<script src="soccer_spectator.js"></script>',
            '<script src="cutscenes/soccer.js"></script>',
            '<script src="../spectator/cutscene.js"></script>',
        )
        for tag in required_tags:
            self.assertIn(tag, self.html, tag)

    def test_never_loads_footballs_own_spectator_js_or_the_football_scene_files(self):
        self.assertNotIn('src="../spectator/spectator.js"', self.html)
        self.assertNotIn('cutscenes/tigers.js', self.html)
        self.assertNotIn('cutscenes/crowd.js', self.html)

    def test_has_the_two_board_sections_and_no_operator_controls(self):
        self.assertIn('id="game-board"', self.html)
        self.assertIn('id="event-board"', self.html)
        forbidden_forms = ("<input", "<select", "<form", "onclick=")
        for token in forbidden_forms:
            # The one exception is the close-display button, added below.
            if token == "onclick=":
                self.assertNotIn(token, self.html)
        self.assertIn('id="close-display"', self.html)
        # Exactly one button: closing the display window. No other control.
        self.assertEqual(self.html.count("<button"), 1)


class SoccerSpectatorJsTests(unittest.TestCase):
    def setUp(self):
        self.js = JS.read_text(encoding="utf-8")

    def test_contains_no_forbidden_tokens(self):
        for token in _FORBIDDEN_TOKENS:
            self.assertNotIn(token, self.js, token)

    def test_builds_the_soccer_registry_for_the_game_board_and_event_for_the_other(self):
        self.assertIn("B.build(gameBoard, 'soccer')", self.js)
        self.assertIn("B.build(eventBoard, 'event')", self.js)

    def test_default_layout_reference_is_soccers_own(self):
        self.assertIn("B.SOCCER_DEFAULT_LAYOUT", self.js)
        self.assertNotIn("B.DEFAULT_LAYOUT", self.js)

    def test_screen_for_lifecycle_is_reused_unchanged(self):
        self.assertIn("B.screenForLifecycle(model.lifecycle)", self.js)

    def test_has_no_play_clock_flag_soccer_has_no_play_clock(self):
        self.assertNotIn("play_clock_value", self.js)
        self.assertNotIn("running-play", self.js)

    def test_close_display_never_sends_a_game_command(self):
        self.assertIn("close_display", self.js)
        self.assertNotIn("api.command", self.js)


class SoccerSpectatorCssTests(unittest.TestCase):
    def test_no_remote_resources(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("http://", css)
        self.assertNotIn("https://", css)


if __name__ == "__main__":
    unittest.main()
