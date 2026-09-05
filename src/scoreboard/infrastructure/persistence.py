"""Embedded SQLite persistence, backup, and the durable action history.

One database file plus one automatically refreshed last-known-good backup live
under the per-user application-data directory (P-001). There is no database
server, no cloud sync, and no registry storage.

Responsibilities
----------------

This module *observes and durably records* transitions. It never produces one:
only :class:`~scoreboard.application.service.ScoreboardService` advances the
authoritative revision, and this module writes down what the service decided.

Every accepted command writes the recoverable state and its action-history row
inside a single transaction, so a crash can never leave a state that no history
row explains, or a history row describing a state that was never stored
(P-002). Rejected operator requests are recorded too, built from the submitted
:class:`~scoreboard.domain.commands.Command` plus the error code and message,
because ``CommandResult.event`` is ``None`` on rejection by design (P-007).

While a clock runs, :meth:`GameStore.checkpoint` writes the materialized
remaining value whenever the *displayed* second changes, using
:mod:`scoreboard.domain.formatting`. Those checkpoints update recoverable state
only; they add no rows to the action history, so a running clock cannot flood
the audit trail (P-003, F-037, F-046).

Timestamps
----------

Wall-clock time is injected separately and is used only for human-readable
history and log timestamps. This module never reads the service's monotonic
clock, and the domain never gains a wall-clock dependency (ARCHITECTURE.md §7).

Carry-over decisions recorded here
----------------------------------

* **The in-memory one-level undo entry is not restored after recovery.** It is
  deliberately absent from the persisted state. After an interruption the
  operator is required to verify the board against the real game before
  resuming (P-005); offering "Undo" for a command they cannot see, issued
  before a crash they may not have witnessed, would invite a second error
  rather than fix the first. The action history still records the command, so
  nothing is lost from the audit trail -- only the one-click reversal is.
* **``PlayClock.preset_seconds`` is not persisted and resets to blank.** It is
  engine-only bookkeeping and is absent from the persisted ``ClockValue``
  contract. A recovered play clock therefore restores its remaining value with
  no remembered preset, so a subsequent Reset blanks it rather than restoring a
  25 or 40 the operator never re-selected. Reloading a preset is one click on
  an always-visible control (F-041).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Final, Iterator, Sequence

from scoreboard.application.snapshots import snapshot_to_state, state_to_snapshot
from scoreboard.domain.commands import Command, CommandResult, CommandType
from scoreboard.domain.formatting import displayed_second
from scoreboard.domain.state import (
    APP_VERSION,
    ClockValue,
    GameState,
    StateValidationError,
)
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics, utc_now
from scoreboard.infrastructure.paths import ScoreboardPaths

#: Bumped only when the stored table shapes change incompatibly.
DATABASE_SCHEMA_VERSION: Final[int] = 1

#: Values stored in ``games.status``.
GAME_ACTIVE: Final[str] = "ACTIVE"
GAME_ARCHIVED: Final[str] = "ARCHIVED"

#: Values stored in ``game_state.checkpoint_kind``.
CHECKPOINT_SESSION_START: Final[str] = "SESSION_START"
CHECKPOINT_RECOVERED: Final[str] = "RECOVERED"
CHECKPOINT_COMMAND: Final[str] = "COMMAND"
CHECKPOINT_CLOCK_TICK: Final[str] = "CLOCK_TICK"
CHECKPOINT_SHUTDOWN: Final[str] = "SHUTDOWN"

#: Values stored in ``action_history.result``.
RESULT_ACCEPTED: Final[str] = "ACCEPTED"
RESULT_REJECTED: Final[str] = "REJECTED"

#: Source recorded for rows the application writes about itself.
SYSTEM_SOURCE: Final[str] = "system"

#: History entries for session lifecycle, distinguishable from operator commands.
SESSION_STARTED: Final[str] = "session_started"
SESSION_RESUMED: Final[str] = "session_resumed"
SESSION_SHUTDOWN: Final[str] = "session_shutdown"

#: A clock that counted down to zero on its own. It is not an operator command
#: -- nobody pressed anything -- but F-037 and F-046 require expiration in the
#: durable history alongside starts, stops, presets, and corrections. The
#: ``system`` source keeps it distinguishable from anything an operator did.
CLOCK_EXPIRED: Final[dict[str, str]] = {
    "game": "game_clock_expired",
    "play": "play_clock_expired",
    "event": "event_countdown_expired",
}

#: The game clock expired naturally while a play clock was running.  The paired
#: system row records why the play clock disappeared instead of falsely calling
#: it a play-clock expiration.
PLAY_CLOCK_CLEARED_ON_GAME_CLOCK_STOP: Final[str] = "play_clock_cleared_on_game_clock_stop"

#: A failed write keeps its history rows in memory and retries them on the next
#: successful transaction. The cap stops an all-session outage from growing
#: without bound; it is far larger than a game's realistic command count.
MAX_PENDING_HISTORY_ROWS: Final[int] = 2000

_SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        closed_at TEXT,
        status TEXT NOT NULL,
        app_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_state (
        game_id INTEGER PRIMARY KEY REFERENCES games(game_id),
        state_revision INTEGER NOT NULL,
        snapshot_json TEXT NOT NULL,
        checkpoint_at TEXT NOT NULL,
        checkpoint_kind TEXT NOT NULL,
        app_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_history (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL REFERENCES games(game_id),
        wall_clock TEXT NOT NULL,
        command TEXT NOT NULL,
        source TEXT NOT NULL,
        team TEXT,
        field TEXT,
        old_value TEXT,
        new_value TEXT,
        result TEXT NOT NULL,
        error_code TEXT,
        error_message TEXT,
        state_revision INTEGER NOT NULL,
        app_version TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS action_history_game ON action_history(game_id, sequence)",
)


class PersistenceError(RuntimeError):
    """Base class for persistence problems the operator may need to see."""


class DatabaseInvalid(PersistenceError):
    """A database file exists but cannot be trusted as a recovery source."""


class InstanceAlreadyRunning(PersistenceError):
    """A second authoritative instance tried to claim the same data directory."""


class NoActiveGame(PersistenceError):
    """A write was attempted before a session was opened. A programmer error."""


# --- Status ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersistenceStatus:
    """What the operator's health strip must say about saving (U-005).

    ``saved`` is only ever true when a commit actually succeeded. A failed
    write leaves it false with a visible message, and the application keeps
    operating from memory until the next command retries (ARCHITECTURE.md §11).
    """

    saved: bool
    message: str
    revision: int | None = None
    checkpoint_at: str | None = None
    using_backup: bool = False
    last_error: str | None = None
    pending_history_rows: int = 0

    @property
    def label(self) -> str:
        """The short text the health strip shows: never ``SAVED`` when it is not."""

        return "SAVED" if self.saved else "NOT SAVED"

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible payload; no domain object crosses this boundary."""

        return {
            "saved": self.saved,
            "label": self.label,
            "message": self.message,
            "revision": self.revision,
            "checkpoint_at": self.checkpoint_at,
            "using_backup": self.using_backup,
            "last_error": self.last_error,
            "pending_history_rows": self.pending_history_rows,
        }


@dataclass(frozen=True, slots=True)
class StoredGame:
    """One game's recoverable state as it was last committed."""

    game_id: int
    state: GameState
    state_revision: int
    checkpoint_at: str
    checkpoint_kind: str
    app_version: str


# --- Single-instance lock ---------------------------------------------------


class InstanceLock:
    """An operating-system lock on the data directory (R-004).

    The lock is an exclusive byte range in a small file. Windows and POSIX both
    release such a lock when the owning process exits, so a crashed instance
    never leaves a stale lock that blocks the next launch -- which matters far
    more here than elegance, because the alternative is an operator who cannot
    restart the scoreboard during a game.

    Refusing the second instance protects the database: two writers on one
    SQLite file is exactly how a game gets corrupted.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._handle: Any = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> "InstanceLock":
        if self._handle is not None:
            return self
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._path, "a+b")
        try:
            self._lock_handle(handle)
        except OSError as exc:
            handle.close()
            raise InstanceAlreadyRunning(
                "Another Scoreboard instance is already using this data folder "
                f"({self._path.parent}). Switch to the running window, or close it "
                "before starting a second copy."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            self._unlock_handle(handle)
        except OSError:
            # The lock is released with the handle in every case that matters;
            # a failure to unlock explicitly must not mask a real shutdown.
            pass
        finally:
            handle.close()

    def __enter__(self) -> "InstanceLock":
        return self.acquire()

    def __exit__(self, *_exc_info: object) -> None:
        self.release()

    @staticmethod
    def _lock_handle(handle: Any) -> None:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_handle(handle: Any) -> None:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# --- Connection helpers -----------------------------------------------------


def connect(path: Path) -> sqlite3.Connection:
    """Open one database with durable, explicitly controlled transactions."""

    # The webview host creates the store before starting its refresh worker.
    # ScoreboardApplication's command lock serializes every store operation, so
    # allow that one connection to cross the startup/refresh thread boundary.
    connection = sqlite3.connect(
        str(path), isolation_level=None, check_same_thread=False
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # Full synchronisation is the point of this module: a game-day power loss
    # must not cost a committed score.
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def apply_schema(connection: sqlite3.Connection, *, app_version: str = APP_VERSION) -> None:
    """Create the tables and record the schema/app version once."""

    for statement in _SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
        ("schema_version", str(DATABASE_SCHEMA_VERSION)),
    )
    connection.execute(
        "INSERT INTO meta(key, value) VALUES('app_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (app_version,),
    )


def validate_database(path: Path) -> str | None:
    """Return ``None`` when the file is a usable database, else why it is not.

    A missing file is *not* invalid: it simply has nothing to recover, and the
    caller distinguishes the two.
    """

    path = Path(path)
    if not path.exists():
        return "no database file"
    if path.stat().st_size == 0:
        return "database file is empty"
    connection = None
    try:
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            return f"integrity check failed: {None if integrity is None else integrity[0]}"
        row = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return "database has no schema version"
        if int(row["value"]) != DATABASE_SCHEMA_VERSION:
            return (
                f"database schema version {row['value']} is not the supported "
                f"version {DATABASE_SCHEMA_VERSION}"
            )
    except (sqlite3.Error, ValueError, OSError) as exc:
        return f"database could not be read: {exc}"
    finally:
        if connection is not None:
            connection.close()
    return None


def read_stored_game(path: Path) -> StoredGame | None:
    """Read the active game's committed state, or ``None`` when there is none."""

    reason = validate_database(path)
    if reason is not None:
        raise DatabaseInvalid(reason)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT g.game_id, s.state_revision, s.snapshot_json,
                   s.checkpoint_at, s.checkpoint_kind, s.app_version
            FROM games AS g
            JOIN game_state AS s ON s.game_id = g.game_id
            WHERE g.status = ?
            ORDER BY g.game_id DESC
            LIMIT 1
            """,
            (GAME_ACTIVE,),
        ).fetchone()
        if row is None:
            return None
        try:
            state = snapshot_to_state(json.loads(row["snapshot_json"]))
        except (json.JSONDecodeError, StateValidationError) as exc:
            raise DatabaseInvalid(f"stored snapshot is not usable: {exc}") from exc
        return StoredGame(
            game_id=int(row["game_id"]),
            state=state,
            state_revision=int(row["state_revision"]),
            checkpoint_at=str(row["checkpoint_at"]),
            checkpoint_kind=str(row["checkpoint_kind"]),
            app_version=str(row["app_version"]),
        )
    finally:
        connection.close()


def read_action_history(path: Path, *, game_id: int | None = None) -> list[dict[str, Any]]:
    """Read the append-only history in committed order, for audit and tests."""

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        if game_id is None:
            rows = connection.execute(
                "SELECT * FROM action_history ORDER BY sequence"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM action_history WHERE game_id = ? ORDER BY sequence",
                (game_id,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def promote_backup(paths: ScoreboardPaths, *, stamp: str) -> Path:
    """Preserve an unusable primary database and put the backup in its place.

    The invalid file is renamed, never deleted: P-006 requires that both files
    survive so the game can be reconstructed by hand if it must be.
    """

    quarantined = paths.quarantine(paths.database, stamp)
    if paths.database.exists():
        paths.database.replace(quarantined)
    shutil.copyfile(paths.backup, paths.database)
    return quarantined


def stopped_clock(value: ClockValue) -> ClockValue:
    """Return the same materialized value with the clock stopped and unanchored."""

    return ClockValue(
        seconds=value.seconds,
        running=False,
        maximum_seconds=value.maximum_seconds,
        deadline_monotonic=None,
        started_at_monotonic=None,
    )


def stopped_state(state: GameState) -> GameState:
    """Every clock stopped at its persisted value, with the revision unchanged.

    ``dataclasses.replace`` is used rather than ``GameState.evolve`` on purpose:
    restoring a saved game is not a new transition, so it must not invent a
    revision the service never issued (P-004).
    """

    return replace(
        state,
        game_clock=stopped_clock(state.game_clock),
        play_clock=stopped_clock(state.play_clock),
        event_countdown=stopped_clock(state.event_countdown),
    )


# --- The store --------------------------------------------------------------


class GameStore:
    """Owns the database, its backup, and the durable action history."""

    def __init__(
        self,
        paths: ScoreboardPaths,
        connection: sqlite3.Connection,
        *,
        wall_clock: Callable[[], datetime] | None = None,
        diagnostics: Diagnostics | None = None,
        app_version: str = APP_VERSION,
        using_backup: bool = False,
    ) -> None:
        self._paths = paths
        self._connection = connection
        self._wall_clock = utc_now if wall_clock is None else wall_clock
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        self._app_version = app_version
        self._using_backup = using_backup
        self._game_id: int | None = None
        self._pending_history: list[tuple[Any, ...]] = []
        self._last_displayed: tuple[int, int, int] | None = None
        self._status = PersistenceStatus(
            saved=False,
            message="No game has been saved yet.",
            using_backup=using_backup,
        )

    @classmethod
    def open(
        cls,
        paths: ScoreboardPaths,
        *,
        wall_clock: Callable[[], datetime] | None = None,
        diagnostics: Diagnostics | None = None,
        app_version: str = APP_VERSION,
        using_backup: bool = False,
    ) -> "GameStore":
        paths.ensure()
        connection = connect(paths.database)
        apply_schema(connection, app_version=app_version)
        return cls(
            paths,
            connection,
            wall_clock=wall_clock,
            diagnostics=diagnostics,
            app_version=app_version,
            using_backup=using_backup,
        )

    # --- Accessors ----------------------------------------------------------

    @property
    def status(self) -> PersistenceStatus:
        return self._status

    @property
    def game_id(self) -> int | None:
        return self._game_id

    @property
    def paths(self) -> ScoreboardPaths:
        return self._paths

    def close(self) -> None:
        try:
            self._connection.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "GameStore":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # --- Session lifecycle --------------------------------------------------

    def begin_session(
        self, state: GameState, *, resume_game_id: int | None = None
    ) -> PersistenceStatus:
        """Adopt a recovered game, or archive the previous one and open a new one.

        Resuming keeps the recovered ``game_id`` so the game's log continues
        uninterrupted. Starting fresh closes the previous game's log and opens a
        new one, which is the same identity boundary ``New Game`` uses (F-023).
        """

        timestamp = self._timestamp()
        previous_game_id = self._game_id
        try:
            with self._transaction() as connection:
                if resume_game_id is not None:
                    row = connection.execute(
                        "SELECT game_id FROM games WHERE game_id = ?", (resume_game_id,)
                    ).fetchone()
                    if row is None:
                        raise NoActiveGame(
                            f"cannot resume game {resume_game_id}: it is not in this database"
                        )
                    self._game_id = int(row["game_id"])
                    self._write_state(connection, state, timestamp, CHECKPOINT_RECOVERED)
                    self._insert_history(
                        connection,
                        self._system_row(SESSION_RESUMED, state, timestamp),
                    )
                else:
                    self._game_id = self._open_game(connection, timestamp)
                    self._write_state(
                        connection, state, timestamp, CHECKPOINT_SESSION_START
                    )
                    self._insert_history(
                        connection,
                        self._system_row(SESSION_STARTED, state, timestamp),
                    )
        except (sqlite3.Error, OSError) as exc:
            # The transaction rolled back, so the identifier it allocated no
            # longer exists. In-memory bookkeeping must roll back with it.
            self._game_id = previous_game_id
            return self._fail("begin_session", exc)
        self._reset_display_cadence(state)
        self._refresh_backup()
        return self._succeed(state, timestamp, "Game state saved.")

    def record_shutdown(self, state: GameState) -> PersistenceStatus:
        """Save at clean shutdown (P-003) and record it in the history."""

        if self._game_id is None:
            return self._status
        timestamp = self._timestamp()
        try:
            with self._transaction() as connection:
                self._flush_pending(connection)
                self._write_state(connection, state, timestamp, CHECKPOINT_SHUTDOWN)
                self._insert_history(
                    connection, self._system_row(SESSION_SHUTDOWN, state, timestamp)
                )
        except (sqlite3.Error, OSError) as exc:
            return self._fail("record_shutdown", exc)
        self._refresh_backup()
        return self._succeed(state, timestamp, "Game state saved at shutdown.")

    # --- Command recording --------------------------------------------------

    def record_command(self, command: Command, result: CommandResult) -> PersistenceStatus:
        """Durably record one submitted command and, if accepted, its new state.

        Accepted: the recoverable state and the history row commit together, in
        one transaction (P-002). Rejected: only the history row is written, from
        the submitted command plus the error, and the stored state is untouched
        because nothing changed (P-007, U-007).
        """

        if self._game_id is None:
            raise NoActiveGame("begin_session() must be called before recording commands")

        timestamp = self._timestamp()
        state: GameState = result.state
        previous_game_id = self._game_id
        is_new_game = result.accepted and command.type is CommandType.NEW_GAME

        if not result.accepted and result.error is not None:
            self._diagnostics.command_rejected(
                command=command.type.value,
                code=result.error.code,
                message=result.error.message,
                source=command.source,
                revision=state.revision,
            )

        try:
            with self._transaction() as connection:
                self._flush_pending(connection)
                if result.accepted:
                    if is_new_game:
                        # The command that ends a game belongs to the log it
                        # closes, so the archived history explains its own end.
                        self._insert_history(
                            connection, self._command_row(command, result, timestamp)
                        )
                        self._close_game(connection, timestamp)
                        self._game_id = self._open_game(connection, timestamp)
                        self._write_state(
                            connection, state, timestamp, CHECKPOINT_SESSION_START
                        )
                        self._insert_history(
                            connection,
                            self._system_row(SESSION_STARTED, state, timestamp),
                        )
                    else:
                        self._write_state(
                            connection, state, timestamp, CHECKPOINT_COMMAND
                        )
                        self._insert_history(
                            connection, self._command_row(command, result, timestamp)
                        )
                else:
                    self._insert_history(
                        connection, self._command_row(command, result, timestamp)
                    )
        except (sqlite3.Error, OSError) as exc:
            self._game_id = previous_game_id
            self._queue_pending(self._command_row(command, result, timestamp))
            return self._fail("record_command", exc)

        if result.accepted:
            self._reset_display_cadence(state)
        self._refresh_backup()
        return self._succeed(state, timestamp, "Game state saved.")

    def record_expiration(
        self, clock: str, state: GameState, *, from_seconds: float
    ) -> PersistenceStatus:
        """Record that ``clock`` reached 0:00 by itself (F-037, F-046).

        The zero state and its history row commit in one transaction, exactly
        like an accepted command, so a crash can never leave a board at zero
        with no record of how it got there. No revision is advanced: expiration
        is something the clock did, not a mutation an operator requested, and
        the service remains the only writer of the authoritative revision.
        """

        if self._game_id is None:
            raise NoActiveGame("begin_session() must be called before recording expiry")
        if clock not in CLOCK_EXPIRED:
            raise ValueError(f"unknown clock: {clock!r}")
        timestamp = self._timestamp()
        row = (
            timestamp,
            CLOCK_EXPIRED[clock],
            SYSTEM_SOURCE,
            None,
            f"{clock}_clock" if clock != "event" else "event_countdown",
            _encode({"seconds": float(from_seconds), "running": True}),
            _encode({"seconds": 0.0, "running": False}),
            RESULT_ACCEPTED,
            None,
            None,
            state.revision,
            self._app_version,
        )
        try:
            with self._transaction() as connection:
                self._flush_pending(connection)
                self._write_state(connection, state, timestamp, CHECKPOINT_CLOCK_TICK)
                self._insert_history(connection, row)
        except (sqlite3.Error, OSError) as exc:
            self._queue_pending(row)
            return self._fail("record_expiration", exc)
        self._reset_display_cadence(state)
        self._refresh_backup()
        return self._succeed(state, timestamp, "Game state saved.")

    def record_game_clock_expiration_and_play_clock_clear(
        self,
        state: GameState,
        *,
        game_from_seconds: float,
        play_from_seconds: float,
    ) -> PersistenceStatus:
        """Atomically record a game expiry and its stop-side play-clock clear.

        Both are system observations and leave ``state.revision`` unchanged,
        but they must share a transaction so recovery never sees the cleared
        board without the reason it happened.
        """

        if self._game_id is None:
            raise NoActiveGame("begin_session() must be called before recording expiry")
        timestamp = self._timestamp()
        common = (RESULT_ACCEPTED, None, None, state.revision, self._app_version)
        game_row = (
            timestamp,
            CLOCK_EXPIRED["game"],
            SYSTEM_SOURCE,
            None,
            "game_clock",
            _encode({"seconds": float(game_from_seconds), "running": True}),
            _encode({"seconds": 0.0, "running": False}),
            *common,
        )
        clear_row = (
            timestamp,
            PLAY_CLOCK_CLEARED_ON_GAME_CLOCK_STOP,
            SYSTEM_SOURCE,
            None,
            "play_clock",
            _encode({"seconds": float(play_from_seconds), "running": True}),
            _encode({"seconds": 0.0, "running": False}),
            *common,
        )
        try:
            with self._transaction() as connection:
                self._flush_pending(connection)
                self._write_state(connection, state, timestamp, CHECKPOINT_CLOCK_TICK)
                self._insert_history(connection, game_row)
                self._insert_history(connection, clear_row)
        except (sqlite3.Error, OSError) as exc:
            self._queue_pending(game_row)
            self._queue_pending(clear_row)
            return self._fail("record_game_clock_expiration_and_play_clock_clear", exc)
        self._reset_display_cadence(state)
        self._refresh_backup()
        return self._succeed(state, timestamp, "Game state saved.")

    # --- Running-clock checkpoints -----------------------------------------

    def checkpoint(self, state: GameState, *, force: bool = False) -> bool:
        """Store a running clock's materialized value once per displayed second.

        ``state`` must carry materialized clock values -- use
        :meth:`~scoreboard.application.service.ScoreboardService.materialized_state`.
        Returns whether a write happened. No action-history row is ever written
        here: display ticks are not operator actions (P-003).
        """

        if self._game_id is None:
            raise NoActiveGame("begin_session() must be called before checkpointing")
        displayed = self._display_key(state)
        if not force and displayed == self._last_displayed:
            return False
        timestamp = self._timestamp()
        try:
            with self._transaction() as connection:
                self._flush_pending(connection)
                self._write_state(connection, state, timestamp, CHECKPOINT_CLOCK_TICK)
        except (sqlite3.Error, OSError) as exc:
            self._fail("checkpoint", exc)
            return False
        self._last_displayed = displayed
        self._succeed(state, timestamp, "Game state saved.")
        return True

    # --- Internals ----------------------------------------------------------

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.commit()
        except BaseException:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            raise

    def _timestamp(self) -> str:
        return self._wall_clock().isoformat()

    def _display_key(self, state: GameState) -> tuple[int, int, int]:
        return (
            displayed_second(state.game_clock.seconds),
            displayed_second(state.play_clock.seconds),
            displayed_second(state.event_countdown.seconds),
        )

    def _reset_display_cadence(self, state: GameState) -> None:
        self._last_displayed = self._display_key(state)

    def _open_game(self, connection: sqlite3.Connection, timestamp: str) -> int:
        self._close_game(connection, timestamp)
        cursor = connection.execute(
            "INSERT INTO games(started_at, closed_at, status, app_version) VALUES(?, NULL, ?, ?)",
            (timestamp, GAME_ACTIVE, self._app_version),
        )
        return int(cursor.lastrowid)

    def _close_game(self, connection: sqlite3.Connection, timestamp: str) -> None:
        connection.execute(
            "UPDATE games SET status = ?, closed_at = ? WHERE status = ?",
            (GAME_ARCHIVED, timestamp, GAME_ACTIVE),
        )

    def _write_state(
        self,
        connection: sqlite3.Connection,
        state: GameState,
        timestamp: str,
        kind: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO game_state(
                game_id, state_revision, snapshot_json, checkpoint_at,
                checkpoint_kind, app_version
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                state_revision = excluded.state_revision,
                snapshot_json = excluded.snapshot_json,
                checkpoint_at = excluded.checkpoint_at,
                checkpoint_kind = excluded.checkpoint_kind,
                app_version = excluded.app_version
            """,
            (
                self._game_id,
                state.revision,
                json.dumps(state_to_snapshot(state), sort_keys=True, separators=(",", ":")),
                timestamp,
                kind,
                state.app_version,
            ),
        )

    def _insert_history(self, connection: sqlite3.Connection, row: tuple[Any, ...]) -> None:
        connection.execute(
            """
            INSERT INTO action_history(
                game_id, wall_clock, command, source, team, field,
                old_value, new_value, result, error_code, error_message,
                state_revision, app_version
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self._game_id, *row),
        )

    def _flush_pending(self, connection: sqlite3.Connection) -> None:
        """Re-insert history rows a previous failed write could not commit.

        Their ``sequence`` is assigned now, so the monotonic sequence stays
        gap-free and strictly increasing; ``wall_clock`` preserves when the
        operator actually acted.
        """

        if not self._pending_history:
            return
        pending, self._pending_history = self._pending_history, []
        for row in pending:
            self._insert_history(connection, row)
        self._diagnostics.persistence_recovered(
            operation="record_command", replayed_rows=len(pending)
        )

    def _queue_pending(self, row: tuple[Any, ...]) -> None:
        if len(self._pending_history) >= MAX_PENDING_HISTORY_ROWS:
            self._pending_history.pop(0)
        self._pending_history.append(row)

    def _command_row(
        self, command: Command, result: CommandResult, timestamp: str
    ) -> tuple[Any, ...]:
        """Build the history row for one submitted command, accepted or not."""

        if result.accepted and result.event is not None:
            event = result.event
            return (
                timestamp,
                command.type.value,
                event.source,
                event.team,
                event.field,
                _encode(event.old_value),
                _encode(event.new_value),
                RESULT_ACCEPTED,
                None,
                None,
                result.state.revision,
                self._app_version,
            )
        # A rejection carries no event by design, so the row is built from the
        # submitted command plus the error: what was asked for, and why it was
        # refused. Nothing changed, so there is no new value to record.
        error = result.error
        return (
            timestamp,
            command.type.value,
            command.source,
            command.team,
            None,
            None,
            _encode(_requested_arguments(command)),
            RESULT_REJECTED,
            None if error is None else error.code,
            None if error is None else error.message,
            result.state.revision,
            self._app_version,
        )

    def _system_row(
        self, event: str, state: GameState, timestamp: str
    ) -> tuple[Any, ...]:
        return (
            timestamp,
            event,
            SYSTEM_SOURCE,
            None,
            "session",
            None,
            _encode({"state_revision": state.revision}),
            RESULT_ACCEPTED,
            None,
            None,
            state.revision,
            self._app_version,
        )

    def _refresh_backup(self) -> None:
        """Refresh the last-known-good backup from the just-committed database.

        The policy is bounded and testable: refresh after a verified commit,
        never from a half-written file, and never on a running-clock tick alone.
        A backup failure is logged and surfaced but does not retract a primary
        save that really did commit.
        """

        try:
            destination = sqlite3.connect(str(self._paths.backup))
            try:
                self._connection.backup(destination)
            finally:
                destination.close()
        except (sqlite3.Error, OSError) as exc:
            self._diagnostics.persistence_failure(operation="refresh_backup", error=str(exc))

    def _succeed(
        self, state: GameState, timestamp: str, message: str
    ) -> PersistenceStatus:
        self._status = PersistenceStatus(
            saved=True,
            message=message,
            revision=state.revision,
            checkpoint_at=timestamp,
            using_backup=self._using_backup,
            last_error=None,
            pending_history_rows=len(self._pending_history),
        )
        return self._status

    def _fail(self, operation: str, error: BaseException) -> PersistenceStatus:
        self._diagnostics.persistence_failure(operation=operation, error=str(error))
        self._status = PersistenceStatus(
            saved=False,
            message=(
                "NOT SAVED: the game is running from memory only. "
                f"Saving failed while {operation.replace('_', ' ')} "
                f"({error}). The next command will try again."
            ),
            revision=self._status.revision,
            checkpoint_at=self._status.checkpoint_at,
            using_backup=self._using_backup,
            last_error=str(error),
            pending_history_rows=len(self._pending_history),
        )
        return self._status


def _encode(value: Any) -> str | None:
    """Serialize a history value as JSON so old/new keep their real shape."""

    if value is None:
        return None
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _requested_arguments(command: Command) -> dict[str, Any]:
    """The populated arguments of a submitted command, for a rejected row."""

    requested: dict[str, Any] = {}
    for name in ("team", "points", "value", "label", "name", "seconds"):
        argument = getattr(command, name, None)
        if argument is not None:
            requested[name] = argument
    requested["confirmed"] = command.confirmed
    if command.expected_revision is not None:
        requested["expected_revision"] = command.expected_revision
    return requested


def decode(value: str | None) -> Any:
    """Read back a value written by :func:`_encode`, for audit and tests."""

    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


HISTORY_COLUMNS: Final[Sequence[str]] = (
    "sequence",
    "game_id",
    "wall_clock",
    "command",
    "source",
    "team",
    "field",
    "old_value",
    "new_value",
    "result",
    "error_code",
    "error_message",
    "state_revision",
    "app_version",
)


__all__ = [
    "CLOCK_EXPIRED",
    "CHECKPOINT_CLOCK_TICK",
    "CHECKPOINT_COMMAND",
    "CHECKPOINT_RECOVERED",
    "CHECKPOINT_SESSION_START",
    "CHECKPOINT_SHUTDOWN",
    "DATABASE_SCHEMA_VERSION",
    "GAME_ACTIVE",
    "GAME_ARCHIVED",
    "HISTORY_COLUMNS",
    "RESULT_ACCEPTED",
    "RESULT_REJECTED",
    "SESSION_RESUMED",
    "SESSION_SHUTDOWN",
    "SESSION_STARTED",
    "DatabaseInvalid",
    "GameStore",
    "InstanceAlreadyRunning",
    "InstanceLock",
    "NoActiveGame",
    "PersistenceError",
    "PersistenceStatus",
    "StoredGame",
    "apply_schema",
    "connect",
    "decode",
    "promote_backup",
    "read_action_history",
    "read_stored_game",
    "stopped_clock",
    "stopped_state",
    "validate_database",
]
