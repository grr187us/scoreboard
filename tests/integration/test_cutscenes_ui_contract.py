"""Cutscenes window and operator hooks (source contract), per
``.scratch/cutscenes/spec.md`` section 7, ``.scratch/cutscenes-v2/spec.md``
sections 2.5-2.6, and ``.scratch/cutscenes-v3/spec.md`` sections 2.4-2.5.

Like ``test_crowd_status_ui.py`` and ``test_team_presets_ui.py``, this proves
the markup and scripts carry the right shape without a live webview: the
Cutscenes window is a small persistent trigger panel (the Field Assistant's
pattern) and the operator window gains a footer button, a status badge, and
six keyboard hotkeys (five events plus cancel) that go through a ``host`` binding kind rather than
the ordinary ``Command`` path -- cutscenes are a host concern (spec section
1) with no ``CommandType`` value of their own.

The v2 rule this file guards hardest: **there is no home/away choice
anywhere.** One button and one hotkey per event, no team toggles, and no
``data-team`` in the window at all -- so a future edit cannot quietly
reintroduce a side the owner asked us to remove.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from scoreboard.domain.commands import CommandType

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"


class OperatorCutsceneHooksTests(unittest.TestCase):
    """Spec 7.2 (v3 2.5): the footer button, the badge, and the six hotkeys."""

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

    def test_the_six_hotkeys_exist_with_the_exact_keys_host_names_and_order(self) -> None:
        # Exactly the six `host` bindings of .scratch/cutscenes-v3/spec.md
        # section 2.5, in that order: five events, then cancel.
        bindings = (
            "{key: 'd', label: 'D', action: 'Cutscene: First down', "
            "host: 'trigger_cutscene', args: ['first_down']}",
            "{key: 't', label: 'T', action: 'Cutscene: Touchdown', "
            "host: 'trigger_cutscene', args: ['touchdown']}",
            "{key: 'o', label: 'O', action: 'Cutscene: Turnover', "
            "host: 'trigger_cutscene', args: ['turnover']}",
            "{key: 'f', label: 'F', action: 'Cutscene: Penalty flag', "
            "host: 'trigger_cutscene', args: ['penalty']}",
            "{key: 'l', label: 'L', action: 'Cutscene: Make some noise', "
            "host: 'trigger_cutscene', args: ['make_some_noise']}",
            "{key: 'c', shift: true, label: 'Shift+C', "
            "action: 'Cancel cutscene', host: 'cancel_cutscene'}",
        )
        positions = []
        for binding in bindings:
            with self.subTest(binding=binding):
                self.assertIn(binding, self.keyboard)
                positions.append(self.keyboard.index(binding))
        self.assertEqual(positions, sorted(positions), "the cutscene bindings are out of order")

    def test_no_cutscene_hotkey_names_a_side_and_shift_t_is_gone(self) -> None:
        cutscene_bindings = [
            line for line in self.keyboard.splitlines() if "trigger_cutscene" in line
        ]
        self.assertEqual(len(cutscene_bindings), 5)
        for line in cutscene_bindings:
            with self.subTest(binding=line.strip()):
                self.assertNotIn("'home'", line)
                self.assertNotIn("'away'", line)
        self.assertNotIn("Shift+T", self.keyboard)

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

    def test_the_five_trigger_buttons_exist_with_their_events_in_order(self) -> None:
        # .scratch/cutscenes-v3/spec.md section 2.4: five buttons, this order.
        buttons = (
            ("trigger-first-down", "first_down"),
            ("trigger-touchdown", "touchdown"),
            ("trigger-turnover", "turnover"),
            ("trigger-penalty", "penalty"),
            ("trigger-make-some-noise", "make_some_noise"),
        )
        positions = []
        for button_id, event in buttons:
            with self.subTest(event=event):
                self.assertIn(f'id="{button_id}"', self.html)
                self.assertIn(f'data-event="{event}"', self.html)
                positions.append(self.html.index(f'id="{button_id}"'))
        self.assertEqual(positions, sorted(positions), "the trigger buttons are out of order")
        self.assertEqual(self.html.count("data-event="), 5)

    def test_each_button_triggers_its_event_with_no_second_argument(self) -> None:
        for event in ("first_down", "touchdown", "turnover", "penalty", "make_some_noise"):
            with self.subTest(event=event):
                self.assertIn(f"trigger('{event}');", self.js)
        self.assertIn("api.trigger(event)", self.js)

    def test_the_penalty_button_wears_the_flag_yellow_not_a_team_colour(self) -> None:
        rule = self.css.split(".trigger-penalty {", 1)[1].split("}", 1)[0]
        self.assertIn("#FFD500", rule)  # THEME["flag"]
        self.assertIn("#030711", rule)  # THEME["ink"]

    def test_the_window_hotkeys_are_d_t_o_f_l_and_shift_c(self) -> None:
        # v3 section 2.4: `O` turnover and `L` ("get Loud") make some noise
        # join D/T/F; Shift+C still cancels and Shift+T is still gone.
        for key in ("d", "t", "o", "f", "l"):
            with self.subTest(key=key):
                self.assertIn(f"if (key === '{key}' && !event.shiftKey)", self.js)
        self.assertIn("if (key === 'c' && event.shiftKey)", self.js)
        self.assertNotIn("key === 't' && event.shiftKey", self.js)

    def test_cancel_is_always_visible_and_starts_disabled(self) -> None:
        cancel = re.search(r'<button[^>]*id="cancel"[^>]*>', self.html)
        self.assertIsNotNone(cancel)
        self.assertIn("disabled", cancel.group(0))
        # Not inside a hidden/collapsible container: it is always on screen.
        self.assertNotIn("<details", self.html.split('id="cancel"', 1)[0][-200:])

    def test_the_window_offers_no_team_choice_at_all(self) -> None:
        # Cutscenes v2: the wall is the Tigers' wall, so there is no side to
        # pick -- not a toggle, not a data attribute, not a variable.
        self.assertNotIn("data-team", self.html)
        self.assertNotIn('id="team-home"', self.html)
        self.assertNotIn('id="team-away"', self.html)
        self.assertNotIn("team-toggle", self.html)
        self.assertNotIn("team-toggle", self.css)
        for name in ("selectedTeam", "teamExplicit", "fillTeamNames"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.js)

    def test_one_pack_select_per_event(self) -> None:
        for event in ("first_down", "touchdown", "turnover", "penalty", "make_some_noise"):
            with self.subTest(event=event):
                self.assertIn(f'data-pack-for="{event}"', self.html)
                self.assertIn(f"renderPackSelect('{event}')", self.js)
        self.assertEqual(self.html.count("data-pack-for="), 5)

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
