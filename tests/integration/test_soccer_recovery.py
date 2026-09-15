"""Integration tests for scoreboard.application.soccer_recovery.

Mirrors tests/integration/test_recovery.py's shape. Includes the required cross-sport isolation
test: a football database in <root> is never offered to soccer at <root>/soccer, and vice versa.
"""

from __future__ import annotations

from scoreboard.application.recovery import RecoverySource, inspect_recovery
from scoreboard.application.service import ScoreboardService
from scoreboard.application.soccer_recovery import (
    inspect_soccer_recovery,
    resume_recovered_soccer_game,
    soccer_stopped_state,
    start_new_soccer_game,
)
from scoreboard.application.soccer_service import SoccerService
from scoreboard.domain.soccer.commands import game_clock_start, set_period, set_score
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.infrastructure.persistence import GameStore
from scoreboard.infrastructure.soccer_store import SoccerGameStore
from tests.integration.support import TemporaryDataDirectoryTest


class SoccerRecoveryTests(TemporaryDataDirectoryTest):
    def soccer_paths(self) -> ScoreboardPaths:
        paths = ScoreboardPaths(self.paths.root / "soccer")
        paths.ensure()
        return paths

    def test_no_saved_game_reports_none(self) -> None:
        report = inspect_soccer_recovery(self.soccer_paths())
        self.assertEqual(report.source, RecoverySource.NONE)
        self.assertFalse(report.can_resume)

    def test_a_saved_game_can_be_resumed_with_clocks_stopped(self) -> None:
        soccer_paths = self.soccer_paths()
        service = SoccerService(monotonic_clock=self.monotonic)
        store = SoccerGameStore.open(soccer_paths, wall_clock=self.wall_clock)
        self.addCleanup(store.close)
        store.begin_session(service.state)

        cmd = set_period("1st", confirmed=True)
        result = service.submit(cmd)
        store.record_command(cmd, result)
        start_cmd = game_clock_start()
        start_result = service.submit(start_cmd)
        store.record_command(start_cmd, start_result)
        store.close()

        report = inspect_soccer_recovery(soccer_paths)
        self.assertTrue(report.can_resume)
        self.assertEqual(report.state.period, "1st")
        self.assertFalse(report.state.game_clock.running)

        resumed = resume_recovered_soccer_game(report)
        self.assertEqual(resumed.state.period, "1st")
        self.assertFalse(resumed.game_clock.running)

    def test_start_new_soccer_game_ignores_any_recovered_row(self) -> None:
        fresh = start_new_soccer_game()
        self.assertEqual(fresh.state.period, "PRE")
        self.assertEqual(fresh.state.revision, 0)

    def test_soccer_stopped_state_stops_game_and_status_clocks_only(self) -> None:
        from scoreboard.domain.soccer.state import ClockValue, SoccerState

        state = SoccerState(
            game_clock=ClockValue(100.0, True, 2400.0, deadline_monotonic=5.0, started_at_monotonic=1.0),
            status_clock=ClockValue(10.0, True, 1800.0, deadline_monotonic=5.0, started_at_monotonic=1.0),
        )
        stopped = soccer_stopped_state(state)
        self.assertFalse(stopped.game_clock.running)
        self.assertFalse(stopped.status_clock.running)
        self.assertEqual(stopped.revision, state.revision)


class CrossSportIsolationTests(TemporaryDataDirectoryTest):
    """A football database in <root> is never offered to soccer at <root>/soccer, and a soccer
    database in <root>/soccer is never offered to football at <root> (spec section 2.5)."""

    def test_football_database_in_root_not_offered_to_soccer_subfolder(self) -> None:
        football_service = ScoreboardService(monotonic_clock=self.monotonic)
        football_store = GameStore.open(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(football_store.close)
        football_store.begin_session(football_service.state)
        football_store.close()

        # inspect_recovery(root) finds the football game.
        football_report = inspect_recovery(self.paths)
        self.assertTrue(football_report.can_resume)

        # inspect_soccer_recovery(root/soccer) must find nothing: a different root entirely.
        soccer_paths = ScoreboardPaths(self.paths.root / "soccer")
        soccer_paths.ensure()
        soccer_report = inspect_soccer_recovery(soccer_paths)
        self.assertFalse(soccer_report.can_resume)
        self.assertEqual(soccer_report.source, RecoverySource.NONE)

    def test_soccer_database_in_subfolder_not_offered_to_football_root(self) -> None:
        soccer_paths = ScoreboardPaths(self.paths.root / "soccer")
        soccer_paths.ensure()
        soccer_service = SoccerService(monotonic_clock=self.monotonic)
        soccer_store = SoccerGameStore.open(soccer_paths, wall_clock=self.wall_clock)
        self.addCleanup(soccer_store.close)
        soccer_store.begin_session(soccer_service.state)
        soccer_store.close()

        soccer_report = inspect_soccer_recovery(soccer_paths)
        self.assertTrue(soccer_report.can_resume)

        football_report = inspect_recovery(self.paths)
        self.assertFalse(football_report.can_resume)
        self.assertEqual(football_report.source, RecoverySource.NONE)

    def test_both_sports_can_hold_a_game_at_once_without_interfering(self) -> None:
        football_service = ScoreboardService(monotonic_clock=self.monotonic)
        football_store = GameStore.open(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(football_store.close)
        football_store.begin_session(football_service.state)

        soccer_paths = ScoreboardPaths(self.paths.root / "soccer")
        soccer_paths.ensure()
        soccer_service = SoccerService(monotonic_clock=self.monotonic)
        soccer_store = SoccerGameStore.open(soccer_paths, wall_clock=self.wall_clock)
        self.addCleanup(soccer_store.close)
        soccer_cmd = set_score("home", 2)
        soccer_result = soccer_service.submit(soccer_cmd)
        soccer_store.begin_session(soccer_service.state)
        soccer_store.record_command(soccer_cmd, soccer_result)

        football_report = inspect_recovery(self.paths)
        soccer_report = inspect_soccer_recovery(soccer_paths)
        self.assertTrue(football_report.can_resume)
        self.assertTrue(soccer_report.can_resume)
        self.assertEqual(soccer_report.state.home_score, 2)
        self.assertEqual(football_report.state.home_score, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
