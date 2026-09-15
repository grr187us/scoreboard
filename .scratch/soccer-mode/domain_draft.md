# Soccer domain design draft (September 15, 2026)

Author: domain-design research agent. Read-only against `src/` and `tests/`; this
file is the only thing this agent wrote. Citations below are `path:line` against
the `feature/soccer-mode` branch at commit `0f5c93d` (the branch tip named in
`CONTEXT_FOR_AGENTS.md`).

Everything here is a **design**, not code. It is written so another agent can
hard-code these names and shapes directly. Every section says which football
module it mirrors and exactly how it diverges.

---

## 0. Module map (what gets created, and what each one reuses from football)

| New module | Mirrors | Reuses from football (imports, not copies) |
|---|---|---|
| `domain/soccer/state.py` | `domain/state.py` | `ClockValue`, `StateValidationError`, `TEAM_SIDES`, `MAX_TEAM_NAME_LENGTH` |
| `domain/soccer/commands.py` | `domain/commands.py` | nothing (own `CommandType`-shaped enum, own error codes) |
| `domain/soccer/clocks.py` | `domain/clocks.py` | `ClockValue` only; the engine classes (`SoccerGameClock`, `SoccerStatusCountdown`) are **new, parallel implementations**, not subclasses — see §0.1 |
| `domain/soccer/rules.py` | `domain/rules.py` | `StateValidationError` (as the shape check inside `RulesError`, same pattern football uses) |
| `domain/soccer/formatting.py` | `domain/formatting.py` | `format_game_clock`, `ceil_seconds`, `BLANK_DISPLAY`, `FormattingError` — these are pure functions of a number of seconds, not football-typed, so importing them directly is safe and avoids re-deriving the rounding rule |
| `application/soccer_service.py` | `application/service.py` | the *pattern* only (own `SoccerScoreboardService` class); no football import except pure helpers above |
| `application/soccer_snapshots.py` | `application/snapshots.py` | pattern only |
| `application/soccer_recovery.py` | `application/recovery.py` | `RecoveryReport`, `RecoverySource`, `NEW_GAME_CHOICE`/`RESUME_CHOICE` (these are sport-agnostic value/enum types already) plus the **one seam described in §5** into `infrastructure/persistence.py` |

### 0.1 Why the clock engine is duplicated rather than shared

`domain/clocks.py`'s `GameClock`, `PlayClock`, and `StatusCountdown`
(`domain/clocks.py:123-748`) each hard-check `isinstance(state, GameState)` in
`from_state`/`apply_to_state` (e.g. `domain/clocks.py:149-150`,
`domain/clocks.py:316-319`). `GameState` is football's frozen dataclass, so
these three classes cannot run against `SoccerState` without either (a)
loosening that check into a generic value with a `game_clock`/`status_clock`
attribute and an `evolve()` method, or (b) a second, soccer-typed copy of the
same ~150-line countdown engine.

**Recommendation: (b), a second copy.** `domain/clocks.py` is on the "shared
seam" list in `FABLE_PROMPT.md` ("Expect this for ... shared files get the
smallest possible additive seam"), but it is not on the byte-identical list
either — so a generalization is *technically* allowed. It is still the riskier
move: `GameClock`/`PlayClock`/`StatusCountdown` are exercised by the entire
football clock test suite, and a signature change (even an additive
`Protocol`) touches a file every football clock test imports. Duplicating the
engine is more code but zero football risk, matches the task's own module map
("`domain/soccer/` holds state, commands, clocks and rules" —
`FABLE_PROMPT.md:61`), and the duplication is small and mechanical (the same
monotonic-deadline arithmetic, retyped against `SoccerState`). If the owner
later wants one engine, the generalization is a pure refactor once both sides
exist and their tests can prove equivalence — safer to do after soccer ships
than before.

`ClockValue` itself (`domain/state.py:227-259`) is untyped with respect to
`GameState` — it is a plain immutable value (seconds/running/maximum/deadline)
with self-contained validation. Both `SoccerState.game_clock` and
`SoccerState.status_clock` should be `scoreboard.domain.state.ClockValue`
directly, exactly as the task instructs. No soccer-specific clock value type
is needed.

`domain/soccer/clocks.py` therefore defines:

- `SoccerGameClock` — copy of `GameClock` (`domain/clocks.py:123-322`),
  `from_state`/`apply_to_state` retyped to `SoccerState`.
- `SoccerStatusCountdown` — copy of `StatusCountdown`
  (`domain/clocks.py:567-748`), same retyping. Soccer's crowd countdown needs
  no play-clock coupling helpers (`clear_play_clock_on_*`,
  `domain/clocks.py:751-789`) because soccer has no play clock at all.
- No `SoccerPlayClock`: soccer has no play clock. (See "Center panel" in
  `FABLE_PROMPT.md:130-131` — the freed space is for stoppage controls, not a
  play clock.)
- `STATUS_CLOCK_PRESETS` and `WARMUP_THRESHOLD_SECONDS`-equivalents are
  redeclared locally with soccer's own defaults (§1, §2).

---

## 1. `SoccerState` (frozen dataclass, `domain/soccer/state.py`)

Mirrors `GameState` (`domain/state.py:307-457`) field for field. `evolve()`
(`domain/state.py:437-451`) is copied verbatim (same unknown-field guard, same
`revision`-is-advanced-only rule) — it has no football-specific behavior.

### 1.1 Module constants (mirrors `domain/state.py:14-123`)

```python
SOCCER_SCHEMA_VERSION: Final[int] = 1
APP_VERSION: Final[str] = "0.1.0"            # same running-build string football uses; not a compatibility gate here either
MAX_TEAM_NAME_LENGTH = 24                     # reuse football's constant directly (domain.state.MAX_TEAM_NAME_LENGTH)
MAX_SOCCER_SCORE: Final[int] = 99
DEFAULT_HOME_NAME: Final[str] = "HOME"
DEFAULT_AWAY_NAME: Final[str] = "AWAY"

PERIOD_LABELS: Final[tuple[str, ...]] = (
    "PRE", "1st", "HALF", "2nd", "OT1", "OT2", "SHOOTOUT", "FINAL",
)
LIVE_PERIOD_LABELS: Final[frozenset[str]] = frozenset({"1st", "2nd", "OT1", "OT2"})
INTERVAL_PERIOD_LABELS: Final[frozenset[str]] = frozenset({"PRE", "HALF"})
LIFECYCLE_LABELS: Final[tuple[str, ...]] = ("PRE_GAME", "IN_PROGRESS", "HALFTIME", "FINAL")

STAT_NAMES: Final[tuple[str, ...]] = ("shots", "saves", "corners", "fouls")
MAX_STAT_VALUE: Final[int] = 99

CARD_KINDS: Final[tuple[str, ...]] = ("yellow", "red")
MAX_CARD_PLAYER_NUMBER: Final[int] = 99

SOCCER_STATUS_LABELS: Final[tuple[str, ...]] = ("INJURY", "DELAY", "WEATHER", "LIGHTNING", "OFFICIALS")
MAX_STATUS_CLOCK_SECONDS: Final[float] = 300.0   # same ceiling football uses (domain.state.MAX_STATUS_CLOCK_SECONDS); reuse the constant directly, it is sport-agnostic

MAX_GAME_CLOCK_MAXIMUM_SECONDS: Final[float] = 60 * 60   # reuse football's constant directly; it is the one hard clock ceiling
MAX_PREGAME_CLOCK_SECONDS: Final[float] = 30 * 60         # default only — GameRules.pregame_seconds decides what actually loads (mirrors football exactly)

MIN_SHOOTOUT_ROUND: Final[int] = 1
DEFAULT_INITIAL_KICKERS: Final[int] = 5   # NISOA/NFHS default; confirmed by rules research, configurable in SoccerRules
```

**Discussion — PERIOD_LABELS as a fixed tuple vs. data-driven from
`overtime_periods`.** The brief asks to discuss a data-driven period list
when rules say N overtime periods. **Recommendation: keep the fixed tuple.**
Football's own `QUARTER_LABELS` (`domain/state.py:105-114`) is fixed even
though `GameRules.timeouts_per_half`/`period_seconds` are configurable — the
label set is a validation domain, the rules decide what a label *means* and
whether reaching it is offered. Doing the same for soccer means:

- `SET_PERIOD` (the correction command, mirrors `SET_QUARTER`) always accepts
  any of the 8 labels, regardless of `SoccerRules.overtime_periods` — an
  operator correcting a mis-click must always be able to reach any label, the
  same way football lets you `set_quarter("OT")` even in a rules config that
  never expects overtime.
- `PERIOD_FORWARD`/`PERIOD_BACK` (mirrors `QUARTER_FORWARD`/`QUARTER_BACK`,
  `domain/commands.py:54-56`) step through the same fixed tuple by index,
  exactly like `_quarter_target` (`application/service.py:1026-1038`). They do
  **not** consult `overtime_periods` — the ◀ ▶ arrows are a manual override
  path, not the automatic post-expiry flow.
- The **automatic** post-expiry offer (item 4 below, "period decision") is the
  one place `overtime_periods`/`shootout_enabled` actually filter what is
  *offered* — it never removes a label from the validation domain, only from
  the button choices shown at that moment. This gives one static, testable
  state-validation surface (same guarantee football's test suite relies on)
  while still letting `SoccerRules` turn overtime and the shootout on or off
  for the moment that matters (natural time expiry).

Two overtime periods (`OT1`, `OT2`) are both always in the label set; a rules
config of `overtime_periods=1` simply never offers `OT2` in the period-decision
prompt (§4) and a manual `set_period("OT2")` still works for a correction, the
same as `set_quarter("OT")` always working in football regardless of whether
that rules config expects to reach it.

### 1.2 `CardEvent` (frozen dataclass, mirrors `BallSpot`, `domain/state.py:284-304`)

```python
@dataclass(frozen=True, slots=True)
class CardEvent:
    team: str                      # "home" | "away"
    kind: str                      # "yellow" | "red"
    player_number: int | None      # 0..99, or None ("unknown/unassigned")
    period: str                    # one of PERIOD_LABELS, captured at the moment of the card
    clock_display: str             # the game clock's formatted string at that moment, e.g. "32:14" or "12:00" (halftime), captured — not recomputed later
```

Validation (in `__post_init__`, same style as `BallSpot.__post_init__`):
`team in TEAM_SIDES`, `kind in CARD_KINDS`, `player_number` is `None` or
`0..MAX_CARD_PLAYER_NUMBER`, `period in PERIOD_LABELS`, `clock_display` a
non-empty string. `clock_display` is captured text, not a `ClockValue`,
because a later game-clock correction must never retroactively rewrite a
card's historical display — the same reasoning that makes football's
`UndoEntry` capture plain values rather than references.

**Design choice — card counts are *derived*, not stored fields.** The brief
asks for both "per-team ... yellow, red counts (0..99)" and "cards as a list
... so cards can also be listed and corrected." Storing both a flat counter
*and* a list invites the counter and the list to disagree the moment a card is
removed by index or corrected. Recommendation: `SoccerState` stores only
`cards: tuple[CardEvent, ...] = ()`, and the counts are **computed
properties** on `SoccerState`:

```python
@property
def home_yellow_cards(self) -> int:
    return sum(1 for c in self.cards if c.team == "home" and c.kind == "yellow")
# ... home_red_cards, away_yellow_cards, away_red_cards likewise
```

This keeps the "0..99" fact true (`len(cards filtered)` can never exceed the
number of cards, which the operator can't push past what a real half-century
of infractions would produce, but nothing enforces 99 explicitly — a natural
consequence of deriving from a list rather than a magic ceiling) and it makes
`remove_card`/`correct` trivially consistent: change the tuple, the counts
update themselves. If the owner insists on flat authoritative counters
instead (e.g. to match a future "NCHSAA cumulative season tracking" feature
that only cares about totals, not who), the fallback is to keep both and make
`add_card`/`remove_card` a single atomic state change of *both* fields in one
`evolve()` call, exactly the discipline `BallSpot`+`down`+`distance` already
follow together in football's Field Assistant transitions
(`application/service.py:176-203`) — flagged here as the alternative, not the
recommendation.

### 1.3 `ShootoutKick` (frozen dataclass)

```python
@dataclass(frozen=True, slots=True)
class ShootoutKick:
    team: str            # "home" | "away"
    round: int           # 1-based; which round of the shootout this is, per team
    kicker_number: int | None   # 0..99, or None
    made: bool
```

Validation: `team in TEAM_SIDES`, `round >= MIN_SHOOTOUT_ROUND`,
`kicker_number` None or 0..99, `made` is `bool`.

### 1.4 `SoccerState` field list

```python
@dataclass(frozen=True, slots=True)
class SoccerState:
    schema_version: int = SOCCER_SCHEMA_VERSION
    app_version: str = APP_VERSION
    revision: int = 0

    home_name: str = DEFAULT_HOME_NAME     # 1..24 chars, trimmed — same rule as football's _require_name
    away_name: str = DEFAULT_AWAY_NAME

    home_score: int = 0                    # 0..MAX_SOCCER_SCORE
    away_score: int = 0

    period: str = "PRE"                    # one of PERIOD_LABELS
    lifecycle: str = "PRE_GAME"            # one of LIFECYCLE_LABELS

    game_clock: ClockValue = ClockValue(MAX_PREGAME_CLOCK_SECONDS, False, MAX_PREGAME_CLOCK_SECONDS)
    # No play_clock field at all — soccer has no play clock (§0.1).

    # Per-team match stats. Each 0..MAX_STAT_VALUE (99).
    home_shots: int = 0
    away_shots: int = 0
    home_saves: int = 0
    away_saves: int = 0
    home_corners: int = 0
    away_corners: int = 0
    home_fouls: int = 0
    away_fouls: int = 0

    # Cards: see §1.2. home_yellow_cards etc. are *properties*, not fields.
    cards: tuple[CardEvent, ...] = ()

    # Shootout tally. See §1.3 and §3 (commands) for how these move.
    shootout_first_kicker: str | None = None     # "home" | "away" | None (not started / not yet decided)
    shootout_kicks: tuple[ShootoutKick, ...] = ()
    shootout_winner: str | None = None           # "home" | "away" | None; set only by finish_shootout

    # F3-style crowd status, identical shape to football's (domain/state.py:339-346).
    game_status: str | None = None               # one of SOCCER_STATUS_LABELS, or None
    status_clock: ClockValue = ClockValue(0.0, False, MAX_STATUS_CLOCK_SECONDS)
    status_clock_cleared: bool = True
```

No `assistant_*` fields exist yet on this state — the soccer Field Assistant
(a later phase per `FABLE_PROMPT.md:156-163`) is not part of this checkpoint's
scope; it should add its own two persisted facts the same additive way
football's assistant did (`domain/state.py:69-76`), landing here later without
touching this design.

No clock-direction field. See §4 for why `SoccerRules.clock_direction` is a
rules value consulted only by formatting, not a state fact.

`evolve()`: identical mechanism to `GameState.evolve()`
(`domain/state.py:437-451`) — collect `fields(self)` names, reject unknown
keys, forbid `revision` in `changes`, bump revision by one, `dataclasses.replace`.

`state_revision`/`home_team_name`/`away_team_name` compatibility properties:
copy verbatim (`domain/state.py:423-435`) if any consuming code expects them;
otherwise drop them — nothing in this draft's view-model section needs them,
but keeping the same property names costs nothing and matches football's
naming exactly for a reader jumping between the two state modules.

`default_state()` — same shape as `domain/state.py:454-457`, returns
`SoccerState()`.

---

## 2. `SoccerRules` (frozen dataclass, `domain/soccer/rules.py`)

Mirrors `GameRules` (`domain/rules.py:82-187`): not game state, lives in
soccer's own `config.json` (under the soccer data root, §5), consulted only at
the moment a length loads (New Game, a period change, the crowd
INJURY/DELAY/WEATHER/LIGHTNING/OFFICIALS button) — never retroactively,
exactly like `domain/rules.py:10-17`'s documented contract.

```python
@dataclass(frozen=True, slots=True)
class SoccerRules:
    half_seconds: float = 40 * 60.0          # varsity default (NFHS 7-1); JV plays 35:00 — same field, different value, not a separate JV/varsity flag (see discussion below)
    halftime_seconds: float = 10 * 60.0      # NFHS 7-1 default; coaches may agree otherwise (still just a number here)
    pregame_seconds: float = MAX_PREGAME_CLOCK_SECONDS   # kickoff countdown, mirrors football's pregame_seconds exactly
    warmup_seconds: float = 3 * 60.0         # same WARMUP-label-at-N mechanism as football (domain/clocks.py:36-57), reused via soccer's own event_phase_for copy

    overtime_seconds: float = 10 * 60.0      # NCHSAA: "two complete 10-minute periods" for conference ties
    overtime_periods: int = 0                # 0, 1, or 2 — how many of OT1/OT2 the period-decision prompt offers (§1.1, §4); 0 is the NCHSAA regular-season default ("still tied → tie")
    golden_goal: bool = False                # NCHSAA conference-tie overtime plays full periods, not golden goal, per the research notes in CONTEXT_FOR_AGENTS.md — default off; flagged for the rules-research agent to confirm against the current handbook

    shootout_enabled: bool = True            # whether the period-decision prompt ever offers "Shootout" (NCHSAA: only non-conference tournament / playoff ties reach kicks from the mark)
    shootout_initial_kickers: int = DEFAULT_INITIAL_KICKERS   # 5, per NISOA/NFHS restatement
    shootout_credit_goal: bool = False        # see §3's discussion under finish_shootout — default OFF until rules research confirms NCHSAA's presentation convention

    mercy_differential: int = 9              # NCHSAA: 9-goal differential ends the match
    mercy_applies: str = "any_time"          # "halftime_only" | "any_time" — NCHSAA text says "9-goal differential at halftime or any time after"; default matches the broader reading

    stop_clock_on_goal: bool = False         # see §4 — operator-decided by default, NFHS 7-4 lists a goal as a clock-stop reason but does not mandate an automatic stop
    clock_direction: str = "down"            # "down" | "up" — see §4

    status_seconds: float = 60.0             # the crowd countdown's one-press default (mirrors football's timeout_seconds, domain/rules.py:43)
```

`period_seconds(label)` (mirrors `GameRules.period_seconds`,
`domain/rules.py:130-146`):

```python
def period_seconds(self, period: str) -> float | None:
    if period == "PRE":
        return self.pregame_seconds
    if period == "HALF":
        return self.halftime_seconds
    if period in ("OT1", "OT2"):
        return self.overtime_seconds
    if period in ("1st", "2nd"):
        return self.half_seconds
    return None   # SHOOTOUT, FINAL: no playable game-clock time
```

**HALF → 2nd resets nothing.** Football's `_quarter_clock_plan` resets
timeouts only on `HALF -> 3rd` (`application/service.py:1137-1141`) because
NFHS grants fresh timeouts per half. Soccer has no timeouts at all (control
refresh decision, `.scratch/` memory: "no timeouts in soccer"), so soccer's
period-clock-plan function (mirroring `_quarter_clock_plan`,
`application/service.py:1107-1142`) has **no** `resets_*` output at all — it
only decides `loads_seconds`/`maximum_seconds`, using the same
entering-or-leaving-an-interval-or-needs-a-fresh-clock logic. `HALF -> 2nd` is
therefore identical in kind to every other period move: it loads
`half_seconds` stopped, and nothing else resets, because there is nothing
else per-half to reset.

**Discussion — varsity/JV as a rule value vs. a separate flag.** The brief
asks for "half length varsity 40:00, JV option." Recommendation: **one
`half_seconds` field**, not a `level: "varsity"|"jv"` enum with two baked-in
lengths. The Setup drawer already lets an operator type any whole-second
value (football's own `RULE_FIELDS`/`_rule_fields_view` pattern,
`domain/rules.py:47-55`, `host/bridge.py:765-808`) — a JV game is simply "set
Half length to 35:00, set Overtime periods to 0" (NCHSAA JV plays no
overtime), the same way an 8-minute youth football quarter is just a
different `quarter_seconds` value today. Baking "varsity" and "JV" in as a
second field would be the only rule in either sport module that names a
competition level rather than a duration, and it would still need the two
literal numbers typed in somewhere — better to leave both numbers as the
single field's two common presets in the *page's* copy (a documented default,
not a domain concept) than to grow the rules dataclass with a mode switch
nothing else consults.

`from_payload`/`to_dict`/`with_changes`: copy the mechanism exactly
(`domain/rules.py:150-172`) — unknown keys ignored, missing keys keep
defaults, a bad value raises `RulesError` with an operator-facing sentence.

`RULE_FIELDS`-equivalent (`SOCCER_RULE_FIELDS`, drives the Setup drawer, same
3-tuple shape `(name, label, kind)` as `domain/rules.py:47-55`):

```
("half_seconds", "Half length", "clock")
("overtime_seconds", "Overtime period length", "clock")
("overtime_periods", "Overtime periods", "count")
("pregame_seconds", "Pregame countdown", "clock")
("halftime_seconds", "Halftime countdown", "clock")
("warmup_seconds", "Warmup label at", "clock")
("golden_goal", "Golden goal", "toggle")            # a new "kind" the Setup drawer needs; football's kinds are only clock/seconds/count today
("shootout_enabled", "Shootout after overtime", "toggle")
("shootout_initial_kickers", "Shootout kickers", "count")
("shootout_credit_goal", "Credit shootout winner a goal", "toggle")
("mercy_differential", "Mercy-rule goal differential", "count")
("mercy_applies", "Mercy rule applies", "choice")   # another new "kind"; values "halftime_only"/"any_time"
("clock_direction", "Game clock direction", "choice")  # values "down"/"up"
("stop_clock_on_goal", "Stop clock automatically on a goal", "toggle")
("status_seconds", "Crowd status countdown", "seconds")
```

The `"toggle"` and `"choice"` kinds are new — football's `_rule_fields_view`
(`host/bridge.py:788-808`) only ever formats `"clock"` (minutes/seconds
split) or falls through to `str(int(value))` for `"seconds"`/`"count"`. A
soccer bridge's own `_soccer_rule_fields_view` needs a small addition: for
`"toggle"`, `entry["display"] = "On" if value else "Off"`; for `"choice"`,
`entry["display"] = str(value)` plus an `entry["options"]` list the page
turns into a dropdown/segmented control. This lives entirely in the new
soccer bridge module — no change to football's `_rule_fields_view`.

---

## 3. Commands (`domain/soccer/commands.py`, mirrors `domain/commands.py`)

Own `SoccerCommandType(str, Enum)`, own `Command`/`CommandError`/
`CommandResult`/`EventIntent`/`UndoEntry` dataclasses — copy the shapes from
`domain/commands.py:194-291` verbatim (they hold no football-specific fields
except `action: FieldAction | None`, which soccer's `Command` drops until the
soccer Field Assistant phase adds its own `SoccerFieldAction` the same way).

### 3.1 Command table

| Command | Args | Validation | Undoable | Confirmed | History label (LAST strip) |
|---|---|---|---|---|---|
| `set_team_name` | `team, name` | 1..24 chars trimmed; only while `lifecycle in ("PRE_GAME",)` | no (not a scoring/lifecycle mistake class; mirrors football's `SET_TEAM_NAME` which is also absent from `UNDOABLE_COMMANDS`) | no | *(not shown — team names don't appear on the strip in football either)* |
| `add_goal` | `team, player: int\|None=None` | team in TEAM_SIDES; player None or 0..99 | **yes** | no | `"HOME goal · 1–0"` style, see §8 |
| `correct_goal` | `team` | team in TEAM_SIDES; rejects below 0 (`SCORE_BELOW_ZERO`-equivalent) | yes | no | `"HOME goal corrected · 1–1"` |
| `set_score` | `team, value` | 0..MAX_SOCCER_SCORE | yes | no | `"HOME score set to 3"` |
| `undo` | — | stack non-empty, else `NOTHING_TO_UNDO`/`NOT_UNDOABLE` | n/a (itself never undoable) | no | *(not itself shown — it replaces the strip with whatever it reversed, exactly like football)* |
| `period_forward` | — | index+1 in range, else `PERIOD_OUT_OF_RANGE` | conditionally, see below | **yes**, same confirmation-dialog contract as football's `_quarter_confirmation` | `"Period: 1st → HALF"` |
| `period_back` | — | index-1 in range | conditionally | yes | `"Period: 2nd → 1st"` |
| `set_period` | `label` | `label in PERIOD_LABELS` | conditionally | yes | `"Period: PRE → 1st"` |
| `new_game` | — | — | n/a (barrier) | yes | *(strip cleared)* |
| `end_game` | — | — | n/a (barrier) | no (mirrors football's `END_GAME`, which is not confirmed either — the Game drawer is itself the confirmation gate per the September 9 decision) | `"Game ended · FINAL"` |
| `game_clock_start` | — | — | no (clock commands are never undoable in football either) | no | *(not shown; clock state isn't a "LAST" fact any more than football's is)* |
| `game_clock_stop` | — | — | no | no | |
| `game_clock_reset` | — | — | no | no | |
| `game_clock_correct` | `seconds` | finite, ≥0, ≤ current maximum | no | no | |
| `add_stat` | `team, stat, step` | `stat in STAT_NAMES`; `step in (1, -1)` | **yes** | no | `"HOME shots +1 → 4"` |
| `set_stat` | `team, stat, value` | `stat in STAT_NAMES`; `0..MAX_STAT_VALUE` | yes | no | `"HOME shots set to 6"` |
| `add_card` | `team, kind, player: int\|None=None` | `kind in CARD_KINDS`; captures `period`/`clock_display` from current state | **yes** (compound: old/new = whole `cards` tuple, mirrors `FINALIZE_FIELD_ACTION`'s `old_values`/`new_values` pattern, `domain/commands.py:263-264`) | no, except a **second yellow to the same player/team is a send-off in real soccer** — flagged as an open rule question; default behavior below | `"AWAY yellow card #10 · 32:14"` |
| `remove_card` | `team, index` | `0 <= index < len(cards)` and `cards[index].team == team` | yes (compound, same pattern) | **yes** (removing a card is a correction with real disciplinary consequence — confirm) | `"Card removed: AWAY yellow #10"` |
| `set_shootout_first_kicker` | `team` | only while `period == "SHOOTOUT"` and `shootout_kicks == ()` | yes | no | `"Shootout: AWAY kicks first"` |
| `shootout_kick` | `team, made: bool, kicker: int\|None=None` | only while `period == "SHOOTOUT"`; `shootout_winner is None` | **yes** (compound: old/new = whole `shootout_kicks` tuple, same reasoning as `add_card`) | no | `"Shootout: HOME made (#7) · 3–2"` |
| `shootout_correct_kick` | `index, made: bool` | `0 <= index < len(shootout_kicks)` | yes (compound) | **yes** (rewrites a recorded result) | `"Shootout kick 4 corrected: missed → made"` |
| `shootout_remove_last` | — | `shootout_kicks` non-empty | yes (compound) | **yes** | `"Shootout: last kick removed"` |
| `finish_shootout` | `winner: str\|None=None` | see discussion below | n/a (barrier — major lifecycle event, like `new_game`) | **yes** | `"Shootout won by HOME, 4–3"` |
| `set_game_status` | `label, seconds: float\|None=None` | `label in SOCCER_STATUS_LABELS`; `seconds` whole, 1..300 | no (matches football's F3 exemption) | no | *(not on the strip — matches football)* |
| `clear_game_status` | — | — | no | no | |
| `status_clock_start` | — | — | no | no | |
| `status_clock_stop` | — | — | no | no | |

**`period_forward`/`period_back`/`set_period` undoable-or-barrier rule**:
copy `_handle_quarter`'s exact logic (`application/service.py:1040-1105`) —
if a clock is running, or the move loads a fresh period clock
(`period_seconds` differs from the current stopped value), the move is a
**barrier** (`clears_undo=True`, no `UndoEntry`), because Undo could not put
the discarded clock value back. Otherwise it is a plain undoable `period`
field change. This is not a soccer-specific decision; it is football's own
reasoning, restated for `SoccerRules.period_seconds`.

**Discussion — `add_card` and a second yellow.** Real soccer disqualifies a
player shown two yellows in one match (the second yellow *is* effectively a
red). The brief doesn't ask for player-level disqualification tracking (no
per-player state beyond the optional number on each `CardEvent`), so
recommend: **`add_card` never auto-escalates.** The operator records a second
yellow as a second `CardEvent(kind="yellow")` for the same player number, and
if the match result is a send-off they separately press the `red` card
control (or an explicit "2nd yellow = red" button that is pure UI sugar
sending two commands: `add_card(team, "yellow", player)` then
`add_card(team, "red", player)`). Auto-escalating inside the domain would
require tracking per-player state this design deliberately doesn't carry
(`player_number` is optional and not unique-checked), and NCHSAA's own
season-long tracking already happens outside this app
(`nchsaa.org/yellow-card-tracking`, cited in `CONTEXT_FOR_AGENTS.md:108-109`)
— the board's job is to log what the referee showed, not adjudicate it.

**Discussion — `finish_shootout`'s winner.** Recommend **derived by
default**: the service computes a winner from `shootout_kicks` using the
standard kicks-from-the-mark procedure (after both sides have taken their
`shootout_initial_kickers` attempts, whichever made more wins outright if
already mathematically decided sooner; beyond that, sudden death — first team
to lead after both have kicked in a round wins). `finish_shootout()` with no
`winner` argument is **rejected** (`INVALID_COMMAND`, "the shootout is not
yet decided") until the tally is decisive; `finish_shootout(winner="home")`
with an explicit winner is accepted *only if it agrees with the derived
winner* — this is not an override lever, it exists so the confirmation
dialog's accept action can pass back exactly the team it displayed, the same
closed loop football's quarter-confirmation uses (the dialog computes text
from the same function the commit path uses, `application/service.py:1257
-1315`). If the operator needs to end a shootout that is not decided (a
protest, a called match), that is a `new_game`/`end_game` situation, not a
`finish_shootout` one.

`shootout_credit_goal` (a `SoccerRules` flag, default `False`) controls
whether `finish_shootout` also applies `+1` to the winner's `home_score`/
`away_score` in the same transition. **This defaults off** because standard
association-football and NFHS convention is that kicks from the mark decide
the *match*, not the *score line* — a 1–1 draw that Home wins on kicks is
usually still reported as "1–1 (4–3 pens)," not "2–1." The brief's own
wording ("NCHSAA if the rules research confirms it") already treats this as
conditional; flag it explicitly in `.scratch/soccer-mode/rules_research.md`
as an open question for the rules-research agent, with the recommended
default of *not* crediting a goal until a primary NCHSAA source says the
scoreboard itself should show the shootout as an added goal.

### 3.2 Barriers (mirrors `NON_UNDOABLE_COMMANDS`, `domain/commands.py:172-178`)

`new_game`, `end_game`, `undo`, `finish_shootout`, and any `period_forward`/
`period_back`/`set_period` that stops a running clock or loads a fresh period
length (§3.1) clear the undo stack exactly as football's do
(`application/service.py:788,813-815`). Crowd-status commands
(`set_game_status`, `clear_game_status`, `status_clock_start`,
`status_clock_stop`) touch the stack **not at all** — neither undoable nor a
barrier — identical to football's F3 exemption
(`domain/commands.py:89-97`, `application/service.py:1389-1395`).

---

## 4. Clock semantics

**Countdown, always, at the engine level.** `SoccerGameClock` (§0.1) is a pure
copy of `GameClock`'s countdown-to-zero deadline math
(`domain/clocks.py:123-322`) — it always counts a `ClockValue.seconds` down
from `maximum_seconds` to `0`. This is deliberate: NFHS's own rule text
(`domain/state.py` football's own precedent, and the research notes in
`CONTEXT_FOR_AGENTS.md:100-101`, "visible clock counts down") makes countdown
the shipped default and the thing every existing engine primitive already
does well (deadline-based, monotonic, survives a tick-loop refresh).

**"Count up" is a display transform, not a different engine.**
`SoccerRules.clock_direction` (`"down"`|`"up"`) is consulted only by
`domain/soccer/formatting.py`'s clock formatter:

```python
def format_soccer_game_clock(seconds: float, maximum_seconds: float, *, direction: str) -> str:
    if direction == "up":
        return format_game_clock(max(0.0, maximum_seconds - seconds))  # reuses football's pure ceil-seconds formatter
    return format_game_clock(seconds)
```

This is the smallest possible seam: no new state field, no new engine, the
authoritative countdown value is unchanged, and correcting or resetting the
clock is still "how much time is left" everywhere in the domain and
persistence layers — only the operator/spectator page's displayed digits flip
for a league that runs an up-counting stadium clock (some NC programs do this
for a running "match clock" feel even though the underlying period still has
a fixed length and still expires at zero). If a future requirement needs a
true stopwatch with no maximum (count up with no expiry), that is a
materially different engine and out of scope for this checkpoint — flagged as
an open question rather than designed here.

**A goal does not stop the clock automatically**, matching NFHS 7-4's "clock
stopped ... after a goal" being a referee signal, not an automatic scoreboard
behavior (`CONTEXT_FOR_AGENTS.md:98-101`). `add_goal` never touches
`game_clock`. `SoccerRules.stop_clock_on_goal` (default `False`) is the
documented escape hatch if a school's officials want the automatic behavior;
when `True`, `_handle_add_goal` (mirroring `_handle_add_score`'s touchdown
side-effect pattern, `application/service.py:894-928`) also issues a
`game_clock.stop()` in the same transition, reported as part of the same
`add_goal` `UndoEntry.old_values`/`new_values` compound (so one Undo restores
both the score and the clock's running state together, exactly like
football's PL-6 touchdown Undo restores score and field status together).

**Natural expiry and the period-decision prompt.** Mirrors football's
`PERIOD_DECISION_QUARTERS`/`period_decision`
(`application/service.py:145-352`) exactly, retargeted:

- `PERIOD_DECISION_PERIODS = frozenset({"2nd", "OT1", "OT2"})` — the end of
  regulation and the end of each overtime period are decision points.
- On natural expiry in one of those periods (via the soccer service's own
  `observe_tick`, copying `application/service.py:423-492`'s shape), the
  service sets a runtime-only `_period_decision_pending = True` and bumps a
  token, exactly like football.
- The bridge's `period_decision` view exposes not just `pending`/`period`/
  `token` but a **`choices` list**, each `{label, command}` pair, computed
  from `SoccerRules` at that moment:
  - Leaving `2nd`: offer `OT1` if `overtime_periods >= 1`, else `SHOOTOUT` if
    `shootout_enabled`, else only `FINAL`. Always also offer `FINAL`
    ("declare it a tie/final now") and `"Keep"` (dismiss, re-arm on next
    expiry — mirrors football's PL-5 "Keep 4th").
  - Leaving `OT1`: offer `OT2` if `overtime_periods >= 2`, else `SHOOTOUT` if
    enabled, else `FINAL`; always also `FINAL`/`Keep`.
  - Leaving `OT2`: offer `SHOOTOUT` if enabled, else `FINAL`; always also
    `FINAL`/`Keep`.
  - Each non-`Keep` choice is just `set_period(label, confirmed=True)` (or,
    for `SHOOTOUT`, `set_period("SHOOTOUT", confirmed=True)` followed by the
    shootout panel appearing per `FABLE_PROMPT.md:133`) — the prompt is
    presentation over the same ordinary command, never a new command type.
- The prompt clears the same way football's does: any accepted command that
  restarts the clock, adds time, or changes the period/lifecycle
  (`_refresh_period_decision`, `application/service.py:385-397`).

**Mercy rule is a derived view flag, never automatic.** No state field.
`SoccerRules.mercy_differential`/`mercy_applies` plus the current score and
period are enough to compute, in the soccer bridge's view model:

```python
def _mercy_reached(state: SoccerState, rules: SoccerRules) -> bool:
    differential = abs(state.home_score - state.away_score)
    if differential < rules.mercy_differential:
        return False
    if rules.mercy_applies == "halftime_only":
        return state.period in ("HALF",) or state.lifecycle == "HALFTIME"
    return True   # "any_time"
```

`operator_view_model["mercy_reached"]` (a plain bool) drives a soft prompt the
same visual weight as the period-decision prompt but with **no command of its
own** — the operator's response is simply to press `end_game` (or `Keep`,
i.e. do nothing) through the ordinary Game drawer. This matches the brief's
"never automatic" instruction and keeps the mercy rule from inventing a new
lifecycle state.

**Pregame and halftime stay on the one game-clock engine**, exactly as
football's September 9, 2026 change (`domain/state.py:32-40`,
`INTERVAL_QUARTER_LABELS`): `INTERVAL_PERIOD_LABELS = {"PRE", "HALF"}` for
soccer too. `PRE` loads `SoccerRules.pregame_seconds`, `HALF` loads
`SoccerRules.halftime_seconds`, both stopped, both through the same
`SoccerGameClock` — no separate interval engine, no separate drawer, mirroring
`CONTEXT_FOR_AGENTS.md:34-35`'s framing of that decision precisely.

---

## 5. Snapshot shape and the `read_stored_game` seam

### 5.1 `application/soccer_snapshots.py`

`state_to_snapshot(state: SoccerState) -> dict`:

```json
{
  "sport": "soccer",
  "schema_version": 1,
  "app_version": "0.1.0",
  "state_revision": 42,
  "teams": {
    "home": {"name": "Eagles", "score": 2},
    "away": {"name": "Hawks", "score": 1}
  },
  "period": "2nd",
  "lifecycle": "IN_PROGRESS",
  "clocks": {
    "game": {"seconds": 1234.0, "running": true, "maximum_seconds": 2400.0}
  },
  "stats": {
    "home": {"shots": 8, "saves": 3, "corners": 4, "fouls": 6},
    "away": {"shots": 5, "saves": 5, "corners": 2, "fouls": 9}
  },
  "cards": [
    {"team": "away", "kind": "yellow", "player_number": 10, "period": "1st", "clock_display": "32:14"}
  ],
  "shootout": {
    "first_kicker": null,
    "winner": null,
    "kicks": []
  },
  "status": {
    "label": null,
    "clock": {"seconds": 0.0, "running": false},
    "clock_cleared": true
  }
}
```

The top-level `"sport": "soccer"` key exists so any future shared tooling
(diagnostics, a combined "what games exist" view, or a mistaken cross-load)
can tell the two snapshot shapes apart on sight without depending on which
`schema_version` number they happen to use — schema versions are already
per-sport (`SOCCER_SCHEMA_VERSION` is independent of football's
`SCHEMA_VERSION`, `domain/state.py:14`), so a wrong-sport load would otherwise
only fail deep inside key lookups with a confusing `KeyError`.

`snapshot_to_state`: same additive-tolerant pattern as football's
(`application/snapshots.py:91-174`) — `snapshot.get("stats", {})`,
`.get("cards", [])`, `.get("shootout", {})`, `.get("status", {})` each fall
back to `SoccerState()`'s defaults, so a snapshot written by an earlier build
of soccer (before, say, corners existed) still loads.

### 5.2 The `read_stored_game` / `GameStore` seam

`read_stored_game` (`infrastructure/persistence.py:420-456`) calls football's
`snapshot_to_state` directly at line 444 — this is the one hardcoded coupling
point the brief asks to resolve. The smallest fix:

```python
def read_stored_game(
    path: Path,
    *,
    decode: Callable[[Mapping[str, Any]], GameState] = snapshot_to_state,
) -> StoredGame | None:
    ...
    state = decode(json.loads(row["snapshot_json"]))
    ...
```

`decode` is keyword-only with football's own decoder as the default, so every
existing football call site (`inspect_recovery`, any test) needs **zero**
changes. `application/recovery.py`'s `inspect_recovery`
(`application/recovery.py:162-286`) gets the same additive keyword,
threaded through to its one `read_stored_game(paths.database)` call
(`application/recovery.py:183`) and its one `read_stored_game(paths.backup)`
call (`application/recovery.py:206`):

```python
def inspect_recovery(
    paths: ScoreboardPaths,
    *,
    diagnostics: Diagnostics | None = None,
    stamp: str | None = None,
    decode: Callable[[Mapping[str, Any]], Any] = snapshot_to_state,
) -> RecoveryReport:
    ...
    stored = read_stored_game(paths.database, decode=decode)
```

`application/soccer_recovery.py` then simply calls
`inspect_recovery(soccer_paths, decode=soccer_snapshot_to_state)`. No change
to `GameStore` itself is needed — `GameStore` never decodes a snapshot; it
only writes `state_to_snapshot(state)` JSON blobs it is handed
(`record_command`/`checkpoint`, `infrastructure/persistence.py:682,845`,
neither of which imports `snapshot_to_state`) and reads them back verbatim as
JSON for `read_action_history`. `GameStore.open`
(`infrastructure/persistence.py:559-581`) needs no `decode` parameter — a
soccer `GameStore` instance is simply opened against soccer's own database
path (§5.3) using the exact same class, unmodified.

`stopped_state` (`infrastructure/persistence.py:505-517`) is a pure
`dataclasses.replace` over any object with `game_clock`/`play_clock`
attributes; it will need one small conditional or a soccer-side copy, because
`SoccerState` has no `play_clock`. Recommendation: a two-line soccer-local
`soccer_stopped_state(state: SoccerState) -> SoccerState` in
`application/soccer_recovery.py` that only stops `game_clock` and
`status_clock` (soccer has no play clock to stop) — do not touch football's
`stopped_state`.

`validate_database`/`promote_backup`/`DATABASE_SCHEMA_VERSION`/`apply_schema`/
`connect` (`infrastructure/persistence.py:383-417`, and the `GameStore`
class itself, `infrastructure/persistence.py:523-682+`) are sport-agnostic —
they operate on a SQLite file's structure and a JSON blob column, never on
`GameState`'s Python type. **Recommendation: reuse the entire `GameStore`
class and schema unmodified**, pointed at a soccer-specific `scoreboard.db`/
`scoreboard.backup.db` pair under `<data root>/soccer/` (already specified in
`CONTEXT_FOR_AGENTS.md:79`). This is the only seam this checkpoint needs
inside `infrastructure/persistence.py`: the one `decode` keyword on
`read_stored_game`.

### 5.3 Data layout (confirms `CONTEXT_FOR_AGENTS.md:77-79`)

```
<data root>/soccer/scoreboard.db
<data root>/soccer/scoreboard.backup.db
<data root>/soccer/config.json        # holds SoccerRules under "rules", same shape football's config.json uses
<data root>/soccer/layouts.json
<data root>/soccer/cutscenes.json
<data root>/soccer/cutscenes/
<data root>/teams.json                # shared, read-only schema — same schools/colors library football already uses
```

---

## 6. Formatting (`domain/soccer/formatting.py`)

Reuses football's pure numeric formatters directly
(`ceil_seconds`, `format_game_clock`, `BLANK_DISPLAY`, `FormattingError` —
all sport-agnostic functions of a float, `domain/formatting.py:65-130`).
Adds:

```python
def format_soccer_game_clock(seconds, maximum_seconds, *, direction="down") -> str:
    # see §4 — direction="up" is elapsed = maximum - remaining
    ...

PERIOD_DISPLAY: Final[dict[str, str]] = {
    "PRE": "Pregame",
    "1st": "1st Half",
    "HALF": "Halftime",
    "2nd": "2nd Half",
    "OT1": "OT 1",
    "OT2": "OT 2",
    "SHOOTOUT": "Shootout",
    "FINAL": "Final",
}

def format_period(period: str) -> str:
    return PERIOD_DISPLAY.get(period, period)

def format_card_summary(cards: tuple[CardEvent, ...], team: str) -> str:
    # "Y: 2 · R: 0"
    yellow = sum(1 for c in cards if c.team == team and c.kind == "yellow")
    red = sum(1 for c in cards if c.team == team and c.kind == "red")
    return f"Y: {yellow} · R: {red}"

def format_card_row(card: CardEvent) -> str:
    # "#10 32:14 1st" — blank player number renders as "—"
    number = f"#{card.player_number}" if card.player_number is not None else "—"
    return f"{number} {card.clock_display} {format_period(card.period)}"

def format_shootout_side(kicks: tuple[ShootoutKick, ...], team: str) -> str:
    # "● ○ ●" for one side, chronological
    return " ".join("●" if k.made else "○" for k in kicks if k.team == team)

def format_shootout_tally(kicks: tuple[ShootoutKick, ...]) -> str:
    # "● ○ ● – ● ● ○"  (home – away)
    home = format_shootout_side(kicks, "home")
    away = format_shootout_side(kicks, "away")
    return f"{home} – {away}" if (home or away) else BLANK_DISPLAY

def format_stat(label: str, value: int) -> str:
    # format_stat("S", 4) -> "S 4"; mirrors format_timeouts's "TO 3" convention (domain/formatting.py:248-255)
    return f"{label} {value}"

STAT_LABELS: Final[dict[str, str]] = {"shots": "S", "saves": "SV", "corners": "COR", "fouls": "F"}
```

`format_game_status` for soccer's crowd word is football's own function,
reused as-is (`domain/formatting.py:133-142`) — it is a pass-through of a
label string, not football-typed.

---

## 7. View-model dotted paths (operator and spectator)

Mirrors football's `spectator_view_model`/`operator_view_model`
(`host/bridge.py:652-871+`) naming exactly where the concept matches, with a
`soccer.` namespace for what's new:

```
schema_version
revision
teams.home.name / teams.home.score
teams.away.name / teams.away.score
period                              # compact label, e.g. "2nd" — same role as football's "quarter"
period_display                      # "2nd Half" — same role as football's "quarter_display"
lifecycle
clocks.game.seconds / .running / .display / .status / .maximum_seconds / .full_display / .label
clocks.event.*                      # PRE/HALF interval countdown, identical shape to football's clocks.event (host/bridge.py:721-740)

soccer.home.shots / soccer.home.saves / soccer.home.corners / soccer.home.fouls
soccer.away.shots / soccer.away.saves / soccer.away.corners / soccer.away.fouls
soccer.home.shots_display / ...     # "S 4" etc., Python-formatted (mirrors football's rendered strings never being composed in JS)
soccer.home.cards.yellow / soccer.home.cards.red     # counts
soccer.home.cards.display                            # "Y: 2 · R: 0"
soccer.home.cards.rows              # [{team, kind, player_number, period, period_display, clock_display, row_display}, ...] for the Corrections drawer's list
soccer.away.cards.* (mirrors home)

soccer.shootout.active               # bool: period == "SHOOTOUT"
soccer.shootout.first_kicker
soccer.shootout.winner
soccer.shootout.home_display         # "● ○ ●"
soccer.shootout.away_display
soccer.shootout.tally_display        # "● ○ ● – ● ● ○"
soccer.shootout.next_team            # whose kick is next, derived from kicks/first_kicker/round
soccer.shootout.round                # current round number
soccer.shootout.sudden_death         # bool

status.label / status.display / status.clock.seconds / status.clock.running / status.clock.display

mercy_reached                        # bool, §4
period_decision.pending / .period / .token / .choices   # choices: [{label, command, args}]

rules                                 # SoccerRules.to_dict()
rule_fields                           # SOCCER_RULE_FIELDS view, §2
status_labels                         # list(SOCCER_STATUS_LABELS)
status_clock_presets                  # [30, 60, 90] — same three football offers, no soccer-specific change needed here

last_action                           # _last_action_view-equivalent; see §8
can_undo
```

`quarter_labels`-equivalent → `period_labels` (`list(PERIOD_LABELS)`), same
role as `host/bridge.py:847`.

---

## 8. History labels for the "LAST:" strip

Mirrors `_last_action_view`/`_LAST_ACTION_SUBJECTS`
(`host/bridge.py:443-536+`). Each row is `{command, team, field, old_value,
new_value, label}` — Python renders `label`, the page only displays it.

| Command | `label` template |
|---|---|
| `add_goal` | `"{TEAM} goal · {home_score}–{away_score}"` |
| `correct_goal` | `"{TEAM} goal corrected · {home_score}–{away_score}"` |
| `set_score` | `"{TEAM} score set to {value}"` |
| `period_forward` / `period_back` / `set_period` | `"Period: {old} → {new}"` (mirrors football's implicit "quarter" wording, composed the same way `_last_action_view` composes score labels today) |
| `add_stat` | `"{TEAM} {STAT_LABEL} {+1|-1} → {new_value}"`, e.g. `"HOME S +1 → 4"` |
| `set_stat` | `"{TEAM} {stat} set to {value}"` |
| `add_card` | `"{TEAM} {kind} card {player_display} · {period_display} {clock_display}"`, e.g. `"AWAY yellow card #10 · 1st Half 32:14"` |
| `remove_card` | `"Card removed: {TEAM} {kind} {player_display}"` |
| `set_shootout_first_kicker` | `"Shootout: {TEAM} kicks first"` |
| `shootout_kick` | `"Shootout: {TEAM} {made|missed} {player_display} · {home_makes}–{away_makes}"` |
| `shootout_correct_kick` | `"Shootout kick {index+1} corrected: {old} → {new}"` |
| `shootout_remove_last` | `"Shootout: last kick removed"` |
| `finish_shootout` | `"Shootout won by {TEAM}, {home_makes}–{away_makes}"` |
| `undo` | *(no row of its own — the strip shows whatever it just reversed, exactly as football's does since Undo pops the stack rather than pushing a new "Undo" entry, `application/service.py:962-1022`)* |

`new_game`/`end_game`/crowd-status commands: no strip row, matching football
(they are barriers/exempt, §3.2, and football's own strip never shows
`NEW_GAME`/`END_GAME`/`SET_GAME_STATUS` either — confirm by inspection of
`_last_action_view`'s callers, which are only fed `service.undo_entry`, and
none of those command types ever produce an `UndoEntry`).

---

## Open questions this draft surfaces (for the rules-research agent / the owner)

1. **`shootout_credit_goal` default** (§3.1) — does NCHSAA's presentation
   convention add a goal to the match score for the shootout winner, or only
   record kicks separately? Recommended default: **off** until a primary
   source says otherwise.
2. **`golden_goal` default** (§2) — `CONTEXT_FOR_AGENTS.md`'s research notes
   say NCHSAA conference-tie overtime plays full periods, not golden goal;
   confirm against the *current* handbook (the notes flag themselves as
   needing re-verification).
3. **`mercy_applies` default** (§2) — "halftime or any time after" reads as
   `"any_time"` to this draft; confirm the precise handbook wording.
4. **Second-yellow escalation** (§3.1) — confirmed as *not* automatic in this
   design; flag to the owner in case they want a one-button "2nd yellow = red"
   UI shortcut in the operator spec (a pure UI composition, no domain change
   needed either way).
5. **`clock_direction` default** — this draft assumes `"down"` is the shipped
   default for every NCHSAA game (matches the football precedent and the
   research notes' "visible clock counts down"); the `"up"` option exists
   only because the brief asked the possibility be configurable, not because
   research has found a program that needs it. Confirm no NCHSAA venue
   actually requires an up-counting stadium clock before shipping the toggle
   as visible UI (it can ship hidden/advanced if unconfirmed).
