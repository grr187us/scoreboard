"""Task 6 persistence integration tests (P-001 through P-009, R-004).

Every case runs in a temporary directory with injected fake clocks: no sleeping,
no real time, and no write outside the temporary directory.
"""

from __future__ import annotations

import os
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from scoreboard.domain import commands as cmd
from scoreboard.domain.formatting import displayed_second
from scoreboard.infrastructure import paths as paths_module
from scoreboard.infrastructure.paths import (
    PathResolutionError,
    ScoreboardPaths,
    resolve_paths,
)
from scoreboard.infrastructure.persistence import (
    BACKUP_MIN_INTERVAL_SECONDS,
    CHECKPOINT_CLOCK_TICK,
    GAME_ACTIVE,
    GAME_ARCHIVED,
    RESULT_ACCEPTED,
    RESULT_REJECTED,
    SESSION_STARTED,
    InstanceAlreadyRunning,
    InstanceLock,
    decode,
    read_action_history,
    read_stored_game,
    validate_database,
)

from tests.integration.support import (
    FailingConnection,
    FakeMonotonic,
    TemporaryDataDirectoryTest,
)


class _AutoAdvancingMonotonic:
    """A monotonic source that advances on its own, every time it is read.

    C4 bounds ``GameStore``'s backup refresh to once every
    :data:`BACKUP_MIN_INTERVAL_SECONDS`, measured against an injected
    monotonic clock. A test that genuinely needs "the backup after this exact
    command" -- rather than after the bounded interval -- injects this instead
    of the real clock, so each read the store takes is already past the
    interval without the test sleeping for real time at all.
    """

    def __init__(self, start: float = 0.0, step: float = BACKUP_MIN_INTERVAL_SECONDS + 0.5) -> None:
        self.value = start
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


class DataLocationTests(TemporaryDataDirectoryTest):
    """P-001, W-005, P-009: runtime data lives outside the repository."""

    def platform_default(self) -> ScoreboardPaths:
        """``resolve_paths()`` with nothing an operator or a shell can add.

        The resolver's documented order is override, then the environment
        variable, then the folder the operator chose through the picker, then
        the platform default. These two tests are about the *platform default*
        alone, so both of the middle layers are removed for the call -- without
        this, the test silently asserted against whatever folder the developer
        had last picked in the real app, and failed on any machine where that
        was not named ``Scoreboard``.
        """

        with mock.patch.dict(os.environ), mock.patch.object(
            paths_module, "read_chosen_root", return_value=None
        ):
            os.environ.pop(paths_module.DATA_DIRECTORY_ENVIRONMENT_VARIABLE, None)
            return resolve_paths()

    def test_the_default_root_is_an_absolute_per_user_location(self) -> None:
        paths = self.platform_default()

        self.assertTrue(paths.root.is_absolute())
        self.assertEqual(paths.root.name, "Scoreboard")
        self.assertEqual(paths.database.name, "scoreboard.db")
        self.assertEqual(paths.backup.name, "scoreboard.backup.db")

    def test_the_default_root_is_not_inside_this_repository(self) -> None:
        repository_root = ScoreboardPaths(Path(__file__).resolve().parents[2]).root
        default = self.platform_default().root

        self.assertNotIn(repository_root, default.parents)
        self.assertNotEqual(repository_root, default)

    def test_a_repository_relative_path_is_refused(self) -> None:
        for candidate in ("data/state", "./scoreboard", "src"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(PathResolutionError):
                    resolve_paths(candidate)

    def test_only_the_expected_runtime_files_are_created(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))

        self.assertEqual(
            sorted(path.name for path in self.paths.root.iterdir()),
            # `cutscenes/` is the operator's pack folder; ensure() makes it like `logs/`.
            ["cutscenes", "logs", "scoreboard.backup.db", "scoreboard.db"],
        )


class TransactionTests(TemporaryDataDirectoryTest):
    """P-002: state and its history row commit together, or not at all."""

    def test_an_accepted_command_commits_state_and_history_together(self) -> None:
        service, store = self.started_session()

        result, status = self.submit(service, store, cmd.add_score("home", 6))

        self.assertTrue(status.saved)
        stored = read_stored_game(self.paths.database)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.state.home_score, 6)
        self.assertEqual(stored.state_revision, result.state.revision)
        history = read_action_history(self.paths.database)
        self.assertEqual(history[-1]["command"], "add_score")
        self.assertEqual(history[-1]["state_revision"], result.state.revision)

    def test_an_interrupted_commit_leaves_the_previous_coherent_state(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        committed = read_stored_game(self.paths.database)
        committed_history = read_action_history(self.paths.database)

        interrupted = FailingConnection(store._connection, fail_commit=True)
        store._connection = interrupted
        lost = cmd.add_score("away", 3)
        result = service.submit(lost)
        status = store.record_command(lost, result)

        self.assertFalse(status.saved)
        self.assertIn("NOT SAVED", status.message)
        # The in-memory game keeps running; only the durable copy fell behind.
        self.assertEqual(service.state.away_score, 3)
        after = read_stored_game(self.paths.database)
        self.assertEqual(after.state.away_score, 0)
        self.assertEqual(after.state.home_score, committed.state.home_score)
        self.assertEqual(after.state_revision, committed.state_revision)
        self.assertEqual(
            len(read_action_history(self.paths.database)), len(committed_history)
        )

    def test_an_interrupted_commit_leaves_a_valid_backup(self) -> None:
        # C4: the backup refresh is bounded to once every
        # BACKUP_MIN_INTERVAL_SECONDS: an auto-advancing monotonic makes each
        # of the two commands below land after the interval, so this test
        # still proves the backup reflects the last *verified* commit, not
        # just the first one of the session.
        service, store = self.started_session(monotonic=_AutoAdvancingMonotonic())
        self.submit(service, store, cmd.add_score("home", 6))

        store._connection = FailingConnection(store._connection, fail_commit=True)
        lost = cmd.add_score("away", 3)
        store.record_command(lost, service.submit(lost))

        self.assertIsNone(validate_database(self.paths.backup))
        self.assertEqual(read_stored_game(self.paths.backup).state.home_score, 6)

    def test_a_write_failure_never_claims_saved_and_retries_next_command(self) -> None:
        service, store = self.started_session()
        real_connection = store._connection
        failing = FailingConnection(real_connection, fail_execute=True)
        store._connection = failing

        blocked = cmd.add_score("home", 6)
        blocked_result = service.submit(blocked)
        blocked_status = store.record_command(blocked, blocked_result)

        self.assertFalse(blocked_status.saved)
        self.assertEqual(blocked_status.label, "NOT SAVED")
        self.assertIn("readonly", blocked_status.last_error)
        self.assertEqual(blocked_status.pending_history_rows, 1)

        # The disk recovers; the very next command saves and replays what was
        # queued, so the audit trail keeps the request that could not be written.
        failing.fail_execute = False
        recovered_status = store.record_command(
            cmd.add_score("away", 3), service.submit(cmd.add_score("away", 3))
        )

        self.assertTrue(recovered_status.saved)
        self.assertEqual(recovered_status.label, "SAVED")
        self.assertEqual(recovered_status.pending_history_rows, 0)
        commands = [row["command"] for row in read_action_history(self.paths.database)]
        self.assertEqual(commands.count("add_score"), 2)
        stored = read_stored_game(self.paths.database)
        self.assertEqual(stored.state.home_score, 6)
        self.assertEqual(stored.state.away_score, 3)


class BoundedBackupTests(TemporaryDataDirectoryTest):
    """C4: a full backup copy on every accepted command is bounded, not free.

    The policy stays "refresh after a verified commit, never from a
    half-written file" -- only the cadence changed: a refresh within
    :data:`BACKUP_MIN_INTERVAL_SECONDS` of the last one is deferred rather
    than skipped, and a later eligible checkpoint (or the store closing)
    flushes it.
    """

    def test_the_backup_is_not_rewritten_on_every_command_inside_the_interval(self) -> None:
        monotonic = FakeMonotonic(1000.0)
        service, store = self.started_session(monotonic=monotonic)
        first_backup_mtime = self.paths.backup.stat().st_mtime_ns
        first_backup_home_score = read_stored_game(self.paths.backup).state.home_score

        # Two commands land well inside the bounded interval: the backup must
        # not move at all, even though the primary database did.
        self.submit(service, store, cmd.add_score("home", 6))
        monotonic.advance(0.5)
        self.submit(service, store, cmd.add_score("away", 3))

        self.assertEqual(self.paths.backup.stat().st_mtime_ns, first_backup_mtime)
        self.assertEqual(
            read_stored_game(self.paths.backup).state.home_score, first_backup_home_score
        )
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 6)
        self.assertTrue(store._backup_pending)

    def test_a_later_checkpoint_flushes_the_deferred_backup_once_the_interval_elapses(self) -> None:
        monotonic = FakeMonotonic(2000.0)
        service, store = self.started_session(monotonic=monotonic)
        self.submit(service, store, cmd.add_score("home", 6))  # deferred: still inside the interval
        self.assertTrue(store._backup_pending)
        self.assertEqual(read_stored_game(self.paths.backup).state.home_score, 0)

        monotonic.advance(BACKUP_MIN_INTERVAL_SECONDS + 0.1)
        wrote = store.checkpoint(service.materialized_state())

        self.assertFalse(store._backup_pending)
        self.assertEqual(read_stored_game(self.paths.backup).state.home_score, 6)
        # The clock was never started, so there was nothing new to checkpoint
        # in the primary database -- only the deferred backup was due.
        self.assertFalse(wrote)

    def test_closing_the_store_flushes_a_still_deferred_backup(self) -> None:
        monotonic = FakeMonotonic(3000.0)
        service, store = self.started_session(monotonic=monotonic)
        self.submit(service, store, cmd.add_score("home", 6))
        self.assertTrue(store._backup_pending)

        store.close()

        self.assertEqual(read_stored_game(self.paths.backup).state.home_score, 6)


class ActionHistoryTests(TemporaryDataDirectoryTest):
    """P-007: append-only history retains accepted and rejected requests."""

    def test_required_fields_are_present_for_an_accepted_command(self) -> None:
        service, store = self.started_session()

        result, _ = self.submit(service, store, cmd.add_score("home", 6))
        row = read_action_history(self.paths.database)[-1]

        self.assertEqual(row["result"], RESULT_ACCEPTED)
        self.assertEqual(row["command"], "add_score")
        self.assertEqual(row["source"], "operator")
        self.assertEqual(row["team"], "home")
        self.assertEqual(row["field"], "home_score")
        self.assertEqual(decode(row["old_value"]), 0)
        self.assertEqual(decode(row["new_value"]), 6)
        self.assertEqual(row["state_revision"], result.state.revision)
        self.assertEqual(row["app_version"], service.state.app_version)
        self.assertTrue(row["wall_clock"].startswith("2026-09-04T"))
        self.assertIsNone(row["error_code"])

    def test_a_rejected_request_is_retained_with_its_code_and_message(self) -> None:
        service, store = self.started_session()
        revision_before = service.revision

        rejected = cmd.correct_score("home", 6)
        result, status = self.submit(service, store, rejected)
        row = read_action_history(self.paths.database)[-1]

        self.assertFalse(result.accepted)
        self.assertTrue(status.saved)
        self.assertEqual(row["result"], RESULT_REJECTED)
        self.assertEqual(row["command"], "correct_score")
        self.assertEqual(row["error_code"], "SCORE_BELOW_ZERO")
        self.assertIn("cannot be corrected below 0", row["error_message"])
        # Nothing changed, so there is no new value: the request is recorded.
        self.assertIsNone(row["old_value"])
        self.assertEqual(decode(row["new_value"])["points"], 6)
        self.assertEqual(row["state_revision"], revision_before)
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 0)

    def test_a_confirmation_prompt_is_recorded_as_a_rejected_request(self) -> None:
        service, store = self.started_session()

        result, _ = self.submit(service, store, cmd.new_game())
        row = read_action_history(self.paths.database)[-1]

        self.assertTrue(result.confirmation_required)
        self.assertEqual(row["result"], RESULT_REJECTED)
        self.assertEqual(row["error_code"], "CONFIRMATION_REQUIRED")

    def test_sequence_is_monotonic_and_matches_submission_order(self) -> None:
        service, store = self.started_session()
        submitted = [
            cmd.add_score("home", 6),
            cmd.add_score("home", 99),  # rejected shape
            cmd.add_score("away", 3),
            cmd.quarter_forward(),
            cmd.undo(),
        ]
        for command in submitted:
            self.submit(service, store, command)

        rows = read_action_history(self.paths.database)
        sequences = [row["sequence"] for row in rows]

        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(len(set(sequences)), len(sequences))
        self.assertEqual(
            [row["command"] for row in rows],
            [SESSION_STARTED] + [command.type.value for command in submitted],
        )

    def test_history_is_append_only_across_an_undo(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        before = len(read_action_history(self.paths.database))

        self.submit(service, store, cmd.undo())
        rows = read_action_history(self.paths.database)

        self.assertEqual(len(rows), before + 1)
        self.assertEqual(rows[-1]["command"], "undo")
        self.assertEqual(decode(rows[-1]["old_value"]), 6)
        self.assertEqual(decode(rows[-1]["new_value"]), 0)

    def test_undoing_a_compound_field_records_a_structured_value_not_a_repr(self) -> None:
        """``ball_on`` is a compound ``BallSpot`` field; Undo's generic old/new
        reporting must serialize it the same structured way its own direct
        command does, not as a Python object string (P-007)."""

        service, store = self.started_session()
        self.submit(service, store, cmd.set_ball_on("home", 40))
        self.submit(service, store, cmd.set_ball_on("away", 22))

        self.submit(service, store, cmd.undo())
        row = read_action_history(self.paths.database)[-1]

        self.assertEqual(row["command"], "undo")
        self.assertEqual(decode(row["old_value"]), {"team": "away", "yard_line": 22})
        self.assertEqual(decode(row["new_value"]), {"team": "home", "yard_line": 40})


class GameIdentityTests(TemporaryDataDirectoryTest):
    """F-023: New Game archives the current game's log and opens a new one."""

    def test_new_game_archives_the_previous_log_and_starts_another(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        first_game_id = store.game_id

        self.submit(service, store, cmd.new_game(confirmed=True))
        second_game_id = store.game_id

        self.assertNotEqual(first_game_id, second_game_id)
        connection = sqlite3.connect(str(self.paths.database))
        try:
            connection.row_factory = sqlite3.Row
            games = {
                row["game_id"]: dict(row)
                for row in connection.execute("SELECT * FROM games").fetchall()
            }
        finally:
            # sqlite3's context manager ends the transaction but does not close
            # the file, and Windows will not remove a temporary directory that
            # still holds an open handle.
            connection.close()
        self.assertEqual(games[first_game_id]["status"], GAME_ARCHIVED)
        self.assertIsNotNone(games[first_game_id]["closed_at"])
        self.assertEqual(games[second_game_id]["status"], GAME_ACTIVE)

    def test_the_new_game_command_closes_the_log_it_ends(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        first_game_id = store.game_id

        self.submit(service, store, cmd.new_game(confirmed=True))

        archived = [row["command"] for row in read_action_history(self.paths.database, game_id=first_game_id)]
        fresh = [row["command"] for row in read_action_history(self.paths.database, game_id=store.game_id)]

        self.assertEqual(archived[-1], "new_game")
        self.assertIn("add_score", archived)
        self.assertEqual(fresh, [SESSION_STARTED])

    def test_recovery_targets_the_new_game_not_the_archived_one(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        self.submit(service, store, cmd.new_game(confirmed=True))

        stored = read_stored_game(self.paths.database)

        self.assertEqual(stored.game_id, store.game_id)
        self.assertEqual(stored.state.home_score, 0)


class RunningClockCheckpointTests(TemporaryDataDirectoryTest):
    """P-003, P-004: checkpoint once per displayed second, with no tick spam."""

    def test_a_running_clock_checkpoints_within_one_displayed_second(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.game_clock_start())
        history_before = len(read_action_history(self.paths.database))

        for _ in range(40):  # ten simulated seconds at a four-per-second refresh
            self.monotonic.advance(0.25)
            store.checkpoint(service.materialized_state())

            authoritative = service.materialized_state().game_clock.seconds
            persisted = read_stored_game(self.paths.database).state.game_clock.seconds
            staleness = displayed_second(persisted) - displayed_second(authoritative)
            self.assertGreaterEqual(staleness, 0)
            self.assertLessEqual(
                staleness,
                1,
                f"checkpoint was {staleness} displayed seconds stale",
            )

        self.assertEqual(
            len(read_action_history(self.paths.database)),
            history_before,
            "clock ticks must not be written to the action history",
        )

    def test_a_checkpoint_is_written_once_per_displayed_second_not_per_call(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.game_clock_start())

        writes = 0
        for _ in range(20):  # five simulated seconds at a four-per-second refresh
            self.monotonic.advance(0.25)
            writes += 1 if store.checkpoint(service.materialized_state()) else 0

        self.assertEqual(writes, 5)
        self.assertEqual(
            read_stored_game(self.paths.database).checkpoint_kind, CHECKPOINT_CLOCK_TICK
        )

    def test_a_stopped_clock_writes_no_checkpoints_at_all(self) -> None:
        service, store = self.started_session()

        writes = 0
        for _ in range(20):
            self.monotonic.advance(0.25)
            writes += 1 if store.checkpoint(service.materialized_state()) else 0

        self.assertEqual(writes, 0)

    def test_a_command_resets_the_cadence_so_the_next_tick_is_measured_from_it(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.game_clock_start())
        self.monotonic.advance(2.5)
        store.checkpoint(service.materialized_state())

        self.submit(service, store, cmd.add_score("home", 6))
        immediately_after = store.checkpoint(service.materialized_state())

        self.assertFalse(immediately_after)
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 6)


class ShutdownTests(TemporaryDataDirectoryTest):
    """P-003: a clean shutdown saves, and says so."""

    def test_clean_shutdown_saves_the_final_state(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        self.submit(service, store, cmd.game_clock_start())
        self.monotonic.advance(12.5)

        status = store.record_shutdown(service.materialized_state())

        self.assertTrue(status.saved)
        stored = read_stored_game(self.paths.database)
        self.assertEqual(stored.checkpoint_kind, "SHUTDOWN")
        self.assertAlmostEqual(stored.state.game_clock.seconds, 1800.0 - 12.5, places=6)
        self.assertEqual(read_action_history(self.paths.database)[-1]["command"], "session_shutdown")


class SecondInstanceTests(TemporaryDataDirectoryTest):
    """R-004: refuse a second authoritative instance, without corruption."""

    def test_a_second_instance_is_refused_with_a_clear_message(self) -> None:
        first = InstanceLock(self.paths.lock).acquire()
        self.addCleanup(first.release)

        with self.assertRaises(InstanceAlreadyRunning) as raised:
            InstanceLock(self.paths.lock).acquire()

        message = str(raised.exception)
        self.assertIn("already using this data folder", message)
        self.assertIn(str(self.paths.root), message)

    def test_the_refused_instance_leaves_the_database_intact(self) -> None:
        service, store = self.started_session()
        self.submit(service, store, cmd.add_score("home", 6))
        lock = InstanceLock(self.paths.lock).acquire()
        self.addCleanup(lock.release)

        with self.assertRaises(InstanceAlreadyRunning):
            InstanceLock(self.paths.lock).acquire()

        self.assertIsNone(validate_database(self.paths.database))
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 6)

    def test_the_lock_is_available_again_after_release(self) -> None:
        first = InstanceLock(self.paths.lock).acquire()
        first.release()

        second = InstanceLock(self.paths.lock).acquire()
        self.addCleanup(second.release)

        self.assertTrue(second.held)


class StoreGuardTests(TemporaryDataDirectoryTest):
    """Programmer errors raise; operator-visible failures return a status."""

    def test_recording_before_a_session_is_a_programmer_error(self) -> None:
        service = self.make_service()
        store = self.make_store()
        command = cmd.add_score("home", 6)

        with self.assertRaises(Exception) as raised:
            store.record_command(command, service.submit(command))

        self.assertIn("begin_session", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
