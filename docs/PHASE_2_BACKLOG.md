# Phase 2 Implementation Backlog

**Status:** Tasks 1-11 implemented and verified locally; Tasks 1-9 audited against this backlog on September 5, 2026. Task 10 is implemented against fake screen lists and its two-display and stadium acceptance is outstanding — see `DISPLAY_CHECKLIST.md`. Hardware and release evidence remains open in the roadmap. Task 12 is not started.
**Last updated:** September 5, 2026

The September 5 audit found no acceptance criterion in Tasks 1-9 unmet by code, and two requirement-level defects that the task-by-task verification had missed because each sat between two tasks. Both are fixed and recorded in the roadmap: clock expiration was never written to the durable action history (F-037, F-046), and the application version was a hard compatibility gate on saved games, so the Task 11 version bump would have made every existing game unrecoverable (P-004, P-006).

Each task is intended for one focused Codex session. Before starting, read the roadmap, requirements, architecture, and this task's dependencies. Afterward, update tests, documentation, and the roadmap with evidence.

## Task 1 — Runtime and Windows multi-window proof

**Objective:** Establish the smallest installable Python project and answer the architecture risk: can one pywebview process reliably host operator and spectator windows, target a selected display, reopen the spectator, and shut down cleanly on Windows?

**Components/files:** `pyproject.toml`; `src/scoreboard/__main__.py`; minimal `host/app.py` and `host/displays.py`; minimal static proof pages; proof tests/instructions.

**Boundaries:** No game state, score controls, real clocks, persistence, styling, OBS, or server. Use placeholder text only. Pin Python/tool versions actually tested.

**Dependencies:** Phase 1 architecture; preferably run after the HDMI test, but a normal second monitor can validate the host first.

**Verification:** Clean virtual-environment setup; open two windows; select second display; enter/exit fullscreen; close/reopen spectator; confirm one process and clean exit; test with network disabled; record WebView2 behavior.

**Acceptance criteria:**

- One documented PowerShell command starts both windows.
- Spectator placement/fullscreen is repeatable on a normal two-display Windows setup.
- Closing spectator leaves operator/host running; reopen works.
- Closing application leaves no orphan process.
- Failure to find the selected display produces a clear operator-visible condition.
- Architecture document is updated if fallback to another host is needed.

## Task 2 — Authoritative game-state model and snapshots

**Objective:** Implement versioned, UI-independent state values, invariants, snapshots, and revisions, including pregame and interval countdown lifecycle/phase values.

**Components/files:** `domain/state.py`; `application/snapshots.py`; `tests/unit/test_state.py`; fixtures for valid/invalid snapshots.

**Boundaries:** State only: names, scores, quarter/lifecycle, game/play/event-countdown value/running fields, and event phase. No command handlers, real time, filesystem, or UI wiring.

**Dependencies:** Task 1 project skeleton.

**Verification:** Unit tests for defaults, name/score bounds, allowed quarter/lifecycle labels, immutable-copy behavior, schema serialization, and invalid data.

**Acceptance criteria:**

- Default snapshot matches the documented pregame state.
- Invalid scores, names, labels, and versions are rejected explicitly.
- Snapshots are JSON-compatible and include schema/app version plus monotonic state revision.
- Domain code imports no host, filesystem, or UI module.

## Task 3 — Game-clock engine

**Objective:** Implement the authoritative countdown game clock using injected monotonic time and materialized stop/correction/reset behavior.

**Components/files:** `domain/clocks.py`; clock fields in `domain/state.py`; fake monotonic fixture; `tests/unit/test_game_clock.py`.

**Boundaries:** Pure clock math and state transitions only. No UI timer, webview calls, persistence, play clock, or wall-clock-based elapsed calculation.

**Dependencies:** Task 2; owner decisions may replace provisional display/tolerance defaults but do not block fake-time logic.

**Verification:** Deterministic tests for start/stop idempotence, reset, correction, expiration, delayed callbacks, sub-second pause/resume, zero clamp, and backwards wall-clock changes having no effect.

**Acceptance criteria:**

- Remaining time is derived from monotonic elapsed time, never callback count.
- Callback stalls produce the mathematically correct result.
- Repeated pause/resume preserves sub-second remainder.
- Expiration stops at zero and is observable exactly once.
- Pure tests require no sleeping and cover boundary/error paths.

## Task 4 — Play-clock engine

**Objective:** Add an independent play clock with 25/40 load-stopped presets, explicit start/stop/clear/correct/expire commands, and the documented coupling to a stopped-to-running game-clock transition.

**Components/files:** `domain/clocks.py`; play-clock state; `tests/unit/test_play_clock.py`; simultaneous-clock tests.

**Boundaries:** No buttons or keyboard mapping. A `25` or `40` command loads its value while stopped; a separate Start begins it. A game-clock transition from stopped to running stops and clears the play clock, while a redundant Start on an already-running game clock has no effect on it. No expiration alarm is part of the MVP.

**Dependencies:** Task 3.

**Verification:** Fake-time tests for 25/40 load-stopped behavior, independence from game clock except the documented transition coupling, clear behavior, expiration without alarm, corrections, and simultaneous progression.

**Acceptance criteria:**

- 25 and 40 commands load their exact documented values while stopped.
- No play-clock command changes game-clock state.
- Delayed callbacks and pause/resume behave without cumulative drift.
- A play clock that reaches zero remains at `0.0` unless cleared or changed; it creates no alarm.

## Task 5 — Command service: scores, quarters, lifecycle, and undo

**Objective:** Route every mutation through a serialized, validated command service with revisions and reversible actions.

**Components/files:** `domain/commands.py`; `application/service.py`; state updates; `tests/unit/test_commands.py`; command-order integration tests.

**Boundaries:** No UI. Implement +1/+2/+3/+6, corrections/direct set, quarter transitions, New/End Game, clock commands, and one-level undo. Do not add down/distance, timeouts, possession, or statistics.

**Dependencies:** Tasks 2–4.

**Verification:** Table-driven command tests, below-zero/above-limit rejection, stale revision behavior, repeated/rapid commands, running-clock quarter confirmation contract, undo eligibility, and lifecycle rules.

**Acceptance criteria:**

- Only the service can advance authoritative revisions.
- Every accepted command yields one complete snapshot and one event intent.
- Rejected commands leave state/revision unchanged with a plain-language error code/message.
- Undo appends a new transition and cannot undo dangerous lifecycle/reset actions.
- Commands remain deterministic under rapid serialized input.

## Task 6 — Atomic persistence, recovery, and event logging

**Objective:** Persist every accepted command safely in embedded SQLite and recover a stopped, validated game with a complete audit trail.

**Components/files:** `infrastructure/paths.py`; SQLite persistence/repository module; `diagnostics.py`; `application/recovery.py`; integration tests/fixtures.

**Boundaries:** One embedded SQLite database plus an automatic last-known-good database backup; no database server, cloud sync, registry storage, or UI beyond returned recovery/status models.

**Dependencies:** Task 5.

**Verification:** Temporary-directory tests for SQLite transaction interruption, corrupt primary database, corrupt primary/backup databases, write failure, running-clock checkpoints, action-history order, second-instance lock, and restart of formerly running clocks.

**Acceptance criteria:**

- Every simulated interrupted write leaves a coherent committed state or a valid backup.
- A corrupt primary database loads the last valid backup and reports that fact.
- Recovered clocks are always stopped at persisted derived values.
- A normal running-clock crash restores a checkpoint no more than one displayed second stale without tick-event log spam.
- Durable action-history entries include required timestamp/sequence/source/old/new/result/version fields for accepted and rejected requests.
- Runtime files are stored outside the repository and remain ignored by Git.

## Task 7 — Operator-interface foundation

**Objective:** Build the main operator layout and connect mouse controls to the command bridge using authoritative snapshots.

**Components/files:** `views/shared/`; `views/operator/`; `host/bridge.py`; UI contract tests; update the Task 1 host.

**Boundaries:** Implement the documented live controls, health strip, last action, correction drawer, event-countdown controls, and confirmations. No keyboard shortcuts yet, spectator polish, settings beyond necessary defaults, or advanced football fields.

**Dependencies:** Tasks 1 and 5–6.

**Verification:** Mouse-path tests for every command; focus/form validation; confirmation cancel/apply; persistence/display health simulation; visual check at 1366×768 with 100% and 125% scaling.

**Acceptance criteria:**

- All high-frequency controls fit without scrolling and match the UX hierarchy.
- Running/stopped state is textual and obvious.
- Typing never changes authoritative state before Apply.
- Dangerous actions are separated and confirm old/new impact.
- Rejected commands and save/display failures remain visible and actionable.

## Task 8 — Spectator-display foundation

**Objective:** Render the minimum spectator state and its pregame/interval countdown presentation responsively from complete authoritative snapshots.

**Components/files:** `views/spectator/`; shared snapshot renderer; viewport tests/screenshots.

**Boundaries:** During game play show team names/scores, quarter, game clock, and play clock. During pregame/interval presentation show only the documented countdown and phase information. No logos, animations, sponsor/media content, OBS, or control elements.

**Dependencies:** Tasks 1–7.

**Verification:** Snapshot rendering tests; visual captures at 1280×720, 1366×768, 1920×1080, portrait/narrow, score 0/99/100/199, 24-character names; update matrix after HDMI evidence.

**Acceptance criteria:**

- No controls, browser chrome, scrollbar, overflow, or clipped supported values.
- Changes appear within the documented latency target on the test laptop.
- Layout preserves aspect ratio and safe margins rather than stretching.
- A newly opened view renders the current complete snapshot immediately.

## Task 9 — Keyboard controls and input safety

**Objective:** Implement and rehearse the provisional shortcut map without accidental repeats or text-field conflicts.

**Components/files:** operator JavaScript/input module; shortcut configuration/help; keyboard tests; UX documentation updates if mappings change.

**Boundaries:** Keyboard is an input adapter to existing commands. No global system hotkeys, Stream Deck, physical controller, or remote operator.

**Dependencies:** Task 7.

**Verification:** Every shortcut on main keyboard and numpad where specified; held-key/repeat; text/select/dialog focus; modifier conflicts; rapid alternating score/clock commands; novice help-panel test.

**Acceptance criteria:**

- One deliberate key-down produces at most one command.
- Editable fields suppress live shortcuts.
- Mouse access exists for every shortcut action.
- Quarter/danger rules are identical for mouse and keyboard.
- Help accurately lists the active map.

## Task 10 — Display selection, fullscreen, and failure recovery

**Objective:** Turn the Task 1 proof into production-quality selection, persisted identity, close/reopen, and disconnect/reconnect behavior.

**Components/files:** `host/displays.py`; host lifecycle; operator health/reopen UI; integration/manual Windows test scripts.

**Boundaries:** Windows display/window management only. No LED/RJ45 protocol, processor configuration, automatic HDMI source switching, OBS projector, or hidden auto-moves during live play.

**Dependencies:** Tasks 1, 6–8 and Phase 0 HDMI evidence for stadium-specific acceptance.

**Verification:** Start with one/two monitors; select each display; save/restart; close/reopen while clocks run; unplug/replug HDMI; change scaling/resolution; processor input reselection at stadium when safe.

**Acceptance criteria:**

- Saved display is selected predictably when present.
- Missing display never hides/blocks the operator; status and explicit recovery are provided.
- Display close/disconnect does not stop clocks or corrupt state.
- Reopened view shows the current revision immediately.
- Stadium result and geometry are documented; no unsupported auto-recovery claim is made.

**Implemented September 5, 2026.** The display is identified by Windows device name plus geometry in `config.json`, never by list position; matching is exact, then by name, then by geometry, with no fallback past that. A bounded periodic check reports a display appearing or disappearing and moves nothing. Selecting, reopening, losing, and forgetting a display are host actions that advance no revision. 73 tests cover the policy against injected screen lists, because this development host has one display.

| Criterion | Status |
|---|---|
| Saved display selected predictably when present | ✅ Against fake screen lists, including resolution, scaling, and device-renumbering changes. 🧪 Unverified on real two-display hardware. |
| Missing display never hides or blocks the operator | ✅ No window is opened, the operator view stays complete, clocks keep running, and the display panel is the explicit recovery. |
| Close or disconnect does not stop clocks or corrupt state | ✅ Asserted for a hand-close and a simulated disconnect: revision unchanged, clock still running, database intact, no history row written. 🧪 A real HDMI unplug is unverified. |
| Reopened view shows the current revision immediately | ✅ Including a play clock that never stopped (D-008). |
| Stadium result and geometry documented; no unsupported auto-recovery claim | 🧪 Open. Depends on the Phase 0 HDMI gate. No auto-recovery is claimed anywhere: reopening is always an operator action. |

The remaining two criteria need hardware. [`DISPLAY_CHECKLIST.md`](DISPLAY_CHECKLIST.md) is written for the person who has it.

## Task 11 — Windows packaging and one-action launch

**Objective:** Produce a pinned, reproducible PyInstaller one-folder build that runs offline without development tools.

**Components/files:** lock/pinned dependency metadata; PyInstaller spec/build script; version metadata; packaging/clean-install documentation; `.gitignore` adjustments.

**Boundaries:** One-folder build first. No auto-updater, installer framework, code signing purchase, Windows service, cloud distribution, or one-file optimization.

**Dependencies:** Tasks 1–10; production-laptop constraints should be known before final acceptance.

**Built out of order on September 5, 2026, before Task 10.** Task 10 needs a two-display machine; Task 11 needs none. The consequence was that the package carried Task 1-era display behaviour and had to be rebuilt after Task 10 before any release. **That rebuild was done on September 5, 2026**, immediately after Task 10; see `PACKAGING.md` and the roadmap's Task 10 evidence.

**Verification:** Build on Windows; copy to a clean Windows account/machine without Python/Node/OBS; disable network; launch via shortcut; verify assets/data locations/logs/version; restart and failure recovery; scan `git status` for build products.

**Acceptance criteria:**

- One action launches operator and spectator behavior with no terminal.
- Package works offline and does not need Python, Node.js, or OBS installed.
- State/logs survive replacing the application folder.
- Missing WebView2/runtime prerequisites are detected with a clear documented remedy.
- Build steps and exact tested Windows versions are recorded.

## Task 12 — Sustained rehearsal and recovery acceptance

**Objective:** Prove the complete MVP under realistic operation before any production/media expansion.

**Components/files:** test scripts/checklists; defect log; requirements traceability; operator quick guide; roadmap evidence log.

**Boundaries:** Fix only defects required by MVP acceptance. Do not add animations, media, OBS, networking, advanced stats, or physical controls during rehearsal.

**Dependencies:** Tasks 1–11; owner-approved clock rules/tolerance; normal-monitor rehearsal before stadium use; Phase 0 gate before stadium rehearsal.

**Verification:** Automated suite; 12-minute clock reference measurement; four-quarter simulated game; two-hour soak; score/quarter correction; forced close/crash; corrupt state; spectator close/disconnect/reopen; offline packaged launch; vendor fallback drill.

**Acceptance criteria:**

- Every requirement in the MVP acceptance suite has evidence or an explicitly approved exception.
- Clock meets the owner-approved tolerance on the target laptop.
- No state divergence, unhandled error, clock lockup, or silent persistence failure occurs in rehearsal/soak.
- A novice operator completes the core workflow and corrections using the UI/help.
- Known defects, recovery time, and go/no-go recommendation are recorded.
- Phase 2 is not marked complete until the stadium display rehearsal and fallback procedure pass.

## Backlog guardrail

If a task reveals a later-phase request, record it in the roadmap and continue the current acceptance criteria unless the new information invalidates the architecture or safety. A visually attractive addition is not a reason to bypass clock, persistence, recovery, or packaging verification.

## Deferred scoreboard fields (not in Phase 2 MVP)

Task 5 explicitly excluded down/distance, timeouts, and possession from the MVP command set. Noted here (2026-09-05) as fields the operator still wants, to be scoped as their own task once Phase 2 acceptance is complete:

- Ball on (yard line)
- Timeouts remaining (per team)
- Current down (and distance)
