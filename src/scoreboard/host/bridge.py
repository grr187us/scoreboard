"""The narrow JavaScript-to-Python boundary (ARCHITECTURE.md section 8).

The operator bridge exposes deliberately few methods:

* ``command(name, args, expected_revision)`` -- build a
  :class:`~scoreboard.domain.commands.Command`, submit it to
  :class:`~scoreboard.application.service.ScoreboardService`, persist the
  result through Task 6, and return a JSON-compatible dictionary;
* ``get_snapshot()`` -- return the same dictionary without changing anything;
* ``reopen_display()`` -- ask the host to recreate the spectator window, which
  changes no game state (D-005);
* ``displays()``, ``select_display(key)``, and ``forget_display()`` -- report
  which displays exist and put the spectator window on one of them (Task 10);
* ``open_test_window()`` -- open a small practice-only spectator preview,
  without changing production-display health or preference;
* ``data_folder()``, ``choose_data_folder()``, and ``use_default_folder()`` --
  report and change where the game and its logs are saved;
* ``presentation_layout()`` and ``open_layout_editor()`` -- report the active
  spectator layout and open the layout editor window;
* ``open_logs_folder()`` -- show the diagnostics log folder in Explorer so a
  bad game can be reported. It never reads or sends the file.

Every group above is a host action, not a game command. Each advances no
revision, writes nothing to the game database, and is asserted to leave a
running clock running: a display, a folder, and a spectator layout are all
something about this laptop or this presentation, not something that happened
in the football game.

The spectator bridge exposes ``get_snapshot()``, an optional ``get_layout()``,
and nothing that mutates.

No domain object crosses this boundary. Every value returned here is a
``str``, ``int``, ``float``, ``bool``, ``None``, ``list``, or ``dict``, so the
payload survives the webview's JSON transport unchanged.

JavaScript stores only ephemeral view state -- an open drawer, focus, unsent
form text. It never computes a score, a clock, or a revision: it renders the
view model it is given. Every displayed clock string is produced here by
:mod:`scoreboard.domain.formatting`, so the operator readout and the persisted
checkpoint can never disagree about what is on the board.
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable, Final

from scoreboard.application.service import ScoreboardService
from scoreboard.domain.clocks import SELECTABLE_EVENT_PHASES, event_phase_for
from scoreboard.domain.commands import (
    Command,
    CommandError,
    CommandResult,
    CommandType,
    UndoEntry,
    FieldAction,
    finalize_field_action,
    validate_command,
)
from scoreboard.domain.field_assistant import absolute_from_ball_spot, home_goal_side
from scoreboard.domain.formatting import (
    BLANK_DISPLAY,
    FormattingError,
    format_ball_on,
    format_distance,
    format_down,
    format_down_and_distance,
    format_event_countdown,
    format_game_clock,
    format_game_status,
    format_play_clock,
    format_possession,
    format_status_clock,
    format_timeouts,
)
from scoreboard.domain.state import (
    GAME_STATUS_LABELS,
    BallSpot,
    GameState,
    QUARTER_LABELS,
    SCHEMA_VERSION,
)
from scoreboard.host.cutscenes import CutsceneDirector
from scoreboard.host.folders import (
    FolderChoice,
    choose_data_folder,
    use_default_folder,
)
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.host.teams import TeamPresets
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import describe_resolution
from scoreboard.infrastructure.persistence import GameStore, PersistenceStatus
from scoreboard.presentation.layout import default_layout

#: The two local input adapters share every command and retain their source.
OPERATOR_MOUSE_SOURCE: Final[str] = "operator-mouse"
OPERATOR_KEYBOARD_SOURCE: Final[str] = "operator-keyboard"

#: Returned when JavaScript asks for something that is not a command at all.
#: This never reaches the service: an unknown name is not a game event.
UNKNOWN_COMMAND: Final[str] = "UNKNOWN_COMMAND"
INVALID_ARGUMENTS: Final[str] = "INVALID_ARGUMENTS"

#: A catch-all rejection for an exception the command path did not expect
#: (C4). Nothing here is a validated command-rejection reason; it exists so an
#: unforeseen bug fails safely -- the operator sees a plain refusal and a
#: complete view instead of the page hanging on a broken promise, and the
#: diagnostics log carries the real exception for later triage.
INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"

#: The message shown for :data:`INTERNAL_ERROR`, identical for ``command()``
#: and ``finalize_field_action()`` so the two catch-alls read as one contract.
_INTERNAL_ERROR_MESSAGE: Final[str] = (
    "That control failed unexpectedly and changed nothing. The game is still "
    "running; see the diagnostics log."
)

#: The arguments each command accepts from a view. Anything else is refused
#: before a Command is built, so a typo in JavaScript cannot become a mutation.
_ALLOWED_ARGUMENTS: Final[dict[CommandType, frozenset[str]]] = {
    CommandType.SET_TEAM_NAME: frozenset({"team", "name"}),
    CommandType.ADD_SCORE: frozenset({"team", "points"}),
    CommandType.CORRECT_SCORE: frozenset({"team", "points"}),
    CommandType.SET_SCORE: frozenset({"team", "value"}),
    CommandType.UNDO: frozenset(),
    CommandType.QUARTER_FORWARD: frozenset(),
    CommandType.QUARTER_BACK: frozenset(),
    CommandType.SET_QUARTER: frozenset({"label"}),
    CommandType.NEW_GAME: frozenset(),
    CommandType.END_GAME: frozenset(),
    CommandType.GAME_CLOCK_START: frozenset(),
    CommandType.GAME_CLOCK_STOP: frozenset(),
    CommandType.GAME_CLOCK_RESET: frozenset(),
    CommandType.GAME_CLOCK_CORRECT: frozenset({"seconds"}),
    CommandType.PLAY_CLOCK_PRESET: frozenset({"seconds"}),
    CommandType.PLAY_CLOCK_PRESET_START: frozenset({"seconds"}),
    CommandType.PLAY_CLOCK_START: frozenset(),
    CommandType.PLAY_CLOCK_STOP: frozenset(),
    CommandType.PLAY_CLOCK_CLEAR: frozenset(),
    CommandType.PLAY_CLOCK_RESET: frozenset(),
    CommandType.PLAY_CLOCK_CORRECT: frozenset({"seconds"}),
    CommandType.EVENT_COUNTDOWN_SELECT: frozenset({"label"}),
    CommandType.EVENT_COUNTDOWN_START: frozenset(),
    CommandType.EVENT_COUNTDOWN_STOP: frozenset(),
    CommandType.EVENT_COUNTDOWN_RESET: frozenset(),
    CommandType.EVENT_COUNTDOWN_CORRECT: frozenset({"seconds"}),
    CommandType.SET_DOWN: frozenset({"value"}),
    CommandType.SET_DISTANCE: frozenset({"value"}),
    CommandType.SET_POSSESSION: frozenset({"team"}),
    CommandType.SET_BALL_ON: frozenset({"team", "value"}),
    CommandType.TIMEOUT_USED: frozenset({"team"}),
    CommandType.TIMEOUT_CORRECT: frozenset({"team", "points"}),
    CommandType.SET_TIMEOUTS: frozenset({"team", "value"}),
    CommandType.SET_GAME_STATUS: frozenset({"label", "seconds"}),
    CommandType.CLEAR_GAME_STATUS: frozenset(),
    CommandType.STATUS_CLOCK_START: frozenset(),
    CommandType.STATUS_CLOCK_STOP: frozenset(),
}

_NUMERIC_ARGUMENTS: Final[frozenset[str]] = frozenset({"points", "value", "seconds"})
_TEXT_ARGUMENTS: Final[frozenset[str]] = frozenset({"team", "label", "name"})

#: Down and distance are the only numeric arguments a control may explicitly
#: clear to "not applicable" by sending ``value: null`` (an operator button
#: sends this deliberately; it never arrives as a stray empty field, which
#: :func:`build_command` still rejects the same way it always has).
_NULLABLE_VALUE_COMMANDS: Final[frozenset[CommandType]] = frozenset(
    {CommandType.SET_DOWN, CommandType.SET_DISTANCE}
)
#: Possession is the only team argument a control may clear to "nobody".
_NULLABLE_TEAM_COMMANDS: Final[frozenset[CommandType]] = frozenset(
    {CommandType.SET_POSSESSION}
)


# --- Display health ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DisplayStatus:
    """What the health strip says about the spectator window (U-005, D-005)."""

    open: bool
    target: str | None = None
    detail: str | None = None
    #: True when there is no display to reopen onto, so one click cannot fix
    #: this and the operator has to pick one (D-002, UX section 6.8).
    needs_selection: bool = False

    @property
    def label(self) -> str:
        if self.open:
            return "DISPLAY OPEN"
        return "DISPLAY NOT FOUND" if self.needs_selection else "DISPLAY CLOSED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": self.open,
            "label": self.label,
            "target": self.target,
            "detail": self.detail,
            # A closed display is recoverable in one click and never stops a
            # clock or closes the operator (D-005).
            "can_reopen": not self.open,
            "needs_selection": self.needs_selection,
        }


class DisplayLink:
    """The host's spectator window, as the bridge needs to see it.

    Keeping this tiny means the bridge can be tested without a webview, and a
    spectator rendering failure has no path to the state engine (R-002).

    The four hooks below are replaced by :class:`~scoreboard.host.app.WindowHost`
    at wiring time. On their own they open, move, and forget nothing, which is
    what lets every display test run on a machine with one screen.
    """

    def __init__(self) -> None:
        self._status = DisplayStatus(open=False, detail="Not opened yet.")

    @property
    def status(self) -> DisplayStatus:
        return self._status

    def mark_open(self, target: str | None = None) -> DisplayStatus:
        self._status = DisplayStatus(open=True, target=target)
        return self._status

    def mark_closed(
        self,
        detail: str = "The spectator window is closed.",
        *,
        needs_selection: bool = False,
    ) -> DisplayStatus:
        self._status = DisplayStatus(
            open=False,
            target=self._status.target,
            detail=detail,
            needs_selection=needs_selection,
        )
        return self._status

    def reopen(self) -> DisplayStatus:
        """Overridden by the host. On its own this link opens no window."""

        return self._status

    def list_displays(self) -> dict[str, Any]:
        """Overridden by the host. On its own this link enumerates nothing."""

        return {
            "displays": [],
            "saved": None,
            "match": None,
            "status": self._status.to_dict(),
        }

    def select(self, key: Any) -> DisplayStatus:
        """Overridden by the host. On its own this link chooses nothing."""

        return self._status

    def forget(self) -> DisplayStatus:
        """Overridden by the host. On its own this link forgets nothing."""

        return self._status

    def open_test_window(self) -> dict[str, str]:
        """Overridden by the host. On its own this opens no practice window."""

        return {"message": "The test window is unavailable."}


# --- Command translation ----------------------------------------------------


def build_command(
    name: Any,
    args: Any = None,
    expected_revision: Any = None,
    *,
    source: str = OPERATOR_MOUSE_SOURCE,
    confirmed: bool = False,
) -> Command | CommandError:
    """Translate a JSON request into a validated ``Command``.

    This is the airlock. A name that is not a command, an argument a command
    does not take, or a value of the wrong type is refused here and never
    reaches the service, so JavaScript cannot invent a mutation.
    """

    if not isinstance(name, str):
        return CommandError(UNKNOWN_COMMAND, "A command name must be text.")
    try:
        command_type = CommandType(name)
    except ValueError:
        return CommandError(UNKNOWN_COMMAND, f"{name!r} is not a control on this board.")

    if args is None:
        args = {}
    if not isinstance(args, dict):
        return CommandError(INVALID_ARGUMENTS, "Command arguments must be a dictionary.")

    allowed = _ALLOWED_ARGUMENTS[command_type]
    source = args.get("source", source)
    if source not in (OPERATOR_MOUSE_SOURCE, OPERATOR_KEYBOARD_SOURCE):
        return CommandError(INVALID_ARGUMENTS, "Unknown operator input source.")
    supplied = {key: value for key, value in args.items() if key not in ("confirmed", "source")}
    unexpected = set(supplied) - allowed
    if unexpected:
        return CommandError(
            INVALID_ARGUMENTS,
            f"{name} does not take {', '.join(sorted(unexpected))}.",
        )

    fields: dict[str, Any] = {}
    for key, value in supplied.items():
        if value is None and (
            (key == "value" and command_type in _NULLABLE_VALUE_COMMANDS)
            or (key == "team" and command_type in _NULLABLE_TEAM_COMMANDS)
        ):
            # An explicit "clear this" control, not a malformed field: down,
            # distance, and possession are the only arguments any command may
            # send as null, and only for the command types declared above.
            fields[key] = None
        elif key in _NUMERIC_ARGUMENTS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return CommandError(
                    INVALID_ARGUMENTS,
                    f"Enter a number for {key}." if value is None
                    else f"{key} must be a number; got {value!r}.",
                )
            numeric = float(value)
            # An empty or malformed field can arrive as NaN or an infinity.
            # Refuse it here: it is not a number, and it would not survive JSON.
            if numeric != numeric or numeric in (float("inf"), float("-inf")):
                return CommandError(INVALID_ARGUMENTS, f"Enter a whole number for {key}.")
            if key in ("points", "value"):
                if numeric != int(numeric):
                    return CommandError(
                        INVALID_ARGUMENTS, f"{key} must be a whole number; got {value!r}."
                    )
                fields[key] = int(numeric)
            else:
                fields[key] = numeric
        elif key in _TEXT_ARGUMENTS:
            if not isinstance(value, str):
                return CommandError(
                    INVALID_ARGUMENTS, f"{key} must be text; got {value!r}."
                )
            fields[key] = value
        else:  # pragma: no cover - _ALLOWED_ARGUMENTS covers every key
            return CommandError(INVALID_ARGUMENTS, f"{key} is not a supported argument.")

    requested_confirmation = args.get("confirmed", confirmed)
    if not isinstance(requested_confirmation, bool):
        return CommandError(INVALID_ARGUMENTS, "Confirmation must be true or false.")

    if expected_revision is not None:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            return CommandError(
                INVALID_ARGUMENTS, "The expected revision must be a whole number."
            )

    command = Command(
        type=command_type,
        confirmed=requested_confirmation,
        source=source,
        expected_revision=expected_revision,
        **fields,
    )
    shape_error = validate_command(command)
    if shape_error is not None:
        return shape_error
    return command


# --- View model -------------------------------------------------------------


def _clock_view(seconds: float, running: bool, display: str) -> dict[str, Any]:
    return {
        "seconds": seconds,
        "running": running,
        "display": display,
        # Text, not colour: the operator must be able to read the state
        # (UX_AND_LAYOUT.md section 2, U-002).
        "status": "RUNNING" if running else "STOPPED",
    }


def _spectator_quarter_label(label: str) -> str:
    """Expand only live-period labels; state keeps the compact football code."""

    return f"{label} Quarter" if label in {"1st", "2nd", "3rd", "4th"} else label


#: Human labels for the "LAST: ..." strip that ``entry.field.replace("_", " ")``
#: would otherwise render awkwardly (``"ball on"`` reads fine on its own, but
#: ``"home timeouts"``/``"away timeouts"`` already say the team, so the team
#: prefix _last_action_view adds for score fields must not double up).
_LAST_ACTION_SUBJECTS: Final[dict[str, str]] = {
    "down": "Down",
    "distance": "Distance",
    "possession": "Possession",
    "ball_on": "Ball on",
    "home_timeouts": "HOME timeouts",
    "away_timeouts": "AWAY timeouts",
}


def _last_action_display(value: Any) -> Any:
    """A JSON-compatible, human-readable rendering of one old/new value.

    Every other undoable field is already a plain ``str``/``int``/``None``
    that reads fine in ``f"{value}"``. ``BallSpot`` (``set_ball_on``) is the
    one compound value reaching here directly through the generic undo path,
    so it needs the same "readable, not a Python repr" treatment before it
    goes into the last-action label or crosses the JSON boundary.
    """

    if isinstance(value, BallSpot):
        return f"{value.team} {value.yard_line}"
    return value


def _field_assistant_label(entry: UndoEntry) -> str:
    """A one-line, human reading of a finalized Field Assistant action.

    The composite entry's old/new values are whole state groups (ball spot,
    possession, down, distance, both scores, the action payload, ...). Shown
    raw, as ``f"{old} → {new}"`` would, the strip became two Python dicts --
    unreadable at a glance during a game. This picks the parts an operator
    actually wants after pressing Confirm: what the assistant recorded (its
    own ``summary``), who scored and the resulting score when points changed,
    and the resulting situation (possession, down and distance, and the spot)
    when a live series follows. Every value is copied from the entry; nothing
    is recomputed, so this can never disagree with what the assistant did.
    """

    new = entry.new_value if isinstance(entry.new_value, dict) else {}
    summary = new.get("summary")
    parts = [str(summary) if summary else "Field action"]

    delta = new.get("score_delta") if isinstance(new.get("score_delta"), dict) else {}
    scoring_teams = [
        team.upper()
        for team in ("home", "away")
        if isinstance(delta.get(team), int) and not isinstance(delta.get(team), bool)
        and delta.get(team) > 0
    ]
    if scoring_teams:
        parts[0] = f"{parts[0]} for {' and '.join(scoring_teams)}"
        parts.append(f"HOME {new.get('home_score')} – AWAY {new.get('away_score')}")

    situation: list[str] = []
    possession = new.get("possession")
    if possession in ("home", "away"):
        situation.append(f"{possession.upper()} ball")
    try:
        down_and_distance = format_down_and_distance(new.get("down"), new.get("distance"))
    except FormattingError:
        down_and_distance = BLANK_DISPLAY
    if down_and_distance != BLANK_DISPLAY:
        situation.append(down_and_distance)
        # The spot only means something while a series is live: after a
        # score it is merely where the ball was, which would read as if the
        # next play starts there.
        spot = new.get("ball_on")
        if isinstance(spot, dict) and spot.get("team") in ("home", "away"):
            try:
                situation[-1] += " at " + format_ball_on(
                    spot["team"], spot.get("yard_line"), str(spot["team"]).upper()
                )
            except (FormattingError, TypeError):
                pass
    if situation:
        parts.append(", ".join(situation))
    return "Field assistant: " + " · ".join(parts)


def _last_action_view(entry: UndoEntry | None) -> dict[str, Any] | None:
    """The previous reversible command and whether Undo can reverse it (U-008)."""

    if entry is None:
        return None
    if entry.field == "field_assistant":
        return {
            "command": entry.command.value,
            "team": entry.team,
            "field": entry.field,
            "old_value": entry.old_value,
            "new_value": entry.new_value,
            "label": _field_assistant_label(entry),
        }
    if entry.field.endswith("_score"):
        subject = f"{(entry.team or '').upper()} score"
    elif entry.field == "quarter":
        subject = "Quarter"
    elif entry.field in _LAST_ACTION_SUBJECTS:
        subject = _LAST_ACTION_SUBJECTS[entry.field]
    else:
        subject = entry.field.replace("_", " ").capitalize()
    old_value = _last_action_display(entry.old_value)
    new_value = _last_action_display(entry.new_value)
    return {
        "command": entry.command.value,
        "team": entry.team,
        "field": entry.field,
        "old_value": old_value,
        "new_value": new_value,
        "label": f"{subject} {old_value} → {new_value}",
    }


def _football_view(state: GameState, *, home_name: str, away_name: str) -> dict[str, Any]:
    """Down/distance/possession/ball-on/timeouts, plus their rendered text.

    Every string here is produced in Python from
    :mod:`scoreboard.domain.formatting`, on the same "JavaScript never derives
    a displayed value" principle the clocks already follow: the operator
    readout and the spectator board cannot disagree about what a down-and-
    distance or a field position reads as.

    ``down_display``, ``distance_display``, ``possession_display``,
    ``home_timeouts_display``, and ``away_timeouts_display`` are the single-
    field renderings the presentation-layout widgets read (spec section 4.5).
    ``down_distance_display`` and ``ball_on_display`` are kept exactly as they
    were: the operator's field-status readout still combines them.
    """

    # Scoring transitions intentionally clear ordinary field status.  Keep
    # the legacy inert BallSpot out of this view in that case: showing an old
    # ball label beside "no possession" would make a completed score look
    # like a live scrimmage series.
    ball_on = state.ball_on
    team_name = (
        None if ball_on is None
        else home_name if ball_on.team == "home" else away_name
    )
    return {
        "down": state.down,
        "distance": state.distance,
        "down_distance_display": format_down_and_distance(state.down, state.distance),
        "down_display": format_down(state.down),
        "distance_display": format_distance(state.distance),
        "possession": state.possession,
        "possession_display": format_possession(state.possession),
        "ball_on": None if ball_on is None else {"team": ball_on.team, "yard_line": ball_on.yard_line},
        "ball_on_display": (
            "—" if ball_on is None
            else format_ball_on(ball_on.team, ball_on.yard_line, str(team_name))
        ),
        "timeouts": {"home": state.home_timeouts, "away": state.away_timeouts},
        "home_timeouts_display": format_timeouts(state.home_timeouts),
        "away_timeouts_display": format_timeouts(state.away_timeouts),
    }


def _status_view(state: GameState) -> dict[str, Any]:
    """F3's crowd-facing status word and its countdown -- one rendered string.

    ``clock_display`` is computed once and reused inside ``clock`` so the two
    can never disagree about what the countdown reads, exactly the same
    "compute once, copy everywhere" rule the rest of this module follows for
    clock text.
    """

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


def spectator_view_model(state: GameState) -> dict[str, Any]:
    """Everything the spectator window renders. It requests nothing else."""

    # PRE has one authoritative countdown: the game-clock engine. The event
    # engine remains the independent halftime interval timer.
    pregame = state.lifecycle == "PRE_GAME"
    event_value = state.game_clock if pregame else state.event_countdown
    countdown_phase = "PREGAME" if pregame else event_phase_for(
        state.event_phase, event_value.seconds
    )
    play_display = format_play_clock(
        state.play_clock.seconds,
        blank_at_zero=state.play_clock_cleared,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": state.revision,
        "teams": {
            "home": {"name": state.home_name, "score": state.home_score},
            "away": {"name": state.away_name, "score": state.away_score},
        },
        "quarter": state.quarter,
        # The saved/game-rule label remains compact (for example, ``2nd``),
        # while this spectator-only field carries the complete human wording.
        "quarter_display": _spectator_quarter_label(state.quarter),
        "lifecycle": state.lifecycle,
        "clocks": {
            "game": _clock_view(
                state.game_clock.seconds,
                state.game_clock.running,
                format_game_clock(state.game_clock.seconds),
            ),
            "play": _clock_view(
                state.play_clock.seconds,
                state.play_clock.running,
                # A cleared clock is visually distinct from a naturally
                # expired 0.0, but its label always remains on the board.
                play_display if play_display else "—",
            ),
            "event": {
                **_clock_view(
                    event_value.seconds,
                    event_value.running,
                    format_event_countdown(event_value.seconds),
                ),
                "phase": countdown_phase,
                "title": "KICKOFF IN" if countdown_phase == "PREGAME" else "UNTIL SECOND HALF",
                # Shown only during HALFTIME, per the confirmed presentation.
                "warmup_follows": "3:00" if countdown_phase == "HALFTIME" else None,
                # The pre-game/halftime layout screens (presentation-screens
                # spec section 1.2) bind a single warmup-line widget to this
                # field rather than composing "Warmup follows: " with
                # warmup_follows in JavaScript -- every game value is produced
                # in Python and merely copied by the renderer.
                "warmup_display": (
                    "Warmup follows: 3:00" if countdown_phase == "HALFTIME" else None
                ),
            },
        },
        # Meaningful only once a game is live; the spectator page hides this
        # alongside the game board during PRE_GAME/HALFTIME (D-001).
        "football": _football_view(
            state, home_name=state.home_name, away_name=state.away_name
        ),
        # F3: the crowd-facing status word and its countdown. ``display`` is
        # "" with nothing raised and ``clock_display`` is "" while the
        # countdown is cleared -- the two spectator widgets bound to these
        # dotted paths hide themselves on empty text (OPTIONAL_WIDGET_IDS),
        # which is how they stay off the wall until the operator raises one.
        "status": _status_view(state),
    }


def operator_view_model(
    service: ScoreboardService,
    *,
    persistence: PersistenceStatus,
    display: DisplayStatus,
    now: float | None = None,
) -> dict[str, Any]:
    """Everything the operator window renders, including health and last action."""

    state = service.materialized_state(now)
    model = spectator_view_model(state)
    model["quarter_labels"] = list(QUARTER_LABELS)
    model["event_phases"] = list(SELECTABLE_EVENT_PHASES)
    model["play_clock_presets"] = [25, 40]
    model["status_labels"] = list(GAME_STATUS_LABELS)
    model["status_clock_presets"] = [30, 60, 90]
    model["last_action"] = _last_action_view(service.undo_entry)
    model["can_undo"] = service.undo_entry is not None
    # I4: the whole reversible stack, newest first, each row already rendered
    # through the same _last_action_view the "LAST: ..." strip uses -- the
    # operator page copies these labels into its history drawer rather than
    # building one itself (ARCHITECTURE.md: Python owns every displayed
    # string). undo_depth is the badge next to "LAST:" (for example ``x3``);
    # it is simply the history's length rather than a separate counter, so
    # the two can never disagree.
    model["undo_history"] = [
        _last_action_view(entry) for entry in service.undo_history
    ]
    model["undo_depth"] = len(model["undo_history"])
    model["assistant"] = {
        "first_quarter_home_direction": state.assistant_first_quarter_home_direction,
        "line_to_gain": state.assistant_line_to_gain,
        "ball_absolute": (
            None if state.ball_on is None else absolute_from_ball_spot(state.ball_on)
        ),
        "home_goal_side": home_goal_side(
            state.assistant_first_quarter_home_direction, state.quarter
        ),
        "offense_direction": (
            1 if state.possession == "home"
            else -1 if state.possession == "away"
            else None
        ),
    }
    model["health"] = {
        "revision": state.revision,
        "display": display.to_dict(),
        "persistence": persistence.to_dict(),
    }
    return model


def _json_safe(value: Any) -> Any:
    """Turn a calculator dataclass into the bridge's JSON-only contract."""

    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


# --- Bridges ----------------------------------------------------------------


class SpectatorBridge:
    """Read-only. There is deliberately no method here that changes anything."""

    def __init__(
        self,
        read_snapshot: Callable[[], dict[str, Any]],
        read_layout: Callable[[], dict[str, Any]] | None = None,
        read_cutscene: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        self._read_snapshot = read_snapshot
        self._read_layout = read_layout
        self._read_cutscene = read_cutscene

    def get_snapshot(self) -> dict[str, Any]:
        return self._read_snapshot()

    def get_layout(self) -> dict[str, Any]:
        """The active presentation layout, or the built-in default.

        ``read_layout`` is optional so a caller that has no layout library yet
        -- a unit test, or an older host -- still returns a usable, valid
        layout rather than raising.
        """

        if self._read_layout is not None:
            return self._read_layout()
        return default_layout()

    def get_cutscene(self) -> dict[str, Any] | None:
        """The program currently playing, or ``None``. Read-only.

        ``read_cutscene`` is optional so a build with no cutscenes director --
        most bridge tests -- answers ``None`` rather than raising. A reopened
        spectator calls this once on load to join a cutscene already in
        progress (spec section 6.1).
        """

        if self._read_cutscene is None:
            return None
        return self._read_cutscene()


class FieldAssistantBridge:
    """The optional Field Assistant's deliberately small JSON API.

    It has no generic ``command`` endpoint.  A draft can only ask Python to
    preview one raw FieldAction or to submit that same action through the one
    composite command.  Closing this bridge/window therefore has no path to
    the game engine; reopening simply reads a fresh complete snapshot.
    """

    def __init__(self, operator: "ScoreboardBridge") -> None:
        self._operator = operator

    def get_snapshot(self) -> dict[str, Any]:
        return self._operator.get_snapshot()

    def preview_field_action(self, action: Any) -> dict[str, Any]:
        return self._operator.preview_field_action(action)

    def finalize_field_action(
        self, action: Any, expected_revision: Any = None
    ) -> dict[str, Any]:
        return self._operator.finalize_field_action(action, expected_revision)


def _open_in_explorer(folder: Path) -> None:
    """Show a folder in Windows Explorer. Returns at once; never reads it."""

    os.startfile(str(folder))  # noqa: S606 - a folder, chosen by this application


class ScoreboardBridge:
    """The operator's only path to authoritative state.

    Every control routes through :meth:`command`. The bridge submits to the
    service, persists the result through Task 6, and returns the complete view
    model so the page re-renders from authority even after a rejection.
    """

    def __init__(
        self,
        service: ScoreboardService,
        store: GameStore,
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
        cutscenes: CutsceneDirector | None = None,
    ) -> None:
        self._service = service
        self._store = store
        self._display = DisplayLink() if display is None else display
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        # Optional: many tests build a bridge with no layout library at all.
        # Both host actions below report plainly rather than raising when it
        # is absent, exactly like a display or a folder that is not there yet.
        self._layouts = layouts
        # Optional for the same reason. When present, every view carries each
        # side's saved identity (short name and colours) looked up by the
        # current team name; the lookup is an in-memory dict read (F4).
        self._teams = teams
        self._field_assistant_opener = field_assistant_opener
        # Optional, exactly like the layout library and the team presets:
        # many tests build a bridge with no director at all, and the three
        # host actions below answer plainly rather than raising when it is
        # absent (spec section 5.1).
        self._cutscenes = cutscenes
        self._cutscenes_opener: Callable[[], dict[str, str]] | None = None
        # Explorer by default; tests inject a recorder. `os.startfile` is
        # Windows-only, which is the only platform this application targets.
        self._logs_opener = logs_opener or _open_in_explorer
        # One lock serialises commands against the display-refresh tick, so a
        # checkpoint can never read a half-applied command.
        self._lock = threading.RLock() if lock is None else lock
        self._on_accepted = on_accepted
        # Injected so a test can exercise the operator's side of the picker
        # without a dialog appearing on someone's screen and waiting forever.
        self._folder_chooser = (
            choose_data_folder if folder_chooser is None else folder_chooser
        )
        # The previous tick's (revision, per-clock running/remaining), used to
        # notice a clock that ran itself down to zero. See _record_expirations.
        self._observed: tuple[int, dict[str, tuple[bool, float]]] | None = None

    # --- The JavaScript API ------------------------------------------------

    def get_snapshot(self) -> dict[str, Any]:
        """The current view model. Reads nothing into the game and changes nothing."""

        with self._lock:
            return self._view()

    def command(
        self,
        name: Any,
        args: Any = None,
        expected_revision: Any = None,
    ) -> dict[str, Any]:
        """Submit one operator command and return its complete result.

        The service submit, the durable record, and the returned payload are
        all built under the lock, exactly as before. What changed for C4 is
        *when* ``on_accepted`` runs: it is the caller's hook into publishing a
        new view to the windows, and publishing can end up at a webview's
        blocking ``evaluate_js`` (ARCHITECTURE.md §8). Calling it after this
        method's ``with`` block releases means a stalled window can never hang
        the next command or the refresh tick behind this lock. A bare
        exception anywhere in the submit/record/payload path is caught here,
        exactly like ``ScoreboardApplication.tick()`` already catches one
        around the refresh loop, so a bug in a sibling command can never leave
        the operator staring at a control that neither completed nor said why.
        """

        accepted_view: dict[str, Any] | None = None
        with self._lock:
            built = build_command(name, args, expected_revision)
            if isinstance(built, CommandError):
                # Refused before the service saw it: nothing changed, and there
                # is no accepted command to persist.
                # Report the source the view actually claimed, so a keyboard
                # rejection is not filed against the mouse (K-001).
                claimed = args.get("source") if isinstance(args, dict) else None
                self._diagnostics.command_rejected(
                    command=str(name), code=built.code, message=built.message,
                    source=claimed if isinstance(claimed, str) else OPERATOR_MOUSE_SOURCE,
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
                self._diagnostics.unhandled_error(
                    context="command", error=exc, command=str(name)
                )
                payload = self._result_payload(
                    accepted=False,
                    error=CommandError(INTERNAL_ERROR, _INTERNAL_ERROR_MESSAGE),
                )
        if accepted_view is not None and self._on_accepted is not None:
            self._on_accepted(accepted_view)
        return payload

    def preview_field_action(self, action: Any) -> dict[str, Any]:
        """Calculate one uncommitted assistant draft in Python.

        The service uses the identical pure calculator when it later handles
        ``finalize_field_action``.  The browser receives only a displayable
        result and never sends calculated down/distance/score values back.
        """

        with self._lock:
            built = self._field_action(action)
            if isinstance(built, CommandError):
                return {
                    "accepted": False,
                    "error": {"code": built.code, "message": built.message},
                    "preview": None,
                    "view": self._view(),
                }
            try:
                preview_result = self._service.preview_field_action(built)
            except Exception as exc:  # expected calculator failures stay visible
                return {
                    "accepted": False,
                    "error": {"code": "INVALID_FIELD_ACTION", "message": str(exc)},
                    "preview": None,
                    "view": self._view(),
                }
            if not preview_result.get("accepted"):
                return {
                    "accepted": False,
                    "error": preview_result.get("error"),
                    "preview": None,
                    # Service's raw persistence snapshot is intentionally not
                    # the webview contract; always return the complete,
                    # formatted bridge view instead.
                    "view": self._view(),
                }
            return {
                "accepted": True,
                "error": None,
                "preview": _json_safe(preview_result.get("preview")),
                "view": self._view(),
            }

    def finalize_field_action(
        self, action: Any, expected_revision: Any = None
    ) -> dict[str, Any]:
        """Persist exactly one composite Field Assistant command.

        This intentionally does not call the manual ``set_*`` commands.  The
        command object submitted here is also the single object recorded by
        the store, preserving one revision, transaction, and durable row.
        """

        accepted_view: dict[str, Any] | None = None
        with self._lock:
            built = self._field_action(action)
            if isinstance(built, CommandError):
                return self._result_payload(accepted=False, error=built)
            if expected_revision is not None and (
                isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
            ):
                return self._result_payload(
                    accepted=False,
                    error=CommandError(INVALID_ARGUMENTS, "The expected revision must be a whole number."),
                )
            try:
                command = finalize_field_action(
                    built,
                    expected_revision=expected_revision,
                    source="field-assistant",
                )
                result = self._service.submit(command)
                self._store.record_command(command, result)
                if result.accepted:
                    accepted_view = self._view()
                payload = self._result_payload(
                    accepted=result.accepted,
                    error=result.error,
                    confirmation_required=result.confirmation_required,
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001 - reported, never left silent
                self._diagnostics.unhandled_error(
                    context="finalize_field_action", error=exc, command="finalize_field_action"
                )
                payload = self._result_payload(
                    accepted=False,
                    error=CommandError(INTERNAL_ERROR, _INTERNAL_ERROR_MESSAGE),
                )
        if accepted_view is not None and self._on_accepted is not None:
            self._on_accepted(accepted_view)
        return payload

    @staticmethod
    def _field_action(value: Any) -> FieldAction | CommandError:
        """Validate the transport envelope without calculating football rules."""

        if not isinstance(value, dict):
            return CommandError(INVALID_ARGUMENTS, "Field Assistant action must be an object.")
        if set(value) != {"kind", "payload"}:
            return CommandError(
                INVALID_ARGUMENTS,
                "Field Assistant action must contain only kind and payload.",
            )
        try:
            return FieldAction(kind=value["kind"], payload=value["payload"])
        except (TypeError, ValueError) as exc:
            return CommandError(INVALID_ARGUMENTS, str(exc))

    def choose_data_folder(self) -> dict[str, Any]:
        """Open the folder picker and remember the answer for the next launch.

        Like :meth:`reopen_display`, this is a host action rather than a game
        command: it advances no revision, writes nothing to the database, and
        cannot be undone through the command history because there is nothing
        in the game to undo. The running game keeps saving where it already
        was, and the payload says so in words the operator can act on.
        """

        # The picker is a modal Windows dialog: this call does not return until
        # the operator chooses or cancels, which may be a while. It must run
        # OUTSIDE the command lock -- that lock is the same one every score,
        # clock, and quarter command and the refresh tick need, so holding it
        # here froze the whole board for as long as the dialog stayed open,
        # with the clocks visibly stuck while real time kept moving. Only the
        # bookkeeping afterwards needs the lock, and only briefly.
        choice = self._folder_chooser()
        with self._lock:
            payload = choice.to_dict()
            self._diagnostics.data_folder_choice(
                outcome=choice.outcome, root=choice.root or "unchanged"
            )
            payload["view"] = self._view()
            return payload

    def open_logs_folder(self) -> dict[str, Any]:
        """Show the diagnostics log folder, so a bad game can be reported.

        A host action like the folder picker: it advances no revision and
        touches nothing in the game. The application already keeps a bounded
        rotating log of every accepted command, expiry, display event, and
        failure, but until now nothing in the window pointed at it -- the only
        way to find it after a bad night was to know the path. Opening the
        folder in Explorer is deliberately all this does; it never reads or
        sends the file itself.
        """

        log_file = self._diagnostics.log_file
        if log_file is None:
            payload: dict[str, Any] = {
                "opened": False,
                "path": None,
                "message": "There is no diagnostics log in this session.",
            }
        else:
            folder = Path(log_file).parent
            try:
                self._logs_opener(folder)
                payload = {
                    "opened": True,
                    "path": str(folder),
                    "message": f"Opened the logs folder: {folder}",
                }
                self._diagnostics.note("logs_folder_opened", path=str(folder))
            except Exception as exc:  # noqa: BLE001 - reported to the operator, never raised
                payload = {
                    "opened": False,
                    "path": str(folder),
                    "message": f"Could not open the logs folder. It is at: {folder}",
                }
                self._diagnostics.unhandled_error(context="open_logs_folder", error=exc)
        with self._lock:
            payload["view"] = self._view()
            return payload

    def use_default_folder(self) -> dict[str, Any]:
        """Forget a chosen folder and return to the standard per-user location."""

        with self._lock:
            choice = use_default_folder()
            payload = choice.to_dict()
            self._diagnostics.data_folder_choice(
                outcome="default", root=choice.root or "unchanged"
            )
            payload["view"] = self._view()
            return payload

    def data_folder(self) -> dict[str, Any]:
        """Where the game is being saved, and why there (U-005)."""

        with self._lock:
            return describe_resolution()

    def presentation_layout(self) -> dict[str, Any]:
        """The active spectator layout and the library it came from (host action).

        Like :meth:`data_folder`, this is read on demand rather than carried in
        the 10 Hz view model: it advances no revision and writes nothing to the
        game database. A build with no layout library at all -- most bridge
        tests -- reports a plain, valid, empty-library payload rather than
        raising.
        """

        with self._lock:
            if self._layouts is None:
                return {
                    "schema_version": 1,
                    "active": None,
                    "names": [],
                    "layout": None,
                    "widgets": [],
                    "limits": {},
                    "issues": [],
                    "fell_back": False,
                    "saved": True,
                    "message": "The presentation layout is unavailable.",
                }
            return self._layouts.state()

    # --- Saved teams (F4) ---------------------------------------------------

    def teams(self) -> dict[str, Any]:
        """The saved-team library and each side's current identity.

        A host action like :meth:`presentation_layout`: read on demand, no
        revision, no command, nothing written to the game database. Applying
        a saved team is the ordinary ``set_team_name`` command, so it keeps
        the pregame-only rule, the confirmation, undo, and the history row.
        """

        with self._lock:
            return self._teams_payload()

    def save_team(self, payload: Any) -> dict[str, Any]:
        """Save or update one team preset in ``teams.json``. Changes no game value."""

        if self._teams is None:
            with self._lock:
                return {**self._teams_payload(), "ok": False,
                        "message": "Saved teams are unavailable in this build."}
        result = self._teams.save(payload)
        with self._lock:
            return {**self._teams_payload(), "ok": result["ok"], "message": result["message"]}

    def delete_team(self, name: Any) -> dict[str, Any]:
        """Delete one team preset from ``teams.json``. Changes no game value."""

        if self._teams is None:
            with self._lock:
                return {**self._teams_payload(), "ok": False,
                        "message": "Saved teams are unavailable in this build."}
        result = self._teams.delete(name)
        with self._lock:
            return {**self._teams_payload(), "ok": result["ok"], "message": result["message"]}

    def _teams_payload(self) -> dict[str, Any]:
        state = self._service.state
        if self._teams is None:
            return {"teams": [], "issues": [], "fell_back": False,
                    "current": {"home": None, "away": None}}
        library = self._teams.state()
        return {
            "teams": library["teams"],
            "issues": library["issues"],
            "fell_back": library["fell_back"],
            "current": self._teams.identities(state.home_name, state.away_name),
        }

    def _with_identity(self, view: dict[str, Any]) -> dict[str, Any]:
        """Attach each side's saved identity (or ``None``) to a view model."""

        teams = view["teams"]
        if self._teams is None:
            identities = {"home": None, "away": None}
        else:
            identities = self._teams.identities(teams["home"]["name"], teams["away"]["name"])
        teams["home"]["identity"] = identities["home"]
        teams["away"]["identity"] = identities["away"]
        return view

    def _with_cutscenes(self, view: dict[str, Any]) -> dict[str, Any]:
        """Attach the cutscenes badge to a view model (spec section 5.1).

        The 10 Hz refresh tick already delivers this to every window, so the
        Cutscenes window and the operator badge never compute a countdown
        themselves -- ``director.status()`` (or ``None``, idle or absent) is
        simply copied.
        """

        view["cutscenes"] = {
            "available": self._cutscenes is not None,
            "playing": None if self._cutscenes is None else self._cutscenes.status(),
        }
        return view

    def open_layout_editor(self) -> dict[str, str]:
        """Open the presentation layout editor window.

        This is a host action, like :meth:`open_test_window`: it advances no
        revision, writes nothing to the game database, and cannot be undone
        through the command history because it never touched it. A failure to
        open the window is reported and survived, exactly like
        :meth:`reopen_display` (R-002).
        """

        with self._lock:
            if self._layouts is None:
                return {"message": "The presentation layout editor is unavailable."}
            try:
                return self._layouts.link.open_editor()
            except Exception as exc:  # noqa: BLE001 - an editor must never stop the game
                self._diagnostics.unhandled_error(context="open_layout_editor", error=exc)
                return {"message": f"The layout editor could not be opened: {exc}"}

    def set_field_assistant_opener(
        self, opener: Callable[[], dict[str, str]] | None
    ) -> None:
        """Install the optional host-window hook after WindowHost is wired."""

        self._field_assistant_opener = opener

    def open_field_assistant(self) -> dict[str, str]:
        """Open the optional helper window without touching game state."""

        with self._lock:
            if self._field_assistant_opener is None:
                return {"message": "The Field Assistant window is unavailable."}
            try:
                return self._field_assistant_opener()
            except Exception as exc:  # noqa: BLE001 - helper failure is contained
                self._diagnostics.unhandled_error(context="open_field_assistant", error=exc)
                return {"message": f"The Field Assistant could not be opened: {exc}"}

    def set_cutscenes_opener(
        self, opener: Callable[[], dict[str, str]] | None
    ) -> None:
        """Install the optional host-window hook after WindowHost is wired."""

        self._cutscenes_opener = opener

    def open_cutscenes(self) -> dict[str, str]:
        """Open the optional Cutscenes window without touching game state.

        A host action like :meth:`open_field_assistant`: it advances no
        revision, submits no command, and writes no history row.
        """

        with self._lock:
            if self._cutscenes_opener is None:
                return {"message": "The Cutscenes window is unavailable."}
            try:
                return self._cutscenes_opener()
            except Exception as exc:  # noqa: BLE001 - helper failure is contained
                self._diagnostics.unhandled_error(context="open_cutscenes", error=exc)
                return {"message": f"The Cutscenes window could not be opened: {exc}"}

    def trigger_cutscene(self, event: Any, team: Any = None) -> dict[str, Any]:
        """Play one cutscene, or report unavailable. No revision, no history.

        Like every host action in this group, a failure is contained and
        reported rather than raised; the returned dict also carries the
        complete operator view so the badge re-renders at once, whichever
        window called this.
        """

        if self._cutscenes is None:
            with self._lock:
                return {
                    "ok": False,
                    "message": "Cutscenes are unavailable.",
                    "view": self._view(),
                }
        # The director is called *outside* the command lock on purpose: its
        # publish reaches a window's ``evaluate_js``, the one call that can
        # block without bound when WebView2 stalls (C4). Holding the lock
        # across it would put a stalled wall back in the path of every clock
        # and score command. The director is thread-safe on its own.
        try:
            result = dict(self._cutscenes.trigger(event, team))
        except Exception as exc:  # noqa: BLE001 - a cutscene must never stop the game
            self._diagnostics.unhandled_error(context="trigger_cutscene", error=exc)
            result = {"ok": False, "message": f"The cutscene could not be triggered: {exc}"}
        with self._lock:
            result["view"] = self._view()
        return result

    def cancel_cutscene(self) -> dict[str, Any]:
        """End whatever cutscene is playing. No revision, no history."""

        if self._cutscenes is None:
            with self._lock:
                return {
                    "ok": False,
                    "message": "Cutscenes are unavailable.",
                    "view": self._view(),
                }
        # Outside the command lock for the same C4 reason as trigger_cutscene.
        try:
            result = dict(self._cutscenes.cancel())
        except Exception as exc:  # noqa: BLE001
            self._diagnostics.unhandled_error(context="cancel_cutscene", error=exc)
            result = {"ok": False, "message": f"The cutscene could not be cancelled: {exc}"}
        with self._lock:
            result["view"] = self._view()
        return result

    def reopen_display(self) -> dict[str, Any]:
        """Recreate the spectator window. This changes no game state (D-005)."""

        with self._lock:
            try:
                self._display.reopen()
            except Exception as exc:  # noqa: BLE001 - a display must never stop the game
                # A spectator failure is reported and survived; the clocks and
                # the operator keep running (R-002).
                self._diagnostics.unhandled_error(context="reopen_display", error=exc)
                self._display.mark_closed(f"The display could not be reopened: {exc}")
            return self._view()

    def open_test_window(self) -> dict[str, str]:
        """Open a practice-only spectator preview without changing game state.

        This is a host action, like :meth:`reopen_display`: it has no revision,
        database, or action-history effect. Unlike reopening, it deliberately
        does not touch production-display health or its saved destination.
        """

        with self._lock:
            return self._display.open_test_window()

    def displays(self) -> dict[str, Any]:
        """Which displays exist, which one is saved, and how it matched.

        Read on demand rather than carried in the view model: enumerating
        screens is a Windows call, and the view model is rebuilt four times a
        second. Like every method in this group it is a host action -- it
        advances no revision and writes nothing to the database.
        """

        with self._lock:
            try:
                payload = self._display.list_displays()
            except Exception as exc:  # noqa: BLE001 - enumeration must not end a game
                self._diagnostics.unhandled_error(context="list_displays", error=exc)
                payload = {
                    "displays": [],
                    "saved": None,
                    "match": None,
                    "error": f"The displays could not be read: {exc}",
                }
            payload["status"] = self._display.status.to_dict()
            payload["view"] = self._view()
            return payload

    def select_display(self, key: Any) -> dict[str, Any]:
        """Put the spectator window on the chosen display and remember it.

        This is the only thing that re-points the saved display. A match found
        at startup refreshes what is stored about the *same* display; only an
        operator standing at the screen can make it a different one, which is
        what "no hidden auto-moves during live play" means in practice.
        """

        with self._lock:
            try:
                self._display.select(key)
            except Exception as exc:  # noqa: BLE001
                self._diagnostics.unhandled_error(context="select_display", error=exc)
                self._display.mark_closed(
                    f"That display could not be opened: {exc}", needs_selection=True
                )
            return self.displays()

    def forget_display(self) -> dict[str, Any]:
        """Forget the saved display without touching the window that is open.

        The spectator window showing the game right now keeps showing it. This
        only clears what the next launch will look for, exactly as **Use
        standard folder** does for the data folder.
        """

        with self._lock:
            try:
                self._display.forget()
            except Exception as exc:  # noqa: BLE001
                self._diagnostics.unhandled_error(context="forget_display", error=exc)
            return self.displays()

    # --- Host-side hooks ----------------------------------------------------

    def tick(self, now: float | None = None) -> dict[str, Any]:
        """Refresh the display and checkpoint a running clock (P-003).

        Called by the host's refresh loop. It never submits a command or
        advances a revision; natural expirations and their documented
        system-caused couplings are the only action-history records it writes.
        """

        with self._lock:
            observation = self._service.observe_tick(now)
            state = observation.state
            try:
                if observation.play_clock_cleared:
                    # Prefer the prior rendered values for the audit row, as
                    # _record_expirations does.  The service fallback covers a
                    # first refresh that happens only after the deadline.
                    game_from_seconds = observation.game_clock_from_seconds
                    play_from_seconds = observation.play_clock_from_seconds
                    if self._observed is not None and self._observed[0] == state.revision:
                        previous = self._observed[1]
                        game_was_running, previous_game_seconds = previous["game"]
                        play_was_running, previous_play_seconds = previous["play"]
                        if game_was_running and previous_game_seconds > 0.0:
                            game_from_seconds = previous_game_seconds
                        if play_was_running and previous_play_seconds > 0.0:
                            play_from_seconds = previous_play_seconds
                    self._store.record_game_clock_expiration_and_play_clock_clear(
                        state,
                        game_from_seconds=game_from_seconds,
                        play_from_seconds=play_from_seconds,
                    )
                    self._diagnostics.clock_expired(
                        clock="game", revision=state.revision
                    )
                    self._diagnostics.play_clock_cleared_on_game_clock_stop(
                        revision=state.revision,
                        reason="game_clock_expired",
                    )
                    self._record_expirations(state, skip={"game", "play"})
                else:
                    self._record_expirations(state)
                self._store.checkpoint(state)
            except Exception as exc:  # noqa: BLE001 - saving must not stop a clock
                self._diagnostics.persistence_failure(operation="checkpoint", error=str(exc))
            return self._view(now)

    def _record_expirations(self, state: GameState, *, skip: set[str] | None = None) -> None:
        """Write a history row for any clock that just counted down to zero.

        A clock reaching 0:00 is not an operator command, so nothing here
        submits one or advances a revision -- but F-037 and F-046 require the
        expiration in the durable history next to the start that preceded it.

        The revision is the discriminator. If it moved since the last tick, an
        accepted command produced the zero (a correction to 0:00, or a
        game-clock Start clearing the play clock), and that command already has
        its own history row. Only an unchanged revision means the clock got
        there on its own.
        """

        current = {
            "game": (state.game_clock.running, state.game_clock.seconds),
            "play": (state.play_clock.running, state.play_clock.seconds),
            "event": (state.event_countdown.running, state.event_countdown.seconds),
            "status": (state.status_clock.running, state.status_clock.seconds),
        }
        previous = self._observed
        self._observed = (state.revision, current)
        if previous is None or previous[0] != state.revision:
            return
        for clock, (running, seconds) in current.items():
            if skip is not None and clock in skip:
                continue
            was_running, was_seconds = previous[1][clock]
            if was_running and was_seconds > 0.0 and not running and seconds <= 0.0:
                self._store.record_expiration(clock, state, from_seconds=was_seconds)
                self._diagnostics.clock_expired(clock=clock, revision=state.revision)

    def display_opened(self, target: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._display.mark_open(target)
            self._diagnostics.display_opened(target=target or "unknown")
            return self._view()

    def display_closed(
        self,
        detail: str = "The spectator window is closed.",
        *,
        needs_selection: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            self._display.mark_closed(detail, needs_selection=needs_selection)
            self._diagnostics.display_closed(reason=detail)
            return self._view()

    def spectator_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._with_identity(
                spectator_view_model(self._service.materialized_state())
            )

    def shutdown(self) -> dict[str, Any]:
        """Save at clean shutdown and report the final persistence status."""

        with self._lock:
            self._store.record_shutdown(self._service.materialized_state())
            return self._view()

    @property
    def service(self) -> ScoreboardService:
        return self._service

    @property
    def display(self) -> DisplayLink:
        return self._display

    # --- Internals ----------------------------------------------------------

    def _view(self, now: float | None = None) -> dict[str, Any]:
        return self._with_cutscenes(
            self._with_identity(
                operator_view_model(
                    self._service,
                    persistence=self._store.status,
                    display=self._display.status,
                    now=now,
                )
            )
        )

    def _result_payload(
        self,
        *,
        accepted: bool,
        error: CommandError | None,
        confirmation_required: bool = False,
        result: CommandResult | None = None,
    ) -> dict[str, Any]:
        return {
            "accepted": accepted,
            # A first submit of a dangerous command changes nothing and asks
            # for confirmation; the view resubmits the same command with
            # confirmed=true (F-022, F-023, U-004).
            "confirmation_required": confirmation_required,
            "error": None
            if error is None
            else {"code": error.code, "message": error.message},
            "event": None
            if result is None or result.event is None
            else {
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
    "INTERNAL_ERROR",
    "INVALID_ARGUMENTS",
    "OPERATOR_MOUSE_SOURCE",
    "OPERATOR_KEYBOARD_SOURCE",
    "UNKNOWN_COMMAND",
    "DisplayLink",
    "DisplayStatus",
    "FieldAssistantBridge",
    "ScoreboardBridge",
    "SpectatorBridge",
    "build_command",
    "operator_view_model",
    "spectator_view_model",
]
