"""Field Assistant durable-composite and game-flow rehearsals (FA-17, 18, 21–25, 28).

These tests deliberately use the public bridge over a real SQLite store.  The
pure rule matrix and the helper-window lifecycle have narrower tests elsewhere;
this file proves the higher-risk boundary: a finalized result is one durable,
complete update that still behaves correctly through a representative
multi-quarter operator sequence and recovery.
"""

from __future__ import annotations

import unittest

from scoreboard.application.recovery import inspect_recovery
from scoreboard.domain.commands import CommandType
from scoreboard.domain.formatting import (
    format_distance,
    format_down,
    format_down_and_distance,
    format_possession,
    format_timeouts,
)
from scoreboard.host.bridge import ScoreboardBridge
from scoreboard.infrastructure.persistence import (
    decode,
    read_action_history,
    read_stored_game,
)

from tests.integration.support import FailingConnection, TemporaryDataDirectoryTest


class FieldAssistantRehearsalCase(TemporaryDataDirectoryTest):
    """One public operator bridge and one real on-disk game per test."""

    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.published: list[dict] = []
        self.bridge = ScoreboardBridge(
            self.service, self.store, on_accepted=self.published.append
        )
        self.send("set_quarter", {"label": "1st", "confirmed": True})

    def send(self, name: str, args: dict | None = None) -> dict:
        result = self.bridge.command(name, args or {}, self.service.revision)
        self.assertTrue(result["accepted"], result["error"])
        return result

    def finalize(self, kind: str, payload: dict, *, revision: int | None = None) -> dict:
        result = self.bridge.finalize_field_action(
            {"kind": kind, "payload": payload},
            self.service.revision if revision is None else revision,
        )
        self.assertTrue(result["accepted"], result["error"])
        return result

    def start_home_series(self, spot: int = 25) -> dict:
        return self.finalize(
            "start_series",
            {
                "offense": "home",
                "ball_absolute": spot,
                "first_quarter_home_direction": 1,
            },
        )

    @staticmethod
    def football(view: dict) -> dict:
        return view["football"]


class AtomicCompositeTests(FieldAssistantRehearsalCase):
    """FA-17/18: no observer or durable row can see a half-applied play."""

    def test_scoring_finalize_is_one_revision_one_history_row_one_complete_publish(self) -> None:
        self.start_home_series(94)
        before_revision = self.service.revision
        before_history = len(read_action_history(self.paths.database))
        before_publishes = len(self.published)

        result = self.finalize("touchdown", {"scoring_team": "home", "add_score": True})

        self.assertEqual(result["view"]["revision"], before_revision + 1)
        self.assertEqual(len(self.published), before_publishes + 1)
        published = self.published[-1]
        self.assertEqual(published["revision"], before_revision + 1)
        self.assertEqual(published["teams"]["home"]["score"], 6)
        football = self.football(published)
        # The bridge's established display convention (BLANK_DISPLAY, and its
        # own "—" for a cleared ball_on) is not this test's to change; assert
        # the raw cleared values and the same formatters/literal it emits.
        self.assertEqual(football["down"], None)
        self.assertEqual(football["distance"], None)
        self.assertEqual(football["possession"], None)
        self.assertEqual(football["ball_on"], None)
        self.assertEqual(football["down_display"], format_down(None))
        self.assertEqual(football["distance_display"], format_distance(None))
        self.assertEqual(
            football["down_distance_display"], format_down_and_distance(None, None)
        )
        self.assertEqual(football["possession_display"], format_possession(None))
        self.assertEqual(football["ball_on_display"], "—")
        self.assertEqual(football["timeouts"], {"home": 3, "away": 3})
        self.assertEqual(football["home_timeouts_display"], format_timeouts(3))
        self.assertEqual(football["away_timeouts_display"], format_timeouts(3))
        assistant = published["assistant"]
        self.assertIsNone(assistant["ball_absolute"])
        self.assertIsNone(assistant["line_to_gain"])
        self.assertEqual(assistant["first_quarter_home_direction"], 1)
        self.assertEqual(assistant["home_goal_side"], "left")
        self.assertIsNone(assistant["offense_direction"])
        rows = read_action_history(self.paths.database)
        self.assertEqual(len(rows), before_history + 1)
        row = rows[-1]
        self.assertEqual(row["command"], CommandType.FINALIZE_FIELD_ACTION.value)
        self.assertEqual(row["state_revision"], before_revision + 1)
        durable = read_stored_game(self.paths.database)
        self.assertEqual(durable.state_revision, before_revision + 1)
        self.assertIsNone(durable.state.ball_on)
        details = decode(row["new_value"])
        self.assertEqual(details["classification"], "touchdown")
        self.assertEqual(details["score_delta"], {"away": 0, "home": 6})

    def test_undo_restores_every_field_and_score_from_one_finalization(self) -> None:
        started = self.start_home_series(94)["view"]
        self.finalize("touchdown", {"scoring_team": "home", "add_score": True})
        before_undo_history = len(read_action_history(self.paths.database))

        undone = self.send("undo")["view"]

        self.assertEqual(undone["teams"]["home"]["score"], started["teams"]["home"]["score"])
        self.assertEqual(self.football(undone), self.football(started))
        self.assertEqual(undone["assistant"], started["assistant"])
        rows = read_action_history(self.paths.database)
        self.assertEqual(len(rows), before_undo_history + 1)
        self.assertEqual(rows[-1]["command"], "undo")
        self.assertEqual(rows[-1]["field"], "field_assistant")


class IsolationAndRecoveryTests(FieldAssistantRehearsalCase):
    """FA-21–24: auxiliary play handling cannot disturb clocks or recovery."""

    def test_finalize_preserves_running_game_and_play_clock_values_exactly(self) -> None:
        self.start_home_series()
        self.send("game_clock_start")
        self.send("play_clock_preset_start", {"seconds": 40})
        before_game = self.service.state.game_clock
        before_play = self.service.state.play_clock
        before_event = self.service.state.event_countdown

        result = self.finalize("normal_play", {"final_absolute": 29})

        self.assertEqual(self.service.state.game_clock, before_game)
        self.assertEqual(self.service.state.play_clock, before_play)
        self.assertEqual(self.service.state.event_countdown, before_event)
        self.assertTrue(result["view"]["clocks"]["game"]["running"])
        self.assertTrue(result["view"]["clocks"]["play"]["running"])

    def test_active_series_and_a_committed_play_recover_with_their_series_state(self) -> None:
        self.start_home_series(25)
        self.finalize("normal_play", {"final_absolute": 31})

        report = inspect_recovery(self.paths)

        self.assertTrue(report.can_resume)
        assert report.state is not None
        self.assertEqual(report.state.possession, "home")
        self.assertEqual(report.state.down, 2)
        self.assertEqual(report.state.distance, 4)
        self.assertEqual(report.state.ball_on.yard_line, 31)
        self.assertEqual(report.state.assistant_first_quarter_home_direction, 1)
        self.assertEqual(report.state.assistant_line_to_gain, 35)
        self.assertFalse(report.state.game_clock.running)
        self.assertFalse(report.state.play_clock.running)

    def test_failed_finalize_persists_neither_partial_state_nor_history_and_operator_recovers(self) -> None:
        self.start_home_series(94)
        durable_before = read_stored_game(self.paths.database)
        history_before = read_action_history(self.paths.database)
        failing = FailingConnection(self.store._connection, fail_execute=True)
        self.store._connection = failing

        result = self.bridge.finalize_field_action(
            {"kind": "touchdown", "payload": {"scoring_team": "home", "add_score": True}},
            self.service.revision,
        )

        self.assertTrue(result["accepted"], result["error"])
        self.assertEqual(result["view"]["health"]["persistence"]["label"], "NOT SAVED")
        durable_after = read_stored_game(self.paths.database)
        self.assertEqual(durable_after.state, durable_before.state)
        self.assertEqual(read_action_history(self.paths.database), history_before)

        failing.fail_execute = False
        recovered = self.send("add_score", {"team": "away", "points": 1})
        self.assertEqual(recovered["view"]["health"]["persistence"]["label"], "SAVED")
        durable_recovered = read_stored_game(self.paths.database)
        self.assertEqual(durable_recovered.state.home_score, 6)
        self.assertEqual(durable_recovered.state.away_score, 1)
        self.assertEqual(
            [row["command"] for row in read_action_history(self.paths.database)[-2:]],
            [CommandType.FINALIZE_FIELD_ACTION.value, "add_score"],
        )


class MultiQuarterRehearsalTests(FieldAssistantRehearsalCase):
    """FA-28: one compact offline sequence across the supported workflows."""

    def test_multi_quarter_sequence_agrees_in_views_history_and_recovery(self) -> None:
        self.start_home_series(25)                         # 1st & 10 HOME 25
        self.finalize("normal_play", {"final_absolute": 31})       # gain
        self.finalize("normal_play", {"final_absolute": 28})       # loss
        self.finalize("incomplete_pass", {})                        # incomplete
        self.finalize(                                             # penalty: repeat down
            "penalty", {"enforced_absolute": 33, "resolution": "repeat_down"}
        )
        self.finalize("turnover", {"new_offense": "away", "final_absolute": 33})

        second_quarter = self.send("set_quarter", {"label": "2nd", "confirmed": True})
        self.assertEqual(second_quarter["view"]["assistant"]["home_goal_side"], "right")
        touchdown = self.finalize("touchdown", {"scoring_team": "away", "add_score": True})
        self.assertEqual(touchdown["view"]["teams"]["away"]["score"], 6)
        self.finalize("try", {"scoring_team": "away", "points": 1})
        kickoff = self.finalize("kickoff", {"receiving_team": "home", "final_absolute": 25})
        self.assertEqual(self.football(kickoff["view"])["down_distance_display"], "1st & 10")
        self.assertEqual(kickoff["view"]["assistant"]["ball_absolute"], 25)

        third_quarter = self.send("set_quarter", {"label": "3rd", "confirmed": True})
        self.assertEqual(third_quarter["view"]["assistant"]["home_goal_side"], "left")
        third_quarter_play = self.finalize("normal_play", {"final_absolute": 34})
        self.assertEqual(third_quarter_play["view"]["assistant"]["ball_absolute"], 34)
        self.send("set_quarter", {"label": "4th", "confirmed": True})
        final_play = self.finalize("incomplete_pass", {})

        view = final_play["view"]
        self.assertEqual(view["quarter"], "4th")
        self.assertEqual(view["teams"]["away"]["score"], 7)
        self.assertEqual(self.football(view)["possession"], "home")
        self.assertEqual(self.football(view)["down"], 3)
        self.assertEqual(view["assistant"]["first_quarter_home_direction"], 1)
        self.assertEqual(view["assistant"]["line_to_gain"], 35)

        finalizations = [
            row for row in read_action_history(self.paths.database)
            if row["command"] == CommandType.FINALIZE_FIELD_ACTION.value
        ]
        self.assertEqual(len(finalizations), 11)
        self.assertEqual(finalizations[-1]["state_revision"], view["revision"])
        self.assertEqual(decode(finalizations[-1]["new_value"])["classification"], "incomplete_pass")

        report = inspect_recovery(self.paths)
        assert report.state is not None
        self.assertEqual(report.state.revision, view["revision"])
        self.assertEqual(report.state.away_score, 7)
        self.assertEqual(report.state.possession, "home")
        self.assertEqual(report.state.down, 3)
        self.assertEqual(report.state.assistant_line_to_gain, 35)


if __name__ == "__main__":
    unittest.main()
