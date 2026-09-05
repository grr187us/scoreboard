# MVP Requirements

**Status:** Phase 1 baseline, updated by the September 5, 2026 Phase 2 audit; implementation Tasks 1-11 are substantially built. Focused Bundle A verification passes, while the full discovered suite still has legacy pregame/quarter expectation failures and unavailable browser-tool errors. Task 10's real two-display/stadium evidence and Task 12 rehearsal remain open.
**Last updated:** September 5, 2026

## 1. Purpose and requirement language

This document defines the smallest testable football scoreboard for Phase 2. `MUST` identifies an acceptance requirement. `SHOULD` identifies a desired behavior that may be changed with documented evidence. A **provisional default** is implementable but still requires project-owner confirmation before live use.

The MVP is a local Windows application with one authoritative state owner, an operator interface, and a separate spectator display. It must work without internet access.

## 2. Confirmed product direction

- The MVP includes both the game clock and the 25/40-second play clock.
- Mouse and keyboard control are both required.
- Initial operation is expected to involve two people: one laptop operator for the Phase 2 core, and a second operator for a future optional peripheral. The peripheral is not a Phase 2 dependency and must not be required for core operation.
- The spectator view contains only team names, scores, quarter, game clock, and play clock.
- The vendor system remains untouched and available as the fallback.
- OBS, direct LED control, networking, and physical-controller integration are not MVP dependencies.

## 3. Provisional football and operating defaults

These values make implementation and testing concrete without claiming to settle school/state rules.

| Topic | Provisional default | Reason | Confirmation needed |
|---|---|---|---|
| Governing baseline | Standard NFHS-style high-school football; local variations will be configured when confirmed | Owner decision | Confirm local/state exceptions before live use |
| Regulation quarter length | 12:00 | Owner decision, consistent with NFHS-style high-school football | Local/state exception only |
| Game-clock direction | Count down to 0:00 | Owner decision | Local/state exception only |
| Pregame countdown | The authoritative Game Clock is a 30:00 `KICKOFF IN` countdown while `PRE` is selected | Owner decision, Bundle A | Confirmed September 5, 2026 |
| Halftime and warmup | One 15:00 total countdown until the second half: `HALFTIME` is the current phase from 15:00 through 3:01 and `WARMUP` from 3:00 through 0:00; show `Warmup follows: 3:00` during halftime | Owner decision | Control/start workflow still needs confirmation. **Open (audit A-2):** NFHS-style practice is commonly a 15-minute intermission *followed by* a 3-minute warmup, which totals 18:00. Confirm the arithmetic against local practice. |
| Game-clock display precision | At one minute or more, display remaining whole seconds rounded up (for example, internal 12:25.1 displays `12:26`); below one minute, display seconds and tenths rounded up | Owner decision | Confirmed |
| Play-clock display precision | Display tenths rounded up during the final five seconds | Owner decision | Confirmed |
| Clock accuracy target | Absolute error no greater than 0.25 seconds over a continuous 12-minute run on the target laptop | Strict enough to expose drift while achievable with monotonic elapsed time | Owner must accept or replace tolerance |
| Play-clock preset action | Plain `25` or `40` loads the selected value while stopped; distinct `25 + Start` and `40 + Start` controls load and start atomically | Owner decision | Confirmed |
| Play-clock venue role | This spectator scoreboard is the stadium's only play-clock display | Owner confirmation | Recovery/visibility requirements are therefore critical |
| Play-clock behavior when game clock starts | When the game clock transitions from stopped to running, clear the play clock: stop it and display `PLAY CLOCK —`. If the game clock was already running, a play-clock countdown continues normally to zero unless an operator clears or changes it. | Owner decision | Define how an expected zero during a live play is presented without a misleading alert. **Open (audit A-1):** this assumes the game clock starts at the snap. Under NFHS-style rules the game clock also starts on the ready-for-play, with the play clock already running; the rule as written would clear the stadium's only play-clock display in those situations. Confirm with the owner and officials before live use. |
| Play-clock behavior when game clock stops | A real game-clock STOP transition, including natural expiration at 0:00, clears a running play clock and displays `PLAY CLOCK —`. A redundant STOP while the game clock is already stopped leaves an independently running play clock unchanged. | Owner decision, September 5, 2026 | Revisit only if officials require a different stopped-clock workflow. |
| Quarter labels | `PRE`, `1st`, `2nd`, `HALF`, `3rd`, `4th`, `OT`, `FINAL`; changed manually | Owner selected a manually chosen overtime workflow pending local confirmation | Confirm local overtime procedure before live use |
| Quarter change | Every forward, back, and direct move requires confirmation. It names source/target, clocks that will stop, and any loaded value. `PRE` → `1st` with time remaining requires the exact accepting action `Start 1st quarter — discard remaining pregame time`; it loads stopped 12:00. At 0:00 it uses the normal confirmation. | Owner decision, Bundle A | Overtime uses the same 12:00 default until local rules are confirmed. |
| Restart recovery | Restore team identity, scores, quarter/phase, and each clock's last persisted remaining whole-second value; never auto-resume a running clock. Require operator verification before resuming recovered state. | Owner decision | Confirmed |
| Durable history | Keep an offline, durable history of accepted and rejected operator actions, including when they occurred and the relevant old/new values, so recovery can be verified after a crash. | Owner decision | Select embedded local storage format |

## 4. Functional requirements

### 4.1 State and command model

| ID | Requirement | Verification |
|---|---|---|
| F-001 | One Python component MUST own the authoritative game state. Views MUST render snapshots and request commands; they MUST NOT mutate authoritative state locally. | Unit test rejected direct/invalid mutations; integration test both views show the same revision. |
| F-002 | Every accepted state-changing command MUST produce a monotonically increasing revision and an event-log entry. | Issue commands and compare revision/log order. |
| F-003 | Commands MUST be validated and serialized so two rapid inputs cannot produce a partially updated state. | Stress-test rapid commands and assert deterministic final state. |
| F-004 | The current state MUST include team names, scores, quarter label, game-clock value/running state, play-clock value/running state, and game lifecycle state. | State-schema unit test. |

### 4.2 Teams and scoring

| ID | Requirement | Verification |
|---|---|---|
| F-010 | The operator MUST be able to set home and away names before a game; trimmed names MUST be 1–24 visible characters. | Boundary and UI tests for empty, 1, 24, and 25 characters. |
| F-011 | Scores MUST start at 0 for a new game and MUST be displayed as non-negative integers. | New-game test and negative-input test. |
| F-012 | Separate home and away controls MUST provide `+1`, `+2`, `+3`, and `+6`. | Click and keyboard tests for every increment/team pair. |
| F-013 | A score change MUST identify the team, delta, old value, and new value in the event log. | Inspect structured log after each command. |
| F-014 | The operator MUST be able to undo the most recent reversible scoring or quarter command. Undo MUST be a new logged command, not deletion of history. | Execute, undo, restart, and verify state/log. |
| F-015 | A correction panel MUST provide `-1`, `-2`, `-3`, and `-6`, reject results below zero without changing state, and visually separate corrections from normal scoring. | UI and command validation tests. |
| F-016 | Direct score entry MUST require an explicit Apply action and confirmation showing old and new values. | UI test that typing alone does not change state. |
| F-017 | The display MUST support at least scores 0–199 without overlap. Values above the supported visual range MUST be rejected with an operator-visible error, not clipped silently. | Layout tests at 0, 99, 100, and 199; rejection at 200. |

### 4.3 Quarter and game lifecycle

| ID | Requirement | Verification |
|---|---|---|
| F-020 | Quarter changes MUST be manual and limited to configured labels. | Command tests for all labels and invalid input. |
| F-021 | The operator MUST be able to move forward or backward one label and select a label directly through correction controls. | Mouse/keyboard tests. |
| F-022 | Every forward, back, and direct quarter action MUST require confirmation, whether stopped or running. The prompt MUST state source/target, which running clocks will stop, and any game-clock value that will load; cancellation changes nothing and the accepted resubmission uses the displayed revision. | Mouse, keyboard, direct-selection, cancellation, and stale-revision tests. |
| F-023 | `New Game` MUST require deliberate confirmation, archive/close the current log, and initialize a clean stopped state. | Cancel/confirm tests and file inspection. |
| F-024 | `End Game` MUST stop both clocks, persist `FINAL`, flush the log, and leave the spectator view readable. It MUST NOT erase the game. | End-game and restart test. |
| F-025 | While `PRE` is selected, the authoritative Game Clock MUST be the stopped/running 30:00 pregame `KICKOFF IN` countdown in both operator and spectator views. Halftime remains a separately modeled 15:00 interval countdown. | New-game, fake-time, render, and recovery tests. |
| F-026 | The interval countdown MUST identify `HALFTIME` while more than 3:00 remains and `WARMUP` at 3:00 or less; during `HALFTIME`, the spectator view MUST visibly state `Warmup follows: 3:00`. | Boundary render tests at 15:00, 3:01, 3:00, and 0:00. |
| F-027 | Pregame Game Clock and halftime interval starts, stops, corrections, expirations, and phase changes MUST be validated commands and logged; their display updates MUST use the same monotonic timing model. Pregame expiry remains `PRE` and does not couple to the play clock. | Fake-time, logging, delayed-callback, and expiry tests. |
| F-028 | The Game Clock controls provide pregame Start, Stop, Reset, and Edit Current Time (up to 30:00) in `PRE`; halftime retains separate interval controls. | UI, boundary, and command tests. |
| F-029 | Accepted `PRE` → live-quarter transitions discard the pregame value and load stopped 12:00. Other live-quarter transitions load stopped 12:00 only from a resulting zero and preserve nonzero values. Returning to PRE loads stopped 30:00. A transition that loads a clock is not undoable. | Forward, back, direct-selection, zero/nonzero, and Undo tests. |

Lifecycle is advanced by existing accepted commands: quarter forward/back/direct
selection and quarter Undo map PRE to PRE_GAME, HALF to HALFTIME, FINAL to FINAL,
and playing labels to IN_PROGRESS. Starting the Game Clock in PRE remains
PRE_GAME; only an accepted quarter transition enters IN_PROGRESS. End Game sets FINAL; New Game restores PRE_GAME.
No expiry advances lifecycle. Team names are editable only in PRE_GAME.

### 4.4 Game clock

| ID | Requirement | Verification |
|---|---|---|
| F-030 | A new game's Game Clock MUST default stopped at 30:00 in PRE; accepted entry to a live quarter loads stopped 12:00. | New-game and transition tests. |
| F-031 | Separate Start and Stop controls MUST be available; repeated Start or Stop commands MUST be idempotent. | Command tests and rapid double-click test. |
| F-032 | The running value MUST be derived from a monotonic time source and a stored anchor/deadline, not by subtracting one on each UI tick. | Unit test with an injected fake clock and delayed callbacks. |
| F-033 | The clock MUST never display below 0:00 and MUST stop automatically at zero. | Advance fake time past expiration. |
| F-034 | UI repaint rate MUST NOT affect authoritative time. After a pause/stall, the next state MUST reflect actual monotonic elapsed time. | Simulate a 3-second callback stall. |
| F-035 | Reset MUST stop the clock and restore the active default: 30:00 in PRE or 12:00 in a live quarter. If the current value is not already the default, reset MUST require confirmation or a two-step armed action. | Cancel/confirm UI test. |
| F-036 | A correction workflow MUST allow setting Game Clock minutes and seconds (0–30 in PRE, 0–12 in live quarters). Opening it MUST stop a running clock; invalid values MUST be rejected without changing state. | Boundary, running-clock, and UI tests. |
| F-037 | Starting, stopping, resetting, expiring, and correcting the clock MUST be logged with old/new values. High-frequency display ticks MUST NOT flood the event log. Expiration has no operator command behind it and is recorded by the refresh tick with source `system`, without advancing a state revision. | Log inspection; expiry-edge tests. |
| F-038 | The clock MUST preserve sub-second remainder internally across stop/start so repeated pauses do not systematically gain or lose time. | Fake-clock pause/resume sequence. |
| F-039 | The game clock MUST display remaining whole seconds rounded up while its rounded tenths value is at least 60.0, then display tenths rounded up. Thus 60.0 displays `1:00`, 59.99 displays `1:00`, 59.9 displays `59.9`, and 12:25.1 displays `12:26`. | Boundary formatter tests using exact nanosecond values. |

### 4.5 Play clock

| ID | Requirement | Verification |
|---|---|---|
| F-040 | The play clock MUST be independent of the game clock and support authoritative 25-second and 40-second presets, except for the explicit start-side and stop-side couplings in F-048 and F-052. | Run one clock while the other is stopped; preset tests. |
| F-041 | Plain `25` and `40` MUST be large, always-visible load-stopped controls. Visually distinct `25 + Start` and `40 + Start` controls MUST atomically load the selected preset and begin the play clock; a separate Start action remains available. | Mouse-path, validation, stopped, and running-clock command tests. |
| F-042 | The operator MUST also be able to Start and Stop the play clock without changing its value. | Command tests. |
| F-043 | The play clock MUST use the same monotonic/deadline timing model as the game clock and MUST stop at zero. | Fake-clock delayed-callback test. |
| F-044 | Resetting the play clock MUST NOT alter the game clock. | Integration test. |
| F-045 | Clock expiration MUST stop the applicable clock at zero without audio, a persistent visual alert, or an automatic lifecycle/quarter change. The stopped zero remains visible unless a separate clear rule applies. | Fake-time expiration and UI tests. |
| F-046 | Preset, start, stop, correction, and expiration events MUST be logged without logging every display tick. A zero reached by an accepted command (a correction to `0`, or the F-048 clear at a game-clock Start) is that command's history row, not an expiration. | Log inspection; expiry-edge tests. |
| F-047 | The play clock MUST display remaining whole seconds rounded up until its rounded tenths value is below 5.0, then display tenths rounded up. Thus 5.0 displays `5`, 4.99 displays `5`, 4.9 displays `4.9`, and 4.01 displays `4.1`. | Boundary formatter tests using exact nanosecond values. |
| F-048 | In `1st`–`4th`/`OT`, a stopped-to-running Game Clock transition MUST stop and clear the play clock. In PRE, Start runs only the pregame countdown and MUST not couple to the play clock. | Integration tests for both modes. |
| F-049 | A play clock that is not cleared by a stopped-to-running or running-to-stopped game-clock transition MUST continue to zero and stop there unless changed by an operator. | Fake-time tests for both game-clock states. |
| F-050 | The operator MUST have a deliberate manual command to stop and clear the play clock. A cleared spectator value displays as `PLAY CLOCK —`; if the play clock reaches `0.0` while the game clock is already running, it remains visibly `0.0` without an alert until this command or another play-clock command. | UI and state-transition tests. |
| F-051 | The play clock MUST provide Edit Current Time in the correction area. Opening it MUST stop a running play clock; the confirmation MUST validate the requested value and offer `Start after applying?`, defaulting to `Remain stopped`. | Boundary, running-clock, and UI tests. |
| F-052 | In live quarters, a real Game Clock running-to-stopped transition through Stop or expiry clears a running play clock. PRE Stop/expiry MUST not couple; pregame expiry remains PRE at 0:00. | Fake-time command and bridge-tick tests. |

## 5. Operator-usability requirements

| ID | Requirement | Verification |
|---|---|---|
| U-001 | All live, high-frequency controls MUST fit on one operator screen at 1366×768 with Windows scaling at 100% and 125%, without scrolling. | Visual/manual test on target modes. |
| U-002 | Game-clock Start and Stop MUST be separate, large, and visibly indicate which state is active. A running game clock uses green and a running play clock uses red as supplementary cues; `RUNNING`/`STOPPED` text remains visible. | Usability review and UI state test. |
| U-003 | Play-clock 25 and 40 controls and both teams' scoring buttons MUST remain visible without opening a menu. | Visual test. |
| U-004 | Dangerous actions (`New Game`, reset game clock, direct score/time correction, `End Game`) MUST be spatially separated and require confirmation or deliberate arming. | Mis-click/cancel tests. |
| U-005 | The operator MUST see a connection/health indicator for the spectator window, persistence status, and the current authoritative revision. | Simulate display close and write failure. |
| U-006 | Focus in a text field MUST suppress global scoring/clock shortcuts. | Type shortcut characters in every editable field. |
| U-007 | Every rejected action MUST leave state unchanged and show plain-language feedback with a recovery action when possible. | Invalid-command tests. |
| U-008 | The previous reversible command and a clearly labeled Undo action MUST be visible during normal operation. | UI inspection. |

## 6. Keyboard requirements

The exact key map may change after operator rehearsal, but the following provisional map is testable and avoids modifiers for the most time-critical actions.

| Key | Action | Safety rule |
|---|---|---|
| `Space` | Toggle game clock start/stop | Disabled while editing text; state is always visible |
| `2` | Load 25-second play preset, stopped | Top-row and numpad key values; target-laptop rehearsal pending |
| `4` | Load 40-second play preset, stopped | Top-row and numpad key values; target-laptop rehearsal pending |
| `P` / `S` | Play clock Start / Stop | Separate explicit actions; suppressed while editing |
| `Q` / `Shift+Q` | Quarter forward/back | Confirmation if a clock is running |
| `Z`, `X`, `C`, `V` | Home +1/+2/+3/+6 | Disabled in text fields |
| `N`, `M`, `,`, `.` | Away +1/+2/+3/+6 | Disabled in text fields |
| `Ctrl+Z` | Undo last reversible command | Never undoes reset/new/end-game actions |
| `Esc` | Close correction/settings dialog | MUST NOT close spectator view or application |

| ID | Requirement | Verification |
|---|---|---|
| K-001 | Mouse access MUST exist for every keyboard action. Keyboard commands MUST record source `operator-keyboard`; mouse commands record `operator-mouse`. | Control inventory check. |
| K-002 | Shortcuts MUST act on key-down once; held keys and OS key-repeat MUST NOT produce repeated scores. | Hold-key test. |
| K-003 | The application MUST ignore unrecognized shortcuts and MUST NOT intercept normal Windows shortcuts outside its focused windows. | Manual keyboard test. |
| K-004 | A help panel MUST show the active shortcut map. | UI inspection. |

Space selects the existing Start or Stop command from the rendered snapshot;
JavaScript does not maintain another running flag. The help panel is generated
from the handler table. All inputs, textareas, selects and contenteditable regions
suppress live shortcuts, as do open confirmation dialogs. Esc closes the top
confirmation or drawer even while editing. Held/repeated keys, composing input,
Alt/Meta combinations and unlisted modifier combinations produce no command.
Numpad behavior and actual Windows repeat timing require target-laptop evidence.

## 7. Spectator-display requirements

| ID | Requirement | Verification |
|---|---|---|
| D-001 | The spectator window MUST show only home name/score, away name/score, quarter, game clock, and play clock in the MVP. | Visual inventory check. |
| D-002 | It MUST support borderless fullscreen on a selected Windows display and remember that preference. If the display is unavailable, it MUST keep the operator usable and report `DISPLAY NOT FOUND` rather than silently taking over the primary screen. | Multi-monitor disconnect/reconnect tests. |
| D-003 | Layout MUST use a resolution-independent logical canvas, scalable typography, and safe margins; it MUST NOT assume the stadium's unknown pixel dimensions. | Render at 1280×720, 1366×768, 1920×1080, and a portrait test mode. |
| D-004 | State changes SHOULD appear within 100 ms in the spectator view on the target laptop; MUST appear within 250 ms. | Timestamped integration test. |
| D-005 | Closing the spectator window MUST NOT stop clocks or close the operator. The operator MUST show `DISPLAY CLOSED` and offer one-click reopen. | Close/reopen test while clocks run. |
| D-006 | If the HDMI display disconnects, authoritative operation and persistence MUST continue. The app MUST move/reopen the spectator view only after an explicit operator action. | Unplug/replug test on a normal HDMI monitor. |
| D-007 | The spectator view MUST contain no operator controls, pointer-dependent information, dialog, browser chrome, or scrollbars. | Fullscreen visual test. |
| D-008 | Because this is the stadium's only play-clock display, the spectator play clock MUST remain highly legible whenever it is active, and display loss/recovery tests MUST explicitly verify play-clock continuity. | Fullscreen and close/reopen tests with an active play clock. |
| D-009 | The spectator board MUST always retain the `PLAY CLOCK` label during game mode. A cleared clock displays `—`, while a naturally expired uncleared clock displays `0.0`. Live periods display as `1st Quarter` through `4th Quarter`; the saved authoritative quarter label remains compact. | View-model and browser render tests. |

## 8. Persistence, recovery, and logging

| ID | Requirement | Verification |
|---|---|---|
| P-000 | A stored game MUST remain recoverable across an application update. Compatibility MUST be decided by the state schema version alone; the application version is provenance and MUST be reported to the operator when it differs, never used to refuse a saved game. | Write a snapshot stamped with an older application version and recover it. |
| P-001 | Configuration MAY use versioned local files, but recoverable state and action history MUST use one embedded SQLite database under a per-user application-data directory. No database server is permitted. | Install/run inspection. |
| P-002 | State changes and their durable action-history entries MUST commit in one SQLite transaction. Maintain an automatically refreshed last-known-good database backup. | Simulated interrupted transaction; validate coherent current or backup database. |
| P-003 | Save after every accepted command and at clean shutdown. While any countdown runs, checkpoint its materialized remaining value at least once per displayed second without adding tick events to the game log. A write failure MUST be visible to the operator and logged where possible. | Permission/full-disk simulation and running-clock checkpoint inspection. |
| P-004 | On restart, restore team names, scores, quarter/phase, and the most recent successful remaining whole-second checkpoint for every clock, with all clocks stopped even if they were running at failure. Under normal writable storage, a checkpoint MUST be no more than one displayed second older than the last authoritative displayed second. | Forced-process-termination test at several sub-second offsets. |
| P-005 | The operator MUST explicitly choose `Resume recovered game` or `Start new game`; no recovered clock may start automatically. | Restart UI test. |
| P-006 | If the current database is invalid, try the last-known-good database backup, identify the fallback visibly, and never guess missing values silently. | Corrupt primary database test. |
| P-007 | Each game MUST have an append-only durable action history with wall-clock timestamp, monotonic sequence, command, source, relevant old/new values, result, and application version. It MUST retain accepted actions and rejected operator requests. | Schema, ordering, and post-crash recovery inspection. |
| P-008 | Startup, shutdown, recovery, display open/close, rejected commands, persistence failures, and unhandled errors MUST be logged. | Scenario inspection. |
| P-009 | Local databases, backups, logs, and live state MUST not be committed to Git. | `git status --ignored` check. |

## 9. Reliability and failure requirements

| ID | Requirement | Verification |
|---|---|---|
| R-001 | The core application MUST launch and operate with all network adapters disabled and no internet access. | Offline acceptance run. |
| R-002 | A spectator-rendering error MUST not terminate the state/clock engine or operator controls. | Inject renderer failure. |
| R-003 | An unhandled fatal error MUST attempt to flush diagnostic logs and preserve the last good state; the next launch MUST show recovery status. | Controlled crash test. |
| R-004 | The application MUST reject a second authoritative instance using the same state directory, with a clear message and no file corruption. | Double-launch test. |
| R-005 | The provisional clock tolerance is ≤0.25 seconds absolute error over 12 continuous minutes and no cumulative pause/resume drift beyond that tolerance. | Compare to an independent monotonic reference on target hardware. |
| R-006 | The MVP MUST complete a four-quarter simulated game and a minimum two-hour soak without state divergence, uncaught errors, or clock lockup. | Rehearsal log and checklist. |
| R-007 | Failure of any future integration MUST be isolated from core operation. | Architecture review now; fault injection when adapters exist. |

## 10. Windows packaging and launch

| ID | Requirement | Verification |
|---|---|---|
| W-001 | Development MUST support a documented PowerShell setup from a clean Windows checkout with pinned dependencies. | Execute in a clean test directory/VM. |
| W-002 | The production deliverable MUST launch from a shortcut or executable without requiring Python, Node.js, a terminal, an internet connection, or OBS on the operator machine. | Test on a Windows account without development tools. |
| W-003 | Use a PyInstaller **one-folder** build initially for diagnosability; one-file packaging is deferred until recovery, startup time, and asset handling are proven. | Packaged launch and file inspection. |
| W-004 | One user action MUST start the state engine and both windows. Clean shutdown MUST close all owned windows/processes. | Task Manager/process inspection. |
| W-005 | Runtime state and logs MUST be outside the installed application directory so updates do not erase a game. | Upgrade/reinstall simulation. |
| W-006 | Packaging MUST include all fonts/assets needed for offline display and a visible application version in diagnostics. | Offline packaged run. |

## 11. Explicit non-goals

The MVP does not implement down/distance, possession, timeouts, penalties, statistics, rosters, team logos/colors as a requirement, animations, sponsor scheduling, audio, video, replay, OBS scenes/control, livestreaming, networking or multiple operators, cloud services, user accounts, automated HDMI switching, direct LED/RJ45 protocols, or the physical USB controller.

It also does not modify the vendor computer, software, controller, or license dongle.

## 12. MVP acceptance suite

The MVP is acceptable only when all of the following are evidenced:

1. A clean Windows installation launches offline with one action.
2. Every home/away increment, correction, undo, and quarter change produces correct state and a structured event.
3. Both clocks pass deterministic fake-time tests, delayed-callback tests, expiration tests, and the owner-approved real-time tolerance.
4. Mouse and keyboard controls pass focus, key-repeat, and dangerous-action tests.
5. The spectator view is readable and free of controls at all test resolutions.
6. Closing/disconnecting/reopening the display does not stop or corrupt authoritative operation.
7. Forced termination restores the last good state with both clocks stopped and a clear recovery choice.
8. Corrupt-current-state recovery uses the backup or reports a safe failure without silently inventing state.
9. A four-quarter rehearsal and two-hour soak complete without divergence or uncaught failure.
10. The vendor fallback remains intact and the stadium HDMI test is recorded before stadium use.

## 13. Owner decisions still required

The following do not block architecture or early implementation but block final MVP sign-off:

- **whether a game-clock Start should always clear the play clock** (audit A-1). The rule as built assumes the game clock starts at the snap; on a ready-for-play start it would blank a play clock that is still legitimately running. This is the one open decision that can visibly mislead the field, because this board is the stadium's only play-clock display;
- **whether the interval is 15:00 total or 15:00 plus a 3:00 warmup** (audit A-2);
- local/state exceptions to the NFHS-style rules baseline, including the overtime procedure;
- acceptable clock-accuracy tolerance;
- overtime labels/workflow;
- production laptop and school software-install restrictions;
- first live-use date and initial operator count.
