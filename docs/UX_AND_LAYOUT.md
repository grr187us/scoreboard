# Operator Workflow and Initial Layouts

**Status:** Phase 1 wireframe baseline; visual design is not implemented
**Last updated:** September 5, 2026 (added the field-status readout, the Field status drawer, the recovery screen's local-time display, and the presentation layout editor; rebuilt the editor as the v2 canvas editor described in section 10)

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
│            1st Quarter                   PLAY CLOCK 40                         │
│                                                                              │
│         3rd & 7            ◀ EAGLES            HOME 35                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

The bottom row was added on September 5, 2026 with the football-state fields (F-060 to F-066). Its four widgets — `down`, `distance`, `possession`, and `ball_on` — are *optional*: the renderer hides a widget whose value is absent from the snapshot rather than drawing an empty box, so a board with no possession set simply omits that indicator. Three of the fifteen widgets default to hidden entirely — the `GAME CLOCK` label and the two timeout counters — because they are a layout choice rather than a required field (D-001); the editor can turn them on. There is no local-time widget on the spectator board: P-010's Eastern-time formatting is for recovery and history timestamps in the operator and startup surfaces.

Visual priorities are scores first, game clock second, team names third, then quarter and play clock. The exact proportions, safe area, font, and color contrast must be tested on a normal monitor and revisited after the stadium HDMI test identifies the real canvas and viewing conditions.

### Responsive strategy

- Render inside a logical 16:9 design canvas, centered within any physical viewport.
- Scale through CSS variables, viewport units, `clamp()`, and grid/flex layout rather than fixed pixels.
- Letterbox or pillarbox deliberately when aspect ratios differ; never stretch text.
- Keep a configurable safe-area inset, provisionally 4% on all sides.
- Use local system fonts (Arial/sans-serif) with tabular numerals and white-on-black contrast; no font download.
- Test at 1280×720, 1366×768, 1920×1080, and one portrait/narrow mode before stadium dimensions are known.
- After the HDMI test, add the confirmed resolution/refresh/overscan mode to the test matrix rather than hard-coding a new layout.

**Widget-rendered board (added September 5, 2026).** The board above is now drawn from fifteen individually positioned, sized, and colored widgets (`views/shared/board.js`) rather than a fixed CSS grid, so the arrangement shown here is the *built-in default* layout, not a hard-coded one — see section 10 for the editor that changes it. The pregame/halftime event-countdown presentation (`KICKOFF IN…` / `UNTIL SECOND HALF…`) keeps its own separate markup and CSS — since the September 5 deep-dive audit it also carries both team names and the score beneath the countdown, so the wall is never scoreless during an intermission — and is **not** covered by the editor in v1 (section 10.8).

## 4. Operator-screen wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SCOREBOARD CONTROL   GAME: 1st 12:00 STOPPED   PLAY: 40 STOPPED              │
│ Display: OPEN ✓   State: SAVED ✓   Rev 184                 [Shortcut Help]   │
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
│ QUARTER [◀] 1st [▶]  3rd & 7 · EAGLES 35 · TO 3/2   LAST: Away +6 (7) [UNDO] │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Corrections ▸ ] [ Halftime ▸ ] [ Field ▸ ] [ Field Assistant ]             │
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
- Show the last reversible action and Undo without opening a menu.
- A display-health failure must take over the health strip but must not obscure clocks or controls.
- Down/distance, field position, and timeouts remaining (added September 5,
  2026) read compactly in the quarter bar, next to the existing quarter
  control rather than as a new row, so the U-001 no-scrolling measurement is
  unaffected. Possession is a short text flag (`◀ BALL` / `BALL ▶`) next to the
  team name it belongs to, not color alone (U-002's principle applied to a new
  field). See section 5a for the controls that set these.

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

### 6.2 Start and stop the game clock

- Click the large Start or Stop button, or press `Space` outside any text field.
- The authoritative state changes once, the status text changes immediately, and the action is logged.
- Start while running and Stop while stopped are harmless no-ops.
- A stalled UI repaint does not affect the authoritative elapsed-time calculation.
- The display never understates time remaining: whole seconds are rounded up at normal precision, and tenths are rounded up below one minute. `1:00` remains visible until the rounded tenths value can display `59.9`.
- `Edit Current Time` stops the game clock if needed, validates the entered minutes/seconds, and then offers `Start after applying?`; `Remain stopped` is selected by default.

### 6.3 Reset play clock to 25 or 40

- Click `25 LOAD` / `40 LOAD`, or press the mapped key.
- The requested value loads while stopped; use the separate play-clock Start command when the official signals ready for play.
- Click the visibly distinct `25 + START` / `40 + START` controls to load that preset and begin its countdown in one atomic action. The plain load controls remain available for a stopped setup.
- The game clock is unchanged.
- The play clock uses the same upward presentation rule and changes to tenths only once its rounded tenths value is below `5.0`; it stays at `5` until it can display `4.9`.
- This is the stadium's only play-clock display, so the active value must remain prominent and display recovery must preserve it.
- In `1st`–`4th`/`OT`, Game Clock start/stop coupling clears the play clock as documented. In PRE, Start/Stop/expiry control only the kickoff countdown.
- No clock expiration produces an alarm. A play clock that reaches `0.0` while the game clock is already running remains visible there until the operator uses the deliberate clear control or issues another play-clock command.
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
to is **Corrections → Spectator display**.

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

- Minimum 44×44 CSS-pixel hit targets; clock and preset controls substantially larger. **`Reopen Display` does not meet this.** It is 32 px tall, raised from 28 px in Task 10, which is the most the health strip can hold without pushing a live control off a 1366×768 screen. Reaching 44 px needs the operator layout re-flowed, not a taller strip, so it belongs with the Settings-surface revisit below.
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

## 10. Presentation layout editor (added September 5, 2026; rebuilt as v2 the same day)

Implements item 3 of "Owner-requested next scoreboard work," delivered after items 1 and 2 (local time, expanded football fields). See "Phase 2 owner request 3 — presentation layout editor" and "Phase 2 owner request 3 — presentation layout editor v2" in `PROJECT_ROADMAP.md` for full evidence, and `.scratch/layout-editor-v2/spec.md` for the design spec four agents built against.

The v1 editor was functionally safe but was numeric-fields-only: no undo, no multi-select, no free text or images, no board background, no fonts, no presets, and no way to rename, duplicate, or delete a stored layout from the UI. v2 turns it into a dense, dark, Figma/Canva-style canvas editor — a real design surface — while keeping every v1 safety property exactly intact.

### 10.1 What it is and is not

The editor still changes only *where and how* the spectator board draws: position, size, color, font, alignment, stacking order, visibility, background, and — new in v2 — free text, images, and simple shapes layered above or below the widgets. It still cannot change *what* any game value says. Every game value a spectator sees is still produced in Python and copied, never computed, by JavaScript; static labels (`GAME CLOCK`, `PLAY CLOCK`) can be moved, resized, restyled, or hidden but never retitled, and a free text element's own wording is operator-typed decorative copy (a sponsor line, an event note) — it is not, and cannot be, bound to a game field (see 10.8). Saving, loading, or editing a layout advances no state revision, submits no `Command`, writes no action-history row, and never touches `scoreboard.db` or its backup — it is a host/presentation concern, exactly like the saved display and the data-folder choice (`docs/ARCHITECTURE.md` §9). The editor's JavaScript has no method named `command`, no `api.command(`, and no method named after any game command; its bridge surface is exactly `get_snapshot`, `layout_state`, `preview_layout`, `clamp_layout`, `reset_widget`, `save_layout`, `select_layout`, `delete_layout`, `rename_layout`, `duplicate_layout`, `reset_layout`.

### 10.2 Opening it

**Advanced ▸ → Presentation layout…** in the operator window opens a separate window at 1220×780, minimum 980×620 — unchanged from v1, because a real canvas editor needs its own preview, layers list, and property panel and does not fit the corrections-drawer pattern used elsewhere. Like the Field Assistant (section 11.2), it opens, closes, and reopens independently of the operator and spectator windows, and closing it affects nothing else. There are deliberately no editing controls on the spectator display itself; it only ever receives a finished layout to render.

### 10.3 Workflow

The window is a toolbar across the top, a layers rail on the left, the canvas in the middle, an inspector on the right, and a status bar along the bottom.

1. Open the editor from Advanced. It loads the active layout and a live read-only snapshot of the current game for its preview.
2. **Toolbar.** The layout name is a menu button listing every stored layout (click to switch) and, below a divider, `Save`, `Save as…`, `Duplicate…`, `Rename…`, `Delete…`, and `Reset to built-in…`. Each of the last five opens a small inline popover with a text field and Confirm/Cancel — there are no browser `alert`/`confirm` dialogs anywhere in the editor. `Default` shows `Rename`/`Delete` disabled with the tooltip "The Default layout is always available," but `Default` **can** be duplicated. Undo/redo icon buttons (`Ctrl+Z`, `Ctrl+Y`/`Ctrl+Shift+Z`) step through the last 100 drafts; a gesture, a nudge, a restack, an add/duplicate/delete, a preset, a clamp, a reset, and every committed property change push one history entry, while a control still being dragged or typed into updates the draft live without spamming history. `+ Text`, `+ Image`, `+ Box` add a free element at the canvas centre and select it; dropping an image file onto the canvas does the same as `+ Image`. A `Presets` menu offers the four built-in starting points (10.4a); choosing one asks to replace the current draft first if it is dirty. Zoom (`50/75/100/150/200%`, `Fit`) scales the canvas without changing anything about the layout itself. `Save` is the one accent-filled primary button, disabled while any validation error is outstanding; `Ctrl+S` saves.
3. **Layers rail.** A `Board` row selects the board itself (its inspector shows background color and safe-area insets — see below). Directly below it, an **Elements** group lists every free text/image/box element the operator has added, most recently stacked first — it comes first so the operator's own additions never scroll out of sight; under it the fifteen widgets are grouped **Teams**, **Clocks**, and **Field** (10.4). Each row shows a small type icon, a label (an element shows its text, its image file name, or its id), an eye toggle that hides it without changing the selection, and — for elements — a trash button. A hidden row is dimmed and says so in its tooltip, not just by dimming. Shift+click a row to add it to the selection.
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

Fifteen widgets cover the spectator board, organized in the layers rail into three groups — **Teams** (home/away name and score, possession), **Clocks** (game clock label/value, play clock label/value, quarter), and **Field** (down, distance, ball on, home/away timeouts). `game_clock_label`, `home_timeouts`, and `away_timeouts` are positionable but ship **hidden by default**, so the default layout keeps drawing exactly the fields today's board draws; the operator turns them on as a deliberate presentation choice.

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

**Possession moves from an inline mark beside the home or away team name (owner request 2) to its own widget**, centered between the two names. Its text is still produced in Python; only its placement changed.

### 10.5 Widget rules

- A widget's text is always produced in Python. The editor changes size, position, color, visibility, and stacking order — never wording.
- Static labels (`game_clock_label`, `play_clock_label`) may be styled, moved, resized, or hidden; their text is owned by the application and there is no free-text editor for them.
- A widget whose value can legitimately be absent from a snapshot (`possession`, `down`, `distance`, `ball_on`, `home_timeouts`, `away_timeouts`) is hidden by the renderer — not drawn as an empty box — whenever its rendered text is blank. Whether the widget is turned on at all is still the operator's choice; the rendering gap for a missing value is automatic and graceful.
- Every widget carries a numeric stacking order so overlap between adjacent widgets (for example a label beside its value) is resolved deterministically rather than by markup order.
- **New in v2**, every widget can additionally carry a font family, letter spacing, an uppercase/normal text-transform, a shadow or outline text effect, a background fill with its own opacity, a border color/width, a corner radius, and inner padding — all optional, all defaulted so the built-in default layout still renders pixel-identical to v1 (same geometry, Arial, no backgrounds, no effects).

### 10.4a Free elements, fonts, and presets (added in v2)

**Free elements.** Alongside the fifteen fixed widgets, a layout may now hold up to 24 **elements** — `text`, `image`, or `box` — added from the toolbar or the canvas context menu and positioned, resized, restacked, and styled exactly like a widget. An element's `id` is generated (`text_1`, `image_1`, `box_1`, …) and never collides with a widget id. A text element carries its own operator-typed wording (1–120 characters, up to 4 lines) and the full text style set (font, weight, size, spacing, transform, effect, color, alignment); a box is nothing but its background/border/radius, useful as a backdrop panel; an image holds a picture the operator supplies. **Elements never take part in widget-overlap validation** — a panel placed behind the scores is the point, not a defect. A text element must still fit inside the safe area like a widget, but an image or box only has to stay inside the canvas and is allowed to cross the safe area, which is how a full-bleed backdrop or a bottom bar is built.

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
- The pregame/halftime **event countdown board** (the `KICKOFF IN…` / `UNTIL SECOND HALF…` presentation) is **not editable in v2**. It keeps its existing markup and CSS untouched; only the in-game widgetized board is covered by the editor.

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
- One **Preview** step calculates the proposed result; a single, large
  **Confirm Play** / **Confirm Transition** button finalizes it. There is no
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
  during ordinary finalization — not yet checked on a physical display or
  under WebView2; only a static browser render has been observed on this
  development host.
- [ ] Native WebView2 rendering of the helper window.
- [ ] A live operator rehearsal of the workflows above.

### 11.6 Deliberately manual

OT direction, onside/blocked kicks, defensive try returns, offsetting/multiple
penalties, enforcement from a spot other than the one proposed, automatic
possession flips, any clock change, live ball tracking, networking, OBS, LED,
and physical controllers all remain outside the helper; the existing Field
Status drawer and score/quarter controls (sections 5a, 5) are the fallback for
anything the helper does not cover.

## Where the game is saved, and which display it is on

The corrections drawer carries two rows that are not game corrections: **Spectator display**, listing the displays Windows is reporting with the saved one named, and **Saved to**, showing the current data folder with **Choose folder…** and **Use standard folder**.

It lives there rather than on the board for a layout reason and a safety reason. The drawer overlays the page and scrolls inside itself, so adding to it cannot push a live control off a 1366x768 screen and does not invalidate the U-001 measurement. And a control that changes where a game is written does not belong beside the scoring buttons.

The placement is the least-bad option available today, not a considered information architecture: the drawer is titled CORRECTIONS, and neither of these is a correction. Task 10 put the display panel in the same place for the same reason and made the problem twice as large; that is an argument for the revisit, not for the drawer. If the operator layout is ever revisited, an explicit Settings surface is the better home for both, along with the 44 px `Reopen Display` target noted in section 8. Raised here so it is reviewed with the rest of the layout rather than settling by default.

The row states that the running game keeps saving where it is and that a new folder applies at the next start. That sentence is the whole safety story for this control and must not be dropped in a redesign.
