"""JSON-compatible snapshot boundary for the authoritative state."""

from __future__ import annotations

import json
from typing import Any, Mapping

from scoreboard.domain.state import (
    APP_VERSION,
    BallSpot,
    ClockValue,
    GameState,
    MAX_GAME_CLOCK_SECONDS,
    MAX_PREGAME_CLOCK_SECONDS,
    MAX_STATUS_CLOCK_SECONDS,
    MAX_TIMEOUTS,
    StateValidationError,
    default_state,
)

_DEFAULT_BALL_ON = BallSpot()


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
        "play_clock_cleared": state.play_clock_cleared,
        "football": {
            "down": state.down,
            "distance": state.distance,
            "possession": state.possession,
            "ball_on": (
                None
                if state.ball_on is None
                else {"team": state.ball_on.team, "yard_line": state.ball_on.yard_line}
            ),
            "timeouts": {"home": state.home_timeouts, "away": state.away_timeouts},
        },
        # Additive Field Assistant recovery state.  It intentionally contains
        # no draft or inferred result: only the first-quarter direction and
        # active series line-to-gain survive a restart.
        "assistant": {
            "first_quarter_home_direction": state.assistant_first_quarter_home_direction,
            "line_to_gain": state.assistant_line_to_gain,
        },
        # F3's crowd-facing status word and its countdown (additive: a
        # snapshot written before this change has no "status" key at all, and
        # must still load with fresh-state defaults -- see snapshot_to_state
        # below and the "football"/"assistant" fallbacks it already follows).
        "status": {
            "label": state.game_status,
            "clock": {
                "seconds": state.status_clock.seconds,
                "running": state.status_clock.running,
            },
            "clock_cleared": state.status_clock_cleared,
        },
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
        # Additive since the football-state expansion: a snapshot written
        # before that change has no "football" key at all, and must still
        # load with the same defaults a fresh GameState() carries (P-004,
        # P-006) rather than becoming unrecoverable.
        football = snapshot.get("football", {})
        # Assistant state is additive.  Older snapshots had no key, and must
        # recover into the safe "assistant setup required" state.
        assistant = snapshot.get("assistant", {})
        # F3's status block is additive too: a snapshot written before this
        # change has no "status" key at all, and must still load with the
        # same defaults a fresh GameState() carries (P-004, P-006).
        status = snapshot.get("status", {})
        status_clock = status.get("clock", {})
        ball_on = football.get(
            "ball_on",
            {"team": _DEFAULT_BALL_ON.team, "yard_line": _DEFAULT_BALL_ON.yard_line},
        )
        timeouts = football.get("timeouts", {})
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
            game_clock=ClockValue(
                game["seconds"],
                game["running"],
                MAX_PREGAME_CLOCK_SECONDS if snapshot["quarter"] == "PRE" else MAX_GAME_CLOCK_SECONDS,
            ),
            play_clock=ClockValue(play["seconds"], play["running"], 40),
            event_countdown=ClockValue(event["seconds"], event["running"], 30 * 60),
            event_phase=snapshot["event_phase"],
            play_clock_cleared=snapshot.get("play_clock_cleared",
                                            play["seconds"] == 0 and not play["running"]),
            down=football.get("down"),
            distance=football.get("distance"),
            possession=football.get("possession"),
            ball_on=(
                None
                if ball_on is None
                else BallSpot(
                    ball_on.get("team", _DEFAULT_BALL_ON.team),
                    ball_on.get("yard_line", _DEFAULT_BALL_ON.yard_line),
                )
            ),
            home_timeouts=timeouts.get("home", MAX_TIMEOUTS),
            away_timeouts=timeouts.get("away", MAX_TIMEOUTS),
            assistant_first_quarter_home_direction=assistant.get(
                "first_quarter_home_direction"
            ),
            assistant_line_to_gain=assistant.get("line_to_gain"),
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
