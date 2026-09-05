# High School Football LED Scoreboard — Project Roadmap

> **Document purpose:** This is the living command-center document for the scoreboard project. It records the current plan, phase status, major decisions, unanswered questions, and the next concrete action.
>
> **Last updated:** September 4, 2026

## How to Use This Document

| Practice | Meaning |
|---|---|
| Update after meaningful work | Record completed tests, decisions, newly discovered constraints, and phase changes. |
| Separate facts from assumptions | A likely answer is not treated as confirmed until it has been tested or documented. |
| Keep near-term work detailed | The current and next phase should be specific. Later phases should stay flexible until earlier findings justify more detail. |
| Require a definition of done | A phase is complete only when its stated exit criteria have been met. |
| Prefer small experiments | Use inexpensive tests to answer uncertain architectural questions before committing to large implementations. |

## Status Key

| Status | Meaning |
|---|---|
| ✅ Complete | Finished and verified. |
| 🟡 In progress | Active work is underway. |
| ⏳ Pending | Planned but not started. |
| 🧪 Needs testing | Believed to be true but requires evidence. |
| ⛔ Blocked | Cannot continue until a dependency or decision is resolved. |
| ➖ Deferred | Intentionally postponed to protect the MVP scope. |

## Project North Star

Build a reliable, offline-capable, and extremely easy-to-operate football scoreboard and LED video-production system for a high-school stadium.

The system may eventually support sophisticated graphics, videos, sponsor content, replays, multiple operators, and the existing physical controller. The first priority is much smaller: prove that a dependable custom scoreboard can be displayed through the stadium's existing HDMI-to-LED signal chain.

**Guiding principle:** Reuse what already works. Build only what differentiates our system.

## Project Guardrails

| Guardrail | Practical effect |
|---|---|
| Reliability over features | A smaller system that survives an entire game is more valuable than an impressive but fragile system. |
| Offline core operation | Scoring and clocks must not depend on internet access or cloud services. |
| Preserve the vendor system | Do not modify, remove, bypass, or interfere with the licensed vendor system or USB key. Keep it available as a fallback. |
| HDMI is the preferred boundary | Treat the LED processor and wall as an existing display system unless testing proves that direct hardware integration is required. |
| Separate responsibilities | Keep game state, game rules, presentation, operator controls, media production, and hardware integrations logically separate. |
| Limit the MVP | Do not add replays, advanced statistics, networking, physical-controller support, or elaborate media tools before the core scoreboard is proven. |
| Correctness over visual polish | Clock and score behavior must be trustworthy before advanced animations or styling. |
| Human-friendly operation | Controls must be clear enough for a student or volunteer to use during a live game. |

## Current Understanding

| Type | Item | Status / Confidence |
|---|---|---|
| Known | The current vendor system uses a Windows 11 laptop and sends video to a processor through HDMI. | Confirmed |
| Known | The processor has four HDMI inputs and physical input-selection controls. | Confirmed by observation; model still unknown |
| Known | Two RJ45-style cables leave the processor, and disconnecting either one blanks one half of the LED wall. | Confirmed by experiment |
| Known | The existing physical scoreboard controller connects to the vendor computer through USB. | Confirmed |
| Known | The local project is initialized as a Git repository on `main`; the target GitHub repository advertised no branches or commits when inspected. | Confirmed September 4, 2026; initial commit/push tracked below |
| Hypothesis | A normal Windows laptop can drive the entire LED wall through an available HDMI input. | Approximately 90% confidence; not yet tested |
| Hypothesis | The LED wall can be treated as one conventional display target, allowing the internal LED protocol to remain irrelevant. | Depends on the HDMI test |
| Decision | Use one authoritative Python process with managed HTML/CSS/JavaScript operator and spectator webview windows for Phase 2. | Documented in `docs/ARCHITECTURE.md`; Windows host proof is Task 1 |
| Undecided | OBS Studio should be part of the system. | Evaluate after the core scoreboard works |
| Deferred | Existing physical-controller integration | Not part of the initial MVP |

## Phase Overview

| Phase | Name | Primary outcome | Current status |
|---:|---|---|---|
| 0 | Discovery and feasibility | Validate the project boundary and document the existing system. | 🟡 Substantially complete; one critical HDMI test remains |
| 1 | Repository, requirements, and architecture | Establish a clean project foundation and an implementation-ready MVP design. | 🟡 In progress; repository/docs are established, owner confirmations and layout agreement remain |
| 2 | Core scoreboard MVP | Produce a dependable local Windows scoreboard with correct football controls and fullscreen output. | 🟡 In progress; Task 1 host proof is implemented, with normal two-display manual evidence pending |
| 3 | Production graphics and OBS/media integration | Add controlled media, scenes, custom cutscenes, and polished presentation without compromising the core scoreboard. | ➖ Deferred |
| 4 | External controls and expanded operation | Investigate and integrate the physical controller and other operator-control options. | ➖ Deferred |
| 5 | Stadium production hardening | Validate full-game reliability, recovery, deployment, operating procedures, and fallback behavior. | ➖ Deferred |

### Phase 2 Task 3 evidence

- Added a monotonic-deadline game-clock engine in [`src/scoreboard/domain/clocks.py`](src/scoreboard/domain/clocks.py) and kept the clock state immutable and revision-safe using the existing `GameState`/`ClockValue` contract.
- Verified with `.\.venv\Scripts\python.exe -m unittest tests.unit.test_game_clock -v` and `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`.

### Phase 2 Task 4 evidence

- Added an independent, monotonic-deadline `PlayClock` engine in [`src/scoreboard/domain/clocks.py`](src/scoreboard/domain/clocks.py) with 25/40-second presets loaded while stopped, explicit start/stop/clear/reset/correct/expire commands, and the same immutable, revision-safe `ClockValue` contract as the game clock. No `GameState`/`ClockValue` fields changed; `PlayClock` carries its own engine-only `preset_seconds` so `reset` can restore the last-loaded preset without touching persisted state.
- Added `clear_play_clock_on_game_clock_start`, a small pure function taking the game clock's prior running state as a boolean, so the documented stopped-to-running coupling is expressed without the play clock re-implementing or depending on `GameClock` internals.
- Verified with `.\.venv\Scripts\python.exe -m unittest tests.unit.test_play_clock -v` (20 tests) and `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` (43 tests, 0 failures).

### Phase 2 Task 5 evidence

- Added pure command, result, event-intent, and shape-validation types in [`src/scoreboard/domain/commands.py`](src/scoreboard/domain/commands.py), and the serialized `ScoreboardService` in [`src/scoreboard/application/service.py`](src/scoreboard/application/service.py). The service owns the current immutable `GameState` plus its `GameClock`/`PlayClock` engines, replaces them on each accepted command, and is the only writer of the authoritative revision.
- `submit()` is one plain synchronous entry point: commands apply in submission order, exactly one revision per accepted command, one complete snapshot plus one event intent returned (command type, team/field, old value, new value). Nothing is written anywhere; persistence and the durable action history remain Task 6. A reentrant `submit()` raises, so serialization cannot be bypassed silently.
- Rejections return a stable code plus a plain-language message and leave state, revision, and both engines untouched: below-zero corrections, scores above 199, invalid quarter labels, invalid team names, invalid direct-set targets, invalid clock corrections and presets, stale revisions, and undo of a dangerous command. Expected validation failures are never raised past the service boundary.
- Undo is a command like any other and appends a new forward transition rather than deleting history or rolling the revision backwards. `New Game`, `End Game`, an already-committed confirmed quarter change, and Undo itself are not undoable; the declared eligibility sets, not individual handlers, have the final say.
- Quarter changes are manual and limited to `QUARTER_LABELS`, with forward/back/direct selection. While both clocks are stopped they apply immediately. While either clock is running, the first call reports `CONFIRMATION_REQUIRED` and stops nothing; a second confirmed call stops both clocks and changes the quarter in one committed transition. `New Game` uses the same explicit two-step shape and produces a clean stopped `default_state()`-equivalent at a fresh forward revision. `End Game` stops both clocks and sets `FINAL` without erasing names, scores, or the quarter.
- No clock math is re-implemented. Clock commands call the existing `GameClock`/`PlayClock` methods, and the service applies `clear_play_clock_on_game_clock_start` because it is the first component that knows whether a Start was a real stopped-to-running transition. The service never reads wall-clock time; one injected monotonic source is shared with both engines.
- Verified with `.\.venv\Scripts\python.exe -m unittest tests.unit.test_commands -v` (45 tests) and `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` (88 tests, 0 failures). `py_compile`, `compileall`, and `pip check` also passed.

### Phase 2 Task 6 prerequisite — display formatter

Task 6's "checkpoint once per displayed second" policy and every Task 7 readout depend on F-039/F-047 rounding, and no module implemented it. It was therefore built first rather than deferred.

- Added [`src/scoreboard/domain/formatting.py`](src/scoreboard/domain/formatting.py): a pure derived view that never changes stored time. All rounding runs through one `ceil_tenths` primitive that folds away binary floating-point noise before rounding up, because `4.9 * 10` is `49.000000000000007` and would otherwise round to a wrong `5`.
- Game clock shows whole seconds while its rounded-tenths value is at least 60.0, then tenths; play clock shows whole seconds until that value is below 5.0, then tenths; event countdowns are always rounded-up `M:SS`.
- `displayed_second()` is the single checkpoint-cadence key shared by persistence and the operator readout, so a saved value and a displayed value can never disagree about which second is showing.
- Verified at every documented boundary with exact literals: game clock 60.0→`1:00`, 59.99→`1:00`, 59.9→`59.9`, 12:25.1→`12:26`; play clock 5.0→`5`, 4.99→`5`, 4.9→`4.9`, 4.01→`4.1`; event countdown 15:00, 3:01, 3:00, 0:00. Two exhaustive sweeps also assert that the display never understates remaining time (0.00–60.00 in hundredths) and that no exact tenth from 0.0 to 720.0 rounds up twice. `tests.unit.test_formatting` passed 13/13.

### Phase 2 Task 8 prerequisite — in-window recovery evidence

- Normal launches now show a separate recovery page for saved or invalid data. It identifies primary/backup source and checkpoint, previews the saved game, resumes stopped, and confirms Start new game. Closing without choosing starts no service or session.
- `StartupBridge` exposes only recovery inspection/resume/new; handoff creates the normal operator with the existing `ScoreboardBridge`. Duplicate choices create one session. Non-interactive `WindowHost.run` retains `RecoveryChoiceRequired`.
- Five focused startup tests passed; full suite 250/250, `compileall`, `pip check`, and diff whitespace checks passed. Native recovery-window interaction remains a target-laptop rehearsal item.

### Phase 2 Task 7 evidence

- Added the narrow bridge in [`src/scoreboard/host/bridge.py`](src/scoreboard/host/bridge.py) with exactly `command(name, args, expected_revision)`, `get_snapshot()`, and a non-mutating `reopen_display()`. It builds a `Command`, submits it to `ScoreboardService`, persists the result through Task 6, and returns a JSON-compatible dictionary. `build_command` is an airlock: an unknown name, an argument a command does not take, a value of the wrong type, or a `NaN` from an empty field is refused before the service ever sees it.
- No domain object crosses the boundary. A walk over every command result and snapshot asserts that only `str`, `int`, `float`, `bool`, `None`, `list`, and `dict` appear, and every payload survives a `json.dumps`/`loads` round trip with `allow_nan=False`.
- Every displayed clock string is produced in Python by `domain/formatting.py`, so the operator readout, the spectator board, and the persisted checkpoint cannot disagree. The tests assert the operator script contains no `Math.floor` and no `toFixed`.
- `Command.source` is `operator-mouse`, and the durable action history records it. Task 9 will add a keyboard source reaching the same commands.
- All 25 commands have a mouse control: a contract test compares every `CommandType` against the `data-command` attributes in the operator page and fails naming any that is missing, and a second test submits every command through the bridge and asserts one accepted revision each. Asserting at the bridge boundary proves the wiring; driving a browser would only prove that one build of WebView2 dispatched a click.
- Typing changes nothing before Apply: every text field carries `data-draft="true"` and no `data-command`, the operator script registers no `input` or `change` listener, and an Apply button reads its field at click time only. Direct score entry and the clock Edit Current Time controls live in the corrections drawer; a test asserts `correct_score` and `set_score` appear only there and never in the always-visible board (F-015, F-016).
- Confirmation is carried on the command. `New Game` and a quarter change while either clock runs both return `CONFIRMATION_REQUIRED` and change nothing; cancel sends no second command; confirm resubmits the same command with `confirmed=True`. Dangerous corrections additionally confirm locally, showing old and new values before anything is sent. Cancel is the focused default.
- The health strip reports the spectator connection, the persistence status, and the authoritative revision. A simulated write failure shows `NOT SAVED` while the game keeps running and the next successful command restores `SAVED`; a closed display shows `DISPLAY CLOSED` with one-click reopen, does not stop a running clock, and a reopen that itself fails is reported without touching the game (D-005, U-005, R-002).
- `expected_revision` comes from the rendered view model, so a stale control is rejected with `STALE_REVISION` rather than applied.
- The Task 1 host now owns the game: [`host/app.py`](src/scoreboard/host/app.py) takes the single-instance lock, inspects recovery, opens one service and one store behind the bridge, and runs a four-per-second refresh loop that checkpoints and pushes view models without ever submitting a command. `ScoreboardApplication` is separated from `WindowHost` so the wiring is testable without opening a window.
- Nothing auto-resumes. When a recoverable game exists and no choice was made, `WindowHost.run` raises `RecoveryChoiceRequired` carrying the report instead of guessing; `--resume` and `--new-game` make the choice. **The in-window recovery screen is not built**: the choice currently arrives from the launch command, which satisfies P-005 but is not the workflow described in `docs/UX_AND_LAYOUT.md` section 6.7. It is recorded below as remaining work.
- Verified with `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` (245 tests, 0 failures), `compileall`, and `pip check`.

#### Task 7 manual observation — 1366x768 at 100% and 125% (U-001)

This is a manual observation, not an automated pass. It was made in the in-app Chromium browser at the equivalent CSS viewports, with the real `index.html`, `operator.css`, and `operator.js` served over `http://127.0.0.1`, rendering a real view model produced by the bridge (112-126, a 20-character away name, a running 9:30 game clock and a running 28 play clock).

| Case | CSS viewport | Result |
|---|---|---|
| 1366x768 at 100% | 1366x768 | No vertical or horizontal scrolling (`scrollHeight == clientHeight`, `scrollWidth == clientWidth`). All 24 live controls fully inside the viewport. Tool bar bottom at 760 of 768. |
| 1366x768 at 125% | 1093x614 | No vertical or horizontal scrolling. All 25 live controls fully inside the viewport and at least 32 px tall and 40 px wide. Tool bar bottom at 598 of 614. |
| Corrections drawer at 125% | 1093x614 | Opens as an overlay from 161 to 598, scrolls inside itself, and the page still does not scroll. All eight quarter buttons present. |
| Confirmation dialog at 125% | 1093x614 | `Change the HOME score?` with `HOME score 112 → 7`, Cancel focused. The board still showed 112: typing plus Apply changed nothing. Cancel left it at 112. |

The check found and fixed one real defect: the body grid assigned rows implicitly, so hiding the alert line moved every region up one row and handed the board the auto-sized row and the quarter bar the flexible one. Each region now names its own `grid-row`.

**Not claimed:** this was Chromium at an equivalent CSS viewport, not WebView2 on a physical 1366x768 Windows display at Windows scaling. The physical-display check stays a release-evidence item.

#### Task 7 host smoke check

`python -m scoreboard --display-index 0 --new-game --auto-close-after-seconds 8` exited 0. It opened the operator and fullscreen spectator windows from bundled `file://` pages under WebView2, logged `STARTUP`, `RECOVERY source=NONE`, `DISPLAY_OPENED target='Display 1'`, and `SHUTDOWN reason=clean`, wrote a valid database and backup plus `session_started`/`session_shutdown` history rows with a stopped 12:00 clock at a `SHUTDOWN` checkpoint, and left no orphan process. It ran against `SCOREBOARD_DATA_DIR` in a temporary folder, which was then removed. This host still exposes only one display, so second-display placement remains unverified.

### Phase 2 Task 7 prerequisite — event-countdown engine and commands

`GameState` carried `event_countdown` and `event_phase` with no engine or command behind them, while Task 7's boundary lists event-countdown controls. Option (a) was chosen and built before the UI, so no control is bound to a command that does not exist.

- Added `EventCountdown` to [`src/scoreboard/domain/clocks.py`](src/scoreboard/domain/clocks.py) using the same monotonic-deadline model as the game and play clocks, plus five validated commands: Select, Start, Stop, Reset, and Edit Current Time (F-027, F-028).
- `event_phase_for()` is a pure derived function reading the *displayed* second, so the label changes exactly between a shown `3:01` and a shown `3:00` while the countdown runs, without an operator command and without a new revision (F-026). `WARMUP` is not selectable: it is the second part of the same interval countdown, which continues without a reset.
- `Start after applying?` is composed in the operator view as an Edit-Current-Time command optionally followed by a Start command, rather than adding a field to the Task 5 command model. `Remain stopped` is therefore the default by construction: not issuing the second command is the default path.
- Independence is asserted in both directions: no countdown command changes the game or play clock, and a running countdown survives every game-clock, play-clock, and scoring command (F-025). `New Game` returns it to the stopped 30:00 pregame default.
- Verified with `.\.venv\Scripts\python.exe -m unittest tests.unit.test_event_countdown -v` (28 tests) and the full suite (177 tests, 0 failures).

### Phase 2 Task 6 evidence

- Added [`src/scoreboard/infrastructure/paths.py`](src/scoreboard/infrastructure/paths.py), [`persistence.py`](src/scoreboard/infrastructure/persistence.py), [`diagnostics.py`](src/scoreboard/infrastructure/diagnostics.py), and [`src/scoreboard/application/recovery.py`](src/scoreboard/application/recovery.py). Persistence observes and durably records transitions; it never produces one. `ScoreboardService` remains the only writer of the authoritative revision, and the restore path uses `dataclasses.replace` rather than `evolve` so recovering a game cannot invent a revision the service never issued.
- Runtime data resolves through the Windows platform API — `SHGetKnownFolderPath(FOLDERID_LocalAppData)` via `ctypes`, confirmed on this host as `C:\Users\<user>\AppData\Local\Scoreboard` — with an environment-variable fallback. A relative path is refused rather than resolved against the working directory. `git status --ignored --short` shows no database, backup, or log inside the repository (P-001, W-005, P-009).
- One SQLite database plus one automatically refreshed `scoreboard.backup.db`; no database server. Every accepted command writes recoverable state and its action-history row inside one `BEGIN IMMEDIATE`/`COMMIT`, with `synchronous = FULL` (P-002). The backup refreshes from the just-committed database after each command commit and at clean shutdown, never from a half-written file and never on a clock tick alone.
- While a clock runs, `GameStore.checkpoint()` stores the materialized remaining value whenever `formatting.displayed_second()` changes — measured at four samples per second in tests, it wrote exactly five times in five simulated seconds and added zero rows to the action history (P-003, F-037, F-046).
- The append-only history records wall-clock timestamp, monotonic `sequence`, command, source, team/field, old/new values, result, error code/message, state revision, and application version. Rejected operator requests are retained and, because `CommandResult.event` is `None` on rejection by design, are built from the submitted `Command` plus `CommandError.code`/`.message`: the request is recorded as the new value and the old value stays null, since nothing changed (P-007).
- Wall-clock time comes from a separately injected `wall_clock` callable used only by persistence and diagnostics. The service's monotonic source is never read for a timestamp, and the domain gained no wall-clock dependency.
- Recovery restores names, scores, quarter/phase, and each clock's most recent checkpoint with every clock stopped, then seeds the game through the existing `ScoreboardService(state=..., monotonic_clock=...)` constructor. `inspect_recovery()` and `resume_recovered_game()`/`start_new_game()` are separate functions, which makes "nothing auto-resumes" structural rather than a comment (P-004, P-005).
- A corrupt primary database is preserved as `scoreboard.invalid-<stamp>.db`, the backup is promoted in its place, and the report says `RECOVERED FROM BACKUP` visibly. If both files are unusable, neither is touched, both paths are reported, and the only offered choice is a new game (P-006).
- A write failure never claims `SAVED`: the status reports `NOT SAVED` with the underlying error, the game keeps running from memory, the unwritable history row is queued, and the next command commits it so the audit trail keeps the request that could not be written.
- `InstanceLock` takes an operating-system byte-range lock on `scoreboard.lock` (`msvcrt` on Windows, `fcntl` elsewhere). The OS releases it when the process exits, so a crash never leaves a stale lock blocking a mid-game restart, and a second instance is refused with a message naming the data folder and leaving the database intact (R-004).
- Startup, shutdown, recovery, display open/close, rejected commands, persistence failures, instance refusal, and unhandled errors go to a bounded rotating `logs/application.log` (1 MB × 5 by default), verified to rotate and stay within its cap (P-008, R-003).
- `New Game` archives the current game's log and opens a new one. The service has no game identity, so it was added at the persistence layer keyed to the `NEW_GAME` transition: the command that ends a game is written into the log it closes, so an archived history explains its own end (F-023).
- Verified with `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` (149 tests, 0 failures), `compileall`, and `pip check`. The 61 new tests all run in temporary directories with injected fake clocks: nothing sleeps, nothing reads real time, and nothing writes outside its temporary directory.

---

## Phase 0 — Discovery and Feasibility

**Goal:** Establish whether custom software can use the existing processor and LED wall as a normal HDMI display, while documenting enough of the current hardware to make safe decisions.

### Phase 0 Checklist

| Work item | Status | Evidence or next action |
|---|---|---|
| Define the project goal and reliability principles | ✅ Complete | Recorded in the project instructions and knowledge base. |
| Document the suspected signal chain | ✅ Complete | Windows computer → HDMI → processor → two RJ45-style links → LED wall. |
| Confirm that the two outbound links serve different wall sections | ✅ Complete | Disconnecting either link blanked the top or bottom half. |
| Establish the vendor system as the protected fallback | ✅ Complete | No license bypass or disruptive modification is planned. |
| Define the intentionally small MVP boundary | ✅ Complete | Basic football scoreboard, clock, play clock, quarter, team names, and local controls. |
| Identify candidate architectures and open-source starting points | ✅ Complete | Candidates recorded; Phase 1 later selected a managed-webview hybrid after review. |
| Test a personal Windows laptop through an available processor HDMI input | 🧪 Needs testing | Planned for Tuesday, September 8, 2026. |
| Confirm the entire Windows desktop appears across the LED wall | 🧪 Needs testing | This is the critical Phase 0 gate. |
| Record Windows-reported resolution, refresh rate, scaling, and orientation | 🧪 Needs testing | Capture screenshots or photographs during the HDMI test. |
| Record processor make, model, connections, and visible configuration | 🧪 Needs testing | Photograph the front, rear, labels, adapters, and connected cables. |

### Phase 0 HDMI Test — Minimum Evidence to Capture

| Check | What to record | Pass condition |
|---|---|---|
| Source detection | Whether Windows detects a second display and how it identifies it | The processor presents a usable display target |
| Full-wall image | Photograph of the Windows desktop or test image on the entire wall | Both halves display one correctly assembled image |
| Resolution | Windows display resolution and active signal resolution | A stable, usable mode is available |
| Refresh rate | Windows-reported refresh rate | Stable image without visible sync problems |
| Scaling | Windows scaling percentage | Scaling behavior is known and reproducible |
| Geometry | Cropping, stretching, seams, offset, or unused pixels | Problems are absent or can be characterized |
| Stability | Leave the desktop visible and exercise normal window movement/video briefly | No dropouts, resync loops, or obvious instability |
| Hardware identity | Processor manufacturer/model and cable/adapter photos | Enough information exists to locate manuals later |
| Recovery | Disconnect/reconnect or reselect the input if safe to do so | The source returns without complicated recovery |

### Phase 0 Definition of Done

Phase 0 is complete when the personal laptop successfully displays a stable, correctly mapped image across the entire LED wall **and** the display settings and processor identity have been recorded. If the test fails, Phase 0 remains open and the observed failure becomes the next architectural investigation.

---

## Phase 1 — Repository, Requirements, Layout, and Architecture

**Goal:** Create a clean, synchronized development foundation and define the smallest application that is ready to implement without prematurely designing the full production system.

**Important constraint:** Phase 1 produces decisions, requirements, project structure, and narrow technical proofs. It should not quietly grow into the complete scoreboard.

### 1.1 Repository Creation and GitHub Synchronization

| Work item | Expected result | Status |
|---|---|---|
| Choose the repository name | A short, durable name that is not tied to a temporary implementation choice such as OBS | ✅ `scoreboard` |
| Create a local Git repository | The working project has version history and a deliberate default branch | ✅ Initialized on `main`; Phase 1 foundation committed |
| Create the GitHub repository | Private or public visibility is explicitly selected | 🟡 Repository exists and advertised no commits; visibility still requires owner confirmation |
| Connect local and GitHub repositories | Local commits can be pushed and pulled successfully | ✅ `origin/main` pushed normally and verified from a separate clean clone |
| Add a practical `.gitignore` | Python environments, caches, logs, local settings, generated media, OBS profiles, and secrets are excluded as appropriate | ✅ Added and reviewed |
| Add a human-readable `README.md` | Purpose, current status, setup instructions, run instructions, and MVP scope are clear | ✅ Added; explicitly pre-implementation |
| Add a license or record that the repository is private/unlicensed | Reuse expectations are unambiguous | ✅ README records that no license is selected; visibility/license choice remains open |
| Establish a simple branch policy | Prefer small branches and reviewed merges; avoid unnecessary workflow complexity | ✅ Recorded in README and agent instructions |
| Verify a clean clone/setup | The project can be cloned into a new folder and prepared using documented steps | ✅ Fresh clone was clean at foundation commit `6f9fc18`; README correctly states no runtime exists yet |

### 1.2 MVP Requirements

| Requirement area | Questions to resolve in Phase 1 | Required output |
|---|---|---|
| Game clock | Starting value, count direction, start/stop behavior, editing, expiration, tenths, and quarter transitions | Written clock behavior specification |
| Play clock | 25/40-second presets, start/stop/reset behavior, visibility, expiration, and independence from game clock | Written play-clock specification |
| Scoring | Required increments, subtraction/correction, maximum display width, and accidental-input handling | Scoring rules and control list |
| Quarter | Allowed values, overtime representation, and whether changes are manual | Quarter behavior specification |
| Team identity | Editable names, abbreviations, colors, and persistence between launches | MVP team-setting requirements |
| Operator input | Mouse controls, keyboard shortcuts, focus behavior, and prevention of browser/OS shortcut conflicts | Input map |
| Display output | Fullscreen behavior, target monitor selection, aspect-ratio handling, and safe margins | Display requirements |
| Recovery | Behavior after closing, crashing, restarting, or losing the display connection | Minimum recovery requirement |
| Persistence | Which values survive restart and when state is saved | Persistence rules |
| Logging | Which operator actions and system events are recorded | Minimal event-log/logging requirement |
| Offline operation | Packages, assets, fonts, and runtime behavior without internet | Offline checklist |
| Accessibility/usability | Button size, contrast, dangerous-action treatment, and running/stopped clock indication | Operator usability checklist |

The testable baseline is now in [`docs/MVP_REQUIREMENTS.md`](docs/MVP_REQUIREMENTS.md). It includes conservative provisional defaults so implementation can proceed, while preserving owner confirmation for official clock rules, tenths, accuracy tolerance, and play-clock reset/start semantics.

### 1.3 Application Layout and Operator Workflow

| Deliverable | What it should answer | Status |
|---|---|---|
| Display-board wireframe | What spectators see and how the layout adapts to the confirmed LED resolution | ✅ Resolution-independent baseline in `docs/UX_AND_LAYOUT.md`; stadium geometry remains open |
| Operator-screen wireframe | Where primary controls live and which information is visible at a glance | ✅ Baseline in `docs/UX_AND_LAYOUT.md`; owner/operator review remains |
| Control hierarchy | Which actions are frequent, occasional, corrective, or dangerous | ✅ Documented |
| Keyboard map | Which shortcuts are fast, memorable, and unlikely to be triggered accidentally | ✅ Provisional, testable map documented; rehearsal may revise it |
| Basic game workflow | Pregame setup → kickoff → normal operation → quarter change → halftime → game end | ✅ Documented |
| Error-correction workflow | How an operator fixes an incorrect score, clock, quarter, or team setting | ✅ Undo, minus, and confirmed direct-set paths documented |
| Display-loss workflow | What the operator does if the fullscreen display closes or the HDMI signal disappears | ✅ Continue authority, alert operator, explicit reopen/reselect workflow documented |

### 1.4 Architecture Decision

| Candidate | Strengths to validate | Concerns to validate | Phase 1 decision |
|---|---|---|---|
| Python game engine + local web renderer | Clear separation, familiar tools, flexible graphics, future WebSocket/API path | Packaging, browser fullscreen behavior, clock authority, multiple-process complexity | ✅ Selected as a one-process managed-webview hybrid |
| HTML/CSS/JavaScript-only local app | Very small initial footprint and strong presentation tools | Reliable persistence, authoritative timing, packaging, future integrations | ➖ Rejected as authoritative core; web presentation retained |
| Python-native desktop/rendering | Single runtime and direct local control | Visual/media flexibility, layout effort, future OBS/browser integration | ➖ Rejected for presentation; native webview hosting retained |
| Adapt an existing open-source project | May save time and provide proven workflows | License, code quality, football completeness, maintainability, Windows support | ➖ Rejected for adoption after six-repository review; borrow concepts only |
| OBS-centered core | Mature scenes, media, and transitions | Configuration burden and unnecessary dependency for basic scoring | ➖ Deferred to Phase 3; not an MVP dependency |
| Hybrid: Python authority + managed web views | One process, testable state/clocks, flexible presentation, controlled Windows windows | pywebview/WebView2 and packaging require an early proof | ✅ Recommended for Phase 2 |

The architecture decision should explicitly identify:

| Decision area | Required answer |
|---|---|
| Authoritative state | Which component owns scores, clocks, quarter, and team settings? |
| Clock model | How is elapsed time calculated without accumulating timer drift? |
| Communication | If controls and display are separate, how do they exchange state locally? |
| Process model | How many applications/processes must an operator start? |
| Packaging | How will the system run on Windows without a developer setup? |
| Display targeting | How will the output reliably open on the correct monitor in fullscreen? |
| Persistence | Where is configuration and recoverable game state stored? |
| Failure behavior | What remains visible and recoverable when a component fails? |
| Extension boundary | How can OBS, media, or physical controls be added later without rewriting game logic? |

### 1.5 Open-Source Evaluation

Evaluate the known candidates before deciding whether to build or adapt. Research should use repository code, licenses, documentation, issues, and recent activity—not screenshots or feature claims alone.

| Evaluation criterion | Why it matters |
|---|---|
| License | Determines whether code can legally be reused or modified. |
| Recent maintenance | Reduces the risk of adopting abandoned dependencies or broken setup instructions. |
| Football rules and controls | A visually attractive overlay may not provide usable game operation. |
| Architecture | Game state and presentation should be reusable independently. |
| Windows and offline support | These are core operating requirements. |
| Clock implementation | Timing must resist drift and support reliable pause/resume/correction. |
| OBS coupling | OBS support is helpful later but should not make the core scoreboard fragile. |
| Packaging/setup | A live operator should not need a development environment. |
| Test coverage and code clarity | Codex-assisted changes still need understandable, verifiable foundations. |
| Meaningful reuse | Adopt only if it saves more effort than it creates. |

✅ Six candidate repositories were inspected at recorded commits. Findings and per-candidate recommendations are in [`docs/OPEN_SOURCE_REVIEW.md`](docs/OPEN_SOURCE_REVIEW.md). No code was copied; missing and conflicting licenses are explicitly recorded.

### 1.6 Initial Project Structure

The Phase 2 architecture is selected, but implementation modules remain uncreated until their backlog task needs them. The structure preserves these concerns:

| Concern | Responsibility |
|---|---|
| Game state | Scores, clocks, quarter, team identity, and validation |
| Game logic | Legal state transitions and football-specific behavior |
| Operator interface | Human controls and correction workflows |
| Display renderer | Spectator-facing scoreboard presentation |
| Configuration | Teams, defaults, display selection, and local settings |
| Persistence/logging | Restart recovery and a record of important actions |
| Integrations | Future OBS, media, controller, or external-device adapters |
| Tests | Clock, scoring, state transitions, persistence, and launch behavior |
| Documentation | Setup, operation, recovery, and architecture decisions |

✅ The minimal boundary directories and a dependency-directed Phase 2 tree are documented in [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md). Only useful boundary README files were created; feature modules remain for the ordered backlog.

### 1.7 Narrow Technical Proofs

Only create a technical proof when it answers a decision that documents alone cannot resolve.

| Proof | Question answered | Success condition |
|---|---|---|
| Fullscreen display proof | Can the chosen renderer open cleanly on a selected Windows display? | Repeatable fullscreen launch without browser chrome or manual rearrangement |
| Clock proof | Can the chosen timing model pause/resume accurately without cumulative drift? | Measured behavior stays within the agreed tolerance |
| Local state update proof | Can operator actions update the display immediately and predictably? | Fast, ordered, observable state changes |
| Restart proof | Can the application restore a safe state after restart? | Documented restart behavior works consistently |

### 1.8 Phase 1 Deliverables

| Deliverable | Definition | Status / evidence |
|---|---|---|
| Synchronized repository | Local and GitHub repositories are connected and a clean clone works. | ✅ `main` tracks `origin/main`; foundation commit `6f9fc18` cloned cleanly. |
| MVP requirements | Ambiguous behavior has been resolved and written down. | 🟡 Testable provisional baseline in `docs/MVP_REQUIREMENTS.md`; owner-only clock decisions remain. |
| Display and operator wireframes | Layouts are understandable before visual polish begins. | ✅ `docs/UX_AND_LAYOUT.md`; owner/operator agreement still requested before UI build. |
| Architecture decision record | Selected approach, rejected alternatives, tradeoffs, and extension boundaries are documented. | ✅ `docs/ARCHITECTURE.md`. |
| Project skeleton | Minimal structure exists for the selected architecture. | ✅ Source/test/asset boundaries exist without feature code; detailed tree in `docs/PROJECT_STRUCTURE.md`. |
| Testing strategy | Core logic, UI behavior, fullscreen output, and recovery have explicit test approaches. | ✅ Requirements, architecture, and backlog contain verification methods. |
| Phase 2 implementation backlog | Small, ordered tasks exist with acceptance criteria. | ✅ Twelve bounded tasks in `docs/PHASE_2_BACKLOG.md`. |

### Phase 1 Definition of Done

Phase 1 is complete when a fresh Windows checkout can be prepared from documented instructions; the MVP behavior and operator workflow are unambiguous; display and control layouts are agreed upon; the core architecture has been selected with written tradeoffs; and Phase 2 has a small, testable implementation backlog.

---

## Phase 2 — Core Scoreboard MVP

**Goal:** Deliver the smallest reliable local scoreboard that can be operated on Windows and displayed fullscreen on a monitor, television, and then the stadium LED wall.

| Planned capability | Current scope |
|---|---|
| Authoritative game state | Home/away scores, game clock, play clock, quarter, and team names |
| Reliable clocks | Start, stop, reset, edit/correct, and accurate elapsed-time calculation |
| Scoring controls | Required football increments plus safe correction/undo behavior |
| Operator interface | Clear mouse controls and documented keyboard shortcuts |
| Spectator display | Readable fullscreen layout designed for the confirmed wall geometry |
| Local persistence | Safe recovery of the agreed state after an interruption |
| Event logging | Important control actions and failures recorded locally |
| Offline packaging | Repeatable Windows installation and launch without internet access |
| Verification | Automated logic tests plus monitor/TV and stadium display testing |

### Phase 2 Definition of Done

The MVP can be installed and launched on the target Windows laptop, operated without development tools or internet access, run its clocks and scoring correctly, recover according to the agreed policy, and display legibly on the stadium wall during a sustained rehearsal.

---

## Phase 3 — Production Graphics, OBS, and Media

**Goal:** Add professional presentation capabilities around the proven scoreboard core.

| Possible workstream | Examples | Current status |
|---|---|---|
| OBS evaluation/integration | Browser source, scenes, transitions, hotkeys, and local WebSocket control | ➖ Deferred |
| Custom cutscenes | Touchdown, big play, defense, player introduction, and hype animations | ➖ Deferred |
| Media playback | Fullscreen videos, images, music-linked content if appropriate, and emergency stop | ➖ Deferred |
| Sponsor content | Static sponsors, scheduled rotation, and proof-of-play logging if needed | ➖ Deferred |
| Visual system | Team themes, logos, typography, safe zones, and reusable templates | ➖ Deferred |
| Source switching workflow | Scoreboard versus media/secondary HDMI source procedures | ➖ Deferred |

### Phase 3 Definition of Done

To be defined after Phase 2 field testing. At minimum, production features must fail safely without corrupting game state or preventing the basic scoreboard from operating.

---

## Phase 4 — External Controls and Expanded Operation

**Goal:** Integrate useful physical or remote controls only after the core application is stable.

| Possible workstream | Examples | Current status |
|---|---|---|
| Peripheral identification | Determine whether the vendor controller appears as HID, keyboard, serial/COM, storage, or a proprietary USB device | ➖ Deferred |
| Safe input mapping | Observe and document control events without modifying the vendor system | ➖ Deferred |
| Controller adapter | Translate supported physical inputs into the application's public control interface | ➖ Deferred |
| Multiple operators | Separate clock, scoreboard, and media responsibilities if operationally justified | ➖ Deferred |
| Additional control surfaces | Stream Deck, keypad, tablet, or dedicated button box if they improve reliability | ➖ Deferred |
| Conflict handling | Define authority when multiple controls attempt simultaneous changes | ➖ Deferred |

### Phase 4 Definition of Done

To be defined after real operators have used Phase 2 and Phase 3. External controls must remain optional: failure or disconnection of a peripheral must not prevent keyboard/mouse operation of the core scoreboard.

---

## Phase 5 — Stadium Production Hardening

**Goal:** Turn the proven system into a documented, recoverable game-day product.

| Possible workstream | Examples | Current status |
|---|---|---|
| Sustained reliability | Full simulated games, soak tests, clock accuracy, and repeated launch tests | ➖ Deferred |
| Failure recovery | App crash, HDMI loss, laptop restart, power interruption, and corrupted local settings | ➖ Deferred |
| Operator procedures | Pregame checklist, live-operation guide, troubleshooting card, and shutdown process | ➖ Deferred |
| Vendor fallback | Rehearsed input switch and clearly defined conditions for returning to the vendor system | ➖ Deferred |
| Deployment | Versioned releases, installer/update process, configuration backup, and rollback | ➖ Deferred |
| Observability | Useful logs, health indicators, and exportable diagnostic information | ➖ Deferred |
| Training | Short training session and practice game for student/volunteer operators | ➖ Deferred |
| Production readiness review | Formal go/no-go checklist before live use | ➖ Deferred |

### Phase 5 Definition of Done

To be defined from field experience. Production readiness will require successful full-game simulations, documented recovery and fallback procedures, trained operators, and a deliberate go/no-go decision by the project owner.

---

## Questions That Need Answers

Answers should be added directly to these tables. When an answer becomes an architectural decision, also record it in the Decision Log.

### Immediate / Phase 0 Questions

| Priority | Question | Current understanding | How to answer | Status |
|---:|---|---|---|---|
| Critical | Can the personal Windows laptop display across the entire LED wall through a normal HDMI input? | Approximately 90% likely | Stadium test planned for September 8, 2026 | 🧪 Needs testing |
| Critical | What resolution and refresh rate does Windows report? | Unknown | Record Windows advanced display settings | 🧪 Needs testing |
| Critical | Does the displayed image have cropping, stretching, seams, offsets, or unused areas? | Unknown | Use a full-screen alignment/test image and photograph the result | 🧪 Needs testing |
| High | What is the processor manufacturer and model? | Unknown | Photograph front, rear, and labels | 🧪 Needs testing |
| High | Does the processor reliably recover after changing or reconnecting HDMI sources? | Unknown | Test input reselection/reconnection when safe | 🧪 Needs testing |
| Medium | Where does HDMI audio go, and will this project need it? | Unknown | Inspect Windows audio devices and stadium audio routing | ⏳ Pending |

### Phase 1 Product Questions

| Priority | Question | Why it matters | Status |
|---:|---|---|---|
| Critical | Is the 25/40-second play clock required in the first implemented MVP? | Yes. Higher-priority instructions make it crucial and `docs/MVP_REQUIREMENTS.md` includes it. | ✅ Resolved |
| Critical | What are the governing game-clock, period, and overtime rules? | Standard NFHS-style football with 12-minute quarters is confirmed. Local/state exceptions and the overtime procedure remain to be confirmed before live use. | 🟡 Baseline confirmed; local exceptions pending |
| Critical | How should clock precision transition on the display? | Confirmed: all visible clock values round upward; game-clock tenths begin below a rounded 60.0 seconds and play-clock tenths below a rounded 5.0 seconds. | ✅ Resolved |
| High | How should pregame, halftime, and warmup be presented and controlled? | Confirmed: a 30:00 `KICKOFF IN` countdown; then one 15:00 `UNTIL SECOND HALF` countdown, labeled `HALFTIME` until 3:00 and `WARMUP` thereafter, with `Warmup follows: 3:00` visible during halftime. Each is manually controlled and has Start, Stop, Reset, and Edit Current Time; edits default to remaining stopped unless the operator selects Start after applying. | ✅ Resolved |
| High | Which score-correction method is required: minus buttons, direct edit, undo, or a combination? | Use one-level Undo, separate minus controls, and confirmed direct entry; every correction is logged. | ✅ Resolved for MVP baseline |
| High | What state must be restored after an application restart? | Confirmed: teams, scores, quarter/phase, and last persisted whole-second values for every clock; all clocks return stopped and the operator verifies before resuming. A durable offline action history is required. | ✅ Resolved; embedded storage format remains open |
| Medium | How should a game-clock time correction behave? | Confirmed: opening Edit Current Time stops the game clock; the confirmation validates the new value and offers `Start after applying?`, defaulting to stopped. | ✅ Resolved |
| Medium | How should a play-clock time correction behave? | Confirmed: Edit Current Time is in Corrections, stops the play clock, and offers validated `Start after applying?`, defaulting to stopped. | ✅ Resolved |
| High | Which embedded local storage format should preserve recovery state and action history? | Confirmed: one embedded SQLite database with automatic backups; no database server. | ✅ Resolved |
| High | What Windows computer will become the primary production machine? | Determines performance, outputs, packaging, and setup constraints. | ⏳ Pending |
| High | What is the intended first live-use date? | Determines how aggressively features must be limited. | ⏳ Pending |
| High | Who will operate the system, and how many operators are expected initially? | Confirmed: two people are expected. Phase 2 has one laptop operator; a second operator will use a future optional peripheral, which remains outside the MVP. | ✅ Resolved |
| Medium | Are team colors and logos required in Phase 2, or are names sufficient? | Names are sufficient for the MVP; colors/logos are explicitly deferred unless display testing reveals a basic contrast need. | ✅ Resolved for MVP scope |
| Medium | Should the spectator display and operator controls run in one application window or separate windows? | Separate managed windows in one Python process, sharing one authoritative state. | ✅ Architecture decision |
| Medium | What clock-accuracy tolerance is acceptable over a full quarter? | Provides a measurable test target. | ⏳ Pending decision |
| Medium | Does the school impose restrictions on software installation or personal laptops? | Could constrain packaging and deployment. | ⏳ Pending |
| Medium | Should the GitHub repository be private or public? | Determines repository setup and licensing needs. | ⏳ Pending decision |
| Medium | Should a 25/40 play-clock preset reset-and-start immediately or load the value while stopped? | Confirmed: load while stopped; an explicit Start command begins the countdown. | ✅ Resolved |
| High | What should happen to the play clock when the game clock starts? | Confirmed: a stopped-to-running game-clock transition stops and clears it; a Start while the game clock is already running does not affect it, so it may continue to zero. No clock expiration alerts; an expected zero remains visible until the operator clears or changes it. | ✅ Resolved |
| Medium | Which overtime labels and clock defaults apply under the school's governing rules? | Prevents the application from inventing a live overtime workflow. | ⏳ Owner/rules confirmation |
| Medium | Does the operator accept the proposed initial shortcut map? | The implementation can use it provisionally, but rehearsal may reveal ambiguous or awkward keys. | ⏳ Operator rehearsal/confirmation |

### Later-Phase Questions

| Phase | Question | Why it can wait | Status |
|---:|---|---|---|
| 3 | Does OBS materially improve the actual stadium workflow? | The core scoreboard can be proven without it. | ➖ Deferred |
| 3 | Will production media use the same laptop, a second laptop, or another HDMI input? | Requires hardware performance and operator-workflow evidence. | ➖ Deferred |
| 3 | What media formats, resolutions, frame rates, and audio routes are required? | Depends on the processor and content workflow. | ➖ Deferred |
| 3 | Who will create and approve cutscenes, logos, sponsor media, and other assets? | Content operations are unnecessary for the core MVP. | ➖ Deferred |
| 4 | How does Windows identify the existing physical controller? | Controller integration is explicitly outside the MVP. | ➖ Deferred |
| 4 | Is using the vendor controller technically and contractually permissible? | Must be answered before building an adapter. | ➖ Deferred |
| 4 | Would a simpler dedicated keypad or Stream Deck be more reliable than adapting the vendor controller? | Actual operator experience should guide the choice. | ➖ Deferred |
| 5 | What is the acceptable recovery time during a live game? | Requires real workflow and fallback testing. | ➖ Deferred |
| 5 | Who has authority to switch back to the vendor system? | Part of the eventual game-day operating procedure. | ➖ Deferred |
| 5 | What spare hardware and backup configuration will be available? | Depends on budget and production setup. | ➖ Deferred |

## Decision Log

Record decisions here so later implementation work does not silently reverse them.

| Date | Decision | Reason | Revisit when |
|---|---|---|---|
| September 4, 2026 | Task 8 gap 1: lifecycle follows accepted quarter commands (including quarter Undo): PRE → PRE_GAME, HALF → HALFTIME, FINAL → FINAL, all playing labels → IN_PROGRESS. A successful game-clock Start leaving pregame/halftime enters IN_PROGRESS; End Game sets FINAL and New Game restores PRE_GAME. HALF selects interval presentation; quarter entry aligns event phase without resetting its time. | No overlapping lifecycle control; team-name validation now leaves pregame. Expiry never advances lifecycle. | Operator rehearsal. |
| September 4, 2026 | Task 8 gap 2: publish after accepted commands under the existing serialization lock, retaining ticks for timed refresh/checkpoint work. | Removes the 250 ms scheduler wait; push-count tests prove delivery without a tick. Physical latency remains release evidence. | Target laptop measurement. |
| September 4, 2026 | Task 9 gap 3: 2/4 load stopped 25/40 presets; P starts and S stops the play clock. Space, Q/Shift+Q, ZXCV, NM comma period, Ctrl+Z and Esc retain their documented purposes. | Matches confirmed mouse/preset behavior. Requirements change precedes keyboard code. | Operator/numpad rehearsal. |
| September 4, 2026 | Task 9 gap 4: Space reads the rendered snapshot and submits existing game_clock_start or game_clock_stop. | No JavaScript running-state copy or toggle command; existing action history stays explicit. | Only if command semantics change. |
| September 4, 2026 | Task 8 gap 5: build and commit an in-window recovery prerequisite before spectator work. A separate startup API offers report/resume/new and creates the normal operator with ScoreboardBridge after choice. | Keeps command() narrow; no clock or service starts before choice. RecoveryChoiceRequired remains the non-interactive guard. | Recovery rehearsal. |

| September 4, 2026 | Keep the personal-laptop HDMI test as the final Phase 0 gate. | It validates the central assumption that the existing LED system can be treated as a normal display. | Revisit only if the test fails or reveals significant mapping problems. |
| September 4, 2026 | Treat the HDMI outcome as likely but unconfirmed. | The project owner estimates a favorable result at approximately 90% confidence, but no direct test has occurred. | Update immediately after the stadium test. |
| September 4, 2026 | Keep OBS optional until after the core scoreboard is proven. | OBS may help production features but is not required to validate scoring, clocks, or fullscreen output. | Evaluate in Phase 3 or earlier only if Phase 1 evidence justifies it. |
| September 4, 2026 | Preserve the vendor system as the fallback. | Live-game reliability requires a known working recovery path. | Do not reverse without an explicit production-readiness decision. |
| September 4, 2026 | Include the independent 25/40-second play clock in the Phase 2 MVP. | The project instructions identify it as crucial; omitting it would leave the MVP operationally incomplete. | Revisit only with explicit owner direction. |
| September 4, 2026 | Use one Python authority with separate managed HTML/CSS/JavaScript operator and spectator windows. | It is the smallest design that combines testable clock/state logic, flexible presentation, one-action startup, and Windows display control without requiring OBS or a local server. | Revisit if the Phase 2 Windows host proof or HDMI test fails materially. |
| September 4, 2026 | Use monotonic deadline-based clocks, not callback-count decrementing. | UI and scheduler delays must not accumulate clock drift. | Revisit only if tests disprove the implementation approach. |
| September 4, 2026 | Use atomic versioned JSON snapshots plus a backup and append-only JSONL event logs. | Original Phase 1 recovery baseline; superseded by the confirmed embedded SQLite decision below. | Superseded September 4, 2026. |
| September 4, 2026 | Do not adopt any of the six reviewed scoreboard repositories. | None satisfies the American-football MVP, direct fullscreen, clock/recovery, Windows, testing, and licensing needs together. | Revisit if requirements change or a better maintained/licensed candidate appears. |
| September 4, 2026 | Keep this repository unlicensed until the owner selects visibility and licensing. | The project must not imply redistribution permission without an explicit owner decision. | Revisit when repository visibility/license is decided. |
| September 4, 2026 | Use standard NFHS-style football as the Phase 2 rules baseline, with 12-minute quarters and manually selected overtime. | Provides an implementable default while preserving local/state adjustments for confirmation before live use. | Revisit when the school's governing rules or local procedure are confirmed. |
| September 4, 2026 | Include a 30:00 `KICKOFF IN` countdown and one 15:00 `UNTIL SECOND HALF` countdown, labeled `HALFTIME` until 3:00 and `WARMUP` thereafter. During halftime, show `Warmup follows: 3:00`. | One total countdown gives spectators an unambiguous time until play resumes while preserving the 12-minute halftime/three-minute warmup breakdown. | Revisit only if the event workflow changes. |
| September 4, 2026 | Round every visible clock value upward: whole seconds at normal precision and tenths in tenths mode. Game-clock tenths begin only below rounded 60.0 seconds; play-clock tenths begin only below rounded 5.0 seconds. | The board never understates remaining time; explicit thresholds prevent awkward `60.0` and `5.0` transitions. | Revisit only if local operating requirements differ. |
| September 4, 2026 | Make 25/40 play-clock presets load while stopped; require a separate Start command. Treat the spectator board as the stadium's only play-clock display. | The operator prefers deliberate starts, and play-clock visibility/recovery cannot rely on another display. | Revisit only if operator rehearsal shows the workflow is too slow. |
| September 4, 2026 | On a game-clock transition from stopped to running, stop and clear the play clock. Do not affect it when the game clock is already running; it may otherwise run to zero unless an operator changes it. | Matches the owner's snap workflow while preserving an independent play clock in running-clock situations. | Revisit if field rehearsal reveals ambiguity. |
| September 4, 2026 | Do not emit alarms or persistent alerts when a game or play clock expires. An uncleared play clock may remain visibly `0.0` when the game clock is already running. | The operator will manage clearing; passive expiration must not create a misleading warning during live play. | Revisit if operator rehearsal shows a missed-expiration risk. |
| September 4, 2026 | After interruption, recover teams, scores, quarter/phase, and every clock's last persisted whole-second value with all clocks stopped; require operator verification before use. Preserve a durable offline history of accepted and rejected operator actions. | Recovery should be fast and auditable without allowing unseen time to elapse. | Revisit only if field recovery testing exposes a practical gap. |
| September 4, 2026 | Use one embedded SQLite database with automatic backups for recoverable state and durable action history. | It provides transactional, queryable, fully offline persistence without a database server or separate installation. | Revisit only if field testing reveals a concrete reliability issue. |
| September 4, 2026 | Make pregame and interval countdowns manually controlled with Start, Stop, Reset, and Edit Current Time. An edit offers `Start after applying?`, defaulting to `Remain stopped`. | Schedule changes must never start a timer unexpectedly, while a correction can deliberately restart it in one controlled action. | Revisit if operator rehearsal identifies a faster safe workflow. |
| September 4, 2026 | Use the same deliberate edit-and-optional-restart pattern for the game clock. | It gives the operator a safe default and a fast, logged correction path when an official directs a restart. | Revisit if field rehearsal exposes an unsafe interaction. |
| September 4, 2026 | Use the same deliberate edit-and-optional-restart pattern for the play clock, with the control in Corrections. | It supports uncommon corrections without crowding the high-frequency 25/40 controls. | Revisit if field rehearsal exposes an unsafe interaction. |
| September 4, 2026 | Plan for two initial people: one Phase 2 laptop operator and one future optional-peripheral operator. | It reflects the intended game-day staffing without coupling the MVP to an unproven peripheral. | Revisit when Phase 4 peripheral work is authorized and tested. |
| September 4, 2026 | Implement F-039/F-047 display rounding as a pure `domain/formatting.py` module before Task 6, rather than inline in each consumer. | The backlog assigned it to no task, yet Task 6's checkpoint cadence and every Task 7 readout depend on it. One shared `displayed_second()` also guarantees a saved value and a displayed value agree about which second is showing. | Revisit only if a confirmed local rule changes the rounding thresholds. |
| September 4, 2026 | Build the event-countdown engine and its Start/Stop/Reset/Edit-Current-Time commands as a named prerequisite between Task 6 and Task 7, rather than deferring them to a later task. | `GameState` already carries `event_countdown` and `event_phase` with no engine or command behind them, F-025–F-028 are MUST requirements, and Task 7's boundary lists event-countdown controls. Building UI against commands that do not exist was the alternative. | Revisit only if the owner removes the pregame/halftime countdowns from the MVP. |
| September 4, 2026 | Do not restore the in-memory one-level undo entry after recovery. | The operator must verify the board against the real game before resuming (P-005). Offering one-click reversal of a command they cannot see, issued before a crash they may not have witnessed, invites a second error rather than fixing the first. The action history still records the command, so only the shortcut is lost. | Revisit if rehearsal shows operators repeatedly need to reverse the last pre-crash action. |
| September 4, 2026 | Do not persist `PlayClock.preset_seconds`; allow it to reset to blank on recovery. | It is engine-only bookkeeping and is deliberately absent from the persisted `ClockValue` contract. A recovered Reset therefore blanks the play clock rather than restoring a 25 or 40 the operator never re-selected, and reloading a preset is one click on an always-visible control. | Revisit only if a recovered game must restore the preset without an operator action. |
| September 4, 2026 | Keep the durable action history inside `scoreboard.db` rather than in a separate JSONL event log, superseding the `infrastructure/event_log.py` sketch in the structure document. | P-002 requires the new state and its history row to commit in one transaction; two files cannot guarantee that. The rotating `application.log` still records program-level diagnostics separately. | Revisit only if an external consumer needs a streaming event file. |
| September 4, 2026 | Compose `Start after applying?` in the operator view as an Edit-Current-Time command followed by an optional Start command, rather than adding a `start_after_apply` field to the command model. | It keeps the Task 5 command contract unchanged, defaults to remaining stopped by simply not issuing the second command, and records both steps in the audit trail. | Revisit if the two-revision sequence proves confusing in the history or in rehearsal. |

## Test and Evidence Log

| Date | Test or observation | Result | Evidence location | Effect on plan |
|---|---|---|---|---|
| Before September 4, 2026 | Disconnected each RJ45-style output link from the processor | Each cable appeared to serve one half of the LED wall | Project knowledge base; photographs not yet recorded here | Supports the hypothesis that the processor distributes video to wall sections; no need to inspect the protocol yet. |
| September 4, 2026 | Inspected six public candidate repositories from shallow clones | No suitable adoption base; useful architecture/timing/UX concepts recorded; two candidates lacked licenses and one had conflicting license evidence | `docs/OPEN_SOURCE_REVIEW.md` records commits and evidence | Select an independent Python-authority/managed-webview architecture and copy no candidate code. |
| September 4, 2026 | Inspected target GitHub repository with `git ls-remote --symref` | No advertised branches or commits; repository appears empty from Git | Command output in Phase 1 session | Safe to establish `main` without integrating remote history; visibility remains unknown. |
| September 4, 2026 | Pushed Phase 1 foundation and cloned `origin/main` into a separate temporary folder | Clean clone checked out `6f9fc18` on `main` with no modifications | Git output in Phase 1 session | Repository synchronization and clean-clone deliverable verified. |
| September 4, 2026 | Phase 2 Task 1 runtime proof on this Windows host | CPython 3.11.11, `pywebview==6.2.1`, and WebView2 `152.0.4191.62` installed/verified. Four focused display/lifecycle tests, editable install, compilation, and dependency check passed. The host opened operator plus explicitly selected fullscreen spectator windows on the one available `5120x1440` display and auto-closed cleanly with no remaining proof/Python process. An unavailable selection returned `DISPLAY NOT FOUND: Display 100`. The runtime launch completed with the normal sandbox network restriction active and made no package/service request. | `docs/PHASE_2_TASK_1_RUNTIME_PROOF.md`; `docs/ARCHITECTURE.md` §10; command output from this session | The selected second-display and manual close/reopen/fullscreen checks remain pending because this host exposes only one display. No fallback host is warranted yet. |
| September 4, 2026 | Follow-up Task 1 executable smoke checks | `scoreboard-proof.exe --display-index 0 --auto-close-after-seconds 5` and the same command with `--display-index 99` both exited with code 0; post-run checks found no remaining `scoreboard-proof`, `python`, or `pythonw` process. `pip check` and `compileall` also passed. The host still reported one connected `5120x1440` display. | PowerShell command output from this session | Clean shutdown and missing-index launch are locally reproducible. The two-display manual checklist, visible invalid-display confirmation, manual spectator close/reopen, fullscreen toggle, and offline repeat remain unverified. |
| September 4, 2026 | Phase 2 Task 2 authoritative state and snapshot tests | Added frozen, validated state/value models for teams, scores, quarter, lifecycle, game/play/event countdown values, and event phase. Added detached JSON-compatible snapshots with schema/app metadata and monotonic revisions. Focused state tests plus the existing display tests passed: 12 tests, 0 failures. | `src/scoreboard/domain/state.py`; `src/scoreboard/application/snapshots.py`; `tests/unit/test_state.py`; `python -m unittest discover -s tests -v` | Task 2 state/snapshot acceptance criteria are met. Timing engines, commands, persistence, and UI remain outside this task. |
| September 4, 2026 | Phase 2 Task 4 play-clock engine tests | Added the `PlayClock` engine covering stopped/default blank behavior, 25/40 preset loads, start/stop idempotence, fake-time advancement, callback stalls, sub-second pause/resume, clear, reset-to-preset, valid/invalid corrections, expiration at and beyond zero, wall-clock independence, rejected-operation state/revision stability, and the documented stopped-to-running game-clock coupling. `tests.unit.test_play_clock` passed 20/20; the full suite passed 43/43. | `src/scoreboard/domain/clocks.py`; `tests/unit/test_play_clock.py`; command output from this session | Task 4 play-clock acceptance criteria are met. Command service, persistence, SQLite, UI, and later tasks remain out of scope. |
| September 4, 2026 | Phase 2 Task 5 command-service tests | Added `domain/commands.py` and the serialized `application/service.py`. Table-driven tests cover one revision plus one complete snapshot and event intent per accepted command across all 20 command types; unchanged state/revision/engines for 20 rejection cases; every `+1/+2/+3/+6` and `-1/-2/-3/-6` for both teams; direct set with old/new reporting at 0, 99, 100, and 199; undo of a score and a quarter as a forward transition, and rejected undo of `New Game`, `End Game`, a confirmed quarter change, and Undo itself; immediate quarter change while stopped versus the two-step confirmation while a clock runs; confirmed `New Game` producing an independent fresh state; `End Game` stopping both clocks and preserving names/scores; clock commands matching direct engine results under a fake monotonic clock; the stopped-to-running play-clock coupling and its no-op on a redundant Start; and deterministic repeated/rapid submission. `tests.unit.test_commands` passed 45/45; the full suite passed 88/88. `py_compile`, `compileall`, and `pip check` passed. | `src/scoreboard/domain/commands.py`; `src/scoreboard/application/service.py`; `tests/unit/test_commands.py`; command output from this session | Task 5 acceptance criteria are met. Persistence, SQLite, the durable action history, UI, OBS, controllers, networking, and pregame/interval countdown commands remain out of scope and belong to Task 6 and later. |
| September 4, 2026 | Phase 2 Task 6 prerequisite: display-formatter boundary tests | Added `domain/formatting.py` and asserted every documented F-039/F-047/F-026 boundary with exact literals, plus two exhaustive sweeps proving the display never understates remaining time and that no exact tenth rounds up twice. `tests.unit.test_formatting` passed 13/13. | `src/scoreboard/domain/formatting.py`; `tests/unit/test_formatting.py`; command output from this session | The rounding gap the backlog left unassigned is closed. Persistence and every Task 7 readout now share one `displayed_second()` definition. |
| September 4, 2026 | Phase 2 Task 6 persistence, recovery, and logging tests | 61 new temporary-directory tests with injected fake wall and monotonic clocks, no sleeping and no writes outside the temporary directory. Covered: state and history committing in one transaction; an interrupted commit leaving the previous coherent state and a valid backup; a write failure reporting `NOT SAVED` and replaying its queued history row on the next command; corrupt primary promoting the preserved backup visibly; corrupt primary and backup recovering nothing and leaving both files byte-identical; corrupt primary with no backup inventing nothing; running-clock checkpoints staying within one displayed second at four samples per second while adding zero history rows, and writing exactly five times in five simulated seconds; action-history order and every required field for accepted, rejected, and confirmation-prompt requests; `New Game` archiving the closed log and opening a new game identity; second-instance refusal leaving the database intact and the lock reusable after release; formerly running clocks recovering stopped with the undo entry and play-clock preset deliberately absent; all nine required diagnostic events and bounded log rotation. `tests.unit.test_formatting` 13/13, `tests.integration.test_persistence` 25/25, `tests.integration.test_recovery` 16/16, `tests.integration.test_diagnostics` 7/7; full suite 149/149. `compileall` and `pip check` passed, and `git status --ignored --short` showed no runtime database, backup, or log inside the repository. | `src/scoreboard/infrastructure/`; `src/scoreboard/application/recovery.py`; `tests/integration/`; command output from this session | Task 6 acceptance criteria are met. UI, bridge, HTML, keyboard, OBS, networking, and spectator work remain out of scope. Forced-process-termination and full-disk behavior on real hardware remain release-evidence items: the simulated failures prove the code paths, not the operating system's behavior under a real power loss. |
| September 4, 2026 | Phase 2 Task 7 operator interface and bridge | 68 new tests. Bridge contract: all 25 commands reachable by mouse and asserted against the operator page's `data-command` attributes; every command accepted through the bridge with one revision each; unknown names, wrong argument names, wrong types, `NaN`, and bad expected revisions refused before the service; JSON-only payloads for every command result and snapshot with no domain object anywhere; the spectator bridge exposing only `get_snapshot`. Behaviour: typing without Apply changing nothing and no `input`/`change` listener existing; local confirmation showing old and new values; `New Game` and a running-clock quarter change asking first, cancel doing nothing, confirm resubmitting with `confirmed=True`; rejections surfacing a plain-language message with the board unchanged; stale revisions refused; a simulated write failure showing `NOT SAVED` while play continues and recovering to `SAVED`; simulated display close/reopen updating the health strip without stopping a clock; a failing reopen and a failing spectator push both survived by the engine. Host: one service and store behind the bridge, a second instance refused, a recoverable game reported but never started, resume restoring 11:40 stopped, ticks publishing to both windows without advancing a revision, and shutdown saving and releasing the lock. Full suite 245/245; `compileall` and `pip check` passed. | `src/scoreboard/host/bridge.py`; `src/scoreboard/host/app.py`; `src/scoreboard/views/`; `tests/integration/test_bridge.py`; `tests/integration/test_host_application.py` | Task 7 acceptance criteria are met at the bridge boundary. Keyboard shortcuts, spectator layout, display-selection hardening, packaging, OBS, and networking remain out of scope. The in-window recovery screen and the physical 1366x768 WebView2 display check remain open. |
| September 4, 2026 | Task 8 recovery prerequisite | Five focused tests; full suite 250/250; compileall, pip check, diff checks passed. | `tests/integration/test_startup.py`; prerequisite evidence above | Native recovery interaction remains release evidence. |
| Planned September 8, 2026 | Personal Windows laptop → HDMI processor input → full LED wall | Pending | Add photographs, screenshots, and notes | Determines whether Phase 0 can close and confirms the preferred system boundary. |

## Current Status

| Item | Current state |
|---|---|
| Active phase | Phase 2 Task 7 operator-interface foundation implemented; Phase 0 hardware gate remains open in parallel |
| Open phase gate | Personal laptop HDMI test on the complete LED wall |
| Confidence in preferred outcome | Approximately 90%, still unverified |
| Implementation status | Tasks 1–7: the one-process pywebview host now owns the game, its SQLite storage, and both windows behind a narrow `command`/`get_snapshot` bridge, on top of the immutable state/snapshot layer, the game, play, and event-countdown engines, the serialized command service, the pure display formatter, and atomic persistence with backup, recovery, the durable action history, the single-instance lock, and bounded diagnostics. The operator view implements the documented live controls, health strip, last action, corrections drawer, countdown controls, and confirmations. The spectator page is still the minimum needed to prove the bridge. Keyboard shortcuts, spectator layout, display-selection hardening, packaging, OBS, server, and peripheral code have not begun. |
| Repository status | `main` tracks `origin/main`; Phase 1 foundation commit `6f9fc18` pushed and independently cloned cleanly |

## Next Action

Recovery prerequisite is verified; next implement Task 8: the spectator-display foundation, rendering the minimum spectator state and its pregame/interval countdown presentation responsively from complete snapshots. Separately, on Tuesday, September 8, 2026, perform the personal-laptop HDMI test and capture the minimum Phase 0 evidence.

Carried forward as open items, none of which may be treated as completed on the strength of a passing automated suite:

1. **Recovery rehearsal.** The in-window choice is implemented and tested at the host boundary; native interaction on the target laptop remains release evidence.
2. **The physical 1366×768 check.** The layout was measured in Chromium at the equivalent CSS viewports, not on a 1366×768 Windows display at 100% and 125% scaling under WebView2.
3. **Two-display behaviour.** This host exposes one display, so second-display placement, manual spectator close/reopen, and fullscreen exit/re-entry remain unverified. Task 10 owns the production work.
4. **Real operating-system failure behaviour.** Interrupted transactions, write failures, and forced termination are proven as code paths against simulated failures; a real power loss or full disk on the target laptop is release evidence.
