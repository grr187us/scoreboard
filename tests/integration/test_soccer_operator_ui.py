"""Soccer operator page (source contract), spec section 4.

These assert against the soccer operator source files rather than a browser,
in the same style as ``tests/integration/test_operator_refresh_ui.py`` and
``tests/integration/test_display_drawer_contract.py``: they prove the markup
and script carry the shape ``.scratch/soccer-mode/spec.md`` section 4 asks
for without needing a webview. The U-001 visual fit at 1093x614, 1180x720,
and 1366x768 is measured by ``tests/ui/soccer_u001.cjs`` in headless Edge
against the real bridge.

Deliberately independent of scoreboard.domain.soccer / scoreboard.host.
soccer_bridge (agents A and B's modules, still landing): every assertion
here reads only the HTML/CSS/JS text this agent owns, so it can run before
those modules exist and does not need to be revisited if their exact field
names still shift before ``api_bridge.md`` is published.

Football's files (src/scoreboard/views/operator/*) are frozen and untouched;
this is a wholly separate page (spec 2, hard rule 1).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
FOOTBALL_ONLY_WORDS = ("FLAG", "TIMEOUT", "TRY", "PLAY CLOCK")


class SoccerOperatorUiTests(unittest.TestCase):
    def setUp(self) -> None:
        operator = VIEWS / "soccer_operator"
        self.html = (operator / "index.html").read_text(encoding="utf-8")
        self.js = (operator / "soccer_operator.js").read_text(encoding="utf-8")
        self.css = (operator / "soccer_operator.css").read_text(encoding="utf-8")
        self.keyboard = (operator / "keyboard.js").read_text(encoding="utf-8")

    # --- helpers -----------------------------------------------------------

    def board(self) -> str:
        return self.html.split('<div class="drawer"', 1)[0]

    def tools(self) -> str:
        return self.html.split('<footer class="tools">', 1)[1].split("</footer>", 1)[0]

    def game_drawer(self) -> str:
        drawer = self.html.split('<div class="drawer" id="game-drawer"', 1)[1]
        return drawer.split('<div class="drawer" id="history-drawer"', 1)[0]

    def setup_drawer(self) -> str:
        drawer = self.html.split('<div class="drawer" id="setup-drawer"', 1)[1]
        return drawer.split('<div class="drawer" id="game-drawer"', 1)[0]

    # --- football is frozen, this page is separate --------------------------

    def test_this_page_never_touches_footballs_files(self) -> None:
        football = VIEWS / "operator"
        self.assertNotEqual(
            (football / "operator.js").read_text(encoding="utf-8"), self.js
        )

    def test_no_football_only_control_leaked_in(self) -> None:
        # Comments (this agent's own) may discuss football/rejected words by
        # name; only the live, uncommented markup matters here.
        live = re.sub(r"<!--.*?-->", "", self.html, flags=re.S)
        for word in FOOTBALL_ONLY_WORDS:
            with self.subTest(word=word):
                self.assertNotIn(word, live)
        self.assertNotIn("play_clock", self.js)
        self.assertNotIn("down_distance", self.html)

    def test_no_combined_stoppage_button(self) -> None:
        # Spec 4.1 decision D: the design draft's STOPPAGE button was not
        # adopted. STOP alone is the stoppage.
        live = re.sub(r"<!--.*?-->", "", self.html, flags=re.S)
        self.assertNotIn("STOPPAGE", live)
        self.assertNotIn("stoppage", self.js)

    # --- spec 4.1: team panels ------------------------------------------------

    def test_each_team_panel_has_score_stats_and_cards(self) -> None:
        for side in ("home", "away"):
            with self.subTest(side=side):
                panel = self.html.split(f'id="{side}-panel"', 1)[1].split("</section>", 1)[0]
                self.assertIn(f'data-field="teams.{side}.score"', panel)
                for stat in ("shots", "saves", "corners", "fouls"):
                    self.assertIn(f'data-stat="{stat}"', panel)
                self.assertIn(f'id="{side}-yellow"', panel)
                self.assertIn(f'id="{side}-red"', panel)
                self.assertIn(f'data-field="soccer.{side}.cards.display"', panel)

    def test_stat_nudges_send_add_stat_with_a_step(self) -> None:
        for side in ("home", "away"):
            for stat in ("shots", "saves", "corners", "fouls"):
                with self.subTest(side=side, stat=stat):
                    self.assertIn(
                        f'data-command="add_stat" data-team="{side}" data-stat="{stat}" data-step="-1"',
                        self.html,
                    )
                    self.assertIn(
                        f'data-command="add_stat" data-team="{side}" data-stat="{stat}" data-step="1"',
                        self.html,
                    )

    def test_nudges_meet_the_44px_floor(self) -> None:
        rule = self.css.split(".stat-cell button.nudge {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: var(--touch)", rule)

    def test_no_literal_32px_anywhere_in_the_css(self) -> None:
        self.assertNotIn("32px", self.css)

    # --- spec 4.2: armed scoring and card entry ------------------------------

    def test_score_and_card_controls_share_one_fixed_height_block(self) -> None:
        rule = self.css.split(".score-controls {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: var(--touch)", rule)

    def test_the_idle_goal_and_card_groups_start_hidden_except_idle(self) -> None:
        for side in ("home", "away"):
            with self.subTest(side=side):
                self.assertNotRegex(self.html, rf'id="{side}-idle"[^>]*\bhidden\b')
                goal = re.search(rf'<div class="score-goal" id="{side}-goal-armed"([^>]*)>', self.html)
                card = re.search(rf'<div class="score-card" id="{side}-card-armed"([^>]*)>', self.html)
                self.assertIn("hidden", goal.group(1))
                self.assertIn("hidden", card.group(1))

    def test_goal_applies_and_disarms(self) -> None:
        for side in ("home", "away"):
            with self.subTest(side=side):
                self.assertIn(f'data-command="add_goal" data-team="{side}"', self.html)
        self.assertIn("name === 'add_goal' || name === 'add_card'", self.js)

    def test_card_confirm_sends_add_card_with_kind(self) -> None:
        for side in ("home", "away"):
            for kind in ("yellow", "red"):
                with self.subTest(side=side, kind=kind):
                    self.assertIn(
                        f'id="{side}-card-confirm-{kind}"', self.html
                    )
                    self.assertIn(
                        f'data-command="add_card" data-team="{side}"\n                  data-kind="{kind}"',
                        self.html,
                    )

    def test_no_number_is_required_for_a_card(self) -> None:
        self.assertIn('data-action="clear_card_number"', self.html)
        self.assertIn("function clearCardNumber(", self.js)

    def test_only_one_team_is_armed_at_a_time_and_it_expires(self) -> None:
        arm_score = self.js.split("function armScore(team)", 1)[1].split("\n  function", 1)[0]
        arm_card = self.js.split("function armCard(team, kind)", 1)[1].split("\n  function", 1)[0]
        self.assertIn("disarmScore()", arm_score)
        self.assertIn("disarmScore()", arm_card)
        self.assertIn("ARM_SECONDS * 1000", arm_score)
        self.assertIn("ARM_SECONDS * 1000", arm_card)
        self.assertIn("var ARM_SECONDS = 8;", self.js)

    def test_the_armed_groups_are_toggled_with_hidden_not_display(self) -> None:
        render = self.js.split("function renderArmed()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("R.show(", render)
        self.assertNotIn("style.display", render)

    def test_the_armed_state_is_a_word_not_only_a_colour(self) -> None:
        self.assertIn('SCORING', self.js)
        self.assertIn('CARD', self.js)
        for side in ("home", "away"):
            self.assertIn(f'id="{side}-armed-flag"', self.html)

    def test_arming_disarms_when_attention_moves_away(self) -> None:
        self.assertIn("window.addEventListener('blur', disarmScore)", self.js)
        open_drawer = self.js.split("function openDrawer(id)", 1)[1].split("\n  }", 1)[0]
        self.assertIn("disarmScore()", open_drawer)
        open_dialog = self.js.split("function openDialog(request)", 1)[1].split("\n  }", 1)[0]
        self.assertIn("disarmScore()", open_dialog)

    # --- spec 4.3: SHOOTOUT panel ---------------------------------------------

    def test_the_shootout_panel_swaps_in_only_during_shootout(self) -> None:
        self.assertIn('id="shootout-block" hidden', self.html)
        render = self.js.split("function renderShootout(", 1)[1].split("\n  }", 1)[0]
        self.assertIn("current.period === 'SHOOTOUT'", render)
        self.assertIn("R.show(document.getElementById('clock-block'), !isShootout)", render)
        self.assertIn("R.show(document.getElementById('shootout-block'), isShootout)", render)

    def test_only_the_next_team_can_record_a_kick(self) -> None:
        render = self.js.split("function renderShootout(", 1)[1].split("\n  }", 1)[0]
        self.assertIn("nextTeam === side", render)
        for side in ("home", "away"):
            for outcome in ("made", "missed"):
                self.assertIn(f'id="shootout-{side}-{outcome}"', self.html)

    def test_finish_shootout_is_gated_on_decided_and_sends_the_derived_winner(self) -> None:
        # The view model carries `decided` and `derived_winner` (spec 3.2:
        # the winner argument must equal the derived winner). The page enables
        # FINISH SHOOTOUT only when decided, confirms, and forwards Python's
        # own derived winner rather than guessing from the tallies.
        self.assertIn('id="finish-shootout" data-command="finish_shootout"', self.html)
        self.assertIn('data-confirm="local"', self.html.split('id="finish-shootout"', 1)[1].split(">", 1)[0])
        self.assertIn("finish.disabled = !shootout.decided", self.js)
        self.assertIn("args.winner = model.soccer.shootout.derived_winner", self.js)
        self.assertNotIn("home_made > shootout.away_made", self.js)

    def test_corrections_wire_remove_card_and_shootout_correct_kick_by_index(self) -> None:
        # Each card row and each kick row carries the view model's index, so
        # the confirmed Remove / Mark made controls name exactly one entry.
        self.assertIn('id="kick-list"', self.html)
        self.assertIn("remove.dataset.command = 'remove_card'", self.js)
        self.assertIn("remove.dataset.index = String(row.index)", self.js)
        self.assertIn("correct.dataset.command = 'shootout_correct_kick'", self.js)
        self.assertIn("correct.dataset.index = String(kick.index)", self.js)

    def test_the_shootout_command_names_match_spec_3_2(self) -> None:
        for command in ("set_shootout_first_kicker", "shootout_kick", "shootout_remove_last", "finish_shootout"):
            with self.subTest(command=command):
                self.assertIn(f'data-command="{command}"', self.html)

    # --- spec 4.1: crowd bar words (decision D) -------------------------------

    def test_the_crowd_bar_offers_exactly_injury_delay_weather(self) -> None:
        body = self.board()
        for label in ("INJURY", "DELAY", "WEATHER"):
            with self.subTest(label=label):
                self.assertIn(f'data-command="set_game_status" data-label="{label}"', body)
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        commands = set(re.findall(r'data-command="([a-z_]+)"', row))
        self.assertEqual(
            commands,
            {"set_game_status", "clear_game_status", "status_clock_start", "status_clock_stop"},
        )

    def test_weather_starts_a_countdown_in_one_press(self) -> None:
        self.assertRegex(
            self.html,
            r'data-command="set_game_status" data-label="WEATHER" data-seconds="\d+"',
        )

    def test_clear_and_countdown_appear_only_when_raised(self) -> None:
        self.assertRegex(self.html, r'<button [^>]*id="crowd-clear"[^>]*\bhidden>')
        countdown = re.search(r'<span class="crowd-countdown" id="crowd-countdown"([^>]*)>', self.html)
        self.assertIn("hidden", countdown.group(1))
        render = self.js.split("function renderCrowdStatus(", 1)[1].split("\n  }", 1)[0]
        self.assertIn("status.label === 'WEATHER'", render)

    def test_no_crowd_control_asks_for_confirmation(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("data-confirm", row)

    def test_crowd_buttons_meet_the_36px_floor(self) -> None:
        rule = self.css.split(".crowd-bar button {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 36px", rule)

    # --- spec 4.4: period bar and drawers -------------------------------------

    def test_the_period_bar_offers_back_forward_and_undo(self) -> None:
        row = self.html.split('class="period-bar"', 1)[1].split("</section>", 1)[0]
        self.assertIn('data-command="period_back"', row)
        self.assertIn('data-command="period_forward"', row)
        self.assertIn('data-command="undo"', row)
        self.assertIn('data-action="open_history"', row)

    def test_period_bar_buttons_meet_the_36px_floor(self) -> None:
        rule = self.css.split(".period-bar button {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 36px", rule)

    def test_the_tool_bar_sends_no_command_and_offers_every_control(self) -> None:
        tools = self.tools()
        self.assertNotIn("data-command", tools)
        for label in ("open_teams", "open_corrections", "open_setup", "open_field_assistant",
                      "open_cutscenes", "open_help", "open_advanced", "open_game"):
            with self.subTest(label=label):
                self.assertIn(f'data-action="{label}"', tools)
        self.assertIn('id="open-game" class="danger" data-action="open_game"', tools)

    def test_the_game_drawer_holds_exactly_the_three_lifecycle_commands(self) -> None:
        drawer = self.game_drawer()
        commands = re.findall(r'data-command="([a-z_]+)"', drawer)
        self.assertEqual(sorted(commands), ["end_game", "game_clock_reset", "new_game"])
        self.assertEqual(drawer.count('class="danger"'), 3)

    def test_setup_drawer_offers_every_soccer_rule_field(self) -> None:
        drawer = self.setup_drawer()
        for field_id in (
            "rule-half-minutes", "rule-half-seconds", "rule-halftime-minutes",
            "rule-warmup-minutes", "rule-pregame-minutes", "rule-overtime-periods",
            "rule-overtime-minutes", "rule-golden-goal", "rule-shootout-enabled",
            "rule-shootout-kickers", "rule-shootout-credit-goal", "rule-mercy-differential",
            "rule-mercy-applies", "rule-stop-clock-on-goal", "rule-clock-direction",
            "rule-weather-minutes",
        ):
            with self.subTest(field_id=field_id):
                self.assertIn(f'id="{field_id}"', drawer)
        self.assertNotIn("data-command", drawer)
        self.assertIn('data-action="save_rules"', drawer)
        self.assertIn('data-action="restore_default_rules"', drawer)

    def test_setup_drawer_renders_toggle_and_choice_kinds(self) -> None:
        drawer = self.setup_drawer()
        self.assertIn('type="checkbox" id="rule-golden-goal"', drawer)
        self.assertIn('<select id="rule-mercy-applies"', drawer)
        self.assertIn('<select id="rule-clock-direction"', drawer)
        self.assertIn("kind === 'toggle'", self.js)
        self.assertIn("kind === 'choice'", self.js)

    # --- spec 3.2: period_decision dialog -------------------------------------

    def test_the_period_dialog_always_offers_keep_and_builds_the_rest_from_python(self) -> None:
        dialog = self.html.split('id="period-dialog"', 1)[1].split("</div>\n  </div>", 1)[0]
        self.assertIn('data-action="period_keep"', dialog)
        self.assertNotIn("data-command", dialog)
        self.assertIn("decision.choices || []", self.js)
        self.assertIn("function buildPeriodChoiceButtons(choices)", self.js)

    def test_the_period_dialog_is_driven_by_python_and_dismissed_per_expiry(self) -> None:
        self.assertIn("model.period_decision", self.js)
        self.assertIn("decision.token !== dismissedPeriodToken", self.js)
        self.assertIn("dismissedPeriodToken = model.period_decision.token", self.js)

    # --- spec 3.2: mercy_reached banner ----------------------------------------

    def test_the_mercy_dialog_offers_only_keep_and_end_game(self) -> None:
        dialog = self.html.split('id="mercy-dialog"', 1)[1].split("</div>\n  </div>", 1)[0]
        self.assertIn('data-action="mercy_keep"', dialog)
        self.assertIn('data-action="mercy_end"', dialog)
        self.assertNotIn("data-command", dialog)

    def test_end_game_from_mercy_goes_through_the_game_drawer(self) -> None:
        handler = self.js.split("action === 'mercy_end'", 1)[1].split("return;", 1)[0]
        self.assertIn("openDrawer('game-drawer')", handler)

    def test_mercy_is_never_automatic(self) -> None:
        refresh = self.js.split("function refreshMercyDialog()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("model.mercy_reached", refresh)
        self.assertNotIn("submit(", refresh)

    # --- section 7: GOAL cutscene trigger ---------------------------------------

    def test_an_accepted_goal_triggers_the_cutscene_with_the_scoring_team(self) -> None:
        handle = self.js.split("function handleResult(", 1)[1].split("\n  /* ---", 1)[0]
        self.assertIn("api.trigger_cutscene('goal', args.team)", handle)

    # --- housekeeping: F-016 and 44px live controls -----------------------------

    def test_typed_text_is_still_a_draft_and_nothing_listens_to_it(self) -> None:
        self.assertIn('data-draft="true"', self.html)
        self.assertNotIn("addEventListener('input'", self.js)
        self.assertNotIn("addEventListener('change'", self.js)

    def test_the_page_grid_has_six_fixed_rows_and_only_the_board_flexes(self) -> None:
        body_rule = self.css.split("body {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-rows: auto auto minmax(0, 1fr) auto auto auto", body_rule)


if __name__ == "__main__":  # pragma: no cover - convenience runner
    unittest.main()
