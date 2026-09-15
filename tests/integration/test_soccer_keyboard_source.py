"""Soccer keyboard binding table (source contract), spec section 4.5.

``views/soccer_operator/keyboard.js`` is a fresh table, not a copy of
football's ``views/operator/keyboard.js`` (different bindings entirely: no
play clock, goals instead of points, a card arm-then-apply path, and a
narrower crowd vocabulary). This test lifts the binding table the same way
``tests/integration/test_keyboard_source.py``/``test_operator_refresh_ui.py``
do for football's, proving every key spec 4.5 lists is present with the
right shape, and that nothing football-only leaked in.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"

# (key, shift, expected command-or-None, expected arm/card/host marker)
EXPECTED_KEYS = [
    ("' '", False, "clock"),
    ("'g'", False, "arm"),
    ("'h'", False, "arm"),
    ("'q'", False, "command"),
    ("'q'", True, "command"),
    ("'a'", False, "command"), ("'a'", True, "command"),
    ("'s'", False, "command"), ("'s'", True, "command"),
    ("'d'", False, "command"), ("'d'", True, "command"),
    ("'f'", False, "command"), ("'f'", True, "command"),
    ("'j'", False, "command"), ("'j'", True, "command"),
    ("'k'", False, "command"), ("'k'", True, "command"),
    ("'l'", False, "command"), ("'l'", True, "command"),
    ("';'", False, "command"), ("';'", True, "command"),
    ("'y'", False, "card"), ("'y'", True, "card"),
    ("'r'", False, "card"), ("'r'", True, "card"),
    ("'i'", False, "command"),
    ("'e'", False, "command"),
    ("'w'", False, "command"),
    ("'x'", False, "command"),
    ("'z'", False, "confirm"),  # ctrl+z
    ("'escape'", False, "close"),
    ("'1'", False, "host"), ("'2'", False, "host"),
    ("'c'", True, "host"),
]


class SoccerKeyboardSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        soccer = VIEWS / "soccer_operator"
        self.js = (soccer / "keyboard.js").read_text(encoding="utf-8")
        football = (VIEWS / "operator" / "keyboard.js").read_text(encoding="utf-8")
        self.football_js = football

    def test_this_is_a_fresh_table_not_a_copy_of_footballs(self) -> None:
        self.assertNotEqual(self.js, self.football_js)
        self.assertNotIn("play_clock", self.js)
        self.assertNotIn("down_distance", self.js)

    def test_the_binding_table_structure_matches_footballs_shape(self) -> None:
        # Same install(options) contract and the same guard rails, so the
        # existing browser-driven test pattern (tests/ui/keyboard.cjs) can be
        # mirrored for soccer without new plumbing.
        for marker in (
            "function install(options)", "function editable(target)",
            "options.blocked()", "options.snapshot()", "event.isComposing",
            "event.altKey || event.metaKey", "global.ScoreboardKeyboard = {install: install};",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_space_toggles_the_game_clock_only(self) -> None:
        line = [l for l in self.js.splitlines() if "label: 'Space'" in l][0]
        self.assertIn("clock: 'game'", line)

    def test_goal_keys_arm_then_apply(self) -> None:
        for key, label in (("g", "home"), ("h", "away")):
            with self.subTest(key=key):
                line = [l for l in self.js.splitlines() if f"key: '{key}'," in l and "add_goal" in l][0]
                self.assertIn(f"arm: '{label}'", line)
                self.assertIn("command: 'add_goal'", line)
                self.assertIn(f"team: '{label}'", line)
                self.assertIn("press once to arm, again to apply", line)

    def test_stat_keys_cover_all_four_stats_both_teams_with_shift_for_minus(self) -> None:
        home_keys = {"a": "shots", "s": "saves", "d": "corners", "f": "fouls"}
        away_keys = {"j": "shots", "k": "saves", "l": "corners", ";": "fouls"}
        for mapping, team in ((home_keys, "home"), (away_keys, "away")):
            for key, stat in mapping.items():
                for shift, step in ((False, "1"), (True, "-1")):
                    with self.subTest(key=key, shift=shift):
                        pattern = re.escape(f"key: '{key}'") + (r",\s*shift: true" if shift else r"(?!.*shift)")
                        matches = [
                            l for l in self.js.splitlines()
                            if f"key: '{key}'" in l and (("shift: true" in l) == shift)
                            and "add_stat" in l
                        ]
                        self.assertEqual(len(matches), 1, (key, shift))
                        line = matches[0]
                        self.assertIn(f"team: '{team}'", line)
                        self.assertIn(f"stat: '{stat}'", line)
                        self.assertIn(f"step: {step}", line)

    def test_card_keys_arm_the_card_panel_and_send_no_command_directly(self) -> None:
        for key, shift, team in (("y", False, "home"), ("y", True, "away"),
                                  ("r", False, "home"), ("r", True, "away")):
            with self.subTest(key=key, shift=shift):
                matches = [
                    l for l in self.js.splitlines()
                    if f"key: '{key}'" in l and (("shift: true" in l) == shift) and "card:" in l
                ]
                self.assertEqual(len(matches), 1)
                line = matches[0]
                self.assertIn(f"team: '{team}'", line)
                kind = "yellow" if key == "y" else "red"
                self.assertIn(f"kind: '{kind}'", line)
        self.assertIn("if (binding.card) {", self.js)
        self.assertIn("options.card(binding.card);", self.js)

    def test_crowd_keys_cover_injury_delay_weather_and_clear(self) -> None:
        for key, label in (("i", "INJURY"), ("e", "DELAY"), ("w", "WEATHER")):
            with self.subTest(key=key):
                line = [l for l in self.js.splitlines() if f"key: '{key}'," in l and "set_game_status" in l][0]
                self.assertIn(f"label: '{label}'", line)
        clear = [l for l in self.js.splitlines() if "key: 'x'" in l][0]
        self.assertIn("clear_game_status", clear)

    def test_ctrl_z_confirms_before_undo(self) -> None:
        line = [l for l in self.js.splitlines() if "ctrl: true" in l][0]
        self.assertIn("command: 'undo'", line)
        self.assertIn("confirm: true", line)

    def test_escape_closes(self) -> None:
        line = [l for l in self.js.splitlines() if "'escape'" in l][0]
        self.assertIn("close: true", line)

    def test_goal_cutscene_is_on_the_number_row_not_a_letter(self) -> None:
        # design_draft.md section 3: letters D/F/T/W are already claimed by
        # stat nudges/STOPPAGE-adjacent bindings, so the one built-in
        # cutscene (spec sections 4.5 and 7) moves to 1 / 2.
        home = [l for l in self.js.splitlines() if "key: '1'" in l and "shift" not in l][0]
        away = [l for l in self.js.splitlines() if "key: '2'" in l and "shift" not in l][0]
        self.assertIn("host: 'trigger_cutscene'", home)
        self.assertIn("args: ['goal', 'home']", home)
        self.assertIn("args: ['goal', 'away']", away)
        cancel = [l for l in self.js.splitlines() if "Shift+C" in l][0]
        self.assertIn("host: 'cancel_cutscene'", cancel)

    def test_no_football_only_binding_leaked_in(self) -> None:
        for token in ("play_clock_start", "play_clock_stop", "timeout_used", "quarter_forward"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.js)


if __name__ == "__main__":  # pragma: no cover - convenience runner
    unittest.main()
