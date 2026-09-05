"""The editor window is presentation-only by construction, not by convention.

These are static checks on the shipped page. They exist because the strongest
guarantee this feature can offer is structural: there is no code path from the
layout editor to a game command, and a test that reads the file is the thing
that keeps it that way as the page grows.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from scoreboard.domain.commands import CommandType
from scoreboard.host.layout_bridge import LayoutEditorBridge
from scoreboard.presentation.layout import WIDGET_IDS, WIDGET_LABELS

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
EDITOR = VIEWS / "layout"

EDITABLE_PROPERTIES = frozenset({
    "visible", "x", "y", "width", "height", "font_scale", "color",
    "text_align", "vertical_align", "font_weight", "z_index",
})


class EditorPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (EDITOR / "index.html").read_text(encoding="utf-8")
        cls.script = (EDITOR / "layout.js").read_text(encoding="utf-8")
        cls.style = (EDITOR / "layout.css").read_text(encoding="utf-8")

    def test_the_three_files_exist_and_are_not_empty(self) -> None:
        for path in (EDITOR / "index.html", EDITOR / "layout.js", EDITOR / "layout.css"):
            self.assertTrue(path.is_file(), path)
            self.assertGreater(path.stat().st_size, 0, path)

    def test_every_asset_the_page_references_is_on_disk(self) -> None:
        references = re.findall(r'(?:src|href)="([^"]+)"', self.html)
        self.assertTrue(references)
        for reference in references:
            self.assertFalse(reference.startswith(("http:", "https:", "//")),
                             f"{reference} must not be fetched from a network")
            resolved = (EDITOR / reference).resolve()
            self.assertTrue(resolved.is_file(), f"{reference} does not exist")

    def test_it_reuses_the_real_spectator_renderer(self) -> None:
        """The preview must be the same renderer, not a second implementation."""

        self.assertIn("../shared/board.js", self.html)
        self.assertIn("../shared/board.css", self.html)
        self.assertIn("ScoreboardBoard", self.script)
        self.assertNotIn("data-widget=", self.html,
                         "widget markup is built by board.js, never duplicated here")


def code_only(script: str) -> str:
    """The script with its comments removed.

    The checks below are about what the editor *does*, not what it says about
    itself: the module comment legitimately names ``bridge.command()`` to
    explain that no such call exists.
    """

    without_blocks = re.sub(r"/\*.*?\*/", " ", script, flags=re.S)
    return re.sub(r"(?m)//.*$", " ", without_blocks)


class NoGameCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (EDITOR / "index.html").read_text(encoding="utf-8")
        cls.script = (EDITOR / "layout.js").read_text(encoding="utf-8")
        cls.code = code_only(cls.script)

    def test_the_page_carries_no_command_control(self) -> None:
        self.assertNotIn("data-command", self.html)

    def test_the_script_never_calls_a_game_command(self) -> None:
        self.assertNotIn("api.command", self.code, "the editor must not submit a command")
        self.assertNotIn(".command(", self.code, "the editor must not submit a command")
        # And the comment that explains the rule is still there to explain it.
        self.assertIn("never calls a game command", self.script)

    def test_no_command_name_appears_anywhere_in_the_editor(self) -> None:
        for command in CommandType:
            self.assertNotIn(command.value, self.html, f"{command.value} in the page")
            self.assertNotIn(command.value, self.code, f"{command.value} in the script")

    def test_it_calls_only_real_methods_of_the_editor_bridge(self) -> None:
        available = {name for name in dir(LayoutEditorBridge) if not name.startswith("_")}
        called = set(re.findall(r"api\.([a-z_]+)\s*\(", code_only(self.script)))

        self.assertTrue(called, "the editor must talk to its bridge")
        self.assertTrue(called.issubset(available),
                        f"unknown bridge methods: {sorted(called - available)}")

    def test_it_says_plainly_what_it_cannot_change(self) -> None:
        self.assertIn("never changes", self.html.lower())
        for word in ("scores", "clocks"):
            self.assertIn(word, self.html.lower())


class ControlCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (EDITOR / "index.html").read_text(encoding="utf-8")
        cls.script = (EDITOR / "layout.js").read_text(encoding="utf-8")

    def test_there_is_a_control_for_every_editable_property(self) -> None:
        declared = set(re.findall(r'data-prop="([a-z_]+)"', self.html))

        self.assertEqual(declared, EDITABLE_PROPERTIES)

    def test_the_widget_list_is_generated_rather_than_hard_coded(self) -> None:
        """Adding a widget in Python must not need an edit to this page."""

        for widget_id in WIDGET_IDS:
            self.assertNotIn(f'"{widget_id}"', self.html, widget_id)
            self.assertNotIn(f"'{widget_id}'", self.html, widget_id)
        for label in WIDGET_LABELS.values():
            self.assertNotIn(label, self.html, label)
        self.assertIn("data-select-widget", self.script)

    def test_the_limits_come_from_python_rather_than_from_literals(self) -> None:
        for key in ("min_font_scale", "max_font_scale", "min_widget_width",
                    "min_widget_height", "text_alignments", "vertical_alignments",
                    "font_weights"):
            self.assertIn(key, self.script, key)

    def test_it_offers_reset_save_and_discard(self) -> None:
        for action in ("save", "save_as_open", "discard", "reset_widget",
                       "reset_layout_confirm", "clamp"):
            self.assertIn(f'data-action="{action}"', self.html, action)

    def test_position_is_reachable_without_typing_a_number(self) -> None:
        """The point of direct manipulation: every geometry change has a
        pointing or keying route that does not involve the number fields."""

        for action in ("nudge_up", "nudge_down", "nudge_left", "nudge_right"):
            self.assertIn(f'data-action="{action}"', self.html, action)
        for action in ("raise", "lower"):
            self.assertIn(f'data-action="{action}"', self.html, action)
        self.assertIn("data-handle", self.script,
                      "resize handles are built by the script")
        for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"):
            self.assertIn(key, self.script, key)
        self.assertIn("pointerdown", self.script, "widgets must be draggable")
        self.assertIn("shiftKey", self.script, "Shift must give a coarser nudge")

    def test_the_number_fields_survive_as_the_precise_fallback(self) -> None:
        """Demoted, not removed: an operator still needs an exact value."""

        self.assertIn('<details class="precise"', self.html)
        for prop in ("x", "y", "width", "height", "z_index"):
            self.assertIn(f'data-prop="{prop}"', self.html, prop)

    def test_the_shared_renderer_grows_no_editing_affordance(self) -> None:
        """Handles and guides belong to the editor's own layers.

        board.js is the spectator window's renderer too. An editing handle
        that leaked into it would be drawn on the LED wall.
        """

        board = (VIEWS / "shared" / "board.js").read_text(encoding="utf-8")
        board_css = (VIEWS / "shared" / "board.css").read_text(encoding="utf-8")
        for forbidden in ("data-handle", "handle", "guide", "drag", "resize"):
            self.assertNotIn(forbidden, board.lower(), forbidden)
            self.assertNotIn(forbidden, board_css.lower(), forbidden)
        self.assertIn('id="handles"', self.html)
        self.assertIn('id="guides"', self.html)

    def test_it_uses_no_blocking_browser_dialog(self) -> None:
        """A modal in a webview blocks the window; the page asks inline instead."""

        for forbidden in ("window.prompt", "window.alert", "window.confirm",
                          "prompt(", "alert(", "confirm("):
            self.assertNotIn(forbidden, self.script, forbidden)

    def test_it_derives_no_displayed_value(self) -> None:
        """No formatting, no rounding of a value, no clock of its own.

        `Math.` was on this list until direct manipulation arrived. It cannot
        stay: a drag produces a pointer event per frame, and converting those
        pixels into canvas fractions, snapping them to a grid, and holding
        them inside the safe area is arithmetic that has to happen in the
        browser -- a bridge round trip per frame is not available. What the
        rule was actually protecting is untouched, and is still asserted
        here and in the two tests below: the editor formats nothing, derives
        no displayed value, and runs no clock. Every string in the preview
        still arrives already formatted in the view model.
        """

        for forbidden in ("toFixed", "parseInt", "parseFloat", "setInterval"):
            self.assertNotIn(forbidden, self.script, forbidden)

    def test_its_only_arithmetic_is_canvas_geometry(self) -> None:
        """Rounding a coordinate is allowed; anything cleverer is not."""

        used = set(re.findall(r"Math\.([a-zA-Z]+)", code_only(self.script)))
        self.assertTrue(used, "the gesture layer is expected to do geometry")
        self.assertEqual(used, {"round"},
                         f"unexpected Math use in the editor: {sorted(used - {'round'})}")

    def test_it_reads_no_formatted_value_out_of_the_view_model(self) -> None:
        """The snapshot is passed to the renderer whole, never picked apart.

        This is the assertion that really carries the old rule: if the editor
        never touches a `.display` or `_display` field, it cannot be
        re-deriving one, whatever arithmetic it does on rectangles.
        """

        code = code_only(self.script)
        for forbidden in (".display", "_display", ".seconds", ".score"):
            self.assertNotIn(forbidden, code, forbidden)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
