"""JSON-compatible snapshot boundary for the authoritative state."""

from __future__ import annotations

import json
from typing import Any, Mapping

from scoreboard.domain.state import (
    APP_VERSION,
    ClockValue,
    GameState,
    StateValidationError,
    default_state,
)


def state_to_snapshot(state: GameState) -> dict[str, Any]:
    """Convert state to a detached, JSON-compatible dictionary."""

    if not isinstance(state, GameState):
        raise TypeError("state must be a GameState")
    return {
        "schema_version": state.schema_version,
        "app_version": state.app_version,
        "state_revision": state.revision,
        "teams": {
            "home": {"name": state.home_name, "score": state.home_score},
            "away": {"name": state.away_name, "score": state.away_score},
        },
        "quarter": state.quarter,
        "lifecycle": state.lifecycle,
        "clocks": {
            "game": {"seconds": state.game_clock.seconds, "running": state.game_clock.running},
            "play": {"seconds": state.play_clock.seconds, "running": state.play_clock.running},
            "event": {
                "seconds": state.event_countdown.seconds,
                "running": state.event_countdown.running,
            },
        },
        "event_phase": state.event_phase,
    }


def snapshot_to_json(state: GameState) -> str:
    """Serialize a complete snapshot using only standard-library JSON."""

    return json.dumps(state_to_snapshot(state), sort_keys=True, separators=(",", ":"))


def snapshot_to_state(snapshot: Mapping[str, Any]) -> GameState:
    """Validate and reconstruct state from a snapshot dictionary."""

    if not isinstance(snapshot, Mapping):
        raise StateValidationError("snapshot must be a mapping")
    try:
        teams = snapshot["teams"]
        clocks = snapshot["clocks"]
        home = teams["home"]
        away = teams["away"]
        game = clocks["game"]
        play = clocks["play"]
        event = clocks["event"]
        return GameState(
            schema_version=snapshot["schema_version"],
            app_version=snapshot["app_version"],
            revision=snapshot["state_revision"],
            home_name=home["name"],
            away_name=away["name"],
            home_score=home["score"],
            away_score=away["score"],
            quarter=snapshot["quarter"],
            lifecycle=snapshot["lifecycle"],
            game_clock=ClockValue(game["seconds"], game["running"], 12 * 60),
            play_clock=ClockValue(play["seconds"], play["running"], 40),
            event_countdown=ClockValue(event["seconds"], event["running"], 30 * 60),
            event_phase=snapshot["event_phase"],
        )
    except (KeyError, TypeError) as exc:
        raise StateValidationError(f"invalid snapshot shape: {exc}") from exc


def json_to_state(payload: str) -> GameState:
    """Deserialize and validate a JSON snapshot."""

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StateValidationError("snapshot is not valid JSON") from exc
    return snapshot_to_state(value)


def snapshot(state: GameState | None = None) -> dict[str, Any]:
    """Return the default or supplied state as a snapshot dictionary."""

    return state_to_snapshot(default_state() if state is None else state)


__all__ = [
    "APP_VERSION",
    "json_to_state",
    "snapshot",
    "snapshot_to_json",
    "snapshot_to_state",
    "state_to_snapshot",
]
