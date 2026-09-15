"""The serialized soccer command service: the only writer of authoritative soccer state.

Mirrors ``scoreboard.application.service`` (spec sections 3.2, 4; domain_draft.md sections 3-4).
Same submit/apply/commit skeleton, own handlers. No play clock, no Field Assistant composite
action (that arrives with the soccer Field Assistant phase, agent G, through
``SoccerFieldAssistantBridge`` submitting ordinary commands -- nothing new here).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Final

from scoreboard.application.soccer_snapshots import state_to_snapshot
from scoreboard.domain.soccer.clocks import SoccerGameClock, SoccerStatusCountdown
from scoreboard.domain.soccer.commands import (
    CONFIRMATION_REQUIRED,
    GOAL_NOT_ALLOWED,
    INVALID_CARD_INDEX,
    INVALID_CLOCK_TIME,
    INVALID_COMMAND,
    INVALID_SHOOTOUT_INDEX,
    INVALID_SHOOTOUT_KICK,
    INVALID_STATUS_CLOCK_PRESET,
    MAX_UNDO_DEPTH,
    NOTHING_TO_UNDO,
    NOT_UNDOABLE,
    PERIOD_OUT_OF_RANGE,
    PREGAME_LIFECYCLES,
    SCORE_ABOVE_MAXIMUM,
    SCORE_BELOW_ZERO,
    SHOOTOUT_NOT_ACTIVE,
    SHOOTOUT_NOT_DECIDED,
    SHOOTOUT_WINNER_MISMATCH,
    SOCCER_NON_UNDOABLE_COMMANDS,
    SOCCER_UNDOABLE_COMMANDS,
    STALE_REVISION,
    TEAM_NAME_NOT_ALLOWED,
    SoccerCommand,
    SoccerCommandError,
    SoccerCommandResult,
    SoccerCommandType,
    SoccerEventIntent,
    SoccerUndoEntry,
    validate_soccer_command,
)
from scoreboard.domain.soccer.formatting import format_soccer_clock
from scoreboard.domain.soccer.rules import SoccerRules, default_soccer_rules
from scoreboard.domain.soccer.shootout import current_round, is_decided, winner as shootout_winner_of
from scoreboard.domain.soccer.state import (
    INTERVAL_PERIOD_LABELS,
    LIVE_PERIOD_LABELS,
    MAX_GAME_CLOCK_MAXIMUM_SECONDS,
    MAX_SOCCER_SCORE,
    MAX_STAT_VALUE,
    PERIOD_LABELS,
    CardEvent,
    ClockValue,
    ShootoutKick,
    SoccerState,
    StateValidationError,
    lifecycle_for_period,
    setup_prompt_detail,
)

FINAL_LIFECYCLE: Final[str] = "FINAL"

#: Natural expiry in these periods asks the operator what comes next (spec section 3.2).
PERIOD_DECISION_PERIODS: Final[frozenset[str]] = frozenset({"2nd", "OT1", "OT2"})


@dataclass(frozen=True, slots=True)
class _Transition:
    event: SoccerEventIntent
    changes: dict[str, Any] = field(default_factory=dict)
    game_clock: SoccerGameClock | None = None
    status_clock: SoccerStatusCountdown | None = None
    undo: SoccerUndoEntry | None = None
    clears_undo: bool = False
    pops_undo: bool = False
    replacement_state: SoccerState | None = None


@dataclass(frozen=True, slots=True)
class _PeriodClockPlan:
    loads_seconds: float | None
    maximum_seconds: float


@dataclass(frozen=True, slots=True)
class SoccerTickObservation:
    """A non-command clock observation made under the bridge command lock."""

    state: SoccerState
    game_clock_expired: bool = False
    game_clock_from_seconds: float = 0.0


def _clock_snapshot(value: ClockValue) -> dict[str, Any]:
    return {"seconds": value.seconds, "running": value.running}


def initial_soccer_state(rules: SoccerRules | None = None, *, revision: int = 0) -> SoccerState:
    """The stopped pregame baseline a new game starts from, under ``rules``."""

    active = default_soccer_rules() if rules is None else rules
    return SoccerState(
        revision=revision,
        game_clock=ClockValue(active.pregame_seconds, False, active.pregame_seconds),
    )


class SoccerService:
    """Validates and applies every authoritative soccer mutation, one at a time."""

    def __init__(
        self,
        *,
        state: SoccerState | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        rules: SoccerRules | None = None,
    ) -> None:
        monotonic = time.monotonic if monotonic_clock is None else monotonic_clock
        if not callable(monotonic):
            raise TypeError("monotonic_clock must be callable")
        if rules is not None and not isinstance(rules, SoccerRules):
            raise TypeError("rules must be a SoccerRules")
        self._rules = default_soccer_rules() if rules is None else rules
        self._period_decision_pending = False
        self._period_decision_token = 0
        initial = initial_soccer_state(self._rules) if state is None else state
        if not isinstance(initial, SoccerState):
            raise TypeError("state must be a SoccerState")
        self._monotonic = monotonic
        self._state = initial
        self._game_clock = SoccerGameClock.from_state(initial, monotonic_clock=monotonic)
        self._status_clock = SoccerStatusCountdown.from_state(initial, monotonic_clock=monotonic)
        self._undo_stack: list[SoccerUndoEntry] = []
        self._undo_blocked_by: SoccerCommandType | None = None
        self._applying = False

    # --- Read-only accessors -------------------------------------------------

    @property
    def state(self) -> SoccerState:
        return self._state

    @property
    def revision(self) -> int:
        return self._state.revision

    @property
    def snapshot(self) -> dict[str, Any]:
        return state_to_snapshot(self._state)

    @property
    def game_clock(self) -> SoccerGameClock:
        return self._game_clock

    @property
    def status_clock(self) -> SoccerStatusCountdown:
        return self._status_clock

    @property
    def rules(self) -> SoccerRules:
        return self._rules

    def set_rules(self, rules: SoccerRules) -> None:
        if not isinstance(rules, SoccerRules):
            raise TypeError("rules must be a SoccerRules")
        self._rules = rules

    @property
    def monotonic_clock(self) -> Callable[[], float]:
        return self._monotonic

    def materialized_state(self, now: float | None = None) -> SoccerState:
        current = float(self._monotonic()) if now is None else float(now)
        return replace(
            self._state,
            game_clock=self._game_clock.to_clock_value(now=current),
            status_clock=self._status_clock.to_clock_value(now=current),
        )

    def observe_tick(self, now: float | None = None) -> SoccerTickObservation:
        current = float(self._monotonic()) if now is None else float(now)
        game_before = self._game_clock.current_value(current)
        game_expired = self._game_clock.value.running and not game_before.running
        game_clock_from_seconds = self._game_clock.value.seconds

        if game_expired:
            self._game_clock = self._game_clock.expire(now=current)
            if (
                self._state.period in PERIOD_DECISION_PERIODS
                and self._state.lifecycle != FINAL_LIFECYCLE
            ):
                self._period_decision_pending = True
                self._period_decision_token += 1

        status_before = self._status_clock.current_value(current)
        status_expired = self._status_clock.value.running and not status_before.running
        if status_expired:
            self._status_clock = self._status_clock.expire(now=current)
            self._state = replace(
                self._state, status_clock=self._status_clock.to_clock_value(now=current)
            )

        return SoccerTickObservation(
            state=self.materialized_state(current),
            game_clock_expired=game_expired,
            game_clock_from_seconds=game_clock_from_seconds if game_expired else 0.0,
        )

    @property
    def undo_entry(self) -> SoccerUndoEntry | None:
        return self._undo_stack[-1] if self._undo_stack else None

    @property
    def undo_history(self) -> tuple[SoccerUndoEntry, ...]:
        return tuple(reversed(self._undo_stack))

    @property
    def mercy_reached(self) -> bool:
        """Derived view flag; never automatic (spec section 4)."""

        rules = self._rules
        if rules.mercy_differential <= 0 or rules.mercy_applies == "off":
            return False
        differential = abs(self._state.home_score - self._state.away_score)
        if differential < rules.mercy_differential:
            return False
        if rules.mercy_applies == "halftime_and_second_half":
            return self._state.period in ("HALF", "2nd") or self._state.lifecycle == "HALFTIME"
        return True  # "any_time"

    def period_decision(self) -> dict[str, Any]:
        """PL-5-style prompt (spec section 3.2/4): whether a period end is waiting."""

        choices: list[dict[str, Any]] = []
        if self._period_decision_pending:
            period = self._state.period
            rules = self._rules
            offered: list[tuple[str, str]] = []
            if period == "2nd":
                if rules.overtime_periods >= 1:
                    offered.append(("OT1", "Overtime 1"))
                elif rules.shootout_enabled:
                    offered.append(("SHOOTOUT", "Shootout"))
            elif period == "OT1":
                if rules.overtime_periods >= 2:
                    offered.append(("OT2", "Overtime 2"))
                elif rules.shootout_enabled:
                    offered.append(("SHOOTOUT", "Shootout"))
            elif period == "OT2":
                if rules.shootout_enabled:
                    offered.append(("SHOOTOUT", "Shootout"))
            for label, text in offered:
                choices.append(
                    {"label": text, "command": "set_period", "args": {"label": label, "confirmed": True}}
                )
            choices.append(
                {"label": "Final", "command": "set_period", "args": {"label": "FINAL", "confirmed": True}}
            )
            choices.append({"label": "Keep", "command": None, "args": {}})
        return {
            "pending": self._period_decision_pending,
            "period": self._state.period,
            "token": self._period_decision_token,
            "choices": choices,
        }

    def _refresh_period_decision(self, before: SoccerState) -> None:
        if not self._period_decision_pending:
            return
        clock = self._game_clock.value
        if (
            clock.running
            or clock.seconds > 0.0
            or self._state.period != before.period
            or self._state.lifecycle != before.lifecycle
        ):
            self._period_decision_pending = False

    # --- Command entry point ---------------------------------------------------

    def submit(self, command: SoccerCommand) -> SoccerCommandResult:
        if not isinstance(command, SoccerCommand):
            raise TypeError("command must be a SoccerCommand")
        if self._applying:
            raise RuntimeError(
                "commands are applied one at a time; a nested submit() is a programmer error"
            )
        self._applying = True
        try:
            return self._apply(command)
        finally:
            self._applying = False

    def _apply(self, command: SoccerCommand) -> SoccerCommandResult:
        shape_error = validate_soccer_command(command)
        if shape_error is not None:
            return self._reject(shape_error)
        if (
            command.expected_revision is not None
            and command.expected_revision != self._state.revision
        ):
            return self._reject(
                SoccerCommandError(
                    STALE_REVISION,
                    "This control was showing revision "
                    f"{command.expected_revision}; the game is now at revision "
                    f"{self._state.revision}. Check the board and try again.",
                )
            )

        now = float(self._monotonic())
        handler = self._HANDLERS[command.type]
        outcome = handler(self, command, now)
        if isinstance(outcome, SoccerCommandError):
            confirmation = None
            if outcome.code == CONFIRMATION_REQUIRED and command.type in (
                SoccerCommandType.PERIOD_FORWARD,
                SoccerCommandType.PERIOD_BACK,
                SoccerCommandType.SET_PERIOD,
            ):
                confirmation = self._period_confirmation(command, now)
            return self._reject(outcome, confirmation=confirmation)
        before = self._state
        result = self._commit(command, outcome, now)
        self._refresh_period_decision(before)
        if (
            command.type is SoccerCommandType.ADD_GOAL
            and result.accepted
            and self._rules.golden_goal
            and self._state.period in ("OT1", "OT2")
        ):
            self._period_decision_pending = True
            self._period_decision_token += 1
        return result

    # --- Commit and rejection --------------------------------------------------

    def _reject(
        self, error: SoccerCommandError, *, confirmation: dict[str, str] | None = None
    ) -> SoccerCommandResult:
        return SoccerCommandResult(
            accepted=False,
            state=self._state,
            snapshot=state_to_snapshot(self._state),
            event=None,
            error=error,
            confirmation_required=error.code == CONFIRMATION_REQUIRED,
            confirmation=confirmation,
        )

    def _commit(
        self, command: SoccerCommand, transition: _Transition, now: float
    ) -> SoccerCommandResult:
        game_clock = self._game_clock if transition.game_clock is None else transition.game_clock
        status_clock = (
            self._status_clock if transition.status_clock is None else transition.status_clock
        )

        if transition.replacement_state is not None:
            next_state = transition.replacement_state
        else:
            changes = dict(transition.changes)
            if "period" in changes:
                changes["lifecycle"] = lifecycle_for_period(changes["period"])
            changes.setdefault("game_clock", game_clock.to_clock_value(now=now))
            changes.setdefault("status_clock", status_clock.to_clock_value(now=now))
            try:
                next_state = self._state.evolve(**changes)
            except StateValidationError as exc:
                return self._reject(SoccerCommandError(INVALID_COMMAND, str(exc)))

        self._state = next_state
        self._game_clock = game_clock
        self._status_clock = status_clock

        undo_entry = transition.undo if command.type in SOCCER_UNDOABLE_COMMANDS else None
        clears_undo = transition.clears_undo or command.type in SOCCER_NON_UNDOABLE_COMMANDS
        if transition.pops_undo:
            if self._undo_stack:
                self._undo_stack.pop()
            self._undo_blocked_by = command.type
        elif undo_entry is not None:
            self._undo_stack.append(undo_entry)
            if len(self._undo_stack) > MAX_UNDO_DEPTH:
                del self._undo_stack[0]
            self._undo_blocked_by = None
        elif clears_undo:
            self._undo_stack.clear()
            self._undo_blocked_by = command.type

        return SoccerCommandResult(
            accepted=True,
            state=next_state,
            snapshot=state_to_snapshot(next_state),
            event=transition.event,
            error=None,
            confirmation_required=False,
        )

    # --- Teams and scoring ------------------------------------------------------

    def _handle_set_team_name(self, command: SoccerCommand, now: float):
        if self._state.lifecycle not in PREGAME_LIFECYCLES:
            return SoccerCommandError(
                TEAM_NAME_NOT_ALLOWED,
                "Team names can only be set before the game starts. Start a new game to change them.",
            )
        state_field = "home_name" if command.team == "home" else "away_name"
        try:
            candidate = self._state.evolve(**{state_field: command.name})
        except StateValidationError as exc:
            return SoccerCommandError(
                "INVALID_TEAM_NAME", f"That team name was rejected: {exc}. Use 1 to 24 visible characters."
            )
        old_value = getattr(self._state, state_field)
        new_value = getattr(candidate, state_field)
        return _Transition(
            changes={state_field: new_value},
            event=SoccerEventIntent(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team, source=command.source,
            ),
        )

    def _handle_add_goal(self, command: SoccerCommand, now: float):
        if self._state.period not in LIVE_PERIOD_LABELS:
            return SoccerCommandError(
                GOAL_NOT_ALLOWED, "A goal can only be recorded during a live period."
            )
        state_field = f"{command.team}_score"
        old_value = getattr(self._state, state_field)
        new_value = old_value + 1
        if new_value > MAX_SOCCER_SCORE:
            return SoccerCommandError(
                SCORE_ABOVE_MAXIMUM,
                f"The board supports scores from 0 to {MAX_SOCCER_SCORE}; {new_value} is out of range.",
            )
        changes = {state_field: new_value}
        next_game_clock = None
        if self._rules.stop_clock_on_goal:
            next_game_clock = self._game_clock.stop(now=now)
        return _Transition(
            changes=changes,
            event=SoccerEventIntent(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team, source=command.source,
            ),
            game_clock=next_game_clock,
            undo=SoccerUndoEntry(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team,
            ),
        )

    def _handle_correct_goal(self, command: SoccerCommand, now: float):
        state_field = f"{command.team}_score"
        old_value = getattr(self._state, state_field)
        new_value = old_value - 1
        if new_value < 0:
            return SoccerCommandError(
                SCORE_BELOW_ZERO, f"The {command.team} score is {old_value}; it cannot be corrected below 0."
            )
        return _Transition(
            changes={state_field: new_value},
            event=SoccerEventIntent(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team,
            ),
        )

    def _handle_set_score(self, command: SoccerCommand, now: float):
        state_field = f"{command.team}_score"
        old_value = getattr(self._state, state_field)
        target = int(command.value)
        return _Transition(
            changes={state_field: target},
            event=SoccerEventIntent(
                command=command.type, field=state_field, old_value=old_value,
                new_value=target, team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field=state_field, old_value=old_value,
                new_value=target, team=command.team,
            ),
        )

    # --- Undo --------------------------------------------------------------

    def _handle_undo(self, command: SoccerCommand, now: float):
        entry = self._undo_stack[-1] if self._undo_stack else None
        if entry is None:
            if self._undo_blocked_by is not None:
                return SoccerCommandError(
                    NOT_UNDOABLE, f"The most recent command ({self._undo_blocked_by.value}) cannot be undone."
                )
            return SoccerCommandError(NOTHING_TO_UNDO, "There is no reversible command to undo.")
        if entry.old_values is not None:
            return _Transition(
                changes=dict(entry.old_values),
                event=SoccerEventIntent(
                    command=command.type, field=entry.field,
                    old_value=entry.new_values, new_value=entry.old_values,
                    team=entry.team, source=command.source,
                ),
                pops_undo=True,
            )
        return _Transition(
            changes={entry.field: entry.old_value},
            event=SoccerEventIntent(
                command=command.type, field=entry.field,
                old_value=getattr(self._state, entry.field), new_value=entry.old_value,
                team=entry.team, source=command.source,
            ),
            pops_undo=True,
        )

    # --- Period and lifecycle ------------------------------------------------

    def _period_target(self, command: SoccerCommand):
        if command.type is SoccerCommandType.SET_PERIOD:
            return str(command.label)
        step = 1 if command.type is SoccerCommandType.PERIOD_FORWARD else -1
        index = PERIOD_LABELS.index(self._state.period) + step
        if not 0 <= index < len(PERIOD_LABELS):
            direction = "past" if step > 0 else "before"
            return SoccerCommandError(
                PERIOD_OUT_OF_RANGE,
                f"The period is {self._state.period}; it cannot move {direction} "
                f"{PERIOD_LABELS[-1] if step > 0 else PERIOD_LABELS[0]}.",
            )
        return PERIOD_LABELS[index]

    def _period_clock_plan(self, source: str, target: str, stopped: SoccerGameClock, now: float) -> _PeriodClockPlan:
        rules = self._rules
        length = rules.period_seconds(target)
        current = stopped.current_value(now)
        entering_interval = target in INTERVAL_PERIOD_LABELS
        leaving_interval = source in INTERVAL_PERIOD_LABELS
        live_needs_fresh = target in LIVE_PERIOD_LABELS and (
            current.seconds <= 0.0 or current.maximum_seconds != length
        )
        if entering_interval or leaving_interval or live_needs_fresh:
            loads = 0.0 if length is None else length
            maximum = MAX_GAME_CLOCK_MAXIMUM_SECONDS if length is None else length
        else:
            loads, maximum = None, current.maximum_seconds
        return _PeriodClockPlan(loads_seconds=loads, maximum_seconds=maximum)

    def _handle_period(self, command: SoccerCommand, now: float):
        target = self._period_target(command)
        if isinstance(target, SoccerCommandError):
            return target

        clock_is_running = self._game_clock.current_value(now).running
        if not command.confirmed:
            return SoccerCommandError(
                CONFIRMATION_REQUIRED, self._period_confirmation(command, now)["detail"]
            )

        old_value = self._state.period
        event = SoccerEventIntent(
            command=command.type, field="period", old_value=old_value, new_value=target,
            source=command.source,
        )
        next_game_clock = self._game_clock.stop(now=now)
        plan = self._period_clock_plan(old_value, target, next_game_clock, now)
        changes: dict[str, Any] = {"period": target}
        if plan.loads_seconds is not None:
            next_game_clock = SoccerGameClock(
                value=ClockValue(plan.loads_seconds, False, plan.maximum_seconds),
                monotonic_clock=self._monotonic,
            )

        if clock_is_running or plan.loads_seconds is not None:
            return _Transition(
                changes=changes, event=event, game_clock=next_game_clock, clears_undo=True,
            )
        return _Transition(
            changes=changes, event=event, game_clock=next_game_clock,
            undo=SoccerUndoEntry(command=command.type, field="period", old_value=old_value, new_value=target),
        )

    def _period_confirmation(self, command: SoccerCommand, now: float) -> dict[str, str]:
        target = self._period_target(command)
        assert not isinstance(target, SoccerCommandError)
        source = self._state.period
        setup = self._setup_sentence() if source == "PRE" and target != "PRE" else ""
        prefix = f"{setup} " if setup else ""
        game = self._game_clock.current_value(now)
        clocks = "The game clock will stop." if game.running else "The game clock is already stopped."
        plan = self._period_clock_plan(source, target, self._game_clock.stop(now=now), now)
        if plan.loads_seconds is not None:
            clock_plan = f"The game clock will load {format_soccer_clock(plan.loads_seconds, 'down', plan.maximum_seconds)} stopped."
        else:
            clock_plan = f"The game clock will remain {format_soccer_clock(game.seconds, 'down', game.maximum_seconds)} stopped."
        if (
            source in INTERVAL_PERIOD_LABELS
            and target in LIVE_PERIOD_LABELS
            and game.seconds > 0.0
        ):
            what = "pregame" if source == "PRE" else "halftime"
            return {
                "title": f"Discard remaining {what} time?",
                "detail": (
                    f"{prefix}Change period from {source} to {target}. {clocks} "
                    f"The {game.seconds:.1f}-second {what} countdown will be discarded. {clock_plan}"
                ),
                "accept_label": f"Start {target} — discard remaining {what} time",
            }
        return {
            "title": "Confirm period change",
            "detail": f"{prefix}Change period from {source} to {target}. {clocks} {clock_plan}",
            "accept_label": f"Change to {target}",
        }

    def _setup_sentence(self) -> str:
        return setup_prompt_detail(self._state.home_name, self._state.away_name)

    def _handle_new_game(self, command: SoccerCommand, now: float):
        if not command.confirmed:
            return SoccerCommandError(
                CONFIRMATION_REQUIRED,
                "New Game replaces the current game with a clean stopped board. Confirm to continue.",
            )
        previous = self._state
        fresh = initial_soccer_state(self._rules, revision=previous.revision + 1)
        return _Transition(
            event=SoccerEventIntent(
                command=command.type, field="game", old_value=previous.revision,
                new_value=fresh.revision, source=command.source,
            ),
            replacement_state=fresh,
            game_clock=SoccerGameClock(value=fresh.game_clock, monotonic_clock=self._monotonic),
            status_clock=SoccerStatusCountdown(value=fresh.status_clock, monotonic_clock=self._monotonic),
            clears_undo=True,
        )

    def _handle_end_game(self, command: SoccerCommand, now: float):
        old_value = self._state.lifecycle
        return _Transition(
            changes={"lifecycle": FINAL_LIFECYCLE},
            event=SoccerEventIntent(
                command=command.type, field="lifecycle", old_value=old_value,
                new_value=FINAL_LIFECYCLE, source=command.source,
            ),
            game_clock=self._game_clock.stop(now=now),
            clears_undo=True,
        )

    # --- Game clock -----------------------------------------------------------

    def _game_clock_transition(self, command: SoccerCommand, now: float, next_clock: SoccerGameClock) -> _Transition:
        return _Transition(
            event=SoccerEventIntent(
                command=command.type, field="game_clock",
                old_value=_clock_snapshot(self._game_clock.current_value(now)),
                new_value=_clock_snapshot(next_clock.current_value(now)), source=command.source,
            ),
            game_clock=next_clock,
        )

    def _handle_game_clock_start(self, command: SoccerCommand, now: float):
        return self._game_clock_transition(command, now, self._game_clock.start(now=now))

    def _handle_game_clock_stop(self, command: SoccerCommand, now: float):
        return self._game_clock_transition(command, now, self._game_clock.stop(now=now))

    def _handle_game_clock_reset(self, command: SoccerCommand, now: float):
        return self._game_clock_transition(command, now, self._game_clock.reset())

    def _handle_game_clock_correct(self, command: SoccerCommand, now: float):
        stopped = self._game_clock.stop(now=now)
        try:
            corrected = stopped.correct(target=float(command.seconds), now=now)
        except StateValidationError as exc:
            return SoccerCommandError(INVALID_CLOCK_TIME, f"Game clock correction rejected: {exc}.")
        return self._game_clock_transition(command, now, corrected)

    # --- Stats ------------------------------------------------------------

    def _handle_add_stat(self, command: SoccerCommand, now: float):
        state_field = f"{command.team}_{command.stat}"
        old_value = getattr(self._state, state_field)
        new_value = old_value + int(command.step)
        if new_value < 0 or new_value > MAX_STAT_VALUE:
            return SoccerCommandError(
                "INVALID_STAT_VALUE", f"{command.stat} must stay between 0 and {MAX_STAT_VALUE}."
            )
        return _Transition(
            changes={state_field: new_value},
            event=SoccerEventIntent(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team,
            ),
        )

    def _handle_set_stat(self, command: SoccerCommand, now: float):
        state_field = f"{command.team}_{command.stat}"
        old_value = getattr(self._state, state_field)
        new_value = int(command.value)
        return _Transition(
            changes={state_field: new_value},
            event=SoccerEventIntent(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field=state_field, old_value=old_value,
                new_value=new_value, team=command.team,
            ),
        )

    # --- Cards --------------------------------------------------------------

    def _handle_add_card(self, command: SoccerCommand, now: float):
        clock_display = format_soccer_clock(
            self._game_clock.current_value(now).seconds,
            self._rules.clock_direction,
            self._game_clock.maximum_seconds,
        )
        new_card = CardEvent(
            team=str(command.team), kind=str(command.kind), player_number=command.player,
            period=self._state.period, clock_display=clock_display,
        )
        old_cards = self._state.cards
        new_cards = old_cards + (new_card,)
        return _Transition(
            changes={"cards": new_cards},
            event=SoccerEventIntent(
                command=command.type, field="cards", old_value=len(old_cards),
                new_value=len(new_cards), team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field="cards", old_value=len(old_cards), new_value=len(new_cards),
                team=command.team, old_values={"cards": old_cards}, new_values={"cards": new_cards},
            ),
        )

    def _handle_remove_card(self, command: SoccerCommand, now: float):
        index = int(command.index)
        cards = self._state.cards
        if not 0 <= index < len(cards) or cards[index].team != command.team:
            return SoccerCommandError(INVALID_CARD_INDEX, "That card index does not match a card for this team.")
        old_cards = cards
        new_cards = cards[:index] + cards[index + 1 :]
        return _Transition(
            changes={"cards": new_cards},
            event=SoccerEventIntent(
                command=command.type, field="cards", old_value=len(old_cards),
                new_value=len(new_cards), team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field="cards", old_value=len(old_cards), new_value=len(new_cards),
                team=command.team, old_values={"cards": old_cards}, new_values={"cards": new_cards},
            ),
        )

    # --- Shootout -------------------------------------------------------------

    def _handle_set_shootout_first_kicker(self, command: SoccerCommand, now: float):
        if self._state.period != "SHOOTOUT" or self._state.shootout_kicks:
            return SoccerCommandError(
                SHOOTOUT_NOT_ACTIVE, "The first kicker can only be set before the first kick, in the shootout period."
            )
        old_value = self._state.shootout_first_kicker
        new_value = command.team
        return _Transition(
            changes={"shootout_first_kicker": new_value},
            event=SoccerEventIntent(
                command=command.type, field="shootout_first_kicker", old_value=old_value,
                new_value=new_value, team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field="shootout_first_kicker", old_value=old_value, new_value=new_value,
            ),
        )

    def _handle_shootout_kick(self, command: SoccerCommand, now: float):
        if self._state.period != "SHOOTOUT":
            return SoccerCommandError(SHOOTOUT_NOT_ACTIVE, "Kicks can only be recorded during the shootout.")
        if self._state.shootout_winner is not None:
            return SoccerCommandError(SHOOTOUT_NOT_ACTIVE, "The shootout is already decided.")
        if self._state.shootout_first_kicker is None:
            return SoccerCommandError(INVALID_SHOOTOUT_KICK, "Set the first kicker before recording a kick.")
        kicks = self._state.shootout_kicks
        round_number = sum(1 for k in kicks if k.team == command.team) + 1
        new_kick = ShootoutKick(
            team=str(command.team), round=round_number, kicker_number=command.player, made=bool(command.made),
        )
        old_kicks = kicks
        new_kicks = kicks + (new_kick,)
        return _Transition(
            changes={"shootout_kicks": new_kicks},
            event=SoccerEventIntent(
                command=command.type, field="shootout_kicks", old_value=len(old_kicks),
                new_value=len(new_kicks), team=command.team, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field="shootout_kicks", old_value=len(old_kicks), new_value=len(new_kicks),
                team=command.team, old_values={"shootout_kicks": old_kicks}, new_values={"shootout_kicks": new_kicks},
            ),
        )

    def _handle_shootout_correct_kick(self, command: SoccerCommand, now: float):
        kicks = self._state.shootout_kicks
        index = int(command.index)
        if not 0 <= index < len(kicks):
            return SoccerCommandError(INVALID_SHOOTOUT_INDEX, "That shootout kick index does not exist.")
        old_kicks = kicks
        target = kicks[index]
        new_kick = ShootoutKick(
            team=target.team, round=target.round, kicker_number=target.kicker_number, made=bool(command.made),
        )
        new_kicks = kicks[:index] + (new_kick,) + kicks[index + 1 :]
        return _Transition(
            changes={"shootout_kicks": new_kicks},
            event=SoccerEventIntent(
                command=command.type, field="shootout_kicks", old_value=target.made,
                new_value=new_kick.made, source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field="shootout_kicks", old_value=target.made, new_value=new_kick.made,
                old_values={"shootout_kicks": old_kicks}, new_values={"shootout_kicks": new_kicks},
            ),
        )

    def _handle_shootout_remove_last(self, command: SoccerCommand, now: float):
        kicks = self._state.shootout_kicks
        if not kicks:
            return SoccerCommandError(INVALID_SHOOTOUT_INDEX, "There is no shootout kick to remove.")
        old_kicks = kicks
        new_kicks = kicks[:-1]
        return _Transition(
            changes={"shootout_kicks": new_kicks},
            event=SoccerEventIntent(
                command=command.type, field="shootout_kicks", old_value=len(old_kicks),
                new_value=len(new_kicks), source=command.source,
            ),
            undo=SoccerUndoEntry(
                command=command.type, field="shootout_kicks", old_value=len(old_kicks), new_value=len(new_kicks),
                old_values={"shootout_kicks": old_kicks}, new_values={"shootout_kicks": new_kicks},
            ),
        )

    def _handle_finish_shootout(self, command: SoccerCommand, now: float):
        if self._state.period != "SHOOTOUT":
            return SoccerCommandError(SHOOTOUT_NOT_ACTIVE, "The shootout is not active.")
        kicks = self._state.shootout_kicks
        initial = self._rules.shootout_initial_kickers
        if not is_decided(kicks, initial):
            return SoccerCommandError(SHOOTOUT_NOT_DECIDED, "The shootout is not yet decided.")
        derived = shootout_winner_of(kicks, initial)
        if command.winner is not None and command.winner != derived:
            return SoccerCommandError(SHOOTOUT_WINNER_MISMATCH, "That is not the shootout's decided winner.")
        changes: dict[str, Any] = {
            "shootout_winner": derived, "period": "FINAL", "lifecycle": FINAL_LIFECYCLE,
        }
        if self._rules.shootout_credit_goal and derived is not None:
            state_field = f"{derived}_score"
            changes[state_field] = getattr(self._state, state_field) + 1
        return _Transition(
            changes=changes,
            event=SoccerEventIntent(
                command=command.type, field="shootout_winner", old_value=None,
                new_value=derived, team=derived, source=command.source,
            ),
            game_clock=self._game_clock.stop(now=now),
            clears_undo=True,
        )

    # --- Crowd status (F3-equivalent) -----------------------------------------

    def _status_clock_transition(self, command: SoccerCommand, now: float, next_clock: SoccerStatusCountdown) -> _Transition:
        return _Transition(
            event=SoccerEventIntent(
                command=command.type, field="status_clock",
                old_value=_clock_snapshot(self._status_clock.current_value(now)),
                new_value=_clock_snapshot(next_clock.current_value(now)), source=command.source,
            ),
            status_clock=next_clock,
        )

    def _handle_set_game_status(self, command: SoccerCommand, now: float):
        old_label = self._state.game_status
        new_label = str(command.label)
        if command.seconds is not None:
            try:
                next_clock = self._status_clock.load_preset(float(command.seconds), now=now).start(now=now)
            except StateValidationError as exc:
                return SoccerCommandError(INVALID_STATUS_CLOCK_PRESET, f"Status clock preset rejected: {exc}.")
            clock_cleared = False
        else:
            next_clock = self._status_clock.clear(now=now)
            clock_cleared = True
        return _Transition(
            changes={"game_status": new_label, "status_clock_cleared": clock_cleared},
            event=SoccerEventIntent(
                command=command.type, field="game_status", old_value=old_label,
                new_value=new_label, source=command.source,
            ),
            status_clock=next_clock,
        )

    def _handle_clear_game_status(self, command: SoccerCommand, now: float):
        old_label = self._state.game_status
        return _Transition(
            changes={"game_status": None, "status_clock_cleared": True},
            event=SoccerEventIntent(
                command=command.type, field="game_status", old_value=old_label,
                new_value=None, source=command.source,
            ),
            status_clock=self._status_clock.clear(now=now),
        )

    def _handle_status_clock_start(self, command: SoccerCommand, now: float):
        return self._status_clock_transition(command, now, self._status_clock.start(now=now))

    def _handle_status_clock_stop(self, command: SoccerCommand, now: float):
        return self._status_clock_transition(command, now, self._status_clock.stop(now=now))

    _HANDLERS: Final[dict[SoccerCommandType, Any]] = {
        SoccerCommandType.SET_TEAM_NAME: _handle_set_team_name,
        SoccerCommandType.ADD_GOAL: _handle_add_goal,
        SoccerCommandType.CORRECT_GOAL: _handle_correct_goal,
        SoccerCommandType.SET_SCORE: _handle_set_score,
        SoccerCommandType.UNDO: _handle_undo,
        SoccerCommandType.PERIOD_FORWARD: _handle_period,
        SoccerCommandType.PERIOD_BACK: _handle_period,
        SoccerCommandType.SET_PERIOD: _handle_period,
        SoccerCommandType.NEW_GAME: _handle_new_game,
        SoccerCommandType.END_GAME: _handle_end_game,
        SoccerCommandType.GAME_CLOCK_START: _handle_game_clock_start,
        SoccerCommandType.GAME_CLOCK_STOP: _handle_game_clock_stop,
        SoccerCommandType.GAME_CLOCK_RESET: _handle_game_clock_reset,
        SoccerCommandType.GAME_CLOCK_CORRECT: _handle_game_clock_correct,
        SoccerCommandType.ADD_STAT: _handle_add_stat,
        SoccerCommandType.SET_STAT: _handle_set_stat,
        SoccerCommandType.ADD_CARD: _handle_add_card,
        SoccerCommandType.REMOVE_CARD: _handle_remove_card,
        SoccerCommandType.SET_SHOOTOUT_FIRST_KICKER: _handle_set_shootout_first_kicker,
        SoccerCommandType.SHOOTOUT_KICK: _handle_shootout_kick,
        SoccerCommandType.SHOOTOUT_CORRECT_KICK: _handle_shootout_correct_kick,
        SoccerCommandType.SHOOTOUT_REMOVE_LAST: _handle_shootout_remove_last,
        SoccerCommandType.FINISH_SHOOTOUT: _handle_finish_shootout,
        SoccerCommandType.SET_GAME_STATUS: _handle_set_game_status,
        SoccerCommandType.CLEAR_GAME_STATUS: _handle_clear_game_status,
        SoccerCommandType.STATUS_CLOCK_START: _handle_status_clock_start,
        SoccerCommandType.STATUS_CLOCK_STOP: _handle_status_clock_stop,
    }


__all__ = ["FINAL_LIFECYCLE", "SoccerService", "SoccerTickObservation", "initial_soccer_state"]
