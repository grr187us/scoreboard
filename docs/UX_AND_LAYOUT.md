# Operator Workflow and Initial Layouts

**Status:** Implemented Phase 2 operator, spectator, recovery, Field Assistant, and layout-editor design baseline. Development-host visual and WebView2 checks exist; physical two-display, 1366×768 at 100%/125% scaling, stadium, and volunteer-rehearsal evidence remain open.
**Last updated:** September 6, 2026 (reconciled I4's 20-entry Undo history, F3's crowd-facing status message and countdown, C5's Display drawer, Field Assistant evidence, and the new Cutscenes window)

## 1. Design intent

The first operator may be a student or volunteer working under time pressure. The interface therefore favors large explicit controls, visible state, reversible ordinary actions, and deliberate dangerous actions. It does not try to resemble a television production console.

The operator and spectator surfaces are separate windows backed by the same authoritative state. The operator sees controls and health information; spectators never do.

Phase 2 is operated from one laptop by the primary operator. A second person is anticipated to operate a future peripheral, but that peripheral remains outside the MVP; its absence cannot block the laptop workflow.

## 2. Control hierarchy

| Frequency/risk | Controls | Treatment |
|---|---|---|
| Constant, time-critical | Game Start/Stop; play-clock 25/40; score `+1/+2/+3/+6` | Large, always visible, one action, keyboard-accessible |
| Frequent | Quarter next; Undo | Visible on main screen; every quarter move confirms |
| Corrective | Score minus/direct set; clock edit; quarter back/direct set | Collapsed correction drawer with old/new preview |
| Pregame | Team names; quarter length; display choice; shortcut help | Setup panel before the game; locked/collapsed during play |
| Dangerous | New Game; reset game clock; End Game | Separate danger area with confirmation or hold/arm pattern |

Color is supplemental, not the only state signal. Text labels such as `RUNNING`, `STOPPED`, `DISPLAY CLOSED`, and `STATE SAVED` remain visible.

## 3. Spectator display wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│       HOME                                             AWAY                  │
│                                                                              │
│        00                                                00                  │
│                                                                              │
│                         ┌────────────────────┐                               │
│                         │       12:00        │  GAME                         │
│                         └────────────────────┘                               │
│                                                                              │
│              TIMEOUT                         1:00                            │
│                                                                              │
│            1st Quarter                   PLAY CLOCK 40                         │
│                                                                              │
│         3rd & 7            ◀ EAGLES            HOME 35                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

The `TIMEOUT` line and the `1:00` beside it are F3's crowd status message and its countdown (added September 6, 2026, section 4.8a of `docs/MVP_REQUIREMENTS.md`). Both are optional widgets sitting in the free band between the scores and the game clock, and both are blank — and so hidden — whenever no status is raised, which is most of a game. They are the board's answer to a stoppage: without them the wall simply froze, still showing the previous down and distance, with nothing to tell the crowd why.

The bottom row was added on September 5, 2026 with the football-state fields (F-060 to F-066). Its four widgets — `down`, `distance`, `possession`, and `ball_on` — are *optional*: the renderer hides a widget whose value is absent from the snapshot rather than drawing an empty box, so a board with no possession set simply omits that indicator. Three of the original fifteen widgets default to hidden entirely — the `GAME CLOCK` label and the two timeout counters — because they are a layout choice rather than a required field (D-001); the editor can turn them on. Two later Status widgets also hide on absent values and are not yet backed by authoritative F3 state. There is no local-time widget on the spectator board: P-010's Eastern-time formatting is for recovery and history timestamps in the operator and startup surfaces.

Visual priorities are scores first, game clock second, team names third, then quarter and play clock. The exact proportions, safe area, font, and color contrast must be tested on a normal monitor and revisited after the stadium HDMI test identifies the real canvas and viewing conditions.

### Responsive strategy

- Render inside a logical 16:9 design canvas, centered within any physical viewport.
- Scale through CSS variables, viewport units, `clamp()`, and grid/flex layout rather than fixed pixels.
- Letterbox or pillarbox deliberately when aspect ratios differ; never stretch text.
- Keep a configurable safe-area inset, provisionally 4% on all sides.
- Use local system fonts (Arial/sans-serif) with tabular numerals and white-on-black contrast; no font download.
- Test at 1280×720, 1366×768, 1920×1080, and one portrait/narrow mode before stadium dimensions are known.
- After the HDMI test, add the confirmed resolution/refresh/overscan mode to the test matrix rather than hard-coding a new layout.

**Widget-rendered board (added September 5, 2026).** The board above is now drawn from seventeen individually positioned, sized, and colored game widgets (`views/shared/board.js`) rather than a fixed CSS grid. Fifteen are the original scoreboard fields; the two Status widgets carry F3's crowd message and its countdown, and render nothing until an operator raises one (section 4.8a). The arrangement shown here is the *built-in default* layout, not a hard-coded one — see section 10 for the editor that changes it. The pregame/halftime event-countdown presentation (`KICKOFF IN…` / `UNTIL SECOND HALF…`) was a separate fixed markup until September 6, 2026; it is now drawn from the active layout's **Pre-game** and **Halftime** screens (eight event widgets: both names and scores, phase label, countdown title, countdown, warmup line), whose built-in defaults reproduce the earlier centred arrangement — including the score beneath the countdown, so the wall is never scoreless during an intermission — and which the editor can rearrange like the game board (section 10.9).

## 4. Operator-screen wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SCOREBOARD CONTROL   GAME: 1st 12:00 STOPPED   PLAY: 40 STOPPED              │
│ Display: OPEN ✓  [Reopen Display] [Display…]   State: SAVED ✓   Rev 184     │
├──────────────────────────┬──────────────────────────┬────────────────────────┤
│ HOME                     │ CLOCKS                   │ AWAY                   │
│ EAGLES              14   │                          │ TIGERS              7  │
│ [ +1 ] [ +2 ] [ +3 ]    │ GAME CLOCK               │ [ +1 ] [ +2 ] [ +3 ]  │
│ [       +6       ]       │       12:00              │ [       +6       ]     │
│                          │ [ START ]    [ STOP ]     │                        │
│                          │ STOPPED                  │                        │
│                          │                          │                        │
│                          │ PLAY CLOCK      40       │                        │
│                          │ [ 25 LOAD ]   [40 LOAD]│                        │
│                          │ [ START ]      [ STOP ]  │                        │
├──────────────────────────┴──────────────────────────┴────────────────────────┤
│ CROWD  [TIMEOUT]  [FLAG][TIMEOUT][INJURY][DELAY][CLEAR]  1:00 [START][STOP]  │
├──────────────────────────────────────────────────────────────────────────────┤
│ QUARTER [◀] 1st [▶] 3rd & 7 · EAGLES 35 · TO 3/2 LAST: Away +6 (7) ×3 [UNDO] │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Teams ▸ ] [ Corrections ▸ ] [ Halftime ▸ ] [ Field ▸ ] [ Field Assistant ] │
│ [ Shortcut Help ] [ Advanced ▸ ]                                             │
│                                              [ End Game… ] [ New Game… ]     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Main-screen rules

- Do not require scrolling for live controls at 1366×768 and 100%/125% scaling.
- Keep team controls spatially mirrored but use explicit HOME/AWAY names on every correction.
- Use separate Start and Stop buttons. Disable or visually de-emphasize the action that is already true.
- Show running/stopped text next to each clock; do not rely on color alone. A
  running game clock is green and a running play clock is red as rapid
  supplementary cues.
- Show the last reversible action and Undo without opening a menu. The `LAST:`
  strip is also the button that opens the Undo history (U-009, audit item I4);
  a small `×N` badge beside it counts the further Undos waiting behind the one
  named, and is hidden at 0 and 1 where it would say nothing new.
- **Added September 6, 2026 (audit item F3).** The crowd row sits directly
  above the quarter bar and is always visible: a chip showing what the wall is
  currently saying, one button per status message, `CLEAR`, and the status
  countdown with its own Start/Stop. It is deliberately not a drawer — a
  message an operator must open a menu to raise is a message that does not get
  raised during a live game. `TIMEOUT` raises the word and starts 1:00 in one
  press; it does **not** charge the timeout, which stays with the separate,
  undoable `timeout_used` control in the Field drawer (section 5a). Like the
  quarter bar it is a fixed-height grid row, so only the board flexes and the
  U-001 no-scrolling measurement still holds; see section 8 for the numbers.
- A display-health failure must take over the health strip but must not obscure clocks or controls.
- Down/distance, field position, and timeouts remaining (added September 5,
  2026) read compactly in the quarter bar, next to the existing quarter
  control rather than as a new row, so the U-001 no-scrolling measurement is
  unaffected. Possession is a short text flag (`◀ BALL` / `BALL ▶`) next to the
  team name it belongs to, not color alone (U-002's principle applied to a new
  field). See section 5a for the controls that set these.
- **Added September 6, 2026 (audit item C5).** `Reopen Display` meets the
  44px accessibility floor and only appears when a display can actually be
  reopened one click (`can_reopen`). A second, always-visible `Display…`
  button sits next to it and opens the Display drawer (section 5b) whether or
  not a reopen is currently possible; it is deliberately quieter (`--edge`
  border) so `Reopen Display`'s warm border stays the one to reach for when
  the wall has gone dark. Both are 44px targets; measured heights and
  overflow results are recorded in section 8.

## 5. Corrections drawer

```text
┌──────────────────────────── CORRECTIONS ─────────────────────────────────────┐
│ Home score: 14  [−1] [−2] [−3] [−6]  Set [ 14 ] [Preview / Apply…]          │
│ Away score:  7  [−1] [−2] [−3] [−6]  Set [  7 ] [Preview / Apply…]          │
│ Game clock: [12]:[00]  (must be stopped)                  [Preview / Apply…] │
│ Quarter: [PRE | 1st | 2nd | HALF | 3rd | 4th | OT | FINAL] [Apply…]          │
│ Play clock: [00]  (must be stopped)                       [Preview / Apply…] │
│                                                               [Close]        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Typing does not change live state. Apply opens a confirmation such as `Change HOME score from 14 to 8?`; cancel is the default focused action for destructive corrections. Minus corrections are logged and undoable.

## 5a. Field status drawer (added September 5, 2026)

```text
┌───────────────────────────── FIELD STATUS ────────────────────────────────────┐
│ Down 3rd & 7        [1st] [2nd] [3rd] [4th] [Clear]                          │
│ Distance to go      [__] [Set] [Goal] [Clear]                                │
│ Possession          [HOME] [AWAY] [Clear]                                    │
│ Ball on EAGLES 35   (HOME|AWAY) [__] [Set]                                   │
│ HOME timeouts 3     [Timeout used] [+1] [__] [Set]                          │
│ AWAY timeouts 2     [Timeout used] [+1] [__] [Set]                          │
│                                                                Close          │
└──────────────────────────────────────────────────────────────────────────────┘
```

Down/distance, possession, field position, and timeouts are frequent,
low-risk, fully reversible corrections in the same sense as a scoring
increment (F-060 through F-066), so **none of these controls require
confirmation**, matching the owner's stated preference that routine reversible
actions should not gain a confirmation dialog they did not ask for. They are
collected in their own drawer, alongside Corrections/Halftime/Advanced,
because the always-visible board is already at its U-001 budget; the
compact readout in the quarter bar (section 4) is what stays always visible.

Field position is one control, not two: the HOME/AWAY toggle only changes
which team's goal line the yard-line field is counted from (a local UI
selection, like a drafted score before Apply), and a single **Set** reads both
at click time and submits one atomic command. This mirrors why the field is
one state value rather than two -- entering a mismatched side and yard line
can never happen, because there is no way to submit half of it.

Down and distance are cleared independently (`Clear` next to each), for a
situation where only one of the two is currently known -- for example,
between plays before the next down is confirmed. Distance `0` is offered as a
dedicated **Goal** button, since "4th & 0" reads as a typo rather than a
goal-to-go situation; the board displays it as `4th & Goal` either way
(F-061).

## 5b. Teams drawer (added September 6, 2026, audit item F4)

```text
┌───────────────────────────────── TEAMS ───────────────────────────────────────┐
│ Pick a saved team for each side. Team names can change only before kickoff,   │
│ and each change asks you to confirm. Colours and short names are saved for    │
│ the board; they never change scores or clocks.                                │
│ Now   [▮▮] EAGLES (EAG)                    [▮▮] TIGERS (TIG)                  │
│ ─────────────────────────────────────────────────────────────────────────────│
│ [▮▮] EAGLES (EAG)     [Use for HOME] [Use for AWAY] [Edit] [Delete…]          │
│ [▮▮] TIGERS (TIG)     [Use for HOME] [Use for AWAY] [Edit] [Delete…]          │
│ ─────────────────────────────────────────────────────────────────────────────│
│ Save a team  [name____] [short_] [primary] [secondary] [Save team]           │
│              [Use HOME name] [Use AWAY name]                                  │
│                                                                Close           │
└──────────────────────────────────────────────────────────────────────────────┘
```

Opened by the new `Teams ▸` tool-bar button (section 4), the first button in
the bar. F4's scope is the S–M "presets" half of the deep-dive finding: a
saved team library with one-click apply, a short name, and two colours. Visual
identity on the spectator board (colour-bound widgets, logos) is explicitly
out of scope for this pass; only the data needed for that later work is
carried in the view model today (see below).

Team identity is **not** game state. `GameState` still keeps only
`home_name`/`away_name`; applying a saved team submits the same, existing,
validated `set_team_name` command an operator could type by hand --
pregame-only (F-010), undoable, and recorded in the action history exactly
like a manual retype. The **library** of saved teams is a laptop preference,
like the presentation layout or the saved display: its own file
(`teams.json`), never the game database, and never able to stop the
scoreboard.

- **Now** mirrors the two live team names with a small swatch (left half the
  saved primary colour, right half secondary) and the saved short name, when
  the current name matches something saved; the swatch and short name are
  hidden when it does not.
- The **list** is built from `api.teams()`, one row per saved team: swatch,
  name and short name, then `Use for HOME` / `Use for AWAY`. These are
  ordinary controls -- the same `set_team_name` command, the same local
  confirmation showing `OLD → NEW`, the same source and revision handling as
  every other correction in this document. Applying a preset after kickoff is
  refused by the bridge exactly like a manual retype would be, and the
  refusal is shown the same way. `Edit` copies a saved team into the form
  below without submitting anything; `Delete…` opens the same confirmation
  dialog used everywhere else in this page, with Cancel doing nothing at all.
  An empty library shows a plain sentence instead of an empty list.
- The **form** saves a name (24 characters, matching the existing team-name
  limit), an optional short name (up to 6 characters, derived from the name
  when left blank), and two colour pickers (defaulting to white and near-black
  the first time). `Use HOME name` / `Use AWAY name` only copy the current
  name into the field -- nothing is submitted until `Save team` is clicked.
  Saving or deleting shows Python's plain-language result (`Saved team
  EAGLES.`, `Updated team EAGLES.`, `Deleted team EAGLES.`, or a refusal such
  as a name already 24 characters over the limit) the same way every other
  host action reports its result.
- On the live board, each team name grows a thin **identity stripe**
  (primary-coloured background, secondary-coloured underline, the short name
  centred in it) directly under the team name, when the current name matches
  a saved team; it is hidden otherwise. It is deliberately thin -- height plus
  border stays under 18px -- because the board's height budget was already
  spent meeting U-001, and this must never be the thing that pushes a live
  control off screen. Measured against a real bridge-produced view model at
  1093×614 (the tightest U-001 viewport): `documentElement.scrollHeight`
  equalled `clientHeight` with the stripe visible on both sides, exactly as it
  did before this feature existed.
- If a build's bridge does not expose `api.teams`/`api.save_team`/
  `api.delete_team` (an older build, or one where the host wiring is not yet
  present), the drawer says "Saved teams are unavailable in this build." and
  the form is disabled. The rest of the operator page is completely unaffected
  -- this is a convenience layer over an existing command, never a dependency
  of it.

## 6. Workflows

### 6.1 Pregame setup

1. Launch the application once; both windows open.
2. If recoverable state exists, choose `Resume recovered game` or `Start new game`. Recovered clocks are stopped.
3. Select the spectator display from the settings panel and enter fullscreen.
4. Enter home and away names; verify the stopped 30:00 PRE Game Clock and selected display.
5. Verify 0–0, `PRE`, `KICKOFF IN 30:00`, stopped play clock, `DISPLAY OPEN`, and `STATE SAVED`.
6. Visually confirm the spectator display and run a short score/clock rehearsal, then restore the starting state through `New Game`.

### 6.1a Pregame, halftime, and warmup presentation

- PRE renders the authoritative Game Clock as `KICKOFF IN 30:00`; the operator Game Clock card shows that same value and state. HALF shows the separate interval, and playing quarters show the game board.
- Before kickoff, Game Clock Start/Stop/Reset/Edit control only the PRE countdown. It does not enter 1st quarter or affect the play clock; natural expiry remains PRE at `0:00`.
- At halftime, the spectator display shows one `UNTIL SECOND HALF` 15:00 countdown. While more than 3:00 remains it labels the current phase `HALFTIME` and visibly states `Warmup follows: 3:00`.
- At 3:00, the same countdown continues without a reset and its current-phase label changes to `WARMUP`.
- The halftime countdown uses the same reliable timing model but remains a separate control. Pregame has no second countdown control.
- **Added September 6, 2026 (verified in the real pywebview runtime the same day).** The on-screen arrangement of this presentation is now the operator's choice: the pregame and halftime screens described above are drawn from the active layout's Pre-game and Halftime screens — the same stored layout document that draws the game board — using a dedicated set of *event widgets* (home/away team name and score, phase label, countdown title, countdown, and warmup line). Every value named above (`KICKOFF IN 30:00`, `UNTIL SECOND HALF`, the `HALFTIME`/`WARMUP` phase label, `Warmup follows: 3:00`) is still produced in Python exactly as this section describes; only where each value is drawn, and how it looks, is now an editable presentation choice. See section 10.9 for the switcher, the event widget inventory, and the per-screen presets.

### 6.2 Start and stop the game clock

- Click the large Start or Stop button, or press `Space` outside any text field.
- The authoritative state changes once, the status text changes immediately, and the action is logged.
- Start while running and Stop while stopped are harmless no-ops.
- A stalled UI repaint does not affect the authoritative elapsed-time calculation.
- The display never understates time remaining: whole seconds are always rounded up, shown as `M:SS` even below a minute; neither clock displays tenths of a second (September 7, 2026). `1:00` remains visible until the clock truly reaches `0:59`.
- `Edit Current Time` stops the game clock if needed, validates the entered minutes/seconds, and then offers `Start after applying?`; `Remain stopped` is selected by default.

### 6.3 Reset play clock to 25 or 40

- Click `25 LOAD` / `40 LOAD`, or press the mapped key.
- The requested value loads while stopped; use the separate play-clock Start command when the official signals ready for play.
- Click the visibly distinct `25 + START` / `40 + START` controls to load that preset and begin its countdown in one atomic action. The plain load controls remain available for a stopped setup.
- The game clock is unchanged.
- The play clock uses the same upward, whole-seconds-only presentation rule; it stays at `5` until it truly reaches `4`.
- This is the stadium's only play-clock display, so the active value must remain prominent and display recovery must preserve it.
- In `1st`–`4th`/`OT`, Game Clock start/stop coupling clears the play clock as documented. In PRE, Start/Stop/expiry control only the kickoff countdown.
- No clock expiration produces an alarm. A play clock that reaches `0` while the game clock is already running remains visible there until the operator uses the deliberate clear control or issues another play-clock command.
- `Edit Current Time` lives in Corrections: it stops the play clock if needed, validates the value, and offers `Start after applying?`; `Remain stopped` is the default.

### 6.4 Update scores

- Click the appropriate team increment or use its shortcut.
- The new score appears in both views, the last-action strip identifies the change, and Undo becomes available.
- Held keys and double-generated browser events must not repeat a score.

### 6.5 Correct a mistake

1. For the immediately preceding reversible command, use Undo.
2. Otherwise open Corrections and use a labeled minus control or direct set.
3. Direct set displays the team, old value, and proposed value before confirmation.
4. A correction is appended to history; the original event is never erased.

The `LAST:` area opens the current Undo history: newest first, at most 20
reversible entries. Each press of Undo reverses the newest entry and records a
new action. A non-reversible barrier clears the available stack, and recovery
starts with an empty stack even though the durable action history remains.

### 6.5a Tell the crowd why play stopped (added September 6, 2026, audit item F3)

1. Press `FLAG`, `TIMEOUT`, `INJURY`, or `DELAY` in the always-visible crowd
   row. The word appears on the wall immediately; the operator board's chip
   shows what the wall is currently saying, and the button that is raised stays
   lit.
2. `TIMEOUT` also loads and starts a 1:00 countdown in the same press. The
   other three raise the word with no countdown.
3. `START`/`STOP` control the countdown without changing the message. A
   countdown that runs out stops at `0:00` and stays there — the message does
   not clear itself, because only the operator knows when play has resumed.
4. Press `CLEAR` when play resumes. The message and the countdown both go, and
   the wall's two Status widgets hide rather than drawing empty boxes.

None of these touch the score, the clocks, the quarter, or field status, and
none of them consumes an Undo (F-081): a crowd toggle must never push a
scoring mistake out of Undo's reach. Charging the timeout against a team is
still the separate, undoable `timeout_used` control in the Field drawer
(section 5a) — the crowd row says *what the wall shows*, not *what the game
records*.

### 6.6 Change quarters

- Use next/back on the main screen or direct selection in Corrections.
- Every path opens one Python-described confirmation, even with clocks stopped. It names source/target, the running clocks that will stop, and any clock value that loads; cancel sends no mutation.
- With pregame time remaining, PRE → 1st uses the stronger accepting action `Start 1st quarter — discard remaining pregame time`. Acceptance discards PRE time, loads stopped 12:00, and enters normal first-quarter behavior. At PRE `0:00`, the normal confirmation is used. Direct selection and keyboard use the same expected-revision protection.

### 6.7 Recover after application restart/crash

1. Relaunch from the normal shortcut/executable.
2. The recovery screen states when the snapshot was saved and whether the primary or backup was used. **The saved time is shown in readable Eastern local time** (for example, `September 5, 2026 at 10:41 AM EDT`, added September 5, 2026), not a raw UTC timestamp; the underlying stored value remains UTC (P-010).
3. Choose Resume to restore names, scores, quarter, and last clock values with both clocks stopped.
4. Compare the restored state with the game situation, make logged corrections if needed, then deliberately restart clocks.
5. If recovery is unavailable/corrupt, keep the vendor system available and use a new game only after confirming the correct live state.

### 6.8 Recover after spectator display closes

- Operator controls and clocks continue.
- The health strip changes to `DISPLAY CLOSED` and exposes `Reopen Display`.
- Reopen creates the view using current authoritative state, on the saved display if available.
- If the saved display is absent, show an explicit display selector; do not silently steal the operator monitor during live play.

Built in Task 10. The strip distinguishes two states, because one is fixed by a
click and the other is not:

| Strip reads | Means | Recovery |
|---|---|---|
| `DISPLAY CLOSED` | The window is gone; the display it was on is still there. | `Reopen Display` — one click, same monitor. |
| `DISPLAY NOT FOUND` | The display itself is gone, or none was ever chosen. | `Reopen Display` opens no window and shows the display panel instead. Only the operator says which screen the board goes to. |

`Reopen Display` stays in the health strip and stays one click, because a dark
wall is not the moment to go looking through a drawer. The panel it falls back
to is **Display… → Available now** (its own drawer since September 6, 2026;
previously **Corrections → Spectator display**, one panel away from
destructive Apply buttons -- see audit item C5 and the closing section of this
document).

### 6.8a Practice with a small spectator preview

- **Advanced → Open test window** opens a bordered, fixed 640×360 (16:9)
  spectator preview beside the operator controls. It is for layout checks and
  home practice, not a substitute for the stadium display.
- It renders the same live snapshot as the spectator board, so score and clock
  changes are useful rehearsal evidence.
- The preview is not fullscreen, is not tied to a selected monitor, and does
  not read or change the saved-display preference. Its close button and any
  rendering failure leave `DISPLAY OPEN`/`DISPLAY CLOSED` health for the real
  production board exactly as it was.

### 6.9 End a game

1. Click `End Game…` in the separated danger area.
2. Review a confirmation showing teams, final score, quarter, and stopped-clock effect.
3. Confirm to stop both clocks, set `FINAL`, persist, and close/flush the event log.
4. Leave the final scoreboard visible until the operator deliberately starts a new game or closes the display.

## 7. Display disconnection and HDMI behavior

Windows may re-enumerate displays after an HDMI disconnect. The application should store a best-effort display identity (name/device identifier plus geometry), detect that the selected display disappeared, and report it. It should not attempt HDMI source switching or interact with the LED processor.

After reconnection, the operator uses `Reopen Display` or selects the returned display. Automatic moves are deferred until ordinary monitor tests show they are predictable.

### How the saved display is recognised (Task 10)

The identity is the Windows device name plus the geometry, stored in
`config.json`. A list position is never used to recognise a display: unplug a
cable and index 1 becomes a different monitor, or the operator's own screen.

Three tiers, most specific first, and the panel says which one happened:

| Tier | What changed | Typical cause |
|---|---|---|
| Exact | Nothing | Normal restart |
| Name | Size, position, or scaling | The processor renegotiated HDMI and came back at a different resolution |
| Geometry | The device name | Windows renumbered the displays after a replug |

There is deliberately no fourth tier. An unmatched preference reports
`DISPLAY NOT FOUND` and opens nothing (D-002).

The host checks the connected displays about every two seconds. That check only
ever *reports*: a display coming back is announced, and reopening onto it stays
an operator action (D-006). Choosing, reopening, losing, and forgetting a
display all advance no revision and write nothing to the game database, so none
of them can disturb a running clock.

### Keyboard input safety (Task 9)

Shortcut Help opens from the toolbar and is generated from the active bindings.
Space reads the displayed running flag; 2/4 load stopped presets, P starts and S
stops the play clock. Q/Shift+Q advances/reverses quarter; ZXCV and NM comma period
add the documented team points; Ctrl+Z undoes; Esc closes the top dialog/drawer.
Editable fields suppress live shortcuts. Confirmation/help blocks live shortcuts;
Cancel is focused, Tab stays inside confirmation, and closing restores focus.
Held shortcut keys and held Enter on a focused button cannot repeat scores.
Mouse and keyboard confirmations preserve the reviewed revision and original
input source. Real numpad and Windows repeat timing require target-laptop rehearsal.

## 8. Accessibility and rehearsal checklist

- Minimum 44×44 CSS-pixel hit targets; clock and preset controls substantially larger. **`Reopen Display` meets this as of September 6, 2026 (audit item C5).** The health strip's `.chip-button` rule (`operator.css`) is `min-height: var(--touch)` (44px), matching the base button rule instead of the 32px concession recorded here through Task 10. The strip is allowed to grow a few pixels rather than the button being squeezed, and at the narrowest supported width the brand text and chip padding shrink first (never the strip wrapping). Measured in the real Chromium engine (Playwright/Edge, headless) against a real bridge-produced view model with `health.display.can_reopen: true`, at both U-001 viewports:

  | Viewport (CSS px) | `#reopen-display` height | `#open-display` height | `documentElement.scrollHeight` vs `clientHeight` | `.clocks button` bottoms | `.health` `scrollWidth` vs `clientWidth` |
  |---|---|---|---|---|---|
  | 1093×614 | 44px | 44px | 614 = 614 (no vertical overflow) | all ≤ viewport height | 1075 ≤ 1075 (no horizontal overflow) |
  | 1180×720 | 44px | 44px | 720 = 720 (no vertical overflow) | all ≤ viewport height | 1162 ≤ 1162 (no horizontal overflow) |

  Clicking the new always-visible `Display…` button opens the Display drawer with the display buttons rendered, at both viewports. This does not replace the recorded HDMI/stadium-hardware verification gap noted elsewhere in this document -- it proves the layout fit and the target size, not the physical display behaviour.
- **The crowd row keeps the no-scrolling measurement (added September 6, 2026, audit item F3).** Adding a whole new always-visible row to a page that already had to earn U-001 is exactly the kind of change that needs measuring rather than assuming, so it was measured in the real Chromium engine (Playwright/Edge, headless) against a bridge-produced view model at its widest: both team names at F-010's 24-character maximum, a nine-entry Undo history behind the `LAST:` strip, and `TIMEOUT` raised with a running countdown.

  | Viewport (CSS px) | `scrollHeight` vs `clientHeight` | `scrollWidth` vs `clientWidth` | `.crowd-bar` overflow | `.crowd-bar button` heights | `#reopen-display` / `#open-display` | Board row |
  |---|---|---|---|---|---|---|
  | 1093×614 | 614 = 614 | 1093 = 1093 | 1075 ≤ 1075 (none) | all 36px | 44px / 44px | 356px |
  | 1180×720 | 720 = 720 | 1180 = 1180 | 1162 ≤ 1162 (none) | all 36px | 44px / 44px | 462px |
  | 1366×768 | 768 = 768 | 1366 = 1366 | 1348 ≤ 1348 (none) | all 36px | 44px / 44px | 510px |

  The new row costs the board its height and nothing else, because `.board` is the only `minmax(0, 1fr)` row in the page grid; every clock button stayed inside the viewport and the page reported no script errors at any of the three. The crowd buttons sit at the quarter bar's 36px floor rather than the 44px floor, which is the same trade the quarter bar's own controls already make — the 44px floor is held for the display-recovery path (C5) and the large scoring and clock controls. Windows 125% scaling remains a manual rehearsal check, as it is for every other row.
- Keyboard focus ring always visible; logical tab order; labels connected to inputs.
- Contrast target of at least WCAG AA for operator text where practical.
- Do not encode home/away or running/stopped solely by red/green.
- Test with a novice operator using only the on-screen labels and a one-page shortcut card.
- During rehearsal, record mis-clicks, hesitations, ambiguous labels, and controls the operator could not find within two seconds.

## 9. Items to revisit after the HDMI test

- Confirm physical canvas resolution, refresh, orientation, scaling, and active-signal mode.
- Photograph/test safe margins, seams, cropping, and color/brightness behavior.
- Rebalance type scale for real viewing distance and pixel pitch.
- Verify fullscreen placement and recovery when the processor input is reselected.
- Decide whether the logical 16:9 canvas is correct or whether a custom aspect-ratio profile is required.

## 10. Presentation layout editor (added September 5, 2026; rebuilt as v2 the same day; pre-game and halftime screens added September 6, 2026)

Implements item 3 of "Owner-requested next scoreboard work," delivered after items 1 and 2 (local time, expanded football fields). See "Phase 2 owner request 3 — presentation layout editor" and "Phase 2 owner request 3 — presentation layout editor v2" in `PROJECT_ROADMAP.md` for full evidence, and `.scratch/layout-editor-v2/spec.md` for the design spec four agents built against. Section 10.9 describes the pre-game and halftime screens added September 6, 2026 against `.scratch/presentation-screens/spec.md`; that work was integrated and verified the same day (focused suites, full discovery run, real pywebview run) — see "Phase 2 owner request 4 — pre-game and halftime screens" in `PROJECT_ROADMAP.md`.

The v1 editor was functionally safe but was numeric-fields-only: no undo, no multi-select, no free text or images, no board background, no fonts, no presets, and no way to rename, duplicate, or delete a stored layout from the UI. v2 turns it into a dense, dark, Figma/Canva-style canvas editor — a real design surface — while keeping every v1 safety property exactly intact.

### 10.1 What it is and is not

The editor still changes only *where and how* the spectator board draws: position, size, color, font, alignment, stacking order, visibility, background, and — new in v2 — free text, images, and simple shapes layered above or below the widgets. It still cannot change *what* any game value says. Every game value a spectator sees is still produced in Python and copied, never computed, by JavaScript; static labels (`GAME CLOCK`, `PLAY CLOCK`) can be moved, resized, restyled, or hidden but never retitled, and a free text element's own wording is operator-typed decorative copy (a sponsor line, an event note) — it is not, and cannot be, bound to a game field (see 10.8). Saving, loading, or editing a layout advances no state revision, submits no `Command`, writes no action-history row, and never touches `scoreboard.db` or its backup — it is a host/presentation concern, exactly like the saved display and the data-folder choice (`docs/ARCHITECTURE.md` §9). The editor's JavaScript has no method named `command`, no `api.command(`, and no method named after any game command; its bridge surface is exactly `get_snapshot`, `layout_state`, `preview_layout`, `clamp_layout`, `reset_widget`, `save_layout`, `select_layout`, `delete_layout`, `rename_layout`, `duplicate_layout`, `reset_layout`.

### 10.2 Opening it

**Advanced ▸ → Presentation layout…** in the operator window opens a separate window at 1220×780, minimum 980×620 — unchanged from v1, because a real canvas editor needs its own preview, layers list, and property panel and does not fit the corrections-drawer pattern used elsewhere. Like the Field Assistant (section 11.2), it opens, closes, and reopens independently of the operator and spectator windows, and closing it affects nothing else. There are deliberately no editing controls on the spectator display itself; it only ever receives a finished layout to render.

### 10.3 Workflow

The window is a toolbar across the top, a layers rail on the left, the canvas in the middle, an inspector on the right, and a status bar along the bottom.

1. Open the editor from Advanced. It loads the active layout and a live read-only snapshot of the current game for its preview.
2. **Toolbar.** The layout name is a menu button listing every stored layout (click to switch) and, below a divider, `Save`, `Save as…`, `Duplicate…`, `Rename…`, `Delete…`, and `Reset to built-in…`. Each of the last five opens a small inline popover with a text field and Confirm/Cancel — there are no browser `alert`/`confirm` dialogs anywhere in the editor. `Default` shows `Rename`/`Delete` disabled with the tooltip "The Default layout is always available," but `Default` **can** be duplicated. Undo/redo icon buttons (`Ctrl+Z`, `Ctrl+Y`/`Ctrl+Shift+Z`) step through the last 100 drafts; a gesture, a nudge, a restack, an add/duplicate/delete, a preset, a clamp, a reset, and every committed property change push one history entry, while a control still being dragged or typed into updates the draft live without spamming history. `+ Text`, `+ Image`, `+ Box` add a free element at the canvas centre and select it; dropping an image file onto the canvas does the same as `+ Image`. A `Presets` menu offers the four built-in starting points (10.4a); choosing one asks to replace the current draft first if it is dirty. Zoom (`50/75/100/150/200%`, `Fit`) scales the canvas without changing anything about the layout itself. `Save` is the one accent-filled primary button, disabled while any validation error is outstanding; `Ctrl+S` saves.
3. **Layers rail.** A `Board` row selects the board itself (its inspector shows background color and safe-area insets — see below). Directly below it, an **Elements** group lists every free text/image/box element the operator has added, most recently stacked first — it comes first so the operator's own additions never scroll out of sight; under it the seventeen game widgets are grouped **Teams**, **Clocks**, **Field**, and **Status** (10.4). `status_message` and `status_clock` preview like every other widget: empty, and so hidden, whenever no crowd status is raised. Each row shows a small type icon, a label (an element shows its text, its image file name, or its id), an eye toggle that hides it without changing the selection, and — for elements — a trash button. A hidden row is dimmed and says so in its tooltip, not just by dimming. Shift+click a row to add it to the selection.
4. **Canvas.** Click a widget or element directly to select it — on the rail or on the canvas — or drag it to move it; drag one of the eight grips on a single selection to resize it. The safe area is a dashed outline labeled at its corner. Snapping to the grid, to other visible items, to the safe area, and to the board edges works exactly as in v1, with a guide line while a snap holds and a small readout chip (`X 24.0% Y 12.0%` or `W 38.0% H 11.8%`) near the pointer while dragging or resizing. Shift+click or a marquee drag over empty canvas selects several items at once; dragging any selected item moves the whole group by one delta, clamped so no member leaves its own boundary (safe area for widgets and text, the canvas itself for images and boxes). Arrow keys nudge the selection one step, Shift+arrow nudges four steps, and `Delete`/`Backspace` removes selected elements (a widget in a mixed selection is left alone — a widget can be hidden but never deleted). `Escape` clears the selection. Right-click opens a small context menu: bring to front/forward, send backward/to back, duplicate and delete (elements), hide/show, and reset (widgets). A hidden item still renders at reduced opacity with a dotted border so it stays selectable.
5. **Inspector.** Its header names the current selection ("Home score", `Text "HOMECOMING"`, "3 items", or "Board"). Sections: *Position & size* (X/Y/W/H as percent, an align/distribute strip, and the four nudge arrows kept from v1); *Layer* (front/forward/backward/back, the numeric stacking order, and the visible checkbox); *Text*, for widgets and text elements (font family, weight, size as a percent of board width, letter spacing, an "Aa/AA" case toggle, a shadow/outline effect control, color, and horizontal/vertical alignment — static widget labels keep the v1 note that their wording is fixed); *Fill & border* (an optional background fill with its own opacity, an optional border with width and corner radius, inner padding for text, and opacity for elements); *Image*, for image elements (a thumbnail, "Replace image…", the fit mode, and a size readout); and *Actions* (`Reset this widget`, `Duplicate`, `Delete`, and `Fit to safe area…` for the whole layout). Selecting `Board` shows the background color, the four safe-area insets as percentages, and a gallery of the built-in presets with an Apply button on each.
6. **Status bar.** The left side reads `✓ No problems` or names the error/warning count; clicking it opens a drawer listing each issue, and clicking an issue selects the affected item. The right side keeps the fixed scope note: "Changes how the board looks. It never changes scores, clocks, or any other game value."
7. Every committed change re-validates the draft against Python and updates the status bar immediately; nothing about *when* Python validates changed from v1 — only the surface for making a change did.

**How a gesture stays safe — unchanged from v1.** A drag produces a pointer event per frame, so the editor — not Python — converts pixels to canvas fractions, snaps them, and holds them inside the applicable boundary. Python still has the last word: every finished gesture calls `preview_layout()`, and `Save` is gated on that answer exactly as it was when the only way to move a widget was to type a number. The same three rules still apply: a hard-boundary drag can never build a layout `Save` then rejects; nothing but a finite, schema-precision number ever reaches the draft, so a collapsed or not-yet-laid-out canvas makes a gesture a no-op instead of writing `NaN`; and a snap only ever shows a guide while it is actually holding.

### 10.3a Keyboard map

| Key | Action |
|---|---|
| Arrow keys | Nudge the selection one step (Shift ×4) |
| `Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z` | Undo / Redo |
| `Ctrl+D` | Duplicate the selection |
| `Delete` / `Backspace` | Remove the selected elements |
| `Escape` | Clear the selection, or close the open menu/popover |
| `Ctrl+S` | Save |
| `Ctrl+A` | Select all visible items |
| `+` / `-` | Zoom in/out (only while focus is not in a field) |

Arrow keys and `Delete` never fire while a text field has focus, so typing a hyphen or a number into a property box cannot nudge or delete the selection.

### 10.4 Widget inventory

Seventeen widgets cover the spectator board, organized in the layers rail into four groups — **Teams** (home/away name and score, possession), **Clocks** (game clock label/value, play clock label/value, quarter), **Field** (down, distance, ball on, home/away timeouts), and **Status** (crowd message, status countdown; added September 6, 2026 with F3). `game_clock_label`, `home_timeouts`, and `away_timeouts` are positionable but ship **hidden by default**, so the default layout keeps drawing exactly the fields today's board draws; the operator turns them on as a deliberate presentation choice.

**What the default changed, and why.** The arrangement, the reading order, and the visual weight are preserved, but the default is a faithful re-expression rather than a pixel copy, in two respects worth recording:

- **Several type sizes are slightly smaller.** The pre-widget board overflowed its own safe area — the browser viewport check failed with `outside safe area: play` at 1280×720, because the down/distance and ball-on lines added by owner request 2 were nested inside the play-clock block and pushed it past the bottom margin. Fitting every widget inside the safe area at all four supported viewports required reducing the score (0.120 → 0.112 of canvas width), game clock (0.100 → 0.093), play clock (0.085 → 0.078), and quarter (0.060 → 0.058) font scales. **This fixes a real defect**; the sizes remain operator-adjustable.
- **Every bold widget uses font weight 700 rather than 800.** That is both scores, both team names, the possession indicator, and the play-clock value. Windows synthesizes weight 800 from Arial with taller metrics (~1.41 em versus ~1.13 em per line), which made a widget's required height depend on its weight. Using one real font weight makes box heights predictable and is visually near-identical.

Both are presentation defaults, not rules: an operator can restore any size through the editor.

| id | Label | What it shows | Default visible |
|---|---|---|---|
| `home_name` | Home team name | The home team's name | Yes |
| `home_score` | Home score | The home team's score | Yes |
| `possession` | Possession | Which team has the ball (`◀ BALL` / `BALL ▶`), blank when neither | Yes |
| `away_name` | Away team name | The away team's name | Yes |
| `away_score` | Away score | The away team's score | Yes |
| `game_clock_label` | Game clock label | The static text `GAME CLOCK` | **No** |
| `game_clock_value` | Game clock | The running/stopped game clock | Yes |
| `quarter` | Quarter | The current quarter/lifecycle label | Yes |
| `down` | Down | The current down (`1st`…`4th`), blank when not set | Yes |
| `distance` | Distance to go | Yards to go, or `Goal`, blank when not set | Yes |
| `play_clock_label` | Play clock label | The static text `PLAY CLOCK` | Yes |
| `play_clock_value` | Play clock | The running/stopped play clock; `—` when cleared | Yes |
| `ball_on` | Ball on | Field position, blank when not set | Yes |
| `home_timeouts` | Home timeouts | Home timeouts remaining, blank when not set | **No** |
| `away_timeouts` | Away timeouts | Away timeouts remaining, blank when not set | **No** |
| `status_message` | Crowd message | The raised crowd status (`FLAG`, `TIMEOUT`, `INJURY`, `DELAY`), blank when none | Yes |
| `status_clock` | Status countdown | The status countdown (`1:00`), blank when cleared | Yes |

**Possession moves from an inline mark beside the home or away team name (owner request 2) to its own widget**, centered between the two names. Its text is still produced in Python; only its placement changed.

### 10.5 Widget rules

- A widget's text is always produced in Python. The editor changes size, position, color, visibility, and stacking order — never wording.
- Static labels (`game_clock_label`, `play_clock_label`) may be styled, moved, resized, or hidden; their text is owned by the application and there is no free-text editor for them.
- A widget whose value can legitimately be absent from a snapshot (`possession`, `down`, `distance`, `ball_on`, `home_timeouts`, `away_timeouts`, `status_message`, `status_clock`) is hidden by the renderer — not drawn as an empty box — whenever its rendered text is blank. Whether the widget is turned on at all is still the operator's choice; the rendering gap for a missing value is automatic and graceful.
- Every widget carries a numeric stacking order so overlap between adjacent widgets (for example a label beside its value) is resolved deterministically rather than by markup order.
- **New in v2**, every widget can additionally carry a font family, letter spacing, an uppercase/normal text-transform, a shadow or outline text effect, a background fill with its own opacity, a border color/width, a corner radius, and inner padding — all optional, all defaulted so the built-in default layout still renders pixel-identical to v1 (same geometry, Arial, no backgrounds, no effects).

### 10.4a Free elements, fonts, and presets (added in v2)

**Free elements.** Alongside the seventeen fixed widget slots, a layout may now hold up to 24 **elements** — `text`, `image`, or `box` — added from the toolbar or the canvas context menu and positioned, resized, restacked, and styled exactly like a widget. An element's `id` is generated (`text_1`, `image_1`, `box_1`, …) and never collides with a widget id. A text element carries its own operator-typed wording (1–120 characters, up to 4 lines) and the full text style set (font, weight, size, spacing, transform, effect, color, alignment); a box is nothing but its background/border/radius, useful as a backdrop panel; an image holds a picture the operator supplies. **Elements never take part in widget-overlap validation** — a panel placed behind the scores is the point, not a defect. A text element must still fit inside the safe area like a widget, but an image or box only has to stay inside the canvas and is allowed to cross the safe area, which is how a full-bleed backdrop or a bottom bar is built.

**Images.** `+ Image` opens a file picker restricted to PNG, JPEG, GIF, and WebP; the file is read locally and embedded in the layout as a `data:` URI — nothing is referenced from disk or a network location. Each image is capped at 2 MB decoded, and every image in a layout together is capped at 6 MB decoded; a file over the limit, or of an unsupported type, is refused inline with a plain message, never a browser alert. Dropping an image file directly onto the canvas does the same thing as the toolbar button. An image element's aspect ratio is preserved when it is added, and its **fit** (contain/cover/fill) is adjustable afterward. SVG is not accepted (10.8) because an SVG file can itself contain a script.

**Fonts.** Ten Windows system fonts are available for any widget or text element — Arial, Arial Black, Impact, Bahnschrift, Segoe UI, Segoe UI Black, Consolas, Georgia, Verdana, and Trebuchet MS — all already installed on Windows, so nothing is downloaded and the board keeps working with no network access.

**Presets.** The `Presets` menu (toolbar) and the presets gallery (Board inspector) offer four complete starting layouts: **Classic** (today's default, unchanged), **Broadcast bar** (a dark rounded bar across the bottom holding both team lines and the game clock, with the top of the board left empty for future media), **Big score** (both scores enlarged across the top half), and **Tigers navy** (a branded look using the project's navy/red palette). Choosing one replaces the current draft — after an inline confirmation if the draft has unsaved changes — but keeps the currently selected layout's *name*, so applying a preset is a starting point to keep editing and save, not an irreversible switch.

**Library management.** The layout-name menu in the toolbar is now a full library manager: **Save**, **Save as…**, **Duplicate…**, **Rename…**, and **Delete…** are all reachable from the UI (v1 could only save and switch; delete existed only on the bridge). Every one of these opens a small inline text-field popover with Confirm/Cancel — there is no browser `prompt`/`confirm` anywhere in the editor. `Default` cannot be renamed or deleted (the control is disabled with an explanatory tooltip) but **can** be duplicated, which is the normal way to start a new layout from the built-in one. Renaming or duplicating to a name already in use is refused with a plain message and changes nothing on disk; renaming the active layout keeps it active under its new name, and duplicating makes the new copy active.

### 10.5a Font and style rules (v2)

- A widget or text element's *wording* is still never editable beyond what 10.5 already says — font, weight, size, spacing, case, color, effect, background, border, and padding are styling, not content.
- Only the ten system fonts in 10.4a are offered; there is no way to load or reference an external font file or web font.
- A text shadow or outline effect is a rendering style, applied identically on the operator's live preview and the real board; it cannot be used to fake a value the board does not actually have.

### 10.6 Safe-area policy

The safe area is a margin inset from all four edges of the logical 16:9 canvas, expressed as a fraction of canvas width/height. It defaults to 4% on every side and is itself an editable, validated property: an operator can widen or narrow it only within a documented minimum and maximum inset, and the four insets together must always leave at least half of the canvas usable on both axes. Every visible widget, and every **text** element, must fit entirely inside the safe area. An **image** or **box** element only has to stay inside the canvas itself and is deliberately allowed to cross the safe area (10.4a). A layout that violates any of this is **rejected outright** with an error naming the widget, the element, or the safe area — it is never silently clamped or accepted (`Fit to safe area…` is an explicit, operator-requested repair, not something `Save` does on its own).

### 10.7 A bad layout

Validation is strict: a value out of range, an unrecognized color format, a widget or text element that would sit outside its boundary, an image that fails to decode or exceeds a size cap, or a serious overlap between two visible widgets is an error, and the layout as a whole is rejected rather than partially applied. A stored layout that fails to load — corrupted, an unrecognized schema version, or otherwise invalid — falls back to the last known valid layout, and if none exists, to the built-in default. A malformed `layouts.json` never prevents the scoreboard from launching.

**A layout saved by v1 (schema version 1) still opens.** It is accepted, every new v2 property is filled in from its default, and the editor shows one warning — "This layout was saved by an earlier version and was upgraded; save it to keep the upgrade." — rather than an error; nothing is rejected just because it predates elements, fonts, or a background color.

**To reset a bad layout:** use **Reset to built-in…** in the editor's layout-name menu, or close the application, delete `layouts.json` from the Scoreboard data folder (the same per-user `%LOCALAPPDATA%\Scoreboard` folder documented in `docs/ARCHITECTURE.md` §9 and `docs/PACKAGING.md`, or the operator-chosen folder if one was set — see "Where the game is saved" below), and relaunch. The scoreboard rebuilds the built-in default layout automatically either way.

### 10.8 What v2 still does not support

- OBS, media playback, animations, sponsor rotation, or video.
- Networking or cloud storage of a layout; every layout, including its embedded images, is a local file.
- Physical controllers.
- Binding a text element's wording to a game field, or any other way to make free text a computed value — a text element's content is fixed operator-typed copy (10.1, 10.4a).
- SVG images — an SVG file can contain a script, which offline, unreviewed image handling should not have to defend against; only PNG/JPEG/GIF/WebP are accepted.
- A font that is not already installed on Windows; nothing is downloaded (10.4a).
- A different hand-tuned layout per screen resolution.
- Editing the operator panel's own layout.
- A fourth screen — end of game, timeouts, or any other lifecycle moment beyond Game, Pre-game, and Halftime — is not added; the schema leaves room for one (`SCREEN_IDS`) but nothing beyond the three current screens is built.

### 10.9 Pre-game and halftime screens (added September 6, 2026)

**The pregame/halftime event countdown board described in 10.8 of earlier revisions of this document is no longer a fixed, uneditable presentation.** As of schema v3, one stored layout describes three screens — Game, Pre-game, and Halftime — and the editor covers all three. The pregame and halftime screens keep their own widget set (10.9a) because they show different information than the game screen, but they are otherwise edited the same way: drag, resize, restyle, restack, add free elements, and apply a preset, all validated by Python before `Save`.

**Screen switcher.** A segmented control in the toolbar, immediately after the layout-name menu and the dirty dot, reads `Game` / `Pre-game` / `Halftime` (one button per screen, the current one shown selected). `Ctrl+1`, `Ctrl+2`, and `Ctrl+3` switch to Game, Pre-game, and Halftime respectively, the same way the numbered zoom shortcuts already work elsewhere in the toolbar. Switching screens clears the current selection, swaps the canvas and layers rail to that screen's widgets and elements, and re-validates against Python; nothing about the draft on the screen being left is discarded — a pending edit on Game is exactly as it was when Pre-game or Halftime is reopened.

#### 10.9a Event widget inventory

The pregame and halftime screens are built from a different widget set than the seventeen game widget slots in 10.4 — eight **event widgets**, grouped **Teams** and **Countdown**:

| id | Label | What it shows |
|---|---|---|
| `home_name` | Home team name | The home team's name |
| `home_score` | Home score | The home team's score |
| `away_name` | Away team name | The away team's name |
| `away_score` | Away score | The away team's score |
| `event_phase` | Phase label | The current countdown phase (for example `HALFTIME` / `WARMUP`) |
| `event_title` | Countdown title | The countdown's title (for example `KICKOFF IN`, `UNTIL SECOND HALF`) |
| `event_clock` | Countdown | The countdown's formatted remaining time |
| `warmup` | Warmup line | `Warmup follows: 3:00`, shown only while the halftime countdown is above the warmup threshold; blank (and hidden by the renderer, not drawn as an empty box) once warmup begins or during pregame |

Every value is still produced in Python and only copied by JavaScript, on exactly the rule stated in 10.1 and 10.5. `event_phase` and `warmup` default to hidden on the pregame screen (there is no phase label or warmup line before kickoff) and visible on halftime; `home_name`, `home_score`, `away_name`, `away_score`, and `event_title`/`event_clock` default to visible on both. Turning a widget on or off, or restyling it, is a per-screen choice — hiding `event_phase` on Halftime does not touch Pre-game, and vice versa.

#### 10.9b Per-screen presets

The `Presets` menu and the Board inspector's presets gallery show a different gallery depending on which screen is selected:

- **Game screen presets** are the same four described in 10.4a (Classic, Broadcast bar, Big score, Tigers navy) and, as of this change, apply **only** to the game screen — choosing one replaces the current draft's top-level `safe_area`, `background`, `widgets`, and `elements` exactly as before, and no longer touches the Pre-game or Halftime screens of the same layout.
- **Pre-game screen presets:** Classic (today's default arrangement), Matchup (both team names enlarged facing each other with a `VS` mark between them, the countdown centered below), Broadcast bar (a dark bar across the bottom holding names, scores, and the countdown, leaving the upper board empty for future media), and Tigers navy (the project's navy/red branded look).
- **Halftime screen presets:** Classic (today's default arrangement), Score first (both scores enlarged beside each name with the phase label and countdown below), Broadcast bar (the same bottom-bar treatment as pre-game, with the phase label and warmup line at its ends), and Tigers navy.

Applying a screen preset replaces only that screen's mini-document (`safe_area`, `background`, `widgets`, `elements`) inside the draft; the layout's name, its other two screens, are kept. The same dirty-draft inline confirmation, history entry, and re-render that already govern the game-screen presets (10.4a) apply here.

#### 10.9c Validation and storage

A validation issue now names the screen it belongs to: a game-screen issue reads exactly as it did before this change (for example "Countdown must sit inside the safe area."), while a pre-game or halftime issue is prefixed with its screen's label (for example "Halftime: Countdown must sit inside the safe area."). The status-bar issue count and the issues drawer cover all three screens at once; selecting an issue from a screen other than the one showing switches to it first. Everything in 10.6 and 10.7 — the safe-area boundary, strict rejection of an out-of-bounds widget or element, and the "never silently clamped" rule — applies independently to each screen.

**One stored layout, three screens.** `layouts.json` still holds one library of named layouts; each layout is one document that now carries the game screen at its top level (unchanged shape, so every existing layout keeps opening) plus a `screens.pregame` and `screens.halftime` mini-document. Saving, duplicating, renaming, or deleting a layout always acts on the whole three-screen document — there is no way to save or share a single screen independently of the layout it belongs to. See `docs/ARCHITECTURE.md` §9 for the on-disk schema.

### 10.10 Tigers Stadium preset (September 7, 2026)

The owner-requested stadium redesign adds a fifth **Tigers Stadium** preset
to each of the Game, Pre-game, and Halftime galleries. Game uses oversized
white scores on red/blue team panels, a large central game clock, a separate
play-clock readout, gold possession and crowd status, and a bottom strip for
down, distance, and field position. Pregame and halftime use a large central
countdown with both names and scores below; halftime retains its phase and
warmup line. All three share a navy background and a subdued three-slash
header motif. The game-clock label is visible in this preset; timeouts remain
hidden. Existing running-clock colours and cleared/expired values still apply.

To use the complete design, open **Advanced → Presentation layout…**, choose
**Presets → Tigers Stadium → Apply** on **Game**, then repeat on **Pre-game**
and **Halftime**, and use **Save as…** to name the layout **Tigers Stadium**.
The existing inline replacement confirmation applies to a dirty draft.
Each Apply affects only the selected screen; Save stores all three together.
Existing layouts and the built-in Default are not replaced by installing the
update. The preset uses fixed design colours, not saved-team colour bindings.

Everything is an ordinary editable widget, text element, or box in schema v3.
No downloaded asset, special renderer, new dependency, animation, or game-state
mutation is introduced. The automated browser matrix checks all three screens
at five viewports, maximum-length names and three-digit scores, plus clock,
status, warmup, editor save/reopen, and cutscene restoration. Stadium viewing
distance, brightness, HDMI geometry, and target-laptop evidence remain open.

## 11. Field Assistant window (added September 5, 2026)

Implements the owner-requested end-of-play helper documented in
[`FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`](FIELD_ASSISTANT_RULES_AND_WORKFLOW.md)
and the "Field Assistant" evidence in `PROJECT_ROADMAP.md`.

### 11.1 What it is and is not

A separate, optional, similarly sized helper window — not a replacement for
the operator's manual Field Status drawer (section 5a) and not a second
authoritative process. Python remains the sole state owner; the helper only
requests a validated `finalize_field_action`. It is opened deliberately,
never automatically, and closing it changes nothing about the game.

### 11.2 Opening it

**Field Assistant** on the operator toolbar opens a separate `pywebview`
window, 1180×720 with a minimum size of 1024×600. Reopening while one is
already open destroys the previous helper window first. A helper push
failure destroys only the helper; operator shutdown closes it along with the
other owned windows; reopening reads the latest snapshot.

### 11.3 Layout

- A prominent draft ball-spot readout sits above the field drawing, visually
  distinct from the current authoritative field status shown alongside it.
- The field shows a clickable, draggable ball, plus on-screen 1-yard nudge
  buttons and arrow-key support for fine adjustment.
- Line to gain and direction are shown with text labels, not color alone.
- Controls for the active workflow (series start, normal play/incomplete,
  penalty, or a scoring/kickoff transition) appear below the field.
- Pressing a play/transition action asks Python for a preview immediately; the
  proposed result becomes the single large Confirm button's label. The old
  separate **Preview result** step no longer exists. There is no
  drag-distance-implies-confirm behavior.
- **Re-sync** and **Discard draft** are always available.
- No clock controls appear in the helper window; finalizing an action never
  starts, stops, resets, or otherwise changes either clock.

### 11.4 Stale-draft protection

If the authoritative revision changes while a draft is open — a manual
field-status edit, a score, or any other accepted command — the helper shows
the banner `FIELD STATUS CHANGED ELSEWHERE — RE-SYNC REQUIRED` and disables
Confirm until the operator re-syncs (rebuilds the draft from the current
snapshot) or discards it.

### 11.5 Target layout, not yet visually verified

- [ ] 1366×768 at 100% and 125% Windows scaling, without page scrolling
  during ordinary finalization — not yet checked on a physical target display.
- [x] Native pywebview/WebView2 rendering and the press-by-press helper flow on
  the development host; this is not target-laptop evidence.
- [ ] A live operator rehearsal of the workflows above.

### 11.6 Deliberately manual

OT direction, onside/blocked kicks, defensive try returns, offsetting/multiple
penalties, enforcement from a spot other than the one proposed, automatic
possession flips, any clock change, live ball tracking, networking, OBS, LED,
and physical controllers all remain outside the helper; the existing Field
Status drawer and score/quarter controls (sections 5a, 5) are the fallback for
anything the helper does not cover.

## 12. Cutscenes window (added September 6, 2026)

Implements the owner's "cutscenes" request: press a button in a small
persistent window and the LED wall plays a branded animation, then returns
to exactly what it was showing. Built against `.scratch/cutscenes/spec.md`,
for the September 6, 2026 redesign `.scratch/cutscenes-v2/spec.md`, and for
the two scenes added the same day (v3) `.scratch/cutscenes-v3/spec.md`.

### 12.1 What it is and is not

A cutscene is a manually-triggered 5–10 second interruption of the spectator
board: a claw-strike intro rips across whatever is currently on screen (for
the events that have one), the board morphs into the built-in **Broadcast
bar** layout (score and clock along the bottom), a FIRST DOWN, TOUCHDOWN,
TURNOVER, FLAG ON THE PLAY, or MAKE SOME NOISE scene plays on the freed-up
upper stage, and the board morphs back to exactly what it was showing
before — same layout, same screen (game, pre-game, or halftime). The five
events, their durations, and their sublines:

| Event (`event`) | Headline | Subline | Duration | Intro | Whose |
|---|---|---|---|---|---|
| `first_down` | FIRST DOWN | TIGERS | 7 s | claw strike | home |
| `touchdown` | TOUCHDOWN | TIGERS | 10 s | claw strike | home |
| `turnover` | TURNOVER | TIGERS BALL | 7 s | claw strike | home |
| `penalty` | FLAG ON THE PLAY | PENALTY | 7 s | none | nobody |
| `make_some_noise` | MAKE SOME NOISE | TIGERS FANS | 5 s | none | home |

The two v3 additions: **TURNOVER** (the Tigers take the ball away — the
defensive counterpart of the touchdown, and it earns the claw) and **MAKE
SOME NOISE** (a 5 s crowd prompt with a live level meter; it has no intro
because a 1.6 s claw would eat a third of it and a crowd prompt wants to be
on the wall *now*).
It is a host/presentation concern, exactly like the presentation layout and
the saved teams: triggering, cancelling, selecting a pack, and rescanning the
packs folder advance no state revision, submit no `Command`, and write
nothing to `scoreboard.db` or its backup. It is **not** automatic — nothing
in this feature fires from a score, a down, or any other game event; the
operator always presses a button or a key. It is **not** an editor: there is
no way to change what a scene draws from inside the app, only which pack
plays for each event. The operator window and the Cutscenes window never show
the animation itself, only a Python-computed status badge and countdown; only
the spectator (and the practice test window) plays it.

**Cutscenes are the home team's, and there is no home/away choice anywhere.**
The wall is the Tigers' wall, so a first down, a touchdown, a turnover, and
the crowd prompt always celebrate the home team whoever has possession, and
a penalty is nobody's —
it only says a flag is down, in penalty yellow rather than either team's
colours. Which side a cutscene is for is a property of the event
(`EVENT_TEAM` in `presentation/cutscenes.py`), not something an operator can
get wrong under pressure: the window has no team toggle, the hotkeys name no
side, and `trigger_cutscene(event)` takes no team argument. The touchdown
scene also shows **no score** — the Broadcast bar underneath is already
showing it, and it keeps updating throughout.

The school name inside every branded cutscene is fixed as **TIGERS**. It is
not copied from the configurable home-team name, so a fresh scoreboard that
still says `HOME` — or a game whose host name was changed — cannot alter the
school-branded scene copy. The subline is a per-event template
(`EVENT_SUBLINE` in `presentation/cutscenes.py`): first down and touchdown
read **TIGERS**, Turnover reads **TIGERS BALL**, Make Some Noise reads
**TIGERS FANS**, and the team-neutral penalty remains **PENALTY**.

### 12.2 Opening it

**Cutscenes** on the operator toolbar, right after **Field Assistant**,
opens a separate, persistent `pywebview` window — the same ownership
pattern as the Field Assistant helper (section 11.2): it opens, closes, and
reopens independently of the operator and spectator windows, reopening
while one is already open replaces the previous window, and closing it
changes nothing about the game or a cutscene already playing. It is meant
to sit beside the operator window for the whole game, since a volunteer
reaches for it at every scoring play.

### 12.3 Layout and keys

The Cutscenes window (`views/cutscenes/`) is a small, dark, high-contrast
panel built for a volunteer under time pressure:

- A header reading `CUTSCENES`, a status line (`Ready`, or
  `PLAYING: TOUCHDOWN · 6.2s` with Python's own countdown), and an
  always-visible **CANCEL** button, disabled only while nothing is playing.
- Five large full-width trigger buttons, in this order: **FIRST DOWN**
  (blue), **TOUCHDOWN** (red), **TURNOVER** (navy with a red edge),
  **PENALTY** (flag yellow on ink, deliberately neither team's colour), and
  **MAKE SOME NOISE** (light blue with a gold edge). Pressing one calls the
  same small bridge the window's own keys use and shows Python's
  plain-language result. There is no team row and no side to pick: the
  event decides (section 12.1). All five, plus the collapsed Packs summary
  below them, fit the window's `520x640` default (and its `420x520`
  minimum) without scrolling — measured in headless Edge at both sizes
  with the buttons at their 64 px floor and 22 px face; at 520×640 each
  button is 92 px tall and the Packs summary ends 12 px above the bottom
  edge.
- A collapsible **Packs** section: one pack picker per event (built-in
  first), **Rescan** (no restart needed after adding or editing a pack
  folder), **Open folder**, and a list of any pack problems found on the
  last scan.

Keyboard, in both the operator window and the Cutscenes window: `D` plays
First down, `T` plays Touchdown, `O` plays Turnover, `F` plays the Penalty
flag, `L` ("get Loud") plays Make some noise, and `Shift+C` cancels
whatever is playing. One key per event, with no side to name. These
are letter keys rather than function keys because F-keys are browser
accelerators inside WebView2 and would not reach the page reliably. They
appear in the operator's Shortcut Help table alongside every other binding.
The operator toolbar also carries a `CUTSCENE: TOUCHDOWN 6.2s`-style badge,
in the existing health strip rather than a new fixed row, so triggering a
cutscene from the main screen is visible without opening the Cutscenes
window at all.

### 12.4 What the wall shows

One JSON *program*, built once in Python per trigger, drives the entire
sequence; the spectator page only interprets it against its own clock. All
times below are relative to the moment the program is applied:

| When | What happens |
|---|---|
| t = 0 | The stage covers the full canvas; the 1.6 s claw-strike intro plays over whatever board is currently showing. A **penalty** has no intro at all (its pack's `intro` defaults to `none`, since the claws are Tigers-branded and a flag is nobody's), and neither does **make some noise** (at 5 s the claw would eat a third of it), so those two scenes mount immediately with the bar already up. |
| ≈ 45% of the intro | The board morphs into the Broadcast bar layout under a 600 ms transition, underneath the still-playing intro. |
| End of the intro | The intro unmounts; the stage shrinks to the upper ~70% of the canvas (above the bar's status row); the main scene — FIRST DOWN, TOUCHDOWN, TURNOVER, FLAG ON THE PLAY, or MAKE SOME NOISE, built-in or a dropped-in video/image — mounts. |
| Duration − outro (600 ms, or 300 ms on a cancel) | The stage fades. |
| Full duration | The scene unmounts, the stage hides, the board morphs back to the operator's own layout, and the window is idle again. |
| Duration + 1.5 s | A safety net: if the host somehow never sent the "end" signal, the spectator page ends the cutscene itself. The board always comes back, even if the host process were to vanish mid-cutscene. |

The bar's clock and score keep updating the whole time — a cutscene never
pauses the authoritative game. Triggering a second cutscene while one is
already playing replaces it immediately rather than queuing; the Cancel
button/hotkey ends one early and restores the board at once.

### 12.5 Packs and the manifest

Cutscenes ship with five code-authored built-in animations (one per event),
so the feature works with no files dropped in at all. To replace one, an
operator or volunteer creates a folder under the `cutscenes` folder inside
the Scoreboard data directory (**Open folder** in the Packs section goes
straight there) containing a `manifest.json`:

```json
{
  "schema_version": 1,
  "name": "Touchdown — roar",
  "event": "touchdown",
  "duration_seconds": 10,
  "intro": "claw_scratch",
  "scene": {"type": "video", "src": "touchdown.webm", "fit": "cover", "loop": false}
}
```

The folder name becomes the pack's id. `event` is `first_down`, `touchdown`,
`turnover`, `penalty`, or `make_some_noise`; `duration_seconds` is optional
(2–30 seconds, clamped rather than rejected if out of range, defaulting per
event if left out: 7, 10, 7, 7, and 5); `intro` is optional (`claw_scratch`
or `none`) and, left out, defaults **per event** — the claw strike for a
first down, touchdown, or turnover, none for a penalty or make some noise;
`scene` is required and is either a built-in animation
(`{"type": "builtin", "id": "first_down"}`, `"touchdown"`, `"turnover"`,
`"penalty"`, or `"make_some_noise"`)
or a media file sitting right beside the manifest
(`video`: `.webm`/`.mp4`; `image`: `.png`/`.gif`/`.jpg`/`.jpeg`/`.webp`/
`.apng`; `fit` is `cover` or `contain`). A media file must be named
directly — no subfolders, no `..` — and must actually be present in the
folder. A manifest with a real problem (an unknown event, a media file that
is not there, a bad schema version) causes the whole pack to be skipped,
with a plain-language reason shown in the Packs section's issues list; nothing
here can crash a trigger or take down the game. Restart is never needed
after adding or editing a pack folder — press **Rescan**. A `README.txt`
explaining all of this is written into the `cutscenes` folder automatically
the first time it is created.

### 12.6 Not yet visually verified on the LED wall

The six built-in scenes (`claw_scratch`, `first_down`, `touchdown`,
`turnover`, `penalty`, `make_some_noise`) are code-authored DOM/CSS/SVG,
redesigned in the v2 pass — and, for the two v3 additions, drawn as
siblings of that pass — against a modern broadcast reference: TMSA colours,
the TMSA crest (`views/spectator/cutscenes/tmsa-logo.png`, shown by the
Tigers scenes and the crowd prompt alike), and no score on the touchdown.
Sound is out of scope (video plays muted), and nothing auto-fires a cutscene
from a score, a down, or any other game event — every trigger is a
deliberate operator action. The feature has been verified against a stub
bridge in a browser and, separately, in the real pywebview/WebView2 runtime
on the development host (see `PROJECT_ROADMAP.md`, "Cutscenes — delivered
for rehearsal" and the v2 and v3 entries that follow it); it has not yet
been seen playing on the physical LED wall.

## Where the game is saved, and which display it is on

**Updated September 6, 2026 (audit item C5).** Which display the spectator
board goes on moved out of the corrections drawer and into its own **Display**
drawer (`#display-drawer`, opened by the always-visible `Display…` button in
the health strip, or by `Reopen Display` itself when there is no display left
to reopen onto). It carries a status row mirroring the health strip
(`DISPLAY OPEN`/`DISPLAY CLOSED`/`DISPLAY NOT FOUND`, the detail text, and a
second `Reopen Display` button), the saved-display summary with **Forget
saved display**, and the list of displays Windows is currently reporting. The
health-strip's one-click `Reopen Display` is unaffected: it still recovers a
closed display without opening anything, per section 6.8. This was the
"revisit" that section 8 previously deferred: the display-recovery path was
the hardest thing on screen to hit -- `Reopen Display` was 32px against the
44px floor, one panel away from destructive corrections. Both problems are
fixed together because they were the same layout problem: the health strip
had no room for a 44px button, and the drawer holding the fallback had no
separation from Corrections.

The corrections drawer keeps one row that is not a game correction: **Saved
to**, showing the current data folder with **Choose folder…** and **Use
standard folder**. It stays there -- it is still the revisit noted below, not
resolved by this pass. It lives there rather than on the board for a layout
reason and a safety reason: the drawer overlays the page and scrolls inside
itself, so adding to it cannot push a live control off a 1366x768 screen and
does not invalidate the U-001 measurement, and a control that changes where a
game is written does not belong beside the scoring buttons.

The placement is the least-bad option available today, not a considered
information architecture: the drawer is titled CORRECTIONS, and this is not a
correction. If the operator layout is ever revisited, an explicit Settings
surface is the better home for it, alongside the Display drawer this pass
already gave its own home. Raised here so it is reviewed with the rest of the
layout rather than settling by default.

The row states that the running game keeps saving where it is and that a new
folder applies at the next start. That sentence is the whole safety story for
this control and must not be dropped in a redesign.
