# MVP Requirements

**Status:** Phase 1 baseline; implementation has not begun
**Last updated:** September 4, 2026

## 1. Purpose and requirement language

This document defines the smallest testable football scoreboard for Phase 2. `MUST` identifies an acceptance requirement. `SHOULD` identifies a desired behavior that may be changed with documented evidence. A **provisional default** is implementable but still requires project-owner confirmation before live use.

The MVP is a local Windows application with one authoritative state owner, an operator interface, and a separate spectator display. It must work without internet access.

## 2. Confirmed product direction

- The MVP includes both the game clock and the 25/40-second play clock.
- Mouse and keyboard control are both required.
- The spectator view contains only team names, scores, quarter, game clock, and play clock.
- The vendor system remains untouched and available as the fallback.
- OBS, direct LED control, networking, and physical-controller integration are not MVP dependencies.

## 3. Provisional football and operating defaults

These values make implementation and testing concrete without claiming to settle school/state rules.

| Topic | Provisional default | Reason | Confirmation needed |
|---|---|---|---|
| Regulation quarter length | 12:00, configurable before a game | Common high-school format and existing project baseline | Confirm against the governing rule set |
| Game-clock direction | Count down to 0:00 | Expected stadium behavior | Confirm |
| Tenths below one minute | Do not display; retain sub-second precision internally | Simplest, least visually disruptive MVP | Owner decision required |
| Clock accuracy target | Absolute error no greater than 0.25 seconds over a continuous 12-minute run on the target laptop | Strict enough to expose drift while achievable with monotonic elapsed time | Owner must accept or replace tolerance |
| Play-clock preset action | Pressing `25` or `40` resets **and starts** the play clock immediately | Minimizes actions during live play | Confirm operator preference/rules |
| Quarter labels | `PRE`, `1st`, `2nd`, `HALF`, `3rd`, `4th`, `OT`, `FINAL`; changed manually | Avoids inventing automatic rule transitions | Confirm overtime labels/workflow |
| Quarter change | Stop both clocks, then require confirmation if either was running | Conservative protection against an accidental transition | Confirm |
| Restart recovery | Restore identity, scores, quarter, and stopped clock values; never auto-resume a running clock | Prevents time advancing unseen during downtime | Confirm before live use |

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
| F-022 | Changing the quarter while a clock is running MUST require confirmation and stop both clocks before committing the change. | Integration test with both clocks running. |
| F-023 | `New Game` MUST require deliberate confirmation, archive/close the current log, and initialize a clean stopped state. | Cancel/confirm tests and file inspection. |
| F-024 | `End Game` MUST stop both clocks, persist `FINAL`, flush the log, and leave the spectator view readable. It MUST NOT erase the game. | End-game and restart test. |

### 4.4 Game clock

| ID | Requirement | Verification |
|---|---|---|
| F-030 | The game clock MUST default to stopped at the configured quarter length (provisionally 12:00). | New-game test. |
| F-031 | Separate Start and Stop controls MUST be available; repeated Start or Stop commands MUST be idempotent. | Command tests and rapid double-click test. |
| F-032 | The running value MUST be derived from a monotonic time source and a stored anchor/deadline, not by subtracting one on each UI tick. | Unit test with an injected fake clock and delayed callbacks. |
| F-033 | The clock MUST never display below 0:00 and MUST stop automatically at zero. | Advance fake time past expiration. |
| F-034 | UI repaint rate MUST NOT affect authoritative time. After a pause/stall, the next state MUST reflect actual monotonic elapsed time. | Simulate a 3-second callback stall. |
| F-035 | Reset MUST stop the clock and restore configured quarter length. If the current value is not already the default, reset MUST require confirmation or a two-step armed action. | Cancel/confirm UI test. |
| F-036 | A correction workflow MUST allow setting minutes and seconds while stopped. Seconds MUST be 0–59; invalid values MUST be rejected without changing state. | Boundary tests. |
| F-037 | Starting, stopping, resetting, expiring, and correcting the clock MUST be logged with old/new values. High-frequency display ticks MUST NOT flood the event log. | Log inspection. |
| F-038 | The clock MUST preserve sub-second remainder internally across stop/start so repeated pauses do not systematically gain or lose time. | Fake-clock pause/resume sequence. |

### 4.5 Play clock

| ID | Requirement | Verification |
|---|---|---|
| F-040 | The play clock MUST be independent of the game clock and support authoritative 25-second and 40-second presets. | Run one clock while the other is stopped; preset tests. |
| F-041 | `25` and `40` MUST be large, always-visible high-frequency controls. The provisional behavior is reset-and-start immediately. | Mouse/keyboard UI tests. |
| F-042 | The operator MUST also be able to Start and Stop the play clock without changing its value. | Command tests. |
| F-043 | The play clock MUST use the same monotonic/deadline timing model as the game clock and MUST stop at zero. | Fake-clock delayed-callback test. |
| F-044 | Resetting the play clock MUST NOT alter the game clock. | Integration test. |
| F-045 | Expiration MUST create a persistent visual alert in the operator view until the next play-clock command. Audio is not part of MVP. | Expiration UI test. |
| F-046 | Preset, start, stop, correction, and expiration events MUST be logged without logging every display tick. | Log inspection. |

## 5. Operator-usability requirements

| ID | Requirement | Verification |
|---|---|---|
| U-001 | All live, high-frequency controls MUST fit on one operator screen at 1366×768 with Windows scaling at 100% and 125%, without scrolling. | Visual/manual test on target modes. |
| U-002 | Game-clock Start and Stop MUST be separate, large, and visibly indicate which state is active. | Usability review and UI state test. |
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
| `2` | Play clock reset/start 25 | Top-row and numpad mapping verified |
| `4` | Play clock reset/start 40 | Top-row and numpad mapping verified |
| `Q` / `Shift+Q` | Quarter forward/back | Confirmation if a clock is running |
| `Z`, `X`, `C`, `V` | Home +1/+2/+3/+6 | Disabled in text fields |
| `N`, `M`, `,`, `.` | Away +1/+2/+3/+6 | Disabled in text fields |
| `Ctrl+Z` | Undo last reversible command | Never undoes reset/new/end-game actions |
| `Esc` | Close correction/settings dialog | MUST NOT close spectator view or application |

| ID | Requirement | Verification |
|---|---|---|
| K-001 | Mouse access MUST exist for every keyboard action. | Control inventory check. |
| K-002 | Shortcuts MUST act on key-down once; held keys and OS key-repeat MUST NOT produce repeated scores. | Hold-key test. |
| K-003 | The application MUST ignore unrecognized shortcuts and MUST NOT intercept normal Windows shortcuts outside its focused windows. | Manual keyboard test. |
| K-004 | A help panel MUST show the active shortcut map. | UI inspection. |

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

## 8. Persistence, recovery, and logging

| ID | Requirement | Verification |
|---|---|---|
| P-001 | Configuration and recoverable game state MUST use versioned local files under a per-user application-data directory; no database server is permitted. | Install/run inspection. |
| P-002 | State writes MUST be atomic: write a temporary file, flush, and replace the previous snapshot. Keep one last-known-good backup. | Kill process during simulated writes; validate either old or new snapshot. |
| P-003 | Save after every accepted command and at clean shutdown. While either clock runs, checkpoint materialized clock values at least once per displayed second without adding tick events to the game log. A write failure MUST be visible to the operator and logged where possible. | Permission/full-disk simulation and running-clock checkpoint inspection. |
| P-004 | On restart, restore team names, scores, quarter, and the most recent successful clock checkpoint with both clocks stopped, even if they were running at failure. Under normal writable storage, the checkpoint MUST be no more than one second older than the last authoritative displayed second. | Forced-process-termination test at several sub-second offsets. |
| P-005 | The operator MUST explicitly choose `Resume recovered game` or `Start new game`; no recovered clock may start automatically. | Restart UI test. |
| P-006 | If the current snapshot is invalid, try the last-known-good snapshot, identify the fallback visibly, and never guess missing values silently. | Corrupt primary snapshot test. |
| P-007 | Each game MUST have an append-only structured event log with timestamp, monotonic sequence, command, source, old/new values, result, and application version. | Schema and ordering test. |
| P-008 | Startup, shutdown, recovery, display open/close, rejected commands, persistence failures, and unhandled errors MUST be logged. | Scenario inspection. |
| P-009 | Local logs and live state MUST not be committed to Git. | `git status --ignored` check. |

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

- governing school/state clock rules and regulation quarter length;
- whether tenths display below one minute;
- acceptable clock-accuracy tolerance;
- whether 25/40 preset buttons reset-and-start or reset-stopped;
- overtime labels/workflow;
- production laptop and school software-install restrictions;
- first live-use date and initial operator count.
