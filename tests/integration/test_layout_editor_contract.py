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

    def test_it_uses_no_blocking_browser_dialog(self) -> None:
        """A modal in a webview blocks the window; the page asks inline instead."""

        for forbidden in ("window.prompt", "window.alert", "window.confirm",
                          "prompt(", "alert(", "confirm("):
            self.assertNotIn(forbidden, self.script, forbidden)

    def test_it_derives_no_displayed_value(self) -> None:
        for forbidden in ("toFixed", "parseInt", "parseFloat", "setInterval", "Math."):
            self.assertNotIn(forbidden, self.script, forbidden)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
