"""Source-contract test for the soccer Cutscenes window: reads
``views/soccer_cutscenes/index.html`` and ``soccer_cutscenes.js`` as text
(no browser) and checks the operator surface the spec promises exists:
GOAL HOME / GOAL AWAY buttons, CANCEL, pack selection, and the "Play GOAL
automatically" switch -- mirroring the style of
``tests/integration/test_cutscenes_window.py`` (football; frozen).
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views" / "soccer_cutscenes"


class SoccerCutscenesWindowFilesTests(unittest.TestCase):
    def test_the_three_files_exist(self) -> None:
        for name in ("index.html", "soccer_cutscenes.js", "soccer_cutscenes.css"):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file(), f"expected {ROOT / name} to exist")

    def _html(self) -> str:
        return (ROOT / "index.html").read_text(encoding="utf-8")

    def _js(self) -> str:
        return (ROOT / "soccer_cutscenes.js").read_text(encoding="utf-8")


class TriggerButtonTests(SoccerCutscenesWindowFilesTests):
    def test_goal_home_and_goal_away_buttons_exist(self) -> None:
        html = self._html()
        self.assertIn('data-event="goal"', html)
        self.assertIn('data-team="home"', html)
        self.assertIn('data-team="away"', html)
        self.assertIn("GOAL HOME", html)
        self.assertIn("GOAL AWAY", html)

    def test_there_is_no_third_trigger_button(self) -> None:
        # Unlike football's five one-per-event buttons, soccer has exactly
        # one event (goal) and two team buttons for it.
        html = self._html()
        self.assertEqual(html.count('class="trigger '), 2)

    def test_a_cancel_button_exists_and_starts_disabled(self) -> None:
        html = self._html()
        self.assertIn('id="cancel"', html)
        self.assertIn("CANCEL", html)
        self.assertIn('id="cancel" class="cancel" disabled', html)

    def test_trigger_buttons_call_the_bridge_with_the_event_and_team(self) -> None:
        js = self._js()
        self.assertIn("api.trigger(event, team)", js)
        self.assertIn("trigger('goal', 'home')", js)
        self.assertIn("trigger('goal', 'away')", js)


class PackSelectionTests(SoccerCutscenesWindowFilesTests):
    def test_a_pack_select_exists_for_goal(self) -> None:
        html = self._html()
        self.assertIn('data-pack-for="goal"', html)

    def test_rescan_and_open_folder_controls_exist(self) -> None:
        html = self._html()
        self.assertIn('id="rescan"', html)
        self.assertIn('id="open-folder"', html)

    def test_select_pack_is_wired_to_the_bridge(self) -> None:
        js = self._js()
        self.assertIn("api.select_pack(event, select.value)", js)


class AutoTriggerSwitchTests(SoccerCutscenesWindowFilesTests):
    def test_the_switch_exists_and_defaults_checked(self) -> None:
        html = self._html()
        self.assertIn('id="auto-goal"', html)
        self.assertIn("Play GOAL automatically", html)
        self.assertIn('id="auto-goal" checked', html)

    def test_the_switch_is_wired_to_set_auto_trigger(self) -> None:
        js = self._js()
        self.assertIn("api.set_auto_trigger('goal', autoGoalCheckbox.checked)", js)

    def test_state_render_reflects_the_persisted_setting(self) -> None:
        js = self._js()
        self.assertIn("renderAutoTrigger", js)
        self.assertIn("state.auto_trigger", js)


class NoCommandEndpointTests(SoccerCutscenesWindowFilesTests):
    def test_the_window_never_calls_a_command_endpoint(self) -> None:
        js = self._js()
        self.assertNotIn("api.command(", js)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
