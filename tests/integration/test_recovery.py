"""Task 6 recovery integration tests (P-004, P-005, P-006, R-003).

Recovery is exercised the way a real restart works: write a game, close the
store as a crash or shutdown would, then inspect the files on disk from scratch.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.application.recovery import (
    NEW_GAME_CHOICE,
    RESUME_CHOICE,
    RecoverySource,
    inspect_recovery,
    resume_recovered_game,
    start_new_game,
)
from scoreboard.domain import commands as cmd
from scoreboard.domain.formatting import displayed_second
from scoreboard.domain.state import APP_VERSION
from scoreboard.infrastructure.local_time import format_local_timestamp
from scoreboard.infrastructure.persistence import (
    read_action_history,
    read_stored_game,
    validate_database,
)

from tests.integration.support import TemporaryDataDirectoryTest, corrupt


class RestartRecoveryTests(TemporaryDataDirectoryTest):
    """P-004: restore names, scores, quarter/phase, and stopped clocks."""

    def crash_with_running_clocks(self) -> None:
        """Save a game with both clocks running, then drop the store."""

        service, store = self.started_session()
        self.submit(service, store, cmd.set_team_name("home", "Tigers"))
        self.submit(service, store, cmd.set_team_name("away", "Eagles"))
        self.submit(service, store, cmd.add_score("home", 6))
        self.submit(service, store, cmd.add_score("away", 3))
        self.submit(service, store, cmd.set_quarter("2nd", confirmed=True))
        self.submit(service, store, cmd.play_clock_preset(40.0))
        self.submit(service, store, cmd.game_clock_start())
        self.submit(service, store, cmd.play_clock_start())
        self.monotonic.advance(7.5)
        store.checkpoint(service.materialized_state())
        self.authoritative = service.materialized_state()
        store.close()

    def test_a_restart_restores_the_game_with_every_clock_stopped(self) -> None:
        self.crash_with_running_clocks()

        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.PRIMARY)
        self.assertTrue(report.can_resume)
        self.assertFalse(report.using_backup)
        self.assertEqual(report.state.home_name, "Tigers")
        self.assertEqual(report.state.away_name, "Eagles")
        self.assertEqual(report.state.home_score, 6)
        self.assertEqual(report.state.away_score, 3)
        self.assertEqual(report.state.quarter, "2nd")
        self.assertEqual(report.state.event_phase, "PREGAME")
        self.assertFalse(report.state.game_clock.running)
        self.assertFalse(report.state.play_clock.running)
        self.assertFalse(report.state.event_countdown.running)

    def test_checkpoint_is_also_offered_as_readable_eastern_time(self) -> None:
        """Operator-facing recovery timestamps are shown in Eastern time.

        The database and diagnostics keep the unambiguous UTC ISO string in
        ``checkpoint_at``; ``checkpoint_at_local`` and the human-facing message
        carry the same instant converted for a person reading the screen.
        """

        self.crash_with_running_clocks()

        report = inspect_recovery(self.paths)

        expected_local = format_local_timestamp(report.checkpoint_at)
        self.assertIsNotNone(report.checkpoint_at)
        self.assertEqual(report.checkpoint_at_local, expected_local)
        self.assertNotEqual(report.checkpoint_at_local, report.checkpoint_at)
        self.assertIn(report.checkpoint_at_local, report.message)
        self.assertEqual(report.to_dict()["checkpoint_at_local"], expected_local)

    def test_restored_clocks_hold_the_last_checkpointed_displayed_second(self) -> None:
        self.crash_with_running_clocks()

        report = inspect_recovery(self.paths)

        for name in ("game_clock", "play_clock"):
            with self.subTest(clock=name):
                restored = getattr(report.state, name).seconds
                authoritative = getattr(self.authoritative, name).seconds
                staleness = displayed_second(restored) - displayed_second(authoritative)
                self.assertGreaterEqual(staleness, 0)
                self.assertLessEqual(staleness, 1)

    def test_a_resumed_service_starts_stopped_at_the_recovered_revision(self) -> None:
        self.crash_with_running_clocks()
        report = inspect_recovery(self.paths)

        service = resume_recovered_game(report, monotonic_clock=self.monotonic)

        self.assertEqual(service.revision, report.state.revision)
        self.assertFalse(service.game_clock.running)
        self.assertFalse(service.play_clock.running)
        # Time passing must not restart a recovered clock.
        self.monotonic.advance(30.0)
        self.assertEqual(
            service.materialized_state().game_clock.seconds,
            report.state.game_clock.seconds,
        )

    def test_the_recovered_undo_entry_is_deliberately_not_restored(self) -> None:
        self.crash_with_running_clocks()
        report = inspect_recovery(self.paths)

        service = resume_recovered_game(report, monotonic_clock=self.monotonic)
        result = service.submit(cmd.undo())

        self.assertIsNone(service.undo_entry)
        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, "NOTHING_TO_UNDO")

    def test_the_recovered_play_clock_preset_resets_rather_than_being_restored(self) -> None:
        self.crash_with_running_clocks()
        report = inspect_recovery(self.paths)
        service = resume_recovered_game(report, monotonic_clock=self.monotonic)

        result = service.submit(cmd.play_clock_reset())

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.play_clock.seconds, 0.0)

    def test_resuming_continues_the_same_game_log(self) -> None:
        self.crash_with_running_clocks()
        report = inspect_recovery(self.paths)
        service = resume_recovered_game(report, monotonic_clock=self.monotonic)

        store = self.make_store()
        store.begin_session(service.state, resume_game_id=report.game_id)
        self.submit(service, store, cmd.add_score("home", 1))

        self.assertEqual(store.game_id, report.game_id)
        commands = [
            row["command"] for row in read_action_history(self.paths.database, game_id=report.game_id)
        ]
        self.assertIn("session_resumed", commands)
        self.assertIn("set_team_name", commands)
        self.assertEqual(commands[-1], "add_score")


class ExplicitChoiceTests(TemporaryDataDirectoryTest):
    """P-005: nothing auto-resumes; the operator picks one of two choices."""

    def test_a_recoverable_game_offers_both_choices_and_starts_neither(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        store.close()

        report = inspect_recovery(self.paths)

        self.assertEqual(report.choices, (RESUME_CHOICE, NEW_GAME_CHOICE))
        # The report is a model, not a running game: it exposes no service.
        self.assertFalse(hasattr(report, "service"))

    def test_starting_new_discards_nothing_on_disk(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        store.close()
        report = inspect_recovery(self.paths)

        fresh = start_new_game(monotonic_clock=self.monotonic)

        self.assertEqual(fresh.state.home_score, 0)
        self.assertEqual(fresh.revision, 0)
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 6)
        self.assertIsNotNone(report.game_id)

    def test_an_empty_data_directory_offers_only_a_new_game(self) -> None:
        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.NONE)
        self.assertFalse(report.can_resume)
        self.assertEqual(report.choices, (NEW_GAME_CHOICE,))
        with self.assertRaises(ValueError):
            resume_recovered_game(report)

    def test_the_report_is_json_compatible(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        store.close()

        payload = inspect_recovery(self.paths).to_dict()

        self.assertEqual(json.loads(json.dumps(payload))["source"], "PRIMARY")
        self.assertEqual(payload["snapshot"]["teams"]["home"]["score"], 6)


class CorruptDatabaseTests(TemporaryDataDirectoryTest):
    """P-006: fall back to the backup visibly; never guess."""

    def saved_game(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        self.submit(service, store, cmd.set_quarter("2nd", confirmed=True))
        store.close()

    def test_a_corrupt_primary_loads_the_backup_and_says_so(self) -> None:
        self.saved_game()
        corrupt(self.paths.database)

        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.BACKUP)
        self.assertTrue(report.using_backup)
        self.assertIn("RECOVERED FROM BACKUP", report.message)
        self.assertTrue(report.can_resume)
        self.assertEqual(report.state.home_score, 6)
        self.assertEqual(report.state.quarter, "2nd")
        self.assertIsNotNone(report.primary_error)

    def test_the_corrupt_primary_is_preserved_and_the_backup_is_promoted(self) -> None:
        self.saved_game()
        original = self.paths.database.read_bytes()
        payload = corrupt(self.paths.database)

        report = inspect_recovery(self.paths, stamp="test-stamp")

        preserved = [self.paths.root / name for name in ("scoreboard.invalid-test-stamp.db",)]
        self.assertEqual(report.preserved_paths, (str(preserved[0]),))
        self.assertEqual(preserved[0].read_bytes(), payload)
        self.assertIsNone(validate_database(self.paths.database))
        self.assertNotEqual(self.paths.database.read_bytes(), payload)
        self.assertGreater(len(original), 0)

    def test_a_promoted_backup_can_be_resumed_and_keeps_writing(self) -> None:
        self.saved_game()
        corrupt(self.paths.database)
        report = inspect_recovery(self.paths)

        service = resume_recovered_game(report, monotonic_clock=self.monotonic)
        store = self.make_store(using_backup=True)
        status = store.begin_session(service.state, resume_game_id=report.game_id)
        self.submit(service, store, cmd.add_score("away", 3))

        self.assertTrue(status.saved)
        self.assertTrue(status.using_backup)
        self.assertEqual(read_stored_game(self.paths.database).state.away_score, 3)

    def test_two_corrupt_databases_recover_nothing_and_preserve_both(self) -> None:
        self.saved_game()
        primary_payload = corrupt(self.paths.database, b"primary is not a database")
        backup_payload = corrupt(self.paths.backup, b"backup is not a database either")

        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.UNRECOVERABLE)
        self.assertFalse(report.can_resume)
        self.assertEqual(report.choices, (NEW_GAME_CHOICE,))
        self.assertIn("RECOVERY FAILED", report.message)
        self.assertIsNotNone(report.primary_error)
        self.assertIsNotNone(report.backup_error)
        # Nothing is guessed and nothing is destroyed: both files stay as found.
        self.assertEqual(self.paths.database.read_bytes(), primary_payload)
        self.assertEqual(self.paths.backup.read_bytes(), backup_payload)
        self.assertEqual(
            set(report.preserved_paths),
            {str(self.paths.database), str(self.paths.backup)},
        )

    def test_a_corrupt_primary_with_no_backup_never_invents_a_game(self) -> None:
        self.saved_game()
        self.paths.backup.unlink()
        corrupt(self.paths.database)

        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.UNRECOVERABLE)
        self.assertFalse(report.can_resume)
        self.assertIsNone(report.state)

    def test_an_empty_primary_file_is_treated_as_unreadable(self) -> None:
        self.saved_game()
        self.paths.database.write_bytes(b"")

        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.BACKUP)
        self.assertEqual(report.state.home_score, 6)


class ApplicationUpgradeRecoveryTests(TemporaryDataDirectoryTest):
    """A build change between the interruption and the restart (P-004, W-006).

    Packaging (Task 11) will move the application off ``0.0.0``. A game saved
    by the previous build must still be offered, because the most likely moment
    to install an update is between two launches of a laptop that is mid-season.
    """

    def saved_game_from_another_version(self, written_by: str = "0.9.3") -> None:
        service, store = self.started_session(app_version=written_by)
        self.submit(service, store, cmd.set_team_name("home", "Tigers"))
        self.submit(service, store, cmd.add_score("home", 6))
        self.submit(service, store, cmd.set_quarter("2nd", confirmed=True))
        self.submit(service, store, cmd.game_clock_start())
        self.monotonic.advance(5.0)
        store.checkpoint(service.materialized_state())
        store.close()
        # Rewrite the stored snapshot as the older build would have written it.
        self.restamp_stored_snapshot(written_by)

    def restamp_stored_snapshot(self, app_version: str) -> None:
        import sqlite3

        for path in (self.paths.database, self.paths.backup):
            connection = sqlite3.connect(str(path))
            try:
                for game_id, payload in connection.execute(
                    "SELECT game_id, snapshot_json FROM game_state"
                ).fetchall():
                    snapshot = json.loads(payload)
                    snapshot["app_version"] = app_version
                    connection.execute(
                        "UPDATE game_state SET snapshot_json = ?, app_version = ? "
                        "WHERE game_id = ?",
                        (json.dumps(snapshot), app_version, game_id),
                    )
                connection.commit()
            finally:
                connection.close()

    def test_a_game_saved_by_an_older_build_is_still_offered(self) -> None:
        self.saved_game_from_another_version("0.9.3")

        report = inspect_recovery(self.paths)

        self.assertEqual(report.source, RecoverySource.PRIMARY)
        self.assertTrue(report.can_resume)
        self.assertEqual(report.state.home_name, "Tigers")
        self.assertEqual(report.state.home_score, 6)
        self.assertEqual(report.state.quarter, "2nd")
        self.assertFalse(report.state.game_clock.running)

    def test_the_saving_version_is_reported_rather_than_lost(self) -> None:
        self.saved_game_from_another_version("0.9.3")

        report = inspect_recovery(self.paths)

        self.assertEqual(report.written_by_app_version, "0.9.3")
        self.assertIn("0.9.3", report.message)
        self.assertEqual(report.to_dict()["written_by_app_version"], "0.9.3")

    def test_the_resumed_game_runs_under_the_current_build(self) -> None:
        self.saved_game_from_another_version("0.9.3")
        report = inspect_recovery(self.paths)

        service = resume_recovered_game(report, monotonic_clock=self.monotonic)

        self.assertEqual(service.state.app_version, APP_VERSION)
        self.assertEqual(service.state.home_score, 6)

    def test_a_matching_version_reports_no_upgrade(self) -> None:
        self.saved_game_from_another_version(APP_VERSION)

        report = inspect_recovery(self.paths)

        self.assertIsNone(report.written_by_app_version)
        self.assertNotIn("is being opened by", report.message)


if __name__ == "__main__":
    unittest.main()
