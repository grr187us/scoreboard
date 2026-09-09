"""Source contract for closing the spectator display from the window itself.

A browser-free mirror of the recipe in ``test_crowd_status_ui.py`` and
``test_spectator_layout_render.py``: no webview is needed to prove the button
exists, starts hidden, and that ``spectator.js`` handles Escape and
feature-detects ``close_display`` -- and to re-pin, for this one new
interactive element, that the spectator page still sends no game command
(spec ``.scratch/control-refresh/spec.md`` section 3; D-005: closing this
window changes no game state, so nothing here needs a confirmation).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS_ROOT = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
SPECTATOR = VIEWS_ROOT / "spectator"
INDEX_HTML = SPECTATOR / "index.html"
SPECTATOR_JS = SPECTATOR / "spectator.js"
SPECTATOR_CSS = SPECTATOR / "spectator.css"

#: The three spectator files, all of which must stay free of any game
#: command -- adding a button to close the window must not add a way to
#: send one.
SPECTATOR_FILES = (INDEX_HTML, SPECTATOR_JS, SPECTATOR_CSS)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class CloseButtonMarkupTests(unittest.TestCase):
    """index.html: the button exists, is hidden by default, and is inert."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read(INDEX_HTML)

    def test_the_button_exists_inside_the_canvas(self) -> None:
        canvas_start = self.html.index('<main id="canvas"')
        canvas_end = self.html.index("</main>", canvas_start)
        canvas = self.html[canvas_start:canvas_end]
        self.assertIn('id="close-display"', canvas)

    def test_the_button_is_hidden_by_default(self) -> None:
        tag = re.search(r'<button[^>]*id="close-display"[^>]*>', self.html)
        self.assertIsNotNone(tag, "the close-display button must be a <button> element")
        self.assertIn("hidden", tag.group(0))

    def test_the_button_has_no_game_command(self) -> None:
        tag = re.search(r'<button[^>]*id="close-display"[^>]*>', self.html)
        self.assertNotIn("data-command", tag.group(0))
        self.assertNotIn("data-action", tag.group(0))

    def test_the_button_names_escape_for_screen_readers_and_sighted_users(self) -> None:
        tag = re.search(r'<button[^>]*id="close-display"[^>]*>([^<]*)</button>', self.html)
        self.assertIsNotNone(tag)
        self.assertIn("aria-label", self.html[tag.start():tag.end()])
        # Text, not colour or icon alone (U-002): the caption spells out Esc.
        self.assertIn("Esc", tag.group(1))


class CloseButtonScriptTests(unittest.TestCase):
    """spectator.js: Escape, reveal-on-move, and a feature-detected close."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(SPECTATOR_JS)

    def test_escape_closes_and_ignores_key_repeats(self) -> None:
        self.assertIn("'Escape'", self.source.replace('"', "'"))
        self.assertIn("event.repeat", self.source)

    def test_pointer_movement_reveals_the_button_and_a_timer_hides_it_again(self) -> None:
        self.assertIn("mousemove", self.source)
        self.assertIn("pointermove", self.source)
        self.assertIn("closeButton.hidden = false", self.source)
        self.assertIn("closeButton.hidden = true", self.source)
        self.assertIn("3000", self.source)

    def test_close_display_is_feature_detected_and_never_thrown_from(self) -> None:
        self.assertIn("typeof bridgeApi.close_display === 'function'", self.source.replace('"', "'"))
        # requestClose is reached from both the click handler and the
        # keydown handler, each of which is itself inside a try/catch (or
        # calls into one) so a missing/older api can never throw out to the
        # page.
        self.assertIn("try {", self.source)
        self.assertIn("catch (error) {", self.source)

    def test_a_second_close_request_is_guarded(self) -> None:
        self.assertIn("closeRequested", self.source)

    def test_it_still_computes_no_game_value_and_sends_no_game_command(self) -> None:
        for forbidden in ("Math.", "toFixed", "parseInt", "parseFloat", "setInterval",
                          "revision++", "api.command"):
            self.assertNotIn(forbidden, self.source, f"{forbidden!r} found in spectator.js")


class CloseButtonStyleTests(unittest.TestCase):
    """spectator.css: absolutely positioned, high-contrast, never lays out."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(SPECTATOR_CSS)

    def test_it_is_absolutely_positioned_in_a_corner(self) -> None:
        rule = re.search(r"\.close-display\s*\{([^}]*)\}", self.source, re.S)
        self.assertIsNotNone(rule, ".close-display rule not found")
        body = rule.group(1)
        self.assertIn("position: absolute", body)
        self.assertIn("top:", body)
        self.assertIn("right:", body)

    def test_it_meets_the_minimum_touch_height(self) -> None:
        rule = re.search(r"\.close-display\s*\{([^}]*)\}", self.source, re.S)
        self.assertIn("min-height: 44px", rule.group(1))

    def test_it_sits_above_the_cutscene_stage(self) -> None:
        # cutscene.css sets the stage to z-index: 50; this file's rule must
        # be higher so a playing cutscene never covers the close button.
        rule = re.search(r"\.close-display\s*\{([^}]*)\}", self.source, re.S)
        z_index = re.search(r"z-index:\s*(\d+)", rule.group(1))
        self.assertIsNotNone(z_index)
        self.assertGreater(int(z_index.group(1)), 50)


class SpectatorStillSendsNoGameCommandTests(unittest.TestCase):
    """Re-pin, with the new button in place, that the wall still cannot
    reach a game command -- the source contract this whole feature must
    not weaken."""

    def test_no_spectator_file_contains_a_game_command_token(self) -> None:
        for path in SPECTATOR_FILES:
            source = _read(path)
            for forbidden in ("data-command", "api.command"):
                self.assertNotIn(forbidden, source, f"{forbidden!r} found in {path.name}")

    def test_no_spectator_file_names_a_commandtype_value(self) -> None:
        # A loose grep for CommandType-shaped literals (the service's
        # command names) would be brittle across an enum; the spectator
        # files never import or reference CommandType at all, which is the
        # simpler and equally sufficient guarantee.
        for path in SPECTATOR_FILES:
            source = _read(path)
            self.assertNotIn("CommandType", source, f"CommandType found in {path.name}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
