"""Cutscenes window and operator hooks (source contract), per
``.scratch/cutscenes/spec.md`` section 7.

Like ``test_crowd_status_ui.py`` and ``test_team_presets_ui.py``, this proves
the markup and scripts carry the right shape without a live webview: the
Cutscenes window is a small persistent trigger panel (the Field Assistant's
pattern) and the operator window gains a footer button, a status badge, and
four keyboard hotkeys that go through a new ``host`` binding kind rather than
the ordinary ``Command`` path -- cutscenes are a host concern (spec section
1) with no ``CommandType`` value of their own.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from scoreboard.domain.commands import CommandType

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"


class OperatorCutsceneHooksTests(unittest.TestCase):
    """Spec 7.2: the footer button, the badge, and the four hotkeys."""

    def setUp(self) -> None:
        self.html = (VIEWS / "operator" / "index.html").read_text(encoding="utf-8")
        self.js = (VIEWS / "operator" / "operator.js").read_text(encoding="utf-8")
        self.css = (VIEWS / "operator" / "operator.css").read_text(encoding="utf-8")
        self.keyboard = (VIEWS / "operator" / "keyboard.js").read_text(encoding="utf-8")

    def test_the_footer_has_an_open_cutscenes_button(self) -> None:
        self.assertIn('id="open-cutscenes"', self.html)
        self.assertIn('data-action="open_cutscenes"', self.html)
        self.assertIn("action === 'open_cutscenes'", self.js)
        self.assertIn("api.open_cutscenes()", self.js)

    def test_the_badge_exists_and_starts_hidden(self) -> None:
        badge = re.search(r'<span[^>]*id="cutscene-badge"[^>]*>', self.html)
        self.assertIsNotNone(badge)
        self.assertIn("hidden", badge.group(0))

    def test_the_badge_is_rendered_from_the_view_never_computed(self) -> None:
        self.assertIn("function renderCutsceneBadge(", self.js)
        badge_fn = self.js.split("function renderCutsceneBadge(", 1)[1].split(
            "\n  /**", 1
        )[0]
        self.assertIn("playing.label", badge_fn)
        self.assertIn("playing.remaining_display", badge_fn)
        # No arithmetic on a duration/elapsed/remaining field: Python's string
        # is copied, never subtracted or divided.
        self.assertNotIn("remaining_ms", badge_fn)
        self.assertNotIn("setInterval", badge_fn)

    def test_the_badge_does_not_add_a_grid_row(self) -> None:
        body_rule = self.css.split("body {", 1)[1].split("}", 1)[0]
        self.assertIn(
            "grid-template-rows: auto auto minmax(0, 1fr) auto auto auto",
            body_rule,
        )
        self.assertNotIn(".cutscene-badge { grid-row", self.css)
        self.assertNotIn(".cutscene-badge {\n  grid-row", self.css)

    def test_the_four_hotkeys_exist_with_the_exact_keys_and_host_names(self) -> None:
        self.assertIn(
            "{key: 'd', label: 'D', action: 'Cutscene: First down', "
            "host: 'trigger_cutscene', args: ['first_down', null]}",
            self.keyboard,
        )
        self.assertIn(
            "{key: 't', label: 'T', action: 'Cutscene: Touchdown (home)', "
            "host: 'trigger_cutscene', args: ['touchdown', 'home']}",
            self.keyboard,
        )
        self.assertIn(
            "{key: 't', shift: true, label: 'Shift+T', "
            "action: 'Cutscene: Touchdown (away)', "
            "host: 'trigger_cutscene', args: ['touchdown', 'away']}",
            self.keyboard,
        )
        self.assertIn(
            "{key: 'c', shift: true, label: 'Shift+C', "
            "action: 'Cancel cutscene', host: 'cancel_cutscene'}",
            self.keyboard,
        )

    def test_a_host_binding_goes_through_the_same_guards_as_a_command(self) -> None:
        install = self.keyboard.split("function install(options)", 1)[1]
        self.assertIn("options.blocked()", install)
        self.assertIn("if (binding.host) {", install)
        self.assertIn("options.host(binding.host, binding.args || [])", install)

    def test_operator_host_callback_calls_the_named_bridge_method(self) -> None:
        # "operator.js implements `host` by calling `api[name].apply(api,
        # args)` and showing the result message" (spec 7.2).
        self.assertIn("api[name].apply(api, args || [])", self.js)
        self.assertIn("host: callHost", self.js)

    def test_no_cutscene_action_travels_through_the_command_path(self) -> None:
        # Cutscenes are a host concern (spec section 1): no Command, no
        # revision, no history row.
        self.assertNotIn('data-command="trigger_cutscene"', self.html)
        self.assertNotIn('data-command="cancel_cutscene"', self.html)
        self.assertNotIn('data-command="open_cutscenes"', self.html)


class CutscenesWindowTests(unittest.TestCase):
    """Spec 7.1: the small persistent trigger panel."""

    def setUp(self) -> None:
        base = VIEWS / "cutscenes"
        self.html = (base / "index.html").read_text(encoding="utf-8")
        self.js = (base / "cutscenes.js").read_text(encoding="utf-8")
        self.css = (base / "cutscenes.css").read_text(encoding="utf-8")

    def test_the_trigger_buttons_exist_with_their_events(self) -> None:
        self.assertIn('id="trigger-first-down"', self.html)
        self.assertIn('data-event="first_down"', self.html)
        self.assertIn('id="trigger-touchdown"', self.html)
        self.assertIn('data-event="touchdown"', self.html)

    def test_cancel_is_always_visible_and_starts_disabled(self) -> None:
        cancel = re.search(r'<button[^>]*id="cancel"[^>]*>', self.html)
        self.assertIsNotNone(cancel)
        self.assertIn("disabled", cancel.group(0))
        # Not inside a hidden/collapsible container: it is always on screen.
        self.assertNotIn("<details", self.html.split('id="cancel"', 1)[0][-200:])

    def test_the_team_toggles_exist(self) -> None:
        self.assertIn('id="team-home"', self.html)
        self.assertIn('data-team="home"', self.html)
        self.assertIn('id="team-away"', self.html)
        self.assertIn('data-team="away"', self.html)

    def test_one_pack_select_per_event(self) -> None:
        for event in ("first_down", "touchdown"):
            with self.subTest(event=event):
                self.assertIn(f'data-pack-for="{event}"', self.html)

    def test_the_packs_section_is_collapsible(self) -> None:
        self.assertIn("<details", self.html)
        self.assertIn('id="rescan"', self.html)
        self.assertIn('id="open-folder"', self.html)
        self.assertIn('id="issues"', self.html)

    def test_it_attaches_on_window_pywebviewready_never_document(self) -> None:
        self.assertIn("window.addEventListener('pywebviewready'", self.js)
        self.assertNotIn("document.addEventListener('pywebviewready'", self.js)
        # Whether the API is already present or arrives later, attachment
        # happens through the same function either way (the Field Assistant
        # bug this pattern fixed: a document listener never fires at all).
        self.assertIn("if (window.pywebview && window.pywebview.api) attachBridge();", self.js)

    def test_it_defines_window_applyView(self) -> None:
        self.assertIn("window.applyView = render;", self.js)

    def test_it_never_computes_a_countdown_locally(self) -> None:
        # Python's `remaining_display` is the text; the page only copies it.
        self.assertIn("playing.remaining_display", self.js)
        self.assertNotIn("remaining_ms -", self.js)
        self.assertNotIn("setInterval", self.js)

    def test_a_first_down_sends_null_team_unless_explicitly_pressed(self) -> None:
        self.assertIn("teamExplicit ? selectedTeam : null", self.js)

    def test_none_of_the_three_files_reference_the_command_api(self) -> None:
        files = (
            ("index.html", self.html),
            ("cutscenes.js", self.js),
            ("cutscenes.css", self.css),
        )
        for label, source in files:
            with self.subTest(file=label):
                self.assertNotIn("api.command", source)
                self.assertNotIn("data-command", source)
                for member in CommandType:
                    self.assertNotIn(
                        member.value, source,
                        f"{label} contains the CommandType value {member.value!r}",
                    )


if __name__ == "__main__":  # pragma: no cover - convenience runner
    unittest.main()
