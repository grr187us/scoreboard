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
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Final, Mapping

from scoreboard.application.snapshots import state_to_snapshot
from scoreboard.domain.clocks import (
    GameClock,
    PlayClock,
    StatusCountdown,
    clear_play_clock_on_game_clock_start,
    clear_play_clock_on_game_clock_stop,
)
from scoreboard.domain.formatting import format_game_clock
from scoreboard.domain.rules import GameRules, default_rules
from scoreboard.domain.field_assistant import (
    FieldAction,
    FieldAssistantContext,
    FieldAssistantValidationError,
    FieldResult,
    SeriesState,
    absolute_from_ball_spot,
    calculate_field_action,
    penalty_enforcement_spot,
)
from scoreboard.domain.commands import (
    CONFIRMATION_REQUIRED,
    INVALID_CLOCK_TIME,
    INVALID_FIELD_ACTION,
    INVALID_COMMAND,
    INVALID_PLAY_CLOCK_PRESET,
    INVALID_STATUS_CLOCK_PRESET,
    INVALID_TEAM_NAME,
    MAX_UNDO_DEPTH,
    NON_UNDOABLE_COMMANDS,
    NOT_UNDOABLE,
    NOTHING_TO_UNDO,
    PREGAME_LIFECYCLES,
    QUARTER_OUT_OF_RANGE,
    SCORE_ABOVE_MAXIMUM,
    SCORE_BELOW_ZERO,
    STALE_REVISION,
    TEAM_NAME_NOT_ALLOWED,
    TIMEOUT_ABOVE_MAXIMUM,
    TIMEOUT_BELOW_ZERO,
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
    INTERVAL_QUARTER_LABELS,
    LIVE_QUARTER_LABELS,
    MAX_SCORE,
    QUARTER_LABELS,
    BallSpot,
    ClockValue,
    GameState,
    MAX_GAME_CLOCK_SECONDS,
    StateValidationError,
    setup_prompt_detail,
)

FINAL_LIFECYCLE: Final[str] = "FINAL"


@dataclass(frozen=True, slots=True)
class _Transition:
    """A handler's accepted outcome, before the service commits it."""

    event: EventIntent
    changes: dict[str, Any] = field(default_factory=dict)
    game_clock: GameClock | None = None
    play_clock: PlayClock | None = None
    status_clock: StatusCountdown | None = None
    undo: UndoEntry | None = None
    clears_undo: bool = False
    #: Set only by ``_handle_undo``: this transition is Undo itself reversing
    #: the stack's top entry, so the commit step must pop exactly that one
    #: entry rather than treating Undo as an ordinary barrier that clears the
    #: whole stack (Undo is a member of ``NON_UNDOABLE_COMMANDS``, which would
    #: otherwise wipe out the older entries a second Undo is meant to reach).
    pops_undo: bool = False
    replacement_state: GameState | None = None


@dataclass(frozen=True, slots=True)
class _QuarterClockPlan:
    """What a quarter move does to the game clock, decided once.

    ``loads_seconds`` is ``None`` when the clock simply keeps its stopped
    value; otherwise the fresh stopped value it loads, with
    ``maximum_seconds`` as that period's length (what Reset returns to).
    """

    loads_seconds: float | None
    maximum_seconds: float
    remaining_seconds: float
    resets_timeouts: bool


@dataclass(frozen=True, slots=True)
class TickObservation:
    """A non-command clock observation made under the bridge command lock."""

    state: GameState
    game_clock_expired: bool = False
    play_clock_cleared: bool = False
    game_clock_from_seconds: float = 0.0
    play_clock_from_seconds: float = 0.0


def _clock_snapshot(value: ClockValue) -> dict[str, Any]:
    """The old/new shape reported for clock commands in an event intent."""

    return {"seconds": value.seconds, "running": value.running}


def _ball_spot_snapshot(value: BallSpot) -> dict[str, Any]:
    """The old/new shape reported for ``set_ball_on`` in an event intent.

    ``dataclasses.asdict`` so this matches, field for field, what Undo's
    generic ``getattr(state, entry.field)`` path produces for the same
    ``BallSpot`` value (persistence.py's JSON encoder applies the same
    conversion there) -- the audit history describes the same field position
    the same way regardless of which path recorded it.
    """

    return asdict(value)


def _field_assistant_values(state: GameState) -> dict[str, Any]:
    """The indivisible state group restored by a Field Assistant Undo."""

    return {
        "ball_on": None if state.ball_on is None else _ball_spot_snapshot(state.ball_on),
        "possession": state.possession,
        "down": state.down,
        "distance": state.distance,
        "assistant_first_quarter_home_direction": state.assistant_first_quarter_home_direction,
        "assistant_line_to_gain": state.assistant_line_to_gain,
        "home_score": state.home_score,
        "away_score": state.away_score,
    }


def _field_assistant_restore_values(state: GameState) -> dict[str, Any]:
    """State-shaped (not JSON-shaped) values retained in a composite Undo."""

    return {
        "ball_on": state.ball_on,
        "possession": state.possession,
        "down": state.down,
        "distance": state.distance,
        "assistant_first_quarter_home_direction": state.assistant_first_quarter_home_direction,
        "assistant_line_to_gain": state.assistant_line_to_gain,
        "home_score": state.home_score,
        "away_score": state.away_score,
    }


def _undo_reported_value(value: Any) -> Any:
    """The JSON-safe old/new value Undo's generic path reports for one field.

    Every other undoable field is already a plain ``str``/``int``/``None``
    that an :class:`EventIntent` can carry as-is. ``BallSpot`` is the one
    compound state field reachable through Undo's generic
    ``getattr(state, entry.field)``, so it is the one case that needs
    converting before it reaches the event -- and, eventually, the bridge and
    the durable history -- exactly as :func:`_ball_spot_snapshot` already
    converts it on ``set_ball_on``'s own direct path.
    """

    if isinstance(value, BallSpot):
        return _ball_spot_snapshot(value)
    return value


def initial_state(rules: GameRules | None = None, *, revision: int = 0) -> GameState:
    """The stopped pregame baseline a new game starts from, under ``rules``.

    ``GameState()`` alone carries the shipped defaults (a 30:00 kickoff, three
    timeouts a side); this applies the operator's configured pregame length
    and timeouts per half instead, which is what New Game and a fresh launch
    both mean by "a clean board".
    """

    active = default_rules() if rules is None else rules
    return GameState(
        revision=revision,
        game_clock=ClockValue(active.pregame_seconds, False, active.pregame_seconds),
        home_timeouts=active.timeouts_per_half,
        away_timeouts=active.timeouts_per_half,
    )


class ScoreboardService:
    """Validates and applies every authoritative mutation, one at a time."""

    def __init__(
        self,
        *,
        state: GameState | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        rules: GameRules | None = None,
    ) -> None:
        monotonic = time.monotonic if monotonic_clock is None else monotonic_clock
        if not callable(monotonic):
            raise TypeError("monotonic_clock must be callable")
        if rules is not None and not isinstance(rules, GameRules):
            raise TypeError("rules must be a GameRules")
        self._rules = default_rules() if rules is None else rules
        initial = initial_state(self._rules) if state is None else state
        if not isinstance(initial, GameState):
            raise TypeError("state must be a GameState")
        self._monotonic = monotonic
        self._state = initial
        # Every engine shares the service's single time source. A play clock
        # rebuilt from state starts with no remembered preset, because
        # preset_seconds is engine-only bookkeeping and is not part of the
        # persisted ClockValue contract; a preset command reloads it.
        self._game_clock = GameClock.from_state(initial, monotonic_clock=monotonic)
        self._play_clock = PlayClock.from_state(initial, monotonic_clock=monotonic)
        self._status_clock = StatusCountdown.from_state(initial, monotonic_clock=monotonic)
        # A bounded, strictly last-in-first-out stack (I4): the newest entry
        # is always index -1, and Undo only ever reverses that one. A single
        # global level would foreclose fixing an earlier mistake the moment a
        # second reversible command follows it; the stack keeps every entry
        # reachable, in order, until a barrier command clears it or it grows
        # past MAX_UNDO_DEPTH and drops its oldest member.
        self._undo_stack: list[UndoEntry] = []
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
    def rules(self) -> GameRules:
        """The timing rules the next quarter change, New Game, or TIMEOUT uses."""

        return self._rules

    def set_rules(self, rules: GameRules) -> None:
        """Replace the rules. Not a command: no revision, no history row.

        Nothing already loaded changes -- a running 2nd quarter keeps its
        clock -- because a rule is what a period *loads*, not a correction to
        the one in progress. The next quarter change, New Game, or crowd
        TIMEOUT press picks the new values up.
        """

        if not isinstance(rules, GameRules):
            raise TypeError("rules must be a GameRules")
        self._rules = rules

    @property
    def status_clock(self) -> StatusCountdown:
        return self._status_clock

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
        return replace(
            self._state,
            game_clock=self._game_clock.to_clock_value(now=current),
            play_clock=self._play_clock.to_clock_value(now=current),
            status_clock=self._status_clock.to_clock_value(now=current),
        )

    def observe_tick(self, now: float | None = None) -> TickObservation:
        """Materialize a refresh and commit the natural-expiry stop coupling.

        ``materialized_state`` intentionally stays read-only.  The bridge calls
        this method while holding its command lock, so the single service
        mutation below cannot race a submitted command.  Natural expiration
        keeps the state revision unchanged, but clearing the running play-clock
        engine is committed so later ticks cannot resume its old deadline.
        """

        current = float(self._monotonic()) if now is None else float(now)
        game_before = self._game_clock.current_value(current)
        play_before = self._play_clock.current_value(current)
        game_expired = self._game_clock.value.running and not game_before.running
        game_clock_from_seconds = self._game_clock.value.seconds
        play_clock_cleared = False

        if game_expired:
            self._game_clock = self._game_clock.expire(now=current)
            # PRE and HALF are interval countdowns, not football game time.
            # Their natural expiry intentionally stays in that quarter and
            # never invokes the normal game/play-clock stop coupling.
            next_play_clock = self._play_clock
            if self._state.quarter not in INTERVAL_QUARTER_LABELS:
                next_play_clock = clear_play_clock_on_game_clock_stop(
                    self._play_clock,
                    game_clock_is_running=False,
                    now=current,
                )
            if next_play_clock is not self._play_clock:
                self._play_clock = next_play_clock
                # This is deliberately not ``evolve``: it records a system
                # observation without assigning an operator-command revision.
                self._state = replace(
                    self._state,
                    play_clock=next_play_clock.to_clock_value(now=current),
                    play_clock_cleared=True,
                )
                play_clock_cleared = True

        status_before = self._status_clock.current_value(current)
        status_expired = self._status_clock.value.running and not status_before.running
        if status_expired:
            self._status_clock = self._status_clock.expire(now=current)
            # This is deliberately not ``evolve``: it records a system
            # observation without assigning an operator-command revision.
            # ``status_clock_cleared`` stays False here -- the wall keeps
            # showing "0:00" alongside the still-raised message until the
            # operator explicitly clears it (.scratch/f3-i4/DESIGN.md).
            self._state = replace(
                self._state, status_clock=self._status_clock.to_clock_value(now=current)
            )

        return TickObservation(
            state=self.materialized_state(current),
            game_clock_expired=game_expired,
            play_clock_cleared=play_clock_cleared,
            game_clock_from_seconds=game_clock_from_seconds if game_expired else 0.0,
            play_clock_from_seconds=play_before.seconds if play_clock_cleared else 0.0,
        )

    @property
    def undo_entry(self) -> UndoEntry | None:
        """The transition a single Undo would reverse, if any.

        This is the stack's newest entry: every existing caller (the bridge's
        "LAST: ..." strip, the tests that asked about "the" undo entry before
        I4 introduced the stack) keeps working unchanged.
        """

        return self._undo_stack[-1] if self._undo_stack else None

    @property
    def undo_history(self) -> tuple[UndoEntry, ...]:
        """Every reversible transition currently on the stack, newest first.

        Newest-first matches the order the operator experiences them in: the
        top row is the one the next Undo reverses, exactly like
        :attr:`undo_entry`.
        """

        return tuple(reversed(self._undo_stack))

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

    def finalize_field_action(
        self, action: FieldAction,
        *,
        expected_revision: int | None = None,
        source: str = "field-assistant",
    ) -> CommandResult:
        """Finalize one Field Assistant action through the normal command path."""

        from scoreboard.domain.commands import finalize_field_action

        return self.submit(
            finalize_field_action(
                action, expected_revision=expected_revision, source=source
            )
        )

    def preview_field_action(
        self, action: FieldAction | Mapping[str, Any]
    ) -> dict[str, Any]:
        """Calculate a Field Assistant proposal without mutating any state."""

        try:
            result = self._calculate_field_action(self._coerce_field_action(action))
        except (FieldAssistantValidationError, TypeError, ValueError) as exc:
            return {
                "accepted": False,
                "error": {"code": INVALID_FIELD_ACTION, "message": str(exc)},
                "view": self.snapshot,
            }
        return {
            "accepted": True,
            "preview": self._field_result_preview(result),
            "view": self.snapshot,
        }

    def _coerce_field_action(self, action: FieldAction | Mapping[str, Any]) -> FieldAction:
        """Accept the bridge's JSON envelope and compatibility UI aliases."""

        if isinstance(action, FieldAction):
            kind, raw = action.kind, dict(action.payload)
        elif isinstance(action, Mapping):
            kind, raw = action.get("kind"), action.get("payload", {})
            if not isinstance(kind, str) or not isinstance(raw, Mapping):
                raise FieldAssistantValidationError("field action needs kind text and an object payload")
            raw = dict(raw)
        else:
            raise FieldAssistantValidationError("field action must be an object")
        has_explicit_enforcement = "enforced_absolute" in raw

        # The first implementation's compact window shares a team selector,
        # direct spot, and option selector between transitions.  Normalize
        # those UI names here; the pure calculator still sees only its clear,
        # documented vocabulary.
        if "ball_on" in raw and isinstance(raw["ball_on"], Mapping):
            spot = raw["ball_on"]
            try:
                raw.setdefault(
                    "ball_absolute",
                    absolute_from_ball_spot(
                        BallSpot(str(spot.get("team")), int(spot.get("yard_line")))
                    ),
                )
            except (TypeError, ValueError, StateValidationError) as exc:
                raise FieldAssistantValidationError(f"invalid direct ball spot: {exc}") from exc
        if "ball_absolute" in raw:
            if kind in {"normal_play", "turnover", "kickoff"}:
                raw.setdefault("final_absolute", raw["ball_absolute"])
            if kind == "penalty" and not has_explicit_enforcement:
                raw.setdefault("enforced_absolute", raw["ball_absolute"])
        if kind == "start_series":
            raw.setdefault("offense", raw.get("team"))
        elif kind == "turnover":
            raw.setdefault("new_offense", raw.get("team"))
        elif kind in {"touchdown", "try", "field_goal", "safety"}:
            raw.setdefault("scoring_team", raw.get("team"))
            if kind == "try":
                raw.setdefault("points", raw.get("option", 0))
            if raw.get("resolution") == "score_already_recorded":
                raw["add_score"] = False
        elif kind == "kickoff":
            raw.setdefault("receiving_team", raw.get("team"))
        elif kind == "manual":
            raw.setdefault("possession", raw.get("team"))
        if kind == "penalty":
            option = raw.get("option")
            # ±5/10/15 are offense-relative shortcuts.  Deriving their
            # direction and field clamp belongs here, never in JavaScript.
            if not has_explicit_enforcement and option in (-15, -10, -5, 5, 10, 15):
                context = self._field_context(raw)
                underlying_raw = raw.get("underlying_action")
                if isinstance(underlying_raw, Mapping):
                    underlying = calculate_field_action(
                        context, self._coerce_field_action(underlying_raw)
                    )
                    if underlying.ball_on is None:
                        raise FieldAssistantValidationError(
                            "a penalty shortcut needs an ordinary proposed final spot"
                        )
                    context = replace(context, ball_on=underlying.ball_on)
                spot, _ = penalty_enforcement_spot(context, int(raw["option"]))
                raw["enforced_absolute"] = spot
            else:
                raw.setdefault("enforced_absolute", raw.get("final_absolute"))
        return FieldAction(kind, raw)

    def _field_context(self, payload: Mapping[str, Any]) -> FieldAssistantContext:
        """Read the current persisted helper facts into calculator context."""

        direction = self._state.assistant_first_quarter_home_direction
        if direction is None:
            supplied = payload.get("first_quarter_home_direction")
            if supplied is not None:
                direction = supplied
        series = SeriesState(direction, self._state.assistant_line_to_gain)
        # Scoring paths do not inspect the context, but a harmless concrete
        # spot lets the same preview adapter report a useful error for all
        # other actions if ordinary field status has intentionally been cleared.
        ball = self._state.ball_on or BallSpot()
        return FieldAssistantContext(
            quarter=self._state.quarter,
            possession=self._state.possession,
            ball_on=ball,
            down=self._state.down,
            distance=self._state.distance,
            series=series,
        )

    def _calculate_field_action(self, action: FieldAction) -> FieldResult:
        return calculate_field_action(self._field_context(action.payload), action)

    @staticmethod
    def _field_result_preview(result: FieldResult) -> dict[str, Any]:
        return {
            "ball_on": None if result.ball_on is None else _ball_spot_snapshot(result.ball_on),
            "possession": result.possession,
            "down": result.down,
            "distance": result.distance,
            "line_to_gain": None if result.series is None else result.series.line_to_gain,
            "first_quarter_home_direction": (
                None if result.series is None else result.series.first_quarter_home_direction
            ),
            "score_delta": {"home": result.score_delta_home, "away": result.score_delta_away},
            "classification": result.classification,
            "summary": result.summary,
            "follow_up": result.follow_up,
            "requires_explicit_turnover": result.requires_explicit_turnover,
        }

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
            confirmation = None
            if outcome.code == CONFIRMATION_REQUIRED and command.type in (
                CommandType.QUARTER_FORWARD,
                CommandType.QUARTER_BACK,
                CommandType.SET_QUARTER,
            ):
                confirmation = self._quarter_confirmation(command, now)
            return self._reject(outcome, confirmation=confirmation)
        return self._commit(command, outcome, now)

    # --- Commit and rejection ----------------------------------------------

    def _reject(
        self, error: CommandError, *, confirmation: dict[str, str] | None = None
    ) -> CommandResult:
        return CommandResult(
            accepted=False,
            state=self._state,
            snapshot=state_to_snapshot(self._state),
            event=None,
            error=error,
            confirmation_required=error.code == CONFIRMATION_REQUIRED,
            confirmation=confirmation,
        )

    def _commit(
        self, command: Command, transition: _Transition, now: float
    ) -> CommandResult:
        game_clock = self._game_clock if transition.game_clock is None else transition.game_clock
        play_clock = self._play_clock if transition.play_clock is None else transition.play_clock
        status_clock = (
            self._status_clock if transition.status_clock is None else transition.status_clock
        )

        if transition.replacement_state is not None:
            next_state = transition.replacement_state
        else:
            changes = dict(transition.changes)
            # Lifecycle is part of the same accepted command, never a UI label.
            if "quarter" in changes:
                quarter = changes["quarter"]
                changes["lifecycle"] = {"PRE": "PRE_GAME", "HALF": "HALFTIME",
                                        "FINAL": "FINAL"}.get(quarter, "IN_PROGRESS")
            if command.type is CommandType.GAME_CLOCK_START and (
                    self._state.quarter not in INTERVAL_QUARTER_LABELS and
                    not self._game_clock.current_value(now).running
                    and game_clock.current_value(now).running):
                changes["play_clock_cleared"] = True
            elif command.type is CommandType.PLAY_CLOCK_CLEAR:
                changes["play_clock_cleared"] = True
            elif command.type in (
                CommandType.PLAY_CLOCK_PRESET,
                CommandType.PLAY_CLOCK_PRESET_START,
                CommandType.PLAY_CLOCK_CORRECT,
            ):
                changes["play_clock_cleared"] = False
            elif command.type is CommandType.PLAY_CLOCK_RESET:
                changes["play_clock_cleared"] = play_clock.preset_seconds == 0
            # Every regular command republishes materialized clocks.  A Field
            # Assistant confirmation is explicitly clock-isolated: preserving
            # the original values and flags is stronger than merely avoiding a
            # start/stop call, and prevents a post-play update from becoming an
            # incidental clock checkpoint.
            if command.type is not CommandType.FINALIZE_FIELD_ACTION:
                changes.setdefault("game_clock", game_clock.to_clock_value(now=now))
                changes.setdefault("play_clock", play_clock.to_clock_value(now=now))
                changes.setdefault("status_clock", status_clock.to_clock_value(now=now))
            try:
                next_state = self._state.evolve(**changes)
            except StateValidationError as exc:
                # A handler produced a value the state model refuses. Reject
                # rather than raise: the operator still gets a usable message.
                return self._reject(CommandError(INVALID_COMMAND, str(exc)))

        self._state = next_state
        self._game_clock = game_clock
        self._play_clock = play_clock
        self._status_clock = status_clock

        # The declared eligibility sets have the final say, so a handler can
        # never quietly make a dangerous command undoable (F-014).
        undo_entry = transition.undo if command.type in UNDOABLE_COMMANDS else None
        clears_undo = transition.clears_undo or command.type in NON_UNDOABLE_COMMANDS
        if transition.pops_undo:
            # Undo is itself a member of NON_UNDOABLE_COMMANDS (there is no
            # "redo"), so the generic ``clears_undo`` check below would wipe
            # the whole stack if it ran here -- exactly the bug this stack
            # exists to fix, since a second Undo needs the older entries still
            # in place. Popping only the one entry Undo just reversed is the
            # entire effect; the rest of the stack, newest-first order and
            # all, is untouched. ``_undo_blocked_by`` is set the same way any
            # other non-undoable command sets it -- it is only ever consulted
            # once the stack is empty, so setting it here is a no-op while
            # older entries remain and becomes the correct "undo cannot be
            # undone" answer the moment the stack drains.
            if self._undo_stack:
                self._undo_stack.pop()
            self._undo_blocked_by = command.type
        elif undo_entry is not None:
            self._undo_stack.append(undo_entry)
            # Drop the oldest entry rather than growing without bound or
            # refusing a correction just because the operator has made a lot
            # of them; MAX_UNDO_DEPTH is generous enough that this only ever
            # trims history nobody was going to reach anyway.
            if len(self._undo_stack) > MAX_UNDO_DEPTH:
                del self._undo_stack[0]
            self._undo_blocked_by = None
        elif clears_undo:
            self._undo_stack.clear()
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
        entry = self._undo_stack[-1] if self._undo_stack else None
        if entry is None:
            if self._undo_blocked_by is not None:
                return CommandError(
                    NOT_UNDOABLE,
                    f"The most recent command ({self._undo_blocked_by.value}) cannot be undone.",
                )
            return CommandError(
                NOTHING_TO_UNDO, "There is no reversible scoring or quarter command to undo."
            )
        if entry.old_values is not None:
            old_values = _field_assistant_values(self._state)
            return _Transition(
                changes=dict(entry.old_values),
                event=EventIntent(
                    command=command.type,
                    field="field_assistant",
                    old_value=old_values,
                    new_value=dict(entry.old_values),
                    team=entry.team,
                    source=command.source,
                ),
                pops_undo=True,
            )
        current = getattr(self._state, entry.field)
        # Undo is a new forward transition, not a rollback: the revision keeps
        # increasing and the reversed values are reported as old/new (F-014).
        return _Transition(
            changes={entry.field: entry.old_value},
            event=EventIntent(
                command=command.type,
                field=entry.field,
                # A compound field such as ball_on (BallSpot) must reach the
                # event/JSON boundary as the same plain dict its own direct
                # command reports, not the domain object generic getattr()
                # produces here (ARCHITECTURE.md section 8: no domain object
                # crosses the bridge).
                old_value=_undo_reported_value(current),
                new_value=_undo_reported_value(entry.old_value),
                team=entry.team,
                source=command.source,
            ),
            pops_undo=True,
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
        if not command.confirmed:
            # Every quarter move is a major lifecycle action. Nothing is
            # stopped and nothing changes until the same revision is accepted.
            return CommandError(
                CONFIRMATION_REQUIRED,
                self._quarter_confirmation(command, now)["detail"],
            )

        old_value = self._state.quarter
        event = EventIntent(
            command=command.type,
            field="quarter",
            old_value=old_value,
            new_value=target,
            source=command.source,
        )
        next_game_clock = self._game_clock.stop(now=now)
        plan = self._quarter_clock_plan(old_value, target, next_game_clock, now)
        changes: dict[str, Any] = {"quarter": target}
        if plan.loads_seconds is not None:
            # One game-clock engine for every quarter label: PRE loads the
            # kickoff countdown, HALF the halftime countdown, a playing
            # quarter its regulation period, overtime its own length --
            # each stopped, each with its period's length as the maximum so
            # Reset Game Clock returns to it. Leaving an interval abandons
            # whatever was left on it deliberately.
            next_game_clock = GameClock(
                value=ClockValue(plan.loads_seconds, False, plan.maximum_seconds),
                monotonic_clock=self._monotonic,
            )
        if plan.resets_timeouts:
            per_half = self._rules.timeouts_per_half
            changes["home_timeouts"] = per_half
            changes["away_timeouts"] = per_half

        if a_clock_is_running or plan.loads_seconds is not None:
            # Either stopping a clock or loading a fresh quarter clock makes a
            # simple quarter-only Undo misleading: it could not restore the
            # clock value that existed before this transition.
            return _Transition(
                changes=changes,
                event=event,
                game_clock=next_game_clock,
                play_clock=self._play_clock.stop(now=now),
                clears_undo=True,
            )
        return _Transition(
            changes=changes,
            event=event,
            game_clock=next_game_clock,
            undo=UndoEntry(
                command=command.type,
                field="quarter",
                old_value=old_value,
                new_value=target,
            ),
        )

    def _quarter_clock_plan(
        self, source: str, target: str, stopped: GameClock, now: float
    ) -> "_QuarterClockPlan":
        """What the game clock (and the timeouts) do on ``source`` -> ``target``.

        Shared by the confirmation text and the transition itself, so the
        dialog can never promise one thing and the commit do another.
        """

        rules = self._rules
        length = rules.period_seconds(target)
        current = stopped.current_value(now)
        entering_interval = target in INTERVAL_QUARTER_LABELS
        leaving_interval = source in INTERVAL_QUARTER_LABELS
        live_needs_fresh = target in LIVE_QUARTER_LABELS and (
            current.seconds <= 0.0
            # A period whose configured length differs from the clock's
            # current maximum (4th -> OT with a shorter overtime, or a rule
            # changed since the last quarter loaded) gets its own length.
            or current.maximum_seconds != length
        )
        if entering_interval or leaving_interval or live_needs_fresh:
            loads = 0.0 if length is None else length
            maximum = MAX_GAME_CLOCK_SECONDS if length is None else length
        else:
            loads, maximum = None, current.maximum_seconds
        return _QuarterClockPlan(
            loads_seconds=loads,
            maximum_seconds=maximum,
            remaining_seconds=current.seconds,
            # NFHS grants each side its timeouts per half: the second half
            # begins with a full allotment. The move is HALF -> 3rd only;
            # stepping back into HALF and forward again would reset twice,
            # which is also what an operator correcting that mistake wants.
            resets_timeouts=(source == "HALF" and target == "3rd"),
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
        # so downstream consumers never see it go backwards (F-023). It loads
        # the operator's configured pregame length and timeouts per half.
        fresh = initial_state(self._rules, revision=previous.revision + 1)
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
            status_clock=StatusCountdown(value=fresh.status_clock, monotonic_clock=self._monotonic),
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
        next_play_clock = self._play_clock if self._state.quarter in INTERVAL_QUARTER_LABELS else (
            clear_play_clock_on_game_clock_start(
                self._play_clock,
                game_clock_was_running=not became_running,
                now=now,
            )
        )
        return self._game_clock_transition(command, now, next_clock, next_play_clock)

    def _handle_game_clock_stop(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        was_running = self._game_clock.current_value(now).running
        next_clock = self._game_clock.stop(now=now)
        next_play_clock = self._play_clock
        if was_running and self._state.quarter not in INTERVAL_QUARTER_LABELS:
            next_play_clock = clear_play_clock_on_game_clock_stop(
                self._play_clock,
                game_clock_is_running=next_clock.current_value(now).running,
                now=now,
            )
        transition = self._game_clock_transition(command, now, next_clock, next_play_clock)
        if next_play_clock is not self._play_clock:
            return replace(transition, changes={"play_clock_cleared": True})
        return transition

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

    def _quarter_confirmation(self, command: Command, now: float) -> dict[str, str]:
        """Describe a pending quarter move without mutating any clock.

        This data crosses the bridge so mouse, keyboard, and direct selection
        get precisely the same words and the same authoritative revision check.

        Leaving PRE with a team name still on its placeholder puts the setup
        sentence first (spec 1.2). The Teams drawer's prompt is the soft half
        of that reminder and can be dismissed; this is the half that cannot be
        missed, because kickoff is the last moment the names still matter.
        """

        target = self._quarter_target(command)
        assert not isinstance(target, CommandError)
        source = self._state.quarter
        setup = self._setup_sentence() if source == "PRE" and target != "PRE" else ""
        prefix = f"{setup} " if setup else ""
        game = self._game_clock.current_value(now)
        active = [
            name for name, running in (
                ("game clock", game.running),
                ("play clock", self._play_clock.current_value(now).running),
            ) if running
        ]
        clocks = (
            "The " + ", ".join(active) + " will stop."
            if active else "All clocks are already stopped."
        )
        plan = self._quarter_clock_plan(source, target, self._game_clock.stop(now=now), now)
        timeouts = (
            f" Both teams return to {self._rules.timeouts_per_half} timeouts."
            if plan.resets_timeouts else ""
        )
        if plan.loads_seconds is not None:
            clock_plan = f"The game clock will load {format_game_clock(plan.loads_seconds)} stopped."
        else:
            clock_plan = f"The game clock will remain {format_game_clock(game.seconds)} stopped."
        if (
            source in INTERVAL_QUARTER_LABELS
            and target in LIVE_QUARTER_LABELS
            and game.seconds > 0.0
        ):
            # Leaving a countdown with time still on it is the one quarter
            # move that throws something away, so it says so in the title.
            what = "pregame" if source == "PRE" else "halftime"
            return {
                "title": f"Discard remaining {what} time?",
                "detail": (
                    f"{prefix}Change quarter from {source} to {target}. {clocks} "
                    f"The {game.seconds:.1f}-second {what} countdown will be discarded. "
                    f"{clock_plan}{timeouts}"
                ),
                "accept_label": f"Start {target} quarter — discard remaining {what} time",
            }
        return {
            "title": "Confirm quarter change",
            "detail": f"{prefix}Change quarter from {source} to {target}. {clocks} {clock_plan}{timeouts}",
            "accept_label": f"Change to {target}",
        }

    def _setup_sentence(self) -> str:
        """The same sentence the operator view model's ``setup.detail`` shows."""

        return setup_prompt_detail(self._state.home_name, self._state.away_name)

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

    def _handle_play_clock_preset_start(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        try:
            started = self._play_clock.load_preset(float(command.seconds), now=now).start(
                now=now
            )
        except StateValidationError as exc:
            return CommandError(INVALID_PLAY_CLOCK_PRESET, f"Play clock preset rejected: {exc}.")
        return self._play_clock_transition(command, now, started)

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

    # --- Crowd status (F3) --------------------------------------------------
    #
    # The crowd-facing status word and its stoppage countdown are presentation,
    # not a scoring or lifecycle fact: none of the four commands below appear
    # in either UNDOABLE_COMMANDS or NON_UNDOABLE_COMMANDS
    # (domain/commands.py), so they leave the undo stack untouched entirely,
    # exactly like the clock commands (.scratch/f3-i4/DESIGN.md).

    def _status_clock_transition(
        self, command: Command, now: float, next_clock: StatusCountdown
    ) -> _Transition:
        return _Transition(
            event=EventIntent(
                command=command.type,
                field="status_clock",
                old_value=_clock_snapshot(self._status_clock.current_value(now)),
                new_value=_clock_snapshot(next_clock.current_value(now)),
                source=command.source,
            ),
            status_clock=next_clock,
        )

    def _handle_set_game_status(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        old_label = self._state.game_status
        new_label = str(command.label)
        if command.seconds is not None:
            # Load the preset and start it in the same transition -- one
            # revision, the play_clock_preset_start precedent -- so pressing
            # TIMEOUT both raises the word and starts its countdown at once.
            try:
                next_clock = self._status_clock.load_preset(
                    float(command.seconds), now=now
                ).start(now=now)
            except StateValidationError as exc:
                return CommandError(
                    INVALID_STATUS_CLOCK_PRESET, f"Status clock preset rejected: {exc}."
                )
            clock_cleared = False
        else:
            next_clock = self._status_clock.clear(now=now)
            clock_cleared = True
        return _Transition(
            changes={"game_status": new_label, "status_clock_cleared": clock_cleared},
            event=EventIntent(
                command=command.type,
                field="game_status",
                old_value=old_label,
                new_value=new_label,
                source=command.source,
            ),
            status_clock=next_clock,
        )

    def _handle_clear_game_status(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        old_label = self._state.game_status
        return _Transition(
            changes={"game_status": None, "status_clock_cleared": True},
            event=EventIntent(
                command=command.type,
                field="game_status",
                old_value=old_label,
                new_value=None,
                source=command.source,
            ),
            status_clock=self._status_clock.clear(now=now),
        )

    def _handle_status_clock_start(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._status_clock_transition(command, now, self._status_clock.start(now=now))

    def _handle_status_clock_stop(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        return self._status_clock_transition(command, now, self._status_clock.stop(now=now))

    # --- Expanded football state --------------------------------------------
    #
    # Down, distance, possession, ball position, and timeouts remaining are
    # direct, independently settable state (docs/PHASE_2_BACKLOG.md "Deferred
    # scoreboard fields"). None of these commands touch a clock, a score, or
    # the quarter, and none of them are derived automatically from another
    # command: a change of possession does not reset down/distance, and a
    # quarter change does not touch any of them either, because inventing that
    # coupling was not requested and is exactly the kind of rule automation
    # this project's guardrails ask to avoid without an explicit decision (see
    # docs/MVP_REQUIREMENTS.md section 3 for what still needs officials'
    # confirmation).

    def _handle_set_down(self, command: Command, now: float) -> _Transition | CommandError:
        old_value = self._state.down
        new_value = command.value
        return _Transition(
            changes={"down": new_value},
            event=EventIntent(
                command=command.type,
                field="down",
                old_value=old_value,
                new_value=new_value,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type, field="down", old_value=old_value, new_value=new_value
            ),
        )

    def _handle_set_distance(self, command: Command, now: float) -> _Transition | CommandError:
        old_value = self._state.distance
        new_value = command.value
        return _Transition(
            changes={"distance": new_value},
            event=EventIntent(
                command=command.type,
                field="distance",
                old_value=old_value,
                new_value=new_value,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type, field="distance", old_value=old_value, new_value=new_value
            ),
        )

    def _handle_set_possession(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        old_value = self._state.possession
        new_value = command.team
        return _Transition(
            changes={"possession": new_value},
            event=EventIntent(
                command=command.type,
                field="possession",
                old_value=old_value,
                new_value=new_value,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type,
                field="possession",
                old_value=old_value,
                new_value=new_value,
            ),
        )

    def _handle_set_ball_on(self, command: Command, now: float) -> _Transition | CommandError:
        old_spot = self._state.ball_on
        new_spot = BallSpot(team=str(command.team), yard_line=int(command.value))
        return _Transition(
            changes={"ball_on": new_spot},
            event=EventIntent(
                command=command.type,
                field="ball_on",
                old_value=_ball_spot_snapshot(old_spot),
                new_value=_ball_spot_snapshot(new_spot),
                team=command.team,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type,
                field="ball_on",
                old_value=old_spot,
                new_value=new_spot,
                team=command.team,
            ),
        )

    def _timeout_field(self, team: str) -> str:
        return f"{team}_timeouts"

    def _handle_timeout_used(self, command: Command, now: float) -> _Transition | CommandError:
        state_field = self._timeout_field(str(command.team))
        old_value = getattr(self._state, state_field)
        new_value = old_value - 1
        if new_value < 0:
            return CommandError(
                TIMEOUT_BELOW_ZERO,
                f"The {command.team} team has no timeouts remaining to use.",
            )
        return self._timeout_transition(command, state_field, old_value, new_value)

    def _handle_timeout_correct(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        state_field = self._timeout_field(str(command.team))
        old_value = getattr(self._state, state_field)
        new_value = old_value + int(command.points)
        if new_value < 0:
            return CommandError(
                TIMEOUT_BELOW_ZERO,
                f"The {command.team} team's timeouts are {old_value}; "
                "a correction cannot take them below 0.",
            )
        if new_value > self._rules.timeouts_per_half:
            return CommandError(
                TIMEOUT_ABOVE_MAXIMUM,
                f"Timeouts remaining cannot exceed {self._rules.timeouts_per_half}.",
            )
        return self._timeout_transition(command, state_field, old_value, new_value)

    def _handle_set_timeouts(self, command: Command, now: float) -> _Transition | CommandError:
        state_field = self._timeout_field(str(command.team))
        old_value = getattr(self._state, state_field)
        new_value = int(command.value)
        if new_value > self._rules.timeouts_per_half:
            return CommandError(
                TIMEOUT_ABOVE_MAXIMUM,
                f"Timeouts remaining cannot exceed {self._rules.timeouts_per_half}.",
            )
        return self._timeout_transition(command, state_field, old_value, new_value)

    def _timeout_transition(
        self, command: Command, state_field: str, old_value: int, new_value: int
    ) -> _Transition:
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

    # --- Field Assistant composite action ---------------------------------

    def _handle_finalize_field_action(
        self, command: Command, now: float
    ) -> _Transition | CommandError:
        assert isinstance(command.action, FieldAction)
        try:
            action = self._coerce_field_action(command.action)
            result = self._calculate_field_action(action)
        except (FieldAssistantValidationError, TypeError, ValueError) as exc:
            return CommandError(INVALID_FIELD_ACTION, f"Field Assistant action rejected: {exc}")
        if result.requires_explicit_turnover:
            return CommandError(
                INVALID_FIELD_ACTION,
                "This is a proposed turnover on downs. Confirm the new offense and final spot explicitly.",
            )

        home_score = self._state.home_score + result.score_delta_home
        away_score = self._state.away_score + result.score_delta_away
        if home_score > MAX_SCORE or away_score > MAX_SCORE:
            return CommandError(
                SCORE_ABOVE_MAXIMUM,
                f"The board supports scores from 0 to {MAX_SCORE}; this transition would exceed it.",
            )

        # Scoring transitions clear a live series but retain a previously
        # established first-quarter direction so the explicit kickoff setup
        # can immediately begin a new series.  A new/start/turnover/kickoff
        # result supplies both authoritative assistant values itself.
        if result.series is None:
            direction = self._state.assistant_first_quarter_home_direction
            line_to_gain = None
        else:
            direction = result.series.first_quarter_home_direction
            line_to_gain = result.series.line_to_gain
        changes = {
            "ball_on": result.ball_on,
            "possession": result.possession,
            "down": result.down,
            "distance": result.distance,
            "assistant_first_quarter_home_direction": direction,
            "assistant_line_to_gain": line_to_gain,
            "home_score": home_score,
            "away_score": away_score,
        }
        old_values = _field_assistant_values(self._state)
        new_values = dict(changes)
        new_values["ball_on"] = (
            None if result.ball_on is None else _ball_spot_snapshot(result.ball_on)
        )
        new_values.update(
            {
                "action": {"kind": action.kind, "payload": dict(action.payload)},
                "classification": result.classification,
                "summary": result.summary,
                "follow_up": result.follow_up,
                "score_delta": {
                    "home": result.score_delta_home,
                    "away": result.score_delta_away,
                },
            }
        )
        return _Transition(
            changes=changes,
            event=EventIntent(
                command=command.type,
                field="field_assistant",
                old_value=old_values,
                new_value=new_values,
                source=command.source,
            ),
            undo=UndoEntry(
                command=command.type,
                field="field_assistant",
                old_value=old_values,
                new_value=new_values,
                old_values=_field_assistant_restore_values(self._state),
                new_values=changes,
            ),
        )

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
        CommandType.PLAY_CLOCK_PRESET_START: _handle_play_clock_preset_start,
        CommandType.PLAY_CLOCK_START: _handle_play_clock_start,
        CommandType.PLAY_CLOCK_STOP: _handle_play_clock_stop,
        CommandType.PLAY_CLOCK_CLEAR: _handle_play_clock_clear,
        CommandType.PLAY_CLOCK_RESET: _handle_play_clock_reset,
        CommandType.PLAY_CLOCK_CORRECT: _handle_play_clock_correct,
        CommandType.SET_DOWN: _handle_set_down,
        CommandType.SET_DISTANCE: _handle_set_distance,
        CommandType.SET_POSSESSION: _handle_set_possession,
        CommandType.SET_BALL_ON: _handle_set_ball_on,
        CommandType.TIMEOUT_USED: _handle_timeout_used,
        CommandType.TIMEOUT_CORRECT: _handle_timeout_correct,
        CommandType.SET_TIMEOUTS: _handle_set_timeouts,
        CommandType.FINALIZE_FIELD_ACTION: _handle_finalize_field_action,
        CommandType.SET_GAME_STATUS: _handle_set_game_status,
        CommandType.CLEAR_GAME_STATUS: _handle_clear_game_status,
        CommandType.STATUS_CLOCK_START: _handle_status_clock_start,
        CommandType.STATUS_CLOCK_STOP: _handle_status_clock_stop,
    }


__all__ = ["FINAL_LIFECYCLE", "ScoreboardService", "TickObservation", "initial_state"]
