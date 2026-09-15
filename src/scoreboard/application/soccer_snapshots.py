"""JSON-compatible snapshot boundary for the authoritative soccer state.

Mirrors ``scoreboard.application.snapshots``. The top-level ``"sport": "soccer"`` key lets any
future shared tooling tell the two snapshot shapes apart on sight (spec section 3.2,
domain_draft.md section 5.1).
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from scoreboard.domain.soccer.state import (
    APP_VERSION,
    MAX_PREGAME_CLOCK_SECONDS,
    MAX_STATUS_CLOCK_SECONDS,
    CardEvent,
    ClockValue,
    ShootoutKick,
    SoccerState,
    StateValidationError,
    default_state,
)

SOCCER_SNAPSHOT_SCHEMA_VERSION = 1


def state_to_snapshot(state: SoccerState) -> dict[str, Any]:
    """Convert state to a detached, JSON-compatible dictionary."""

    if not isinstance(state, SoccerState):
        raise TypeError("state must be a SoccerState")
    return {
        "sport": "soccer",
        "schema_version": state.schema_version,
        "app_version": state.app_version,
        "state_revision": state.revision,
        "teams": {
            "home": {"name": state.home_name, "score": state.home_score},
            "away": {"name": state.away_name, "score": state.away_score},
        },
        "period": state.period,
        "lifecycle": state.lifecycle,
        "clocks": {
            "game": {
                "seconds": state.game_clock.seconds,
                "running": state.game_clock.running,
                "maximum_seconds": state.game_clock.maximum_seconds,
            },
        },
        "stats": {
            "home": {
                "shots": state.home_shots,
                "saves": state.home_saves,
                "corners": state.home_corners,
                "fouls": state.home_fouls,
            },
            "away": {
                "shots": state.away_shots,
                "saves": state.away_saves,
                "corners": state.away_corners,
                "fouls": state.away_fouls,
            },
        },
        "cards": [
            {
                "team": c.team,
                "kind": c.kind,
                "player_number": c.player_number,
                "period": c.period,
                "clock_display": c.clock_display,
            }
            for c in state.cards
        ],
        "shootout": {
            "first_kicker": state.shootout_first_kicker,
            "winner": state.shootout_winner,
            "kicks": [
                {
                    "team": k.team,
                    "round": k.round,
                    "kicker_number": k.kicker_number,
                    "made": k.made,
                }
                for k in state.shootout_kicks
            ],
        },
        "status": {
            "label": state.game_status,
            "clock": {
                "seconds": state.status_clock.seconds,
                "running": state.status_clock.running,
            },
            "clock_cleared": state.status_clock_cleared,
        },
    }


def snapshot_to_json(state: SoccerState) -> str:
    """Serialize a complete snapshot using only standard-library JSON."""

    return json.dumps(state_to_snapshot(state), sort_keys=True, separators=(",", ":"))


def snapshot_to_state(snapshot: Mapping[str, Any]) -> SoccerState:
    """Validate and reconstruct state from a snapshot dictionary.

    Additive-tolerant: ``stats``/``cards``/``shootout``/``status`` may each be absent (an older
    build's snapshot) and fall back to ``SoccerState()``'s defaults (spec section 3.2).
    """

    if not isinstance(snapshot, Mapping):
        raise StateValidationError("snapshot must be a mapping")
    try:
        teams = snapshot["teams"]
        clocks = snapshot["clocks"]
        home = teams["home"]
        away = teams["away"]
        game = clocks["game"]
        stats = snapshot.get("stats", {})
        home_stats = stats.get("home", {})
        away_stats = stats.get("away", {})
        cards_raw = snapshot.get("cards", [])
        shootout = snapshot.get("shootout", {})
        kicks_raw = shootout.get("kicks", [])
        status = snapshot.get("status", {})
        status_clock = status.get("clock", {})

        cards = tuple(
            CardEvent(
                team=c["team"],
                kind=c["kind"],
                player_number=c.get("player_number"),
                period=c["period"],
                clock_display=c["clock_display"],
            )
            for c in cards_raw
        )
        kicks = tuple(
            ShootoutKick(
                team=k["team"],
                round=k["round"],
                kicker_number=k.get("kicker_number"),
                made=k["made"],
            )
            for k in kicks_raw
        )

        return SoccerState(
            schema_version=snapshot["schema_version"],
            app_version=snapshot["app_version"],
            revision=snapshot["state_revision"],
            home_name=home["name"],
            away_name=away["name"],
            home_score=home["score"],
            away_score=away["score"],
            period=snapshot["period"],
            lifecycle=snapshot["lifecycle"],
            game_clock=ClockValue(
                game["seconds"],
                game["running"],
                game.get(
                    "maximum_seconds",
                    MAX_PREGAME_CLOCK_SECONDS if snapshot["period"] == "PRE" else 2400.0,
                ),
            ),
            home_shots=home_stats.get("shots", 0),
            away_shots=away_stats.get("shots", 0),
            home_saves=home_stats.get("saves", 0),
            away_saves=away_stats.get("saves", 0),
            home_corners=home_stats.get("corners", 0),
            away_corners=away_stats.get("corners", 0),
            home_fouls=home_stats.get("fouls", 0),
            away_fouls=away_stats.get("fouls", 0),
            cards=cards,
            shootout_first_kicker=shootout.get("first_kicker"),
            shootout_kicks=kicks,
            shootout_winner=shootout.get("winner"),
            game_status=status.get("label"),
            status_clock=ClockValue(
                status_clock.get("seconds", 0.0),
                status_clock.get("running", False),
                MAX_STATUS_CLOCK_SECONDS,
            ),
            status_clock_cleared=status.get("clock_cleared", True),
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise StateValidationError(f"invalid snapshot shape: {exc}") from exc


def json_to_state(payload: str) -> SoccerState:
    """Deserialize and validate a JSON snapshot."""

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StateValidationError("snapshot is not valid JSON") from exc
    return snapshot_to_state(value)


def snapshot(state: SoccerState | None = None) -> dict[str, Any]:
    """Return the default or supplied state as a snapshot dictionary."""

    return state_to_snapshot(default_state() if state is None else state)


__all__ = [
    "APP_VERSION",
    "SOCCER_SNAPSHOT_SCHEMA_VERSION",
    "json_to_state",
    "snapshot",
    "snapshot_to_json",
    "snapshot_to_state",
    "state_to_snapshot",
]
