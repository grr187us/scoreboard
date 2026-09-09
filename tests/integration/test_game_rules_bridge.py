"""The Setup drawer's host actions and page contract (September 9, 2026).

``rules()`` and ``save_rules()`` on the operator bridge are host actions in
the ``save_team``/``set_motion`` family: they advance no revision, submit no
command, and write no action-history row. Saved rules land in ``config.json``
under their own section and are read back at the next launch; a refused
payload changes nothing and returns the operator's sentence. The page half is
a source contract in the style of ``test_crowd_status_ui.py``: the tool bar
offers Setup where the removed Halftime drawer used to be, the drawer holds no
game command, and the crowd TIMEOUT button takes its length from the view.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from scoreboard.domain.rules import GameRules, default_rules
from scoreboard.host.app import ScoreboardApplication
from scoreboard.host.bridge import ScoreboardBridge
from scoreboard.infrastructure import config
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.persistence import read_action_history
from tests.integration.support import TemporaryDataDirectoryTest

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
OPERATOR_HTML = (VIEWS / "operator" / "index.html").read_text(encoding="utf-8")
OPERATOR_JS = (VIEWS / "operator" / "operator.js").read_text(encoding="utf-8")
KEYBOARD_JS = (VIEWS / "operator" / "keyboard.js").read_text(encoding="utf-8")


class RulesBridgeTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.published: list[dict] = []
        self.written: list[GameRules] = []
        self.bridge = ScoreboardBridge(
            self.service, self.store,
            on_accepted=self.published.append,
            rules_writer=self._write,
        )

    def _write(self, rules: GameRules) -> bool:
        self.written.append(rules)
        return config.write_rules(self.paths, rules)

    def send(self, name: str, args: dict | None = None) -> dict:
        return self.bridge.command(name, args or {}, self.service.revision)


class HostActionTests(RulesBridgeTestCase):
    def test_rules_reports_the_values_in_force_with_their_labels(self) -> None:
        payload = self.bridge.rules()
        self.assertEqual(payload["rules"], default_rules().to_dict())
        self.assertEqual(payload["defaults"], default_rules().to_dict())
        names = [field["name"] for field in payload["fields"]]
        self.assertEqual(names, [
            "quarter_seconds", "overtime_seconds", "pregame_seconds",
            "halftime_seconds", "warmup_seconds", "timeout_seconds", "timeouts_per_half",
        ])
        quarter = payload["fields"][0]
        self.assertEqual((quarter["minutes"], quarter["seconds"], quarter["display"]), (12, 0, "12:00"))
        self.assertEqual(payload["fields"][-1]["display"], "3")
        json.dumps(payload)  # JSON-compatible, like every bridge return value

    def test_saving_touches_no_game_state_and_persists(self) -> None:
        self.send("game_clock_start")
        revision = self.service.revision
        rows_before = len(read_action_history(self.paths.database))

        result = self.bridge.save_rules({"quarter_seconds": 480, "timeout_seconds": 45,
                                         "timeouts_per_half": 2})

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["saved"])
        self.assertEqual(self.service.revision, revision)
        self.assertEqual(len(read_action_history(self.paths.database)), rows_before)
        self.assertTrue(self.service.state.game_clock.running)
        self.assertEqual(self.service.rules.quarter_seconds, 480)
        self.assertEqual(self.written[-1].timeout_seconds, 45)
        self.assertEqual(config.read_rules(self.paths).timeouts_per_half, 2)
        stored = json.loads(self.paths.config.read_text(encoding="utf-8"))
        self.assertEqual(stored[config.RULES_SECTION]["quarter_seconds"], 480)
        # Every window gets the new view, since the TIMEOUT button and the
        # warmup line read the rules from it.
        self.assertEqual(self.published[-1]["rules"]["timeout_seconds"], 45)

    def test_a_refused_payload_changes_nothing(self) -> None:
        before = self.service.rules
        result = self.bridge.save_rules({"quarter_seconds": 15})
        self.assertFalse(result["ok"])
        self.assertIn("Quarter length", result["message"])
        self.assertEqual(self.service.rules, before)
        self.assertEqual(self.written, [])
        self.assertFalse(self.paths.config.exists())
        self.assertEqual(result["rules"], before.to_dict())

    def test_a_failed_write_keeps_the_rules_for_this_session(self) -> None:
        def refuse(rules: GameRules) -> bool:
            raise OSError("disk full")

        bridge = ScoreboardBridge(self.service, self.store, rules_writer=refuse)
        result = bridge.save_rules({"halftime_seconds": 600})
        self.assertTrue(result["ok"])
        self.assertFalse(result["saved"])
        self.assertIn("could not be saved", result["message"])
        self.assertEqual(self.service.rules.halftime_seconds, 600)

    def test_a_bridge_without_a_writer_still_applies(self) -> None:
        bridge = ScoreboardBridge(self.service, self.store)
        result = bridge.save_rules({"pregame_seconds": 600})
        self.assertTrue(result["ok"])
        self.assertTrue(result["saved"])
        self.assertEqual(self.service.rules.pregame_seconds, 600)

    def test_the_view_carries_the_rules_and_the_clock_length(self) -> None:
        view = self.bridge.get_snapshot()
        self.assertEqual(view["rules"], default_rules().to_dict())
        self.assertEqual(view["rule_fields"][3]["display"], "15:00")
        self.assertNotIn("event_phases", view)
        game = view["clocks"]["game"]
        self.assertEqual((game["maximum_seconds"], game["full_display"], game["label"]),
                         (1800.0, "30:00", "KICKOFF COUNTDOWN"))
        self.send("set_quarter", {"label": "1st", "confirmed": True})
        self.assertEqual(self.bridge.get_snapshot()["clocks"]["game"]["label"], "GAME CLOCK")
        self.assertEqual(self.bridge.get_snapshot()["clocks"]["game"]["full_display"], "12:00")

    def test_the_spectator_view_carries_no_rules_block(self) -> None:
        self.assertNotIn("rules", self.bridge.spectator_snapshot())

    def test_saved_rules_shape_the_next_quarter_and_the_crowd_timeout(self) -> None:
        self.bridge.save_rules({"halftime_seconds": 600, "warmup_seconds": 120,
                                "timeout_seconds": 45})
        self.send("set_quarter", {"label": "2nd", "confirmed": True})
        result = self.send("set_quarter", {"label": "HALF", "confirmed": True})
        event = result["view"]["clocks"]["event"]
        self.assertEqual(event["display"], "10:00")
        self.assertEqual(event["warmup_follows"], "2:00")
        timeout = self.send("set_game_status", {"label": "TIMEOUT", "seconds": 45})
        self.assertTrue(timeout["accepted"], timeout["error"])
        self.assertEqual(timeout["view"]["status"]["clock_display"], "0:45")


class StartupTests(TemporaryDataDirectoryTest):
    def test_stored_rules_are_read_at_launch_and_used_for_the_first_game(self) -> None:
        config.write_rules(self.paths, GameRules(pregame_seconds=600, timeouts_per_half=4))
        # NullDiagnostics, as test_display_selection.py does: a real log file
        # would stay open past the temporary folder's cleanup on Windows.
        app = ScoreboardApplication(
            self.paths, diagnostics=NullDiagnostics(), acquire_lock=False
        )
        self.addCleanup(app.shutdown)
        self.assertEqual(app.rules.pregame_seconds, 600)
        bridge = app.start_new()
        view = bridge.get_snapshot()
        self.assertEqual(view["clocks"]["game"]["display"], "10:00")
        self.assertEqual(view["football"]["timeouts"], {"home": 4, "away": 4})
        bridge.save_rules({"pregame_seconds": 900})
        self.assertEqual(app.rules.pregame_seconds, 900)
        self.assertEqual(config.read_rules(self.paths).pregame_seconds, 900)

    def test_a_damaged_rules_section_reads_as_the_defaults(self) -> None:
        config.write_section(self.paths, config.RULES_SECTION, {"quarter_seconds": "twelve"})
        self.assertEqual(config.read_rules(self.paths), default_rules())
        config.write_section(self.paths, config.RULES_SECTION, "nonsense")
        self.assertEqual(config.read_rules(self.paths), default_rules())


class OperatorPageContractTests(unittest.TestCase):
    def _tools_bar(self) -> str:
        tools = OPERATOR_HTML.split('<footer class="tools">', 1)[1]
        return tools.split("</footer>", 1)[0]

    def _setup_drawer(self) -> str:
        drawer = OPERATOR_HTML.split('<div class="drawer" id="setup-drawer"', 1)[1]
        return drawer.split('<div class="drawer" id="field-drawer"', 1)[0]

    def test_the_tool_bar_offers_setup_and_no_halftime_drawer(self) -> None:
        tools = self._tools_bar()
        self.assertIn('data-action="open_setup"', tools)
        self.assertNotIn("open_event", OPERATOR_HTML)
        self.assertNotIn('id="event-drawer"', OPERATOR_HTML)
        self.assertNotIn("event_countdown", OPERATOR_HTML)
        self.assertNotIn("event_countdown", OPERATOR_JS)
        self.assertNotIn("event_countdown", KEYBOARD_JS)

    def test_the_setup_drawer_holds_no_game_command(self) -> None:
        drawer = self._setup_drawer()
        self.assertNotIn("data-command", drawer)
        self.assertIn('data-action="save_rules"', drawer)
        self.assertIn('data-action="restore_default_rules"', drawer)
        for field in ("rule-quarter-minutes", "rule-overtime-minutes", "rule-pregame-minutes",
                      "rule-halftime-minutes", "rule-warmup-minutes", "rule-timeout-seconds",
                      "rule-timeouts-per-half"):
            with self.subTest(field=field):
                self.assertIn(f'id="{field}"', drawer)
        # Typing changes nothing until Save (F-016).
        inputs = re.findall(r"<input[^>]*>", drawer)
        self.assertTrue(inputs)
        for tag in inputs:
            self.assertIn('data-draft="true"', tag)

    def test_the_script_uses_the_two_host_actions_and_derives_nothing(self) -> None:
        self.assertIn("api.rules()", OPERATOR_JS)
        self.assertIn("api.save_rules(", OPERATOR_JS)
        self.assertIn("openDrawer('setup-drawer')", OPERATOR_JS)
        self.assertNotIn("Math.floor", OPERATOR_JS)
        # The crowd TIMEOUT button takes its length from the rules Python
        # sends, so the command it fires is exactly what Python holds.
        self.assertIn("rules.timeout_seconds", OPERATOR_JS)
        self.assertIn('data-field="clocks.game.label"', OPERATOR_HTML)


if __name__ == "__main__":
    unittest.main()
