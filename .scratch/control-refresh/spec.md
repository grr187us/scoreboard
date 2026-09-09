# Scoreboard Control refresh — shared spec (September 8, 2026)

Owner decisions (asked and answered this session):

1. **Team choice after New Game: soft prompt.** The Teams drawer opens by itself after a
   New Game (and on first load of a pregame board whose names are still the defaults). It can
   be dismissed; nothing is locked. But the board must make "teams not chosen" impossible to
   miss, and the kickoff confirmation must say it in words.
2. **Scoring: Field Assistant + two-step on the main screen.** The `+1/+2/+3/+6` buttons no
   longer sit exposed. Each team panel has one `SCORE ▸` arm control; pressing it reveals the
   four point buttons (and a cancel) in the same space; one point press applies and disarms.
   Keyboard score keys become the same two steps (first press arms, second applies).
3. **Protection pattern: confirm dialog.** Undo (button and Ctrl+Z) shows a dialog naming
   exactly what will be reversed. Nothing on the main screen changes the score, quarter, or
   history with a single accidental press except the quick timeout below, which the owner
   asked to be one press (it is undoable).
4. **Quick timeout: charge only.** `HOME TIMEOUT` / `AWAY TIMEOUT` on the main screen send
   `timeout_used` for that team and nothing else. They do not touch the crowd message, the
   countdown, or any clock.

Plus the owner's other two asks:

5. **New Game / End Game / Reset Game Clock move into a `Game ▸` drawer.** They leave the
   always-visible tool bar. The drawer is the "separate danger area" of UX section 2.
6. **The spectator display can be closed from the display window itself.** Esc on the
   spectator window and a mouse-revealed corner button both close *only that window*; the
   operator health strip goes to `DISPLAY CLOSED` with one-click `Reopen Display`. The
   operator's Display drawer gets a `Close Display` button too. No game state changes (D-005).

Guardrails that still hold, verbatim from the repo's own rules:

- U-001: nothing on the operator page scrolls at 1366×768 or 1093×614; only the board flexes.
  `tests/ui/keyboard.cjs` measures every visible button at both viewports.
- K-001: every `CommandType` except `finalize_field_action` has a `data-command` control
  somewhere in `operator/index.html` (or a `'data-command', '<name>'` literal in operator.js).
  `tests/integration/test_bridge.py::MousePathTests` enforces it.
- F-016: text fields are drafts (`data-draft="true"`), read at click time only; no
  `input`/`change` listener in operator.js.
- Python owns every displayed string that describes game state. JS may own only view-state
  wording (button captions, dialog titles for local confirms — the existing pattern).
- The four kinds of ephemeral view state operator.js may hold become: open drawer, pending
  confirmation, unapplied typed text, and **which team's scoring is armed**. Update the file
  header comment.
- Never run `npm`/`pip install`. Node is at `C:\Program Files\nodejs` (not on PATH):
  `export PATH="/c/Program Files/nodejs:$PATH"` in Bash before any UI test.
- Test command (from repo root, Bash):
  `SCOREBOARD_DATA_DIR="$TMP/sb-test" ./.venv/Scripts/python.exe -m unittest tests.integration.test_bridge -v`
  (never add `-t .`). Full suite: `-m unittest discover -s tests -v` (about 60 s, includes browser suites when node is on PATH).

---

## 1. Cross-agent contract (pinned names — every agent hard-codes exactly these)

### 1.1 Operator view model addition (Python → operator page)

`operator_view_model()` in `src/scoreboard/host/bridge.py` adds:

```python
model["setup"] = {
    "teams_pending": bool,   # pregame lifecycle AND (home name is default OR away name is default)
    "home_pending": bool,    # pregame AND state.home_name == "HOME"
    "away_pending": bool,    # pregame AND state.away_name == "AWAY"
    "detail": str,           # "" when nothing is pending, else a plain sentence, see below
}
```

- "pregame" means `state.lifecycle in PREGAME_LIFECYCLES` (`"PRE_GAME"`).
- Default names are the `GameState` field defaults (`home_name="HOME"`, `away_name="AWAY"`).
  Expose them as module constants `DEFAULT_HOME_NAME` / `DEFAULT_AWAY_NAME` in
  `scoreboard/domain/state.py` and use them (do not re-type the literals in bridge.py).
- `detail` wording, exact:
  - both pending: `"Choose the HOME and AWAY teams before kickoff."`
  - home only: `"Choose the HOME team before kickoff."`
  - away only: `"Choose the AWAY team before kickoff."`
  - nothing pending: `""`
- The spectator view model does **not** get `setup` (the wall never shows operator prompts).
- The operator page must tolerate an older view model with no `setup` key (treat as nothing
  pending), the same way it tolerates a missing `undo_history`.

### 1.2 Kickoff confirmation names unchosen teams (Python)

`ScoreboardService._quarter_confirmation` (service.py): when `source == "PRE"` and the target
is not `PRE`, and either team name is still its default, the returned `detail` starts with
the same sentence as `setup.detail` above (e.g. `"Choose the HOME and AWAY teams before
kickoff. Change quarter from PRE to 1st. ..."`). `title` and `accept_label` are unchanged.
This is the "hard to miss" half of the soft prompt.

### 1.3 Closing the spectator window (Python host actions)

- `SpectatorBridge.__init__` gains keyword `close: Callable[[], dict[str, Any]] | None = None`
  and a method:

  ```python
  def close_display(self) -> dict[str, Any]:
      """Close this window only. Changes no game state (D-005)."""
  ```
  Returns `{"closed": bool, "message": str}`. With no `close` callable:
  `{"closed": False, "message": "This display cannot close itself in this build."}`.
  Update the class docstring: it is read-only *about the game*; the one action it exposes
  closes its own window and can reach nothing else.
- `DisplayLink` (bridge.py) gains a hook `close(self) -> DisplayStatus` (host-overridden; on
  its own it closes nothing and returns the current status), and `ScoreboardBridge` gains

  ```python
  def close_display(self) -> dict[str, Any]:
  ```
  a host action in the `reopen_display` family (under `_lock`, diagnostics-contained,
  advances no revision, writes no history row). Returns the `displays()` payload (so the
  drawer re-renders) — i.e. `{"displays": [...], "saved": ..., "match": ..., "status": {...},
  "view": {...}}`.
- `WindowHost.close_spectator(self) -> dict[str, str]` (app.py): under `_lock` take
  `self.spectator_window`, set it to `None`, destroy it outside the lock, then call
  `self.application.spectator_closed(CLOSED_BY_OPERATOR_DETAIL)` and `_set_status(...)`.
  The late `closed` event from that window must be a no-op (`_spectator_closed` already
  guards on identity). With no window open it returns
  `{"status": "DISPLAY CLOSED: no display window is open"}`-style plain message and changes
  nothing. Wire it: `application.display.close = self.close_spectator` (next to the existing
  `reopen`/`forget` wiring), and pass `close=self.close_spectator` into the `SpectatorBridge`
  created in `open_spectator`. The practice test window's `SpectatorBridge` gets
  `close=self.close_test_window` (a new small method that destroys `self.test_window` and
  forgets it — it never touches display health).
- Pinned detail string (module constant in app.py, `CLOSED_BY_OPERATOR_DETAIL`):
  `"The display window was closed on purpose. Reopen Display puts it back on the saved display."`
  After it, health is `open: False`, `label: "DISPLAY CLOSED"`, `can_reopen: True`,
  `needs_selection: False`.

### 1.4 Operator page bridge calls (JS → Python)

- `api.close_display()` → the `ScoreboardBridge.close_display` payload above; render
  `payload.view`, re-render the display drawer from it, and show `payload.status.detail`
  in the alert line.
- Everything else goes through `api.command(name, args, expectedRevision)` exactly as today.

### 1.5 Spectator page bridge calls (JS → Python)

- `api.close_display()` (may be absent on an older host: feature-detect with
  `typeof api.close_display === 'function'`, never throw).

---

## 2. Operator page — target layout

Same six grid rows; nothing new is a row. Only the contents of the team panels, the quarter
bar's UNDO, the tool bar, and the drawers change.

```
┌ health strip: unchanged ─────────────────────────────────────────────────────────────────┐
├ alert line: unchanged ───────────────────────────────────────────────────────────────────┤
│ HOME ◀ BALL          │ GAME CLOCK   12:00      │ AWAY                                     │
│ EAGLES               │ STOPPED [START][STOP]   │ TIGERS                                   │
│ (identity stripe)    │ PLAY CLOCK  25          │ (identity stripe)                        │
│ NOT CHOSEN (pregame only, when name is default) │ NOT CHOSEN …                            │
│        14            │ [25][40] [25+START]…    │        7                                 │
│ [ SCORE ▸ ][TIMEOUT 3]│                        │ [ SCORE ▸ ][TIMEOUT 2]                   │
│   armed →  [+1][+2][+3][+6][✕]  (same height as the row it replaces)                     │
├ crowd bar: unchanged ────────────────────────────────────────────────────────────────────┤
│ QUARTER [◀] 1st [▶]  3rd & 7 · EAGLES 35 · TO 3/2     LAST: Away +6 (7) ×3  [UNDO…]     │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ [Teams ▸][Corrections ▸][Halftime ▸][Field ▸][Field Assistant][Cutscenes][Shortcut Help] │
│ [Advanced ▸]                                                              [ Game ▸ ]     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Team panel (`section.team`, both sides mirrored)

- Keep: `h2` with possession flag, `.team-name`, `.identity-stripe`, `.score`.
- Add `<p class="team-pending" id="home-pending" hidden>NOT CHOSEN</p>` (and `away-`),
  shown iff `model.setup.home_pending` (resp. `away_pending`). Warn colour (`--warn`),
  small caps, text first. It sits between the stripe and the score and must cost under 20px
  so U-001 holds; when hidden it takes no space.
- Replace `.score-buttons` with a `.score-controls` block of **fixed height** (one 52px row):
  - Idle state (`data-armed="false"`): `[ SCORE ▸ ]` (`data-action="arm_score"
    data-team="home"`, id `home-arm`) and `[ TIMEOUT · 3 ]` (`data-command="timeout_used"
    data-team="home"`, id `home-timeout`; its count is a nested
    `<span data-field="football.timeouts.home">`). The timeout button is `disabled` when the
    count is 0 (render-time; Python still rejects below zero).
  - Armed state (`data-armed="true"`): `[+1][+2][+3][+6]` as the real
    `data-command="add_score" data-team="home" data-points="N"` controls (K-001 unchanged),
    plus `[✕]` (`data-action="disarm_score"`, aria-label "Cancel scoring").
  - Only one team can be armed at a time; arming one disarms the other.
  - Auto-disarm after **8 seconds** with no point press (a `setTimeout` — the only timer this
    file may own; it computes no game value). Disarm also on: a point press (accepted or
    rejected), Escape, opening any drawer, a confirmation dialog opening, or window blur.
  - Toggle visibility with `hidden` on the two inner groups, never `style.display`, and
    keep both groups inside the same fixed-height block so the panel's height never changes.
  - Armed visual: the armed panel gets `class="team is-armed"` (accent border) and the point
    buttons are the large `.wide`-style targets they were. Text first: the arm button's
    caption changes to `SCORING…` while armed? No — the arm button is hidden while armed;
    the `✕` and the highlighted border carry the state, and the `h2` gains a visible
    `<span class="armed-flag">` reading ` · SCORING` (text, not colour alone, U-002).

### 2.2 Quarter bar

- `UNDO` becomes `UNDO…`: `data-command="undo" data-confirm="local"
  data-confirm-title="Undo the last action?"`. `describeChange()` for `undo` returns
  `'Reverses: ' + model.last_action.label` (Python's label; JS adds only the prefix).
  Both undo buttons (quarter bar and `#history-drawer`) carry the same attributes; the
  history drawer's is the same control so `test_crowd_status_ui` keeps finding
  `data-command="undo"` inside the drawer.
- Ctrl+Z: the keyboard binding gains `confirm: true`; `ScoreboardKeyboard.install` calls
  `options.confirm(command, args, {title})` instead of `options.submit` for such bindings,
  and operator.js's `confirm` opens the same dialog (`change` = `Reverses: …`) with
  `source: 'operator-keyboard'`. The dialog's Confirm resubmits with `confirmed: true` as
  today (the service ignores `confirmed` on undo; the round trip is identical to any other
  local confirm).
- Everything else in the bar (quarter ◀ ▶, field status, LAST strip) unchanged.

### 2.3 Tool bar

Order: `Teams ▸`, `Corrections ▸`, `Halftime ▸`, `Field ▸`, `Field Assistant`,
`Cutscenes`, `Shortcut Help`, `Advanced ▸`, spacer, `Game ▸` (`id="open-game"
data-action="open_game" class="danger"`). The three danger `data-command` buttons leave
this footer. While `model.setup.teams_pending` is true the `Teams ▸` button gets class
`is-attention` (warm border + `title="Choose the teams before kickoff."`).

### 2.4 Game drawer (new, `id="game-drawer"`, aria-label "Game")

```
GAME
hint: Nothing here happens without a confirmation. Scores and clocks stay on the main screen.
row  Game clock  [Reset Game Clock…]   (data-command="game_clock_reset" data-confirm="local", titles as today; operator.js keeps updating its confirmDetail for PRE)
row  This game   [End Game…]           (data-command="end_game" data-confirm="local", as today)
row  Next game   [New Game…]           (data-command="new_game"; the service asks for confirmation)
row.end [Close]
```
All three keep `class="danger"`. Add `'game-drawer'` to `closeDrawers()`.

### 2.5 Corrections drawer

- Score rows gain `+1 +2 +3 +6` **before** the existing `−1…−6`: `data-command="add_score"`
  for the team, no confirm (they are inside the drawer, which is the protection). Keep the
  set-score input + Apply….
- Everything else unchanged (clock edits, quarter choices, pregame team names, data folder).

### 2.6 Teams drawer — the soft prompt

- Add `<p class="hint attention" id="teams-prompt" hidden></p>` at the top of the panel;
  its text is `model.setup.detail` and it is shown iff `teams_pending`.
- operator.js opens this drawer by itself (`openDrawer('teams-drawer'); refreshTeams();`) in
  exactly two places:
  1. in `handleResult` when `name === 'new_game' && result.accepted`;
  2. once, in the `R.whenReady` snapshot callback, when the first rendered model has
     `setup.teams_pending === true` (a fresh game at launch, or a recovered pregame board
     with default names).
  It never re-opens on its own after that (no polling on `render`), so a dismissed prompt
  stays dismissed until the next New Game.

### 2.7 Display drawer

- Add `[Close Display]` (`id="close-display" data-action="close_display"`) in the status
  row, shown iff `health.display.open`. Handler: `api.close_display()` → `renderDisplays(
  payload)` (which renders `payload.view`) and `showAlert(payload.status.detail)`.
- `test_display_drawer_contract` requires the drawer to hold host actions only and no
  `danger` class — keep it that way.

### 2.8 Keyboard (keyboard.js)

- Score keys `Z X C V` / `N M , .`: the binding gains `arm: 'home'|'away'` and keeps
  `command: 'add_score'`/`args`. `install` routes them to `options.score(binding)`; in
  operator.js: if that team is currently armed → `submit('add_score', args, {source:
  'operator-keyboard'})` and disarm; else arm that team (no bridge call). Help text becomes
  e.g. `Home +6 (press once to arm, again to apply)`.
- `Ctrl+Z` → `confirm: true` (2.2).
- New binding: `Escape` already closes dialog/drawer; extend `options.close()` so it also
  disarms scoring (Escape with nothing open and a team armed just disarms).
- Everything else (clocks, quarter, cutscene host keys, F13–F20) unchanged.
- `tests/ui/keyboard.cjs` + `test_keyboard_browser.py`: update the `map` rows for score keys
  (press twice; assert first press sends nothing and arms, second sends `add_score`), the
  Ctrl+Z row (a dialog, confirmed through `#confirm-accept`), the focused-button repeat test
  (it focuses `[data-command="add_score"]…` — arm first via the SCORE button click), the help
  table expectation, and the shortcut count. The startup-page block and the U-001 fit loop
  stay as they are (the fit loop must pass with a team armed as well: arm HOME, then run it).

### 2.9 What must not change

- The health strip, crowd bar, clocks column, Halftime, Field, History, Help, Advanced
  drawers, the confirmation dialog, `submit()`/`handleResult()`'s revision handling, and every
  `data-field` binding.
- `render()` still computes nothing; the arm state and its timer are the only new view state.

---

## 3. Spectator page — closing from the window

Files: `src/scoreboard/views/spectator/index.html`, `spectator.js`, `spectator.css`.

- `index.html`: add, inside `<main id="canvas">` after the stage,
  `<button type="button" id="close-display" class="close-display" hidden
  aria-label="Close this display window">✕ CLOSE DISPLAY (Esc)</button>`. It is the only
  interactive element the page has ever had; the source-contract tests that say "control-free"
  mean *no game command* (`data-command`, `api.command`) — keep that literally true.
- `spectator.js`:
  - `keydown` on `document`: `Escape` → `requestClose()`. Ignore repeats.
  - `mousemove`/`pointermove` on `document`: show the button (`hidden=false`) and restart a
    3-second timer that hides it again. A wall with no pointer never sees it. Click → `requestClose()`.
  - `requestClose()`: if `api && typeof api.close_display === 'function'`, call it once and
    ignore the result (the window is going away); otherwise do nothing. Guard against double
    calls with a local flag. Never throw; wrap in try/catch like the rest of the file.
  - Store the `api` from `R.whenReady` in a module variable so the handlers can reach it.
- `spectator.css`: `.close-display` is `position:absolute; top:12px; right:12px;` on the
  canvas, 44px min height, high-contrast (white on `rgba(0,0,0,.75)` with a 2px white border),
  `z-index` above the cutscene stage, `cursor:pointer`, and never affects layout (absolute).
- Tests: `tests/integration/test_spectator_close_ui.py` (new, source contract in the style of
  `test_crowd_status_ui.py`): the button exists and is `hidden` by default; `spectator.js`
  handles `Escape`, feature-detects `close_display`, and the three spectator files still
  contain no `data-command`, `api.command`, or `CommandType` value. Run
  `tests.integration.test_spectator_layout_render` and `tests.integration.test_cutscene_player_contract`
  afterwards; if either pins "no `<button>`" literally, extend it to allow exactly this one id
  and say why in the test.

---

## 4. Python — tests each agent owns

- `tests/integration/test_display_close.py` (new): with `test_display_selection.py`'s
  `DisplayHostTestCase` fakes — `close_spectator` destroys the open window, health becomes
  `DISPLAY CLOSED` with `can_reopen: True` and `needs_selection: False` and the pinned detail,
  a running game clock keeps running and the revision does not move, the late `closed` event
  from the destroyed window is a no-op, `reopen_spectator` afterwards opens a new window on
  the saved display, `close_spectator` with no window open reports plainly, the
  `SpectatorBridge` handed to the spectator window can call `close_display()` and get
  `closed: True`, a `SpectatorBridge` built without `close` answers `closed: False`, and the
  operator bridge's `close_display()` returns the `displays()` payload, advances no revision,
  and writes no history row. `close_test_window` closes only the practice window.
- `tests/integration/test_team_setup_prompt.py` (new): `setup` block on the operator view for
  fresh/home-set/away-set/both-set/after-kickoff; the four exact `detail` strings; absent from
  the spectator view; the kickoff confirmation detail starts with the sentence while a name is
  default and is unchanged once both are chosen; `set_team_name` clears the flag; `new_game`
  brings it back.
- `tests/integration/test_operator_refresh_ui.py` (new, owned by the operator-page agent):
  source contract — no `add_score` control outside `.score-controls`/`#corrections`;
  `.score-controls` point buttons are `hidden` by default; both `undo` controls carry
  `data-confirm="local"`; the tool bar holds no `data-command` at all and offers `open_game`;
  `#game-drawer` holds exactly `game_clock_reset`, `end_game`, `new_game`; `timeout_used`
  appears once per team on the board; `#close-display` and `close_display` in operator.js;
  `#teams-prompt`; `new_game` accepted → `openDrawer('teams-drawer')`; `closeDrawers` names
  `game-drawer`; keyboard score bindings carry `arm:`; Ctrl+Z carries `confirm: true`.
- Existing tests to update (operator-page agent): `test_bridge.py` —
  `test_dangerous_corrections_confirm_locally_before_anything_is_sent` add `"undo"`; nothing
  else there should need to change. `test_crowd_status_ui.py` (`grid-template-rows` line and
  `.crowd-bar` rules stay) — check `test_the_crowd_row_never_sends_a_scoring_or_timeout_command`
  still passes (the crowd row itself is unchanged). `test_team_presets_ui.py` unchanged.
  `test_cutscenes_ui_contract.py` pins keyboard.js lines for D/T/O/F/L/Shift+C — leave those
  lines byte-identical.

---

## 5. Docs (last agent, after the code lands)

`docs/UX_AND_LAYOUT.md` sections 2, 4 (wireframe + main-screen rules), 5 (Corrections +N), a
new 5c "Game drawer" and 5d "Teams prompt", 6.1 step 4, 6.4 (scoring is two-step), 6.5
(Undo confirms), 6.8 (closing the display from the window; Close Display in the drawer), 6.9
(End Game lives in Game ▸), section 8 checklist (U-001 re-measured: record the keyboard.cjs
result), and the keyboard map. `docs/ARCHITECTURE.md`: `SpectatorBridge` now has one
self-closing action; D-005 unchanged. `PROJECT_ROADMAP.md`: an "owner request 5 — control
refresh, September 8, 2026" entry listing the four decisions above. `tests/README.md`: the
three new test files. Run `./.venv/Scripts/python.exe tools/check_markdown_links.py`.
