"""Diagnostic-log integration tests (P-008, R-003).

The diagnostic log is the record of what the *program* did. It is bounded and
rotates; the durable action history in SQLite is the record of what happened in
the *game* and is never rotated away.
"""

from __future__ import annotations

import unittest

from scoreboard.domain import commands as cmd
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics

from tests.integration.support import FailingConnection, TemporaryDataDirectoryTest


class DiagnosticEventTests(TemporaryDataDirectoryTest):
    """Every event P-008 names must be recorded."""

    def make_diagnostics(self, **kwargs) -> Diagnostics:
        diagnostics = Diagnostics(self.paths, wall_clock=self.wall_clock, **kwargs)
        self.addCleanup(diagnostics.close)
        return diagnostics

    def log_text(self) -> str:
        return self.paths.log_file.read_text(encoding="utf-8")

    def test_all_required_events_are_recorded(self) -> None:
        diagnostics = self.make_diagnostics()

        diagnostics.startup(app_version="0.0.0")
        diagnostics.recovery(source="BACKUP", message="loaded the backup")
        diagnostics.display_opened(target="Display 2")
        diagnostics.display_closed(reason="operator closed the window")
        diagnostics.command_rejected(
            command="add_score", code="SCORE_ABOVE_MAXIMUM", message="out of range"
        )
        diagnostics.persistence_failure(operation="record_command", error="disk full")
        diagnostics.unhandled_error(context="render", error="boom")
        diagnostics.instance_refused(reason="lock held")
        diagnostics.shutdown(reason="clean")
        diagnostics.flush()

        text = self.log_text()
        for event in (
            "STARTUP",
            "RECOVERY",
            "DISPLAY_OPENED",
            "DISPLAY_CLOSED",
            "COMMAND_REJECTED",
            "PERSISTENCE_FAILURE",
            "UNHANDLED_ERROR",
            "INSTANCE_REFUSED",
            "SHUTDOWN",
        ):
            with self.subTest(event=event):
                self.assertIn(event, text)

    def test_startup_records_the_version_and_the_data_location(self) -> None:
        diagnostics = self.make_diagnostics()

        diagnostics.startup(app_version="0.0.0")
        diagnostics.flush()

        text = self.log_text()
        self.assertIn("app_version=0.0.0", text)
        self.assertIn(str(self.paths.root), text)

    def test_the_log_is_bounded_and_rotates(self) -> None:
        diagnostics = self.make_diagnostics(max_bytes=2_000, backup_count=2)

        for index in range(500):
            diagnostics.note("SOAK", index=index, filler="x" * 80)
        diagnostics.flush()

        log_files = sorted(path.name for path in self.paths.log_directory.iterdir())
        self.assertEqual(
            log_files, ["application.log", "application.log.1", "application.log.2"]
        )
        for path in self.paths.log_directory.iterdir():
            with self.subTest(path=path.name):
                self.assertLessEqual(path.stat().st_size, 4_000)

    def test_a_null_logger_writes_no_file(self) -> None:
        NullDiagnostics().startup(app_version="0.0.0")

        self.assertFalse(self.paths.log_file.exists())


class PersistenceDiagnosticTests(TemporaryDataDirectoryTest):
    """The store reports rejections and write failures through diagnostics."""

    def setUp(self) -> None:
        super().setUp()
        self.diagnostics = Diagnostics(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(self.diagnostics.close)

    def log_text(self) -> str:
        self.diagnostics.flush()
        return self.paths.log_file.read_text(encoding="utf-8")

    def test_a_rejected_command_is_logged_with_its_code(self) -> None:
        service, store = self.started_session(diagnostics=self.diagnostics)

        self.submit(service, store, cmd.correct_score("home", 6))

        text = self.log_text()
        self.assertIn("COMMAND_REJECTED", text)
        self.assertIn("code=SCORE_BELOW_ZERO", text)

    def test_a_write_failure_is_logged_and_its_recovery_is_logged_too(self) -> None:
        service, store = self.started_session(diagnostics=self.diagnostics)
        failing = FailingConnection(store._connection, fail_execute=True)
        store._connection = failing

        command = cmd.add_score("home", 6)
        store.record_command(command, service.submit(command))
        self.assertIn("PERSISTENCE_FAILURE", self.log_text())

        failing.fail_execute = False
        retry = cmd.add_score("away", 3)
        store.record_command(retry, service.submit(retry))

        text = self.log_text()
        self.assertIn("PERSISTENCE_RECOVERED", text)
        self.assertIn("replayed_rows=1", text)

    def test_recovery_source_is_logged_at_startup(self) -> None:
        from scoreboard.application.recovery import inspect_recovery

        service, store = self.started_session(diagnostics=self.diagnostics)
        self.submit(service, store, cmd.add_score("home", 6))
        store.close()

        inspect_recovery(self.paths, diagnostics=self.diagnostics)

        self.assertIn("RECOVERY source=PRIMARY", self.log_text())


if __name__ == "__main__":
    unittest.main()
