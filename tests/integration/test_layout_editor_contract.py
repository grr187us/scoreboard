"""The editor window is presentation-only by construction, not by convention.

These are static checks on the shipped page. They exist because the strongest
guarantee this feature can offer is structural: there is no code path from the
layout editor to a game command, and a test that reads the file is the thing
that keeps it that way as the page grows.

v2 splits the editor's JavaScript across four files (`layout.js`,
`editor-state.js`, `editor-canvas.js`, `editor-panels.js`) that share one
`window.LayoutEditor` namespace. Every check below that used to read just
`layout.js` now reads all four -- concatenated into ``ALL_SCRIPT`` -- so
splitting the file cannot quietly weaken a guarantee that used to apply to
the whole script.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import scoreboard.presentation.layout as layout_module
from scoreboard.domain.commands import CommandType
from scoreboard.host.layout_bridge import LayoutEditorBridge
from scoreboard.presentation.layout import WIDGET_IDS, WIDGET_LABELS

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
EDITOR = VIEWS / "layout"

#: Every JavaScript file this window ships, in load order. Kept as a literal
#: list (rather than a glob) so a stray extra .js file must be added here on
#: purpose before its contents count toward any of the guarantees below.
SCRIPT_FILES = ("layout.js", "editor-state.js", "editor-canvas.js", "editor-panels.js")

EDITABLE_PROPERTIES = frozenset({
    # v1 widget properties.
    "visible", "x", "y", "width", "height", "font_scale", "color",
    "text_align", "vertical_align", "font_weight", "z_index",
    # v2 widget/element style properties (spec section 1.3).
    "font_family", "letter_spacing", "text_transform", "text_effect",
    "background", "background_opacity", "border_color", "border_width",
    "corner_radius", "padding", "display_format", "fit_text", "corner_cut", "cut_corners",
    # Element-only properties (spec section 1.4).
    "text", "opacity", "fit",
})


def read_scripts() -> dict[str, str]:
    return {name: (EDITOR / name).read_text(encoding="utf-8") for name in SCRIPT_FILES}


def code_only(script: str) -> str:
    """The script with its comments removed.

    The checks below are about what the editor *does*, not what it says about
    itself: a module comment legitimately names ``bridge.command()`` to
    explain that no such call exists.
    """

    without_blocks = re.sub(r"/\*.*?\*/", " ", script, flags=re.S)
    return re.sub(r"(?m)//.*$", " ", without_blocks)


class EditorPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (EDITOR / "index.html").read_text(encoding="utf-8")
        cls.scripts = read_scripts()
        cls.script = "\n".join(cls.scripts[name] for name in SCRIPT_FILES)
        cls.style = (EDITOR / "layout.css").read_text(encoding="utf-8")

    def test_the_editor_files_exist_and_are_not_empty(self) -> None:
        paths = [EDITOR / "index.html", EDITOR / "layout.css"] + [EDITOR / name for name in SCRIPT_FILES]
        for path in paths:
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

    def test_the_scripts_share_one_namespace(self) -> None:
        for name in SCRIPT_FILES:
            self.assertIn("LayoutEditor", self.scripts[name], name)


class NoGameCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (EDITOR / "index.html").read_text(encoding="utf-8")
        cls.scripts = read_scripts()
        cls.script = "\n".join(cls.scripts[name] for name in SCRIPT_FILES)
        cls.code = code_only(cls.script)

    def test_the_page_carries_no_command_control(self) -> None:
        self.assertNotIn("data-command", self.html)

    def test_the_script_never_calls_a_game_command(self) -> None:
        self.assertNotIn("api.command", self.code, "the editor must not submit a command")
        self.assertNotIn(".command(", self.code, "the editor must not submit a command")
        # And the comment that explains the rule is still there to explain it.
        self.assertIn("never calls a game command", self.scripts["layout.js"])

    def test_no_command_name_appears_anywhere_in_the_editor(self) -> None:
        for command in CommandType:
            self.assertNotIn(command.value, self.html, f"{command.value} in the page")
            self.assertNotIn(command.value, self.code, f"{command.value} in the script")

    def test_no_lowercase_undo_appears_anywhere(self) -> None:
        """History is `history_back`/`history_forward`; visible labels use the
        capitalized words "Undo"/"Redo" only. Python's `in` is case-sensitive,
        so this is a stronger, un-comment-stripped check than the CommandType
        scan above: the lowercase word must not occur even in a comment."""

        self.assertNotIn("undo", self.html)
        for name in SCRIPT_FILES:
            self.assertNotIn("undo", self.scripts[name], name)

    def test_it_calls_only_real_methods_of_the_editor_bridge(self) -> None:
        available = {name for name in dir(LayoutEditorBridge) if not name.startswith("_")}
        called = set(re.findall(r"api\.([a-z_]+)\s*\(", self.code))

        self.assertTrue(called, "the editor must talk to its bridge")
        self.assertTrue(called.issubset(available),
                        f"unknown bridge methods: {sorted(called - available)}")

    def test_no_event_countdown_prefix_appears_anywhere(self) -> None:
        """The event screens' widgets (event_phase, event_title, event_clock)
        sit one prefix away from the real command family
        (event_countdown_select/_start/_stop/_reset/_correct). The per-value
        scan above already covers each full command name; this checks the
        shared prefix itself, so a typo that drops a suffix cannot slip a
        command-shaped identifier past the per-value check."""

        self.assertNotIn("event_countdown", self.html)
        for name in SCRIPT_FILES:
            self.assertNotIn("event_countdown", self.scripts[name], name)

    def test_it_says_plainly_what_it_cannot_change(self) -> None:
        self.assertIn("never changes", self.html.lower())
        for word in ("scores", "clocks"):
            self.assertIn(word, self.html.lower())


class ControlCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (EDITOR / "index.html").read_text(encoding="utf-8")
        cls.scripts = read_scripts()
        cls.script = "\n".join(cls.scripts[name] for name in SCRIPT_FILES)

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

    def test_it_offers_a_screen_switcher(self) -> None:
        """The Game/Pre-game/Halftime tablist (spec section 3): an empty
        container in the HTML, populated with `data-screen="<id>"` buttons
        generated from `state.screens` at runtime -- so no screen id ever
        needs to be a literal in the page itself."""

        self.assertIn('id="screen-switch"', self.html)
        self.assertIn('role="tablist"', self.html)
        self.assertIn("data-screen", self.script)

    def test_screen_presets_are_available(self) -> None:
        """Pre-game and Halftime each apply from `state.screen_presets`,
        the per-screen counterpart to the Game screen's `state.presets`."""

        self.assertIn("screen_presets", self.script)

    def test_reset_widget_passes_the_current_screen(self) -> None:
        """`reset_widget` now resets one widget on one screen: the bridge
        call must carry the widget id, the whole draft, and which screen,
        exactly `api.reset_widget(id, draft, screen)`."""

        code = code_only(self.script)
        match = re.search(r"api\.reset_widget\(([^)]*)\)", code)
        self.assertIsNotNone(match, "the editor must call api.reset_widget(...)")
        args = [part.strip() for part in match.group(1).split(",")]
        self.assertEqual(len(args), 3,
                          f"reset_widget must be called with (id, draft, screen); got {args}")

    def test_no_event_widget_or_screen_label_literal_in_html(self) -> None:
        """Generalizes `test_the_widget_list_is_generated_rather_than_hard_coded`
        to the event registry and the screen labels added for pre-game/
        halftime: none of them may be hard-coded in the page either.

        Depends on Agent A's schema v3 registries; skips until they land.
        """

        event_widget_ids = getattr(layout_module, "EVENT_WIDGET_IDS", None)
        event_widget_labels = getattr(layout_module, "EVENT_WIDGET_LABELS", None)
        screen_labels = getattr(layout_module, "SCREEN_LABELS", None)
        if event_widget_ids is None or event_widget_labels is None or screen_labels is None:
            self.skipTest(
                "depends on Agent A's schema v3 registries (EVENT_WIDGET_IDS/"
                "EVENT_WIDGET_LABELS/SCREEN_LABELS), not yet landed"
            )
        for widget_id in event_widget_ids:
            self.assertNotIn(f'"{widget_id}"', self.html, widget_id)
            self.assertNotIn(f"'{widget_id}'", self.html, widget_id)
        for label in event_widget_labels.values():
            self.assertNotIn(label, self.html, label)
        for label in screen_labels.values():
            self.assertNotIn(label, self.html, label)

    def test_the_limits_come_from_python_rather_than_from_literals(self) -> None:
        for key in ("min_font_scale", "max_font_scale", "min_widget_width",
                    "min_widget_height", "text_alignments", "vertical_alignments",
                    "font_weights", "font_families", "text_transforms", "text_effects",
                    "image_fits", "widget_groups", "max_text_length", "max_image_bytes"):
            self.assertIn(key, self.script, key)

    def test_it_offers_reset_save_and_discard(self) -> None:
        for action in ("save", "save_as_open", "discard", "reset_widget",
                       "reset_layout_confirm", "clamp"):
            self.assertIn(f'data-action="{action}"', self.html, action)

    def test_it_offers_history_back_and_forward(self) -> None:
        for action in ("history_back", "history_forward"):
            self.assertIn(f'data-action="{action}"', self.html, action)
        self.assertIn("Undo", self.html)
        self.assertIn("Redo", self.html)

    def test_it_offers_rename_duplicate_and_delete_for_stored_layouts(self) -> None:
        for action in ("rename_layout_open", "duplicate_layout_open", "delete_layout_open"):
            self.assertIn(f'data-action="{action}"', self.html, action)

    def test_it_offers_the_three_element_types(self) -> None:
        for action in ("add_text", "add_image", "add_box"):
            self.assertIn(f'data-action="{action}"', self.html, action)

    def test_the_image_picker_is_restricted_to_the_four_accepted_types(self) -> None:
        match = re.search(r'<input[^>]*id="image-file-input"[^>]*>', self.html)
        self.assertIsNotNone(match, "no #image-file-input file picker")
        tag = match.group(0)
        self.assertEqual(re.search(r'type="([^"]+)"', tag).group(1), "file")
        accept = re.search(r'accept="([^"]+)"', tag)
        self.assertIsNotNone(accept, "the file input must restrict its accepted types")
        types = {value.strip() for value in accept.group(1).split(",")}
        self.assertEqual(types, {"image/png", "image/jpeg", "image/gif", "image/webp"})

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
        """Demoted, not removed: an operator still needs an exact value.

        v2 replaces v1's collapsed `<details class="precise">` box with a
        always-visible "Position & size" section (direct manipulation is now
        the primary route via drag, so there is no need to hide the numbers
        behind a disclosure widget) -- but the controls themselves must still
        be there for every geometry property.
        """

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
        # display_format is layout metadata, not a formatted snapshot field.
        for forbidden in (r"\.display\b", r"_display\b", r"\.seconds\b", r"\.score\b"):
            self.assertNotRegex(code, forbidden)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
