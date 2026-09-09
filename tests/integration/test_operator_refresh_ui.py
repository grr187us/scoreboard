"""The September 8, 2026 control refresh, operator page (source contract).

These assert against the operator source files rather than a browser, in the
same style as ``tests/integration/test_display_drawer_contract.py`` and
``tests/integration/test_crowd_status_ui.py``: they prove the markup and the
script carry the shape the owner asked for without needing a webview.

What they deliberately do not attempt is the U-001 visual fit -- that is
measured by ``tests/ui/keyboard.cjs``, which drives the real page in headless
Edge at both supported viewports, with a team armed as well as idle.

The four owner decisions pinned here (.scratch/control-refresh/spec.md):

1. Teams are a soft prompt, not a lock.
2. Scoring on the main screen is two steps: arm, then apply.
3. Undo names exactly what it reverses before anything is sent.
4. The quick timeout charges a timeout and touches nothing else.

Plus the two other asks: the game lifecycle moved into its own drawer, and the
spectator display can be closed from the operator's Display drawer.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"


class OperatorRefreshUiTests(unittest.TestCase):
    def setUp(self) -> None:
        operator = VIEWS / "operator"
        self.html = (operator / "index.html").read_text(encoding="utf-8")
        self.js = (operator / "operator.js").read_text(encoding="utf-8")
        self.css = (operator / "operator.css").read_text(encoding="utf-8")
        self.keyboard = (operator / "keyboard.js").read_text(encoding="utf-8")

    # --- helpers ---------------------------------------------------------

    def board(self) -> str:
        """The always-visible page, with every overlay drawer removed."""
        return self.html.split('<div class="drawer"', 1)[0]

    def tools(self) -> str:
        return self.html.split('<footer class="tools">', 1)[1].split("</footer>", 1)[0]

    def game_drawer(self) -> str:
        drawer = self.html.split('<div class="drawer" id="game-drawer"', 1)[1]
        return drawer.split('<div class="drawer" id="history-drawer"', 1)[0]

    # --- decision 2: two-step scoring ------------------------------------

    def test_no_add_score_control_sits_outside_the_armed_panel_or_corrections(self) -> None:
        # Every +N on the board must be inside a .score-controls block, which
        # is hidden until the operator arms that team. The only other place
        # add_score is allowed is the Corrections drawer, where the drawer
        # itself is the protection.
        remaining = self.html
        for block in re.findall(
            r'<div class="score-controls".*?\n      </div>', self.html, re.S
        ):
            remaining = remaining.replace(block, "")
        corrections = self.html.split('<div class="drawer" id="corrections"', 1)[1]
        corrections = corrections.split('<div class="drawer" id="display-drawer"', 1)[0]
        remaining = remaining.replace(corrections, "")

        self.assertNotIn('data-command="add_score"', remaining)

    def test_the_armed_point_buttons_start_hidden(self) -> None:
        for side in ("home", "away"):
            with self.subTest(side=side):
                group = re.search(
                    rf'<div class="score-armed" id="{side}-armed"([^>]*)>', self.html
                )
                self.assertIsNotNone(group)
                self.assertIn("hidden", group.group(1))

    def test_each_side_has_one_arm_control_and_one_cancel(self) -> None:
        board = self.board()
        for side in ("home", "away"):
            with self.subTest(side=side):
                self.assertIn(
                    f'id="{side}-arm" data-action="arm_score" data-team="{side}"', board
                )
        self.assertEqual(board.count('data-action="disarm_score"'), 2)
        self.assertIn("action === 'arm_score'", self.js)
        self.assertIn("action === 'disarm_score'", self.js)

    def test_only_one_team_is_armed_at_a_time_and_it_expires(self) -> None:
        arm = self.js.split("function armScore(team)", 1)[1].split("\n  function", 1)[0]
        # Arming disarms whatever was armed, so two panels can never show
        # point buttons together.
        self.assertIn("disarmScore()", arm)
        self.assertIn("ARM_SECONDS * 1000", arm)
        self.assertIn("var ARM_SECONDS = 8;", self.js)

    def test_the_armed_groups_are_toggled_with_hidden_not_display(self) -> None:
        render = self.js.split("function renderArmed()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("R.show(", render)
        self.assertNotIn("style.display", render)

    def test_the_armed_state_is_a_word_not_only_a_colour(self) -> None:
        # U-002: the heading says SCORING; the accent border is a second cue.
        self.assertIn('class="armed-flag" id="home-armed-flag"', self.html)
        self.assertIn('class="armed-flag" id="away-armed-flag"', self.html)
        self.assertIn("SCORING", self.html)
        self.assertIn("-armed-flag", self.js)

    def test_the_score_block_has_a_fixed_height_so_arming_moves_nothing(self) -> None:
        rule = self.css.split(".score-controls {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 52px", rule)

    def test_arming_disarms_when_attention_moves_away(self) -> None:
        for trigger in (
            "window.addEventListener('blur', disarmScore)",
            "if (name === 'add_score') {",
        ):
            with self.subTest(trigger=trigger):
                self.assertIn(trigger, self.js)
        # A drawer or a dialog covers the board, so both put the points away.
        open_drawer = self.js.split("function openDrawer(id)", 1)[1].split(
            "\n  }", 1
        )[0]
        self.assertIn("disarmScore()", open_drawer)
        open_dialog = self.js.split("function openDialog(request)", 1)[1].split(
            "\n  }", 1
        )[0]
        self.assertIn("disarmScore()", open_dialog)

    # --- decision 4: the quick timeout -----------------------------------

    def test_the_board_charges_a_timeout_once_per_team_and_nothing_else(self) -> None:
        board = self.board()
        for side in ("home", "away"):
            with self.subTest(side=side):
                self.assertEqual(
                    board.count(f'data-command="timeout_used" data-team="{side}"'), 1
                )
                self.assertIn(f'id="{side}-timeout"', board)
                # The count beside it is bound, never computed.
                self.assertIn(f'data-field="football.timeouts.{side}"', board)

    # --- decision 3: Undo confirms ---------------------------------------

    def test_both_undo_controls_confirm_locally(self) -> None:
        controls = re.findall(
            r'data-command="undo"\s+data-confirm="local"\s+'
            r'data-confirm-title="Undo the last action\?"',
            self.html,
        )
        self.assertEqual(len(controls), 2, "the strip's Undo and the drawer's")

    def test_the_undo_dialog_says_what_python_said_the_last_action_was(self) -> None:
        describe = self.js.split("function describeUndo()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("'Reverses: '", describe)
        self.assertIn("model.last_action.label", describe)

    def test_ctrl_z_takes_the_same_two_steps(self) -> None:
        binding = [
            line for line in self.keyboard.splitlines() if "'Ctrl+Z'" in line
        ]
        self.assertEqual(len(binding), 1)
        self.assertIn("confirm: true", binding[0])
        self.assertIn("options.confirm(binding.command", self.keyboard)
        self.assertIn("confirm: function (name, args, options)", self.js)

    def test_score_keys_arm_before_they_apply(self) -> None:
        armed = [line for line in self.keyboard.splitlines() if "arm: '" in line]
        self.assertEqual(len(armed), 8, "Z X C V and N M , .")
        for line in armed:
            with self.subTest(binding=line.strip()):
                self.assertIn("command: 'add_score'", line)
                self.assertIn("press once to arm, again to apply", line)
        self.assertIn("options.score(binding)", self.keyboard)
        self.assertIn("score: function (binding)", self.js)

    def test_escape_puts_the_points_away(self) -> None:
        close = self.js.split("close: function ()", 1)[1].split("\n    }", 1)[0]
        self.assertIn("armedTeam", close)
        self.assertIn("disarmScore()", close)

    # --- owner request 5: the Game drawer --------------------------------

    def test_the_tool_bar_sends_no_command_at_all(self) -> None:
        tools = self.tools()
        self.assertNotIn("data-command", tools)
        self.assertIn('id="open-game" class="danger" data-action="open_game"', tools)
        self.assertIn("action === 'open_game'", self.js)

    def test_the_game_drawer_holds_exactly_the_three_lifecycle_commands(self) -> None:
        drawer = self.game_drawer()
        commands = re.findall(r'data-command="([a-z_]+)"', drawer)
        self.assertEqual(
            sorted(commands), ["end_game", "game_clock_reset", "new_game"]
        )
        # All three stay marked dangerous wherever they live (U-004).
        self.assertEqual(drawer.count('class="danger"'), 3)
        self.assertIn('aria-label="Game"', drawer)

    def test_the_game_drawer_closes_with_the_others(self) -> None:
        close_drawers = self.js.split("function closeDrawers()", 1)[1].split("}", 1)[0]
        self.assertIn("'game-drawer'", close_drawers)

    # --- decision 1: the soft prompt -------------------------------------

    def test_the_board_says_when_a_team_was_never_chosen(self) -> None:
        board = self.board()
        for side in ("home", "away"):
            with self.subTest(side=side):
                tag = re.search(rf'<p class="team-pending" id="{side}-pending"([^>]*)>', board)
                self.assertIsNotNone(tag)
                self.assertIn("hidden", tag.group(1))
        self.assertIn("NOT CHOSEN", board)

    def test_the_teams_drawer_carries_pythons_sentence(self) -> None:
        self.assertIn('id="teams-prompt"', self.html)
        render = self.js.split("function renderSetup(current)", 1)[1].split(
            "\n  }", 1
        )[0]
        # Every word is Python's; the page picks none of it (the wording rule).
        self.assertIn("setup.detail", render)
        self.assertIn("setup.teams_pending", render)
        self.assertIn("setup.home_pending", render)
        self.assertIn("setup.away_pending", render)
        # An older view model with no `setup` block must not throw.
        self.assertIn("current.setup || {}", render)

    def test_the_drawer_opens_itself_after_an_accepted_new_game(self) -> None:
        handle = self.js.split("function handleResult(", 1)[1].split(
            "\n  /* ---", 1
        )[0]
        self.assertIn("name === 'new_game'", handle)
        self.assertIn("openDrawer('teams-drawer')", handle)

    def test_the_drawer_opens_once_at_launch_and_never_from_render(self) -> None:
        ready = self.js.split("R.whenReady(function (bridge)", 1)[1]
        self.assertIn("view.setup.teams_pending", ready)
        self.assertIn("openDrawer('teams-drawer')", ready)
        self.assertIn("promptedForTeams", ready)
        # A dismissed prompt stays dismissed: render() must not re-open it.
        render = self.js.split("function render(next)", 1)[1].split("\n  }", 1)[0]
        self.assertNotIn("openDrawer", render)

    # --- owner request 6: closing the display ----------------------------

    def test_the_display_drawer_offers_a_close_button(self) -> None:
        drawer = self.html.split('<div class="drawer" id="display-drawer"', 1)[1]
        drawer = drawer.split('<div class="drawer" id="teams-drawer"', 1)[0]
        self.assertIn('id="close-display" data-action="close_display"', drawer)
        # Host action only: no command, no revision, no danger class (D-005).
        self.assertNotIn("data-command", drawer)
        self.assertNotIn("danger", drawer.split('id="close-display"', 1)[1])

    def test_the_close_handler_uses_the_pinned_bridge_call(self) -> None:
        handler = self.js.split("action === 'close_display'", 1)[1].split(
            "\n    if (action ===", 1
        )[0]
        self.assertIn("api.close_display()", handler)
        self.assertIn("renderDisplays(payload)", handler)
        self.assertIn("payload.status.detail", handler)
        # Feature-detected, so an older host says so plainly instead of throwing.
        self.assertIn("typeof api.close_display !== 'function'", handler)

    def test_close_display_is_only_offered_while_a_display_is_open(self) -> None:
        health = self.js.split("function renderHealth(health)", 1)[1].split(
            "\n  }", 1
        )[0]
        self.assertIn(
            "R.show(document.getElementById('close-display'), health.display.open)",
            health,
        )

    # --- corrections ------------------------------------------------------

    def test_corrections_can_add_points_as_well_as_take_them_away(self) -> None:
        corrections = self.html.split('<div class="drawer" id="corrections"', 1)[1]
        corrections = corrections.split('<div class="drawer" id="display-drawer"', 1)[0]
        for side in ("home", "away"):
            row = corrections.split(f'data-field="teams.{side}.score"', 1)[1]
            row = row.split("</div>", 1)[0]
            adds = re.findall(
                rf'data-command="add_score" data-team="{side}" data-points="(\d)"', row
            )
            self.assertEqual(adds, ["1", "2", "3", "6"], side)
            # And they come before the corrections they undo.
            self.assertLess(
                row.index('data-command="add_score"'),
                row.index('data-command="correct_score"'),
                side,
            )

    # --- what must not change --------------------------------------------

    def test_the_page_still_adds_no_grid_row(self) -> None:
        body_rule = self.css.split("body {", 1)[1].split("}", 1)[0]
        self.assertIn(
            "grid-template-rows: auto auto minmax(0, 1fr) auto auto auto", body_rule
        )

    def test_typed_text_is_still_a_draft_and_nothing_listens_to_it(self) -> None:
        # F-016 is unchanged by any of this.
        self.assertIn('data-draft="true"', self.html)
        self.assertNotIn("addEventListener('input'", self.js)
        self.assertNotIn("addEventListener('change'", self.js)

    def test_the_file_header_names_the_fourth_kind_of_view_state(self) -> None:
        header = self.js.split("*/", 1)[0]
        self.assertIn("four kinds", header)
        self.assertIn("armed", header)


if __name__ == "__main__":  # pragma: no cover - convenience runner
    unittest.main()
