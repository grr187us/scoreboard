# Soccer domain + application API (agent A)

Status: authoritative signatures for `domain/soccer/*`, `application/soccer_service.py`,
`soccer_snapshots.py`, `soccer_recovery.py`, `infrastructure/soccer_store.py`. Update this
file if anything changes while building; other agents should diff against the latest version.

## `scoreboard.domain.soccer.state`

```python
SOCCER_SCHEMA_VERSION: int = 1
APP_VERSION: str = "0.1.0"
MAX_TEAM_NAME_LENGTH: int = 24   # re-exported from scoreboard.domain.state
MAX_SOCCER_SCORE: int = 99
DEFAULT_HOME_NAME: str = "HOME"
DEFAULT_AWAY_NAME: str = "AWAY"

PERIOD_LABELS: tuple[str, ...] = ("PRE", "1st", "HALF", "2nd", "OT1", "OT2", "SHOOTOUT", "FINAL")
LIVE_PERIODS: tuple[str, ...] = ("1st", "2nd", "OT1", "OT2")           # tuple, per IMPLEMENTERS.md
LIVE_PERIOD_LABELS: frozenset[str]                                     # same members, frozenset form
INTERVAL_PERIODS: tuple[str, ...] = ("PRE", "HALF")
INTERVAL_PERIOD_LABELS: frozenset[str]
LIFECYCLE_LABELS: tuple[str, ...] = ("PRE_GAME", "IN_PROGRESS", "HALFTIME", "FINAL")
STAT_NAMES: tuple[str, ...] = ("shots", "saves", "corners", "fouls")
MAX_STAT_VALUE: int = 99
CARD_KINDS: tuple[str, ...] = ("yellow", "red")
MAX_CARD_PLAYER_NUMBER: int = 99
SOCCER_STATUS_LABELS: tuple[str, ...] = ("INJURY", "DELAY", "WEATHER")   # spec 3.1, NOT domain_draft's 5
MAX_STATUS_CLOCK_SECONDS: float = 1800.0   # 30:00 (NCHSAA lightning wait; spec section 3.1)
MAX_GAME_CLOCK_MAXIMUM_SECONDS: float = 3600.0
MIN_SHOOTOUT_ROUND: int = 1
DEFAULT_INITIAL_KICKERS: int = 5

def lifecycle_for_period(label: str) -> str: ...
    # PRE -> PRE_GAME, HALF -> HALFTIME, FINAL -> FINAL, else IN_PROGRESS

class StateValidationError(ValueError): ...   # own subclass, not football's

@dataclass(frozen=True, slots=True)
class CardEvent:
    team: str                # "home" | "away"
    kind: str                # "yellow" | "red"
    player_number: int | None
    period: str               # one of PERIOD_LABELS, captured at the moment
    clock_display: str        # formatted clock text captured at the moment

@dataclass(frozen=True, slots=True)
class ShootoutKick:
    team: str
    round: int                # >= 1
    kicker_number: int | None
    made: bool

@dataclass(frozen=True, slots=True)
class SoccerState:
    schema_version: int = SOCCER_SCHEMA_VERSION
    app_version: str = APP_VERSION
    revision: int = 0
    home_name: str = DEFAULT_HOME_NAME
    away_name: str = DEFAULT_AWAY_NAME
    home_score: int = 0
    away_score: int = 0
    period: str = "PRE"
    lifecycle: str = "PRE_GAME"
    game_clock: ClockValue = ClockValue(1800.0, False, 1800.0)   # domain.state.ClockValue, reused
    home_shots: int = 0
    away_shots: int = 0
    home_saves: int = 0
    away_saves: int = 0
    home_corners: int = 0
    away_corners: int = 0
    home_fouls: int = 0
    away_fouls: int = 0
    cards: tuple[CardEvent, ...] = ()
    shootout_first_kicker: str | None = None
    shootout_kicks: tuple[ShootoutKick, ...] = ()
    shootout_winner: str | None = None
    game_status: str | None = None
    status_clock: ClockValue = ClockValue(0.0, False, 1800.0)
    status_clock_cleared: bool = True

    # derived properties
    @property
    def home_yellow(self) -> int: ...
    @property
    def home_red(self) -> int: ...
    @property
    def away_yellow(self) -> int: ...
    @property
    def away_red(self) -> int: ...
    @property
    def shootout_home_made(self) -> int: ...
    @property
    def shootout_away_made(self) -> int: ...
    @property
    def state_revision(self) -> int: ...
    @property
    def home_team_name(self) -> str: ...
    @property
    def away_team_name(self) -> str: ...

    def evolve(self, **changes: Any) -> "SoccerState": ...

def default_state() -> SoccerState: ...
```

Reused directly from `scoreboard.domain.state` by import (not copied): `ClockValue`, `TEAM_SIDES`,
`MAX_TEAM_NAME_LENGTH`, `setup_prompt_detail`. **Soccer's `StateValidationError` is its own class**,
not football's, so a soccer test asserting the exception type must import it from
`scoreboard.domain.soccer.state`.

## `scoreboard.domain.soccer.commands`

```python
class SoccerCommandType(str, Enum):
    SET_TEAM_NAME = "set_team_name"
    ADD_GOAL = "add_goal"
    CORRECT_GOAL = "correct_goal"
    SET_SCORE = "set_score"
    UNDO = "undo"
    PERIOD_FORWARD = "period_forward"
    PERIOD_BACK = "period_back"
    SET_PERIOD = "set_period"
    NEW_GAME = "new_game"
    END_GAME = "end_game"
    GAME_CLOCK_START = "game_clock_start"
    GAME_CLOCK_STOP = "game_clock_stop"
    GAME_CLOCK_RESET = "game_clock_reset"
    GAME_CLOCK_CORRECT = "game_clock_correct"
    ADD_STAT = "add_stat"
    SET_STAT = "set_stat"
    ADD_CARD = "add_card"
    REMOVE_CARD = "remove_card"
    SET_SHOOTOUT_FIRST_KICKER = "set_shootout_first_kicker"
    SHOOTOUT_KICK = "shootout_kick"
    SHOOTOUT_CORRECT_KICK = "shootout_correct_kick"
    SHOOTOUT_REMOVE_LAST = "shootout_remove_last"
    FINISH_SHOOTOUT = "finish_shootout"
    SET_GAME_STATUS = "set_game_status"
    CLEAR_GAME_STATUS = "clear_game_status"
    STATUS_CLOCK_START = "status_clock_start"
    STATUS_CLOCK_STOP = "status_clock_stop"

@dataclass(frozen=True, slots=True)
class SoccerCommand:
    type: SoccerCommandType
    team: str | None = None
    name: str | None = None            # set_team_name
    value: int | None = None           # set_score / set_stat target
    player: int | None = None          # add_goal / add_card player number, or shootout kicker number
    label: str | None = None           # set_period / set_game_status
    seconds: float | None = None       # game_clock_correct / set_game_status
    stat: str | None = None            # add_stat / set_stat name
    step: int | None = None            # add_stat +-1
    kind: str | None = None            # add_card kind
    made: bool | None = None           # shootout_kick / shootout_correct_kick
    index: int | None = None           # remove_card / shootout_correct_kick index
    winner: str | None = None          # finish_shootout
    confirmed: bool = False
    source: str = "operator"
    expected_revision: int | None = None

@dataclass(frozen=True, slots=True)
class SoccerCommandError:
    code: str
    message: str

@dataclass(frozen=True, slots=True)
class SoccerEventIntent:
    command: SoccerCommandType
    field: str
    old_value: Any
    new_value: Any
    team: str | None = None
    source: str = "operator"

@dataclass(frozen=True, slots=True)
class SoccerUndoEntry:
    command: SoccerCommandType
    field: str
    old_value: Any
    new_value: Any
    team: str | None = None
    old_values: Mapping[str, Any] | None = None
    new_values: Mapping[str, Any] | None = None

@dataclass(frozen=True, slots=True)
class SoccerCommandResult:
    accepted: bool
    state: Any
    snapshot: dict[str, Any]
    event: SoccerEventIntent | None = None
    error: SoccerCommandError | None = None
    confirmation_required: bool = False
    confirmation: dict[str, str] | None = None
    @property
    def revision(self) -> int: ...
    @property
    def error_code(self) -> str | None: ...

SOCCER_UNDOABLE_COMMANDS: frozenset[SoccerCommandType]      # ADD_GOAL, CORRECT_GOAL, SET_SCORE,
    # PERIOD_FORWARD, PERIOD_BACK, SET_PERIOD, ADD_STAT, SET_STAT, ADD_CARD, REMOVE_CARD,
    # SET_SHOOTOUT_FIRST_KICKER, SHOOTOUT_KICK, SHOOTOUT_CORRECT_KICK, SHOOTOUT_REMOVE_LAST
SOCCER_NON_UNDOABLE_COMMANDS: frozenset[SoccerCommandType]  # NEW_GAME, END_GAME, UNDO, FINISH_SHOOTOUT
# set_game_status/clear_game_status/status_clock_start/status_clock_stop/set_team_name/
# game_clock_* are in NEITHER set (F3-style exemption, mirrors football)

SOCCER_ALLOWED_ARGUMENTS: dict[SoccerCommandType, frozenset[str]]
    # e.g. {SoccerCommandType.ADD_GOAL: frozenset({"team", "player"}), ...}

def build_soccer_command(
    name: str, args: Mapping[str, Any], expected_revision: int | None, *, source: str = "operator"
) -> SoccerCommand | SoccerCommandError: ...
    # the airlock: unknown command name / disallowed argument key -> SoccerCommandError(INVALID_COMMAND, ...)

def validate_soccer_command(command: SoccerCommand) -> SoccerCommandError | None: ...
    # shape-only validation, no state
```

Error code constants (module-level `Final[str]`): `INVALID_COMMAND`, `INVALID_TEAM`,
`INVALID_TEAM_NAME`, `TEAM_NAME_NOT_ALLOWED`, `INVALID_SCORE_TARGET`, `SCORE_ABOVE_MAXIMUM`,
`SCORE_BELOW_ZERO`, `GOAL_NOT_ALLOWED`, `INVALID_PERIOD`, `PERIOD_OUT_OF_RANGE`,
`CONFIRMATION_REQUIRED`, `NOTHING_TO_UNDO`, `NOT_UNDOABLE`, `INVALID_CLOCK_TIME`, `STALE_REVISION`,
`INVALID_STAT`, `INVALID_STAT_VALUE`, `INVALID_CARD_KIND`, `INVALID_CARD_PLAYER`,
`INVALID_CARD_INDEX`, `INVALID_SHOOTOUT_TEAM`, `INVALID_SHOOTOUT_KICK`, `INVALID_SHOOTOUT_INDEX`,
`SHOOTOUT_NOT_DECIDED`, `SHOOTOUT_WINNER_MISMATCH`, `INVALID_GAME_STATUS`,
`INVALID_STATUS_CLOCK_PRESET`, `MAX_UNDO_DEPTH` (=20, same as football).

Factory helpers exist for every command (`set_team_name(...)`, `add_goal(...)`, ... same names as
football's `domain.commands` factories, snake_case, keyword-only `source`).

## `scoreboard.domain.soccer.clocks`

```python
class StateValidationError(ValueError): ...   # re-exported from domain.soccer.state, same object

STATUS_CLOCK_PRESETS: tuple[float, ...]   # not fixed presets; soccer only loads WEATHER's configured seconds,
                                           # so this is not consulted by the service -- kept only for symmetry
WARMUP_THRESHOLD_SECONDS: float = 180.0

def event_phase_for(phase: str, seconds: float, *, warmup_threshold: float = WARMUP_THRESHOLD_SECONDS) -> str: ...

@dataclass(frozen=True, slots=True)
class SoccerGameClock:
    value: ClockValue
    monotonic_clock: Callable[[], float]
    revision: int = 0
    @classmethod
    def from_state(cls, state: SoccerState, *, monotonic_clock: Callable[[], float] | None = None) -> "SoccerGameClock": ...
    # same instance methods as football's GameClock: seconds, running, maximum_seconds, expired,
    # current_value, remaining_at, start, stop, reset, correct, expire, apply_to_state, to_clock_value

@dataclass(frozen=True, slots=True)
class SoccerStatusCountdown:
    value: ClockValue
    monotonic_clock: Callable[[], float]
    revision: int = 0
    @classmethod
    def from_state(cls, state: SoccerState, *, monotonic_clock: Callable[[], float] | None = None) -> "SoccerStatusCountdown": ...
    # same instance methods as football's StatusCountdown, plus load_preset(seconds)
```

No `SoccerPlayClock` — soccer has no play clock.

## `scoreboard.domain.soccer.rules`

```python
@dataclass(frozen=True, slots=True)
class SoccerRules:
    half_seconds: float = 2400.0            # 40:00
    halftime_seconds: float = 600.0         # 10:00
    warmup_seconds: float = 180.0           # 3:00
    pregame_seconds: float = 1800.0         # 30:00
    overtime_periods: int = 2               # 0..2
    overtime_seconds: float = 600.0         # 10:00
    golden_goal: bool = False
    shootout_enabled: bool = False
    shootout_initial_kickers: int = 5       # 1..11
    shootout_credit_goal: bool = True
    mercy_differential: int = 9             # 0(off)..20
    mercy_applies: str = "halftime_and_second_half"  # | "any_time" | "off"
    stop_clock_on_goal: bool = True
    clock_direction: str = "down"           # | "up"
    weather_seconds: float = 1800.0         # 1..1800

    def period_seconds(self, period: str) -> float | None: ...
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_payload(cls, payload: Any) -> "SoccerRules": ...
    def with_changes(self, **changes: Any) -> "SoccerRules": ...

class RulesError(ValueError): ...  # own class, mirrors domain.rules.RulesError

SOCCER_RULE_FIELDS: tuple[tuple[str, str, str], ...]
    # (name, label, kind) rows, kind in {"clock","count","toggle","choice","note"}; includes a
    # ("late_sub_note", "<the NFHS 7-4-3 sentence>", "note") row with NO corresponding dataclass
    # field -- consumers must special-case kind == "note" and skip getattr().

def default_soccer_rules() -> SoccerRules: ...
def read_soccer_rules(paths: ScoreboardPaths) -> SoccerRules: ...      # over infrastructure.config
def write_soccer_rules(paths: ScoreboardPaths, rules: SoccerRules) -> bool: ...
def soccer_rules_from_mapping(raw: Mapping[str, Any]) -> SoccerRules: ...   # == SoccerRules.from_payload
def soccer_rules_to_mapping(rules: SoccerRules) -> dict[str, Any]: ...     # == rules.to_dict()
```

`read_soccer_rules`/`write_soccer_rules` use `infrastructure.config.read_section`/`write_section`
against section name `"rules"` in soccer's own `config.json` (i.e. `<root>/soccer/config.json`) —
identical mechanism to football's, just called with the soccer `ScoreboardPaths` and `SoccerRules`.

## `scoreboard.domain.soccer.formatting`

```python
PERIOD_DISPLAY: dict[str, str]   # PRE->"Pregame", 1st->"1st Half", HALF->"Halftime", 2nd->"2nd Half",
                                  # OT1->"OT 1", OT2->"OT 2", SHOOTOUT->"Shootout", FINAL->"Final"
PERIOD_DISPLAY_SHORT: dict[str, str]  # PRE->"PRE", 1st->"1ST", HALF->"HALF", 2nd->"2ND", OT1->"OT1",
                                        # OT2->"OT2", SHOOTOUT->"SHOOT", FINAL->"FINAL"
STAT_LABELS: dict[str, str]   # shots->"S", saves->"SV", corners->"COR", fouls->"F"

def format_period(period: str) -> str: ...
def format_period_short(period: str) -> str: ...
def format_soccer_clock(value: float, direction: str, maximum: float) -> str: ...
    # direction "down": format_game_clock(value); direction "up": format_game_clock(maximum - value)
def format_stat(name: str, value: int) -> str: ...             # format_stat("shots", 4) -> "S 4"
def format_cards(yellow: int, red: int) -> str: ...             # "" at 0/0, else "Y 2 · R 0"
def format_shootout_dots(kicks: tuple[ShootoutKick, ...], team: str) -> str: ...  # "● ○ ●"
```

Reused directly from `scoreboard.domain.formatting`: `format_game_clock`, `ceil_seconds`,
`BLANK_DISPLAY`, `FormattingError`, `format_game_status`, `format_status_clock`.

## `scoreboard.domain.soccer.shootout`

```python
def next_kicker(kicks: tuple[ShootoutKick, ...], first_kicker: str | None, initial_kickers: int) -> str | None: ...
def is_decided(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> bool: ...
def winner(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> str | None: ...
def current_round(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> int: ...
def in_sudden_death(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> bool: ...
```

All pure functions over the kicks tuple; no state, no rules object beyond the plain int.

## `scoreboard.application.soccer_service`

```python
def initial_soccer_state(rules: SoccerRules | None = None, *, revision: int = 0) -> SoccerState: ...

@dataclass(frozen=True, slots=True)
class SoccerTickObservation:
    state: SoccerState
    game_clock_expired: bool = False
    game_clock_from_seconds: float = 0.0

class SoccerService:
    def __init__(self, *, state=None, monotonic_clock=None, rules=None) -> None: ...
    # accessors: state, revision, snapshot, game_clock, status_clock, rules, set_rules(rules),
    # monotonic_clock, materialized_state(now=None), observe_tick(now=None) -> SoccerTickObservation,
    # undo_entry, undo_history, mercy_reached: bool, period_decision() -> dict,
    # (period_decision is a METHOD here, not a property, because its "choices" depend on
    # SoccerRules at call time -- see the note below)
    def submit(self, command: SoccerCommand) -> SoccerCommandResult: ...
```

`period_decision()` returns
`{"pending": bool, "period": str, "token": int, "choices": [{"label": str, "command": "set_period", "args": {"label": <PERIOD_LABELS member>}}, ...]}`.
`mercy_reached` is a plain `bool` property, computed from `SoccerRules.mercy_differential`/`mercy_applies`
and the current score/period — never automatic, no command of its own (spec section 4).

No play-clock accessors exist (`play_clock`, `try_pending`, `preview_field_action`, etc. from
football's service have no soccer equivalent).

## `scoreboard.application.soccer_snapshots`

```python
def state_to_snapshot(state: SoccerState) -> dict[str, Any]: ...   # top-level "sport": "soccer", "schema_version": 1
def snapshot_to_state(snapshot: Mapping[str, Any]) -> SoccerState: ...  # additive: missing blocks -> defaults
def snapshot_to_json(state: SoccerState) -> str: ...
def json_to_state(payload: str) -> SoccerState: ...
```

Snapshot shape (see domain_draft.md section 5.1 for the full example): top-level keys `sport`,
`schema_version`, `app_version`, `state_revision`, `teams`, `period`, `lifecycle`, `clocks.game`,
`stats`, `cards`, `shootout` (`first_kicker`/`winner`/`kicks`), `status`
(`label`/`clock`/`clock_cleared`).

## `scoreboard.application.soccer_recovery`

```python
def soccer_stopped_state(state: SoccerState) -> SoccerState: ...   # stops game_clock and status_clock only

def inspect_soccer_recovery(
    paths: ScoreboardPaths, *, diagnostics: Diagnostics | None = None, stamp: str | None = None,
) -> RecoveryReport: ...
    # = application.recovery.inspect_recovery(paths, diagnostics=diagnostics, stamp=stamp,
    #                                          decode=soccer_snapshots.snapshot_to_state,
    #                                          stop_clocks=soccer_stopped_state)

def resume_recovered_soccer_game(
    report: RecoveryReport, *, monotonic_clock=None, rules: SoccerRules | None = None,
) -> SoccerService: ...

def start_new_soccer_game(*, monotonic_clock=None, rules: SoccerRules | None = None) -> SoccerService: ...
```

Uses football's `RecoveryReport`/`RecoverySource`/`RESUME_CHOICE`/`NEW_GAME_CHOICE` types directly
(they are sport-agnostic value/enum types, per IMPLEMENTERS.md and domain_draft.md section 0).

## `scoreboard.infrastructure.soccer_store`

```python
class SoccerGameStore(GameStore):
    # subclasses infrastructure.persistence.GameStore, overriding only the two private methods that
    # hard-code football's snapshot codec / clock shape:
    #   _display_key(self, state) -> tuple[int, ...]           # soccer has one clock, not two
    #   (state_to_snapshot/snapshot_to_state calls route through the additive `decode=`/`encode=`
    #    keywords described below rather than an override, since GameStore.checkpoint/record_command
    #    call state_to_snapshot directly)
    @classmethod
    def open(cls, paths: ScoreboardPaths, **kwargs) -> "SoccerGameStore": ...  # same signature as GameStore.open
```

### Seams added to shared files (additive, football-default-preserving)

- `infrastructure/persistence.py`:
  - `read_stored_game(path, *, decode=snapshot_to_state)` — new keyword-only `decode`, defaulting to
    football's own decoder; `StoredGame.state` is typed `Any` (loosened from `GameState`).
  - `GameStore.__init__`/`GameStore.open` gain a keyword-only `encode=state_to_snapshot` (football's
    encoder as the default) used everywhere the class currently calls `state_to_snapshot(state)`
    directly (`_write_state`, and nowhere else). `SoccerGameStore.open(paths, ...)` passes
    `encode=soccer_snapshots.state_to_snapshot`.
  - `GameStore._display_key` becomes an overridable method (already private; `SoccerGameStore`
    overrides it to key on the single `game` clock only, since soccer has no play clock).
- `application/recovery.py`:
  - `inspect_recovery(paths, *, diagnostics=None, stamp=None, decode=snapshot_to_state, stop_clocks=stopped_state)`
    — both new keyword-only parameters, defaulting to football's own functions; threaded through to
    its two `read_stored_game(...)` calls and to `_restored`/`_offer` (which now call the injected
    `stop_clocks` instead of the hard-coded `stopped_state`).

Football's own call sites (`application/recovery.py`'s existing tests, `host/app.py`) need zero
changes: every new keyword defaults to reproducing today's behaviour exactly.

## Data layout

`<root>/soccer/scoreboard.db`, `scoreboard.backup.db`, `config.json` (sections `"rules"`,
`"display"`, `"presentation"`), `layouts.json`, `cutscenes.json`, `cutscenes/`, `scoreboard.lock`,
`logs/application.log`. `<root>/teams.json` stays shared and untouched (football's `paths.teams`
already points at the root, not the sport subfolder — `ScoreboardPaths.for_sport` only changes
`root`, so callers must keep using the *original* root paths object for `teams.json`, per
`host/app.py`'s `SoccerApplication.root_paths` in the spec).
