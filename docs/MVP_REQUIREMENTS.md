# MVP Requirements

**Status:** Phase 1 baseline reconciled with the September 6, 2026 working tree. Tasks 1-11 are substantially built; the current full suite is green at 913 tests with 3 explicit A-1 skips. Task 10's real two-display/stadium evidence and Task 12 rehearsal remain open. C4 publication isolation is only partially complete and the latest working tree must be repackaged before target-laptop acceptance; see `PROJECT_ROADMAP.md` and `CURRENT_PROJECT_AUDIT_2026-09-06.md`.
**Last updated:** September 6, 2026

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
| F-014 | The operator MUST be able to undo reversible scoring, quarter, clock-correction, field-status, and Field Assistant commands from a bounded in-memory LIFO history. The current bound is 20. Undo MUST be a new logged command, not deletion of history; deliberate non-reversible barriers clear the stack, and recovery MUST NOT restore pre-crash undo entries. | Execute multiple reversible commands, undo in LIFO order, cross a barrier, restart, and verify state/log/history behavior. |
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

### 4.6 Down, distance, possession, ball position, and timeouts

Implemented September 5, 2026 (docs/PHASE_2_BACKLOG.md "Deferred scoreboard
fields"). Every field here is independently settable, validated, undoable, and
persisted; none is derived automatically by a scoring, clock, or quarter
command (F-020 through F-052 are unchanged by this section).

| ID | Requirement | Verification |
|---|---|---|
| F-060 | The operator MUST be able to set the current down to 1st, 2nd, 3rd, or 4th, or clear it to not-applicable. Down MUST NOT change automatically. | Command and undo tests; quarter/new-game interaction tests. |
| F-061 | The operator MUST be able to set distance to go (0-99 yards) or clear it to not-applicable. A distance of `0` MUST display as `Goal`, not a literal zero. | Formatter boundary tests; command tests. |
| F-062 | The operator MUST be able to set which team has possession, or clear it to neither team. | Command and undo tests. |
| F-063 | The operator MUST be able to set field position as a team plus a yard line (0-50) counted from that team's own goal line. Field position MUST be one validated, undoable unit; an Undo MUST NOT be able to pair one command's team with a different command's yard line. | Command, undo, and JSON-boundary regression tests. |
| F-064 | Each team's timeouts remaining (0 to a configured maximum, provisional default 3) MUST be independently trackable: a quick "timeout used" action that decrements by one and is rejected rather than going negative, a ±1 correction, and a direct Set for the corrections surface. Timeouts MUST NOT reset automatically at any lifecycle transition. | Command tests for the floor/ceiling rejections and undo. |
| F-065 | `New Game` MUST reset down, distance, possession, and field position to not-applicable/default, and both teams' timeouts to the configured maximum, in the same transition as every other reset field. | New-game test. |
| F-066 | Down, distance, possession, ball position, and timeouts remaining MUST be rendered as text by Python (not derived in JavaScript), on the operator view at all times and on the spectator view whenever the game board is shown (see D-001, D-009). | View-model and browser render tests. |

**Owner decisions still required (see section 13):** whether 3 timeouts per
team is correct and whether it should reset at halftime (B-1); whether a
change of possession should prompt for new down/distance (B-2); whether field
position should display relative to the named team's own goal line or as an
OWN/OPP-relative label (B-3); whether timeouts remaining should also appear on
the spectator board (B-4).

### 4.7 Field Assistant — convenience path (added September 5, 2026)

Implemented after section 4.6, as a separate, optional helper window
(`docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`) that proposes and finalizes
ordinary end-of-play field-status updates. It is a convenience path only: it
does not remove, disable, or change the behavior of the manual down,
distance, possession, and ball-on controls in section 4.6, which remain the
fallback for every play the helper does not support.

F-070 through F-074 below are this document's acceptance-level requirements
for the feature. The granular FA-01 through FA-28 verification matrix is a
separate namespace that lives entirely in
`FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` and is deliberately not duplicated
here; when the two disagree, the matrix is the authority on rules detail and
this section is the authority on scope.

| ID | Requirement | Verification |
|---|---|---|
| F-070 | The Field Assistant MUST be a separate window the operator opens deliberately. It MUST NOT be required to update down, distance, possession, or field position, and the existing manual controls (F-060 through F-063) MUST remain fully usable whether or not the helper window is open. | Manual-control regression tests with the helper open and closed. |
| F-071 | A finalized helper action (an ordinary play, a penalty outcome, or a defined scoring/kickoff transition) MUST change every affected field through exactly one validated, revision-checked, undoable composite command. JavaScript MUST NOT derive or apply football rules. | Composite-command atomicity and undo tests. |
| F-072 | The helper MUST read one snapshot revision as its draft baseline. If the authoritative revision changes before the draft is confirmed, Confirm MUST be disabled and the operator MUST re-sync or discard before finalizing. | Stale-revision refusal tests. |
| F-073 | Finalizing a helper action MUST NOT start, stop, reset, or otherwise change either clock's value or running state. | Clock-isolation tests across every supported transition. |
| F-074 | A saved game recorded before the Field Assistant existed MUST recover safely, with the helper reporting that setup is required, never a migration failure. | Old-snapshot recovery tests. |

**Deliberately manual, not automated by the helper:** OT direction,
onside/blocked kicks, defensive try returns, offsetting/multiple penalties,
enforcement from a spot other than the one proposed, and automatic possession
flips remain the documented manual escape hatch
(`docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` section 7). Native WebView2
rendering of the helper window, the 1366×768-at-100%/125% visual check, and a
live operator rehearsal remain outstanding (`docs/UX_AND_LAYOUT.md` §11).

### 4.8 Crowd-facing game status (added September 6, 2026, audit item F3)

When play stopped, the board previously froze with no explanation: there was no
`FLAG`, `TIMEOUT`, `INJURY`, or `DELAY` indicator anywhere and no timeout
countdown, so the crowd saw a still scoreboard — still showing the old down and
distance — while a penalty was being worked. The layout editor's free text
could not fill the gap, because it is fixed operator-typed copy rather than a
live toggle (`docs/UX_AND_LAYOUT.md` section 10.8).

| ID | Requirement | Verification |
|---|---|---|
| F-080 | The operator MUST be able to raise one crowd-facing status message — `FLAG`, `TIMEOUT`, `INJURY`, or `DELAY` — on the spectator board, and clear it, from an always-visible control that needs no drawer, menu, or mode change. | Command tests; operator source-contract test. |
| F-081 | A status message MUST be presentation only. It MUST NOT change score, clocks, quarter, down, distance, possession, field position, or timeouts, and it MUST NOT enter, clear, or consume the F-014 undo history — a crowd toggle must never push a scoring mistake out of reach. | Command and undo-isolation tests. |
| F-082 | A status countdown MUST be available beside the message, loadable to 30, 60, or 90 seconds, startable and stoppable independently, using the same monotonic/deadline timing model as the other clocks (F-032) and stopping at zero. Raising `TIMEOUT` MUST load and start 60 seconds in one single transition. | Fake-time command tests; one-revision test. |
| F-083 | Both the message and the countdown MUST be rendered as text by Python and bound by the spectator board as ordinary optional widgets: absent or empty text hides the widget rather than drawing an empty box, so neither appears on the wall until the operator raises one (D-001, F-066). | View-model and layout-render tests. |
| F-084 | A status message MUST NOT clear itself when its countdown expires — the expired `0:00` is itself information the crowd wants, and only the operator knows when play has resumed. `New Game` MUST clear both message and countdown with every other reset field (F-065). | Fake-time expiry and new-game tests. |

**Deliberately not built.** The wall shows the status *word* only, with no team
name: the default board has no free space that holds `TIMEOUT — ` plus a
24-character name (F-010) legibly, which team called a timeout is already
carried by `timeout_used` and the timeouts readout, and an operator who wants
it on the wall can enlarge or restyle the widget in the layout editor. A crowd
status is never charged against a team's timeouts — `timeout_used` remains the
separate, undoable command that does that. The Field Assistant does not raise
`FLAG` automatically; opening a draft in a helper window must not mutate
authoritative state (F-072).

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
| U-009 | The operator MUST be able to see the whole undo history — every action a repeated Undo would reverse, newest first, with the next one marked — before spending it, and without leaving the live controls, so a second action never forecloses fixing the first with no view of what is being given up (F-014, audit item I4). | Source-contract and view-model tests. |

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
| D-001 | The spectator window MUST show home name/score, away name/score, quarter, game clock, play clock, and, while the game board is shown, down/distance, field position, and possession (F-060 through F-066, added September 5, 2026). During pregame and halftime, when the countdown board replaces the game board, that board MUST also show both team names and both scores beneath the countdown (added September 5, 2026, deep-dive audit C3). Since September 6, 2026 that countdown board is the active layout's pre-game or halftime **screen** (schema v3, `docs/UX_AND_LAYOUT.md` §10.9): its built-in default satisfies this requirement, and an operator who hides a score widget is making a deliberate layout choice. By default, timeouts remaining and the static game-clock label are not drawn. The editor can expose those optional widgets and add decorative free text, images, and shapes. Since September 6, 2026 the game registry also carries the optional `status_message` and `status_clock` widgets (section 4.8): both are empty, and therefore hidden, until the operator raises a crowd status, so the board is unchanged from before F3 in normal play. | Visual inventory check; layout-editor widget-visibility and element-rendering tests; crowd-status view-model and render tests. |
| D-002 | It MUST support borderless fullscreen on a selected Windows display and remember that preference. If the display is unavailable, it MUST keep the operator usable and report `DISPLAY NOT FOUND` rather than silently taking over the primary screen. | Multi-monitor disconnect/reconnect tests. |
| D-003 | Layout MUST use a resolution-independent logical canvas, scalable typography, and safe margins; it MUST NOT assume the stadium's unknown pixel dimensions. The safe-area margin is now a validated, editable layout property (default 4% inset per side, adjustable only within a documented minimum and maximum inset; added September 5, 2026): every visible widget must fit inside it, and a layout that would place one outside it is rejected rather than silently accepted or clipped. | Render at 1280×720, 1366×768, 1920×1080, and a portrait test mode; layout-editor safe-area validation tests. |
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
| P-010 | Operator-facing startup/recovery timestamps (for example, the recovery screen's "Last saved" value) MUST be shown in human-readable Eastern local time (`America/New_York`), including daylight-saving handling. Stored/logged timestamps (the database, the action history, and the diagnostics log) MAY remain unambiguous ISO/UTC values. Added September 5, 2026. | Unit tests at EST/EDT and the daylight-saving transition boundaries; recovery-report integration test. |

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

Down, distance, possession, ball position, and timeouts are implemented (section 4.6, September 5, 2026) and are no longer non-goals. The MVP does not implement penalties, statistics, rosters, team logos on the board, animations, sponsor scheduling, audio, video, replay, OBS scenes/control, livestreaming, networking or multiple operators, cloud services, user accounts, automated HDMI switching, direct LED/RJ45 protocols, or the physical USB controller.

A presentation layout editor for spectator-board placement, sizing, color, free text, images, and simple shapes is implemented as v2 (September 5, 2026; `docs/UX_AND_LAYOUT.md` §10, `docs/PHASE_2_BACKLOG.md`). It remains presentation-only: it advances no state revision, submits no command, and does not add media, OBS, animations, sponsor rotation, networking, per-resolution layouts, physical controllers, SVG images, downloaded fonts, or a way to bind free text to an authoritative field. **Added September 6, 2026 (verified in focused suites, the full discovery run, and a real pywebview run):** the pregame/halftime event countdown board, previously excluded from the editor, is now covered by it as two additional editable screens (schema v3) — see `docs/UX_AND_LAYOUT.md` §10.9 and `docs/ARCHITECTURE.md` §9. See `docs/PHASE_2_BACKLOG.md` for the full exclusion list.

Saved team presets are implemented (September 6, 2026, audit item F4; `docs/UX_AND_LAYOUT.md` §5b, `docs/ARCHITECTURE.md` §9): an operator can save a team's name, short name, and two colours to `teams.json` and apply it to either side in one confirmed click. That click is the existing `set_team_name` command, so F-010 and the pregame-only rule are unchanged; the colours and short name are shown on the operator's own board and carried in every view model, but **no spectator-board widget binds to them yet** — team colours and logos on the wall remain a later presentation-layout feature, not a requirement.

A Field Assistant convenience path for ordinary end-of-play field-status updates is implemented (section 4.7, September 5, 2026; `docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`). It automates only the scrimmage, penalty, and scoring/kickoff outcomes that document describes; OT direction, onside/blocked kicks, defensive try returns, offsetting/multiple penalties, non-standard enforcement spots, automatic possession flips, and any clock change remain manual, unautomated corrections through the existing controls.

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
- first live-use date and initial operator count;
- **B-1: is 3 timeouts per team the correct default, and should it reset at halftime?** NFHS-style rules award 3 timeouts per team per half; this build starts both teams at 3 and never resets automatically, requiring a manual correction at halftime (section 4.6, F-064);
- **B-2: should a change of possession clear or prompt for new down/distance?** Currently fully independent by design; a real possession change almost always means "1st & 10" for the new team;
- **B-3: is field position described relative to the named team's own goal line (for example "Eagles 35"), or should it use an OWN/OPP-relative convention?** Affects display and operator-control wording only, not the stored value;
- **B-4: should timeouts remaining be added to the spectator board?** Currently operator-only (D-001).
