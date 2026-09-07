# Phase 2 Implementation Backlog

**Status:** Tasks 1-11 are substantially implemented; after the September 6, 2026 F3/I4 work the full discovered suite is green — **913 tests, 0 failures, 0 errors, 3 skipped** from a clean temporary Python 3.11.9 environment with Node.js on `PATH` and isolated operator data. The 3 skips are blocked on question A-1 and are not a pass. Task 10's two-display and stadium acceptance is outstanding; Task 12 is not started. Current working-tree work also implements I4's 20-entry Undo stack, F3's crowd-facing status message and countdown end to end, and the presets half of F4, while C4 is reopened for a cross-thread delivery-ordering gap. See `../PROJECT_ROADMAP.md` and `CURRENT_PROJECT_AUDIT_2026-09-06.md`. Historical discovery counts remain in the roadmap for lineage.
**Last updated:** September 7, 2026

**Owner-requested presentation follow-up, September 7:** Tigers Stadium is
implemented as a fifth editable preset for each of Game, Pre-game, and
Halftime. Full suite: **1115 tests, zero failures/errors, 3 expected A-1 skips**;
the new browser test covers 60 layout cases and editor save/reopen and cutscene
restoration. The Windows package was rebuilt and verified. See
[the workflow](UX_AND_LAYOUT.md#1010-tigers-stadium-preset-september-7-2026)
and `PROJECT_ROADMAP.md` for evidence. This presentation-only owner request
does not advance Task 12 or any hardware gate; suggestions 2 and 3 (motion
and a field graphic) remain outside this task.

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
- A play clock that reaches zero remains at `0` unless cleared or changed; it creates no alarm.

## Task 5 — Command service: scores, quarters, lifecycle, and undo

**Objective:** Route every mutation through a serialized, validated command service with revisions and reversible actions.

**Components/files:** `domain/commands.py`; `application/service.py`; state updates; `tests/unit/test_commands.py`; command-order integration tests.

**Boundaries:** No UI. Implement +1/+2/+3/+6, corrections/direct set, quarter transitions, New/End Game, clock commands, and the original one-level Undo. Do not add down/distance, timeouts, possession, or statistics. **Later expansion:** audit I4 now keeps up to 20 reversible entries in memory; the Task 5 boundary remains historical, not the current Undo limit.

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

**Historical Task 8 boundary:** During game play show team names/scores, quarter, game clock, and play clock. The original pregame/interval screen showed only countdown and phase information. Audit C3 later corrected that release-level omission: current schema-v3 pregame/halftime screens also retain both team names and scores. No controls, OBS, or authoritative logic belong in the spectator page.

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

## Post-audit testing follow-ups — September 5, 2026

Local test-window feedback is tracked as individual issues in
[`../.scratch/testing-followups/`](../.scratch/testing-followups/). These are
not silently folded into Task 12: the first two change a documented clock and
quarter-safety workflow and need an owner decision before implementation.

| Issue | Scope | Status | Recommended delivery |
|---|---|---|---|
| 01 — Pregame game-clock unification | Show/control the `30:00` pregame countdown through Game Clock; halftime remains separate | ✅ Bundle A implemented and verified September 5 | Delivered with 02 |
| 02 — Quarter-transition safeguards | Confirm every quarter action; PRE → 1st time abandonment uses owner-approved action wording | ✅ Bundle A implemented and verified September 5 | Delivered with 01 |
| 03 — Running-clock colors | Green running game clock; red running play clock, with text status retained | ✅ Implemented and verified September 5 | Delivered with 04 |
| 04 — Persistent Play Clock label and quarter title | Show `PLAY CLOCK —` after a clear; render `2nd Quarter` and equivalent live labels | ✅ Implemented and verified September 5 | Delivered with 03 |
| 05 — Presentation layout editor discovery | Safe, offline visual-editor research | ✅ v1 delivered September 5, 2026; ✅ rebuilt as a v2 canvas editor the same day | v1 delivered numeric constrained editing (no drag-and-drop); v2 replaced it with pointer drag/resize, multi-select, undo, free elements, fonts, and presets — see "Phase 2 owner request 3 — presentation layout editor v2" in `PROJECT_ROADMAP.md` |

The owner explicitly considers routine scoring increments such as `+6` quick,
reversible actions; do not add confirmation to them. Major time/lifecycle
commands remain the safety focus.

## Backlog guardrail

If a task reveals a later-phase request, record it in the roadmap and continue the current acceptance criteria unless the new information invalidates the architecture or safety. A visually attractive addition is not a reason to bypass clock, persistence, recovery, or packaging verification.

## Deferred scoreboard fields — ✅ implemented September 5, 2026

Task 5 explicitly excluded down/distance, timeouts, and possession from the MVP
command set. The owner asked for these to be added after the local-time
presentation work and before the presentation layout editor:

- ball on / current yard line;
- timeouts remaining for each team;
- current down;
- to go / distance;
- possession;
- any additional essential football field found during the requirements review.

This follow-up was a separate state-and-controls task, not a reason to reopen
the Phase 2 MVP boundaries before Task 12 and the hardware evidence are
complete. It covers authoritative state, validated commands, operator
controls, spectator rendering, persistence/recovery, and action history, and
does not add statistics, media, OBS, networking, or physical-controller
integration. Values and rules that depend on local officials or league
practice are recorded as open decisions (B-1 through B-4) rather than guessed;
see "Phase 2 owner request 2 — expanded football state and controls" in
`PROJECT_ROADMAP.md` for full evidence, including a real defect (a domain
object briefly reaching the JSON/history boundary through Undo) found and
fixed during testing. No additional essential field beyond the five listed
was identified during the requirements review.

## Presentation layout editor — ✅ v1 delivered, ✅ v2 delivered, both September 5, 2026; ✅ v3 (pre-game and halftime screens) delivered September 6, 2026

Implements item 3 of "Owner-requested next scoreboard work" in
`PROJECT_ROADMAP.md`, delivered after the local-time presentation and expanded
football fields it was waiting on (items 1 and 2, both implemented and
verified above). See "Phase 2 owner request 3 — presentation layout editor"
and "Phase 2 owner request 3 — presentation layout editor v2" in
`PROJECT_ROADMAP.md` for full evidence, `.scratch/layout-editor-v2/spec.md`
for the v2 design spec, and `docs/UX_AND_LAYOUT.md` §10 for the operator-facing
workflow, widget inventory, free elements, fonts, presets, and safe-area
policy.

**What v1 did.** A separate editor window, opened from the operator's
Advanced drawer, let an operator reposition, resize, recolor, realign,
restack, and show or hide each of fifteen spectator-board widgets through
numeric controls, validated against a safe-area margin and minimum widget
size, with a live preview drawn by the same renderer as the real board.
Layouts were named, saved locally in `layouts.json`, and could be reset to
the built-in default per-widget or entirely. There was no drag-and-drop, no
undo, no multi-select, no free text or images, no board background, no
fonts, and no presets, and rename/duplicate/delete existed on the bridge but
not in the UI — "stuck 20 years in the past," in the owner's words, which is
what prompted v2 the same day.

**What v2 adds, on the same window and the same window size (1220×780,
minimum 980×620).** A real canvas editor: pointer-driven drag/resize with
snapping and guides (carried over from the interim drag-enabled build),
multi-select and group-drag, undo/redo over the last 100 drafts, up to 24
free `text`/`image`/`box` elements layered with the widgets, a board
background color, ten selectable system fonts plus letter-spacing/
transform/shadow/outline text effects, fill/border/corner-radius/padding for
any widget or element, four built-in presets (Classic, Broadcast bar, Big
score, Tigers navy), and full library management (rename, duplicate, delete,
reset-to-built-in) from inline popovers rather than browser dialogs. Schema
version moved from 1 to 2; a v1-saved layout is accepted and silently
upgraded with one warning rather than rejected. See `docs/UX_AND_LAYOUT.md`
§10 for the complete workflow.

**What v2 deliberately does not do.** OBS, media playback, animations,
sponsor rotation, video, networking, cloud storage of a layout (images
included — every image is embedded as a local `data:` URI, capped at 2 MB per
image and 6 MB total per layout), physical controllers, a way to bind a free
text element's wording to a game field, SVG images (an SVG can carry a
script), a font that is not already installed on Windows, editing the
operator panel's own layout, or a different hand-tuned layout per screen
resolution. The pregame/halftime event countdown board keeps its existing
markup and styling and is **not editable in v2**.

**What this does not touch.** Phase 2 acceptance, Task 12 (sustained
rehearsal), and every piece of hardware/stadium evidence this backlog and the
roadmap track are unaffected — the editor changes only spectator-board
presentation and cannot reach `scoreboard.db`, the action history, or the
state revision; the bridge's public surface is unchanged in shape (still no
`command()` method and no method named after any game command) and grew only
by the `rename_layout`/`duplicate_layout` pair the UI now exposes. Phase 3's
remaining workstreams (OBS, cutscenes, media, sponsor content, team
themes/logos) also remain deferred; only the presentation-layout-editor line
item of that list moved, and only because the owner asked for it ahead of the
rest of Phase 3.

**Verification.** Focused suites: schema 95, persistence+bridge 58, renderer
contract, and editor contract 25 all pass. The editor was driven in the
preview browser against a stub bridge (boot, select, add text/image/box, drag
with snapping, history back/forward, presets with inline confirm, library
menu, context menu, multi-select, zoom) and in the real pywebview/WebView2
runtime via `WindowHost` (editor opened, text and box elements added, history
stepped, board background set, `Save` wrote a schema-2 `layouts.json`, and the
practice spectator window received the push with elements, background, and
text). Full discovery run after v2 (September 5, 2026, `SCOREBOARD_DATA_DIR` isolated): **703 tests, 16 failures, 3 errors** — the same inventory as the pre-v2 baseline; the one new failure the run surfaced (`test_the_build_script_requires_every_view_file`, because the editor gained three script files) was fixed by adding them to `tools/build_package.py` before this was recorded. Not verified at the time: the
`tests/ui/` Playwright browser suites (no Node.js on this machine), any
hardware/LED/two-display evidence, and WebView2 file-picker behavior for the
Image button on the operator laptop. **Update, September 6, 2026:** Node.js and a repo-local Playwright are now installed, and the `tests/ui/` suites ran for the first time against this editor — see the Improvements table (I1/I2) and the "Automated suite failure inventory" resolution in `../PROJECT_ROADMAP.md` for the two real defects (a spectator name-overflow and a layers-rail click-loss bug) that run found and fixed. The current full discovered suite is green: 853 tests, 0 failures, 0 errors, 3 skipped. Hardware/LED/two-display evidence and the WebView2 file-picker check remain open.

### Presentation layout editor v3 — pre-game and halftime screens — ✅ delivered September 6, 2026

Implements the owner's request that the pregame and halftime presentation
(the `KICKOFF IN…` / `UNTIL SECOND HALF…` countdown board, previously fixed
markup untouched by the editor) become customizable "just like the
scoreboard," against the design spec at
`.scratch/presentation-screens/spec.md`. Five Sonnet agents built this in
parallel against disjoint file ownership (schema, renderer, editor, bridge,
docs); the orchestrator then integrated and verified it the same day (focused
suites, the full discovery run against the known baseline, and a real
pywebview run) — evidence under "Phase 2 owner request 4 — pre-game and
halftime screens" in `PROJECT_ROADMAP.md`.

**What changed.** `LAYOUT_SCHEMA_VERSION` moves from 2 to 3. One stored
layout document now describes three screens: the in-game screen keeps its
v2 shape at the document's top level (unchanged, so every v1/v2 layout and
test keeps working), and two new screens, `screens.pregame` and
`screens.halftime`, are each a complete mini-document with their own safe
area, background, widgets, and elements — but built from a different,
smaller widget registry of eight **event widgets** (home/away team name and
score, phase label, countdown title, countdown, warmup line) rather than the
current seventeen game widget slots. The last two carry F3's crowd status
message and its countdown, and are empty (and therefore hidden) until an
operator raises one. A v1 or v2 file upgrades on read with the existing
`SCHEMA_UPGRADED` warning; a v3 file missing `screens` fills both from
default with `MISSING_SCREENS`. The editor gains a Game / Pre-game /
Halftime toolbar switcher (`Ctrl+1/2/3`), a per-screen presets gallery (four
each for pre-game and halftime, alongside the four existing game-screen
presets, which no longer touch the other two screens), and issue messages
that name the screen they belong to. Every v1/v2 safety property is
unchanged: still no path to a game command, still no state-revision advance,
still nothing written to `scoreboard.db`, still gated on Python validation
before `Save`. See `docs/UX_AND_LAYOUT.md` §10.9 and `docs/ARCHITECTURE.md`
§9 for the full behavior and schema description.

**What this does not touch.** Task 12, the Phase 0 HDMI gate, and every
piece of hardware/stadium evidence remain unaffected. A fourth screen beyond
Game/Pre-game/Halftime, binding free text to a game field, SVG images, a
per-resolution layout, and editing the operator panel's own layout all
remain out of scope, exactly as they were for v1/v2.

**Verification.** Focused schema/editor/renderer/bridge suites, the full
discovery run, the preview-browser stub, and a real pywebview/WebView2
development-host run were completed and are recorded in `PROJECT_ROADMAP.md`.
This remains development evidence, not hardware or stadium acceptance.

## Field Assistant — delivered for rehearsal, September 5, 2026

Implements the Field Assistant request recorded as "Owner-requested next
scoreboard work" item 4 in `PROJECT_ROADMAP.md`, against the design in
[`../docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`](../docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md),
whose status line now reads implemented (with one recorded amendment) rather
than "proposed design."

**What it does.** A separate, optional, similarly sized helper window
(1180×720, minimum 1024×600), opened deliberately from the operator toolbar,
proposes and finalizes ordinary end-of-play field-status updates —
scrimmage plays, incomplete passes, penalty ±5/±10/±15 shortcuts with their
down consequences, explicit turnovers, and touchdown/try/field-goal/safety/
kickoff transitions — through one validated, undoable composite command
(`finalize_field_action`). It never starts, stops, or reads clock controls,
and it never replaces the existing manual Field Status drawer, which remains
the fallback for anything the helper does not cover.

**Automated coverage.** `tests/unit/test_field_assistant.py` (the pure FA-01
through FA-18 rule matrix, including the corrected per-team direction),
additions to `tests/unit/test_commands.py` and `tests/unit/test_state.py`
(composite command, undo, clock isolation, additive state, old-snapshot
recovery), `tests/integration/test_bridge.py::FieldAssistantBridgeTests`
(read-only preview, stale-draft refusal, unchanged manual controls),
`tests/integration/test_field_assistant_rehearsal.py` (atomicity, undo,
recovery, a simulated persistence failure, and a multi-quarter rehearsal),
and `tests/integration/test_field_assistant_window.py` (host window
lifecycle against pywebview-shaped fakes).

**"Delivered for rehearsal," not stadium-ready.** Native pywebview/WebView2
rendering and the full helper flow were exercised on the development host.
No physical target-laptop 1366×768-at-100%/125% check and no live operator
rehearsal have been performed (`docs/UX_AND_LAYOUT.md` §11.5). This work
does not advance Task 12, the Phase 0 HDMI gate, or any other
stadium-readiness item above.

**Backlog candidates carried forward as manual-only exclusions**, matching
`docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` section 7:

- OT direction, once local overtime rules are confirmed.
- Onside kicks, blocked kicks, and defensive try/kick returns.
- Offsetting or multiple penalties, and enforcement from a spot other than
  the proposed one.
- Automatic possession flips inferred from a score, a safety, or ball
  position alone.
- Any clock interaction from within the helper.
