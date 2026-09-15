# Soccer-mode seams audit

Read-only research for the spec checkpoint. Every finding below was verified by
reading the named file directly (line numbers cited are from the
`feature/soccer-mode` branch as read on September 15, 2026). Nothing under
`src/`, `tests/`, `tools/`, or `docs/` was edited to produce this document.

Overall conclusion up front: the codebase's existing seams are already good.
Zero `if sport == ...` branches are required **inside any existing football
code path** (service handlers, bridge view-model builders, layout validation,
cutscene director/build_program, board.js render logic). Every seam below is
either (a) already generic enough to reuse unchanged by construction, (b)
reusable with one new **optional, default-preserving** parameter, or (c) needs
a parallel soccer module because the existing one is irreducibly football-typed.
The only sport-dispatch logic anywhere is host-level wiring (which bridge/
service/paths/table to construct), which lives outside every football module.

---

## Part A — shared-file seams

### 1. `src/scoreboard/__main__.py`

No seam needed inside this file's logic today, but it is the first host-level
wiring point that will need one. `main()` (lines 136–177) unconditionally
builds `ScoreboardApplication()` then `WindowHost(application, ...)`, then
calls `host.run(startup_choice=args.startup_choice, ...)`. There is no
`--sport` argument, no sport selection anywhere in `parse_args()` (lines
21–76).

- **Proposed minimal additive change:** none to the CLI contract for
  football's default path. The sport picker is a **runtime UI choice** (see
  item 3, `views/startup/*`), not a CLI flag, per the owner's brief ("On
  launch the operator chooses Football or Soccer"). `__main__.py` needs no
  change at all: `ScoreboardApplication`/`WindowHost` stay the single
  construction path, and the sport choice happens inside `WindowHost.run()`
  before the existing recovery-choice branch (see item 2).
- **Risk to football if done wrong:** none — this file requires no edit.
- **Golden-diff check:** a byte-diff of `__main__.py` against the frozen-file
  hash list catches any unintended edit outright.

### 2. `src/scoreboard/host/app.py`

This is the busiest shared file. Findings per named symbol:

**`ScoreboardApplication.__init__`** (lines 190–262): builds one
`ScoreboardPaths`, one `Diagnostics`, one `RecoveryReport` (`inspect_recovery`),
one `PresentationLayouts`, one `TeamPresets`, one `GameRules` (`config.read_rules`),
one `CutsceneDirector` — all football-typed, all built unconditionally in the
constructor. Nothing here takes a `sport` parameter.

- **Proposed minimal additive change:** `ScoreboardApplication` stays the
  football-only class exactly as it is (this is the class the golden run
  exercises for the frozen path). Add a **new sibling class**
  `SoccerApplication` in a new module (e.g. `host/soccer_app.py`) that builds
  the soccer-flavoured equivalents: `paths.for_sport("soccer")` (see item 9),
  a `SoccerService`/`SoccerBridge` pair (see items 6–7), and its own
  `PresentationLayouts`/`CutsceneDirector` instances constructed by passing the
  soccer paths object and (per items 10–11) either the already-generic
  storage layer unchanged or an injectable registry/module parameter. `WindowHost`
  is the one class that would hold a reference to *either* application object
  depending on the operator's sport choice, decided once at startup before
  `_choose_startup` runs (see below) — that decision point is host wiring, not
  a branch inside `ScoreboardApplication` itself.

**`ScoreboardApplication.resume` / `start_new`** (lines 278–290): call
`resume_recovered_game`/`start_new_game` from `application/recovery.py`
directly, and construct only a `ScoreboardBridge` via `_begin`.

- **Proposed minimal additive change:** none to these methods. A parallel
  `SoccerApplication.resume`/`start_new` calls the new
  `resume_recovered_soccer_game`/`start_new_soccer_game` (item 7) instead.

**`ScoreboardApplication._begin`** (lines 292–317): opens a `GameStore`,
builds one `ScoreboardBridge` with football's `layouts`/`teams`/`cutscenes`/
`rules_writer`.

- **Proposed minimal additive change:** none — `SoccerApplication._begin`
  (its own method, same shape) builds a `SoccerBridge` instead, reusing
  `GameStore.open()` unchanged (item 8) with an injected soccer snapshot
  decoder.

**`ScoreboardApplication.recovery_payload`** (lines 270–276): calls
`spectator_view_model(self.report.state, rules=self.rules)` — football-typed.
A `SoccerApplication.recovery_payload` mirrors this calling a soccer
`spectator_view_model`.

**`WindowHost.run`** (lines 650–669): the interactive entry point. Today it
unconditionally does:
```python
needs_choice = self.application.report.source is not RecoverySource.NONE
if needs_choice and startup_choice is None:
    ...
    self.startup_window = webview.create_window(
        "Recover scoreboard", url=view_url("startup"),
        js_api=StartupBridge(self.application.recovery_payload, self._choose_startup),
        ...
    )
else:
    self._choose_startup(startup_choice or "new")
```
This is the exact point the owner's brief says needs a **sport picker before**
Resume/New. Today there is only one `self.application` (football), so `run()`
has nothing to pick between.

- **Proposed minimal additive change:** the cleanest additive seam is to make
  `WindowHost` own **two** `ScoreboardApplication`-shaped objects (football's
  existing one, plus a new `SoccerApplication`) and add one new startup screen
  state *before* today's recovery-or-new branch: a sport choice. Concretely,
  `views/startup/index.html`/`startup.js` (item 3) gains a sport-picker step,
  `StartupBridge` gains a `choose_sport(sport)` method, and `WindowHost.run`'s
  `self.application` reference becomes "whichever application object the
  operator picked" — resolved once, before `_choose_startup` is ever called.
  Every method below `_choose_startup` (`_operator_loaded`, `_start_button_box`,
  `open_field_assistant`, etc.) then operates on `self.application` exactly as
  today; **none of their bodies need an `if sport ==` branch** because they
  already only ever see one application object per running process. The
  branch lives in exactly one place: the sport-picker's callback, which
  decides which application object becomes `self.application` for the rest of
  the process lifetime.
- **Risk to football if done wrong:** if the two-application host wiring is
  implemented by adding conditionals into `_choose_startup`, `_operator_loaded`,
  or any of the `open_*` methods instead of switching `self.application` once
  up front, every one of those methods becomes a fork point that could regress
  football silently. The additive-safe shape is "resolve once, then behave
  identically to today for the rest of the process."
- **Golden-diff check:** the football golden run drives `WindowHost` with
  `startup_choice="new"` end-to-end; if the sport-picker step accidentally
  changes what happens when Football is chosen (extra window, different
  view URL, different bridge type), the golden JSON diff (operator/spectator
  view models) goes non-empty immediately, and the frozen-file hash for
  `app.py` flags any edit at all inside the football-only methods.

**`WindowHost._choose_startup`** (lines 671–689): unconditionally builds
`self.application.resume()`/`.start_new()`, opens `view_url("operator")` with
that bridge as `js_api`. This method's body would need to open
`view_url("soccer_operator")` when the soccer application is active — the one
place inside `app.py` that plausibly needs an `if sport ==`-shaped decision
(or, cleaner, a `self.application.operator_view_name` property each
application class defines, so `_choose_startup` reads `view_url(self.application.operator_view_name)` — additive to `app.py` only via one new attribute access, no branch).

- **Proposed minimal additive change:** give `ScoreboardApplication` and
  `SoccerApplication` a shared read-only attribute (e.g.
  `operator_view_name = "operator"` on the football class, `"soccer_operator"`
  on the soccer class). `_choose_startup`'s one line
  `url=view_url("operator")` becomes `url=view_url(self.application.operator_view_name)`
  — a one-line, additive, non-branching change that is identical for football
  (the attribute defaults to `"operator"`, unchanged output).
- **Risk to football if done wrong:** low — this is a single attribute lookup
  replacing a literal string; the frozen-file hash and golden run both catch
  any accidental change to football's `"operator"` value.

**`WindowHost._operator_loaded`** (lines 696–724): opens the spectator window,
starts the publisher, `application.start_refresh()`, `self._start_button_box()`.
Entirely delegates to `self.application`/`self._start_button_box`; no sport
literal appears. No change needed beyond the button-box table (next item).

**`WindowHost._start_button_box`** (lines 726–753): constructs
```python
hook = ButtonBoxHook(
    dispatch, diagnostics=self.application.diagnostics, on_status=on_status
)
```
— no `table=` argument, so it always uses `HOTKEY_TABLE` (football's 8-key
table). `ButtonBoxHook.__init__` (hotkeys.py line 128) already accepts an
optional `table: tuple[HotkeyBinding, ...] = HOTKEY_TABLE` parameter (verified
by direct read — see item 15).

- **Proposed minimal additive change:** add one soccer-only constant in
  `hotkeys.py` (e.g. `SOCCER_HOTKEY_TABLE = (HOTKEY_TABLE[6], HOTKEY_TABLE[7])`,
  the existing F21/F22 `HotkeyBinding` entries only — `game_clock_start`/
  `game_clock_stop`), and in `_start_button_box` pass
  `table=SOCCER_HOTKEY_TABLE if self.application is self._soccer_application else HOTKEY_TABLE`
  (or, cleaner, `table=self.application.hotkey_table` where each application
  class exposes its own table, defaulting football's to `HOTKEY_TABLE`). This
  is the one true `if sport == ...`-shaped decision inside `app.py`, and it is
  explicitly named here per the brief's instruction to keep such branches to a
  last resort and name each one.
- **Risk to football if done wrong:** `HOTKEY_TABLE` itself must never be
  edited (only referenced); if the conditional were accidentally inverted or
  the attribute defaulted wrong, football's F15–F20 play-clock buttons would
  go dead. `tests/integration/test_button_box_hook.py` pins `HOTKEY_TABLE`'s
  exact 8 entries and would not catch a wrong *selection* of table at the
  call site (it tests the table's shape, not `_start_button_box`'s wiring) —
  a new soccer-specific test asserting `_start_button_box` selects
  `SOCCER_HOTKEY_TABLE` only for the soccer application is needed.
- **Golden-diff check:** the football real-pywebview run (per the brief's
  verification list) exercising the button box directly with Football chosen
  would show F15–F20 still working; the frozen-file hash on `hotkeys.py`
  proves `HOTKEY_TABLE` itself is untouched.

**`WindowHost.open_field_assistant`** (1105–1138): builds
`FieldAssistantBridge(bridge)` and opens `view_url("field_assistant")`.
Football-only per the brief ("views/field_assistant/\* … stay byte-identical").
A soccer Field Assistant needs its own `open_soccer_field_assistant` method
(new, additive) opening `view_url("soccer_field_assistant")` with a new
`SoccerFieldAssistantBridge(soccer_bridge)` — this file gains a new method,
the existing one is untouched.

**`WindowHost.open_cutscenes`** (1147–1184): builds
`CutscenesBridge(self.application.cutscenes, bridge)` and opens
`view_url("cutscenes")`. Soccer needs its own `open_soccer_cutscenes`
(new method) with a `SoccerCutscenesBridge` and `view_url("soccer_cutscenes")`
if the Cutscenes window's contents differ enough to warrant a separate page;
otherwise the existing `Cutscenes` window/bridge could be reused as-is if it
is already generic over "whichever `CutsceneDirector` the active application
built" (it takes `self.application.cutscenes` directly, so this works
unchanged as long as `self.application` is the soccer application when
soccer cutscenes are wanted).

**`WindowHost.open_spectator`** (904–981) and **`open_test_window`**
(1038–1073): both call `view_url("spectator")` unconditionally and build a
`SpectatorBridge(self._spectator_snapshot, read_layout=self.application.layouts.current_layout, ...)`.
`SpectatorBridge`'s constructor (host/bridge.py 918–1001) takes plain
callables and is sport-agnostic by construction (verified directly — see item
6), so **no change is required here structurally**: `self._spectator_snapshot`
already delegates to `self.application.bridge.spectator_snapshot()`, so
whichever application is active determines the shape of the JSON pushed. The
one open question is whether the spectator **page itself**
(`view_url("spectator")`) is reused with a different board kind, or whether
soccer gets `view_url("soccer_spectator")` — the views audit (item 16)
recommends a separate page, in which case these two methods need a small
additive branch selecting the view name from `self.application.spectator_view_name`
(same pattern as `operator_view_name` above).

**`WindowHost.open_layout_editor`** (1075–1103): builds
`LayoutEditorBridge(self.application.layouts, self._spectator_snapshot)` and
opens `view_url("layout")`. `PresentationLayouts` is already parameterized by
a `paths` object (verified — item 11), so `self.application.layouts` already
resolves to the right library depending on which application is active; if
the editor UI itself needs to know the widget registry (see item 11's
`layout_module` parameter), `LayoutEditorBridge`/`PresentationLayouts` need
one new optional constructor parameter, not a change to `open_layout_editor`.

**`WindowHost._deliver`** (1412–1533): dispatches pushed view models to
`operator`/`spectator`/`field_assistant`/`cutscenes` windows by name, entirely
data-driven off `window_name` — no sport literal anywhere. No change needed;
a soccer field-assistant/cutscenes window reuses this dispatch by window-name
convention (e.g. `"soccer_field_assistant"`) once `_publish`/`set_field_assistant_active`-equivalent wiring is extended, which is additive.

**`WindowHost.publish_cutscene`** (1193–1215): pushes to `spectator`/
`test_window` unconditionally — reused as-is for soccer's spectator window if
it's the same window object; if soccer's spectator is a separate window
attribute (e.g. `self.soccer_spectator_window`), this method needs a new
sibling `publish_soccer_cutscene`, not a branch inside the existing one.

- **Summary of the one true branch in `app.py`:** the button-box table
  selection in `_start_button_box` (named above) is the only place a genuine
  `if sport == ...`-style decision belongs inside this file. Every other
  seam is either "resolve which application object is active once, up front"
  or "add a new sibling method," neither of which touches football's existing
  code path.

### 3. `src/scoreboard/host/startup.py`

Read in full (19 lines). `StartupBridge` has exactly three methods:
`get_recovery()` → `self._report()`, `resume_recovered_game()` → `self._choose("resume")`,
`start_new_game()` → `self._choose("new")`. No sport concept exists here at all.

- **Proposed minimal additive change:** add one new method,
  `choose_sport(sport: str) -> None`, calling a new `self._choose_sport(sport)`
  callback supplied by `WindowHost`, which records which application
  (football/soccer) becomes active and then proceeds to show the *existing*
  recovery-or-new choice for that sport (reusing `get_recovery`/
  `resume_recovered_game`/`start_new_game` unchanged, now scoped to whichever
  application `_choose_sport` selected). This is a pure addition: one new
  method, zero changes to the three existing ones.
- **Risk to football if done wrong:** none if the three existing methods are
  left untouched; risk appears only if `_choose` is made sport-aware by
  editing its signature rather than by the host having already switched
  `self.application` before `_choose` runs.
- **Golden-diff check:** `StartupBridge`'s three existing methods are covered
  by the golden run picking "Football" then "New game" — an empty diff proves
  they still behave identically.

### 4. `src/scoreboard/views/startup/*`

Read `index.html` and `startup.js` in full. Today the page shows only
"Resume recovered game" / "Start new game" (with a confirm step for New);
`get_recovery()` is called immediately on load (`startup.js` line 27) and its
`report.view` (a football `spectator_view_model`) is rendered as a summary
(lines 32–38). There is no sport concept anywhere in this page.

- **Proposed minimal additive change:** add one new, prior screen state (a
  sport picker: "Football" / "Soccer" buttons) shown *before* the existing
  Resume/New screen, gated behind a new `#sport-pick` section analogous to the
  existing `#new-confirm` section (index.html lines 23–26). On a sport choice,
  `startup.js` calls the new `choose_sport(sport)` bridge method (item 3),
  then proceeds to call `get_recovery()`/render the existing Resume/New screen
  exactly as today, now scoped to that sport's recovery report. This is
  additive HTML/JS (new section + new event handlers) with the existing
  Resume/New markup, IDs, and `startup.js` logic (lines 1–43) left completely
  untouched — the new step simply runs first.
- **Risk to football if done wrong:** if the existing element IDs
  (`#resume`, `#new`, `#new-confirm`, `#message`, `#checkpoint`, `#summary`,
  `#error`) were renumbered or restructured to make room for the sport
  picker, any UI contract test pinning this page's DOM (if one exists) would
  break, and the golden pywebview run's Football path would visibly change.
  Keeping the sport-picker as a **new, separate, initially-shown section**
  that simply hides itself and reveals the untouched existing markup avoids
  this entirely.
- **Golden-diff check:** a real-pywebview run choosing "Football" then
  driving the existing Resume/New flow should produce byte-identical
  `get_recovery()`/`resume_recovered_game()`/`start_new_game()` behavior to
  today; this is exactly the football regression test the brief already
  requires ("one real pywebview run with Football chosen that opens the
  operator window").

### 5. `src/scoreboard/host/bridge.py` — what a soccer bridge subclasses/reuses vs. duplicates

Read in full by the research agent; independently spot-checked (`SCREEN_KINDS`,
`GAME_CLOCK_LABELS`, `_spectator_quarter_label`, `FINAL_HIDDEN_WIDGET_IDS`
locations confirmed directly — see Part C). Class/function locations:
`DisplayStatus` (205–232), `DisplayLink` (235–310), `build_command()`
(316–416), `_ALLOWED_ARGUMENTS` (150–184, a `dict[CommandType, frozenset[str]]`
keyed on football's `CommandType` enum), `_football_view()` (571–620),
`spectator_view_model()` (652–762, hard-codes a `"football"` key at line 744
holding `_football_view(...)`), `operator_view_model()` (836–900, football
Field Assistant fields at 880–894), `SpectatorBridge` (918–1001),
`FieldAssistantBridge` (1004–1048), `ScoreboardBridge.__init__` (1065–1120),
`ScoreboardBridge.command()` (1130–1198).

- **Verdict:** `ScoreboardBridge` is **not** sport-generic — it is wired
  directly to football's `CommandType`/`GameState`/`GameRules` at
  construction, and every view builder reads football-shaped state fields
  (`down`, `distance`, `possession`, `ball_on`, timeouts, assistant fields).
  There is no `if sport ==` branch in this file today; everything is
  football's, unconditionally.
- **What a soccer bridge should do:** be an **entirely parallel class**
  (`SoccerBridge` in a new `host/soccer_bridge.py`), not a subclass — there is
  nothing meaningful left to inherit from `ScoreboardBridge` once `command()`,
  `_ALLOWED_ARGUMENTS`, and every view-model helper are overridden.
- **What can be reused unchanged, by composition (not inheritance):**
  - `DisplayLink`/`DisplayStatus` (235–310, 205–232) — no game-state coupling
    at all; a soccer window can share the instance or get its own.
  - `SpectatorBridge` (918–1001) — its constructor takes plain callables
    (`read_snapshot`, `read_layout`, `read_cutscene`, `close`, `read_motion`)
    and is shape-agnostic about what `read_snapshot()` returns. A soccer
    spectator window reuses this class exactly, injecting
    `SoccerBridge.get_snapshot` as `read_snapshot`.
  - `GameStore` (see item 8) is generic at the storage layer.
  - `PresentationLayouts`/`layout_bridge` plumbing (item 11) is already
    parameterized by `paths`.
  - `_json_safe` and `_open_in_explorer` are pure utilities, reusable as-is.
- **Not reusable:** `FieldAssistantBridge` (1004–1048) forwards
  football-specific commands (`set_assistant_direction`, `FieldAction`) — a
  soccer assistant needs its own parallel class if the concept differs.
- **Risk to football if done wrong:** none if `bridge.py` stays untouched.
  Risk only appears if someone tries to *generalize* `_football_view`/
  `operator_view_model` with a `sport` parameter instead of writing separate
  `_soccer_view`/soccer view-model functions — that would reintroduce the
  branches this audit is trying to avoid, inside a file the frozen-file hash
  is meant to guard.
- **Golden-diff check:** a full-file diff of `bridge.py` should show zero
  changes for the soccer PR; the golden JSON snapshot of
  `operator_view_model`/`spectator_view_model` for a fixed football command
  sequence is the runtime backstop.

### 6. `src/scoreboard/application/service.py` and `recovery.py`

**`service.py`:** football-only imports at 34–94 (`domain.state.GameState`,
`domain.rules.GameRules`, `domain.commands.*`, `domain.field_assistant.*`,
`domain.clocks.*`). `initial_state()` (223–238) builds a `GameState(...)`
directly. `ScoreboardService.__init__` (244–286) is typed to
`GameState | None`, `GameRules | None`. `submit()` (518–531) is a generic
dispatch loop (type-check + reentrancy guard only) — the one genuinely generic
piece. `_apply()` (681–714) looks up `self._HANDLERS[command.type]`, keyed on
football's `CommandType`. `_commit()` (731–824) bakes football rules directly
into the shared commit path — spot-checked directly:
```python
if "quarter" in changes:
    quarter = changes["quarter"]
    changes["lifecycle"] = {"PRE": "PRE_GAME", "HALF": "HALFTIME",
                            "FINAL": "FINAL"}.get(quarter, "IN_PROGRESS")
if command.type is CommandType.GAME_CLOCK_START and (...):
    changes["play_clock_cleared"] = True
```
(lines 745–763, confirmed by direct read). `_HANDLERS` dict (1737–1772) is
entirely football `CommandType` values.

- **Verdict:** not generic over game state; no seam to inject a different
  state/rules type. `_commit`'s special-casing is football rules baked into
  what looks like a shared commit path.
- **Proposed minimal additive change:** a **parallel `SoccerService`** class
  in a new module, copying the submit/apply/commit **skeleton** (dispatch
  loop, `_HANDLERS` dict pattern, undo stack shape, monotonic clock injection)
  but with its own `_Transition`, its own `_HANDLERS`, and its own `_commit`
  containing soccer's rules (single running match clock / stoppage handling,
  card/stat commands) — not a subclass, since overriding `_commit` alone would
  mean overriding nearly the entire class anyway. The low-level clock engines
  (`GameClock`/`PlayClock`/`StatusCountdown` from `domain/clocks.py`) may be
  reusable *by type* if soccer's clock behaves similarly (one continuously
  running match clock), independent of the service-level orchestration.

**`recovery.py`:** `RecoverySource`/`RecoveryReport` (41–116) are generic in
shape. `inspect_recovery(paths, ...)` (162–285) takes a `ScoreboardPaths` and
calls `read_stored_game`/`validate_database`/`promote_backup` from
`persistence.py` — **almost** sport-agnostic at this level; the football
coupling is one level down, inside `persistence.read_stored_game`'s
`snapshot_to_state` call (item 8). `resume_recovered_game` (288–309) and
`start_new_game` (312–327) directly construct `ScoreboardService(state=..., ...)`
— irreducibly football-coupled as written.

- **Proposed minimal additive change:** give `inspect_recovery` one new
  optional keyword, `state_decoder: Callable[[Path], StoredGame | None] = read_stored_game`
  (defaulting to today's football function, so every existing call site is
  unaffected), and add sibling functions `resume_recovered_soccer_game`/
  `start_new_soccer_game` that build a `SoccerService` and pass a soccer-aware
  decoder. This is additive (new optional kwarg, default reproduces today's
  exact behavior) and needs no change to any existing call site. The more
  conservative alternative — a fully separate `soccer_recovery.py` duplicating
  `inspect_recovery`'s ~120 lines — has zero risk but duplicates non-trivial
  backup/corruption-handling control flow; the optional-kwarg approach is
  recommended as the smaller true diff, still strictly additive.
- **Risk to football if done wrong:** the single highest-risk move in this
  whole audit is trying to "generalize" `_commit`/`_HANDLERS`/`initial_state`
  in place — `_commit` contains several football-specific inline conditionals
  that are easy to disturb while generalizing. Any change to
  `inspect_recovery`'s signature also risks changing football's default
  recovery behavior if the new parameter's default doesn't reproduce today's
  exact call.
- **Golden-diff check:** (a) full-file diff of `service.py` should show zero
  changes; (b) a golden test running a fixed command sequence through
  `ScoreboardService` and asserting the exact `state_to_snapshot()` JSON and
  `_HANDLERS`/`_ALLOWED_ARGUMENTS` set match a stored fixture; (c) for
  `recovery.py`, a golden `inspect_recovery` test against fixed corrupt/valid/
  backup database fixtures, asserting `RecoveryReport.to_dict()` is unchanged
  with no `state_decoder` kwarg passed.

### 7. `src/scoreboard/infrastructure/paths.py`

Read in full. `ScoreboardPaths` (149–234) is a single flat `root: Path`
dataclass; every file/dir is a simple `self.root / FILENAME` property:
`database` (164), `backup` (167), `config` (171), `layouts` (175), `teams`
(179), `cutscenes` (183), `cutscene_selection` (187), `lock` (191),
`log_directory` (195), `log_file` (199). `ensure()` (211–222) creates `root`,
`log_directory`, `cutscenes`. `resolve_paths()` (351–380) is the sole
construction path used everywhere.

- **Proposed minimal additive change:** add one method after `describe()`
  (~line 235):
  ```python
  def for_sport(self, sport: str) -> "ScoreboardPaths":
      """A ScoreboardPaths for a specific sport's own db/backup/config/
      layouts/cutscenes, rooted under <root>/<sport>/."""
      return ScoreboardPaths(self.root / sport)
  ```
  This alone would also move `teams.json` under `<root>/soccer/teams.json`,
  which the brief says should stay shared. Two additive options to fix that:
  1. Add an optional `teams_root: Path | None = None` field to the frozen
     dataclass (default `None` = "use `self.root`"), and change the `teams`
     property to `(self.teams_root or self.root) / TEAMS_FILENAME`. Additive
     (new optional field, default preserves today's exact behavior);
     `for_sport()` becomes `ScoreboardPaths(root=self.root / sport, teams_root=self.root)`.
  2. **Simpler and lower-risk:** leave `ScoreboardPaths` completely untouched
     and have call sites hold two instances — `football_paths` (whose
     `.teams` is used by both sports) and `soccer_paths = ScoreboardPaths(root / "soccer")`
     for everything else. Zero change to `paths.py` at all.
  Given the "zero football-path branches" goal, option 2 is the safer
  recommendation; option 1 is the nicer API at slightly higher (but still
  low) risk.
- **Risk to football if done wrong:** a careless `for_sport()`/`teams_root`
  implementation (e.g. changing the `teams` property's default) could break
  every existing call site doing `paths.teams`. `ensure()` is unaffected
  either way since it operates relative to whatever `root` it's given.
- **Golden-diff check:** a unit test asserting
  `ScoreboardPaths(root=X).database == X / "scoreboard.db"` (today's
  behavior) still holds, plus a new test asserting
  `ScoreboardPaths(root=X).for_sport("soccer").database == X / "soccer" / "scoreboard.db"`
  and that the football paths object's `.teams` is untouched.

### 8. `persistence.py` — can `GameStore` store a soccer snapshot unchanged?

Read in full. Coupling point confirmed directly: line 67 imports
`snapshot_to_state`/`state_to_snapshot` from `application/snapshots.py`
(itself confirmed hard-typed to `GameState` — `state_to_snapshot(state: GameState)`
at snapshots.py line 24, `isinstance(state, GameState)` check at line 27).
`GameStore.__init__` (526–557) takes `paths`, connection, wall-clock,
diagnostics, app-version, monotonic — **no state-type parameter anywhere**.
`GameStore.open()` (559–581) is schema-agnostic (creates tables, connects).
`record_command()`/`_write_state()` (682–746, 920–948) only ever call
`state_to_snapshot(state)` and JSON-dump the result — this works for *any*
object `state_to_snapshot` can serialize. The one real coupling point is
**reading back**: `read_stored_game()` line 444 hard-calls football's
`snapshot_to_state` to reconstitute a `GameState`, and `StoredGame.state`
(242–251) is typed `GameState`. `checkpoint()`'s `_display_key()` (897–901)
also reads `state.game_clock.seconds`/`state.play_clock.seconds` directly —
football's two-clock shape.

- **Answer to the audit question:** the **write** path (SQL schema,
  `record_command`, `checkpoint`, `_write_state`) is snapshot-shape-agnostic
  today and needs no change to store a soccer snapshot blob. The **read**
  path (`read_stored_game`) and the checkpoint-cadence key
  (`_display_key`) are the two coupling points that need to change for a
  soccer `GameStore` to read its own snapshots back correctly.
- **Proposed minimal additive change:** two small, additive changes:
  1. `read_stored_game(path, *, decoder: Callable[[dict], Any] = snapshot_to_state)`
     — a new optional keyword defaulting to today's football function. Every
     existing call site (recovery.py, tests) is unaffected; a soccer caller
     passes `decoder=soccer_snapshot_to_state`.
  2. `GameStore.__init__`/`.open()` gains an optional
     `display_key: Callable[[GameState], tuple] | None = None` parameter,
     defaulting to the current `_display_key` behavior, used instead when
     provided — lets a soccer `GameStore` (the *same* class) checkpoint on
     its own clock cadence.
  If avoiding any change to `persistence.py` is preferred: subclass
  `GameStore` and override `_display_key` (not called anywhere outside the
  class, so overriding is clean), and duplicate `read_stored_game`'s handful
  of call-site lines as `read_stored_soccer_game` (since it's a free
  function, not a method).
- **Risk to football if done wrong:** an optional parameter with a
  default equal to today's exact behavior is low-risk. Risk rises sharply if
  `state_to_snapshot` itself (the shared serializer, not the store) were made
  polymorphic instead of adding a soccer-specific sibling — that would touch
  football's serialization path directly.
- **Golden-diff check:** a fixture SQLite database with one committed
  football game; assert `read_stored_game(path)` returns a `StoredGame` whose
  `state_to_snapshot(state)` matches a stored golden JSON exactly, with no
  `decoder` kwarg passed, both before and after the change. Also assert the
  SQL schema DDL is byte-identical (no schema change is needed for soccer).

### 9. `config.py`

Read in full. `read_config`/`write_config` (52–100) are section-agnostic.
`read_section(paths, section)`/`write_section(paths, section, value)`
(103–122) are **fully generic** — keyed purely by `paths.config` and a plain
string section name, with **zero football-specific logic**. Only
`read_rules`/`write_rules` (147–168) are football-typed convenience wrappers
constructing `GameRules` directly (`GameRules.from_payload`, `.to_dict()`).

- **Answer:** `read_section`/`write_section` need **zero change** to add a
  soccer rules section — a soccer module can call
  `write_section(paths, "soccer_rules", soccer_rules.to_dict())` today, with
  this file completely untouched. `write_section`'s read-modify-write
  behavior already guarantees football's `rules`/`display`/`presentation`
  sections and a new `soccer_rules` section coexist safely in one
  `config.json` without clobbering each other (or, if soccer uses a separate
  `config.json` under `paths.for_sport("soccer").config`, there's no
  coexistence question at all).
- **Proposed minimal additive change:** none to `config.py`. Add a new
  soccer-domain module (e.g. `domain/soccer/rules.py`) with
  `SOCCER_RULES_SECTION = "soccer_rules"` and `read_soccer_rules`/
  `write_soccer_rules` wrapper functions calling this file's existing
  `read_section`/`write_section` unchanged.
- **Risk to football if done wrong:** essentially none, since `config.py`
  needs no modification. The only way to introduce risk is choosing a soccer
  section name that collides with `"display"`/`"presentation"`/`"rules"`.
- **Golden-diff check:** a full-file diff of `config.py` should show no
  changes at all — the strongest possible check. A test writing both a
  football `rules` section and a soccer `soccer_rules` section to the same
  `config.json` and asserting `read_config` round-trips both untouched
  confirms no collision.

### 10. `layouts.py` and `layout_bridge.py`

Read in full. `layouts.py`: `default_library()` (84–87) built from
`presentation.layout.default_layout()`. `read_library(paths)`/
`write_library(paths, library)` (110–195, 198–223) and every one of
`save_layout`/`select_layout`/`delete_layout`/`rename_layout`/
`duplicate_layout`/`reset_library` (226–394) take `paths: ScoreboardPaths`
explicitly and derive the file location purely from `paths.layouts`.
`layout_bridge.py`: `PresentationLayouts.__init__` (91–117) takes
`paths: ScoreboardPaths` (93) and calls `layouts_infra.read_library(paths)`
(101); holds no reference to `ScoreboardService` at all.
`PresentationLayouts.state()` (130–155) calls
`layout_module.widget_descriptors()`/`screen_descriptors()`/
`preset_descriptors()`/`screen_preset_descriptors()` (139–147) — **this is
where football-specific registries enter**, via a fixed module-level import
of `presentation.layout`, not an injected parameter. `LayoutEditorBridge`
(332–388) forwards to a `PresentationLayouts` instance; its `get_snapshot`
(349–352) is wired to whatever `read_snapshot` callable it's given (already
generic).

- **Answer:** the **storage layer** (`layouts.py`'s functions) is already
  fully parameterized by `paths` — pointing `PresentationLayouts` at a soccer
  `ScoreboardPaths` (item 7) would "just work" for reading/writing
  `<root>/soccer/layouts.json`, zero code change. The **widget/screen
  registry layer** (`layout_module` functions) is not parameterized — it's a
  fixed import, so `PresentationLayouts`/`LayoutEditorBridge` as written
  cannot serve a soccer-specific widget registry without one small addition.
- **Proposed minimal additive change:** add an optional `layout_module`
  parameter to `PresentationLayouts.__init__`, defaulting to today's
  `scoreboard.presentation.layout` import, used everywhere `state()`/
  `preview()`/`clamp()`/`reset_widget()` currently reference the module-level
  import directly. Football's behavior is unchanged when the parameter is
  omitted; a soccer build passes a new `scoreboard.presentation.soccer_layout`
  module (see item 11) implementing the same function names.
- **Risk to football if done wrong:** low for the storage layer (already
  generic). Higher if `presentation/layout.py`'s shared registries were
  edited in place to "add soccer widgets" instead of using a fully separate
  module — a new widget ID could collide with a football one, or
  `default_layout()` could be changed to branch on sport, corrupting
  football's default. The injectable-module approach avoids this.
- **Golden-diff check:** (a) full-file diff of `layouts.py` should show zero
  changes; `layout_bridge.py` should show only the one additive constructor
  parameter; (b) a golden test asserting
  `PresentationLayouts(football_paths).state()` returns byte-identical JSON
  before/after, with no `layout_module` kwarg passed; (c) a golden fixture
  `layouts.json` written by today's build should still `read_library()`
  identically.

### 11. `presentation/layout.py` — registries keyed by `SCREEN_KINDS`

Read in full by the research agent; every symbol location independently
spot-checked directly. Confirmed exact lines:
```
SCREEN_IDS: Final[tuple[str, ...]] = ("game", "pregame", "halftime")   # line 80
SCREEN_KINDS: Final[dict[str, str]] = {                                 # lines 85-87
    "game": "game", "pregame": "event", "halftime": "event",
}
WIDGET_REGISTRIES: Final[dict[str, WidgetRegistry]] = {                 # lines 422-431
    "game": WidgetRegistry(WIDGET_IDS, ...),
    "event": WidgetRegistry(EVENT_WIDGET_IDS, ...),
}
```
`_validate_screen(raw, screen_id)` (2370–2489) — confirmed by direct read:
```python
kind = SCREEN_KINDS[screen_id]
registry = WIDGET_REGISTRIES[kind]
```
(lines 2384–2385). Every subsequent check in the function (widget ids,
labels, optional set, overlap checking) is driven purely off the
`WidgetRegistry` object — **the function itself never needs to change**;
it only needs `SCREEN_KINDS`/`WIDGET_REGISTRIES` to gain new keys, or a
soccer-owned mirror of the same lookup pattern.

`preset_descriptors()`/`screen_preset_descriptors()` (4256, 4086) and
`validate_layout()` (2591–2713) are **not** registry-generic — `validate_layout`
hard-codes the top-level "game" screen plus a literal
`"screens": {"pregame": ..., "halftime": ...}` dict (2708–2711), and
`default_screen()` (2543–2567) special-cases `screen_id == "game"` and
otherwise assumes every other screen is a Broadcast Welcome event screen.
These are football/event-screens-specific document-assembly functions, not
reusable for a soccer document shape.

- **Proposed minimal additive change:** do **not** touch `_validate_screen`,
  `SCREEN_IDS`, `SCREEN_KINDS`, `WIDGET_REGISTRIES`, or `validate_layout` in
  place. Add a new sibling module `presentation/soccer_layout.py` defining
  its own registries (home/away score, clock, period, shots, saves, corners,
  fouls, cards, shootout) and its own `WidgetRegistry(...)` instance (importing
  the frozen `WidgetRegistry` dataclass from `layout.py` — a pure, read-only
  import), plus its own `validate_soccer_layout()`, `default_soccer_layout()`,
  `soccer_preset_descriptors()` reusing `layout.py`'s pure private helpers
  (`_validate_widget`, `_validate_safe_area`, `_validate_background`,
  `_validate_element`, `_check_overlaps`, `LayoutIssue`, etc.) by import
  rather than duplicating their logic. If later it's worth sharing
  `_validate_screen` itself for a soccer screen, that becomes possible with
  **additive-only dict entries** (e.g. `SCREEN_KINDS["soccer_game"] = "soccer"`,
  `WIDGET_REGISTRIES["soccer"] = WidgetRegistry(...)`) since `_validate_screen`
  only ever does exact-key lookups and nothing in the codebase iterates
  `WIDGET_REGISTRIES`'s full keyset (confirmed by direct search). `SCREEN_IDS`
  itself should **not** gain a soccer entry, since `validate_layout`,
  `screen_descriptors()`, and `preset_descriptors()`/`screen_preset_descriptors()`
  iterate `SCREEN_IDS` to build football's own document/UI shape.
- **Risk to football if done wrong:** touching `SCREEN_IDS`/`SCREEN_KINDS`/
  `WIDGET_REGISTRIES` *values* (not adding new keys) changes what
  `_validate_screen`, `validate_layout`, `screen_descriptors`, or
  `preset_descriptors` do for the existing "game"/"event" kinds. Every
  football layout test asserts exact issue codes/messages/geometry.
- **Golden-diff check:** the golden-shape tests assert `preset_descriptors()`/
  `screen_preset_descriptors()` validate with zero warnings and exact widget
  geometry per preset; any change to the shared registry lookup or values
  breaks those exact-match assertions immediately. `_normalized_preset()`
  round-trips every preset through `validate_layout` itself, so a broken
  shared helper fails at test-collection time, not silently.

### 12. `presentation/cutscenes.py` + `host/cutscenes.py` + `infrastructure/cutscene_packs.py`

Read in full by the research agent; `CUTSCENE_EVENTS` location and
`CutsceneDirector`'s fixed imports independently spot-checked directly.

`presentation/cutscenes.py`: `CUTSCENE_EVENTS` is a plain module constant,
confirmed at lines 39–41:
```python
CUTSCENE_EVENTS: Final[tuple[str, ...]] = (
    "first_down", "touchdown", "turnover", "penalty", "make_some_noise",
)
```
`EVENT_LABELS`/`EVENT_HEADLINES`/`EVENT_TEAM`/`EVENT_SUBLINE`/
`DEFAULT_DURATION_SECONDS`/`EVENT_DEFAULT_INTRO`/`BUILTIN_SCENE_IDS` (42–96)
are all keyed literally by the 5 football event strings. `validate_manifest()`
(265–360) hard-checks `raw_event in CUTSCENE_EVENTS` and falls back to
`CUTSCENE_EVENTS[0]`. `build_program()`/`event_descriptors()` (489–581)
iterate `CUTSCENE_EVENTS` explicitly. Nothing in this module references a
football *field name* the way `layout.py` does — it is generic over an
"event id → metadata" shape, but the event set and its companion dicts are
literal singular constants, not a swappable registry object.

`host/cutscenes.py`: `CutsceneDirector.__init__` (74–107, confirmed by direct
read) takes `paths: ScoreboardPaths` plus assorted callables — **already
parameterized by `paths` for storage location** — but hard-imports
`cutscenes_module` (`from scoreboard.presentation import cutscenes as
cutscenes_module`, a fixed module-level import) and references
`cutscenes_module.CUTSCENE_EVENTS` directly at lines 112, 206, and 370
(confirmed by direct grep and read):
```python
def _note_library_issues(self) -> None:
    for event in cutscenes_module.CUTSCENE_EVENTS:
        ...
```
There is **no** constructor parameter to override the events module — this
nuances the "already generic" read: the *pack folder location* is injectable
(via `paths`), but the *event vocabulary* is not.

`infrastructure/cutscene_packs.py`: fixed imports of `cutscenes_module`,
`CUTSCENE_EVENTS`, `builtin_pack`, `validate_manifest` (confirmed at lines
29–35). Every function (`ensure_packs_directory`, `scan_packs`,
`read_selection`, `write_selection`, `library`) takes only a `paths` object
and always reads/writes `paths.cutscenes`/`paths.cutscene_selection` — fixed
`@property`s on `ScoreboardPaths` deriving from `CUTSCENES_DIRECTORY_NAME`/
`CUTSCENE_SELECTION_FILENAME` constants (confirmed directly in `paths.py`).
`read_selection`/`write_selection` also filter by `event in CUTSCENE_EVENTS`,
so even pointing the scan at a different folder would silently drop any
soccer event id.

- **Proposed minimal additive change (zero edits to the three existing
  files):**
  1. New `presentation/soccer_cutscenes.py`: `SOCCER_CUTSCENE_EVENTS = ("goal", ...)`
     plus its own `EVENT_LABELS`/`EVENT_HEADLINES`/`EVENT_TEAM`/`EVENT_SUBLINE`/
     `DEFAULT_DURATION_SECONDS`/`EVENT_DEFAULT_INTRO`/`BUILTIN_SCENE_IDS`/
     `THEME`, and its own `validate_manifest`/`build_program`/
     `event_descriptors`, reusing the small stateless helpers by import.
  2. New, purely additive `ScoreboardPaths` properties, e.g.
     `soccer_cutscenes -> self.root / "soccer" / "cutscenes"` and
     `soccer_cutscene_selection -> self.root / "soccer" / "cutscenes.json"`
     (or simply reuse `paths.for_sport("soccer").cutscenes`/
     `.cutscene_selection` from item 7's `for_sport`, which already gives the
     right paths for free).
  3. New `infrastructure/soccer_cutscene_packs.py` mirroring
     `cutscene_packs.py`'s scan/selection functions but importing from
     `soccer_cutscenes` and reading the soccer paths.
  4. New `host/soccer_cutscenes.py` with a `SoccerCutsceneDirector`/
     `SoccerCutscenesBridge` mirroring `CutsceneDirector`/`CutscenesBridge`
     but importing the soccer presentation/infrastructure modules. (A less
     preferred alternative: add optional `cutscenes_module=`/
     `cutscene_packs_module=` constructor parameters to the existing
     `CutsceneDirector`, defaulting to football's current fixed imports —
     additive via new optional parameters, but touches the existing class
     body, carrying more audit risk than a fully parallel class.)
- **Risk to football if done wrong:** any edit to `CUTSCENE_EVENTS`,
  `paths.cutscenes`/`paths.cutscene_selection`, or the fixed imports in
  `host/cutscenes.py`/`infrastructure/cutscene_packs.py` immediately changes
  which folder football scans, which events are recognized, or what
  `event_descriptors()` returns to the operator's Cutscenes window — the
  whole call chain from `WindowHost` down to `library()` is single-path with
  no branching today.
- **Golden-diff check:** `tests/integration/test_cutscene_director.py`-style
  tests pin `CUTSCENE_EVENTS` to exactly 5 entries and check `select_pack`/
  `rescan`/`state()` against "five built-ins"; `tests/unit/test_cutscene_schema.py`
  asserts `len(BUILTIN_SCENE_IDS) == 5`. Any change to the football module
  constants that shrinks/grows/renames the set breaks these immediately.

### 13. `views/shared/board.js`

Read in full by the research agent; `screenForLifecycle` and
`registryForKind` independently spot-checked directly. Confirmed exact code:

`REGISTRIES` (lines 2245–2260): exactly two keys, `game` and `event`.
`registryForKind(kind)` (2262–2264):
```js
function registryForKind(kind) {
  return kind === 'event' ? REGISTRIES.event : REGISTRIES.game;
}
```
`build(container, kind)` (2529–2551): `var resolvedKind = kind === 'event' ? 'event' : 'game';` — same binary collapse.
`screenForLifecycle(lifecycle)` (3217–3225, confirmed directly):
```js
function screenForLifecycle(lifecycle) {
  if (lifecycle === 'PRE_GAME') { return 'pregame'; }
  if (lifecycle === 'HALFTIME') { return 'halftime'; }
  return 'game';
}
```
`applyLayout`/`applyModel` (2837+, 3148+) both resolve the registry generically
via `registryForRoot(boardRoot)` (which reads `boardRoot.dataset.boardKind`,
stamped by `build()`), and are not otherwise hard-coded to `'game'`/`'event'`
except two `boardRoot.dataset.boardKind === 'game'` checks (3161, 3163, 3186)
gating football-only view-model fields (`hidden_widgets`,
`hidden_element_prefixes`, `WIDGET_FORMAT_FIELDS`) — additive-safe no-ops for
any other kind since the condition simply won't match.

- **Proposed additive change:** add `SOCCER_WIDGET_IDS`/`SOCCER_WIDGET_FIELDS`/
  `SOCCER_WIDGET_TEXTS`/`SOCCER_OPTIONAL_WIDGET_IDS` (and `SOCCER_EVENT_*` if
  a soccer pregame/halftime screen is wanted) JSON literals mirroring a new
  Python-side soccer registry, add `soccer`/`soccer_event` keys to the
  `REGISTRIES` object, and widen `registryForKind`/`build`'s ternaries into a
  small lookup that still falls through to `game` for anything unrecognized:
  ```js
  function registryForKind(kind) {
    if (kind === 'event') return REGISTRIES.event;
    if (kind === 'soccer') return REGISTRIES.soccer;
    if (kind === 'soccer_event') return REGISTRIES.soccer_event;
    return REGISTRIES.game;
  }
  ```
  `screenForLifecycle` does **not** need a soccer branch: it is only ever
  called by football's `spectator.js` (line 65) against football's lifecycle
  values. A soccer spectator page should call its own analogous mapping
  function (soccer likely needs `FIRST_HALF`/`HALFTIME`/`SECOND_HALF`/
  `EXTRA_TIME`/`SHOOTOUT`, not just three states) living in a soccer-owned JS
  module — this shared function stays untouched either way.
- **Risk to football if done wrong:** editing the existing ternaries in place
  (rather than adding new `if` branches before the existing fallback) risks
  changing the `'game'`/`'event'` fallback semantics for an unrecognized/
  mistyped kind string. Mutating any existing JSON literal instead of adding
  new ones desyncs the Python↔JS mirror test and changes the live football
  board.
- **Golden-diff check:** the registry-mirroring test lifts the JS literal
  text between `=` and the closing `;` and `json.loads`s it against
  `scoreboard.presentation.layout`'s matching constants — a malformed new
  soccer literal fails to parse immediately; an accidental edit to an
  existing football literal fails the value-equality check immediately.

### 14. `views/shared/board.css`

Read in full by the research agent (298 lines). Entirely id/content-agnostic
— no selector names a football-specific widget id; every rule targets
structural classes/attributes set generically by `board.js` (`.widget`,
`.widget-text`, `.element`, `[data-cut-corners]`, `[data-anim=...]`, etc.).
The only content-specific selector is a font-rendering nudge
(`.widget[data-font="impact"] .clock-colon`, not a widget-id rule).

- **Proposed additive change:** soccer widgets need **no new classes in this
  shared file** — they are `.widget`/`.element` instances placed by
  `board.js`'s generic `build()`/`applyLayout()`, styled through the existing
  CSS custom properties. A soccer-specific look (a card-color chip, a
  shootout indicator) should live in a **new soccer-only stylesheet**
  (e.g. `views/soccer_shared/soccer-board.css` or loaded only by
  `views/soccer_spectator/`), the same pattern `spectator.css`/`cutscene.css`
  already use alongside `board.css`.
- **Risk to football if done wrong:** adding soccer-specific selectors into
  this shared file risks specificity collisions since it is used
  unconditionally by both the frozen spectator board and the layout editor's
  live preview canvas.
- **Golden-diff check:** a full-file diff should show zero changes; any
  visual-diff/screenshot test on the football spectator/editor pages would
  catch collateral damage from a shared-file edit.

### 15. `host/hotkeys.py`

Read in full directly (281 lines — see snippet above in item 2).
`HOTKEY_TABLE` (56–65): 8 `HotkeyBinding` entries, F15–F22.
`ButtonBoxHook.__init__` (120–141) **already** accepts
`table: tuple[HotkeyBinding, ...] = HOTKEY_TABLE` (confirmed directly at line
128), stored as `self._table` and used in `_run()`'s registration loop (196)
and dispatch (231). `command_for(vk, table=HOTKEY_TABLE)` (74–80) likewise
already takes an optional `table`. `BUTTON_BOX_SOURCE` (32) is sport-agnostic.

- **Proposed minimal additive change:** the class needs **zero** changes —
  it is already parameterized. Add one new module-level constant:
  ```python
  SOCCER_HOTKEY_TABLE: Final[tuple[HotkeyBinding, ...]] = (
      HOTKEY_TABLE[6],  # F21 -> game_clock_start
      HOTKEY_TABLE[7],  # F22 -> game_clock_stop
  )
  ```
  and change exactly one call site (`host/app.py`'s `_start_button_box`,
  lines 748–750) to pass `table=SOCCER_HOTKEY_TABLE` when the soccer
  application is active (named explicitly in item 2 above as the one true
  branch inside `app.py`). `HOTKEY_TABLE` itself is never edited.
- **Risk to football if done wrong:** if the additive `table=` argument were
  passed unconditionally instead of conditionally, football's F15–F20
  play-clock buttons would go dead. If `HOTKEY_TABLE` itself were edited
  (reordered or changed) instead of adding a new constant, `command_for`'s
  lookup and the physical button-box pin map would desync.
- **Golden-diff check:** `tests/integration/test_button_box_hook.py` pins
  `HOTKEY_TABLE`'s exact 8 entries and fails on any edit to them; a new
  soccer-specific test asserting `_start_button_box` selects
  `SOCCER_HOTKEY_TABLE` only for the soccer application covers the wiring
  gap that file's existing test doesn't.

### 16. `views/spectator/*` — reuse with a query/kind, or a separate `views/soccer_spectator/`?

Read in full by the research agent. `views/spectator/index.html` hard-codes
its `<script>`/`<link>` tags (no manifest, no directory scan) — confirmed
directly:
```html
<script src="cutscenes/builtin.js"></script>
<script src="cutscenes/tigers.js"></script>
<script src="cutscenes/crowd.js"></script>
<script src="cutscene.js"></script>
```
`spectator.js` builds `#game-board`/`#event-board` via
`B.build(gameBoard, 'game')`/`B.build(eventBoard, 'event')` (lines 55–56),
and drives everything off football's `screenForLifecycle` (line 65,
`PRE_GAME`/`HALFTIME`/else). `SpectatorBridge` itself (host/bridge.py
918–1001) is sport-agnostic by construction (plain injected callables), but
the **page** hard-codes football's lifecycle vocabulary and its cutscene
scene-file list.

- **Recommendation: a separate `views/soccer_spectator/`**, not a query
  param on this page. Reasons: (1) mixing two sports' lifecycle vocabularies
  into `screenForLifecycle`-style logic would force editing a function item
  13 already establishes should stay untouched; (2) the cutscene scene-id
  test (item 12/17) scans exactly `views/spectator/cutscenes/*.js` and
  asserts exactly 5 football ids — a soccer scene file must live outside that
  folder, and since cutscenes are wired through `spectator.js`'s
  override-layout seam, keeping soccer's spectator page separate is the path
  of least resistance for keeping that test's guardrail intact; (3) `index.html`
  and `spectator.js` are both explicit entries on `tools/build_package.py`'s
  `REQUIRED_FILES` list (item 19) — a new `views/soccer_spectator/index.html`
  + `.js` needs its own additive entries there, never risking football's
  existing required files being flagged missing.
- **Risk to football if done wrong:** reusing this page with a query param
  means every future `spectator.js` change has to consider two sports' state
  machines simultaneously via the one shared `window.applyView` — a bug in
  soccer lifecycle handling could regress football rendering.
- **Golden-diff check:** the cutscene scene-registry test (scans
  `views/spectator/cutscenes/*.js` for exactly five football ids) fails
  immediately if a soccer scene file were dropped into that directory instead
  of a new `views/soccer_spectator/cutscenes/` directory.

### 17. `views/layout/*` — does the editor need any change?

Read in full by the research agent; `screenForLifecycle`/`SCREEN_KINDS`
cross-checked directly. `layout_state()`'s screen descriptors already carry a
`"kind"` field (confirmed directly:
`kind = SCREEN_KINDS[screen_id]` / `registry = WIDGET_REGISTRIES[kind]` at
`presentation/layout.py` lines 3019–3020, feeding `screen_descriptors()`).
`Board.build(boardRoot, descriptor.kind)` **is** called generically at
`layout.js` line 118 inside `app.switchScreen` — no football-specific
branching at that call site. Hard-coded string occurrences found:
- `layout.js:61` — `screen: 'game',` (initial default screen, bootstrap only).
- `layout.js:86` — `app.screenDoc()`: `if (app.screen === 'game') { return app.draft; }`
  else builds/returns `app.draft.screens[app.screen]` generically — already
  screen-id-generic beyond the "game" special case (the top-level document is
  "game"-only because that's schema v3's shape).
- `layout.js:644` — `applyPresetAction(id)`: `if (app.screen === 'game') {`
  gets a full-layout preset copy; any other `app.screen` value falls to a
  generic per-screen-document branch.
- `layout.js:1347` — bootstrap `Board.build(boardRoot, 'game')`, only matters
  before `layout_state()` returns and `switchScreen` re-runs with the real
  descriptor's kind.
- `editor-panels.js:668` — `if (app.screen === 'game')` inside
  `currentPresets(app)`; any other screen id already falls through to
  `byScreen[app.screen]` generically.

- **Answer:** for a **separate** `views/soccer_layout/` page (mirroring the
  spectator decision in item 16), **no code change is needed** — the pattern
  is already screen-id-generic (`app.screenDoc()`, `applyPresetAction()`,
  `currentPresets()`, `Board.build(boardRoot, descriptor.kind)` all key off
  `app.screen`/`descriptor.kind` rather than an enumerated whitelist, with
  `'game'` used only as football's designated top-level/default screen id).
  If soccer screens were instead added to the *same* editor instance, only
  the bootstrap literal (`layout.js:1347`) is a true special case to touch
  (harmless either way, since `switchScreen` immediately re-runs `Board.build`
  with the real kind).
- **Risk to football if done wrong:** none if a separate page is used. If the
  same page/`app` object were extended instead, the risk is in the two
  `if (app.screen === 'game')` special-cases (`layout.js:86`, `:644`;
  `editor-panels.js:668`) — inverting or broadening these carelessly could
  make football's Game screen start reading from `draft.screens.game` instead
  of the top-level document, corrupting saved football layouts.
- **Golden-diff check:** `presentation/layout.py`'s schema validation tests
  would fail if `screen_descriptors()` stopped emitting football's three
  screens correctly; the JS↔Python literal-mirroring test (item 13) plus any
  editor DOM test exercising `switchScreen('game'/'pregame'/'halftime')`
  would catch a regression in the `'game'`-special-case branches.

### 18. `tools/build_package.py` `REQUIRED_FILES` and `tools/scoreboard.spec`

Read in full by the research agent. `REQUIRED_FILES` (build_package.py,
lines 36–82) is an **explicit tuple of individual file path strings** — not a
glob (e.g. every `views/layout/*.js` file, `views/spectator/index.html`/
`.css`/`.js`, `views/shared/base.css`/`board.css`/`board.js`/`render.js`,
font files, the crest PNG are all named individually). `verify()`
(117–183) checks every `REQUIRED_FILES` entry exists and is non-empty, and
**separately** does a generic `views.rglob("*")` scan for remote-resource
markers (`http://`, `https://`, `//cdn`) across the *whole* `views/` tree —
that second check is already additive-safe and would automatically cover any
new `views/soccer_*/` file.

- **Answer:** **yes**, adding new files under `views/soccer_*` requires new
  lines in `REQUIRED_FILES` (purely additive tuple entries, existing ones
  untouched) so the packaged build verifies they landed; the remote-resource
  scan needs no edit. `domain/soccer/` (pure Python, not under `views/`) is
  not referenced by this script at all — Python package inclusion is
  governed by `pyproject.toml`/PyInstaller's `Analysis`, not this file.
- **`tools/scoreboard.spec`** (read in full, 138 lines): the critical block
  (lines 68–76) is a **directory glob** (`VIEWS.rglob("*")`) over the entire
  `views/` tree feeding `Analysis(datas=view_files, ...)` — fully
  additive-safe; any new file under `views/soccer_spectator/` or
  `views/soccer_layout/` is automatically discovered and copied into the same
  `scoreboard/views/<relative-dir>` layout the app expects. `Analysis.pathex`
  includes the whole `src` tree, so `domain/soccer/**/*.py` is picked up the
  same way existing domain modules are, **as long as it's actually imported**
  somewhere reachable from `__main__.py`'s import graph — if soccer code is
  only imported dynamically when a soccer game starts, it may need one
  additive entry in `hiddenimports=[...]` (lines 85–89), the same pattern
  already used for `webview.platforms.edgechromium`.
- **Risk to football if done wrong:** forgetting to add new soccer view
  files to `REQUIRED_FILES` would not break football — the check only
  asserts presence of the *listed* files — it would just mean a missing/empty
  soccer file ships silently instead of failing the build. Editing existing
  entries would break football's build verification.
- **Golden-diff check:** `python tools/build_package.py --verify-only` (or a
  full build) fails immediately with "missing from the package: ..." for any
  omitted *football* line; a full-file diff of both `REQUIRED_FILES`'
  existing entries and `scoreboard.spec`'s glob logic should show only new
  additive lines/entries.

### 19. `pyproject.toml` package-data patterns

Read in full by the research agent (54 lines). Package-data block (43–54):
```toml
[tool.setuptools.package-data]
scoreboard = ["views/**/*.html", "views/**/*.css", "views/**/*.js", "views/**/*.png",
              "views/**/img/*.png",
              "views/**/fonts/*.ttf", "views/**/fonts/*.txt"]
```
Recursive glob patterns rooted at `views/`, not an explicit file list.
`[tool.setuptools.packages.find]` (40–41) uses `where = ["src"]` with no
`include`/`exclude` narrowing, so any new Python subpackage under
`src/scoreboard/` (e.g. `domain/soccer/` with an `__init__.py`) is
auto-discovered without any edit.

- **Answer:** **no edit needed**, for both `views/soccer_*/**` (already
  matched by the existing `views/**/*.ext` globs for `.html`/`.css`/`.js`/
  `.png`/img/fonts) and `domain/soccer/**` (matched by setuptools' package
  auto-discovery, which governs `.py` files, not `package-data`). An edit
  would only be needed if a soccer asset used an **uncovered extension**
  (e.g. `.svg`, `.woff`, a bundled `.json` resource) — a new glob line,
  purely additive, zero risk to the existing football patterns.
- **Risk to football if done wrong:** none from adding files that already
  match the existing globs; risk would only appear if the patterns were
  narrowed or rewritten to an explicit list instead of left alone.
- **Golden-diff check:** `tools/build_package.py`'s `REQUIRED_FILES`
  verification (item 18) and its readiness `--check` are the effective
  end-to-end proof that these globs still deliver every football file into
  the frozen package.

---

## Part B — tests that scan directories or pin counts

Grepped `tests/` for `rglob`, `iterdir`, `\.glob\(`, `listdir`, `VIEWS /`,
`for path in`, `register\(`, `len\(`, plus targeted reads of the named
contract files. Summary of what a new, purely-additive soccer file could and
could not trip:

### B.1 — `tests/integration/test_packaging.py` (HIGH RISK — needs a mandatory additive edit elsewhere)

- `view_files()` (lines 48–49): `return sorted(path for path in VIEWS.rglob("*") if path.is_file())`.
  This is the **only** `rglob` hit in the whole test suite, and it scans the
  entire `src/scoreboard/views` tree recursively — any new file under
  `views/soccer_operator/`, `views/soccer_spectator/`, etc. **will** be
  picked up.
- `test_every_view_file_matches_a_declared_pattern` (51–63): every file found
  by `view_files()` must match one of `pyproject.toml`'s package-data
  `fnmatch` patterns. Since those patterns are `views/**/*.ext` globs
  (item 19), this test is **safe** as long as new soccer files use extensions
  already covered (`.html`/`.js`/`.css`/`.png`/fonts). It only breaks if
  soccer introduces a genuinely new extension not yet declared — an allowed,
  additive `pyproject.toml` edit.
- `test_the_build_script_requires_every_view_file` (65–74): computes
  `expected` from the same recursive `view_files()` scan and compares against
  `required` = the file-path strings found by regex inside
  `tools/build_package.py`. **This test will break unconditionally** the
  moment any new file exists under `views/` unless `REQUIRED_FILES` (item 18)
  is updated with the new soccer file paths by name. This is a real,
  guaranteed, but purely additive and expected edit to a build-script data
  list — not a change to football behavior.
- `BundledAssetTests` (91–133) are scoped to a fixed `BUNDLED_ASSETS` tuple of
  football's own font/crest files — unaffected by new soccer directories.

**Conclusion:** adding files under `views/soccer_*/` is safe for football's
*behavior*, but is a hard, mandatory trigger for two specific additive edits:
(a) `tools/build_package.py`'s `REQUIRED_FILES` gains the new soccer file
paths, and (b) `pyproject.toml`'s package-data patterns gain a new glob line
only if a new file extension is introduced. Both are named, expected, and
zero-risk-to-football edits to shared config — not edits to football's logic.

### B.2 — `tests/integration/test_bridge.py` — the `CommandType`↔operator-page contract (confirms soccer needs its own enum)

All of the following import `from scoreboard.domain.commands import CommandType`
directly and iterate that exact enum (no dynamic enum discovery anywhere):

- `test_every_command_has_a_control_in_the_operator_page` (106–119): asserts
  `{command.value for command in CommandType} - {FINALIZE_FIELD_ACTION} - controls == set()`,
  where `controls` is scraped from `data-command="..."` literals in the
  football operator's HTML/JS. **Any new member added to this same enum must
  have a matching `data-command` in the football operator page**, or this
  fails.
- `test_no_control_names_a_command_that_does_not_exist` (121–125): the
  inverse — every `data-command` in football's operator HTML must be a known
  `CommandType` value. Adding soccer members to the same enum doesn't break
  this one directly, but grows the enum's membership without football's HTML
  ever using the new values.
- `test_every_command_reaches_the_service_through_the_bridge` (141–159) and
  `test_every_command_result_is_json_compatible` (780–792): for every
  `CommandType` member (except `FINALIZE_FIELD_ACTION`), constructs a fresh
  football session/bridge and asserts the command is **accepted**, using
  football-specific `COMMAND_PRELUDES`/`COMMAND_PAYLOADS` fixture dicts. **A
  soccer member added to the same enum fails here immediately** — football's
  bridge/service has no handler and no fixture payload for it.
- `tests/integration/test_layout_bridge.py:124-129,135-139` similarly iterate
  `CommandType` (one asserts recorded history-command names are a subset of
  `CommandType` values plus a small system-event allowlist; one asserts the
  read-only layout-editor bridge exposes no attribute named after any
  `CommandType` value) — both would need soccer-command awareness if soccer
  commands joined the same enum.
- `tests/integration/test_layout_editor_contract.py:127-130`
  (`test_no_command_name_appears_anywhere_in_the_editor`) also iterates
  `CommandType`, asserting none of its values appear as literal text in the
  football layout editor's markup.

**Conclusion (confirmed by direct import inspection):** defining soccer
commands as members of a **brand-new, separate class** (`SoccerCommandType`)
that none of these six tests ever import or iterate keeps all of them
completely blind to it — zero risk. Adding soccer members directly to
football's `CommandType` breaks at minimum the operator-control-coverage test,
the bridge-acceptance test, and the JSON-compatibility test outright. **Soccer
needs its own command-type enum**, confirming the brief's own instinct.

### B.3 — Cutscene "mirror"/schema tests — scoped to football's fixed folder, safe from a new soccer folder

- `tests/unit/test_cutscene_schema.py`, `BuiltinSceneRegistryMirrorTests`
  (~919–953): `_registrations()` hardcodes
  `folder = .../src/scoreboard/views/spectator/cutscenes` and does
  `sorted(folder.glob("*.js"))` — **only** that one football folder, and it
  is non-recursive. `test_the_scene_files_register_the_intro_and_every_scene_id`
  asserts `len(BUILTIN_SCENE_IDS) == 5` (a hand-maintained Python dict, not
  derived from the scan) and that each literal id appears somewhere in the
  concatenated text of files in that one folder. A soccer scene file in a
  **different** folder (e.g. `views/soccer_spectator/cutscenes/`) is
  completely invisible to this test. It would technically not *break* even if
  placed in the *same* football folder (the test only checks presence of the
  5 known ids, not absence of extras) — but it would then get picked up by
  the much stricter contract test below.
- `tests/integration/test_cutscene_player_contract.py`: hardcodes a `SCENE_IDS`
  dict mapping exactly the three football scene files (`builtin.js`,
  `tigers.js`, `crowd.js`) to their registered ids, and a `FORBIDDEN_IN_SCENES`
  tuple checked only against those three files. A new soccer scene file in a
  new folder is not enumerated here and is never read or checked at all.
  **Safe** — but also means a soccer cutscene folder gets **none** of this
  contract's safety net (no-network/no-innerHTML-abuse checks) unless a
  parallel soccer-specific contract test is written.
- `tests/integration/test_spectator_layout_render.py`: hardcodes
  `BOARD_JS`/`SPECTATOR_JS` as two fixed paths (`shared/board.js`,
  `spectator/spectator.js`) — no glob, no directory scan. A new soccer
  spectator module under `views/soccer_spectator/` is invisible to it.
  **Safe.**

**Conclusion:** all of these tests use hand-authored, non-recursive, single-
folder scans or literal file-path tuples by deliberate design (a code comment
in `test_layout_editor_contract.py` even says so explicitly: "kept as a
literal list rather than a glob so a stray extra .js file must be added here
on purpose"). A brand-new soccer folder for views/cutscenes is invisible to
every one of them, as intended.

### B.4 — Other named contract tests

- `tests/integration/test_layout_editor_contract.py`: uses a literal
  `SCRIPT_FILES` tuple scoped to `VIEWS / "layout"` — no whole-tree scan.
  Only the shared `CommandType` iteration (B.2) creates cross-cutting risk,
  and only if soccer joins the same enum. **Safe** otherwise.
- `tests/integration/test_keyboard_source.py`: purely behavioral
  (`build_command`/`bridge.command` against fixed football command names) —
  no directory scan, no enum iteration. **Not at risk.**
- `tests/integration/test_button_box_hook.py`: `_page_fkey_rows()` parses
  only `VIEWS/"operator"/"keyboard.js"` by regex, asserts `len(page) == 8`
  (today's football row count), compares against `HOTKEY_TABLE`. Entirely
  scoped to football's own files. **Safe.**
- `tests/integration/test_cutscenes_ui_contract.py`: reads only fixed
  football paths under `views/operator/` and `views/cutscenes/`; imports
  `CommandType` only in a docstring note, not an assertion. **Safe.**
- No `test_cutscene_player_contract*` count assertion touches a soccer
  folder (covered in B.3).

### B.5 — overall Part B conclusion

The single guaranteed-to-break test on any new `views/` file is
`test_packaging.py::test_the_build_script_requires_every_view_file`, which
requires a mandatory (and expected) additive edit to
`tools/build_package.py`'s `REQUIRED_FILES`. The `CommandType`-enum family of
tests confirms soccer must use a wholly separate enum. Every cutscene
mirror/schema/contract test and the spectator-layout-render test use
deliberately narrow, non-recursive, hand-authored scans that are blind to a
new soccer directory by design.

---

## Part C — hard-coded lifecycle/quarter labels a soccer board would reuse or must not collide with

All five symbols confirmed by direct read/grep against the branch.

### `screenForLifecycle`

- **Defined:** `views/shared/board.js:3217-3225`:
  ```js
  function screenForLifecycle(lifecycle) {
    if (lifecycle === 'PRE_GAME') { return 'pregame'; }
    if (lifecycle === 'HALFTIME') { return 'halftime'; }
    return 'game';
  }
  ```
- **Called:** `views/spectator/spectator.js:65` —
  `var screenId = B.screenForLifecycle(model.lifecycle);`
- **Kind:** a plain function on a literal string, exported at `board.js:3273`.
- **Soccer path:** generic enough to reuse as-is if soccer only needs
  PRE_GAME/HALFTIME/else semantics (it degrades to `'game'` for any
  unrecognized string, with no football-specific behavior beyond three
  literals). If soccer needs finer states (`FIRST_HALF`/`SECOND_HALF`/
  `EXTRA_TIME`/`SHOOTOUT`), define an analogous function in a soccer-owned JS
  module rather than editing this one — no edit to `board.js` required
  either way.

### `INTERVAL_QUARTER_LABELS`

- **Defined:** `domain/state.py:40` —
  `INTERVAL_QUARTER_LABELS: Final[frozenset[str]] = frozenset({"PRE", "HALF"})`.
- **Referenced:** `application/service.py` (import at line 84, used at 456,
  750, 1119, 1120, 1215, 1230, 1295 — football's `GameService` logic gating
  clock/quarter transitions) and `host/bridge.py` (import at line 93, used
  at 667 inside `spectator_view_model` to decide the event-clock block's
  shape).
- **Kind:** a plain module constant, but entangled with 7 call sites deep
  inside football's own `GameService`/`bridge.py` — not a simple lookup table
  an outside caller could reuse meaningfully.
- **Soccer path:** needs its own analogous constant (e.g.
  `SOCCER_INTERVAL_LABELS`) defined alongside a soccer `GameService`/
  view-model, since soccer needs its own service/bridge functions anyway.
  Football's constant is untouched and safe to leave as-is.

### `GAME_CLOCK_LABELS`

- **Defined:** `host/bridge.py:646-649`:
  ```python
  GAME_CLOCK_LABELS: Final[dict[str, str]] = {
      "PRE": "KICKOFF COUNTDOWN",
      "HALF": "HALFTIME COUNTDOWN",
  }
  ```
- **Referenced:** one call site, `bridge.py:712` —
  `.get(state.quarter, "GAME CLOCK")` inside `spectator_view_model`.
- **Kind:** a small, self-contained dict used only within football's own
  view-model function.
- **Soccer path:** a soccer equivalent (`soccer_spectator_view_model` or
  similar, in a new soccer bridge module) freely defines its own dict with
  soccer captions (e.g. "KICK-OFF COUNTDOWN"). No coupling risk — football's
  is untouched and never iterated by any test that would need updating.

### `_spectator_quarter_label`

- **Defined:** `host/bridge.py:433-436`:
  ```python
  def _spectator_quarter_label(label: str) -> str:
      """Expand only live-period labels; state keeps the compact football code."""
      return f"{label} Quarter" if label in {"1st", "2nd", "3rd", "4th"} else label
  ```
- **Referenced:** one call site, `bridge.py:698` —
  `"quarter_display": _spectator_quarter_label(state.quarter)`.
- **Kind:** a private (leading-underscore), single-call-site helper hardcoding
  football's exact quarter vocabulary and the word "Quarter" — soccer uses
  halves/periods, not quarters.
- **Soccer path:** needs its own equivalent (e.g. `_soccer_period_label`) in
  a soccer bridge module. Fully isolated; zero external coupling to worry
  about.

### `FINAL_HIDDEN_WIDGET_IDS`

- **Defined:** `presentation/layout.py:347-349`:
  ```python
  FINAL_HIDDEN_WIDGET_IDS: Final[tuple[str, ...]] = (
      "game_clock_label", "game_clock_value", "play_clock_label", "play_clock_value",
  )
  ```
  (also exported in `layout.py`'s `__all__`, line 4420).
- **Referenced:** `host/bridge.py` (import at line 116, used at 757 —
  `"hidden_widgets": list(FINAL_HIDDEN_WIDGET_IDS) if final else []` inside
  `spectator_view_model`'s FINAL-lifecycle widget-hiding logic) and
  `tests/integration/test_spectator_layout_render.py` (asserts this tuple is
  a subset of `layout.WIDGET_IDS` and equals the FINAL-lifecycle
  `hidden_widgets` view-model field exactly).
- **Kind:** a plain tuple of football's own widget-id strings, referencing
  football's own `WIDGET_IDS` registry; the one test checking it is scoped
  only to `layout.WIDGET_IDS`, blind to any parallel soccer registry.
- **Soccer path:** a soccer layout module (item 11's
  `presentation/soccer_layout.py`) with its own `WIDGET_IDS` registry
  defines its own analogous constant (e.g. `SOCCER_FINAL_HIDDEN_WIDGET_IDS`)
  referencing soccer's own widget ids. No shared/global widget-id space to
  collide in.

### Part C summary table

| Symbol | Location | Football-only or reusable? | Soccer path |
|---|---|---|---|
| `screenForLifecycle` | `board.js:3217` (shared file, called by `spectator.js:65`) | Generic enough to reuse as-is, or shadow with a soccer function | No edit to `board.js` needed either way |
| `INTERVAL_QUARTER_LABELS` | `domain/state.py:40`, 7 call sites in `service.py`/`bridge.py` | Entangled with football's service/bridge internals | Define `SOCCER_INTERVAL_LABELS` alongside a soccer service/bridge |
| `GAME_CLOCK_LABELS` | `bridge.py:646`, one call site | Self-contained dict | Define analogous dict in soccer's bridge module |
| `_spectator_quarter_label` | `bridge.py:433`, one call site | Private helper, football vocabulary | Define `_soccer_period_label` in soccer's bridge module |
| `FINAL_HIDDEN_WIDGET_IDS` | `layout.py:347`, checked only against football's own `WIDGET_IDS`/tests | Plain tuple, football widget ids | Define analogous constant in soccer's layout module |

None of the five Part C symbols require editing football's existing files —
each is either a self-contained constant/function soccer can define an analog
of in its own new modules, or (`screenForLifecycle`) generic enough to
potentially be called as-is.
