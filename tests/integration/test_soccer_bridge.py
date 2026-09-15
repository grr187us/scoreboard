"""``SoccerBridge`` contract tests: the airlock, view-model strings, and
command source propagation. Mirrors ``tests/integration/test_bridge.py``'s
style but scoped to soccer's own command set (spec section 3.2, 4).
"""

from __future__ import annotations

import unittest

from scoreboard.host.soccer_app import SoccerApplication
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.persistence import read_action_history

from tests.integration.support import TemporaryDataDirectoryTest


class SoccerBridgeTestCase(TemporaryDataDirectoryTest):
    def make_bridge(self):
        application = SoccerApplication(
            self.paths, diagnostics=NullDiagnostics(), monotonic_clock=self.monotonic,
        )
        self.addCleanup(application.shutdown)
        return application.start_new(), application

    def advance_to_period(self, bridge, label: str):
        """Step ``period_forward`` (confirmed) until ``period`` is reached."""

        view = bridge.get_snapshot()
        guard = 0
        while view["period"] != label and guard < 10:
            result = bridge.command("period_forward", {"confirmed": True}, view["revision"])
            self.assertTrue(result["accepted"], result.get("error"))
            view = result["view"]
            guard += 1
        self.assertEqual(view["period"], label)
        return view


class AirlockTests(SoccerBridgeTestCase):
    def test_unknown_command_is_refused(self) -> None:
        bridge, _ = self.make_bridge()
        result = bridge.command("do_a_backflip", {}, 0)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], "INVALID_COMMAND")

    def test_a_disallowed_argument_is_refused(self) -> None:
        bridge, _ = self.make_bridge()
        result = bridge.command("add_goal", {"team": "home", "points": 6}, 0)
        self.assertFalse(result["accepted"])
        self.assertIsNotNone(result["error"])

    def test_a_refused_command_writes_no_history_row(self) -> None:
        bridge, application = self.make_bridge()
        bridge.command("do_a_backflip", {}, 0)
        # The airlock refuses before the service or the store ever see it, so
        # no row is written at all -- mirroring football's behaviour that an
        # UNKNOWN_COMMAND never reaches record_command().
        history = read_action_history(application.paths.database)
        self.assertEqual([row["command"] for row in history if row["command"] == "do_a_backflip"], [])

    def test_a_non_dict_args_is_refused(self) -> None:
        bridge, _ = self.make_bridge()
        result = bridge.command("add_goal", "home", 0)
        self.assertFalse(result["accepted"])

    def test_stale_revision_is_refused(self) -> None:
        bridge, _ = self.make_bridge()
        result = bridge.command("add_stat", {"team": "home", "stat": "shots", "step": 1}, 999)
        self.assertFalse(result["accepted"])


class SourcePropagationTests(SoccerBridgeTestCase):
    def test_default_source_is_operator_mouse(self) -> None:
        bridge, application = self.make_bridge()
        bridge.command("add_stat", {"team": "home", "stat": "shots", "step": 1}, 0)
        history = read_action_history(application.paths.database)
        rows = [row for row in history if row["command"] == "add_stat"]
        self.assertEqual(rows[-1]["source"], "operator-mouse")

    def test_explicit_source_kwarg_is_recorded(self) -> None:
        bridge, application = self.make_bridge()
        bridge.command(
            "add_stat", {"team": "home", "stat": "shots", "step": 1}, 0, source="operator-keyboard",
        )
        history = read_action_history(application.paths.database)
        rows = [row for row in history if row["command"] == "add_stat"]
        self.assertEqual(rows[-1]["source"], "operator-keyboard")

    def test_source_inside_args_wins_over_the_kwarg(self) -> None:
        """PL-1-style button-box dispatch tags the source inside args."""

        bridge, application = self.make_bridge()
        bridge.command(
            "add_stat",
            {"team": "home", "stat": "shots", "step": 1, "source": "button-box"},
            0,
        )
        history = read_action_history(application.paths.database)
        rows = [row for row in history if row["command"] == "add_stat"]
        self.assertEqual(rows[-1]["source"], "button-box")


class ViewModelAcrossPeriodsTests(SoccerBridgeTestCase):
    def test_pregame_period_display(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        self.assertEqual(view["period"], "PRE")
        self.assertEqual(view["period_display"], "Pregame")

    def test_first_half_period_display(self) -> None:
        bridge, _ = self.make_bridge()
        view = self.advance_to_period(bridge, "1st")
        self.assertEqual(view["period_display"], "1st Half")
        self.assertEqual(view["lifecycle"], "IN_PROGRESS")

    def test_halftime_period_display(self) -> None:
        bridge, _ = self.make_bridge()
        view = self.advance_to_period(bridge, "HALF")
        self.assertEqual(view["period_display"], "Halftime")
        self.assertEqual(view["lifecycle"], "HALFTIME")

    def test_second_half_period_display(self) -> None:
        bridge, _ = self.make_bridge()
        view = self.advance_to_period(bridge, "2nd")
        self.assertEqual(view["period_display"], "2nd Half")

    def test_final_period_hides_the_clock_and_sets_lifecycle(self) -> None:
        bridge, _ = self.make_bridge()
        view = self.advance_to_period(bridge, "FINAL")
        self.assertEqual(view["period_display"], "Final")
        self.assertEqual(view["lifecycle"], "FINAL")
        self.assertEqual(view["board"]["hidden_widgets"], ["game_clock_label", "game_clock_value"])

    def test_a_goal_is_refused_outside_a_live_period(self) -> None:
        bridge, _ = self.make_bridge()
        result = bridge.command("add_goal", {"team": "home"}, bridge.get_snapshot()["revision"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], "GOAL_NOT_ALLOWED")

    def test_a_goal_is_accepted_during_a_live_period_and_updates_score(self) -> None:
        bridge, _ = self.make_bridge()
        view = self.advance_to_period(bridge, "1st")
        result = bridge.command("add_goal", {"team": "home"}, view["revision"])
        self.assertTrue(result["accepted"], result.get("error"))
        self.assertEqual(result["view"]["teams"]["home"]["score"], 1)


class StatsAndCardsTests(SoccerBridgeTestCase):
    def test_add_stat_updates_the_view_and_its_display_string(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        result = bridge.command("add_stat", {"team": "away", "stat": "corners", "step": 1}, view["revision"])
        self.assertTrue(result["accepted"], result.get("error"))
        away = result["view"]["soccer"]["away"]
        self.assertEqual(away["corners"], 1)
        self.assertEqual(away["corners_display"], "COR 1")

    def test_add_card_updates_counts_and_rows(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        result = bridge.command(
            "add_card", {"team": "home", "kind": "yellow", "player": 10}, view["revision"],
        )
        self.assertTrue(result["accepted"], result.get("error"))
        cards = result["view"]["soccer"]["home"]["cards"]
        self.assertEqual(cards["yellow"], 1)
        self.assertEqual(len(cards["rows"]), 1)
        self.assertEqual(cards["rows"][0]["player_number"], 10)

    def test_a_red_card_is_reflected_in_its_own_count(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        result = bridge.command(
            "add_card", {"team": "away", "kind": "red", "player": 4}, view["revision"],
        )
        self.assertTrue(result["accepted"], result.get("error"))
        cards = result["view"]["soccer"]["away"]["cards"]
        self.assertEqual(cards["red"], 1)
        self.assertEqual(cards["display"], "Y 0 · R 1")


class ShootoutTests(SoccerBridgeTestCase):
    def _enter_shootout(self, bridge):
        view = bridge.get_snapshot()
        result = bridge.command("set_period", {"label": "SHOOTOUT", "confirmed": True}, view["revision"])
        self.assertTrue(result["accepted"], result.get("error"))
        return result["view"]

    def test_shootout_view_is_active_once_the_period_is_set(self) -> None:
        bridge, _ = self.make_bridge()
        view = self._enter_shootout(bridge)
        self.assertTrue(view["soccer"]["shootout"]["active"])
        self.assertEqual(view["board"]["hidden_widgets"], ["game_clock_label", "game_clock_value"])

    def test_first_kicker_and_a_kick_update_the_tally(self) -> None:
        bridge, _ = self.make_bridge()
        view = self._enter_shootout(bridge)
        result = bridge.command("set_shootout_first_kicker", {"team": "home"}, view["revision"])
        self.assertTrue(result["accepted"], result.get("error"))
        view = result["view"]
        result = bridge.command(
            "shootout_kick", {"team": "home", "made": True, "player": 7}, view["revision"],
        )
        self.assertTrue(result["accepted"], result.get("error"))
        shootout = result["view"]["soccer"]["shootout"]
        self.assertEqual(shootout["home_made"], 1)
        self.assertEqual(shootout["next_team"], "away")


class StatusAndHealthTests(SoccerBridgeTestCase):
    def test_status_is_blank_when_nothing_is_raised(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        self.assertEqual(view["status"]["display"], "")

    def test_set_game_status_raises_the_crowd_word(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        result = bridge.command(
            "set_game_status", {"label": "WEATHER", "seconds": 1800}, view["revision"],
        )
        self.assertTrue(result["accepted"], result.get("error"))
        self.assertEqual(result["view"]["status"]["label"], "WEATHER")
        self.assertTrue(result["view"]["status"]["active"])

    def test_health_carries_revision_display_and_persistence(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        self.assertIn("revision", view["health"])
        self.assertIn("display", view["health"])
        self.assertIn("persistence", view["health"])
        self.assertTrue(view["health"]["persistence"]["saved"])

    def test_button_box_defaults_to_none(self) -> None:
        bridge, _ = self.make_bridge()
        self.assertIsNone(bridge.get_snapshot()["button_box"])

    def test_set_button_box_status_is_reflected_in_the_view(self) -> None:
        bridge, _ = self.make_bridge()
        bridge.set_button_box_status({"active": True, "registered": ["F21", "F22"]})
        self.assertEqual(bridge.get_snapshot()["button_box"]["active"], True)


class UndoAndHistoryTests(SoccerBridgeTestCase):
    def test_no_last_action_before_any_command(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        self.assertIsNone(view["last_action"])
        self.assertFalse(view["can_undo"])
        self.assertEqual(view["undo_depth"], 0)

    def test_an_undoable_command_becomes_the_last_action(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        bridge.command("add_stat", {"team": "home", "stat": "shots", "step": 1}, view["revision"])
        view = bridge.get_snapshot()
        self.assertIsNotNone(view["last_action"])
        self.assertTrue(view["can_undo"])
        self.assertEqual(view["undo_depth"], 1)

    def test_undo_reverses_the_last_command(self) -> None:
        bridge, _ = self.make_bridge()
        view = bridge.get_snapshot()
        bridge.command("add_stat", {"team": "home", "stat": "shots", "step": 1}, view["revision"])
        view = bridge.get_snapshot()
        self.assertEqual(view["soccer"]["home"]["shots"], 1)
        result = bridge.command("undo", {}, view["revision"])
        self.assertTrue(result["accepted"], result.get("error"))
        self.assertEqual(result["view"]["soccer"]["home"]["shots"], 0)


class MercyAndPeriodDecisionTests(SoccerBridgeTestCase):
    def test_mercy_not_reached_at_the_start(self) -> None:
        bridge, _ = self.make_bridge()
        self.assertFalse(bridge.get_snapshot()["mercy_reached"])

    def test_period_decision_is_present_and_not_pending_at_the_start(self) -> None:
        bridge, _ = self.make_bridge()
        decision = bridge.get_snapshot()["period_decision"]
        self.assertIn("pending", decision)
        self.assertFalse(decision["pending"])


if __name__ == "__main__":
    unittest.main()
