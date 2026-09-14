# Post-Live Fixes Backlog

> **Document purpose:** Everything learned from the first official game run on the app (September 2026), turned into ordered, actionable tickets. Each ticket names the file and line where the current behaviour lives, the fix, and the evidence needed before it can be called done. Update `PROJECT_ROADMAP.md` when a ticket's status changes.

**Status:** 6 tickets open, 2 resolved. Owner decisions recorded September 14, 2026.
**Last updated:** September 14, 2026
**Source:** Owner debrief after the first live game. Overall verdict was "pretty good experience"; the items below are what went wrong.

## Priority key

| Priority | Meaning |
|---|---|
| **P0** | Broke the game-day workflow or made the button box unusable. Fix first. |
| **P1** | Put wrong or missing information on the board, or forced a workaround every drive. |
| **P2** | Friction; a real fix but nothing was shown wrong on the board. |

## Suggested order of attack

1. **PL-8** owner action items (drop in the flashed sketch) so PL-1 can be tested against the real mapping.
2. **PL-1** global button-box hook. Biggest single failure; also removes one cause of PL-8's rocker desync.
3. **PL-2** field assistant live sync. Second biggest failure; also the most likely explanation for PL-6.
4. **PL-3** quick +/- adjustments.
5. **PL-6** touchdown flow verification and control-panel coupling.
6. **PL-4** hide clocks on FINAL, **PL-5** end-of-4th prompt.
7. **PL-7** swap drive direction.
8. **PL-8** firmware and mapping audit, bench test, soak test.

## Rebuild reminder (after every ticket)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\build_package.py
```

Then refresh `dist\Scoreboard-0.1.0.zip` (the September 8 build forgot this once), append a dated "Latest local build" paragraph to `PACKAGING.md`, and record the evidence in `PROJECT_ROADMAP.md`. Suite baseline before this backlog: 1136 tests, 0 failures, 0 errors, 3 expected A-1 skips.

## Owner action items

- [ ] **Copy the sketch that is actually flashed on the Pro Micro into `hardware/scoreboard_button_box/`.** The committed `scoreboard_button_box.ino` predates commits `f5d3ad6` and `e5dec11`; it has no F21/F22 and maps D4-D9 differently from the app. Until the real sketch is in git, nobody can audit the mapping. If it was never reflashed after the remap, say so; that alone explains wrong-button behaviour.
- [ ] **Confirm the rocker wiring.** Which pin the rocker is on, and whether it is a maintained (latching) switch or momentary. PL-8 assumes maintained.
- [ ] **Note anything else you remember about the box misbehaving** (which button, which screen was up, whether you were holding it) as a dated comment under PL-8.

---

## PL-1 — Button box works on every screen (issue 2)

**Priority:** P0 · **Status:** open · **Type:** defect

**Symptom:** The game clock rocker and play clock buttons only work while the scoreboard control panel is the selected window. With Cutscenes, Field Assistant, or any other screen up, nothing on the box does anything.

**Root cause / current behaviour:**

- Every screen is its own top-level OS window created by `webview.create_window` in `src/scoreboard/host/app.py` (startup `:655`, operator `:679`, spectator `:897`, layout `:1047`, field assistant `:1082`, cutscenes `:1125`). There are no tabs or iframes.
- The F15-F22 bindings live in a page-level `document` keydown listener in `src/scoreboard/views/operator/keyboard.js` (table `:4-55`, listener `:64`), loaded only by `views/operator/index.html:657` and installed by `views/operator/operator.js:1268-1309`. The file calls itself a "Focused-window input adapter" and that is exactly what it is.
- The Pro Micro is a plain USB keyboard. Windows delivers its keystrokes to whichever window has focus, so any other window swallows them. None of the other pages bind F-keys (`cutscenes.js:149`, `field_assistant.js:392`, `spectator.js:188`, `layout.js:1253`).
- Aggravating: Cutscenes opens with `on_top=True` (`app.py:1132`) and nothing ever hands focus back to the operator window.
- No Python or OS-level hook exists anywhere (`pynput`, `keyboard`, `RegisterHotKey`, `GetAsyncKeyState` all absent from `src/`, `tools/`, `pyproject.toml`).

**Fix (owner decision: global OS-level hook):**

- New module `src/scoreboard/host/hotkeys.py`. A daemon thread registers F15-F22 with Win32 `RegisterHotKey` via `ctypes` (VK codes 0x7E-0x85, modifier `MOD_NOREPEAT` 0x4000 so a held key fires once) and runs a `GetMessage` loop. On `WM_HOTKEY` it dispatches the same command the page would have sent (F15 quick 25, F16 quick 40, F17 load 40, F18 load 25, F19 clear, F20 play clock start, F21 game clock start, F22 game clock stop) through the bridge with `source: 'button-box'`. No new dependency; the stadium laptop is offline.
- Start the hook in `app.py` once the operator window exists; unregister the keys on shutdown. If registration fails because another program owns a key, log it and fall back to the existing page listener.
- Decide and test the dedupe: `RegisterHotKey` swallows the keystroke so the operator page never sees it, meaning the F15-F22 rows can be removed from `keyboard.js` (leaving the laptop-keyboard letter bindings). Prove there is no double fire with the operator window focused.
- Either drop `on_top=True` on the cutscenes window or re-focus the operator window after opening it. Not strictly needed once the hook exists, but it stops the cutscene window from trapping the mouse workflow.

**Components/files:** `src/scoreboard/host/hotkeys.py` (new), `src/scoreboard/host/app.py`, `src/scoreboard/host/bridge.py` (source tag), `src/scoreboard/views/operator/keyboard.js`, `tests/ui/keyboard.cjs:81-88`, `tests/ui/test_keyboard_browser.py` (31-binding assertion).

**Dependencies:** PL-8 owner action items for the real mapping. The command names are already stable.

**Verification:**

- Unit test the dispatch table with a fake `user32` (no real hotkey registration in the suite).
- Integration test that the hook's key-to-command table equals the F-key rows of `keyboard.js` (or that those rows are gone and the hook is the single source).
- Real pywebview run: open Field Assistant, focus it, press every box button and flip the rocker both ways; repeat with Cutscenes focused, Layout editor focused, and with Notepad focused. Record which window was focused for each press.
- Double-fire check: operator window focused, press each button, confirm one history entry per press.

**Acceptance criteria:**

- Every box button and both rocker positions work regardless of which app window, or which other program, has focus.
- No command fires twice when the operator window is focused.
- Hook start and stop are logged; a failed registration produces an operator-visible warning, not a silent fallback.
- Existing keyboard browser suite passes with its binding count deliberately updated, not loosened.

---

## PL-2 — Field assistant refreshes on its own (issue 5)

**Priority:** P0 · **Status:** resolved (September 14, 2026) · **Type:** defect

**Symptom:** Any change made on the control panel forced a manual "Reload from scoreboard" on the field assistant. The owner "had to refresh the field assistant ALLLLL the time."

**Root cause / current behaviour:**

- The assistant already receives live pushes. `src/scoreboard/host/publisher.py:59` delivers to operator, spectator, then field assistant; `host/app.py:450-499` fans out at `REFRESH_INTERVAL_SECONDS = 0.1` (`app.py:108`) plus after every accepted command (`bridge.py:1106-1107`, `:1199-1200`). The page subscribes via `window.applyView = render` (`views/field_assistant/field_assistant.js:502`).
- The page then rejects what it receives. `render()` ends with `if (model.revision !== baseRevision) markStale();` (`field_assistant.js:321`). `baseRevision` is captured on first snapshot and only reset by `clearDraft()` or a committed action (`:326`, `:483`). Every control-panel command bumps `GameState.revision` (`domain/state.py:414-428`), so the very next push shows the red "FIELD STATUS CHANGED ELSEWHERE, RE-SYNC REQUIRED" banner (`index.html:20`) and disables Confirm (`:324`). The same revision gate is repeated in the preview path (`:338`) and the confirm path (`:471`), and a server-side `STALE_REVISION` rejection also calls `markStale()` (`:480`). All four must change together.
- The draft ball is deliberately not re-seeded by pushes: `pendingReseed` is only set on open, on Re-sync, and after a commit (`:37-43`, `:307-317`, `:476`). That amendment is recorded in `FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`.
- Clock ticks do not bump revision (`service.py:322-338`), so this only fires on real commands, but every field edit, score, timeout, and quarter change is a real command.

**Fix (owner decision: live-sync, keep my ball spot, Confirm never disabled):**

- On every `applyView`, adopt `model.revision` as `baseRevision` and re-render. Remove the revision-drift call to `markStale()`; Confirm stays enabled.
- Re-seed the draft ball from the live state on each push unless the operator has moved the ball since the last push. Track a `ballTouched` flag set by drag, click, arrow keys, and the nudge buttons (`:384-401`), cleared on commit and on manual Reload.
- Keep `finalize_field_action(committed, baseRevision)` (`:473`, `bridge.py:1153`). The service already rejects a true conflict; on rejection show a short toast, re-seed, and let the operator confirm again instead of blocking.
- Keep the Reload button as an explicit "discard my draft" only. Rename or re-label it accordingly.
- Update the amendment in `FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` that introduced the stale gate.

**Components/files:** `src/scoreboard/views/field_assistant/field_assistant.js`, `index.html`, `field_assistant.css` (banner becomes a toast), `docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`, `tests/integration/test_field_assistant_window.py`, `tests/integration/test_field_assistant_rehearsal.py`.

**Dependencies:** None. Ship before PL-6 so the touchdown verification is not confused by the stale gate.

**Verification:**

- Real runtime: open the assistant, change the down on the control panel, watch the assistant update within a push interval with Confirm enabled. Drag the ball, then add a score on the control panel; the dragged ball must stay put and the score must update.
- Real runtime conflict: change ball-on on the control panel while a preview is pending, press Confirm, confirm the toast and re-seed path.
- Integration tests for both paths; rehearsal test extended with an interleaved control-panel command.

**Acceptance criteria:**

- No manual reload is needed at any point in a rehearsal game.
- Confirm is never disabled because of a change made elsewhere.
- An in-progress ball spot survives unrelated changes; an untouched ball follows the board.
- A genuine conflict is surfaced without blocking and resolves in one extra tap.

**Resolution (September 14, 2026):** `field_assistant.js` adopts `model.revision` on every push and response; `markStale` and all four revision gates are gone, and a pending press is re-previewed (without disabling Confirm) when the revision changes. The draft ball follows the board until touched (`ballTouched` set by pointerdown, arrow keys and nudges via `nudgeScreen`, and the typed yard line; cleared by an accepted commit, a refused `STALE_REVISION` race, and the button now labelled **Discard draft & reload**). A refused race shows a five-second `#conflict` toast, re-seeds, re-previews, and completes on the next Confirm. The stale banner and its CSS are replaced by the toast. Verified: source-contract tests in `tests/integration/test_field_assistant_window.py` (4 rewritten), `LiveSyncRehearsalTests` plus an interleaved `set_down` in the multi-quarter rehearsal in `tests/integration/test_field_assistant_rehearsal.py`, and a real pywebview run (`.scratch/post-live-fixes/realrun_pl2.py`, 27/27) with both windows open: control-panel 3rd down adopted within a push with Confirm sampled every 50 ms and never disabled, a nudged ball unmoved by a control-panel +6, an untouched ball following a control-panel Ball On change, and an injected race refused once, toasted, and committed on the second Confirm. Screenshots: `.scratch/post-live-fixes/evidence/pl2-0{1,2,3}-*.png`.

---

## PL-3 — Quick +/- adjustments for down, yards to go, and ball on (issue 1)

**Priority:** P1 · **Status:** resolved (September 14, 2026) · **Type:** feature

**Symptom:** Small corrections (one down, a few yards, ball moved a yard) are constant in a real game and the control panel only offers presets and typed inputs.

**Current behaviour:** Field Status drawer at `src/scoreboard/views/operator/index.html:470-512`: down is four presets plus Clear (`:477-483`), distance is a number input plus Set/Goal/Clear (`:485-493`), ball on is a side toggle plus a number input plus Set (`:502-512`). The main-screen strip at `:158-161` is read-only. Timeouts, by contrast, already have `+1` buttons (`:514-530`). The only field-position nudges in the app are on the assistant (`field_assistant/index.html:31-34`).

**Fix (owner decision: main-screen strip and the drawer, no new hotkeys):**

- Add compact `-`/`+` buttons next to Down, To Go, and Ball On on the main strip, and the same beside the existing controls in the drawer.
- Down: step 1..4 and clamp. Distance: step 1..99; Goal stays Goal until Set. Ball on: `-1`/`+1` and `-5`/`+5`, crossing the 50 by flipping `BallSpot.team`, clamping at 0 (goal line).
- Reuse the existing commands `set_down`, `set_distance`, `set_ball_on` (`src/scoreboard/domain/commands.py:544-562`). Add one pure helper, `nudge_ball_spot(spot, yards)`, in the domain layer so the arithmetic is tested once and mirrors the assistant's nudge math (`field_assistant.js:384-401`).
- Buttons must be at least 44 px tall to match the existing touch target rule.

**Components/files:** `src/scoreboard/views/operator/index.html`, `operator.js`, `operator.css`, `src/scoreboard/domain/state.py` or `domain/football.py` (helper), `tests/unit/test_state.py`, `tests/integration/test_operator_refresh_ui.py`.

**Dependencies:** None.

**Verification:** Unit tests for the helper across the 50 and at both goal lines; operator refresh UI test for the new buttons; real-run screenshot of the strip and drawer at 1366x768.

**Acceptance criteria:**

- Each of the six adjustments is one tap from the main screen.
- Ball on crosses the 50 correctly in both directions and never goes past a goal line.
- Every nudge appears in the action history and is undoable like any other command.

**Resolution (September 14, 2026):** The quarter-bar strip now carries `−`/`+` beside Down and To Go and `−5 −1 / +1 +5` beside Ball On (eight 44 px buttons), and the Field Status drawer repeats them beside its existing controls. Each button sends the existing `set_down` / `set_distance` / `set_ball_on` command with only a `nudge` step; `ScoreboardBridge._resolve_nudge` turns the step into the explicit value under the command lock using the new pure helpers `nudge_down` and `nudge_distance` (`domain/state.py`) and `nudge_ball_spot` (`domain/field_assistant.py`, reusing the assistant's absolute-axis conversions: `+` is toward the AWAY goal line, `−` toward the HOME goal line, flipping sides across the 50 and stopping at 0). The history row is therefore an ordinary `set_*` command and Undo reverses it as usual. A nudge that would change nothing (already 4th, on the goal line), a blank distance, or Goal is refused with a sentence the operator sees; Goal stays Goal until Set. Verified: helper unit tests across the 50 and at both goal lines (`tests/unit/test_state.py`), bridge translation/refusal/undo tests (`tests/integration/test_bridge.py::NudgeTests`), source-contract tests for the strip, drawer, and touch floor (`tests/integration/test_operator_refresh_ui.py`), the keyboard browser suite's U-001 overflow check at both viewports, and a real pywebview run (`.scratch/post-live-fixes/realrun_pl3.py`, 22/22) at a 1366×768 and a 1093×614 CSS viewport: one tap each from the strip, cross-50 in both directions, four history rows, Undo, the Goal refusal, no overflow, all 16 buttons measured at 44 px. Screenshots: `.scratch/post-live-fixes/evidence/pl3-01-strip-1366.png`, `pl3-02-field-drawer-1366.png`, `pl3-03-strip-1093.png`.

---

## PL-4 — Hide the clocks on FINAL (issue 3)

**Priority:** P1 · **Status:** open · **Type:** defect

**Symptom:** After switching to FINAL the board still showed a clock value (12:00 or whatever was loaded).

**Root cause / current behaviour:** There is no lifecycle conditional in the display path. `spectator_view_model` in `src/scoreboard/host/bridge.py:618-715` always formats `clocks.game.display` (`:661-674`). The widget binding is `presentation/layout.py:284-286` and `views/shared/board.js:79-80`. `board.js:3135-3178` hides a widget only when it is in `OPTIONAL_WIDGET_IDS` and its text is empty (`:3171`, `refreshHidden` `:2415-2419`), and `game_clock_value` is not optional (`presentation/layout.py:327-337`). The only lifecycle branch is `screenForLifecycle` (`board.js:3180-3189`), which sends FINAL to the game board.

**Fix (owner decision: hide game clock and play clock, values and labels):**

- In `spectator_view_model`, return `""` for the game clock display, play clock display, and their labels when `state.quarter == "FINAL"` or lifecycle is FINAL.
- Add `game_clock_value`, `game_clock_label`, `play_clock_value`, `play_clock_label` to `OPTIONAL_WIDGET_IDS` so the existing `hasValue` path hides them. The list exists twice and must match: `presentation/layout.py:327-337` and `views/shared/board.js:123`.
- Check every preset (Game boards, Grid, Tigers Stadium, Fifty Yard Line) for a background box or hairline that looks wrong with the clock gone; adjust the preset if needed.
- Quarter widget keeps showing FINAL; scores stay.

**Components/files:** `src/scoreboard/host/bridge.py`, `src/scoreboard/presentation/layout.py`, preset layout files, `tests/integration/test_spectator.py`, `tests/ui/test_spectator_browser.py`.

**Dependencies:** None.

**Verification:** Unit test on the view model for FINAL vs 4th; browser test case; real-run screenshot of FINAL on each preset using the layout editor recipe.

**Acceptance criteria:**

- On FINAL, no clock digits or clock labels are visible on any preset.
- Leaving FINAL (quarter back) restores the clocks.
- Operator control panel still shows the clocks so the operator can see what would come back.

---

## PL-5 — End of 4th: ask Final or Overtime (issue 4)

**Priority:** P1 · **Status:** open · **Type:** feature

**Symptom:** When the 4th quarter ended, the app gave no guidance; the operator had to know to step the quarter forward or press End Game.

**Current behaviour:** Game clock expiry only stops the clocks and clears the play clock (`src/scoreboard/application/service.py:340-399` `observe_tick`; bridge handling `bridge.py:1696-1727`). The quarter never changes on its own. Quarter stepping is a plain index walk over `("PRE","1st","2nd","HALF","3rd","4th","OT","FINAL")` (`domain/state.py:105-114`, `service.py:883-892`) and every step asks for confirmation (`:903-909`). End Game (`views/operator/index.html:563`, `service.py:1025-1041`) sets lifecycle FINAL without changing the quarter label. OT is one label using `GameRules.overtime_seconds` (`domain/rules.py:86-90`, `period_seconds()` `:130-146`).

**Fix (owner decision: prompt when the Q4 clock hits 0:00):**

- When `observe_tick` sees the game clock reach zero and the quarter is 4th (or OT), set a `pending_period_decision` field in the view model.
- The operator page shows a modal with three choices: **Final** (`set_quarter FINAL` plus end game), **Overtime** (`set_quarter OT`, loads `overtime_seconds`), **Keep 4th** (dismiss; for an untimed down or a clock correction).
- Re-arm the prompt if the clock is restarted and expires again. Dismissing does not consume it permanently.
- Multiple OT periods are out of scope for this ticket; note it as a follow-up if the owner wants OT2.

**Components/files:** `src/scoreboard/application/service.py`, `src/scoreboard/host/bridge.py`, `src/scoreboard/views/operator/index.html`, `operator.js`, `tests/unit/test_game_clock.py`, `tests/integration/test_bridge.py`, `tests/integration/test_operator_refresh_ui.py`.

**Dependencies:** PL-4 so choosing Final immediately blanks the clocks.

**Verification:** Unit test that the flag appears only for 4th/OT expiry; operator browser test for the modal and each button; real-run drive the clock to 0:00 in the 4th and take each branch.

**Acceptance criteria:**

- The prompt appears on the control panel at 0:00 in the 4th without any other action.
- Final produces the FINAL board with hidden clocks; Overtime loads the configured OT length; Keep 4th leaves the state untouched.
- The prompt does not appear on expiry in the 1st, 2nd, or 3rd.

---

## PL-6 — Touchdown clears field status, adds 6, then offers the try (issue 6)

**Priority:** P1 · **Status:** open · **Type:** verify, then feature

**Symptom (owner's words):** Tapping Touchdown on the field assistant should clear the down and yards to go, add 6 points, and move straight to a screen offering PAT kick (1), 2-point conversion (2), or no good (0). The penalty option must remain available on that screen. Owner is not sure exactly what happened during the game.

**Current behaviour:** The rules already do most of this. `preview_touchdown` (`src/scoreboard/domain/field_assistant.py:418-430`) yields +6 with `ball_on`, `possession`, `down`, `distance` all cleared; the commit writes everything in one revision (`service.py:1506-1525`). After a confirmed TD the page auto-opens the score panel on the TRY block for the scoring team (`field_assistant.js:485-492`), with NO GOOD / KICK +1 / 2-POINT +2 (`index.html:147-158`, `preview_try` `field_assistant.py:436`). The most likely game-day explanation is PL-2: the red stale banner had disabled Confirm, so the tap looked dead. The control panel's own +6 buttons (`views/operator/index.html:59-62`, `:118-121`) have no coupling to field status at all, by design (`:473-474`).

**Fix:**

1. **Verify first, in the real app, after PL-2 lands.** Record a TD from the assistant with the board visible and confirm: score +6, down/distance/ball-on widgets blank on the board and on the operator strip, TRY panel opens for the right team, PENALTY button still reachable from that panel, try commit follows with "Set up the kickoff."
2. If step 1 reveals a gap (for example the TRY panel does not expose Penalty, or the operator strip keeps showing 1st & 10), fix it there.
3. **Control-panel coupling.** Make the operator +6 buttons also clear down, distance, and ball on, and show a "try pending" hint on the strip. Default: clear only, no modal on the control panel; the assistant is where the try is chosen. Confirm this default with the owner during implementation.

**Components/files:** `src/scoreboard/views/field_assistant/` (verify), `src/scoreboard/views/operator/index.html`, `operator.js`, `src/scoreboard/application/service.py` (score handler), `tests/integration/test_field_assistant_rehearsal.py`, `tests/unit/test_commands.py`.

**Dependencies:** PL-2.

**Verification:** Real-run TD and try from the assistant with screenshots of both windows and the board; rehearsal test extended with TD, try, kickoff; unit test for the control-panel +6 clearing.

**Acceptance criteria:**

- One tap on Touchdown plus Confirm yields +6, blank down/distance/ball on, and the try screen.
- Penalty is reachable from the try screen.
- A +6 on the control panel also blanks the field status and hints that a try is pending.

---

## PL-7 — Swap which direction each team drives (issue 7)

**Priority:** P2 · **Status:** open · **Type:** feature

**Symptom:** If the direction was picked wrong at kickoff there is no way to correct it for the rest of the game.

**Current behaviour:** Direction is one persisted integer, `GameState.assistant_first_quarter_home_direction` (`src/scoreboard/domain/state.py:313`, validated `:204-211`), written by the first committed assistant action (`service.py:1510-1522`). It only decides which screen side the HOME goal is drawn on per quarter (`home_goal_side()` `domain/field_assistant.py:109-131`, exposed at `bridge.py:824-838`). The direction panel is shown only until it is saved (`field_assistant.js:88-92`, `:194-198`) and the click handler ignores presses after that (`:415-416`). Only Undo or New Game can change it.

**Fix:**

- Add a command `set_assistant_direction(+1 | -1)` (`domain/commands.py`, handler in `service.py`) so the flip is its own undoable history entry.
- Add a "Swap sides" button in the assistant's field strip, visible whenever a direction is saved, with a one-tap confirm. Remove the early return at `field_assistant.js:415-416`.
- Ball spot and line to gain are absolute yard lines, so they do not move; only the end-zone labels mirror.
- Optionally expose the same control in the operator Field Status drawer.

**Components/files:** `src/scoreboard/domain/commands.py`, `src/scoreboard/application/service.py`, `src/scoreboard/host/bridge.py`, `src/scoreboard/views/field_assistant/index.html`, `field_assistant.js`, `tests/unit/test_field_assistant.py`, `tests/unit/test_commands.py`.

**Dependencies:** PL-2 (the assistant must pick up the flip without a reload).

**Verification:** Unit test that the flip mirrors `home_goal_side` in every quarter; real-run flip in the 2nd quarter and confirm the labels mirror and the ball stays on the same yard line.

**Acceptance criteria:**

- Direction can be swapped at any time from the assistant.
- The swap is in the action history and undoable.
- Nothing about the ball, line to gain, down, or distance changes when swapping.

---

## PL-8 — Button box mapping and firmware audit (issue 8)

**Priority:** P0 · **Status:** open (blocked on owner action items) · **Type:** investigation

**Symptom (owner's words):** Something is off in the hotkey mapping or the Pro Micro program. Seen during the game: a button did the wrong thing, the rocker got out of sync with the clock, and holding or double-pressing caused a problem.

**Current behaviour and findings:**

- **Stale sketch.** `hardware/scoreboard_button_box/scoreboard_button_box.ino` was last changed in commit `449adc8`, before the remaps in `f5d3ad6` and `e5dec11`. It defines only F13-F20 (`:35-42`), has no rocker pin, and its D4-D9 mapping (`:53-61`, `:73-80`) disagrees with the app's `keyboard.js:10-23` on every button. If the box was flashed from this file, Quick 25 / Quick 40 / load / clear / start are all crossed and the game clock rocker does nothing. The header refers to a wiring guide that does not exist in the repo.
- **Rocker edge behaviour.** The firmware fires only on the closing edge (`:150-161`) and sends a 20 ms tap (`KEY_HOLD_MS`, `:89`, `:139-142`). A maintained rocker that is already ON when the app starts, or that is flipped while another window has focus (PL-1), sends nothing the app acts on, so the physical switch position and the clock state diverge with no resync path. The app side is correct for a rocker: F21/F22 are absolute start/stop, not toggles (`keyboard.js:22-23`), and the domain ignores redundant starts and stops (`domain/clocks.py:211-212`, `:233-234`; `service.py:1060-1076`).
- **Hold and repeat.** Firmware is press-edge only with a 25 ms debounce (`:88`) and never auto-repeats. The page drops `event.repeat` and duplicate keydowns via a `held` set (`keyboard.js:63-88`) and clears it on window blur (`:109`). On paper a held button cannot double fire; the game-day report says otherwise, so this must be reproduced on the bench, not reasoned about.
- **Tests.** `tests/ui/keyboard.cjs:74-160` covers the page mapping, repeat, and duplicate-keydown safety. Nothing checks that the sketch and the app agree, and nothing covers focus routing or rocker resync.

**Plan:**

1. Owner action items above (real sketch, rocker wiring, any notes).
2. **Bench test in test mode:** hold D5 while plugging in, then press each button and flip the rocker with Notepad focused; record what each types. Compare with the expected label. This tells us in five minutes whether the box or the app is wrong.
3. **Reconcile the mapping** so the sketch, `keyboard.js`, and the new `hotkeys.py` (PL-1) agree. Add an integration test that parses the `.ino` `#define` and pin tables and the app table and asserts they match, so they cannot drift again.
4. **Rocker as authoritative state:** send F21 on close and F22 on open, and send the current position once at boot after the seed delay. With PL-1 in place the app then always tracks the switch.
5. **Hold / double press:** soak test that sends 50 rapid presses and 5 long holds per key through the real app and counts one command per press in the history; on the bench, hold each button for five seconds and confirm one action.
6. Write the missing wiring guide as `hardware/scoreboard_button_box/README.md` (pins, key codes, board settings, test mode).

**Components/files:** `hardware/scoreboard_button_box/scoreboard_button_box.ino`, new `hardware/scoreboard_button_box/README.md`, `src/scoreboard/host/hotkeys.py` (PL-1), `src/scoreboard/views/operator/keyboard.js`, `tests/ui/keyboard.cjs`, new `tests/integration/test_button_box_mapping.py`.

**Dependencies:** Owner action items; PL-1.

**Verification:** Bench test log in `docs/evidence/`; mapping test green; soak test green; real-run rocker check: start the app with the rocker in START and confirm the clock is running.

**Acceptance criteria:**

- The committed sketch is the one on the box, and a test proves it matches the app.
- Every button does what its label says in a bench test and in the real app.
- The rocker position and the game clock state agree after app start, after a window change, and after a flip.
- No button fires twice on hold or on a quick double press.

## Comments

- 2026-09-14: Backlog created from the owner's post-game debrief and a code walk. Owner chose the global OS hook for PL-1, live-sync with preserved ball spot for PL-2, clock-expiry trigger for PL-5, strip plus drawer for PL-3, and both clocks hidden for PL-4. Owner will supply the flashed sketch for PL-8.
