"""A complete soccer game driven through SoccerService + SoccerGameStore (spec section 9).

Mirrors tests/integration/test_full_game_rehearsal.py's intent for football, but soccer has no
bridge in this agent's ownership yet (agent B owns SoccerBridge), so this drives
``SoccerService.submit`` directly and persists through ``SoccerGameStore``, exactly the way
``inspect_soccer_recovery``/``resume_recovered_soccer_game`` are meant to be exercised.

Stages: PRE -> 1st -> goals -> cards -> HALF -> 2nd -> crash/resume with stopped clocks -> OT1
-> OT2 -> SHOOTOUT -> finish with +1 credit -> FINAL.
"""

from __future__ import annotations

import unittest

from scoreboard.application.soccer_recovery import (
    inspect_soccer_recovery,
    resume_recovered_soccer_game,
)
from scoreboard.application.soccer_service import SoccerService
from scoreboard.domain.soccer.commands import (
    add_card,
    add_goal,
    add_stat,
    game_clock_start,
    game_clock_stop,
    set_period,
    set_shootout_first_kicker,
    set_team_name,
    shootout_kick,
    undo,
)
from scoreboard.domain.soccer.rules import SoccerRules
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.infrastructure.persistence import read_action_history
from scoreboard.infrastructure.soccer_store import SoccerGameStore

from tests.integration.support import TemporaryDataDirectoryTest


class SoccerFullGameRehearsal(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.soccer_paths = ScoreboardPaths(self.paths.root / "soccer")
        self.soccer_paths.ensure()
        self.rules = SoccerRules(overtime_periods=2, shootout_enabled=True, shootout_credit_goal=True)
        self.service = SoccerService(monotonic_clock=self.monotonic, rules=self.rules)
        self.store = SoccerGameStore.open(self.soccer_paths, wall_clock=self.wall_clock)
        self.addCleanup(self.store.close)
        status = self.store.begin_session(self.service.state)
        self.assertTrue(status.saved, status.message)

    def send(self, command) -> object:
        result = self.service.submit(command)
        status = self.store.record_command(command, result)
        self.assertTrue(result.accepted, f"{command} was rejected: {result.error}")
        self.assertTrue(status.saved, status.message)
        return result

    def test_full_game(self) -> None:
        service = self.service

        # PRE
        self.send(set_team_name("home", "Eagles"))
        self.send(set_team_name("away", "Tigers"))
        self.assertEqual(service.state.period, "PRE")
        self.assertEqual(service.state.lifecycle, "PRE_GAME")

        # PRE -> 1st
        self.send(set_period("1st", confirmed=True))
        self.assertEqual(service.state.game_clock.seconds, self.rules.half_seconds)
        self.send(game_clock_start())
        self.monotonic.advance(600.0)

        # Goals
        self.send(add_goal("home"))
        self.send(add_goal("away"))
        self.send(add_goal("home"))
        self.assertEqual((service.state.home_score, service.state.away_score), (2, 1))

        # Stats
        self.send(add_stat("home", "shots", 1))
        self.send(add_stat("home", "corners", 1))

        # Cards
        self.send(add_card("away", "yellow", player=10))
        self.send(add_card("home", "red", player=4))
        self.assertEqual(len(service.state.cards), 2)
        # correct a mis-recorded card via undo
        self.send(undo())
        self.assertEqual(len(service.state.cards), 1)
        self.send(add_card("home", "red", player=4))

        self.send(game_clock_stop())

        # 1st -> HALF
        self.send(set_period("HALF", confirmed=True))
        self.assertEqual(service.state.game_clock.seconds, self.rules.halftime_seconds)
        self.assertEqual(service.state.lifecycle, "HALFTIME")

        # HALF -> 2nd
        self.send(set_period("2nd", confirmed=True))
        self.assertEqual(service.state.game_clock.seconds, self.rules.half_seconds)
        self.send(game_clock_start())
        self.monotonic.advance(300.0)
        self.send(add_goal("away"))
        self.assertEqual((service.state.home_score, service.state.away_score), (2, 2))

        # --- Crash and resume, clocks stopped ---
        revision_before_crash = service.state.revision
        self.store.close()
        report = inspect_soccer_recovery(self.soccer_paths)
        self.assertTrue(report.can_resume)
        self.assertEqual(report.state.revision, revision_before_crash)
        self.assertFalse(report.state.game_clock.running, "recovery always stops every clock")

        service = resume_recovered_soccer_game(report, monotonic_clock=self.monotonic, rules=self.rules)
        self.service = service
        self.store = SoccerGameStore.open(self.soccer_paths, wall_clock=self.wall_clock)
        self.addCleanup(self.store.close)
        resume_status = self.store.begin_session(service.state, resume_game_id=report.game_id)
        self.assertTrue(resume_status.saved)

        # Natural expiry of 2nd -> period decision pending
        self.send(game_clock_start())
        self.monotonic.advance(self.rules.half_seconds + 1.0)
        service.observe_tick()
        decision = service.period_decision()
        self.assertTrue(decision["pending"])
        self.assertIn("Overtime 1", [c["label"] for c in decision["choices"]])

        # 2nd -> OT1
        self.send(set_period("OT1", confirmed=True))
        self.assertEqual(service.state.game_clock.seconds, self.rules.overtime_seconds)
        self.send(game_clock_start())
        self.monotonic.advance(self.rules.overtime_seconds + 1.0)
        service.observe_tick()
        self.assertTrue(service.period_decision()["pending"])

        # OT1 -> OT2
        self.send(set_period("OT2", confirmed=True))
        self.send(game_clock_start())
        self.monotonic.advance(self.rules.overtime_seconds + 1.0)
        service.observe_tick()
        decision = service.period_decision()
        self.assertTrue(decision["pending"])
        self.assertIn("Shootout", [c["label"] for c in decision["choices"]])

        # OT2 -> SHOOTOUT
        self.send(set_period("SHOOTOUT", confirmed=True))
        self.assertEqual(service.state.period, "SHOOTOUT")
        self.send(set_shootout_first_kicker("home"))
        for team, made in (
            ("home", True), ("away", False),
            ("home", True), ("away", False),
            ("home", True), ("away", False),
        ):
            self.send(shootout_kick(team, made))
        self.assertTrue(service.state.shootout_winner is None)

        from scoreboard.domain.soccer.shootout import is_decided, winner as shootout_winner

        self.assertTrue(is_decided(service.state.shootout_kicks, self.rules.shootout_initial_kickers))
        derived = shootout_winner(service.state.shootout_kicks, self.rules.shootout_initial_kickers)
        self.assertEqual(derived, "home")

        from scoreboard.domain.soccer.commands import finish_shootout

        pre_finish_score = service.state.home_score
        self.send(finish_shootout(winner="home"))
        self.assertEqual(service.state.period, "FINAL")
        self.assertEqual(service.state.lifecycle, "FINAL")
        self.assertEqual(service.state.shootout_winner, "home")
        self.assertEqual(service.state.home_score, pre_finish_score + 1)

        # The durable history explains the whole game.
        rows = read_action_history(self.soccer_paths.database)
        commands_seen = {row["command"] for row in rows}
        self.assertIn("add_goal", commands_seen)
        self.assertIn("add_card", commands_seen)
        self.assertIn("finish_shootout", commands_seen)
        self.assertGreater(len(rows), 10)


if __name__ == "__main__":
    unittest.main()
