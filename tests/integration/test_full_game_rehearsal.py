"""A complete four-quarter game driven through the real bridge (R-006).

Every other suite proves one behaviour in isolation. This one asks the question
an operator actually cares about: after a whole game -- pregame countdown, four
quarters of snap-by-snap play-clock work, halftime, corrections, an undo, a
crash in the third quarter, and End Game -- does the board still agree with what
happened on the field, and does the durable history explain it?

It is a fake-time rehearsal, not the Task 12 acceptance run: no window opens, no
real second passes, and nothing here can substitute for a two-hour soak on the
target laptop. What it does prove is that the state, clock, persistence, and
recovery layers stay consistent across a game-length sequence of real commands
rather than across the handful each focused test issues.
"""

from __future__ import annotations

import unittest

from scoreboard.application.recovery import (
    RecoverySource,
    inspect_recovery,
    resume_recovered_game,
)
from scoreboard.domain.formatting import displayed_second
from scoreboard.host.bridge import DisplayLink, ScoreboardBridge
from scoreboard.infrastructure.persistence import read_action_history

from tests.integration.support import TemporaryDataDirectoryTest

#: Plays simulated per quarter. Enough to accumulate any per-command rounding
#: error while keeping the whole rehearsal well under a second of test time.
PLAYS_PER_QUARTER = 30

#: Seconds of game clock consumed by one simulated play.
PLAY_SECONDS = 12.0

QUARTER_SECONDS = 12 * 60.0


class FullGameRehearsal(TemporaryDataDirectoryTest):
    """One game, start to FINAL, through the same bridge the operator uses."""

    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.bridge = ScoreboardBridge(self.service, self.store, display=DisplayLink())
        self.revisions: list[int] = [self.service.revision]
        self.expected_home = 0
        self.expected_away = 0

    # --- Driving the board --------------------------------------------------

    def send(self, name: str, args: dict | None = None, *, confirm: bool = False) -> dict:
        """Submit one command the way the operator view does, and keep score.

        A ``CONFIRMATION_REQUIRED`` answer is resubmitted with ``confirmed``
        exactly once, mirroring the dialog, so the rehearsal exercises the real
        two-step path rather than skipping past it.
        """

        payload = dict(args or {})
        result = self.bridge.command(name, payload, self.service.revision)
        if result["confirmation_required"] and confirm:
            payload["confirmed"] = True
            result = self.bridge.command(name, payload, result["view"]["revision"])
        self.revisions.append(result["view"]["revision"])
        self.assertTrue(
            result["view"]["health"]["persistence"]["saved"],
            result["view"]["health"]["persistence"]["message"],
        )
        return result

    def advance(self, seconds: float, step: float = 0.25) -> None:
        """Let time pass the way the host does: fixed refresh ticks, no sleeping."""

        remaining = seconds
        while remaining > 1e-9:
            move = min(step, remaining)
            self.monotonic.advance(move)
            remaining -= move
            self.bridge.tick()

    def play(self, seconds: float = PLAY_SECONDS) -> None:
        """One snap: 40-second play clock, snap, game clock runs, whistle."""

        self.send("play_clock_preset", {"seconds": 40})
        self.send("play_clock_start")
        self.advance(4.0)
        # The snap. Starting the game clock blanks the play clock (F-048).
        self.send("game_clock_start")
        self.advance(seconds)
        self.send("game_clock_stop")

    def score(self, team: str, points: int) -> None:
        self.send("add_score", {"team": team, "points": points})
        if team == "home":
            self.expected_home += points
        else:
            self.expected_away += points

    def quarter(self, label: str) -> None:
        self.send("set_quarter", {"label": label}, confirm=True)
        self.send("game_clock_reset")

    def history(self) -> list[dict]:
        return read_action_history(self.paths.database)

    # --- The rehearsal ------------------------------------------------------

    def test_a_whole_game_stays_consistent_from_pregame_to_final(self) -> None:
        self.send("set_team_name", {"team": "home", "name": "Tigers"})
        self.send("set_team_name", {"team": "away", "name": "Eagles"})

        # Pregame: the 30:00 countdown runs down on its own and expires.
        # Follow-up 01 "unified pregame clock": while PRE is selected the
        # game-clock engine is the one authoritative KICKOFF IN countdown in
        # both operator and spectator views (docs/MVP_REQUIREMENTS.md F-025),
        # so Game Clock Start -- not the separate event-countdown commands --
        # is what actually runs it down.
        self.send("game_clock_start")
        self.advance(30 * 60.0, step=1.0)
        view = self.bridge.get_snapshot()
        self.assertEqual(view["clocks"]["event"]["display"], "0:00")
        self.assertFalse(view["clocks"]["event"]["running"])

        # First half.
        self.quarter("1st")
        for index in range(PLAYS_PER_QUARTER):
            self.play()
            if index == 9:
                self.score("home", 6)
                self.score("home", 1)
            if index == 22:
                self.score("away", 3)

        self.quarter("2nd")
        for index in range(PLAYS_PER_QUARTER):
            self.play()
            if index == 15:
                self.score("away", 6)
                self.score("away", 2)

        # An operator mis-click and its undo, mid-game, with clocks stopped.
        self.send("add_score", {"team": "home", "points": 3})
        self.send("undo")
        self.assertEqual(self.bridge.get_snapshot()["teams"]["home"]["score"],
                         self.expected_home)

        # Halftime: one 15:00 countdown whose label becomes WARMUP at 3:00.
        self.send("set_quarter", {"label": "HALF"}, confirm=True)
        self.send("event_countdown_select", {"label": "HALFTIME"})
        self.send("event_countdown_start")
        self.advance(11 * 60.0 + 59.0, step=1.0)
        self.assertEqual(self.bridge.get_snapshot()["clocks"]["event"]["phase"], "HALFTIME")
        self.advance(2.0)
        self.assertEqual(self.bridge.get_snapshot()["clocks"]["event"]["phase"], "WARMUP")
        self.advance(3 * 60.0, step=1.0)

        # Second half, interrupted by a crash partway through the third.
        self.quarter("3rd")
        for _ in range(12):
            self.play()
        self.score("home", 6)

        self.crash_and_resume()

        for _ in range(PLAYS_PER_QUARTER - 12):
            self.play()

        self.quarter("4th")
        for index in range(PLAYS_PER_QUARTER):
            self.play()
            if index == 27:
                self.score("home", 3)

        # A scoreboard correction after the final whistle, then End Game.
        self.send("correct_score", {"team": "away", "points": 2})
        self.expected_away -= 2
        self.send("end_game")

        self.assert_board_matches_the_field()
        self.assert_history_explains_the_game()

    # --- The interruption ---------------------------------------------------

    def crash_and_resume(self) -> None:
        """Drop the process mid-quarter with a clock running, then restart."""

        self.send("play_clock_preset", {"seconds": 25})
        self.send("play_clock_start")
        self.send("game_clock_start")
        self.advance(7.0)
        before = self.service.materialized_state()
        self.store.close()  # No shutdown record: this is a crash, not an exit.

        report = inspect_recovery(self.paths)
        self.assertEqual(report.source, RecoverySource.PRIMARY)
        self.assertTrue(report.can_resume)
        self.assertEqual(report.state.home_score, before.home_score)
        self.assertEqual(report.state.away_score, before.away_score)
        self.assertEqual(report.state.quarter, before.quarter)
        self.assertEqual(report.state.home_name, "Tigers")

        # P-004: every clock comes back stopped, no more than one displayed
        # second behind where it was, and never ahead of it.
        self.assertFalse(report.state.game_clock.running)
        self.assertFalse(report.state.play_clock.running)
        self.assertGreaterEqual(
            report.state.game_clock.seconds, before.game_clock.seconds
        )
        self.assertLessEqual(
            displayed_second(report.state.game_clock.seconds)
            - displayed_second(before.game_clock.seconds),
            1,
        )

        self.service = resume_recovered_game(report, monotonic_clock=self.monotonic)
        self.store = self.make_store()
        self.store.begin_session(self.service.state, resume_game_id=report.game_id)
        self.bridge = ScoreboardBridge(self.service, self.store, display=DisplayLink())
        self.revisions.append(self.service.revision)

    # --- Assertions ---------------------------------------------------------

    def assert_board_matches_the_field(self) -> None:
        view = self.bridge.get_snapshot()

        self.assertEqual(view["teams"]["home"]["name"], "Tigers")
        self.assertEqual(view["teams"]["away"]["name"], "Eagles")
        self.assertEqual(view["teams"]["home"]["score"], self.expected_home)
        self.assertEqual(view["teams"]["away"]["score"], self.expected_away)
        self.assertEqual(view["lifecycle"], "FINAL")
        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertFalse(view["clocks"]["play"]["running"])
        self.assertTrue(view["health"]["persistence"]["saved"])

        # No clock ever went below zero or above its configured maximum.
        self.assertGreaterEqual(view["clocks"]["game"]["seconds"], 0.0)
        self.assertLessEqual(view["clocks"]["game"]["seconds"], QUARTER_SECONDS)
        self.assertGreaterEqual(view["clocks"]["play"]["seconds"], 0.0)
        self.assertLessEqual(view["clocks"]["play"]["seconds"], 40.0)

        # The game clock consumed exactly the simulated playing time. A crash
        # and a restart in the middle must not have moved it.
        consumed = QUARTER_SECONDS - view["clocks"]["game"]["seconds"]
        self.assertAlmostEqual(consumed, PLAYS_PER_QUARTER * PLAY_SECONDS, places=6)

    def assert_history_explains_the_game(self) -> None:
        rows = self.history()
        sequences = [int(row["sequence"]) for row in rows]

        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(len(sequences), len(set(sequences)))
        for row in rows:
            self.assertIn(row["result"], ("ACCEPTED", "REJECTED"))
            self.assertTrue(row["wall_clock"])
            self.assertTrue(row["app_version"])
            self.assertIsNotNone(row["state_revision"])

        commands = [str(row["command"]) for row in rows]
        for required in (
            "set_team_name",
            "add_score",
            "correct_score",
            "undo",
            "set_quarter",
            "game_clock_start",
            "game_clock_stop",
            "game_clock_reset",
            "play_clock_preset",
            "play_clock_start",
            "event_countdown_start",
            "end_game",
            "session_started",
            "session_resumed",
        ):
            self.assertIn(required, commands, f"{required} missing from the history")

        # The countdowns ran themselves to zero, so their expiry is recorded
        # even though no operator pressed anything (F-037, F-046).
        self.assertIn("event_countdown_expired", commands)

        # Revisions only ever move forward, including across the restart.
        self.assertEqual(self.revisions, sorted(self.revisions))

        # Undo appended a forward transition rather than deleting history.
        self.assertGreater(
            commands.index("undo"), commands.index("set_team_name"), "undo was recorded"
        )


if __name__ == "__main__":
    unittest.main()
