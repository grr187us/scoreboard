"""Shared fixtures for the temporary-directory integration tests.

The two fake clocks are deliberately separate objects, mirroring the production
split: the service and its engines advance on the monotonic source, and only
persistence and logging read the wall clock.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scoreboard.application.service import ScoreboardService
from scoreboard.infrastructure.paths import ScoreboardPaths, resolve_paths
from scoreboard.infrastructure.persistence import GameStore


class FakeMonotonic:
    """A monotonic source advanced only by the test."""

    def __init__(self, value: float = 1000.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class FakeWallClock:
    """A wall clock that ticks one second per reading, for stable timestamps."""

    def __init__(self, start: datetime | None = None, step_seconds: float = 1.0) -> None:
        self.value = start or datetime(2026, 9, 4, 19, 30, tzinfo=timezone.utc)
        self.step = timedelta(seconds=step_seconds)
        self.readings = 0

    def __call__(self) -> datetime:
        self.readings += 1
        current = self.value
        self.value += self.step
        return current


class FailingConnection:
    """A connection proxy that fails on demand, to simulate a bad disk.

    It delegates everything to the real connection, so a test can fail exactly
    one operation and then verify that the database is still coherent.
    """

    def __init__(
        self,
        real: sqlite3.Connection,
        *,
        fail_execute: bool = False,
        fail_commit: bool = False,
        error: str = "attempt to write a readonly database",
    ) -> None:
        self._real = real
        self.fail_execute = fail_execute
        self.fail_commit = fail_commit
        self.error = error

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        if self.fail_execute:
            raise sqlite3.OperationalError(self.error)
        return self._real.execute(*args, **kwargs)

    def commit(self) -> Any:
        if self.fail_commit:
            raise sqlite3.OperationalError(self.error)
        return self._real.commit()

    def rollback(self) -> Any:
        return self._real.rollback()

    def backup(self, *args: Any, **kwargs: Any) -> Any:
        return self._real.backup(*args, **kwargs)

    def close(self) -> Any:
        return self._real.close()


def corrupt(path: Path, payload: bytes = b"this is not a SQLite database at all") -> bytes:
    """Overwrite a database file with bytes SQLite cannot read."""

    path.write_bytes(payload)
    return payload


class TemporaryDataDirectoryTest(unittest.TestCase):
    """Base case giving each test its own runtime data directory."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="scoreboard-test-")
        self.addCleanup(directory.cleanup)
        self.temporary_root = Path(directory.name)
        self.paths: ScoreboardPaths = resolve_paths(self.temporary_root / "Scoreboard")
        self.paths.ensure()
        self.monotonic = FakeMonotonic()
        self.wall_clock = FakeWallClock()

    def make_service(self, **kwargs: Any) -> ScoreboardService:
        return ScoreboardService(monotonic_clock=self.monotonic, **kwargs)

    def make_store(self, **kwargs: Any) -> GameStore:
        kwargs.setdefault("wall_clock", self.wall_clock)
        store = GameStore.open(self.paths, **kwargs)
        # Windows keeps an open database file locked, so every store must be
        # closed before the temporary directory is removed.
        self.addCleanup(store.close)
        return store

    def started_session(self, **kwargs: Any) -> tuple[ScoreboardService, GameStore]:
        service = self.make_service()
        store = self.make_store(**kwargs)
        status = store.begin_session(service.state)
        self.assertTrue(status.saved, status.message)
        return service, store

    def submit(self, service: ScoreboardService, store: GameStore, command: Any) -> Any:
        """Do exactly what the bridge does: submit, then persist the result."""

        result = service.submit(command)
        status = store.record_command(command, result)
        return result, status
