"""Soccer's narrow JavaScript-to-Python boundary. Mirrors ``host/bridge.py``'s
``ScoreboardBridge``/``spectator_view_model``/``operator_view_model`` (spec
sections 2.2/3.3; signatures per ``.scratch/soccer-mode/api_domain.md``).

``SoccerBridge`` is a parallel class, not a subclass of ``ScoreboardBridge``:
every view builder in football's bridge reads football-shaped state (down,
distance, possession, timeouts), and the command airlock is football's own
``CommandType``. There is nothing left to inherit once ``command()`` and
every view-model helper are soccer's own. What *is* reused, by composition
and plain import -- never by touching ``host/bridge.py``, which is frozen
(spec 2.4) -- is everything in it that carries no football-shaped state at
all: ``DisplayLink``, ``DisplayStatus``, ``SpectatorBridge``, ``_json_safe``,
``_open_in_explorer``, plus ``host/teams.py``'s ``TeamPresets`` and
``host/layout_bridge.py``'s ``PresentationLayouts``.

Every string here is produced in Python from
:mod:`scoreboard.domain.soccer.formatting`, on the same "JavaScript never
derives a displayed value" principle football's bridge follows.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Final

from scoreboard.application.soccer_service import SoccerService
from scoreboard.domain.soccer.commands import (
    SoccerCommand,
    SoccerCommandError,
    SoccerCommandResult,
    SoccerUndoEntry,
    build_soccer_command,
)
from scoreboard.domain.soccer.formatting import (
    PERIOD_DISPLAY,
    format_cards,
    format_period,
    format_period_short,
    format_shootout_dots,
    format_stat,
)
from scoreboard.domain.soccer.rules import (
    SOCCER_RULE_FIELDS,
    RulesError,
    SoccerRules,
    default_soccer_rules,
    soccer_rules_to_mapping,
)
from scoreboard.presentation.soccer_layout import SOCCER_FINAL_HIDDEN_WIDGET_IDS
from scoreboard.domain.soccer.shootout import (
    current_round,
    in_sudden_death,
    is_decided,
    next_kicker,
    winner as derived_winner,
)
from scoreboard.domain.soccer.state import (
    DEFAULT_AWAY_NAME,
    DEFAULT_HOME_NAME,
    PERIOD_LABELS,
    SOCCER_SCHEMA_VERSION,
    SOCCER_STATUS_LABELS,
    SoccerState,
)
from scoreboard.domain.formatting import format_game_clock, format_game_status, format_status_clock
from scoreboard.host.bridge import (
    DisplayLink,
    DisplayStatus,
    _json_safe,
    _open_in_explorer,
)
from scoreboard.host.folders import FolderChoice, choose_data_folder, use_default_folder
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.host.teams import TeamPresets
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import describe_resolution
from scoreboard.infrastructure.soccer_store import SoccerGameStore

#: Mirrors football's operator-input source constants (host/bridge.py).
OPERATOR_MOUSE_SOURCE: Final[str] = "operator-mouse"
OPERATOR_KEYBOARD_SOURCE: Final[str] = "operator-keyboard"
FIELD_ASSISTANT_SOURCE: Final[str] = "field-assistant"
BUTTON_BOX_SOURCE: Final[str] = "button-box"

INVALID_ARGUMENTS: Final[str] = "INVALID_ARGUMENTS"
INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"
_INTERNAL_ERROR_MESSAGE: Final[str] = (
    "That control failed unexpectedly and changed nothing. The game is still "
    "running; see the diagnostics log."
)

#: A soccer game never leaves PRE_GAME before kickoff (mirrors football's
#: ``domain.commands.PREGAME_LIFECYCLES``, which this module does not import
#: because it is keyed to football's own lifecycle values -- they happen to
#: share this one literal).
PREGAME_LIFECYCLES: Final[tuple[str, ...]] = ("PRE_GAME",)

#: What the operator's game-clock card is called outside ordinary play (spec
#: 3.3), mirroring football's ``GAME_CLOCK_LABELS``.
GAME_CLOCK_LABELS: Final[dict[str, str]] = {
    "PRE": "KICKOFF COUNTDOWN",
    "HALF": "HALFTIME COUNTDOWN",
}

#: Periods during which the game clock counts an interval rather than play.
_INTERVAL_PERIODS: Final[tuple[str, ...]] = ("PRE", "HALF")

#: The stat fields, in the order the panel shows them (spec 4.1).
_STAT_NAMES: Final[tuple[str, ...]] = ("shots", "saves", "corners", "fouls")


def _clock_view(seconds: float, running: bool, display: str) -> dict[str, Any]:
    return {
        "seconds": seconds,
        "running": running,
        "display": display,
        "status": "RUNNING" if running else "STOPPED",
    }


def _stats_view(state: SoccerState, team: str) -> dict[str, Any]:
    view: dict[str, Any] = {}
    for name in _STAT_NAMES:
        value = getattr(state, f"{team}_{name}")
        view[name] = value
        view[f"{name}_display"] = format_stat(name, value)
    yellow = getattr(state, f"{team}_yellow")
    red = getattr(state, f"{team}_red")
    rows = [
        {
            # The index into ``state.cards`` that ``remove_card`` takes.
            "index": index,
            "team": card.team,
            "kind": card.kind,
            "player_number": card.player_number,
            "period": card.period,
            "clock_display": card.clock_display,
            "display": (
                f"#{card.player_number} · {card.clock_display} · "
                f"{format_period_short(card.period)}"
            ),
        }
        for index, card in enumerate(state.cards)
        if card.team == team
    ]
    view["cards"] = {
        "yellow": yellow,
        "red": red,
        "display": format_cards(yellow, red),
        "yellow_display": "" if yellow == 0 else f"Y {yellow}",
        "red_display": "" if red == 0 else f"R {red}",
        "rows": rows,
    }
    return view


def _shootout_view(state: SoccerState, rules: SoccerRules) -> dict[str, Any]:
    kicks = state.shootout_kicks
    initial = rules.shootout_initial_kickers
    active = state.period == "SHOOTOUT"
    next_team = None
    if active and state.shootout_winner is None:
        next_team = next_kicker(kicks, state.shootout_first_kicker, initial)
    decided = is_decided(kicks, initial)
    return {
        "active": active,
        "first_kicker": state.shootout_first_kicker,
        "winner": state.shootout_winner,
        # Derived before ``finish_shootout`` records it: the page enables
        # FINISH SHOOTOUT only when ``decided`` and sends ``derived_winner``.
        "decided": decided,
        "derived_winner": derived_winner(kicks, initial) if decided else None,
        # Every kick with its index, for Corrections (``shootout_correct_kick``).
        "kicks": [
            {
                "index": index,
                "team": kick.team,
                "round": kick.round,
                "kicker_number": kick.kicker_number,
                "made": kick.made,
                "display": (
                    f"{index + 1}. {kick.team.upper()}"
                    + (f" #{kick.kicker_number}" if kick.kicker_number is not None else "")
                    + (" made" if kick.made else " missed")
                ),
            }
            for index, kick in enumerate(kicks)
        ],
        "round": current_round(kicks, initial),
        "sudden_death": in_sudden_death(kicks, initial),
        "next_team": next_team,
        "home_display": format_shootout_dots(kicks, "home"),
        "away_display": format_shootout_dots(kicks, "away"),
        "home_made": state.shootout_home_made,
        "away_made": state.shootout_away_made,
        "tally_display": f"{state.shootout_home_made}-{state.shootout_away_made}",
    }


def _status_view(state: SoccerState) -> dict[str, Any]:
    clock_display = format_status_clock(
        state.status_clock.seconds, blank_at_zero=state.status_clock_cleared
    )
    return {
        "label": state.game_status,
        "active": state.game_status is not None,
        "display": format_game_status(state.game_status),
        "clock_display": clock_display,
        "clock": _clock_view(state.status_clock.seconds, state.status_clock.running, clock_display),
    }


def soccer_spectator_view_model(
    state: SoccerState, *, rules: SoccerRules | None = None
) -> dict[str, Any]:
    """Everything the soccer spectator window renders (spec 3.3, 5)."""

    from scoreboard.domain.soccer.clocks import event_phase_for
    from scoreboard.domain.state import ClockValue

    active_rules = default_soccer_rules() if rules is None else rules
    interval = state.period in _INTERVAL_PERIODS
    event_value = state.game_clock if interval else ClockValue(
        0.0, False, state.game_clock.maximum_seconds
    )
    countdown_phase = "PREGAME" if state.period == "PRE" else event_phase_for(
        "HALFTIME", event_value.seconds, warmup_threshold=active_rules.warmup_seconds
    )
    final = state.period == "FINAL" or state.lifecycle == "FINAL"
    shootout = state.period == "SHOOTOUT"
    # board.js hides literal widget ids (the same mechanism as football's
    # FINAL_HIDDEN_WIDGET_IDS): the clock disappears on FINAL and during the
    # shootout, which has no clock.
    hidden_widgets: list[str] = (
        list(SOCCER_FINAL_HIDDEN_WIDGET_IDS) if (final or shootout) else []
    )
    return {
        "schema_version": SOCCER_SCHEMA_VERSION,
        "revision": state.revision,
        "teams": {
            "home": {"name": state.home_name, "score": state.home_score},
            "away": {"name": state.away_name, "score": state.away_score},
        },
        "period": state.period,
        "period_display": format_period(state.period),
        "period_display_short": format_period_short(state.period),
        "lifecycle": state.lifecycle,
        "clocks": {
            "game": {
                **_clock_view(
                    state.game_clock.seconds,
                    state.game_clock.running,
                    format_game_clock(state.game_clock.seconds),
                ),
                "maximum_seconds": state.game_clock.maximum_seconds,
                "full_display": format_game_clock(state.game_clock.maximum_seconds),
                "label": GAME_CLOCK_LABELS.get(state.period, "GAME CLOCK"),
            },
            "event": {
                **_clock_view(
                    event_value.seconds,
                    event_value.running,
                    format_game_clock(event_value.seconds),
                ),
                "phase": countdown_phase,
                "title": "KICKOFF IN" if countdown_phase == "PREGAME" else "UNTIL SECOND HALF",
            },
        },
        "soccer": {
            "home": _stats_view(state, "home"),
            "away": _stats_view(state, "away"),
            "shootout": _shootout_view(state, active_rules),
        },
        "status": _status_view(state),
        "board": {"hidden_widgets": hidden_widgets},
        "mercy_reached": False,  # overwritten by operator_view_model with the service's value
    }


def _soccer_rule_fields_view(rules: SoccerRules) -> list[dict[str, Any]]:
    fields = []
    for name, label, kind in SOCCER_RULE_FIELDS:
        if kind == "note":
            # api_domain.md: a "note" row carries no dataclass field at all.
            fields.append({"name": name, "label": label, "kind": kind, "value": None, "display": label})
            continue
        value = getattr(rules, name)
        entry: dict[str, Any] = {"name": name, "label": label, "kind": kind, "value": value}
        if kind == "clock":
            whole = int(value)
            entry["minutes"] = whole // 60
            entry["seconds"] = whole % 60
            entry["display"] = format_game_clock(value)
        elif kind == "toggle":
            entry["display"] = "On" if value else "Off"
        else:
            entry["display"] = str(value)
        fields.append(entry)
    return fields


def _setup_view(state: SoccerState) -> dict[str, Any]:
    pregame = state.lifecycle in PREGAME_LIFECYCLES
    home_pending = pregame and state.home_name == DEFAULT_HOME_NAME
    away_pending = pregame and state.away_name == DEFAULT_AWAY_NAME
    return {
        "teams_pending": home_pending or away_pending,
        "home_pending": home_pending,
        "away_pending": away_pending,
    }


_SOCCER_LAST_ACTION_SUBJECTS: Final[dict[str, str]] = {
    "period": "Period",
    "home_shots": "HOME shots", "away_shots": "AWAY shots",
    "home_saves": "HOME saves", "away_saves": "AWAY saves",
    "home_corners": "HOME corners", "away_corners": "AWAY corners",
    "home_fouls": "HOME fouls", "away_fouls": "AWAY fouls",
    "shootout_first_kicker": "First kicker",
}


def _last_action_view(entry: SoccerUndoEntry | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    if entry.field.endswith("_score"):
        subject = f"{(entry.team or '').upper()} score"
    elif entry.field in _SOCCER_LAST_ACTION_SUBJECTS:
        subject = _SOCCER_LAST_ACTION_SUBJECTS[entry.field]
    else:
        subject = entry.field.replace("_", " ").capitalize()
    return {
        "command": entry.command.value,
        "team": entry.team,
        "field": entry.field,
        "old_value": entry.old_value,
        "new_value": entry.new_value,
        "label": f"{subject} {entry.old_value} → {entry.new_value}",
    }


def soccer_operator_view_model(
    service: SoccerService,
    *,
    persistence: Any,
    display: DisplayStatus,
    now: float | None = None,
) -> dict[str, Any]:
    """Everything the soccer operator window renders (spec 3.3)."""

    state = service.materialized_state(now)
    model = soccer_spectator_view_model(state, rules=service.rules)
    model["period_labels"] = list(PERIOD_LABELS)
    model["rules"] = soccer_rules_to_mapping(service.rules)
    model["rule_fields"] = _soccer_rule_fields_view(service.rules)
    model["status_labels"] = list(SOCCER_STATUS_LABELS)
    model["status_clock_presets"] = [int(service.rules.weather_seconds)]
    model["last_action"] = _last_action_view(service.undo_entry)
    model["can_undo"] = service.undo_entry is not None
    model["undo_history"] = [_last_action_view(entry) for entry in service.undo_history]
    model["undo_depth"] = len(model["undo_history"])
    model["period_decision"] = service.period_decision()
    model["mercy_reached"] = service.mercy_reached
    model["setup"] = _setup_view(state)
    model["health"] = {
        "revision": state.revision,
        "display": display.to_dict(),
        "persistence": persistence.to_dict(),
    }
    return model


class SoccerFieldAssistantBridge:
    """Mirrors ``host/bridge.py``'s ``FieldAssistantBridge``, but soccer's
    assistant has no composite calculator (spec E): every action is one of
    ``get_snapshot``, ``preview_assist``, or ``finalize_assist``, each of
    which forwards to the operator bridge's ordinary ``command`` with the
    ``field-assistant`` source (spec section 6, "field assistant" contract).
    This class is a placeholder only used if agent G's own module is not yet
    importable; the real implementation lives in
    ``host/soccer_field_assistant.py``.
    """

    def __init__(self, operator: "SoccerBridge") -> None:
        self._operator = operator

    def get_snapshot(self) -> dict[str, Any]:
        return self._operator.get_snapshot()


class SoccerBridge:
    """The soccer operator's only path to authoritative state."""

    def __init__(
        self,
        service: SoccerService,
        store: SoccerGameStore,
        *,
        display: DisplayLink | None = None,
        diagnostics: Diagnostics | None = None,
        lock: threading.RLock | None = None,
        on_accepted: Callable[[dict[str, Any]], None] | None = None,
        folder_chooser: Callable[[], FolderChoice] | None = None,
        layouts: PresentationLayouts | None = None,
        teams: TeamPresets | None = None,
        field_assistant_opener: Callable[[], dict[str, str]] | None = None,
        logs_opener: Callable[[Path], None] | None = None,
        cutscenes: Any = None,
        rules_writer: Callable[[SoccerRules], bool] | None = None,
    ) -> None:
        self._service = service
        self._store = store
        self._rules_writer = rules_writer
        self._display = DisplayLink() if display is None else display
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        self._layouts = layouts
        self._teams = teams
        self._field_assistant_opener = field_assistant_opener
        self._cutscenes = cutscenes
        self._cutscenes_opener: Callable[[], dict[str, str]] | None = None
        self._logs_opener = logs_opener or _open_in_explorer
        self._lock = threading.RLock() if lock is None else lock
        self._on_accepted = on_accepted
        self._folder_chooser = choose_data_folder if folder_chooser is None else folder_chooser
        self._button_box: dict[str, Any] | None = None

    # --- The JavaScript API --------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._view()

    def command(
        self,
        name: Any,
        args: Any = None,
        expected_revision: Any = None,
        *,
        source: str = OPERATOR_MOUSE_SOURCE,
    ) -> dict[str, Any]:
        """Submit one operator command and return its complete result.

        ``build_soccer_command`` (``domain.soccer.commands``) is the airlock:
        an unknown name or a disallowed argument never reaches the service.
        Mirrors ``ScoreboardBridge.command``'s lock discipline exactly (C4):
        ``on_accepted`` runs after the lock releases, so a stalled window can
        never hang the next command behind it.
        """

        # build_soccer_command's airlock does not tolerate an extra "source"
        # key inside args (unlike football's build_command, which filters it
        # out itself) -- see domain.soccer.commands.SOCCER_ALLOWED_ARGUMENTS.
        # A caller that tags the source inline (the button-box hook does)
        # still wins over the keyword default; it is simply pulled out first.
        claimed_source = source
        forwarded_args = args
        if isinstance(args, dict) and "source" in args:
            claimed_source = args["source"] if isinstance(args["source"], str) else source
            forwarded_args = {key: value for key, value in args.items() if key != "source"}

        accepted_view: dict[str, Any] | None = None
        with self._lock:
            built = build_soccer_command(name, forwarded_args, expected_revision, source=claimed_source)
            if isinstance(built, SoccerCommandError):
                self._diagnostics.command_rejected(
                    command=str(name), code=built.code, message=built.message,
                    source=claimed_source,
                )
                return self._result_payload(accepted=False, error=built)
            try:
                result = self._service.submit(built)
                self._store.record_command(built, result)
                if result.accepted:
                    accepted_view = self._view()
                payload = self._result_payload(
                    accepted=result.accepted,
                    error=result.error,
                    confirmation_required=result.confirmation_required,
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001 - reported, never left silent
                self._diagnostics.unhandled_error(context="command", error=exc, command=str(name))
                payload = self._result_payload(
                    accepted=False, error=SoccerCommandError(INTERNAL_ERROR, _INTERNAL_ERROR_MESSAGE),
                )
        if accepted_view is not None and self._on_accepted is not None:
            self._on_accepted(accepted_view)
        return payload

    # --- Host actions: folders, logs -----------------------------------------

    def choose_data_folder(self) -> dict[str, Any]:
        choice = self._folder_chooser()
        with self._lock:
            payload = choice.to_dict()
            self._diagnostics.data_folder_choice(outcome=choice.outcome, root=choice.root or "unchanged")
            payload["view"] = self._view()
            return payload

    def use_default_folder(self) -> dict[str, Any]:
        with self._lock:
            choice = use_default_folder()
            payload = choice.to_dict()
            self._diagnostics.data_folder_choice(outcome="default", root=choice.root or "unchanged")
            payload["view"] = self._view()
            return payload

    def data_folder(self) -> dict[str, Any]:
        with self._lock:
            return describe_resolution()

    def open_logs_folder(self) -> dict[str, Any]:
        log_file = self._diagnostics.log_file
        if log_file is None:
            payload: dict[str, Any] = {
                "opened": False, "path": None,
                "message": "There is no diagnostics log in this session.",
            }
        else:
            folder = Path(log_file).parent
            try:
                self._logs_opener(folder)
                payload = {"opened": True, "path": str(folder), "message": f"Opened the logs folder: {folder}"}
                self._diagnostics.note("logs_folder_opened", path=str(folder))
            except Exception as exc:  # noqa: BLE001 - reported, never raised
                payload = {"opened": False, "path": str(folder),
                           "message": f"Could not open the logs folder. It is at: {folder}"}
                self._diagnostics.unhandled_error(context="open_logs_folder", error=exc)
        with self._lock:
            payload["view"] = self._view()
            return payload

    # --- Presentation layout --------------------------------------------------

    def presentation_layout(self) -> dict[str, Any]:
        with self._lock:
            if self._layouts is None:
                return {
                    "schema_version": 1, "active": None, "names": [], "layout": None,
                    "widgets": [], "limits": {}, "issues": [], "fell_back": False,
                    "saved": True, "message": "The presentation layout is unavailable.",
                }
            return self._layouts.state()

    def open_layout_editor(self) -> dict[str, str]:
        with self._lock:
            if self._layouts is None:
                return {"message": "The presentation layout editor is unavailable."}
            try:
                return self._layouts.link.open_editor()
            except Exception as exc:  # noqa: BLE001 - an editor must never stop the game
                self._diagnostics.unhandled_error(context="open_layout_editor", error=exc)
                return {"message": f"The layout editor could not be opened: {exc}"}

    # --- Saved teams (shared teams.json, spec F4) -----------------------------

    def teams(self) -> dict[str, Any]:
        with self._lock:
            return self._teams_payload()

    def save_team(self, payload: Any) -> dict[str, Any]:
        if self._teams is None:
            with self._lock:
                return {**self._teams_payload(), "ok": False, "message": "Saved teams are unavailable in this build."}
        result = self._teams.save(payload)
        with self._lock:
            return {**self._teams_payload(), "ok": result["ok"], "message": result["message"]}

    def delete_team(self, name: Any) -> dict[str, Any]:
        if self._teams is None:
            with self._lock:
                return {**self._teams_payload(), "ok": False, "message": "Saved teams are unavailable in this build."}
        result = self._teams.delete(name)
        with self._lock:
            return {**self._teams_payload(), "ok": result["ok"], "message": result["message"]}

    def _teams_payload(self) -> dict[str, Any]:
        state = self._service.state
        if self._teams is None:
            return {"teams": [], "issues": [], "fell_back": False, "current": {"home": None, "away": None}}
        library = self._teams.state()
        return {
            "teams": library["teams"], "issues": library["issues"], "fell_back": library["fell_back"],
            "current": self._teams.identities(state.home_name, state.away_name),
        }

    def _with_identity(self, view: dict[str, Any]) -> dict[str, Any]:
        teams = view["teams"]
        if self._teams is None:
            identities = {"home": None, "away": None}
        else:
            identities = self._teams.identities(teams["home"]["name"], teams["away"]["name"])
        teams["home"]["identity"] = identities["home"]
        teams["away"]["identity"] = identities["away"]
        return view

    # --- Rules (Setup drawer) -------------------------------------------------

    def rules(self) -> dict[str, Any]:
        with self._lock:
            return self._rules_payload()

    def save_rules(self, payload: Any) -> dict[str, Any]:
        view: dict[str, Any] | None = None
        with self._lock:
            try:
                rules = SoccerRules.from_payload(payload)
            except RulesError as exc:
                self._diagnostics.command_rejected(
                    command="save_rules", code="INVALID_RULES", message=str(exc), source=OPERATOR_MOUSE_SOURCE,
                )
                return {"ok": False, "message": str(exc), **self._rules_payload()}
            self._service.set_rules(rules)
            saved = True
            if self._rules_writer is not None:
                try:
                    saved = bool(self._rules_writer(rules))
                except Exception as exc:  # noqa: BLE001 - reported, never left silent
                    self._diagnostics.unhandled_error(context="save_rules", error=exc, command="save_rules")
                    saved = False
            message = (
                "Rules saved. They apply the next time a period, a new game, is loaded."
                if saved else
                "Rules applied for this game but could not be saved to disk; "
                "they will return to the previous values at the next launch."
            )
            view = self._view()
            result = {"ok": True, "saved": saved, "message": message, **self._rules_payload()}
        if self._on_accepted is not None:
            self._on_accepted(view)
        return result

    def _rules_payload(self) -> dict[str, Any]:
        return {
            "rules": soccer_rules_to_mapping(self._service.rules),
            "defaults": soccer_rules_to_mapping(default_soccer_rules()),
            "fields": _soccer_rule_fields_view(self._service.rules),
            "default_fields": _soccer_rule_fields_view(default_soccer_rules()),
        }

    # --- Cutscenes --------------------------------------------------------------

    def set_field_assistant_opener(self, opener: Callable[[], dict[str, str]] | None) -> None:
        self._field_assistant_opener = opener

    def open_field_assistant(self) -> dict[str, str]:
        with self._lock:
            if self._field_assistant_opener is None:
                return {"message": "The Field Assistant window is unavailable."}
            try:
                return self._field_assistant_opener()
            except Exception as exc:  # noqa: BLE001 - helper failure is contained
                self._diagnostics.unhandled_error(context="open_field_assistant", error=exc)
                return {"message": f"The Field Assistant could not be opened: {exc}"}

    def set_cutscenes_opener(self, opener: Callable[[], dict[str, str]] | None) -> None:
        self._cutscenes_opener = opener

    def open_cutscenes(self) -> dict[str, str]:
        with self._lock:
            if self._cutscenes_opener is None:
                return {"message": "The Cutscenes window is unavailable."}
            try:
                return self._cutscenes_opener()
            except Exception as exc:  # noqa: BLE001 - helper failure is contained
                self._diagnostics.unhandled_error(context="open_cutscenes", error=exc)
                return {"message": f"The Cutscenes window could not be opened: {exc}"}

    def trigger_cutscene(self, event: Any, team: Any = None) -> dict[str, Any]:
        """Play one cutscene. Soccer's GOAL event needs the scoring ``team``
        (spec section 7): unlike football's penalty-only trigger, there is no
        single side the event alone decides.
        """

        if self._cutscenes is None:
            with self._lock:
                return {"ok": False, "message": "Cutscenes are unavailable.", "view": self._view()}
        try:
            result = dict(self._cutscenes.trigger(event, team))
        except Exception as exc:  # noqa: BLE001 - a cutscene must never stop the game
            self._diagnostics.unhandled_error(context="trigger_cutscene", error=exc)
            result = {"ok": False, "message": f"The cutscene could not be triggered: {exc}"}
        with self._lock:
            result["view"] = self._view()
        return result

    def cancel_cutscene(self) -> dict[str, Any]:
        if self._cutscenes is None:
            with self._lock:
                return {"ok": False, "message": "Cutscenes are unavailable.", "view": self._view()}
        try:
            result = dict(self._cutscenes.cancel())
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="cancel_cutscene", error=exc)
            result = {"ok": False, "message": f"The cutscene could not be cancelled: {exc}"}
        with self._lock:
            result["view"] = self._view()
        return result

    def _with_cutscenes(self, view: dict[str, Any]) -> dict[str, Any]:
        view["cutscenes"] = {
            "available": self._cutscenes is not None,
            "playing": None if self._cutscenes is None else self._cutscenes.status(),
        }
        return view

    # --- Display -----------------------------------------------------------------

    def reopen_display(self) -> dict[str, Any]:
        with self._lock:
            try:
                self._display.reopen()
            except Exception as exc:  # noqa: BLE001 - a display must never stop the game
                self._diagnostics.unhandled_error(context="reopen_display", error=exc)
                self._display.mark_closed(f"The display could not be reopened: {exc}")
            return self._view()

    def close_display(self) -> dict[str, Any]:
        with self._lock:
            try:
                self._display.close()
            except Exception as exc:  # noqa: BLE001
                self._diagnostics.unhandled_error(context="close_display", error=exc)
                self._display.mark_closed(f"The display could not be closed: {exc}")
            return self.displays()

    def open_test_window(self) -> dict[str, str]:
        with self._lock:
            return self._display.open_test_window()

    def displays(self) -> dict[str, Any]:
        with self._lock:
            try:
                payload = self._display.list_displays()
            except Exception as exc:  # noqa: BLE001 - enumeration must not end a game
                self._diagnostics.unhandled_error(context="list_displays", error=exc)
                payload = {"displays": [], "saved": None, "match": None,
                           "error": f"The displays could not be read: {exc}"}
            payload["status"] = self._display.status.to_dict()
            payload["view"] = self._view()
            return payload

    def select_display(self, key: Any) -> dict[str, Any]:
        with self._lock:
            try:
                self._display.select(key)
            except Exception as exc:  # noqa: BLE001
                self._diagnostics.unhandled_error(context="select_display", error=exc)
                self._display.mark_closed(f"That display could not be opened: {exc}", needs_selection=True)
            return self.displays()

    def forget_display(self) -> dict[str, Any]:
        with self._lock:
            try:
                self._display.forget()
            except Exception as exc:  # noqa: BLE001
                self._diagnostics.unhandled_error(context="forget_display", error=exc)
            return self.displays()

    # --- Host-side hooks -----------------------------------------------------

    def tick(self, now: float | None = None) -> dict[str, Any]:
        with self._lock:
            observation = self._service.observe_tick(now)
            state = observation.state
            try:
                self._store.checkpoint(state)
            except Exception as exc:  # noqa: BLE001 - saving must not stop a clock
                self._diagnostics.persistence_failure(operation="checkpoint", error=str(exc))
            return self._view(now)

    def display_opened(self, target: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._display.mark_open(target)
            self._diagnostics.display_opened(target=target or "unknown")
            return self._view()

    def display_closed(
        self, detail: str = "The spectator window is closed.", *, needs_selection: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            self._display.mark_closed(detail, needs_selection=needs_selection)
            self._diagnostics.display_closed(reason=detail)
            return self._view()

    def spectator_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._with_identity(
                soccer_spectator_view_model(self._service.materialized_state(), rules=self._service.rules)
            )

    def shutdown(self) -> dict[str, Any]:
        with self._lock:
            self._store.record_shutdown(self._service.materialized_state())
            return self._view()

    @property
    def service(self) -> SoccerService:
        return self._service

    @property
    def display(self) -> DisplayLink:
        return self._display

    # --- Internals -------------------------------------------------------------

    def _view(self, now: float | None = None) -> dict[str, Any]:
        return self._with_button_box(
            self._with_cutscenes(
                self._with_identity(
                    soccer_operator_view_model(
                        self._service, persistence=self._store.status, display=self._display.status, now=now,
                    )
                )
            )
        )

    def set_button_box_status(self, status: dict[str, Any] | None) -> None:
        with self._lock:
            self._button_box = None if status is None else dict(status)

    def _with_button_box(self, view: dict[str, Any]) -> dict[str, Any]:
        view["button_box"] = self._button_box
        return view

    def _result_payload(
        self,
        *,
        accepted: bool,
        error: SoccerCommandError | None,
        confirmation_required: bool = False,
        result: SoccerCommandResult | None = None,
    ) -> dict[str, Any]:
        return {
            "accepted": accepted,
            "confirmation_required": confirmation_required,
            "error": None if error is None else {"code": error.code, "message": error.message},
            "event": None if result is None or result.event is None else {
                "command": result.event.command.value,
                "field": result.event.field,
                "team": result.event.team,
                "old_value": result.event.old_value,
                "new_value": result.event.new_value,
            },
            "confirmation": None if result is None else result.confirmation,
            "view": self._view(),
        }


__all__ = [
    "BUTTON_BOX_SOURCE",
    "FIELD_ASSISTANT_SOURCE",
    "INTERNAL_ERROR",
    "INVALID_ARGUMENTS",
    "OPERATOR_KEYBOARD_SOURCE",
    "OPERATOR_MOUSE_SOURCE",
    "SoccerBridge",
    "SoccerFieldAssistantBridge",
    "soccer_operator_view_model",
    "soccer_spectator_view_model",
]
