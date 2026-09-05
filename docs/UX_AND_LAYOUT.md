# Operator Workflow and Initial Layouts

**Status:** Phase 1 wireframe baseline; visual design is not implemented
**Last updated:** September 4, 2026

## 1. Design intent

The first operator may be a student or volunteer working under time pressure. The interface therefore favors large explicit controls, visible state, reversible ordinary actions, and deliberate dangerous actions. It does not try to resemble a television production console.

The operator and spectator surfaces are separate windows backed by the same authoritative state. The operator sees controls and health information; spectators never do.

Phase 2 is operated from one laptop by the primary operator. A second person is anticipated to operate a future peripheral, but that peripheral remains outside the MVP; its absence cannot block the laptop workflow.

## 2. Control hierarchy

| Frequency/risk | Controls | Treatment |
|---|---|---|
| Constant, time-critical | Game Start/Stop; play-clock 25/40; score `+1/+2/+3/+6` | Large, always visible, one action, keyboard-accessible |
| Frequent | Quarter next; Undo | Visible on main screen; confirmation if clocks are running |
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
│                 1st                         PLAY 40                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

Visual priorities are scores first, game clock second, team names third, then quarter and play clock. The exact proportions, safe area, font, and color contrast must be tested on a normal monitor and revisited after the stadium HDMI test identifies the real canvas and viewing conditions.

### Responsive strategy

- Render inside a logical 16:9 design canvas, centered within any physical viewport.
- Scale through CSS variables, viewport units, `clamp()`, and grid/flex layout rather than fixed pixels.
- Letterbox or pillarbox deliberately when aspect ratios differ; never stretch text.
- Keep a configurable safe-area inset, provisionally 4% on all sides.
- Use local system fonts (Arial/sans-serif) with tabular numerals and white-on-black contrast; no font download.
- Test at 1280×720, 1366×768, 1920×1080, and one portrait/narrow mode before stadium dimensions are known.
- After the HDMI test, add the confirmed resolution/refresh/overscan mode to the test matrix rather than hard-coding a new layout.

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
│ QUARTER  [ ◀ ]   1st   [ ▶ ]    LAST: Away +6 (7)       [ UNDO ]            │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Corrections ▸ ] [ Pregame / Settings ▸ ] [ Reopen Display ]               │
│                                              [ End Game… ] [ New Game… ]     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Main-screen rules

- Do not require scrolling for live controls at 1366×768 and 100%/125% scaling.
- Keep team controls spatially mirrored but use explicit HOME/AWAY names on every correction.
- Use separate Start and Stop buttons. Disable or visually de-emphasize the action that is already true.
- Show running/stopped text next to each clock; do not rely on button color.
- Show the last reversible action and Undo without opening a menu.
- A display-health failure must take over the health strip but must not obscure clocks or controls.

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

## 6. Workflows

### 6.1 Pregame setup

1. Launch the application once; both windows open.
2. If recoverable state exists, choose `Resume recovered game` or `Start new game`. Recovered clocks are stopped.
3. Select the spectator display from the settings panel and enter fullscreen.
4. Enter home and away names; verify the confirmed 12:00 quarter length and the selected clock-display preference.
5. Verify 0–0, `PRE`, stopped game clock, stopped play clock, `DISPLAY OPEN`, and `STATE SAVED` on the operator view.
6. Visually confirm the spectator display and run a short score/clock rehearsal, then restore the starting state through `New Game`.

### 6.1a Pregame, halftime, and warmup presentation

- Quarter selection controls presentation: PRE shows the event countdown, HALF shows the interval, and playing quarters show the game board. Starting the game clock leaves pregame/interval presentation. Entering PRE/HALF loads its stopped preset only when switching countdown kind; an already selected countdown retains its value. No extra lifecycle control is required.
- Before kickoff, the spectator display shows a labeled `KICKOFF IN` 30:00 countdown. This is separate from the stopped 12:00 game clock.
- At halftime, the spectator display shows one `UNTIL SECOND HALF` 15:00 countdown. While more than 3:00 remains it labels the current phase `HALFTIME` and visibly states `Warmup follows: 3:00`.
- At 3:00, the same countdown continues without a reset and its current-phase label changes to `WARMUP`.
- These countdowns are operator-controlled, use the same reliable timing model as game clocks, and do not start, stop, or reset the game or play clock.
- Each event countdown provides Start, Stop, Reset, and `Edit Current Time`. Editing opens a confirmation with a `Start after applying?` radio choice; `Remain stopped` is selected by default.

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
- The game clock is unchanged.
- The play clock uses the same upward presentation rule and changes to tenths only once its rounded tenths value is below `5.0`; it stays at `5` until it can display `4.9`.
- This is the stadium's only play-clock display, so the active value must remain prominent and display recovery must preserve it.
- When the game clock transitions from stopped to running, the play clock is stopped and its spectator area becomes blank. Starting an already-running game clock does not affect it; it may then count to zero unless an operator clears or changes it.
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
- If either clock is running, the application warns that both will stop; cancel is safe.
- On confirmation, stop both clocks and change the quarter plus its matching lifecycle/presentation. Do not automatically reset either clock until official behavior is confirmed.

### 6.7 Recover after application restart/crash

1. Relaunch from the normal shortcut/executable.
2. The recovery screen states when the snapshot was saved and whether the primary or backup was used.
3. Choose Resume to restore names, scores, quarter, and last clock values with both clocks stopped.
4. Compare the restored state with the game situation, make logged corrections if needed, then deliberately restart clocks.
5. If recovery is unavailable/corrupt, keep the vendor system available and use a new game only after confirming the correct live state.

### 6.8 Recover after spectator display closes

- Operator controls and clocks continue.
- The health strip changes to `DISPLAY CLOSED` and exposes `Reopen Display`.
- Reopen creates the view using current authoritative state, on the saved display if available.
- If the saved display is absent, show an explicit display selector; do not silently steal the operator monitor during live play.

### 6.9 End a game

1. Click `End Game…` in the separated danger area.
2. Review a confirmation showing teams, final score, quarter, and stopped-clock effect.
3. Confirm to stop both clocks, set `FINAL`, persist, and close/flush the event log.
4. Leave the final scoreboard visible until the operator deliberately starts a new game or closes the display.

## 7. Display disconnection and HDMI behavior

Windows may re-enumerate displays after an HDMI disconnect. The application should store a best-effort display identity (name/device identifier plus geometry), detect that the selected display disappeared, and report it. It should not attempt HDMI source switching or interact with the LED processor.

After reconnection, the operator uses `Reopen Display` or selects the returned display. Automatic moves are deferred until ordinary monitor tests show they are predictable.

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

- Minimum 44×44 CSS-pixel hit targets; clock and preset controls substantially larger.
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

## Where the game is saved

The corrections drawer carries one row that is not a game correction: **Saved to**, showing the current data folder with **Choose folder…** and **Use standard folder**.

It lives there rather than on the board for a layout reason and a safety reason. The drawer overlays the page and scrolls inside itself, so adding to it cannot push a live control off a 1366x768 screen and does not invalidate the U-001 measurement. And a control that changes where a game is written does not belong beside the scoring buttons.

The placement is the least-bad option available today, not a considered information architecture: the drawer is titled CORRECTIONS, and this is not a correction. If the operator layout is ever revisited, an explicit Settings surface is the better home. Raised here so it is reviewed with the rest of the layout rather than settling by default.

The row states that the running game keeps saving where it is and that a new folder applies at the next start. That sentence is the whole safety story for this control and must not be dropped in a redesign.
