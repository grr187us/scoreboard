"""Startup inspection and the operator's explicit recovery choice, for soccer.

Mirrors ``scoreboard.application.recovery``, calling straight into football's own
``inspect_recovery`` with the additive ``decode``/``stop_clocks`` seams (spec section 2.5,
domain_draft.md section 5.2) rather than duplicating the recovery-report logic. Football's
``RecoveryReport``/``RecoverySource``/``RESUME_CHOICE``/``NEW_GAME_CHOICE`` are reused directly:
they are sport-agnostic value/enum types.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from scoreboard.application.recovery import (
    NEW_GAME_CHOICE,
    RESUME_CHOICE,
    RecoveryReport,
    RecoverySource,
    inspect_recovery,
)
from scoreboard.application.soccer_service import SoccerService, initial_soccer_state
from scoreboard.application.soccer_snapshots import snapshot_to_state, state_to_snapshot
from scoreboard.domain.soccer.rules import SoccerRules
from scoreboard.domain.soccer.state import SoccerState
from scoreboard.infrastructure.diagnostics import Diagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths


def soccer_stopped_state(state: SoccerState) -> SoccerState:
    """Every soccer clock stopped at its persisted value, revision unchanged.

    Soccer has no play clock, so only ``game_clock`` and ``status_clock`` are stopped (unlike
    football's ``stopped_state``, which also stops a play clock).
    """

    def _stopped(value):
        return replace(value, running=False, deadline_monotonic=None, started_at_monotonic=None)

    return replace(
        state,
        game_clock=_stopped(state.game_clock),
        status_clock=_stopped(state.status_clock),
    )


def inspect_soccer_recovery(
    paths: ScoreboardPaths,
    *,
    diagnostics: Diagnostics | None = None,
    stamp: str | None = None,
) -> RecoveryReport:
    """Decide what soccer game can be recovered from ``paths`` (soccer's own root)."""

    return inspect_recovery(
        paths,
        diagnostics=diagnostics,
        stamp=stamp,
        decode=snapshot_to_state,
        stop_clocks=soccer_stopped_state,
        encode=state_to_snapshot,
    )


def resume_recovered_soccer_game(
    report: RecoveryReport,
    *,
    monotonic_clock: Callable[[], float] | None = None,
    rules: SoccerRules | None = None,
) -> SoccerService:
    """Seed a soccer service from the recovered, already-stopped state."""

    if report.state is None:
        raise ValueError("this recovery report has no state to resume")
    return SoccerService(state=report.state, monotonic_clock=monotonic_clock, rules=rules)


def start_new_soccer_game(
    *,
    monotonic_clock: Callable[[], float] | None = None,
    rules: SoccerRules | None = None,
) -> SoccerService:
    """Begin from the documented stopped pregame baseline, discarding nothing."""

    return SoccerService(state=initial_soccer_state(rules), monotonic_clock=monotonic_clock, rules=rules)


__all__ = [
    "NEW_GAME_CHOICE",
    "RESUME_CHOICE",
    "RecoveryReport",
    "RecoverySource",
    "inspect_soccer_recovery",
    "resume_recovered_soccer_game",
    "soccer_stopped_state",
    "start_new_soccer_game",
]
