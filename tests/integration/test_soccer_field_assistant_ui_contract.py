"""Soccer Field Assistant window source contract, per
``.scratch/soccer-mode/spec.md`` section 6 and IMPLEMENTERS.md.

Like ``test_cutscenes_ui_contract.py`` and ``test_field_assistant_window.py``'s
source-contract half, this proves the markup/script/style carry the right
shape without a live webview: control ids exist, no score or clock control
exists anywhere on this page, every live button is at least 44px, and no
control regresses to a smaller 32px touch target.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views" / "soccer_field_assistant"


class SoccerFieldAssistantSourceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (VIEWS / "index.html").read_text(encoding="utf-8")
        self.js = (VIEWS / "soccer_field_assistant.js").read_text(encoding="utf-8")
        self.css = (VIEWS / "soccer_field_assistant.css").read_text(encoding="utf-8")

    # -- required control ids --------------------------------------------

    def test_header_shows_revision_and_read_only_clock_and_period(self) -> None:
        self.assertIn('id="revision"', self.html)
        self.assertIn('id="clocks"', self.html)
        self.assertIn('id="resync"', self.html)

    def test_both_team_columns_have_all_six_big_buttons(self) -> None:
        for team in ("home", "away"):
            for stat in ("shots", "saves", "corners", "fouls"):
                with self.subTest(team=team, stat=stat):
                    self.assertIn(f'data-action="stat" data-team="{team}" data-stat="{stat}"', self.html)
            for card in ("yellow", "red"):
                with self.subTest(team=team, card=card):
                    self.assertIn(f'data-action="card" data-team="{team}" data-card="{card}"', self.html)

    def test_player_number_pad_exists_with_digits_backspace_and_no_number(self) -> None:
        for digit in "0123456789":
            with self.subTest(digit=digit):
                self.assertIn(f'data-digit="{digit}"', self.html)
        self.assertIn('id="pad-backspace"', self.html)
        self.assertIn('id="pad-no-number"', self.html)
        self.assertIn('id="player-number-readout"', self.html)

    def test_scoreboard_now_line_exists(self) -> None:
        self.assertIn('id="scoreboard-now"', self.html)
        self.assertIn("Scoreboard now", self.js)

    def test_shootout_block_exists_and_is_hidden_by_default(self) -> None:
        shootout = re.search(r'<section[^>]*id="shootout-panel"[^>]*>', self.html)
        self.assertIsNotNone(shootout)
        self.assertIn("hidden", shootout.group(0))
        self.assertIn('id="shootout-status"', self.html)
        self.assertIn('id="shootout-dots-home"', self.html)
        self.assertIn('id="shootout-dots-away"', self.html)
        for team in ("home", "away"):
            for made in ("true", "false"):
                with self.subTest(team=team, made=made):
                    self.assertIn(f'data-action="shootout_kick" data-team="{team}" data-made="{made}"', self.html)
        self.assertIn('data-action="first_kicker" data-team="home"', self.html)
        self.assertIn('data-action="first_kicker" data-team="away"', self.html)

    def test_shootout_is_shown_only_for_the_shootout_period(self) -> None:
        self.assertIn("function shootoutActive() { return Boolean(model && model.period === 'SHOOTOUT'); }", self.js)
        self.assertIn("panel.hidden = !active;", self.js)

    def test_only_the_next_team_can_kick_in_the_shootout_panel(self) -> None:
        self.assertIn("button.disabled = Boolean(nextTeam) && button.getAttribute('data-team') !== nextTeam;", self.js)

    def test_cancel_and_confirm_buttons_exist(self) -> None:
        self.assertIn('id="cancel"', self.html)
        confirm = re.search(r'<button[^>]*id="confirm"[^>]*>', self.html)
        self.assertIsNotNone(confirm)
        self.assertIn("disabled", confirm.group(0))

    def test_confirm_label_comes_from_preview_assist_never_hardcoded(self) -> None:
        self.assertIn("api.preview_assist(request)", self.js)
        self.assertIn("confirmButton.textContent = result.label;", self.js)
        self.assertIn("api.finalize_assist(committed, baseRevision)", self.js)

    # -- no score / clock controls anywhere -------------------------------

    def test_no_score_control_exists(self) -> None:
        for forbidden in ("add_goal", "set_score", "GOAL", "data-action=\"goal\"", "correct_goal"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.html)
                self.assertNotIn(forbidden, self.js)

    def test_no_clock_or_period_control_exists(self) -> None:
        for forbidden in (
            "game_clock_start", "game_clock_stop", "game_clock_reset", "game_clock_correct",
            "period_forward", "period_back", "set_period", "status_clock_start", "status_clock_stop",
            "id=\"start\"", "id=\"stop\"",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.html)
                self.assertNotIn(forbidden, self.js)

    def test_no_undo_control_exists(self) -> None:
        self.assertNotIn("undo", self.html.lower())
        self.assertNotIn("api.command(", self.js)

    def test_the_page_never_calls_a_generic_command_endpoint(self) -> None:
        # Only three bridge methods exist on this page: get_snapshot,
        # preview_assist, finalize_assist -- no api.command(...).
        for allowed in ("api.get_snapshot()", "api.preview_assist(", "api.finalize_assist("):
            with self.subTest(allowed=allowed):
                self.assertIn(allowed, self.js)
        self.assertNotIn("api.command(", self.js)
        self.assertNotIn("api.add_goal", self.js)
        self.assertNotIn("api.set_score", self.js)

    # -- live sync (spec section 6) ---------------------------------------

    def test_every_push_is_adopted_and_confirm_is_never_disabled_by_an_unrelated_change(self) -> None:
        self.assertIn("baseRevision = model.revision;", self.js)
        self.assertNotIn("model.revision !== baseRevision", self.js)
        self.assertIn("if (revisionChanged && selected && api && autoPreviewTimer === null) preview();", self.js)

    def test_a_stale_revision_shows_a_toast_and_one_more_confirm_finishes(self) -> None:
        self.assertIn('id="conflict"', self.html)
        self.assertIn("function isStale(result)", self.js)
        self.assertIn("if (isStale(result)) { showConflict(); preview(); }", self.js)

    def test_the_bridge_is_attached_on_the_window_ready_event(self) -> None:
        self.assertIn("window.addEventListener('pywebviewready'", self.js)
        self.assertNotIn("document.addEventListener('pywebviewready'", self.js)

    def test_window_applyview_hook_exists_for_the_host_push(self) -> None:
        self.assertIn("window.applyView = render;", self.js)

    # -- sizing -------------------------------------------------------------

    def test_every_button_control_is_at_least_44px_and_none_regress_to_32px(self) -> None:
        self.assertIn("--touch: 44px", (VIEWS.parent / "shared" / "base.css").read_text(encoding="utf-8"))
        # Only rules that style actual controls (buttons); the notice/conflict
        # text banners are not touch targets and are exempt.
        button_rules = re.findall(r"(?:^|[,}])\s*([^{}\n]*button[^{}\n]*)\{([^{}]*)\}", self.css)
        heights = [int(m) for _selector, body in button_rules for m in re.findall(r"min-height\s*:\s*(\d+)px", body)]
        self.assertTrue(heights, "expected at least one button min-height rule")
        for height in heights:
            with self.subTest(height=height):
                self.assertGreaterEqual(height, 44)
        self.assertNotIn("32px", self.css)
        self.assertNotIn("32px", self.html)
        self.assertNotIn("32px", self.js)


if __name__ == "__main__":
    unittest.main()
