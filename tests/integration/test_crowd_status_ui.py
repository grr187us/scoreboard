"""Audit items F3 and I4: the operator's crowd row and undo history (source contract).

These assert against the operator source files rather than a browser, in the
same style as ``tests/integration/test_display_drawer_contract.py`` and
``tests/integration/test_team_presets_ui.py``: they prove the markup and the
script carry the right shape without needing a webview.

What they deliberately do not attempt is the U-001 visual fit. Adding a whole
new always-visible row to a page that already had to earn its no-scrolling
measurement is exactly the kind of change a source-text assertion cannot
prove, so that was measured by hand with Playwright/Edge and recorded in
``PROJECT_ROADMAP.md``; what *is* pinned here is the CSS decision that makes
the fit possible -- the crowd row is a fixed ``auto`` grid row and the board
is still the only row that flexes.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from scoreboard.domain.state import GAME_STATUS_LABELS

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"


class CrowdStatusRowTests(unittest.TestCase):
    """F3: every crowd message is one press away, and none of them scores."""

    def setUp(self) -> None:
        self.css = (VIEWS / "operator" / "operator.css").read_text(encoding="utf-8")
        self.js = (VIEWS / "operator" / "operator.js").read_text(encoding="utf-8")
        self.html = (VIEWS / "operator" / "index.html").read_text(encoding="utf-8")

    def test_every_status_label_has_its_own_always_visible_button(self) -> None:
        # The finding F3 records is that the existing free text was "decorative
        # and pre-positioned, not a live toggle". A control an operator has to
        # open a drawer to reach would not fix that, so these must live in the
        # page body, outside every `class="drawer"` block.
        body = self.html.split('<div class="drawer"', 1)[0]
        for label in GAME_STATUS_LABELS:
            with self.subTest(label=label):
                self.assertIn(
                    f'data-command="set_game_status" data-label="{label}"', body
                )

    def test_the_crowd_row_is_outside_every_drawer(self) -> None:
        body = self.html.split('<div class="drawer"', 1)[0]
        self.assertIn('class="crowd-bar"', body)

    def test_clearing_and_the_countdown_are_reachable_by_mouse(self) -> None:
        for command in ("clear_game_status", "status_clock_start", "status_clock_stop"):
            with self.subTest(command=command):
                self.assertIn(f'data-command="{command}"', self.html)

    def test_the_timeout_button_starts_a_sixty_second_countdown_in_one_press(self) -> None:
        self.assertIn(
            'data-command="set_game_status" data-label="TIMEOUT" data-seconds="60"',
            self.html,
        )

    def test_no_crowd_control_asks_for_confirmation(self) -> None:
        # A crowd message is instantly reversible and the whole point is
        # speed; a confirmation dialog here would defeat the feature.
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("data-confirm", row)

    def test_the_crowd_row_never_sends_a_scoring_or_timeout_command(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        commands = set(re.findall(r'data-command="([a-z_]+)"', row))
        self.assertEqual(
            commands,
            {"set_game_status", "clear_game_status", "status_clock_start",
             "status_clock_stop"},
        )

    def test_the_row_renders_only_values_python_sent(self) -> None:
        # The chip and the countdown are copied from the view model; the page
        # derives neither. `status.display` and `status.clock_display` are the
        # same two fields the spectator widgets bind to.
        self.assertIn('data-field="status.clock_display"', self.html)
        self.assertIn("status.display", self.js)

    def test_the_crowd_row_is_a_fixed_grid_row_and_the_board_still_flexes(self) -> None:
        body_rule = self.css.split("body {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-rows: auto auto minmax(0, 1fr) auto auto auto", body_rule)
        self.assertIn(".crowd-bar { grid-row: 4; }", self.css)
        self.assertIn(".quarter-bar { grid-row: 5; }", self.css)
        self.assertIn(".tools { grid-row: 6; }", self.css)

    def test_every_crowd_button_meets_the_row_touch_floor(self) -> None:
        rule = self.css.split(".crowd-bar button {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 36px", rule)


class UndoHistoryUiTests(unittest.TestCase):
    """I4: the operator can see what a repeated Undo would give up (U-009)."""

    def setUp(self) -> None:
        self.css = (VIEWS / "operator" / "operator.css").read_text(encoding="utf-8")
        self.js = (VIEWS / "operator" / "operator.js").read_text(encoding="utf-8")
        self.html = (VIEWS / "operator" / "index.html").read_text(encoding="utf-8")

    def test_the_last_action_strip_opens_the_history(self) -> None:
        self.assertIn('id="last-action-button"', self.html)
        self.assertIn('data-action="open_history"', self.html)
        self.assertIn("open_history", self.js)

    def test_the_history_drawer_exists_and_closes_with_the_others(self) -> None:
        self.assertIn('id="history-drawer"', self.html)
        close_drawers = self.js.split("function closeDrawers()", 1)[1].split("}", 1)[0]
        self.assertIn("'history-drawer'", close_drawers)

    def test_the_history_is_rendered_from_labels_python_produced(self) -> None:
        # Every row's wording is `entry.label`, built by the bridge's
        # `_last_action_view`. The page must not compose one from old_value/
        # new_value, which would let the operator's list and the durable
        # history disagree about what an action did.
        render = self.js.split("function renderHistory(", 1)[1].split(
            "\n  function ", 1
        )[0]
        self.assertIn("entry.label", render)
        self.assertNotIn("old_value", render)
        self.assertNotIn("new_value", render)

    def test_the_next_undo_is_marked_and_the_list_is_newest_first(self) -> None:
        render = self.js.split("function renderHistory(", 1)[1].split(
            "\n  function ", 1
        )[0]
        self.assertIn("index === 0", render)
        self.assertIn("next Undo", render)

    def test_the_drawer_offers_undo_but_no_way_to_reach_past_a_newer_entry(self) -> None:
        drawer = self.html.split('id="history-drawer"', 1)[1].split("</div>\n\n", 1)[0]
        self.assertIn('data-command="undo"', drawer)
        # Undo is strictly last-in-first-out: restoring an old value out of
        # order would produce a board no sequence of commands could have
        # produced, so no row may carry its own command or index.
        self.assertNotIn("data-index", drawer)
        render = self.js.split("function renderHistory(", 1)[1].split(
            "\n  function ", 1
        )[0]
        self.assertNotIn("data-command", render)

    def test_the_depth_badge_is_hidden_when_it_would_say_nothing(self) -> None:
        render = self.js.split("function renderLastAction(", 1)[1].split(
            "\n  /**", 1
        )[0]
        self.assertIn("depth < 2", render)

    def test_every_undo_control_is_disabled_together(self) -> None:
        # There are two now -- the strip's and the drawer's -- and a disabled
        # strip button beside a live drawer button would be a lie about
        # whether anything is reversible.
        render = self.js.split("function renderLastAction(", 1)[1].split(
            "\n  /**", 1
        )[0]
        self.assertIn('querySelectorAll(\'[data-command="undo"]\')', render)


if __name__ == "__main__":  # pragma: no cover - convenience runner
    unittest.main()
