"""Startup inspection and the operator's explicit recovery choice.

Nothing here resumes a game. :func:`inspect_recovery` reads what survived an
interruption and reports it; the operator then chooses ``Resume recovered
game`` or ``Start new game``, and only that choice builds a service (P-005).
Two functions rather than one flag makes the "no automatic resume" rule
structural instead of a comment.

Recovery restores team names, scores, quarter/phase, and each clock's most
recent checkpoint **with every clock stopped**, even when it was running at the
moment of failure (P-004). The board is therefore always behind reality by at
most the time since the crash, never ahead of it, and the operator reconciles
the difference deliberately before restarting a clock.

This module returns models. It renders nothing: the operator view is Task 7.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable

from scoreboard.application.service import ScoreboardService, initial_state
from scoreboard.application.snapshots import state_to_snapshot
from scoreboard.domain.rules import GameRules
from scoreboard.domain.state import APP_VERSION, GameState
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.local_time import format_local_timestamp
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.infrastructure.persistence import (
    DatabaseInvalid,
    StoredGame,
    promote_backup,
    read_stored_game,
    stopped_state,
    validate_database,
)


class RecoverySource(str, Enum):
    """Where the offered state came from, and whether one exists at all."""

    #: The primary database was valid and held an active game.
    PRIMARY = "PRIMARY"
    #: The primary database was unusable; the last-known-good backup was loaded.
    BACKUP = "BACKUP"
    #: Both databases were readable but held no game to recover.
    NONE = "NONE"
    #: Neither database could be trusted. Nothing is guessed (P-006).
    UNRECOVERABLE = "UNRECOVERABLE"


#: The two choices the operator must pick between. Never chosen automatically.
RESUME_CHOICE: str = "Resume recovered game"
NEW_GAME_CHOICE: str = "Start new game"


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """What startup found, and what the operator may choose to do about it."""

    source: RecoverySource
    message: str
    state: GameState | None = None
    game_id: int | None = None
    checkpoint_at: str | None = None
    #: ``checkpoint_at`` rendered as human-readable Eastern time for an
    #: operator to read, e.g. ``"September 5, 2026 at 10:41 AM EDT"``.
    #: ``checkpoint_at`` itself stays an unambiguous UTC ISO 8601 string, which
    #: is what the database and diagnostics log keep using.
    checkpoint_at_local: str | None = None
    checkpoint_kind: str | None = None
    primary_error: str | None = None
    backup_error: str | None = None
    preserved_paths: tuple[str, ...] = ()
    #: The application version that wrote the offered game, when it differs
    #: from the running build. Shown so the operator knows an update happened
    #: between the interruption and this launch; it never blocks recovery.
    written_by_app_version: str | None = None

    @property
    def can_resume(self) -> bool:
        """Whether ``Resume recovered game`` is an available choice."""

        return self.state is not None

    @property
    def using_backup(self) -> bool:
        """Whether the offered state came from the backup, which must be shown."""

        return self.source is RecoverySource.BACKUP

    @property
    def choices(self) -> tuple[str, ...]:
        return (RESUME_CHOICE, NEW_GAME_CHOICE) if self.can_resume else (NEW_GAME_CHOICE,)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible report; no domain object crosses this boundary."""

        return {
            "source": self.source.value,
            "message": self.message,
            "can_resume": self.can_resume,
            "using_backup": self.using_backup,
            "choices": list(self.choices),
            "game_id": self.game_id,
            "checkpoint_at": self.checkpoint_at,
            "checkpoint_at_local": self.checkpoint_at_local,
            "checkpoint_kind": self.checkpoint_kind,
            "primary_error": self.primary_error,
            "backup_error": self.backup_error,
            "preserved_paths": list(self.preserved_paths),
            "written_by_app_version": self.written_by_app_version,
            "snapshot": None if self.state is None else state_to_snapshot(self.state),
        }


def _restored(state: GameState) -> GameState:
    """The offered state: every clock stopped, running under this build.

    ``app_version`` is stamped to the running build because that is the version
    now responsible for the game; the version that wrote it is reported
    separately on :class:`RecoveryReport` rather than being silently lost. The
    revision is untouched, so restoring still invents nothing (P-004).
    """

    return replace(stopped_state(state), app_version=APP_VERSION)


def _written_by(stored: StoredGame) -> str | None:
    """The saving version, when a build change happened across the restart."""

    written = stored.state.app_version
    return None if written == APP_VERSION else written


def _upgrade_note(stored: StoredGame) -> str:
    written = _written_by(stored)
    if written is None:
        return ""
    return (
        f" This game was saved by version {written} and is being opened by "
        f"version {APP_VERSION}; check the board before resuming."
    )


def _offer(stored: StoredGame, source: RecoverySource, message: str) -> RecoveryReport:
    return RecoveryReport(
        source=source,
        message=message + _upgrade_note(stored),
        # Stopping the clocks happens here, once, so no caller can forget it.
        state=_restored(stored.state),
        game_id=stored.game_id,
        checkpoint_at=stored.checkpoint_at,
        checkpoint_at_local=format_local_timestamp(stored.checkpoint_at),
        checkpoint_kind=stored.checkpoint_kind,
        written_by_app_version=_written_by(stored),
    )


def inspect_recovery(
    paths: ScoreboardPaths,
    *,
    diagnostics: Diagnostics | None = None,
    stamp: str | None = None,
) -> RecoveryReport:
    """Decide what can be recovered, without resuming anything.

    A corrupt primary database is preserved under a new name and the backup is
    promoted in its place, so the fallback is both usable and visible (P-006).
    If neither file can be trusted, both are left exactly as they are and the
    report says so: the application never invents a score or a clock value.
    """

    log = NullDiagnostics() if diagnostics is None else diagnostics
    paths.ensure()
    primary_error = validate_database(paths.database)
    primary_missing = primary_error is not None and not paths.database.exists()

    if primary_error is None:
        try:
            stored = read_stored_game(paths.database)
        except DatabaseInvalid as exc:
            primary_error = str(exc)
        else:
            if stored is not None:
                report = _offer(
                    stored,
                    RecoverySource.PRIMARY,
                    "A saved game was found. Its clocks are stopped at the last "
                    f"checkpoint ({format_local_timestamp(stored.checkpoint_at)}).",
                )
                log.recovery(source=report.source.value, message=report.message)
                return report
            report = RecoveryReport(
                source=RecoverySource.NONE,
                message="No game was in progress. Start a new game.",
            )
            log.recovery(source=report.source.value, message=report.message)
            return report

    backup_error = validate_database(paths.backup)
    if backup_error is None:
        try:
            stored = read_stored_game(paths.backup)
        except DatabaseInvalid as exc:
            backup_error = str(exc)
            stored = None
        if backup_error is None and stored is not None:
            preserved: tuple[str, ...] = ()
            if not primary_missing:
                quarantined = promote_backup(paths, stamp=stamp or stored.checkpoint_at)
                preserved = (str(quarantined),)
            else:
                promote_backup(paths, stamp=stamp or stored.checkpoint_at)
            report = RecoveryReport(
                source=RecoverySource.BACKUP,
                message=(
                    "RECOVERED FROM BACKUP: the main game file could not be read, "
                    "so the last-known-good backup was loaded. Its clocks are "
                    f"stopped at {format_local_timestamp(stored.checkpoint_at)}. "
                    "Check the board against the real game before resuming."
                    + _upgrade_note(stored)
                ),
                state=_restored(stored.state),
                game_id=stored.game_id,
                checkpoint_at=stored.checkpoint_at,
                checkpoint_at_local=format_local_timestamp(stored.checkpoint_at),
                checkpoint_kind=stored.checkpoint_kind,
                primary_error=primary_error,
                preserved_paths=preserved,
                written_by_app_version=_written_by(stored),
            )
            log.recovery(
                source=report.source.value,
                message=report.message,
                primary_error=primary_error,
                preserved=";".join(preserved),
            )
            return report
        if backup_error is None and stored is None:
            report = RecoveryReport(
                source=RecoverySource.NONE,
                message=(
                    "The main game file could not be read and the backup holds no "
                    "game in progress. Start a new game."
                ),
                primary_error=primary_error,
            )
            log.recovery(source=report.source.value, message=report.message)
            return report

    if primary_missing and (backup_error is not None and not paths.backup.exists()):
        report = RecoveryReport(
            source=RecoverySource.NONE,
            message="No saved game was found. Start a new game.",
        )
        log.recovery(source=report.source.value, message=report.message)
        return report

    # Both files exist and neither can be trusted. Preserve them untouched and
    # say exactly where they are; do not guess at the missing values (P-006).
    preserved = tuple(
        str(path) for path in (paths.database, paths.backup) if path.exists()
    )
    report = RecoveryReport(
        source=RecoverySource.UNRECOVERABLE,
        message=(
            "RECOVERY FAILED: neither the main game file nor its backup could be "
            "read, so no game can be restored. Both files have been left in place "
            "for inspection. Start a new game and enter the current score and time "
            "from the field."
        ),
        primary_error=primary_error,
        backup_error=backup_error,
        preserved_paths=preserved,
    )
    log.recovery(
        source=report.source.value,
        message=report.message,
        primary_error=primary_error,
        backup_error=backup_error,
    )
    return report


def resume_recovered_game(
    report: RecoveryReport,
    *,
    monotonic_clock: Callable[[], float] | None = None,
    rules: GameRules | None = None,
) -> ScoreboardService:
    """Seed a service from the recovered, already-stopped state.

    The state passes through the ordinary
    ``ScoreboardService(state=..., monotonic_clock=...)`` constructor, so a
    resumed game is validated by exactly the same rules as a fresh one, and the
    service remains the only component that can advance the revision.

    The in-memory one-level undo entry is deliberately **not** restored: see the
    decision recorded in :mod:`scoreboard.infrastructure.persistence`.
    """

    if report.state is None:
        raise ValueError("this recovery report has no state to resume")
    return ScoreboardService(
        state=report.state, monotonic_clock=monotonic_clock, rules=rules
    )


def start_new_game(
    *,
    monotonic_clock: Callable[[], float] | None = None,
    rules: GameRules | None = None,
) -> ScoreboardService:
    """Begin from the documented stopped pregame baseline, discarding nothing.

    Any recovered database rows stay on disk; starting new opens a new game
    identity at the persistence layer rather than deleting the previous game.
    The baseline loads the operator's configured pregame length and timeouts
    per half (``rules``), or the shipped defaults.
    """

    return ScoreboardService(
        state=initial_state(rules), monotonic_clock=monotonic_clock, rules=rules
    )


__all__ = [
    "NEW_GAME_CHOICE",
    "RESUME_CHOICE",
    "RecoveryReport",
    "RecoverySource",
    "inspect_recovery",
    "resume_recovered_game",
    "start_new_game",
]
