"""Soccer's Field Assistant bridge: mirrors ``host.bridge.FieldAssistantBridge``.

Spec: ``.scratch/soccer-mode/spec.md`` section 6 ("Soccer Field Assistant").

Football's assistant calculates field geometry (ball spot, down, distance) and
is a large pure rules engine (``domain.field_assistant``) fronted by a bridge
that previews and finalizes a composite play. Soccer's assistant is much
smaller by design (spec section 6, owner choice E): it only logs stats, cards,
and shootout kicks that a sideline volunteer can enter with a big-button
touchscreen. It never touches the score directly, the clock, or the period --
those stay operator-only.

Two things are kept deliberately separate, exactly as football keeps
``domain.field_assistant`` (pure) separate from ``host.bridge.FieldAssistantBridge``
(the window's JSON API):

* :func:`map_assist_action` is a pure function with no I/O: it is the single
  allow-list translating a JSON action envelope into the one ordinary soccer
  command (name, args) the assistant may ever send. Every kind not in the
  allow-list raises :class:`SoccerFieldAssistantError` -- there is no
  fall-through path by which a new command name (or a forbidden one, such as
  ``add_goal`` or any clock/period/undo command) could reach the operator.
* :func:`describe_assist_preview` is a second pure function that turns the
  mapped command's args plus a snapshot (the JSON view model, not a live
  service) into the Confirm button's label and the plain-English "resulting"
  text. It never mutates anything and is why :meth:`SoccerFieldAssistantBridge
  .preview_assist` can never change the game's revision.

``SoccerFieldAssistantBridge`` itself is the thin JSON-facing object a
soccer Field Assistant window is opened with (mirroring
``FieldAssistantBridge(operator)`` in ``host/bridge.py``). ``operator`` is a
``SoccerBridge`` (agent B, ``host/soccer_bridge.py``): this module depends only
on it exposing ``get_snapshot()`` and
``command(name, args, expected_revision, *, source="operator")`` -- the shape
IMPLEMENTERS.md documents for ``SoccerBridge.command`` -- so it can be pointed
at a test double until that module lands. ``finalize_assist`` is the only
method that calls ``operator.command`` (tagged ``source="field-assistant"``,
matching how ``FieldAssistantBridge.set_assistant_direction`` tags football's
one allowed command); ``preview_assist`` never does.
"""

from __future__ import annotations

from typing import Any, Final, Mapping, Protocol

__all__ = [
    "ASSIST_ACTION_KINDS",
    "CARD_KINDS",
    "STAT_NAMES",
    "SoccerFieldAssistantError",
    "SoccerFieldAssistantBridge",
    "SoccerOperatorLike",
    "describe_assist_preview",
    "map_assist_action",
]

# Mirrors scoreboard.domain.soccer.state.STAT_NAMES / CARD_KINDS (api_domain.md).
# Duplicated here, rather than imported, so this module's allow-list keeps
# working unchanged even if agent A's module import path is not yet available
# in a given test environment; the values are the spec's own vocabulary
# (spec section 3.1) and are exercised for agreement in the unit tests.
STAT_NAMES: Final[tuple[str, ...]] = ("shots", "saves", "corners", "fouls")
CARD_KINDS: Final[tuple[str, ...]] = ("yellow", "red")
TEAM_SIDES: Final[frozenset[str]] = frozenset(("home", "away"))

#: The complete allow-list of action kinds the assistant may translate into a
#: command. Anything else -- "goal", "score", "set_score", any clock or period
#: command, "undo" -- is refused by :func:`map_assist_action` because it is
#: simply not a key in this mapping (spec section 6, owner choice E: "GOAL
#: stays operator-only").
ASSIST_ACTION_KINDS: Final[dict[str, str]] = {
    "stat": "add_stat",
    "card": "add_card",
    "shootout_kick": "shootout_kick",
    "first_kicker": "set_shootout_first_kicker",
}

_STAT_DISPLAY: Final[dict[str, str]] = {
    "shots": "SHOT",
    "saves": "SAVE",
    "corners": "CORNER",
    "fouls": "FOUL",
}
_CARD_DISPLAY: Final[dict[str, str]] = {"yellow": "YELLOW", "red": "RED"}


class SoccerFieldAssistantError(ValueError):
    """Raised when a field assistant action is not one this module supports."""


class SoccerOperatorLike(Protocol):
    """The slice of ``SoccerBridge`` this module depends on (IMPLEMENTERS.md).

    A structural type only -- nothing here imports ``host.soccer_bridge``, so
    this module and its tests work whether or not that module exists yet.
    """

    def get_snapshot(self) -> dict[str, Any]: ...

    def command(
        self, name: str, args: Any, expected_revision: Any, *, source: str = "operator"
    ) -> dict[str, Any]: ...


def _require_team(action: Mapping[str, Any]) -> str:
    team = action.get("team")
    if team not in TEAM_SIDES:
        raise SoccerFieldAssistantError("team must be 'home' or 'away'")
    return team


def _optional_player_number(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 99:
        raise SoccerFieldAssistantError(f"{field_name} must be a whole number from 0 through 99 or null")
    return value


def map_assist_action(action: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate one JSON action envelope into (command name, command args).

    This is the whole allow-list. It is a pure function -- no snapshot, no
    bridge, no I/O -- so it is unit-testable on its own, per IMPLEMENTERS.md's
    instruction to keep the mapping separate from the bridge. Every supported
    ``kind`` is spelled out explicitly; the final ``raise`` is reached for
    every unsupported kind, including every football/legacy or soccer command
    this assistant must never be able to send (``add_goal``, ``set_score``,
    ``correct_goal``, any ``game_clock_*``/``status_clock_*``/period/``undo``
    command, or an unrecognised string).
    """

    if not isinstance(action, Mapping):
        raise SoccerFieldAssistantError("action must be an object")
    kind = action.get("kind")

    if kind == "stat":
        team = _require_team(action)
        stat = action.get("stat")
        if stat not in STAT_NAMES:
            raise SoccerFieldAssistantError(f"stat must be one of {STAT_NAMES}")
        step = action.get("step")
        if step not in (1, -1):
            raise SoccerFieldAssistantError("step must be +1 or -1")
        return "add_stat", {"team": team, "stat": stat, "step": step}

    if kind == "card":
        team = _require_team(action)
        card = action.get("card")
        if card not in CARD_KINDS:
            raise SoccerFieldAssistantError(f"card must be one of {CARD_KINDS}")
        player_number = _optional_player_number(action.get("player_number"), "player_number")
        return "add_card", {"team": team, "kind": card, "player": player_number}

    if kind == "shootout_kick":
        team = _require_team(action)
        made = action.get("made")
        if not isinstance(made, bool):
            raise SoccerFieldAssistantError("made must be true or false")
        kicker_number = _optional_player_number(action.get("kicker_number"), "kicker_number")
        return "shootout_kick", {"team": team, "made": made, "kicker": kicker_number}

    if kind == "first_kicker":
        team = _require_team(action)
        return "set_shootout_first_kicker", {"team": team}

    raise SoccerFieldAssistantError(f"unsupported field assistant action kind: {kind!r}")


def _team_stat(snapshot: Mapping[str, Any], team: str, stat: str) -> int | None:
    try:
        value = snapshot["soccer"][team][stat]
    except (KeyError, TypeError):
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def describe_assist_preview(
    snapshot: Mapping[str, Any], kind: str, command_args: Mapping[str, Any]
) -> dict[str, str]:
    """Compute the Confirm label and resulting text for an already-mapped action.

    Pure and read-only: ``snapshot`` is a JSON view model (as returned by
    ``get_snapshot()``), never a live service, so nothing here can change the
    game's revision. This is what lets
    :meth:`SoccerFieldAssistantBridge.preview_assist` be a plain read.
    """

    team = command_args.get("team")
    team_label = str(team).upper() if team else "?"

    if kind == "stat":
        stat = command_args["stat"]
        step = command_args["step"]
        current = _team_stat(snapshot, team, stat)
        resulting_value = None if current is None else max(0, current + step)
        stat_word = _STAT_DISPLAY.get(stat, str(stat).upper())
        resulting = f"{team_label} {stat_word}" + (f" #{resulting_value}" if resulting_value is not None else "")
        return {"label": f"CONFIRM → {resulting}", "resulting": resulting}

    if kind == "card":
        card = command_args["kind"]
        player = command_args.get("player")
        suffix = f" #{player}" if player is not None else ""
        resulting = f"{team_label} {_CARD_DISPLAY.get(card, str(card).upper())}{suffix}"
        return {"label": f"CONFIRM → {resulting}", "resulting": resulting}

    if kind == "shootout_kick":
        made = command_args["made"]
        kicker = command_args.get("kicker")
        suffix = f" #{kicker}" if kicker is not None else ""
        resulting = f"{team_label} {'MADE' if made else 'MISSED'}{suffix}"
        return {"label": f"CONFIRM → {resulting}", "resulting": resulting}

    if kind == "first_kicker":
        resulting = f"{team_label} KICKS FIRST"
        return {"label": f"CONFIRM → {resulting}", "resulting": resulting}

    raise SoccerFieldAssistantError(f"unsupported field assistant action kind: {kind!r}")


class SoccerFieldAssistantBridge:
    """The soccer Field Assistant window's deliberately small JSON API.

    Mirrors ``host.bridge.FieldAssistantBridge``: no generic ``command``
    endpoint is exposed here. A draft can only ask Python to preview one raw
    action or to submit that same action through the one ordinary command the
    allow-list in :func:`map_assist_action` names. Closing this bridge/window
    has no path to the game engine beyond that; reopening simply reads a fresh
    complete snapshot from ``operator``.
    """

    def __init__(self, operator: SoccerOperatorLike) -> None:
        self._operator = operator

    def get_snapshot(self) -> dict[str, Any]:
        """The current complete operator view model. Reads nothing else."""

        return self._operator.get_snapshot()

    def preview_assist(self, action: Any) -> dict[str, Any]:
        """Read-only: the Confirm label and resulting text for ``action``.

        Never calls ``operator.command`` -- only ``get_snapshot()`` -- so a
        preview can never change the game's revision, no matter how many
        times it is pressed while the operator dithers over a button.
        """

        try:
            name, args = map_assist_action(action)
        except SoccerFieldAssistantError as exc:
            return {"ok": False, "label": None, "resulting": None, "error": str(exc)}
        snapshot = self._operator.get_snapshot()
        described = describe_assist_preview(snapshot, action["kind"], args)
        return {"ok": True, "label": described["label"], "resulting": described["resulting"], "error": None}

    def finalize_assist(self, action: Any, expected_revision: Any = None) -> dict[str, Any]:
        """Submit exactly one ordinary command for ``action``, or refuse it.

        The only method on this bridge that reaches ``operator.command``.
        Every accepted action is tagged ``source="field-assistant"``, so its
        history row is attributable exactly like football's
        ``set_assistant_direction`` (``host/bridge.py``).
        """

        try:
            name, args = map_assist_action(action)
        except SoccerFieldAssistantError as exc:
            return {
                "accepted": False,
                "error": {"code": "ASSIST_ACTION_NOT_ALLOWED", "message": str(exc)},
            }
        return self._operator.command(name, args, expected_revision, source="field-assistant")
