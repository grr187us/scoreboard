# F3 (crowd-facing game-state messages) and I4 (undo history) — agreed design

**Implementation status, September 6, 2026:** I4 is implemented as the agreed
20-entry in-memory LIFO stack. F3 is only partially implemented: the two layout
and renderer slots exist, but authoritative state, timing, commands, bridge
values, operator controls, and end-to-end tests do not.

This is the single source of truth for both features. Every worker reads it
first and does not re-litigate the decisions here. Anything not written here is
an ordinary judgement call: follow the surrounding code's grain.

Repository conventions that apply to every part of this work:

* Python owns every displayed string. JavaScript copies values; it never
  derives one. New display text is produced in `domain/formatting.py` and
  reaches the view through `host/bridge.py`.
* One accepted command advances exactly one state revision. A rejected command
  changes nothing and returns a plain-language code plus message; expected
  validation failures are returned, never raised.
* `domain/state.py` must not import `domain/commands.py`.
* No domain object crosses the bridge — the bridge speaks plain JSON.
* Tests sit at the lowest layer that can prove the behaviour (see
  `tests/README.md`). Every new behaviour gets a test, and each new test file
  gets a row in the `tests/README.md` table.
* Run the suite as:
  `PATH="$PATH:/c/Program Files/nodejs" SCOREBOARD_DATA_DIR=<temp dir> ./.venv/Scripts/python.exe -m unittest discover -s tests`
  Node must be on PATH or the three `tests/ui` browser checks error out.
  Baseline before this work: **837 tests, 0 failures, 0 errors, 3 skipped**.
  Reconciled working-tree result: **853 tests, 0 failures, 0 errors, 3 skipped**.

---

## Part 1 — F3: crowd-facing game-state messages

### What it is

The wall gains two new spectator widgets: a **crowd message** (one of `FLAG`,
`TIMEOUT`, `INJURY`, `DELAY`, or nothing) and a **status countdown** beside it,
so a stoppage is explained on the board instead of the board simply freezing.
The operator toggles both live from an always-visible row.

### Deliberate limits (do not widen)

* The wall shows the **status word only** — no team name. The board's free
  space cannot hold `TIMEOUT — <24-character name>` legibly at the default
  geometry, and inventing a narrower composed string would put display logic in
  two places. Which team called a timeout is already shown by the existing
  `timeout_used` command and the timeouts readout. An operator who wants the
  team on the wall can restyle/enlarge the widget in the layout editor.
* The status is **not** part of undo. It is presentation, and consuming the
  undo slot (or, after I4, a stack entry) with a crowd toggle would push a real
  scoring mistake out of reach. `set_game_status` / `clear_game_status` /
  `status_clock_start` / `status_clock_stop` appear in **neither**
  `UNDOABLE_COMMANDS` nor `NON_UNDOABLE_COMMANDS`, exactly like the clock
  commands, so they leave the undo stack untouched.
* The message does **not** clear itself when the countdown expires. The
  countdown reaching `0:00` is itself information the crowd wants; the operator
  clears the message when play resumes.
* The Field Assistant does **not** raise `FLAG` automatically. Opening a draft
  in a separate window must not mutate authoritative state. The operator
  presses `FLAG`.

### Domain — `src/scoreboard/domain/state.py`

Add:

```python
GAME_STATUS_LABELS: Final[tuple[str, ...]] = ("FLAG", "TIMEOUT", "INJURY", "DELAY")
MAX_STATUS_CLOCK_SECONDS: Final[float] = 300.0
```

New `GameState` fields (append after `play_clock_cleared`, keeping every
existing default unchanged):

```python
game_status: str | None = None
status_clock: ClockValue = ClockValue(0.0, False, MAX_STATUS_CLOCK_SECONDS)
status_clock_cleared: bool = True
```

Validation in `__post_init__`, in the module's existing style:

* `game_status` is `None` or a member of `GAME_STATUS_LABELS`; anything else
  raises `StateValidationError`.
* `status_clock` must be a `ClockValue` whose `maximum_seconds ==
  MAX_STATUS_CLOCK_SECONDS`.
* `status_clock_cleared` must be a bool.

### Domain — `src/scoreboard/domain/clocks.py`

Add `STATUS_CLOCK_PRESETS: Final[tuple[float, ...]] = (30.0, 60.0, 90.0)` and a
`StatusCountdown` engine, modelled directly on `PlayClock` (same immutable
frozen dataclass, same monotonic-deadline math, same `revision` bookkeeping):

* `value: ClockValue = ClockValue(0.0, False, MAX_STATUS_CLOCK_SECONDS)`
* `from_state(state)` reads `state.status_clock`.
* `current_value(now)` / `remaining_at(now)` / `seconds` / `running` /
  `maximum_seconds` / `expired` — copy `PlayClock`'s semantics exactly,
  including the "a running clock past its deadline materializes as stopped at
  0.0" rule.
* `load_preset(seconds, *, now=None)` accepts only a member of
  `STATUS_CLOCK_PRESETS` (raise `StateValidationError` otherwise, mirroring
  `_validate_preset`); loads stopped.
* `start(now)`, `stop(now)`, `clear(now)`, `expire(now)`,
  `to_clock_value(now)`, `apply_to_state(state)`.
* No `correct` and no `reset` — the operator reloads a preset instead. Do not
  add them speculatively.

Keep `PlayClock`'s `_validate_preset` untouched; write a sibling validator for
the status presets rather than widening the play clock's.

### Domain — `src/scoreboard/domain/formatting.py`

Add, in the module's existing style and with the same "returns a string, never
raises for in-range input" contract:

* `format_game_status(label: str | None) -> str` — the label, or `""`.
* `format_status_clock(seconds: float, *, blank_at_zero: bool) -> str` —
  `M:SS` (`"1:00"`, `"0:07"`, `"0:00"`), and `""` when `blank_at_zero` is true
  and the value is zero. Round the same way `format_game_clock` does so a
  running countdown never shows a value the operator has not reached yet.
  Reuse `format_game_clock`'s helper if there is one rather than re-deriving
  minute/second arithmetic.

### Domain — `src/scoreboard/domain/commands.py`

Four new `CommandType` members:

```python
SET_GAME_STATUS = "set_game_status"
CLEAR_GAME_STATUS = "clear_game_status"
STATUS_CLOCK_START = "status_clock_start"
STATUS_CLOCK_STOP = "status_clock_stop"
```

New error codes `INVALID_GAME_STATUS` and `INVALID_STATUS_CLOCK_PRESET`
(exported in `__all__` with the others).

`validate_command` shape rules:

* `SET_GAME_STATUS` requires `label` in `GAME_STATUS_LABELS`; `seconds` is
  optional and, when present, must be a member of `STATUS_CLOCK_PRESETS`.
  Reject with `INVALID_GAME_STATUS` / `INVALID_STATUS_CLOCK_PRESET`.
* `CLEAR_GAME_STATUS`, `STATUS_CLOCK_START`, `STATUS_CLOCK_STOP` take no
  arguments.

None of the four goes in `UNDOABLE_COMMANDS` or `NON_UNDOABLE_COMMANDS`.
Add matching module-level factory helpers beside the existing ones.

### Application — `src/scoreboard/application/service.py`

* `_Transition` gains `status_clock: StatusCountdown | None = None`.
* `__init__` builds `self._status_clock = StatusCountdown.from_state(initial,
  monotonic_clock=monotonic)`; expose a read-only `status_clock` property
  beside `play_clock`.
* `materialized_state` includes
  `status_clock=self._status_clock.to_clock_value(now=current)`.
* `_apply` commits `transition.status_clock` the way it commits the other three
  engines, and — inside the same `if command.type is not
  CommandType.FINALIZE_FIELD_ACTION:` branch that already materializes the
  other clocks — adds
  `changes.setdefault("status_clock", status_clock.to_clock_value(now=now))`.
* `observe_tick` commits natural expiry for the status clock exactly as it
  already does for the play clock: when a running status clock has run to zero,
  replace the engine with `expire(now)` and `dataclasses.replace` the state's
  `status_clock` (no revision advance — this is a system observation).
  `status_clock_cleared` stays `False` on natural expiry, so the wall shows
  `0:00`; only `clear_game_status` sets it back to `True`.
* Handlers:
  * `_handle_set_game_status` — sets `game_status`. When `command.seconds` is
    present, loads that preset and starts it in the same transition (one
    revision, the `play_clock_preset_start` precedent) and sets
    `status_clock_cleared=False`; when absent, clears the status clock and sets
    `status_clock_cleared=True`. `EventIntent(field="game_status", old_value=<previous label>, new_value=<label>)`.
  * `_handle_clear_game_status` — `game_status=None`, status clock cleared,
    `status_clock_cleared=True`. Same event field.
  * `_handle_status_clock_start` / `_handle_status_clock_stop` — mirror the
    play-clock handlers, `EventIntent(field="status_clock", old/new=_clock_snapshot(...))`.
    Starting a clock that is at zero is a no-op start (same as `PlayClock.start`).
* Register all four in the handler table.

### Application — `src/scoreboard/application/snapshots.py`

`state_to_snapshot` gains a top-level `"status"` block; keep it additive and
readable:

```python
"status": {
    "label": state.game_status,
    "clock": {"seconds": state.status_clock.seconds,
              "running": state.status_clock.running},
    "clock_cleared": state.status_clock_cleared,
},
```

`snapshot_to_state` reads `snapshot.get("status", {})` and falls back to the
fresh-`GameState()` defaults, exactly the way `football` and `assistant`
already do, so a game saved before this change still recovers (P-004, P-006).
Add a test proving a pre-status snapshot loads.

### Host — `src/scoreboard/host/bridge.py`

* `_ALLOWED_ARGUMENTS`: `SET_GAME_STATUS: frozenset({"label", "seconds"})`, the
  other three `frozenset()`.
* `spectator_view_model` gains a top-level `"status"` block — this is what both
  the wall and the operator read:

```python
"status": {
    "label": state.game_status,
    "active": state.game_status is not None,
    "display": format_game_status(state.game_status),
    "clock_display": format_status_clock(
        state.status_clock.seconds, blank_at_zero=state.status_clock_cleared
    ),
    "clock": _clock_view(
        state.status_clock.seconds,
        state.status_clock.running,
        <the same clock_display string>,
    ),
},
```

  `status.display` is `""` when there is no message and `status.clock_display`
  is `""` when the countdown is cleared: the two spectator widgets are optional
  and hide themselves on empty text, which is how they stay off the wall until
  the operator raises one.
* `operator_view_model` additionally sets
  `model["status_labels"] = list(GAME_STATUS_LABELS)` and
  `model["status_clock_presets"] = [30, 60, 90]`.
* `_record_expirations` also notices a status clock that ran itself to zero and
  records it, in the same shape as the existing play-clock expiry note.

### Presentation — `src/scoreboard/presentation/layout.py` (+ the `board.js` mirror)

Two new widgets in the **game** registry only (the event screens keep their
eight widgets unchanged):

| id | label | field | group |
|---|---|---|---|
| `status_message` | `Crowd message` | `status.display` | `Status` |
| `status_clock` | `Status countdown` | `status.clock_display` | `Status` |

* Append both to `WIDGET_IDS`, `WIDGET_LABELS`, `WIDGET_FIELDS`,
  `OPTIONAL_WIDGET_IDS`, and `WIDGET_GROUPS`; `WIDGET_GROUP_ORDER` becomes
  `("Teams", "Clocks", "Field", "Status")`.
* Neither is in `WIDGET_TEXTS` (both draw a real value).
* Default geometry — these coordinates were chosen so that **no pair of
  visible default widgets overlaps at all**; they sit in the two free gaps of
  the band between the score block (ends `y = 0.406`) and the game clock
  (starts `y = 0.470`), between the three `visible: False` defaults that
  already live there (`home_timeouts` `x 0.040–0.240`, `game_clock_label`
  `x 0.400–0.600`, `away_timeouts` `x 0.760–0.960`). Do not move those three,
  and do not widen these two into them — an operator who later turns the
  timeouts on must not get a serious-overlap error:

```python
"status_message": {
    "id": "status_message", "visible": True,
    "x": 0.240, "y": 0.408, "width": 0.160, "height": 0.056,
    "font_scale": 0.026, "color": "#FFC845",
    "text_align": "center", "vertical_align": "middle",
    "font_weight": 800, "z_index": 0,
},
"status_clock": {
    "id": "status_clock", "visible": True,
    "x": 0.600, "y": 0.408, "width": 0.160, "height": 0.056,
    "font_scale": 0.026, "color": "#FFC845",
    "text_align": "center", "vertical_align": "middle",
    "font_weight": 800, "z_index": 0,
},
```

  Verify the arithmetic yourself before writing the tests: `status_message`
  spans `x 0.240–0.400`, `status_clock` spans `x 0.600–0.760`, both
  `y 0.408–0.464`, and every visible default widget's rectangle is disjoint
  from both. If a rectangle does touch one, adjust the *new* widget, never an
  existing one, and say so in your report.
* `LAYOUT_SCHEMA_VERSION` stays `3`. This is an additive registry change: a
  stored layout that predates it is missing the two ids, which the validator
  already treats as a warning and fills from the default.
* Mirror **all** of the above in `src/scoreboard/views/shared/board.js`'s
  `WIDGET_IDS` / `WIDGET_FIELDS` / `OPTIONAL_WIDGET_IDS` / `DEFAULT_LAYOUT`
  JSON literals. Those literals are parsed as strict JSON by
  `tests/integration/test_spectator_layout_render.py`: double-quoted keys and
  strings, no trailing commas, no comments inside the braces, no computed
  values.
* The layout editor builds its rail from `widget_descriptors()`, so both
  widgets should appear there with no editor change. Confirm that by reading
  the descriptor code and say so; if a hard-coded group list needs the new
  `Status` group, add it.

---

## Part 2 — I4: an undo history instead of one global level

### What it is

`ScoreboardService` keeps a bounded **stack** of reversible transitions instead
of a single entry, so a second undoable action no longer forecloses fixing the
first, and the operator can see the whole stack before spending it.

### Rules (do not widen)

* Strictly last-in-first-out. `UNDO` always reverses the newest entry and pops
  it; there is no "undo that one instead" affordance, because restoring an old
  value out of order would produce a state no sequence of commands could have
  produced.
* A command that is **not** undoable is still a **barrier**: it clears the
  whole stack and records `_undo_blocked_by`, exactly as today. Silently
  skipping past an un-undoable action to reverse an older one is the failure
  mode this finding is about; the fix is to *show* the stack, not to walk past
  a barrier. Every existing test that asserts "after `new_game` there is
  nothing to undo" must keep passing unchanged.
* `MAX_UNDO_DEPTH: Final[int] = 20` in `domain/commands.py`. Pushing onto a
  full stack drops the oldest entry.
* The stack is in-memory only, as `UndoEntry`'s docstring already says: a
  restart starts empty. Do not persist it.

### `src/scoreboard/application/service.py`

* Replace `self._undo: UndoEntry | None` with
  `self._undo_stack: list[UndoEntry]` (keep `self._undo_blocked_by`).
* Keep the existing `undo_entry` property working — it returns
  `self._undo_stack[-1] if self._undo_stack else None` — so every current
  caller (`host/bridge.py`'s `_last_action_view`, the tests) is unchanged.
* Add `undo_history` returning a **newest-first tuple** of the entries.
* `_Transition` gains `pops_undo: bool = False`; `_handle_undo` returns
  `pops_undo=True` and **stops** returning `clears_undo=True`.
* `_apply`'s commit block becomes, in effect:
  * `UNDO` accepted → pop the entry it just reversed; leave the rest of the
    stack and `_undo_blocked_by` alone (it is `None` whenever the stack is
    non-empty).
  * an undoable command → push, cap at `MAX_UNDO_DEPTH`, clear
    `_undo_blocked_by`.
  * `clears_undo` or a member of `NON_UNDOABLE_COMMANDS` → empty the stack and
    set `_undo_blocked_by`.
  Keep the existing comment's point: the declared eligibility sets have the
  final say, so a handler can never quietly make a dangerous command undoable.
* `_handle_undo`'s `NOTHING_TO_UNDO` / `NOT_UNDOABLE` messages and codes are
  unchanged.

### `src/scoreboard/host/bridge.py`

* `operator_view_model` gains
  `model["undo_history"] = [_last_action_view(entry) for entry in service.undo_history]`
  (newest first, already-rendered labels — the page must not build a label) and
  `model["undo_depth"] = len(model["undo_history"])`.
* `last_action` and `can_undo` keep their current meaning and shape.
* `_last_action_view` is unchanged.

---

## Part 3 — the operator page (both features)

`src/scoreboard/views/operator/index.html`, `operator.css`, `operator.js`.

### F3 controls

An **always-visible** crowd row. F3's complaint is precisely that the existing
free text is "decorative and pre-positioned, not a live toggle", so these must
not be buried in a drawer.

* Preferred shape: a new `.crowd-bar` grid row between `.board` and
  `.quarter-bar`. `body`'s `grid-template-rows` becomes
  `auto auto minmax(0, 1fr) auto auto auto`; `.crowd-bar { grid-row: 4 }`,
  `.quarter-bar { grid-row: 5 }`, `.tools { grid-row: 6 }`. Only the board row
  flexes, so the new row costs the board its height and nothing scrolls.
* Contents, left to right: a `CROWD` label; a status chip `#crowd-status`
  showing `status.display` or `—`; `FLAG`, `TIMEOUT`, `INJURY`, `DELAY`
  buttons; `CLEAR`; the countdown `#crowd-clock` bound to
  `status.clock_display`; `START` and `STOP`.
* Wiring, using the existing generic `data-command` path — no new dispatch code:
  * `data-command="set_game_status" data-label="FLAG"` (and `INJURY`, `DELAY`).
  * `TIMEOUT` is `data-command="set_game_status" data-label="TIMEOUT"
    data-seconds="60"` — one press raises the message and starts the 1:00
    countdown, the `play_clock_preset_start` precedent.
  * `CLEAR` is `data-command="clear_game_status"`.
  * `START`/`STOP` are `data-command="status_clock_start"` /
    `"status_clock_stop"`.
  * No confirmation on any of them: a crowd message is instantly reversible and
    the whole point is speed.
* In `render()`: set the chip text from `model.status.display` (falling back to
  `—`), mark the button matching `model.status.label` with the existing
  `is-active` class, and use the existing `markState` helper for START/STOP the
  way the other clocks do. Read only from the view model.
* `TIMEOUT` sits next to — and does not replace — the existing `timeout_used`
  controls. The crowd button shows the word on the wall; `timeout_used` charges
  the timeout. Two separate commands with different undo semantics; say so in a
  comment.

### I4 controls

* The `LAST:` strip becomes the way in: replace the plain `<span
  class="last-action">` with a button (`#last-action-button`,
  `data-action="open_history"`) that still shows `LAST: <label>` and adds a
  small depth badge (`#undo-depth`, e.g. `×3`, hidden at 0 or 1).
* New drawer `#history-drawer` (`aria-label="Undo history"`) listing
  `model.undo_history` newest first, built the way `renderDisplays` /
  `renderTeams` build their lists — each row is the entry's already-rendered
  `label`, the first row marked as the one the next `UNDO` reverses. Include a
  hint that Undo reverses them in order, newest first, and that an action that
  cannot be undone clears the list. Put an `UNDO` button
  (`data-command="undo"`) and a `Close` in the drawer so the operator can walk
  back while watching the list. Add `'history-drawer'` to `closeDrawers()`'s
  list and an `open_history` branch in `handleAction`.
* Do not add a footer button — the tool bar is already at its width budget at
  1093 px (C5).

### Sizing acceptance (this is a hard gate, C5/U-001)

Measure with the repo's own Playwright/Edge setup at **1093×614** and
**1180×720** and report the numbers:

* `document.documentElement.scrollHeight === document.documentElement.clientHeight`
  and no horizontal overflow at both sizes.
* Every crowd-row button is at least 36 px tall (the `.quarter-bar button`
  floor) and every existing 44 px control (`#reopen-display`, `#open-display`,
  the display-drawer rows) is still 44 px.
* Every clock button is still inside the viewport.

If the extra row will not fit, the documented fallback is to fold the crowd
controls into the quarter bar as a single row (dropping the `CROWD` label text
and the `is-active` chip) rather than moving them into a drawer. Report which
shape you shipped.

---

## Documentation (owned by the coordinator, not the workers)

`docs/ARCHITECTURE.md`, `docs/MVP_REQUIREMENTS.md`, `docs/UX_AND_LAYOUT.md`,
`docs/PROJECT_STRUCTURE.md`, `PROJECT_ROADMAP.md`, and `tests/README.md` rows.
Workers add their own `tests/README.md` row and nothing else in `docs/`.
