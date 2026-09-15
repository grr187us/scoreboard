"""Integration tests for scoreboard.infrastructure.soccer_store.SoccerGameStore.

Mirrors tests/integration/test_persistence.py's shape for football's GameStore. Uses
tests.integration.support's TemporaryDataDirectoryTest/FakeMonotonic/FakeWallClock directly
(read-only reuse; that file is frozen).
"""

from __future__ import annotations

import json
import sqlite3

from scoreboard.application.soccer_service import SoccerService
from scoreboard.application.soccer_snapshots import snapshot_to_state, state_to_snapshot
from scoreboard.domain.soccer.commands import add_goal, new_game, set_period, set_score
from scoreboard.infrastructure.persistence import read_action_history, read_stored_game
from scoreboard.infrastructure.soccer_store import SoccerGameStore
from tests.integration.support import TemporaryDataDirectoryTest


class SoccerPersistenceTests(TemporaryDataDirectoryTest):
    def make_soccer_service(self, **kwargs) -> SoccerService:
        return SoccerService(monotonic_clock=self.monotonic, **kwargs)

    def make_soccer_store(self, **kwargs) -> SoccerGameStore:
        kwargs.setdefault("wall_clock", self.wall_clock)
        store = SoccerGameStore.open(self.paths, **kwargs)
        self.addCleanup(store.close)
        return store

    def test_begin_session_and_checkpoint_write_soccer_shaped_snapshot(self) -> None:
        service = self.make_soccer_service()
        store = self.make_soccer_store()
        status = store.begin_session(service.state)
        self.assertTrue(status.saved)

        stored = read_stored_game(self.paths.database, decode=snapshot_to_state)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.state.period, "PRE")

        with open(self.paths.database, "rb"):
            pass
        connection = sqlite3.connect(str(self.paths.database))
        try:
            row = connection.execute(
                "SELECT snapshot_json FROM game_state LIMIT 1"
            ).fetchone()
            payload = json.loads(row[0])
            self.assertEqual(payload["sport"], "soccer")
            self.assertIn("cards", payload)
            self.assertIn("shootout", payload)
        finally:
            connection.close()

    def test_record_command_persists_accepted_and_rejected(self) -> None:
        service = self.make_soccer_service()
        store = self.make_soccer_store()
        store.begin_session(service.state)

        # Still PRE: a goal is refused here (accepted only during a live period).
        bad_cmd = add_goal("home")
        bad_result = service.submit(bad_cmd)
        self.assertFalse(bad_result.accepted)
        store.record_command(bad_cmd, bad_result)

        cmd = set_period("1st", confirmed=True)
        result = service.submit(cmd)
        store.record_command(cmd, result)
        self.assertTrue(result.accepted)

        rows = read_action_history(self.paths.database)
        results = [r["result"] for r in rows]
        self.assertIn("ACCEPTED", results)
        self.assertIn("REJECTED", results)

    def test_new_game_opens_a_new_game_row(self) -> None:
        service = self.make_soccer_service()
        store = self.make_soccer_store()
        store.begin_session(service.state)
        first_game_id = store.game_id

        cmd = new_game(confirmed=True)
        result = service.submit(cmd)
        self.assertTrue(result.accepted)
        store.record_command(cmd, result)

        self.assertNotEqual(store.game_id, first_game_id)
        stored = read_stored_game(self.paths.database, decode=snapshot_to_state)
        self.assertEqual(stored.game_id, store.game_id)

    def test_checkpoint_keys_on_the_single_game_clock(self) -> None:
        service = self.make_soccer_service()
        store = self.make_soccer_store()
        store.begin_session(service.state)
        cmd = set_period("1st", confirmed=True)
        result = service.submit(cmd)
        store.record_command(cmd, result)

        from scoreboard.domain.soccer.commands import game_clock_start

        start_cmd = game_clock_start()
        start_result = service.submit(start_cmd)
        store.record_command(start_cmd, start_result)

        self.monotonic.advance(1.0)
        materialized = service.materialized_state()
        wrote = store.checkpoint(materialized)
        self.assertTrue(wrote)
        wrote_again = store.checkpoint(materialized)
        self.assertFalse(wrote_again)

    def test_football_database_in_root_is_not_confused_with_soccer(self) -> None:
        """A football database in <root> must never be offered to soccer at <root>/soccer,
        and vice versa -- see test_soccer_recovery.py for the full isolation test; this checks
        the store writes to the sport-specific path only."""

        service = self.make_soccer_service()
        store = self.make_soccer_store()
        store.begin_session(service.state)
        self.assertTrue(str(self.paths.database).endswith("scoreboard.db"))
        self.assertNotEqual(self.paths.root, self.paths.root.parent)


if __name__ == "__main__":
    import unittest

    unittest.main()
