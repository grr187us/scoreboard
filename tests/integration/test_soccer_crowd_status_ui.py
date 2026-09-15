"""The soccer operator's crowd row and undo history (source contract).

Mirrors ``tests/integration/test_crowd_status_ui.py`` in style and intent,
for the soccer operator page instead of football's. Spec 4.1 decision D
narrows the crowd vocabulary to three words -- INJURY, DELAY, WEATHER -- and
drops football's FLAG/TIMEOUT/OFFICIALS' TIME OUT entirely; WEATHER is the
only one that carries a countdown (the NCHSAA 30-minute lightning wait).

The labels are hardcoded here (not imported from scoreboard.domain.soccer.
state) because that module is still landing from agent A; spec.md section
3.1 is the source of truth for ``SOCCER_STATUS_LABELS``.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
SOCCER_STATUS_LABELS = ("INJURY", "DELAY", "WEATHER")


class SoccerCrowdStatusRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.css = (VIEWS / "soccer_operator" / "soccer_operator.css").read_text(encoding="utf-8")
        self.js = (VIEWS / "soccer_operator" / "soccer_operator.js").read_text(encoding="utf-8")
        self.html = (VIEWS / "soccer_operator" / "index.html").read_text(encoding="utf-8")

    def test_every_status_label_has_its_own_always_visible_button(self) -> None:
        body = self.html.split('<div class="drawer"', 1)[0]
        for label in SOCCER_STATUS_LABELS:
            with self.subTest(label=label):
                self.assertIn(f'data-command="set_game_status" data-label="{label}"', body)

    def test_no_football_only_crowd_words(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        for word in ("FLAG", "OFFICIALS", "GOAL"):
            with self.subTest(word=word):
                self.assertNotIn(word, row)
        # Exactly the three labels, no more.
        labels = re.findall(r'data-label="([A-Z]+)"', row)
        self.assertEqual(sorted(set(labels)), sorted(SOCCER_STATUS_LABELS))

    def test_the_crowd_row_is_outside_every_drawer(self) -> None:
        body = self.html.split('<div class="drawer"', 1)[0]
        self.assertIn('class="crowd-bar"', body)

    def test_clearing_and_the_countdown_are_reachable_by_mouse(self) -> None:
        for command in ("clear_game_status", "status_clock_start", "status_clock_stop"):
            with self.subTest(command=command):
                self.assertIn(f'data-command="{command}"', self.html)

    def test_only_weather_carries_a_seconds_argument(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        for label in ("INJURY", "DELAY"):
            with self.subTest(label=label):
                button = re.search(rf'<button [^>]*data-label="{label}"[^>]*>', row).group(0)
                self.assertNotIn("data-seconds", button)
        weather = re.search(r'<button [^>]*data-label="WEATHER"[^>]*>', row).group(0)
        self.assertIn("data-seconds", weather)

    def test_no_crowd_control_asks_for_confirmation(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("data-confirm", row)

    def test_the_crowd_row_never_sends_a_scoring_or_stat_command(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        commands = set(re.findall(r'data-command="([a-z_]+)"', row))
        self.assertEqual(
            commands,
            {"set_game_status", "clear_game_status", "status_clock_start", "status_clock_stop"},
        )

    def test_the_row_renders_only_values_python_sent(self) -> None:
        self.assertIn('data-field="status.clock_display"', self.html)
        self.assertIn("status.display", self.js)

    def test_the_crowd_row_is_a_fixed_grid_row_and_the_board_still_flexes(self) -> None:
        body_rule = self.css.split("body {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-rows: auto auto minmax(0, 1fr) auto auto auto", body_rule)
        self.assertIn(".crowd-bar { grid-row: 4; }", self.css)
        self.assertIn(".period-bar { grid-row: 5; }", self.css)
        self.assertIn(".tools { grid-row: 6; }", self.css)

    def test_every_crowd_button_meets_the_row_touch_floor(self) -> None:
        rule = self.css.split(".crowd-bar button {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 36px", rule)

    def test_clear_and_the_countdown_start_hidden_and_follow_the_raised_status(self) -> None:
        self.assertRegex(self.html, r'<button [^>]*id="crowd-clear"[^>]*\bhidden>')
        countdown = re.search(r'<span class="crowd-countdown" id="crowd-countdown"([^>]*)>', self.html)
        self.assertIsNotNone(countdown)
        self.assertIn("hidden", countdown.group(1))
        group = self.html.split('id="crowd-countdown"', 1)[1].split("</span>\n  </section>", 1)[0]
        for control in ('id="crowd-clock"', 'id="crowd-start"', 'id="crowd-stop"'):
            with self.subTest(control=control):
                self.assertIn(control, group)
        render = self.js.split("function renderCrowdStatus(", 1)[1].split("\n  }", 1)[0]
        self.assertIn("status.label === 'WEATHER'", render)
        self.assertIn("R.show(document.getElementById('crowd-countdown'), hasCountdown)", render)
        self.assertIn("R.show(document.getElementById('crowd-clear')", render)

    def test_appearing_controls_come_after_every_message_button(self) -> None:
        row = self.html.split('class="crowd-bar"', 1)[1].split("</section>", 1)[0]
        last_message = max(row.index(f'data-label="{label}"') for label in SOCCER_STATUS_LABELS)
        self.assertLess(last_message, row.index('id="crowd-clear"'))
        self.assertLess(row.index('id="crowd-clear"'), row.index('id="crowd-countdown"'))

    def test_clear_is_yellow_start_green_stop_red(self) -> None:
        for selector, colour in ((".crowd-bar button.crowd-clear {", "#ffc845"),
                                 (".crowd-bar button.crowd-go {", "#2e9e6a"),
                                 (".crowd-bar button.crowd-halt {", "#c43d3d")):
            with self.subTest(selector=selector):
                rule = self.css.split(selector, 1)[1].split("}", 1)[0]
                self.assertIn(f"background: {colour}", rule)


class SoccerUndoHistoryUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.css = (VIEWS / "soccer_operator" / "soccer_operator.css").read_text(encoding="utf-8")
        self.js = (VIEWS / "soccer_operator" / "soccer_operator.js").read_text(encoding="utf-8")
        self.html = (VIEWS / "soccer_operator" / "index.html").read_text(encoding="utf-8")

    def test_the_last_action_strip_opens_the_history(self) -> None:
        self.assertIn('id="last-action-button"', self.html)
        self.assertIn('data-action="open_history"', self.html)
        self.assertIn("open_history", self.js)

    def test_the_history_drawer_exists_and_closes_with_the_others(self) -> None:
        self.assertIn('id="history-drawer"', self.html)
        close_drawers = self.js.split("function closeDrawers()", 1)[1].split("}", 1)[0]
        self.assertIn("'history-drawer'", close_drawers)

    def test_the_history_is_rendered_from_labels_python_produced(self) -> None:
        render = self.js.split("function renderHistory(", 1)[1].split("\n  function ", 1)[0]
        self.assertIn("entry.label", render)
        self.assertNotIn("old_value", render)
        self.assertNotIn("new_value", render)

    def test_the_next_undo_is_marked_and_the_list_is_newest_first(self) -> None:
        render = self.js.split("function renderHistory(", 1)[1].split("\n  function ", 1)[0]
        self.assertIn("index === 0", render)
        self.assertIn("next Undo", render)

    def test_the_drawer_offers_undo_but_no_way_to_reach_past_a_newer_entry(self) -> None:
        drawer = self.html.split('id="history-drawer"', 1)[1].split("</div>\n\n", 1)[0]
        self.assertIn('data-command="undo"', drawer)
        self.assertNotIn("data-index", drawer)
        render = self.js.split("function renderHistory(", 1)[1].split("\n  function ", 1)[0]
        self.assertNotIn("data-command", render)

    def test_the_depth_badge_is_hidden_when_it_would_say_nothing(self) -> None:
        render = self.js.split("function renderLastAction(", 1)[1].split("\n  function ", 1)[0]
        self.assertIn("depth < 2", render)

    def test_every_undo_control_is_disabled_together(self) -> None:
        render = self.js.split("function renderLastAction(", 1)[1].split("\n  function ", 1)[0]
        self.assertIn('querySelectorAll(\'[data-command="undo"]\')', render)


if __name__ == "__main__":  # pragma: no cover - convenience runner
    unittest.main()
