"""The serialized command service: the only writer of authoritative state.

The service owns one immutable :class:`~scoreboard.domain.state.GameState` plus
the :class:`~scoreboard.domain.clocks.GameClock` and
:class:`~scoreboard.domain.clocks.PlayClock` engines that materialize its clock
values. Every scoring, quarter, lifecycle, and clock mutation enters through
:meth:`ScoreboardService.submit`, which is a plain synchronous method: commands
are applied one at a time in submission order, so two rapid requests can never
leave a partially applied state (F-003).

Contract:

* Exactly one state revision is advanced per accepted command (F-002).
* An accepted command returns one complete snapshot plus one
  :class:`~scoreboard.domain.commands.EventIntent` for a future logger; this
  module writes nothing anywhere. Persistence and the durable action history
  belong to Task 6.
* A rejected command leaves state, revision, and both clock engines untouched
  and returns a plain-language code/message. Expected validation failures are
  never raised past this boundary; raised exceptions signal programmer errors
  (a non-``Command`` argument, or a reentrant submit).
* No clock math is re-implemented here. The service calls the existing engine
  methods and the documented module-level coupling helper, and it never reads
  wall-clock time: all timing flows through one injected monotonic source that
  is shared with both engines.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Final

from scoreboard.application.snapshots import state_to_snapshot
from scoreboard.domain.clocks import (
    EventCountdown,
    GameClock,
    PlayClock,
    clear_play_clock_on_game_clock_start,
    event_phase_for,
)
from scoreboard.domain.commands import (
    CONFIRMATION_REQUIRED,
    INVALID_CLOCK_TIME,
    INVALID_EVENT_PHASE,
    INVALID_COMMAND,
    INVALID_PLAY_CLOCK_PRESET,
    INVALID_TEAM_NAME,
    NON_UNDOABLE_COMMANDS,
    NOT_UNDOABLE,
    NOTHING_TO_UNDO,
    PREGAME_LIFECYCLES,
    QUARTER_OUT_OF_RANGE,
    SCORE_ABOVE_MAXIMUM,
    SCORE_BELOW_ZERO,
    STALE_REVISION,
    TEAM_NAME_NOT_ALLOWED,
    UNDOABLE_COMMANDS,
    Command,
    CommandError,
    CommandResult,
    CommandType,
    EventIntent,
    UndoEntry,
    validate_command,
)
from scoreboard.domain.state import (
    MAX_SCORE,
    QUARTER_LABELS,
    ClockValue,
    GameState,
    StateValidationError,
    default_state,
)

FINAL_LIFECYCLE: Final[str] = "FINAL"


@dataclass(frozen=True, slots=True)
class _Transition:
    """A handler's accepted outcome, before the service commits it."""

    event: EventIntent
    changes: dict[str, Any] = field(default_factory=dict)
    game_clock: GameClock | None = None
    play_clock: PlayClock | None = None
    event_clock: EventCountdown | None = None
    undo: UndoEntry | None = None
    clears_undo: bool = False
    replacement_state: GameState | None = None


def _clock_snapshot(value: ClockValue) -> dict[str, Any]:
    """The old/new shape reported for clock commands in an event intent."""

    return {"seconds": value.seconds, "running": value.running}


class ScoreboardService:
    """Validates and applies every authoritative mutation, one at a time."""

    def __init__(
        self,
        *,
        state: GameState | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        monotonic = time.monotonic if monotonic_clock is None else monotonic_clock
        if not callable(monotonic):
            raise TypeError("monotonic_clock must be callable")
        initial = default_state() if state is None else state
        if not isinstance(initial, GameState):
            raise TypeError("state must be a GameState")
        self._monotonic = monotonic
        self._state = initial
        # Both engines share the service's single time source. A play clock
        # rebuilt from state starts with no remembered preset, because
        # preset_seconds is engine-only bookkeeping and is not part of the
        # persisted ClockValue contract; a preset command reloads it.
        self._game_clock = GameClock.from_state(initial, monotonic_clock=monotonic)
        self._play_clock = PlayClock.from_state(initial, monotonic_clock=monotonic)
        self._event_clock = EventCountdown.from_state(initial, monotonic_clock=monotonic)
        self._undo: UndoEntry | None = None
        self._undo_blocked_by: CommandType | None = None
        self._applying = False

    # --- Read-only accessors ------------------------------------------------

    @property
    def state(self) -> GameState:
        """The current immutable authoritative state."""

        return self._state

    @property
    def revision(self) -> int:
        return self._state.revision

    @property
    def snapshot(self) -> dict[str, Any]:
        """A detached, JSON-compatible copy of the current state."""

        return state_to_snapshot(self._state)

    @property
    def game_clock(self) -> GameClock:
        return self._game_clock

    @property
    def play_clock(self) -> PlayClock:
        return self._play_clock

    @property
    def event_clock(self) -> EventCountdown:
        return self._event_clock

    @property
    def monotonic_clock(self) -> Callable[[], float]:
        """The single time source shared by the service and both engines."""

        return self._monotonic

    def materialized_state(self, now: float | None = None) -> GameState:
        """The current state with both clocks materialized at ``now``.

        This is a read-only view for display and for persistence checkpoints,
        not a transition: the revision is unchanged, so ``dataclasses.replace``
        is used rather than :meth:`GameState.evolve`. A running clock's stored
        ``seconds`` is only refreshed by an accepted command, so a checkpoint
        must ask for the derived value rather than reading the last commit.
        """

        current = float(self._monotonic()) if now is None else float(now)
        countdown = self._event_clock.to_clock_value(now=current)
        return replace(
            self._state,
            game_clock=self._game_clock.to_clock_value(now=current),
            play_clock=self._play_clock.to_clock_value(now=current),
            event_countdown=countdown,
            # The HALFTIME/WARMUP label is derived, so it changes at 3:00 while
            # the countdown runs rather than waiting for the next command.
            event_phase=event_phase_for(self._state.event_phase, countdown.seconds),
        )

    @property
    def undo_entry(self) -> UndoEntry | None:
        """The transition a single Undo would reverse, if any."""

        return self._undo

    # --- Command entry point ------------------------------------------------

    def submit(self, command: Command) -> CommandResult:
        """Validate and apply one command, returning its complete result."""

        if not isinstance(command, Command):
            raise TypeError("command must be a Command")
        if self._applying:
            raise RuntimeError(
                "commands are applied one at a time; a nested submit() is a programmer error"
            )
        self._applying = True
        try:
            return self._apply(command)
        finally:
            self._applying = False

    def _apply(self, command: Command) -> CommandResult:
        shape_error = validate_command(command)
        if shape_error is not None:
            return self._reject(shape_error)
        if (
            command.expected_revision is not None
            and command.expected_revision != self._state.revision
        ):
            return self._reject(
                CommandError(
                    STALE_REVISION,
                    "This control was showing revision "
                    f"{command.expected_revision}; the game is now at revision "
                    f"{self._state.revision}. Check the board and try again.",
                )
            )

        now = float(self._monotonic())
        handler = self._HANDLERS[command.type]
        outcome = handler(self, command, now)
        if isinstance(outcome, CommandError):
            return self._reject(outcome)
        return self._commit(command, outcome, now)

    # --- Commit and rejection ----------------------------------------------

    def _reject(self, error: CommandError) -> CommandResult:
        return CommandResult(
            accepted=False,
            state=self._state,
            snapshot=state_to_snapshot(self._state),
            event=None,
            error=error,
            confirmation_required=error.code == CONFIRMATION_REQUIRED,
        )

    def _commit(
        self, command: Command, transition: _Transition, now: float
    ) -> CommandResult:
        game_clock = self._game_clock if transition.game_clock is None else transition.game_clock
        play_clock = self._play_clock if transition.play_clock is None else transition.play_clock
        event_clock = (
            self._event_clock if transition.event_clock is None else transition.event_clock
        )

        if transition.replacement_state is not None:
            next_state = transition.replacement_state
        else:
            changes = dict(transition.changes)
            # Every accepted command republishes both materialized clock values so
            # the snapshot is complete and current at the moment it was applied.
            changes.setdefault("game_clock", game_clock.to_clock_value(now=now))
            changes.setdefault("play_clock", play_clock.to_clock_value(now=now))
            countdown = event_clock.to_clock_value(now=now)
            changes.setdefault("event_countdown", countdown)
            changes["event_phase"] = event_phase_for(
                changes.get("event_phase", self._state.event_phase), countdown.seconds
            )
            try:
                next_state = self._state.evolve(**changes)
            except StateValidationError as exc:
                # A handler produced a value the state model refuses. Reject
                # rather than raise: the operator still gets a usable message.
                return self._reject(CommandError(INVALID_COMMAND, str(exc)))

        self._state = next_state
        self._game_clock = game_clock
        self._play_clock = play_clock
        self._event_clock = event_clock

        # The declared eligibility sets have the final say, so a handler can
        # never quietly make a dangerous command undoable (F-014).
        undo_entry = transition.undo if command.type in UNDOABLE_COMMANDS else None
        clears_undo = transition.clears_undo or command.type in NON_UNDOABLE_COMMANDS
        if undo_entry is not None:
            self._undo = undo_entry
            self._undo_blocked_by = None
        elif clears_undo:
            self._undo = None
            self._undo_blocked_by = command.type

        return CommandResult(
            accepted=True,
            state=next_state,
            snapshot=state_to_snapshot(next_state),
            event=transition.event,
            error=None,
            confirmation_required=False,
        )

    # --- Teams and scoring --------------------------------------------------

    def _handle_set_team_name(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        if self._state.lifecycle not in PREGAME_LIFECYCLES:
            return CommandError(
                TEAM_NAME_NOT_ALLOWED,
                "Team names can only be set before the game starts. Start a new game to change them.",
            )
        state_field = "home_name" if command.team == "home" else "away_name"
        try:
            # Reuse the state model's own trimming and 1-24 character rule (F-010).
            candidate = self._state.evolve(**{state_field: command.name})
        except StateValidationError as exc:
            return CommandError(
                INVALID_TEAM_NAME,
                f"That team name was rejected: {exc}. Use 1 to 24 visible characters.",
            )
        old_value = getattr(self._state, state_field)
        new_value = getattr(candidate, state_field)
        return _Transition(
            changes={state_field: new_value},
            event=EventIntent(
                command=command.type,
                field=state_field,
                old_value=old_value,
                new_value=new_value,
                team=command.team,
                source=command.source,
            ),
        )

    def _score_transition(
        self, command: Command, delta: int
    ) -> _Transition | CommandError:
        state_field = f"{command.team}_score"
        old_value = getattr(self._state, state_field)
        new_value = old_value + delta
        if new_value < 0:
            return CommandError(
                SCORE_BELOW_ZERO,
                f"The {command.team} score is {old_value}; it cannot be corrected below 0.",
            )
        if new_value > MAX_SCORE:
            return CommandError(
                SCORE_ABOVE_MAXIMUM,
                f"The board supports scores from 0 to {MAX_SCORE}; {new_value} is out of range.",
            )
        return _Transition(
            changes={state_field: new_value},
            event=EventIntent(
                command=command.type,
                field=state_field,
                old_value=old_value,
                new_value=new_value,
                team=command.team,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type,
                field=state_field,
                old_value=old_value,
                new_value=new_value,
                team=command.team,
            ),
        )

    def _handle_add_score(self, command: Command, now: float) -> _Transition | CommandError:
        return self._score_transition(command, int(command.points))

    def _handle_correct_score(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._score_transition(command, -abs(int(command.points)))

    def _handle_set_score(self, command: Command, now: float) -> _Transition | CommandError:
        state_field = f"{command.team}_score"
        # The 0-199 target range is a pure shape rule, already enforced by
        # validate_command; only the reported old value needs state here.
        old_value = getattr(self._state, state_field)
        target = int(command.value)
        return _Transition(
            changes={state_field: target},
            event=EventIntent(
                command=command.type,
                field=state_field,
                old_value=old_value,
                new_value=target,
                team=command.team,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type,
                field=state_field,
                old_value=old_value,
                new_value=target,
                team=command.team,
            ),
        )

    # --- Undo ---------------------------------------------------------------

    def _handle_undo(self, command: Command, now: float) -> _Transition | CommandError:
        entry = self._undo
        if entry is None:
            if self._undo_blocked_by is not None:
                return CommandError(
                    NOT_UNDOABLE,
                    f"The most recent command ({self._undo_blocked_by.value}) cannot be undone.",
                )
            return CommandError(
                NOTHING_TO_UNDO, "There is no reversible scoring or quarter command to undo."
            )
        current = getattr(self._state, entry.field)
        # Undo is a new forward transition, not a rollback: the revision keeps
        # increasing and the reversed values are reported as old/new (F-014).
        return _Transition(
            changes={entry.field: entry.old_value},
            event=EventIntent(
                command=command.type,
                field=entry.field,
                old_value=current,
                new_value=entry.old_value,
                team=entry.team,
                source=command.source,
            ),
            clears_undo=True,
        )

    # --- Quarter and lifecycle ---------------------------------------------

    def _quarter_target(self, command: Command) -> str | CommandError:
        if command.type is CommandType.SET_QUARTER:
            return str(command.label)
        step = 1 if command.type is CommandType.QUARTER_FORWARD else -1
        index = QUARTER_LABELS.index(self._state.quarter) + step
        if not 0 <= index < len(QUARTER_LABELS):
            direction = "past" if step > 0 else "before"
            return CommandError(
                QUARTER_OUT_OF_RANGE,
                f"The quarter is {self._state.quarter}; it cannot move {direction} "
                f"{QUARTER_LABELS[-1] if step > 0 else QUARTER_LABELS[0]}.",
            )
        return QUARTER_LABELS[index]

    def _handle_quarter(self, command: Command, now: float) -> _Transition | CommandError:
        target = self._quarter_target(command)
        if isinstance(target, CommandError):
            return target

        a_clock_is_running = (
            self._game_clock.current_value(now).running
            or self._play_clock.current_value(now).running
        )
        if a_clock_is_running and not command.confirmed:
            # Nothing is stopped and nothing changes yet: the operator must
            # resubmit the same command with confirmed=True (F-022).
            return CommandError(
                CONFIRMATION_REQUIRED,
                f"A clock is running. Confirm to stop both clocks and change the quarter "
                f"from {self._state.quarter} to {target}.",
            )

        old_value = self._state.quarter
        event = EventIntent(
            command=command.type,
            field="quarter",
            old_value=old_value,
            new_value=target,
            source=command.source,
        )
        if a_clock_is_running:
            # One committed step: stop both clocks and change the quarter.
            return _Transition(
                changes={"quarter": target},
                event=event,
                game_clock=self._game_clock.stop(now=now),
                play_clock=self._play_clock.stop(now=now),
                clears_undo=True,
            )
        return _Transition(
            changes={"quarter": target},
            event=event,
            undo=UndoEntry(
                command=command.type,
                field="quarter",
                old_value=old_value,
                new_value=target,
            ),
        )

    def _handle_new_game(self, command: Command, now: float) -> _Transition | CommandError:
        if not command.confirmed:
            return CommandError(
                CONFIRMATION_REQUIRED,
                "New Game replaces the current game with a clean stopped board. "
                "Confirm to continue.",
            )
        previous = self._state
        # A new game replaces the current one; the revision keeps moving forward
        # so downstream consumers never see it go backwards (F-023).
        fresh = GameState(revision=previous.revision + 1)
        return _Transition(
            event=EventIntent(
                command=command.type,
                field="game",
                old_value=previous.revision,
                new_value=fresh.revision,
                source=command.source,
            ),
            replacement_state=fresh,
            game_clock=GameClock(value=fresh.game_clock, monotonic_clock=self._monotonic),
            play_clock=PlayClock(value=fresh.play_clock, monotonic_clock=self._monotonic),
            event_clock=EventCountdown.from_state(fresh, monotonic_clock=self._monotonic),
            clears_undo=True,
        )

    def _handle_end_game(self, command: Command, now: float) -> _Transition | CommandError:
        old_value = self._state.lifecycle
        # Scores, names, quarter, and the undo history's audit value are kept;
        # only the clocks stop and the lifecycle becomes FINAL (F-024).
        return _Transition(
            changes={"lifecycle": FINAL_LIFECYCLE},
            event=EventIntent(
                command=command.type,
                field="lifecycle",
                old_value=old_value,
                new_value=FINAL_LIFECYCLE,
                source=command.source,
            ),
            game_clock=self._game_clock.stop(now=now),
            play_clock=self._play_clock.stop(now=now),
            clears_undo=True,
        )

    # --- Game clock ---------------------------------------------------------

    def _game_clock_transition(
        self, command: Command, now: float, next_clock: GameClock, next_play_clock: PlayClock | None = None
    ) -> _Transition:
        return _Transition(
            event=EventIntent(
                command=command.type,
                field="game_clock",
                old_value=_clock_snapshot(self._game_clock.current_value(now)),
                new_value=_clock_snapshot(next_clock.current_value(now)),
                source=command.source,
            ),
            game_clock=next_clock,
            play_clock=next_play_clock,
        )

    def _handle_game_clock_start(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        was_running = self._game_clock.current_value(now).running
        next_clock = self._game_clock.start(now=now)
        became_running = next_clock.current_value(now).running and not was_running
        # The service is the first component that knows whether this Start was a
        # real stopped-to-running transition, so it applies the documented
        # coupling here (F-048). A redundant Start leaves the play clock alone.
        next_play_clock = clear_play_clock_on_game_clock_start(
            self._play_clock,
            game_clock_was_running=not became_running,
            now=now,
        )
        return self._game_clock_transition(command, now, next_clock, next_play_clock)

    def _handle_game_clock_stop(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._game_clock_transition(command, now, self._game_clock.stop(now=now))

    def _handle_game_clock_reset(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._game_clock_transition(command, now, self._game_clock.reset())

    def _handle_game_clock_correct(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        # Editing the current time stops a running game clock first (F-036).
        stopped = self._game_clock.stop(now=now)
        try:
            corrected = stopped.correct(target=float(command.seconds), now=now)
        except StateValidationError as exc:
            return CommandError(INVALID_CLOCK_TIME, f"Game clock correction rejected: {exc}.")
        return self._game_clock_transition(command, now, corrected)

    # --- Play clock ---------------------------------------------------------

    def _play_clock_transition(
        self, command: Command, now: float, next_clock: PlayClock
    ) -> _Transition:
        return _Transition(
            event=EventIntent(
                command=command.type,
                field="play_clock",
                old_value=_clock_snapshot(self._play_clock.current_value(now)),
                new_value=_clock_snapshot(next_clock.current_value(now)),
                source=command.source,
            ),
            play_clock=next_clock,
        )

    def _handle_play_clock_preset(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        try:
            loaded = self._play_clock.load_preset(float(command.seconds), now=now)
        except StateValidationError as exc:
            return CommandError(INVALID_PLAY_CLOCK_PRESET, f"Play clock preset rejected: {exc}.")
        return self._play_clock_transition(command, now, loaded)

    def _handle_play_clock_start(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._play_clock_transition(command, now, self._play_clock.start(now=now))

    def _handle_play_clock_stop(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._play_clock_transition(command, now, self._play_clock.stop(now=now))

    def _handle_play_clock_clear(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._play_clock_transition(command, now, self._play_clock.clear(now=now))

    def _handle_play_clock_reset(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._play_clock_transition(command, now, self._play_clock.reset())

    def _handle_play_clock_correct(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        # Editing the current time stops a running play clock first (F-051).
        stopped = self._play_clock.stop(now=now)
        try:
            corrected = stopped.correct(target=float(command.seconds), now=now)
        except StateValidationError as exc:
            return CommandError(INVALID_CLOCK_TIME, f"Play clock correction rejected: {exc}.")
        return self._play_clock_transition(command, now, corrected)

    # --- Event countdowns ---------------------------------------------------

    def _event_transition(
        self,
        command: Command,
        now: float,
        next_clock: EventCountdown,
        *,
        phase: str | None = None,
    ) -> _Transition:
        changes: dict[str, Any] = {}
        if phase is not None:
            changes["event_phase"] = phase
        return _Transition(
            changes=changes,
            event=EventIntent(
                command=command.type,
                field="event_countdown",
                old_value=_clock_snapshot(self._event_clock.current_value(now)),
                new_value=_clock_snapshot(next_clock.current_value(now)),
                source=command.source,
            ),
            event_clock=next_clock,
        )

    def _handle_event_countdown_select(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        # Selecting an event loads its configured length while stopped, so no
        # countdown can begin without a separate, deliberate Start (F-028).
        stopped = self._event_clock.stop(now=now)
        try:
            loaded = stopped.select(str(command.label), now=now)
        except StateValidationError as exc:
            return CommandError(INVALID_EVENT_PHASE, f"Event countdown rejected: {exc}.")
        return self._event_transition(command, now, loaded, phase=str(command.label))

    def _handle_event_countdown_start(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        # A countdown never alters the game or play clock (F-025).
        return self._event_transition(command, now, self._event_clock.start(now=now))

    def _handle_event_countdown_stop(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._event_transition(command, now, self._event_clock.stop(now=now))

    def _handle_event_countdown_reset(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._event_transition(command, now, self._event_clock.reset())

    def _handle_event_countdown_correct(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        # Edit Current Time stops a running countdown first. The optional
        # start-after-applying choice is a separate Start command issued by the
        # operator view, so remaining stopped is the default by construction.
        stopped = self._event_clock.stop(now=now)
        try:
            corrected = stopped.correct(target=float(command.seconds), now=now)
        except StateValidationError as exc:
            return CommandError(
                INVALID_CLOCK_TIME, f"Event countdown correction rejected: {exc}."
            )
        return self._event_transition(command, now, corrected)

    _HANDLERS: Final[dict[CommandType, Any]] = {
        CommandType.SET_TEAM_NAME: _handle_set_team_name,
        CommandType.ADD_SCORE: _handle_add_score,
        CommandType.CORRECT_SCORE: _handle_correct_score,
        CommandType.SET_SCORE: _handle_set_score,
        CommandType.UNDO: _handle_undo,
        CommandType.QUARTER_FORWARD: _handle_quarter,
        CommandType.QUARTER_BACK: _handle_quarter,
        CommandType.SET_QUARTER: _handle_quarter,
        CommandType.NEW_GAME: _handle_new_game,
        CommandType.END_GAME: _handle_end_game,
        CommandType.GAME_CLOCK_START: _handle_game_clock_start,
        CommandType.GAME_CLOCK_STOP: _handle_game_clock_stop,
        CommandType.GAME_CLOCK_RESET: _handle_game_clock_reset,
        CommandType.GAME_CLOCK_CORRECT: _handle_game_clock_correct,
        CommandType.PLAY_CLOCK_PRESET: _handle_play_clock_preset,
        CommandType.PLAY_CLOCK_START: _handle_play_clock_start,
        CommandType.PLAY_CLOCK_STOP: _handle_play_clock_stop,
        CommandType.PLAY_CLOCK_CLEAR: _handle_play_clock_clear,
        CommandType.PLAY_CLOCK_RESET: _handle_play_clock_reset,
        CommandType.PLAY_CLOCK_CORRECT: _handle_play_clock_correct,
        CommandType.EVENT_COUNTDOWN_SELECT: _handle_event_countdown_select,
        CommandType.EVENT_COUNTDOWN_START: _handle_event_countdown_start,
        CommandType.EVENT_COUNTDOWN_STOP: _handle_event_countdown_stop,
        CommandType.EVENT_COUNTDOWN_RESET: _handle_event_countdown_reset,
        CommandType.EVENT_COUNTDOWN_CORRECT: _handle_event_countdown_correct,
    }


__all__ = ["FINAL_LIFECYCLE", "ScoreboardService"]
