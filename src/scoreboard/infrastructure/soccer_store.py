"""Soccer's embedded SQLite persistence: a thin subclass of football's ``GameStore``.

Mirrors ``infrastructure.persistence.GameStore``. Same schema, same file names, pointed at
``<root>/soccer/scoreboard.db`` (spec section 2.6). ``validate_database``/``promote_backup``/
``DATABASE_SCHEMA_VERSION``/``apply_schema``/``connect`` and the ``GameStore`` class's SQL are
sport-agnostic (they operate on a SQLite file and a JSON blob column, never on ``GameState``'s
Python type), so this reuses the entire class, overriding only the two private methods that
hard-code football's snapshot codec and clock shape (``.scratch/soccer-mode/IMPLEMENTERS.md``),
plus ``record_command``'s ``NEW_GAME`` identity check, which compares against football's own
``CommandType`` enum member and would otherwise never match a ``SoccerCommandType.NEW_GAME``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from scoreboard.application.soccer_snapshots import state_to_snapshot
from scoreboard.domain.soccer.commands import SoccerCommandType
from scoreboard.domain.soccer.state import SoccerState
from scoreboard.infrastructure.persistence import (
    CHECKPOINT_COMMAND,
    CHECKPOINT_SESSION_START,
    SESSION_STARTED,
    GameStore,
)


class SoccerGameStore(GameStore):
    """``GameStore`` pointed at soccer's own database, with soccer's snapshot codec."""

    def _display_key(self, state: SoccerState) -> tuple[int]:
        """Soccer has one clock, not two: key the checkpoint cadence on it alone."""

        from scoreboard.domain.formatting import displayed_second

        return (displayed_second(state.game_clock.seconds),)

    def _write_state(
        self, connection: sqlite3.Connection, state: SoccerState, timestamp: str, kind: str
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

    def record_command(self, command: Any, result: Any):
        """Identical to ``GameStore.record_command`` except the ``NEW_GAME`` identity check.

        Football's method compares ``command.type is CommandType.NEW_GAME`` -- a different
        enum class, so it never matches ``SoccerCommandType.NEW_GAME`` even though the string
        value is the same. Everything else -- the transaction shape, the history rows, the
        backup cadence -- is sport-agnostic and reused unchanged from the parent class.
        """

        from scoreboard.infrastructure.persistence import NoActiveGame

        if self._game_id is None:
            raise NoActiveGame("begin_session() must be called before recording commands")

        timestamp = self._timestamp()
        state = result.state
        previous_game_id = self._game_id
        is_new_game = result.accepted and command.type is SoccerCommandType.NEW_GAME

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
                        self._insert_history(connection, self._command_row(command, result, timestamp))
                        self._close_game(connection, timestamp)
                        self._game_id = self._open_game(connection, timestamp)
                        self._write_state(connection, state, timestamp, CHECKPOINT_SESSION_START)
                        self._insert_history(
                            connection, self._system_row(SESSION_STARTED, state, timestamp)
                        )
                    else:
                        self._write_state(connection, state, timestamp, CHECKPOINT_COMMAND)
                        self._insert_history(connection, self._command_row(command, result, timestamp))
                else:
                    self._insert_history(connection, self._command_row(command, result, timestamp))
        except (sqlite3.Error, OSError) as exc:
            self._game_id = previous_game_id
            self._queue_pending(self._command_row(command, result, timestamp))
            return self._fail("record_command", exc)

        if result.accepted:
            self._reset_display_cadence(state)
        self._refresh_backup()
        return self._succeed(state, timestamp, "Game state saved.")


__all__ = ["SoccerGameStore"]
