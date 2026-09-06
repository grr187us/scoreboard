# High School Football LED Scoreboard — Project Roadmap

> **Document purpose:** This is the living command-center document for the scoreboard project. It records the current plan, phase status, major decisions, unanswered questions, and the next concrete action.
>
> **Last updated:** September 6, 2026

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
| 2 | Core scoreboard MVP | Produce a dependable local Windows scoreboard with correct football controls and fullscreen output. | 🟡 In progress; Tasks 1-11 implemented and locally verified, audited September 5, 2026. Task 12, the two-display checklist, and all hardware/release evidence remain. |
| 3 | Production graphics and OBS/media integration | Add controlled media, scenes, custom cutscenes, and polished presentation without compromising the core scoreboard. | ➖ Deferred |
| 4 | External controls and expanded operation | Investigate and integrate the physical controller and other operator-control options. | ➖ Deferred |
| 5 | Stadium production hardening | Validate full-game reliability, recovery, deployment, operating procedures, and fallback behavior. | ➖ Deferred |

### Phase 2 Task 10 evidence — display selection, fullscreen, and failure recovery

The last implementation task in Phase 2. It replaces the Task 1 proof's fixed `--display-index` with a remembered display, an explicit selector, and disconnect reporting.

**The identity is a device name plus geometry, never a list position.** An index is the least durable thing Windows offers: unplug a cable and index 1 is a different monitor, or the operator's own screen. The preference lives in the `display` section of [`config.json`](src/scoreboard/infrastructure/config.py) — the first use of the file the architecture reserved in Phase 1 — and is recognised in three tiers, each of which the operator is shown by name:

| Tier | What changed | What it looks like in the stadium |
|---|---|---|
| `exact` | Nothing | A normal restart |
| `name` | Size, position, or scaling | The processor renegotiated HDMI and came back at another resolution |
| `geometry` | The device name | Windows renumbered the displays after a replug |

**There is deliberately no fourth tier.** An unmatched preference reports `DISPLAY NOT FOUND`, opens nothing, and asks the operator. A fullscreen board landing on top of the controls twenty minutes before kickoff is the one outcome worth refusing outright (D-002), so the fallback that would have caused it does not exist. With nothing ever saved, the default is the first *non-primary* display; on a one-display machine that is deliberately no answer at all, and the operator can still choose that screen on purpose.

**`--display-index` now defaults to the saved display rather than `1`.** A technician can still force an index from a terminal, and doing so does not overwrite what is saved. Only an operator choosing a display in the panel re-points the preference; recognising the saved display refreshes its stored geometry, so a resolution change is recorded without the preference ever becoming a *different* monitor.

**Disconnects are reported, never acted on.** The host samples the display list about twice a second — Windows offers no event pywebview passes on, so noticing an unplugged wall means asking — and if the display the board is on has gone, the health strip says so and says what is still true: the game is running and still saving. When it comes back, the strip says that too and stops there. Reopening is the operator's decision (D-006, and the Task 10 boundary against hidden auto-moves). If the display list cannot be read at all, the check switches itself off for the session and logs why, rather than filling a game's log with the same failure; the manual panel still reads live.

**Nothing here can touch the game.** Selecting, reopening, losing, and forgetting a display are host actions on the `reopen_display()` model: no revision, no database write, no action-history row. Tests assert a running clock is still running and showing the right time after each one.

**The health strip now distinguishes two states**, because one is fixed by a click and the other is not: `DISPLAY CLOSED` (the window went, the display is still there — one click) and `DISPLAY NOT FOUND` (the display went, or none was chosen). `Reopen Display` stays in the strip and stays one click; when it cannot resolve a display it opens no window and shows the panel instead. The panel itself lives in the corrections drawer beside **Saved to**, for the same layout reason: the drawer overlays and scrolls inside itself, so nothing added there can push a live control off a 1366x768 screen.

- 73 tests cover the policy: 32 pure ones in [`tests/test_displays.py`](tests/test_displays.py) and 41 host-level ones in [`tests/integration/test_display_selection.py`](tests/integration/test_display_selection.py). The screen list, the device names, and `webview.create_window` are all injected, so a second monitor is plugged in by appending to a list and unplugged by removing from it. That is the only way any of this is reachable on this host.
- Three of them were confirmed to bite by deliberately breaking the code they cover: disabling disconnect detection failed two disconnect tests, and adding a primary-display fallback failed the missing-display test. Two tests that passed under mutation were strengthened rather than kept.
- The layout was re-measured in Chromium at both U-001 viewports with the strip in its **widest** state (`DISPLAY NOT FOUND` plus a visible `Reopen Display`, longest chip text throughout). At 1366x768 nothing scrolls, no live control leaves the viewport, and the strip ends at 1347 of 1366. At 1093x614 (125%) nothing scrolls, the drawer overlays 58-598 and scrolls inside itself, and the page does not.
- That measurement found one real defect and one it could not fix. `Reopen Display` was 28 px tall — under the 32 px the Task 7 note recorded for every live control, and far under the documented 44x44 target. It is now 32 px, which is the most the strip can hold without pushing a live control off 1366x768. **Reaching 44 px needs the operator layout re-flowed**, and that belongs with the Settings-surface revisit already recorded in `docs/UX_AND_LAYOUT.md`, not with this task.
- The operator JavaScript was exercised in a real browser engine against a stub bridge, because Node.js is not installed here and the `tests/ui/` browser tests therefore cannot run: the panel rendered, a display row sent the right key, **Forget saved display** reported plainly without disturbing the open board, and a reopen that could not resolve a display opened the panel instead of a window.
- **The package was rebuilt**, which was the outstanding consequence of building Task 11 out of order. 152 files, 27.4 MB, 0.1.0. The rebuilt build was then confirmed to carry the new behaviour and not the old: with nothing saved it opened no window and logged the plain-language reason; with a display saved it logged `DISPLAY_SELECTED ... how=exact` and opened on it; with a corrupt `config.json` it started normally as though nothing were saved. Details in [Packaging](docs/PACKAGING.md).

**Not claimed.** This host exposes one display (5120x1440), so **no acceptance criterion that needs a second monitor has been observed on hardware**. Real placement, fullscreen on a second screen, an actual HDMI unplug and replug, Windows re-enumeration timing, resolution and scaling changes, and every stadium behaviour are untested. What is established is that the *policy* is right and that nothing about a display can reach the game. The rest is [the two-display checklist](docs/DISPLAY_CHECKLIST.md), which is written and entirely unticked. A passing suite must not be read as a display ever having been placed on a second monitor.

Two further gaps worth naming. The periodic check calls `WinForms.Screen.AllScreens` from the refresh worker thread; that is believed safe and is fully exception-isolated, but it has only ever run against one display on this machine. And the two-second cadence was chosen by reasoning about cost, not measured against how long Windows actually takes to re-enumerate after an HDMI event — the checklist asks for that number.

### Operator-chosen data folder

Requested directly by the owner: a folder picker so an operator can decide where the game and its logs are written, instead of accepting a path buried several folders deep in `%LOCALAPPDATA%`.

- Added [`host/folders.py`](src/scoreboard/host/folders.py), a native Windows folder dialog with two paths and no new dependency: the window's own dialog through pywebview when the operator clicks the control inside the running application, and a WinForms dialog on a dedicated single-threaded-apartment thread when there is no window at all. Both libraries are already pinned and already ship in the package.
- Reachable three ways: **Corrections → Saved to → Choose folder…** in the operator window, `--choose-data-folder` from a terminal or a second shortcut, and **Use standard folder** to undo the choice. The control sits inside the drawer, which overlays and scrolls inside itself, so no always-visible control moved and the U-001 measurement is untouched.
- **The choice takes effect at the next launch, not immediately.** The database connection, the instance lock, and the log handler are all open on the current folder while a game is running; relocating them under a live game is a far larger and riskier operation than this feature, and not one an operator should be able to trigger mid-quarter by accident. Every message says so.
- The pointer lives in `data-location.json` in the *platform default* root, never in the folder it names, because a pointer stored inside the folder it points at could never be found again. Resolution order is now: explicit override, then `SCOREBOARD_DATA_DIR`, then the chosen folder, then the platform default. The environment variable outranks the operator's choice deliberately, so a rehearsal can never write into the real game folder.
- A stale choice never stops the scoreboard. A pointer that is missing, corrupt, relative, or names a folder that is no longer reachable — the USB stick is not plugged in tonight — falls back to the standard location and starts normally. Reading a choice creates no directory: resolving a path must not have side effects.
- Like `reopen_display()`, the bridge methods are host actions rather than game commands: they advance no revision, write nothing to the database, and are asserted not to disturb a running clock. A dialog that cannot open, a folder that cannot be written to, and a cancel are all reported in plain language rather than raised, because this is a button an operator may press during a game.
- 29 tests in [`tests/integration/test_data_folder.py`](tests/integration/test_data_folder.py) cover the pointer, the resolution order, five kinds of stale or malformed pointer, validation, all four picker outcomes, the bridge's no-game-state guarantee, and the operator control's placement. The dialog is injected throughout; a test that opened a real folder dialog would wait for a person forever.
- The dialog itself was confirmed to open for real from `--choose-data-folder`, and cancelling it wrote nothing.

**Not claimed.** The dialog has been opened but never driven to a completed selection by hand, and no game has yet been run from a relocated folder. Both belong in the target-laptop rehearsal.

### Phase 2 Task 11 evidence — Windows packaging and one-action launch

Built **out of backlog order**: Task 11 lists Tasks 1-10 as dependencies, and Task 10 is not started. The reason is practical — Task 10 needs a two-display machine this development host does not have, while Task 11 needs neither. The consequence is recorded rather than hidden: **this package carries the Task 1-era display behaviour**, a fixed `--display-index` with no persisted display identity and no disconnect handling. It must be rebuilt after Task 10 before any release.

- One-folder PyInstaller build (W-003) driven by [`tools/build_package.py`](tools/build_package.py) against [`tools/scoreboard.spec`](tools/scoreboard.spec). 152 files, 27.3 MB. The build script verifies rather than trusts: every page, stylesheet, and script present and non-empty; no bundled page referencing a remote resource; and the frozen executable running `--check` end to end and reporting the expected version.
- **A packaging defect was found and fixed in the process.** The package-data declaration listed only `views/**/*.html`, so a non-editable install shipped the pages without their stylesheets or scripts — a blank LED wall that no test would have caught, because every test until now ran from a source checkout. A wheel now contains all eleven view files, and a test asserts every view file matches a declared pattern.
- The application version moved off the `0.0.0` placeholder to **0.1.0**, with one definition in `domain/state.py`. The packaging metadata reads it through `dynamic = ["version"]`, and the spec parses it for the executable's Windows version resource, so a build cannot be stamped with a version the running code does not report (W-006). `Scoreboard.exe` Properties shows FileVersion and ProductVersion 0.1.0, and the diagnostics log records `STARTUP app_version=0.1.0`. This bump is only safe because of the recovery fix recorded above.
- The build is windowed, so there is no console (W-004). Added [`host/preflight.py`](src/scoreboard/host/preflight.py): a WebView2 runtime check and a `report()` that prints in a checkout and opens a message box in a packaged build. **Verified against the real frozen build** — launching a second copy while the lock was held produced a message box titled `Scoreboard is already running` rather than a silent exit. A scoreboard that does nothing when double-clicked is indistinguishable from a broken shortcut.
- `--check` reports the application version, the WebView2 version, and the data folder, and writes the same report to `logs/readiness.txt`. It deliberately opens no dialog: a readiness check is run from a terminal and from the build script, and a modal dialog hangs both. That was found the hard way — the first implementation showed a dialog and blocked the build script's own verification. `--show` adds the dialog for a double-clickable shortcut.
- **W-005 verified by experiment.** A game was seeded into the packaged data folder, the entire application folder was deleted and rebuilt, and the new build recovered the same game — Tigers 7, Eagles 3, second quarter, `game_id` 1 — with its action history continuing in one log. Replacing the application mid-season does not touch a game.
- A packaged launch against an isolated data folder opened the operator and fullscreen spectator windows, logged `STARTUP`/`RECOVERY`/`DISPLAY_OPENED`/`SHUTDOWN reason=clean`, exited 0, and left no orphan process.
- Fourteen tests in [`tests/integration/test_packaging.py`](tests/integration/test_packaging.py) hold the contracts that only break at build time: package data covers every view file, the frozen build resolves its pages under `sys._MEIPASS`, the version has one source, and a missing WebView2 runtime produces a message naming the remedy.
- Build steps, tested versions, install instructions, exit codes, and the SmartScreen behaviour of an unsigned executable are in [Packaging](docs/PACKAGING.md).

**Not claimed.** Everything in this task was done on the development host. The clean-machine launch with no Python or Node, the network-disabled run (R-001), the real absence of WebView2, SmartScreen behaviour under school machine policy, startup time on the target laptop, and second-display placement are all still open, and are listed as a checklist in `docs/PACKAGING.md`.

### Phase 2 audit — September 5, 2026

A full read of the implemented code against `docs/MVP_REQUIREMENTS.md`, `docs/PHASE_2_BACKLOG.md`, and this roadmap. The purpose was to find where the working documents and the working software had drifted apart before Task 10 begins.

**What held up.** Every acceptance criterion in backlog Tasks 1-9 is met by code, and the layer boundaries the architecture asks for are intact: the service is still the only writer of the authoritative revision, no clock arithmetic exists outside `domain/`, every displayed clock string is produced in Python, and no domain object crosses the bridge. `docs/PROJECT_STRUCTURE.md` still describes the tree that exists.

**Two requirement-level defects, both fixed.** Each sat *between* two tasks, which is why nine rounds of task-by-task verification missed them.

1. **Clock expiration was never recorded** (F-037, F-046). The engines have `expire()` and it is unit tested, but nothing in the service, bridge, or host ever called it, and no `CommandType` covers it. A clock that ran itself to 0:00 left a start in the durable history and then silence, so an audit after a disputed end-of-quarter could not show when the clock reached zero. Fixed below.
2. **The application version was a hard compatibility gate on saved games** (P-004, P-006, W-006). `GameState` refused any snapshot whose `app_version` was not exactly the running build's. Confirmed by experiment: with the stored version at `0.0.0` and the running build moved to `0.1.0`, `inspect_recovery` reported `UNRECOVERABLE` on both the primary database and its backup. Task 11 packaging necessarily moves the version off `0.0.0`, so installing an update between two launches would have destroyed the recoverability of a game in progress — the exact moment recovery matters most. Fixed below.

**Documentation drift corrected.** `README.md` still said "No working scoreboard application exists in this repository yet" and "Phase 2 — core MVP: not started", and `src/scoreboard/README.md` said no application code existed. Both are rewritten. The launch and test commands in `README.md` are now the real ones.

**Open questions raised by the audit, not defects.** Recorded here so they reach the owner rather than being settled silently in code:

| # | Question | Why it matters | Status |
|---:|---|---|---|
| A-1 | Should a game-clock Start always blank the play clock? | F-048 assumes the game clock starts at the snap. Under NFHS-style rules the game clock also starts on the ready-for-play — after an out-of-bounds play or a penalty — with the play clock already running to the snap. In those situations the current rule blanks the stadium's only play-clock display and the operator must reload a preset. | 🧪 Needs owner/officials confirmation before live use |
| A-2 | Is 15:00 the correct total interval? | The modelled interval is 15:00 total, split `HALFTIME` 15:00-3:01 and `WARMUP` 3:00-0:00. NFHS-style practice is commonly a 15-minute intermission *followed by* a 3-minute warmup, which is 18:00 total. The split is a documented owner decision; the arithmetic should be confirmed against local practice. | 🧪 Needs owner confirmation |
| A-3 | Is a single 12:00 quarter length enough? | `MAX_GAME_CLOCK_SECONDS` is simultaneously the reset default, the correction ceiling, and a state invariant. A shorter JV quarter or a different overtime clock would require a code change, not a setting. | ➖ Deferred; revisit if a second quarter length is ever needed |
| A-4 | The play-clock preset is not persisted. | `preset_seconds` is engine-only, so after a recovery the play clock's RESET blanks the board instead of restoring 25 or 40 until a preset is pressed again. Documented, and pressing `25`/`40` is normal per-snap operation anyway. | ➖ Accepted; note in the operator guide |
| A-5 | Bridge-level rejections are not in the durable history. | An unknown command name or a malformed argument is refused before the service sees it and reaches only the rotating diagnostic log, not the action history. Defensible for a name that is not a command; a malformed argument from a real control is closer to a rejected operator request under P-007. | ➖ Accepted for the MVP; revisit if a rejection is ever missing during rehearsal |

### Phase 2 defect fix — clock expiration is recorded (F-037, F-046)

- The refresh tick now notices a clock that counted itself to zero and writes one `game_clock_expired` / `play_clock_expired` / `event_countdown_expired` row with source `system`, its old running value, and the zero it reached. The zero state and its history row commit in one transaction, exactly like an accepted command.
- Nothing about the command model changed. No revision is advanced, no `CommandType` was added, and the refresh loop still never submits a command: expiration is something a clock did, not a mutation an operator requested.
- The state revision is the discriminator that keeps it honest. If the revision moved since the previous tick, an accepted command produced the zero — a correction to 0:00, or a game-clock Start blanking a running play clock under F-048 — and that command already has its own row, so no expiration is invented. Only an unchanged revision means the clock got there on its own.
- Seven focused tests in [`tests/integration/test_bridge.py`](tests/integration/test_bridge.py) cover expiry recorded exactly once for the game and play clocks, the revision left alone, and the three non-expiry cases: a clock stopped short of zero, a play clock cleared by a game-clock Start, and a running clock corrected to 0:00.

### Phase 2 defect fix — complete tenths cadence and game-stop play-clock clear (F-052)

- The host refresh cadence is now 100 ms, so the existing correct formatter can deliver every game-clock tenth instead of skipping values between 250 ms updates. Checkpoints remain keyed to displayed seconds, so the faster refresh does not add state writes or history noise.
- A real game-clock Stop clears a running play clock in the same accepted command. A redundant Stop while the game clock was already stopped deliberately leaves an independently running play clock alone.
- Natural game-clock expiry is observed under the existing bridge command lock. The service commits the play-clock clear into its engine and the persisted `play_clock_cleared` state without advancing the game revision, so later ticks cannot continue the old play-clock deadline. The durable history writes `game_clock_expired` and `play_clock_cleared_on_game_clock_stop` together with source `system`; it does not mislabel the clear as a play-clock expiry.
- Focused fake-time unit/integration coverage verifies the explicit Stop, the no-op Stop, the blank state on the first expiry tick, persistence/history attribution, no revision advance, and continued blank state on later ticks. `\.venv\Scripts\python.exe -m unittest discover -s tests -q` passed **392 tests** with `SCOREBOARD_DATA_DIR` set process-locally to the platform default, isolating the test run from the operator's saved data-folder choice; `compileall`, `pip check`, and `git diff --check` also passed.

### Phase 2 defect fix — a saved game survives an application update (P-004, P-006)

- `app_version` is now provenance, not a compatibility gate: only `schema_version` decides whether a stored game can be read. Gating on the build number made every saved game unrecoverable the moment the version changed.
- The saving version is reported rather than discarded. `RecoveryReport` carries `written_by_app_version`, the recovery message names both versions when they differ ("saved by version X ... opened by version Y; check the board before resuming"), and the resumed game runs stamped with the current build, which is the version now responsible for it.
- Four tests in [`tests/integration/test_recovery.py`](tests/integration/test_recovery.py) rewrite a stored snapshot as an older build would have written it and assert the game is still offered with its names, scores, quarter, and stopped clocks; that the saving version reaches the report and its JSON payload; that the resumed service runs under the current build; and that a matching version reports no upgrade. The unit test that previously asserted the unsafe behaviour now asserts the safe one.

### Phase 2 verification — whole-game rehearsal under fake time (R-006 partial)

- Added [`tests/integration/test_full_game_rehearsal.py`](tests/integration/test_full_game_rehearsal.py): one complete game through the real bridge, service, store, and recovery path. Pregame 30:00 countdown run to expiry; four quarters of 30 snaps each, every snap loading a 40-second preset, starting the play clock, snapping (game-clock Start blanks it), running the game clock and stopping it; scoring across both teams; a mis-click and its Undo; the halftime countdown driven across the 3:01/3:00 `HALFTIME`→`WARMUP` boundary; a crash with both clocks running in the third quarter followed by inspection and resume; a post-whistle correction; End Game.
- It asserts what a scorer would check afterwards: final scores match the arithmetic of every increment, correction, and undo; the game clock consumed exactly the simulated playing time across the crash; lifecycle is `FINAL` with both clocks stopped; no clock left its 0-to-maximum range; persistence reported `SAVED` after every command; the recovered board was no more than one displayed second behind and never ahead; the action-history sequence is strictly increasing and gap-free; and every command class the game used, plus `session_resumed` and the countdown expiry, appears in the history.
- It is also a persistence soak by construction: several thousand refresh ticks and their checkpoints, which is why it takes roughly 30 seconds. It is **not** the Task 12 acceptance run. Nothing here measures real elapsed time, WebView2, display behaviour, or the target laptop.

### Phase 2 verification — real-time clock measurement on the development host (R-005 partial)

Every clock test until now used an injected fake clock, which proves the arithmetic but never lets a real second pass. This is a first real-time reading, on this development host only.

| Measurement | Result | Tolerance |
|---|---|---|
| Worst absolute error over a continuous 12:00 run, sampled 2,875 times | 0.0129 s | 0.25 s |
| Absolute error at the end of the 12:00 run | 0.000179 s | 0.25 s |
| Cumulative drift across 401 stop/start cycles | 0.0060 s | 0.25 s |

The worst-case figure is dominated by the gap between reading the reference and reading the engine inside one sample, not by drift: the final error after twelve continuous minutes is under a fifth of a millisecond, and 401 pause/resume cycles accumulated six milliseconds. That is the expected shape for a monotonic-deadline clock and confirms there is no per-tick or per-pause accumulation.

**Not claimed.** This is `time.monotonic` measured against `time.perf_counter` on a development machine with no window open. R-005 asks for the target laptop, under the real refresh loop, a real WebView2 window, and an independent reference. That measurement stays open.

### Phase 2 owner request 1 — human-readable local time

Implements item 1 of "Owner-requested next scoreboard work" below.

- Added [`infrastructure/local_time.py`](src/scoreboard/infrastructure/local_time.py): a pure `format_local_timestamp()` converting a stored UTC ISO 8601 timestamp (or `datetime`) into Eastern local time, e.g. `September 5, 2026 at 10:41 AM EDT`. One IANA zone name (`America/New_York`) is the whole daylight-saving policy; there is no separate EDT/EST branch anywhere in the codebase.
- **Windows does not ship the IANA time zone database**, so Python's `zoneinfo.ZoneInfo("America/New_York")` raised `ZoneInfoNotFoundError` on this development host until `tzdata==2026.3` was added as a pinned runtime dependency in `pyproject.toml`. This is an offline-operation requirement (R-001, W-006): the scoreboard must not depend on Windows or the network to resolve a time zone, and PyInstaller bundles pure-Python packages, so no packaging change is needed beyond the dependency pin.
- `application/recovery.py`'s `RecoveryReport` gained `checkpoint_at_local` alongside the existing `checkpoint_at`. The primary- and backup-source recovery messages, the in-window recovery screen (`views/startup/startup.js`), and the non-interactive `--resume`/`--new-game` CLI fallback in `__main__.py` all now show the local-time string; `checkpoint_at` itself, the SQLite `wall_clock` columns, and the diagnostics log keep their unambiguous UTC ISO values unchanged, exactly as requested.
- A malformed or unparsable timestamp is returned unchanged rather than raising, and `None` stays `None`: a broken timestamp must not blank the rest of the recovery screen, on the same "an optional failure must not stop core operation" principle R-002 applies to the spectator window.
- Verified with 11 focused tests in [`tests/unit/test_local_time.py`](tests/unit/test_local_time.py) — summer/winter offsets, the 2026 spring-forward and fall-back transition instants either side of the skipped/repeated local hour, midnight/noon, microseconds, a naive `datetime` treated as UTC, and unparsable/empty/`None` input — plus an integration test in `tests/integration/test_recovery.py` asserting the recovery report, its `to_dict()` JSON payload, and its message text all carry the same converted string.

### Phase 2 owner request 2 — expanded football state and controls

Implements item 2 of "Owner-requested next scoreboard work" below, and closes the "Deferred scoreboard fields" entry in `docs/PHASE_2_BACKLOG.md`.

- Added six new authoritative `GameState` fields, all optional/independent and untouched by any existing command: `down` (1-4 or `None`), `distance` (0-99, where `0` means goal-to-go, or `None`), `possession` (`"home"`/`"away"`/`None`), `ball_on` (a new `BallSpot` value), `home_timeouts`/`away_timeouts` (0-3, default 3). None of them are derived automatically — a change of possession does not reset down/distance, and a quarter change does not touch any of them — because inventing that coupling was not requested and the project guardrails ask for an explicit decision before automating a football rule.
- **Field position is one compound value, `BallSpot(team, yard_line)`,** on the same immutable-dataclass pattern `ClockValue` already uses, rather than two separate state fields. `yard_line` (0-50) is always counted from `team`'s own goal line, the way officials and broadcasts say it ("the Eagles' 35"), so no absolute end-to-end field scale had to be invented. Keeping it one field means the generic single-field Undo machinery reverses it correctly as a unit (side and yard line can never end up mismatched after an Undo).
- Seven new validated commands in `domain/commands.py` — `set_down`, `set_distance`, `set_possession`, `set_ball_on`, `timeout_used`, `timeout_correct`, `set_timeouts` — each with its own shape validation, service-level range/state checks (`TIMEOUT_BELOW_ZERO`/`TIMEOUT_ABOVE_MAXIMUM` mirror the existing score-correction pattern), and factory helper. All seven are reversible through the current bounded Undo stack.
- **Persistence is additive with no schema-version bump.** `application/snapshots.py` nests the new fields under one `"football"` snapshot key; a snapshot written before this change has no such key at all, and `snapshot_to_state()` falls back to the same defaults `default_state()` carries, so an older saved game stays recoverable (P-004, P-006) exactly like the `play_clock_cleared` precedent it follows.
- **A real defect was found and fixed during testing.** Undo's generic old/new reporting (`getattr(state, entry.field)`) read the raw `BallSpot` domain object directly into the returned `EventIntent` for an undone `set_ball_on`, which would have violated "no domain object crosses the bridge" (ARCHITECTURE.md §8) and made that one command's result payload fail `json.dumps`. Fixed by converting a `BallSpot` value to its plain `{"team": ..., "yard_line": ...}` dictionary wherever Undo's generic path reports it (`application/service.py`), and by teaching `infrastructure/persistence.py`'s history-row JSON encoder to convert any dataclass generically (`dataclasses.asdict`) rather than falling back to a Python `repr()` string. A regression test for each layer (`tests/integration/test_bridge.py`, `tests/integration/test_persistence.py`) exercises exactly this path: `set_ball_on` twice, then Undo.
- Operator UI: the quarter bar gained a compact, always-visible field-status readout (down & distance, field position, timeouts) next to the existing quarter control, and a new **Field ▸** drawer alongside the existing Corrections/Halftime/Advanced drawers holds the setting controls — direct-select down buttons, a distance entry with a Goal shortcut, a possession toggle, a ball-on side toggle plus yard-line entry, and per-team timeout controls. A short text flag (`◀ BALL` / `BALL ▶`), not color alone, marks which team has possession next to its name (U-002's principle). None of these controls require confirmation, matching the owner's existing "routine, reversible actions don't need a confirmation dialog" guidance recorded in `docs/PHASE_2_BACKLOG.md`.
- Spectator UI: down-and-distance and ball-on are rendered as a second, smaller line nested inside the existing quarter and play-clock grid cells, and the possession flag is nested inside the existing team-name element. Nothing was added as a new top-level grid item and no row proportion changed, so the Task 7/8 `U-001`/viewport work this project already verified is not disturbed. Timeouts remaining is exposed in the view model but is not yet drawn on the spectator board (recorded as an open item below).
- Every string an operator or spectator sees is produced in Python (`domain/formatting.py`'s new `format_down_and_distance()` and `format_ball_on()`), on the same "JavaScript never derives a displayed value" principle the clocks already follow.
- **Manually verified in the in-app Chromium browser** against a stub bridge (this development host still has no Node/Playwright, so `tests/ui/` cannot run — the same limitation recorded throughout Phase 2): the operator page at 1366×768 and at 1093×614 (125% scaling) shows no scrolling and the same toolbar-bottom pixel positions the Task 7 U-001 measurement recorded; the Field drawer opens and its down/distance/possession/ball-on/timeout controls round-trip through the (stub) bridge and re-render correctly, including the side-toggle-plus-yard-line compound entry; the spectator page renders down-and-distance, field position, and possession correctly at 1366×768 including under extreme content (24-character names, scores at 199, `4th & Goal`) with no overlap and no scrolling.
- 46 new automated tests: `tests/unit/test_state.py` (`BallSpot` validation, new field validation, snapshot round-trip and pre-expansion backward compatibility), `tests/unit/test_commands.py` (shape validation, and a new `FootballStateTests` class covering undo, clearing, quarter/new-game interaction, and timeout boundaries), `tests/unit/test_formatting.py` (`format_down_and_distance`/`format_ball_on` boundaries), `tests/integration/test_bridge.py` (view-model rendering, the JSON-safety regression above, and the existing generic per-`CommandType` contract tests extended to cover all seven new commands), and `tests/integration/test_persistence.py` (the compound-field Undo history regression). The full suite was run before and after this work; the failing/erroring set is byte-for-byte identical (the same 16 failures and 2 errors, all pre-existing legacy pregame/quarter-confirmation and Node-unavailable issues already recorded elsewhere in this document), so nothing here introduced a regression.

**Owner/officials decisions still open, not blocking implementation:**

| # | Question | Why it matters | Status |
|---:|---|---|---|
| B-1 | Is 3 timeouts per team the right default, and should it auto-reset at halftime? | NFHS-style rules award 3 timeouts per team **per half**. This build starts both teams at 3 and never resets them automatically; the operator must use the Field drawer's direct Set control at halftime. | 🧪 Needs owner/officials confirmation before live use |
| B-2 | Should a change of possession clear or prompt for new down/distance? | Currently fully independent by design (no invented automation); a real change of possession almost always means "1st & 10" for the new team, which today needs two extra operator actions. | ➖ Accepted for the MVP; revisit if rehearsal shows it is error-prone |
| B-3 | Is "yards from the named team's own goal line" (e.g. "Eagles 35") the field-position convention this stadium's staff expect, versus an OWN/OPP-relative convention? | Changes only the display and the Field-drawer side toggle's meaning, not the stored value. | 🧪 Needs owner confirmation |
| B-4 | Should timeouts remaining appear on the spectator board? | Currently operator-only; the spectator board already shows down/distance/ball-on/possession. | ➖ Deferred; add if requested |

**Not claimed.** Native WebView2 rendering of the new controls, real Windows keyboard/touch interaction with the Field drawer, and a two-hour rehearsal exercising the new fields are all still open, on the same basis as every other Task 7-10 UI claim in this document.

### Phase 2 owner request 3 — presentation layout editor

Implements item 3 of "Owner-requested next scoreboard work" below, delivered
after items 1 and 2 (local time, expanded football state), and closes
discovery issue 05 in `.scratch/testing-followups/issues/`. This is
spectator-presentation work only: it changes nothing about Phase 2 acceptance,
Task 12, the Phase 0 HDMI gate, or any hardware/stadium evidence, all of which
remain exactly where they were before this request.

- **What it is.** A new `presentation.layout` module defines a versioned,
  pure (no I/O) schema for fifteen spectator-board widgets — every property a
  widget carries (position, size, font scale, color, text/vertical alignment,
  font weight, visibility, stacking order), the safe-area policy, and strict
  validation with no silent repair. `infrastructure.layouts` persists named
  layouts to a new `layouts.json`, and `host.layout_bridge.PresentationLayouts`
  reads/validates/stores/publishes them as a host concern: saving, loading,
  selecting, deleting, or resetting a layout advances no state revision,
  submits no `Command`, writes no action-history row, and never touches
  `scoreboard.db` or its backup. A new editor window, opened from the
  operator's Advanced drawer (**Presentation layout…**), lets an operator
  edit a layout through numeric fields against a live preview built from the
  same renderer (`views/shared/board.js`) as the real spectator board; there
  is no dragging. `docs/UX_AND_LAYOUT.md` §10 has the full operator-facing
  description.
- **The spectator board is now widget-rendered.** `views/shared/board.js`
  replaces the previous fixed CSS grid with fifteen individually positioned
  widgets, driven by the same layout document the editor produces. The
  pregame/halftime event-countdown presentation keeps its existing markup and
  CSS untouched and is **not editable in v1** — a documented, deliberate
  limitation, not an oversight.
- **Coordinates are normalized and canvas-relative**, not pixels: `x`/`y`/
  `width`/`height` are fractions (0.0-1.0) of the logical 16:9 canvas, and
  `font_scale` is a fraction of canvas *width* specifically, matching the
  existing `calc(var(--canvas-width) * .12)` convention so current type sizes
  carry over exactly. See the Decision Log for why.
- **Possession moved from an inline mark beside the team name (owner request
  2) to its own widget**, centered between the two names. Its text is still
  produced in Python; only its placement changed.
- **The default layout reproduces today's board exactly.** `game_clock_label`,
  `home_timeouts`, and `away_timeouts` are positionable widgets that ship
  **hidden by default**, because the current spectator board draws none of
  them; an operator turns them on as a deliberate presentation choice, which
  answers requirement D-001's default field inventory the same way as before
  and does **not** resolve owner decision B-4 (whether timeouts should appear
  on the spectator board), which remains open.
- **Validation is strict, with a two-tier fallback.** A value out of range, an
  invalid color, a widget outside the safe area, a widget below the minimum
  size, or a serious overlap between two *visible* widgets is an error and the
  whole layout is rejected — never partially applied or silently clamped. A
  stored layout that fails to load falls back to the last known valid layout,
  and if none exists, to the built-in default; a malformed `layouts.json`
  never prevents the scoreboard from launching. Overlap is checked only among
  visible widgets, because a hidden widget cannot visually collide, which is
  why `game_clock_label`/`home_timeouts`/`away_timeouts` may sit in otherwise
  occupied space while hidden.
- **`layouts.json` is a separate file from `config.json` and
  `scoreboard.db`.** A damaged layout library must not be able to cost the
  operator a saved game, and vice versa; it follows the same atomic
  temp-file-plus-`os.replace` write and the same "a preference file may never
  stop the scoreboard" contract as `config.py`. See `docs/ARCHITECTURE.md` §9.
- **No drag-and-drop or drag-resize in v1.** Every geometry property is a
  numeric field with a documented minimum/maximum from `limits()`. This
  answers discovery issue 05's level-2 recommendation (named-slot editing
  within constrained zones) with numeric constrained editing rather than a
  pointer-drag interaction; the issue file records why.
- **No mutating game method exists on the editor's bridge.** The editor can
  read a live read-only snapshot and validate/preview/save/select/delete/reset
  a layout; it has no `command()` method and cannot reach a score, clock,
  quarter, or any other game value.
- Automated verification: **100 focused Python tests pass** — `tests/unit/test_layout_schema.py` (42), `tests/integration/test_layout_persistence.py` (18), `tests/integration/test_layout_bridge.py` (18), `tests/integration/test_spectator_layout_render.py` (8), and `tests/integration/test_layout_editor_contract.py` (14). The three browser checks that complete the picture — `tests/ui/test_spectator_browser.py` (2) and `tests/ui/test_layout_editor_browser.py` (1) — passed when they were written on a host with Node.js and Playwright, and **error rather than skip on a host without that tooling**, which is the state of this machine; they are not currently reproducible here and must not be counted as passing without a run that says so. The full discovered suite ran **597 tests with 15 failures and 3 errors**, every one of which reproduces the pre-existing baseline in "Automated suite failure inventory" below; **no failure is a regression from this work**. The browser viewport check that previously failed (`outside safe area: play`) now passes. `compileall`, `pip check`, and `git diff --check` all passed.

**Not claimed.** No hardware, two-display, LED-wall, or WebView2 rendering of
the editor or the widgetized board has been observed; every claim above is a
source-level and (where noted) browser-automation claim on this development
host, on the same basis as every other Phase 2 UI claim in this document.
Stadium safe margins, brightness, and readability at the real viewing
distance remain items to revisit after the HDMI test
(`docs/UX_AND_LAYOUT.md` §9), unaffected by this work. Task 12, the Phase 0
HDMI gate, and the two-display checklist are untouched and unadvanced by this
request.

### Phase 2 owner request 3 — presentation layout editor v2

The v1 editor above was safe but, in the owner's words, "stuck 20 years in
the past": a ~600 px preview in a 1220 px window, fifteen buttons and
0-to-1 fraction number boxes, no undo, no multi-select, no alignment tools,
no free text, no images, no shapes, no board background, no fonts, no
presets, and no way to rename, duplicate, or delete a stored layout from the
UI even though the bridge could already do it. Rebuilt the same day, against
the design spec at `.scratch/layout-editor-v2/spec.md`, by four agents
working in parallel against disjoint file ownership (schema, renderer,
editor, bridge), with a fifth agent reviewing the combined diff and writing
this and the surrounding documentation. Every v1 safety property is
unchanged: the editor still has no path to a game command, still advances no
state revision, still writes nothing to `scoreboard.db`, and `Save` is still
gated on Python's validation of the whole draft.

- **Schema v2** (`src/scoreboard/presentation/layout.py`). `LAYOUT_SCHEMA_VERSION`
  is now 2. A document whose `schema_version` is 1 is accepted and upgraded in
  place — every new property filled from its default, one warning
  (`SCHEMA_UPGRADED`) rather than an error — so every layout saved by v1
  keeps opening; any other version is still a hard `SCHEMA_VERSION` error. New:
  a top-level `background` color; an `elements` list (`text`/`image`/`box`,
  up to `MAX_ELEMENTS = 24`) with its own id, geometry, stacking order, and
  (for `text`) the full style set widgets now also carry — font family (a
  fixed ten-entry Windows-system-font table), letter spacing, text
  transform, a shadow/outline effect, background fill and opacity, border
  color/width, corner radius, and padding. An `image` element's `src` is a
  `data:` URI whose decoded bytes are magic-byte-checked and capped at 2 MB
  per image and 6 MB total per layout. Elements are excluded from
  widget-overlap validation by design; only `text` elements are held to the
  safe area, while `image`/`box` need only stay inside the canvas. Four
  built-in presets (`classic`, `broadcast`, `big_score`, `tigers`) each
  validate with zero warnings. The schema module remains pure and its public
  functions still never raise on malformed input.
- **Bridge and storage.** `infrastructure/layouts.py` gained `rename_layout`
  and `duplicate_layout`, and `host/layout_bridge.py`'s `PresentationLayouts`
  gained matching `rename`/`duplicate` methods, both following the existing
  `select`/`delete` pattern exactly: atomic, write-nothing-on-refusal,
  publish-on-success-only, with `Default` protected from rename (but not
  duplicate) and a name collision refused rather than overwritten.
  `LayoutEditorBridge`'s public surface is still exactly `get_snapshot,
  layout_state, preview_layout, clamp_layout, reset_widget, save_layout,
  select_layout, delete_layout, rename_layout, duplicate_layout,
  reset_layout` — no `command()`, no method named after any `CommandType`
  value.
- **Renderer** (`views/shared/board.js`/`board.css`). `applyLayout` now
  reconciles element nodes by id (create/update/remove) instead of rebuilding
  the DOM, inserts them before the first widget node so a widget always draws
  above an element at equal stacking order, and paints the board background
  on the container rather than the board root. Every house rule from v1
  still holds and is mechanically checked: no `Math.` beyond `Math.round`, no
  `toFixed`/`parseInt`/`parseFloat`/`setInterval`/`api.command`, and — new for
  v2 — neither `board.js` nor `board.css` may contain the substrings
  `handle`, `guide`, `drag`, or `resize` anywhere, including comments, so an
  editing affordance can never leak onto the LED wall.
- **Editor** (`views/layout/`), split into `layout.js` (bootstrap/bridge),
  `editor-state.js` (draft, history, selection, element factories), and
  `editor-canvas.js`/`editor-panels.js` (gestures and UI). A dense,
  dark, Figma/Canva-style canvas replaces the numeric-only v1 panel: pointer
  drag/resize with snapping and guides, multi-select and group-drag, undo/redo
  over the last 100 drafts, add-text/add-image/add-box, four presets, and full
  library management (rename/duplicate/delete/reset-to-built-in) through
  inline popovers rather than browser dialogs. The contract test now reads
  every `.js` file in the editor directory for the forbidden-token checks (no
  `CommandType` substring, no `alert`/`confirm`/`prompt`, no `.score`/
  `.display` substrings, `Math.` only followed by `round`), so splitting the
  file could not weaken them.
- **A cumulative-delta bug in `moveGroupBy`** (multi-selection drag) was
  found and fixed during implementation: the original computed each move's
  delta from the previous pointer position rather than the pointer-down
  origin, which would have let repeated small moves drift out of sync with
  the actual pointer distance. The fix computes the delta once from the
  gesture's start position on every pointer-move, then clamps the whole
  group by that single delta so relative positions inside the selection
  cannot desynchronize. See the review findings for this delivery for an
  independent check of the fix.
- **Verified so far.** Focused suites pass: schema 95, persistence+bridge 58,
  renderer contract, and editor contract 25. The editor was driven in the
  preview browser against a stub bridge (boot, select, add text/image/box,
  drag with snapping, history back/forward, presets with inline confirm,
  library menu, context menu, multi-select, zoom) and, separately, in the
  real pywebview/WebView2 runtime via `WindowHost` (editor window opened,
  text and box elements added through `evaluate_js`, history stepped, the
  board background set, `Save` wrote a schema-2 `layouts.json`, and the
  practice spectator window received the push with elements, background, and
  text).
- **Not verified.** The `tests/ui/` Playwright browser suites (still no
  Node.js on this development host, same limitation as every other Phase 2
  UI claim); any hardware/LED/two-display evidence; WebView2 file-picker
  behavior for the Image button on the real operator laptop. The full
  discovery run after v2 (September 5, 2026, isolated `SCOREBOARD_DATA_DIR`)
  reported **703 tests, 16 failures, 3 errors** — the same inventory as the
  "Automated suite failure inventory" baseline below; the one new failure it
  surfaced (`test_the_build_script_requires_every_view_file`, the editor's
  three new script files) was fixed in `tools/build_package.py` first. A review pass then fixed six further defects before the final run: the editor never cleared its unsaved flag after a save, a plain selection click on the canvas dirtied the draft and pushed history, an image element's corner radius did not clip the picture, the renderer accepted any `data:image/*` subtype where the schema allows four, element issue messages embedded unbounded raw text, and oversized images and over-limit element lists were decoded before rejection; `Fit to safe area` now narrates element repairs too.
  Task 12, the Phase 0 HDMI gate, and the two-display checklist are untouched
  and unadvanced by this request, exactly as the v1 delivery above recorded.

### Phase 2 owner request 4 — pre-game and halftime screens (September 6, 2026)

**Status: ✅ delivered and verified September 6, 2026.** Five parallel
Sonnet agents built it against `.scratch/presentation-screens/spec.md`
(schema, renderer, editor, bridge, docs) and the orchestrator then
integrated and verified it: focused suites green (schema 114, editor contract
30, spectator renderer contract 18, layout bridge and persistence), a full
discovery run of **750 tests with 15 failures and 3 errors** — exactly the
pre-existing inventory in "Automated suite failure inventory", no
regression — and a real pywebview/WebView2 run through `WindowHost` in which
the editor was switched to Pre-game, the Matchup preset applied, a text
element added, `Save` wrote a schema-3 `layouts.json`, the practice spectator
drew that pregame screen during `PRE_GAME`, and a confirmed move to `HALF`
switched it to the halftime screen with the warmup line. Not verified:
`tests/ui/` Playwright suites (no Node.js here) and any LED/hardware
rendering.

**What was asked.** Today the pregame and halftime "event board" (countdown
title, countdown, phase, warmup line, score line) is drawn from fixed HTML
in `views/spectator/index.html`; only the in-game board is a layout. The
owner asked for the pregame and halftime screens to be customizable "just
like the scoreboard," with a few presets for each — the same request that
`docs/UX_AND_LAYOUT.md` §10.8 had, until this entry, recorded as explicitly
excluded from the v1/v2 editor.

**What was built.** One stored layout document now
describes three screens instead of one. The in-game screen keeps its v2
shape at the top level of the document, so every existing test, file, and
push keeps working unmodified. Two new screens live under `screens.pregame`
and `screens.halftime`, each a complete mini-document with its own safe
area, background, widgets (a different, eight-item **event widget**
registry: home/away name and score, phase label, countdown title, countdown,
warmup line), and free elements. `LAYOUT_SCHEMA_VERSION` moves from 2 to 3;
a v1 or v2 file upgrades on read with the existing `SCHEMA_UPGRADED`
warning. The renderer gains a `build(container, kind)` / `applyLayout` split
between the `"game"` and `"event"` widget kinds and drops the old
hand-written pregame/halftime markup in favor of drawing the event screen
the same way the game board is drawn. The editor gains a Game / Pre-game /
Halftime toolbar switcher (`Ctrl+1/2/3`), per-screen presets (pre-game:
Classic, Matchup, Broadcast bar, Tigers navy; halftime: Classic, Score
first, Broadcast bar, Tigers navy — the four existing game-screen presets no
longer touch the other two screens), and validation issues that name their
screen. Every v1/v2 safety property is unchanged by design: the editor still
has no path to a game command, still advances no state revision, still
writes nothing to `scoreboard.db`, and `Save` is still gated on Python's
validation of the whole three-screen draft. `clocks.event.warmup_display` is
a new view-model field (`bridge.py`) carrying the same `"Warmup follows:
3:00"` string the old HTML computed inline, now produced once in Python and
only copied by the event screen's `warmup` widget.

**File map (per spec section 8; each agent owned a disjoint set).**

| Agent | Files |
|---|---|
| A — schema | `src/scoreboard/presentation/layout.py`, `tests/unit/test_layout_schema.py` |
| B — renderer | `src/scoreboard/views/shared/board.js`, `board.css`, `src/scoreboard/views/spectator/*`, `tests/integration/test_spectator_layout_render.py`, `tests/integration/test_spectator.py`, `tests/ui/spectator.cjs`, `tests/ui/test_spectator_browser.py` |
| C — editor | `src/scoreboard/views/layout/*`, `tests/integration/test_layout_editor_contract.py`, `tests/ui/layout_editor.cjs`, `tests/ui/test_layout_editor_browser.py` |
| D — bridge | `src/scoreboard/infrastructure/layouts.py`, `src/scoreboard/host/layout_bridge.py`, `src/scoreboard/host/bridge.py` (warmup_display only), `src/scoreboard/host/app.py` (only if needed), `tests/integration/test_layout_bridge.py`, `test_layout_persistence.py`, `test_bridge.py` (new warmup test only), `test_host_application.py` |
| E — docs (this entry) | `docs/UX_AND_LAYOUT.md` §6.1a and §10 (new §10.9), `docs/ARCHITECTURE.md` §9, `docs/PHASE_2_BACKLOG.md`, `docs/MVP_REQUIREMENTS.md`, `PROJECT_ROADMAP.md`, `README.md` |

**Verification status: verified by the orchestrator, September 6, 2026.**
Focused suites per agent pass (schema 114, editor contract 30, spectator
renderer contract 18, layout bridge, persistence, and the bridge's warmup
tests). The full discovery run reports **750 tests, 15 failures, 3 errors**
— the same inventory as the `308ddd6` baseline above, so no regression. In
the preview browser against a stub bridge, every pre-game and halftime
preset was applied and inspected by screenshot (two geometry defects found
that way — overflowing scores in "Score first", a wrapping warmup line in
"Broadcast bar" — were fixed before this was recorded). In the real
pywebview/WebView2 runtime via `WindowHost`: the editor opened, switched to
Pre-game, applied "Matchup", added a text element, `Save` wrote a schema-3
`layouts.json` whose `screens.pregame` carried both elements, the practice
spectator drew that pregame screen during `PRE_GAME`, and a confirmed move
to `HALF` switched it to the halftime screen showing `HALFTIME` and
"Warmup follows: 3:00". Not verified: the `tests/ui/` Playwright suites
(no Node.js on this host) and LED/hardware rendering.

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

### Phase 2 Task 9 evidence

- Added a focused operator keyboard adapter and table-generated Shortcut Help. Map: Space game Start/Stop from rendered snapshot; 2/4 load stopped 25/40 presets; P/S play Start/Stop; Q/Shift+Q quarter forward/back; ZXCV home +1/+2/+3/+6; NM comma period away +1/+2/+3/+6; Ctrl+Z Undo; Esc close dialog/drawer. Requirements section 6 now matches the confirmed preset decision.
- Every mapped game action reaches the existing `command()` signature with restricted `source` metadata in its args envelope. The same operator submission and confirmation functions serve both inputs, preserve the reviewed expected revision through confirmation, and retain source in durable accepted/rejected/prompt history. No toggle command or separate clock state exists in JavaScript.
- Real-browser-to-real-bridge test verifies all 16 command bindings plus Esc, exact arguments/revisions, repeat and duplicate keydown suppression, focused-button Space/held Enter safety, all nine existing fields plus textarea/select/contenteditable, ignored modifiers/composition, confirmation suppression/cancel, identical mouse/keyboard running-clock quarter round trips, stale confirmation, recovery-screen isolation, table-generated help, and live control bounds at 1366x768 and 1093x614 CSS viewports. Two source contract tests reject invalid source metadata and check durable history.
- Focused Task 9 tests 3/3; full suite 261/261. `compileall`, `pip check`, JavaScript syntax, diff whitespace, UTF-8 and relative Markdown file-link checks passed. No runtime database or log is in the repository. The complete change inventory was a separate `docs/TASK_8_9_CHANGE_REPORT.md`, removed on September 5, 2026 because it duplicated information the commits already carry and its repository-status statements had been superseded four times over; the changes themselves are commits `c3fd05a` (recovery prerequisite), `6691c13` (Task 8 spectator foundation), and `d03066e` (Task 9 keyboard and input safety).
- Numpad behavior, actual Windows repeat timing, novice rehearsal and physical WebView2 scaling remain release evidence. Browser automation cannot establish these results. No Task 10, packaging, OBS, controller or networking work was started.

### Persistence runtime follow-up

- The first real control launch exposed a runtime-only defect: SQLite created its connection on the webview thread, while the refresh worker and shutdown path attempted checkpoints on other threads. Python's default SQLite thread-affinity check therefore reported `NOT SAVED`, even though the database and persistence code were present.
- Updated [`src/scoreboard/infrastructure/persistence.py`](src/scoreboard/infrastructure/persistence.py) to allow the single connection to cross that boundary; the existing application `RLock` continues to serialize commands, checkpoints, and shutdown.
- Added a worker-thread checkpoint regression test in [`tests/integration/test_host_application.py`](tests/integration/test_host_application.py). The focused host/persistence suite passed 38/38, the regression passed, and an actual Windows host launch exited 0 with no persistence failure in its isolated log.

### Phase 2 Task 8 evidence

- Spectator page now renders mutually exclusive game/event presentations inside a centered logical 16:9 canvas with configurable 4% inset, proportional type and local fonts. Only documented fields appear; blank play-clock space differs from expired `0.0`.
- Accepted commands publish immediately under the shared command/tick lock. Push-count tests assert one spectator delivery before any tick, none for rejection, and continued scoring/running clocks after injected push failure. Reopen reads the current complete snapshot and retains an active play clock.
- Added authoritative, persisted `play_clock_cleared`: inspection disproved the request's assumption that the old view model distinguished stopped expiry from clear. Presets/corrections reveal it; clear/game-start coupling blanks it; expiration and recovery retain visibility. Legacy snapshots missing the additive field preserve old stopped-zero blank behavior because their intent cannot be recovered.
- Lifecycle now follows existing accepted commands as recorded in the Decision Log. Quarter entry selects the matching event preset only when switching event kind; an already selected interval retains time. Team-name editing leaves pregame, and expiry never advances lifecycle.
- Focused authority tests 6/6 and browser tests 2/2 passed; full suite 258/258. Browser matrix covers 36 cases (four viewports, four scores with 24 W characters per name, pregame and four interval boundaries), text bounds/no overlaps/no scrollbars, initial revision, blank/zero, and injected page-render failure. `compileall`, `pip check`, JS syntax and diff checks passed.
- Manual visual observations and exact viewport measurements are in [Task 8 captures](docs/evidence/task8/README.md). No physical LED, two-display or 100/250 ms end-to-end latency result is claimed. Those remain release evidence.

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
- Nothing auto-resumes. At the Task 7 boundary, when a recoverable game existed and no choice was made, `WindowHost.run` raised `RecoveryChoiceRequired` carrying the report instead of guessing; `--resume` and `--new-game` made the choice. The in-window recovery screen was then added as the Task 8 prerequisite: `StartupBridge` now presents the report and creates the normal operator only after Resume or New Game. Native WebView2 interaction remains release evidence.
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
| Project skeleton | Minimal structure exists for the selected architecture. | ✅ Source/test/asset boundaries established; Phase 2 implementation now fills the documented boundaries. Detailed tree in `docs/PROJECT_STRUCTURE.md`. |
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
| Presentation layout editor | Safe offline editing of spectator-board placement and colors through validated visual-only layouts | ✅ v1 delivered early, inside Phase 2, on September 5, 2026 at the owner's direct request, rebuilt as v2 the same day, and extended to the pre-game and halftime screens (v3) on September 6, 2026 — see "Phase 2 owner request 3" and "owner request 4" above. Delivering it does not advance any other Phase 3 workstream in this table |
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
| High | Which score-correction method is required: minus buttons, direct edit, undo, or a combination? | Use Undo, separate minus controls, and confirmed direct entry; every correction is logged. Undo began as one-level and is now a bounded 20-entry stack (I4). | ✅ Resolved and expanded |
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
| September 5, 2026 | A remembered display is matched by device name and geometry, in three tiers, with **no index fallback**. An unmatched preference reports `DISPLAY NOT FOUND` and opens nothing. | An index is not an identity: unplug a cable and index 1 is a different monitor, or the operator's own screen. A fullscreen board covering the controls during a game is worse than no board, so the fallback that would cause it does not exist (D-002). | If real hardware shows a fourth recognisable identity, such as a stable monitor serial, that survives what these three do not. |
| September 5, 2026 | Only an operator choosing a display re-points the saved display. Recognising the saved display refreshes its geometry; an index or a default open remembers nothing. | Otherwise a night when the wall is missing and the operator works on one screen would silently overwrite the wall as the saved display, and the next launch would be wrong in a way nobody changed. | If an operator ever asks for "remember whatever I last used". |
| September 5, 2026 | A display appearing or disappearing is reported and never acted on; the check runs about twice a second and switches itself off after a failure. | D-006 and the Task 10 boundary both forbid hidden auto-moves during live play. The cadence is a compromise between learning about a dark wall within a dead ball and calling Windows four times a second forever; disabling after a failure avoids filling a game's log with one repeated fault. | When the checklist measures how long Windows really takes to re-enumerate after an HDMI event. |
| September 5, 2026 | `config.json` holds operator preferences, read tolerantly: damaged, truncated, or newer-version content reads as "nothing saved" and never stops a launch. A newer-version file is left on disk rather than overwritten. | The same trade the data-folder pointer makes. On a game night a stale setting must cost one click, never the game. Leaving a newer file alone means returning to the newer build does not lose the operator's setting. | If a preference is ever added whose absence is genuinely unsafe, which none is today. |
| September 5, 2026 | The display panel goes in the corrections drawer beside **Saved to**, and `Reopen Display` stays a one-click control in the health strip. | The drawer overlays and scrolls inside itself, so it costs no always-visible layout and does not invalidate U-001. A dark wall is not the moment to go looking through a drawer, so the recovery button stays where it is. | At the operator-layout revisit, where both belong on a real Settings surface. |
| September 5, 2026 | An operator-chosen data folder takes effect at the next launch, never immediately, and its pointer lives in the platform default root. | The store's connection, the instance lock and the log handler are open on the current folder during a game, so relocating live is a far bigger operation than the request; and a pointer inside the folder it points at could never be found again. | If relocating a running game is ever genuinely needed, which would require closing and reopening the store under the command lock. |
| September 5, 2026 | Build Task 11 before Task 10, out of backlog order, and record that the package carries Task 1-era display behaviour. | Task 10 needs a two-display machine the development host does not have; Task 11 needs none. Building the packaging path now surfaced a shipped-assets defect that only a real build could expose. | Immediately after Task 10: the package must be rebuilt before any release. |
| September 5, 2026 | Move the application version to 0.1.0, with `domain/state.py` as its one definition and the packaging metadata and executable resource following it. | W-006 wants a visible version, and `0.0.0` was the pre-implementation placeholder. A single definition means a build can never be stamped with a version the running code does not report. | Each release; bump deliberately, never as a side effect. |
| September 5, 2026 | A packaged build reports fatal startup problems in a message box; `--check` never opens one. | A windowed build has no console, so a silent exit is indistinguishable from a broken shortcut. But a readiness check is run by terminals and scripts, and a modal dialog hangs both -- which it did, to this project's own build script, before the split. | If a fatal path ever needs to run unattended. |
| September 5, 2026 | `schema_version` is the only compatibility gate on a stored game; `app_version` is provenance and is reported, never enforced. | Gating on the build number made every saved game unrecoverable the moment the version changed, which Task 11 packaging guarantees will happen. A mid-season update installed between two launches would have destroyed a game in progress. | A future schema change that genuinely cannot be read by an older or newer build; that is what `schema_version` is for. |
| September 5, 2026 | Record clock expiration as a `system`-sourced action-history row written by the refresh tick, rather than adding an expire command or letting the tick submit one. | F-037 and F-046 require expiration in the durable history, but nobody presses anything when a clock reaches zero. Keeping it out of the command model preserves the rule that the service is the only writer of the authoritative revision. | If expiration ever needs to change game state — an automatic quarter advance, for example — at which point it becomes a real command and needs a confirmation policy. |
| September 5, 2026 | Distinguish a genuine expiry from a commanded zero by comparing the state revision between refresh ticks. | A game-clock Start blanks a running play clock (F-048) and a correction can set 0:00; both reach zero without expiring. The command that caused them already has its own history row, so inventing an expiration as well would misreport the field. | If a future command changes a clock without advancing a revision. |
| September 5, 2026 | Human-facing saved/checkpoint timestamps use Eastern local time (`America/New_York`) with a readable zone-bearing format; internal elapsed timing remains monotonic and machine timestamps remain unambiguous. | Operators need to reconcile recovery information quickly, while daylight-saving-aware conversion prevents UTC/raw ISO strings from being mistaken for local time. | When another operator-visible timestamp is added or the project adopts a different deployment timezone policy. |
| September 5, 2026 | Add ball on, to go, down, timeouts, possession, and any requirements-reviewed essential football fields before starting the presentation layout editor. | These are game-operation information and authoritative-state concerns, while text size/position/color editing is spectator-only presentation work that must not obscure the core workflow. | After the expanded-field task is verified and operators identify additional essential fields. |
| September 5, 2026 | Field position is one compound state field, `BallSpot(team, yard_line)`, with `yard_line` counted from `team`'s own goal line (0-50) — not two separate fields and not an absolute 0-100 field scale. | Matches how officials and broadcasts describe field position ("the Eagles' 35"); keeping it one field, on the same pattern as `ClockValue`, lets the generic Undo machinery reverse it as a unit with no special case. | If a future need (an absolute field-position graphic, for example) requires a coordinate that is not team-relative. |
| September 5, 2026 | Down, distance, possession, ball position, and timeouts are never changed automatically by another command (scoring, quarter, or clock). Timeouts default to 3 per team and are not auto-reset at halftime. | Automating a football rule (for example, resetting timeouts at halftime, or clearing down/distance on a change of possession) risks encoding a rule the owner or officials have not confirmed; an explicit operator action is always correct even if one click slower. | If rehearsal (Task 12) shows operators reliably forget one of these steps and officials confirm the automatic rule. |
| September 5, 2026 | The durable history's generic JSON encoder (`infrastructure/persistence.py`) converts any dataclass value via `dataclasses.asdict` rather than falling back to `str()`. | Undo's generic old/new reporting reads a state field by name and can hold a compound value like `BallSpot`; a `str()` fallback recorded a Python repr in the audit trail and, at the bridge layer, briefly broke JSON serialization for that field until the corresponding service-layer fix. | If a future compound state field needs a different serialized shape than its own field names. |
| September 5, 2026 | A genuine game-clock running-to-stopped transition clears a running play clock: explicit Stop does so in its command commit; natural expiry clears it through a bridge-locked observed tick without advancing the revision. | The stadium board must not keep showing a self-running play clock after the game clock has stopped. The observed expiry path mutates the play-clock engine and writes the game-expiry and system-caused clear records together, so a later tick cannot revive the old deadline and recovery retains why it disappeared. A redundant Stop remains a no-op for an independent play clock. | If officials require a different stopped-game-clock workflow. |
| September 5, 2026 | Spectator-widget coordinates are normalized fractions (0.0-1.0) of the logical 16:9 canvas for `x`/`y`/`width`/`height`, and `font_scale` is a fraction of canvas **width** specifically, not height or a mix of both. | Matches the existing CSS convention (`calc(var(--canvas-width) * .12)`), so the widgetized board's default geometry reproduces today's type sizes exactly instead of inventing a new scale the whole board would need re-tuning against. | If the canvas is ever given a non-16:9 logical aspect ratio. |
| September 5, 2026 | A layout is validated strictly: any out-of-range value, invalid color, out-of-safe-area widget, undersized widget, or serious overlap is an error and the whole layout is rejected. A stored layout that fails to load falls back to the last known valid layout, then to the built-in default, and never blocks launch. | Presentation state must obey the same "a preference file may never stop the scoreboard" rule as `config.json` and the data-folder pointer, while still refusing to render a layout that would put required scoreboard information off-screen or unreadable. | If a future property needs a graded warning instead of a hard error. |
| September 5, 2026 | Spectator layouts are stored in their own `layouts.json`, never as a section inside `config.json`. | A layout library can hold several named layouts and carries its own schema version; keeping it a separate file means a damaged layout library cannot cost the operator a saved game, and a damaged game cannot cost the operator a saved layout — the same reasoning that already keeps the action history inside `scoreboard.db` rather than a shared file. | If layouts and operator preferences are ever shown to need one combined migration path. |
| September 5, 2026 | Overlap validation considers only **visible** widgets. | A hidden widget cannot visually collide with anything, so this is what lets `game_clock_label`, `home_timeouts`, and `away_timeouts` sit in otherwise-occupied default positions while hidden, without the validator rejecting the built-in default layout. | If a future workflow needs to warn about a hidden widget that would collide once shown. |
| September 5, 2026 | `game_clock_label`, `home_timeouts`, and `away_timeouts` ship as positionable widgets that default to **hidden**. | The current spectator board draws none of them, so hiding them by default makes the widgetized board's default layout reproduce today's board exactly; requirement D-001's default field inventory is answered the same way as before, and turning them on becomes a deliberate operator presentation choice rather than an automatic answer to open owner decision B-4. | If the owner decides timeouts should be visible by default rather than opt-in. |
| September 5, 2026 | The presentation layout editor uses numeric fields with documented min/max for every geometry property; there is no drag-and-drop or drag-resize in v1. | Matches discovery issue 05's chosen level (constrained named-slot editing) while keeping the implementation to validated number entry rather than pointer-based hit-testing and drag math, which is a materially larger and riskier UI surface for a first version. | If rehearsal or the owner asks for direct manipulation and the added complexity is judged worthwhile. |
| September 5, 2026 | **Superseded the same day.** The layout editor is rebuilt as a v2 canvas editor: pointer drag/resize with snapping and guides, multi-select and group-drag, undo/redo, and free text/image/box elements are now in v1's place, and "no free text or images" is no longer a v1/v2 exclusion — schema v2 adds validated `text`/`image`/`box` elements (up to 24, images capped at 2 MB/6 MB decoded) alongside the fifteen widgets. Every v1 safety property (no path to a game command, no state-revision advance, strict Python validation gating `Save`) is unchanged. | The owner's verdict on the numeric-only v1 editor was "stuck 20 years in the past." Direct manipulation and free decorative content were judged worth the added UI surface once the safety invariants above were confirmed intact by an independent review pass. | If a future editor generation needs a different interaction model; the underlying schema/bridge/renderer safety contract is expected to outlive any particular UI. |
| September 6, 2026 | The pre-game and halftime screens live **inside one layout document** (`screens.pregame` / `screens.halftime`, schema v3), not as a separate library or file alongside `layouts.json`'s existing layouts. | An operator thinks of "the layout" as one design choice for the whole spectator experience, not three unrelated files that could drift out of sync (a Tigers-navy game board paired with a Classic pregame screen by accident); one document also means Save/duplicate/rename/delete already act on the right unit with no new bridge surface, and a v1/v2 file upgrades to v3 by gaining two default screens rather than needing a migration into a second store. | If an operator workflow emerges needing to reuse one pregame screen across several otherwise-different game-screen layouts, which would argue for screens as independently addressable objects. |
| September 5, 2026 | The Field Assistant is a one-panel-at-a-time screen for a volunteer with five minutes of training: direction is asked once in plain words ("Which end zone does HOME score in during the 1st quarter?"), "who has the ball" starts every series including kickoff returns, and each play is "click where the ball ended, press what happened" (**PLAY OVER**, **INCOMPLETE PASS**, **OTHER TEAM'S BALL HERE**, with **PENALTY…**, **SCORE…**, **FIX MANUALLY…** as sub-panels). The Confirm button's label is the previewed result. A punt, interception, fumble, turnover on downs, and kickoff return are all the same explicit `turnover`/`start_series` change of possession to Python. A new `manual` action lets the operator state team, down, distance (or Goal) and the clicked spot; Python validates and derives only the line to gain, in one atomic command. | The owner's second operator attempt (September 5, 2026) still could not finalize anything. The real cause was a defect — the helper attached its bridge on a `document`-level `pywebviewready` listener that pywebview never fires (it dispatches on `window`), so Confirm could never enable — but the owner's verdict on the screen itself was that a workflow dropdown, hidden control groups, a "HOME attacks toward" dropdown, and a separate Preview press were too hard for a normal person, and that kickoffs/punts and an intuitive manual override were missing. Both were fixed together; the rules, envelope, and atomic boundary did not change. | If a live operator rehearsal shows a step volunteers still miss, or if the owner wants the Field drawer's manual controls removed from the main window (they are unchanged today). |
| September 5, 2026 | The Field Assistant's rules direction is fixed per team in the label-based absolute coordinate (HOME always `+1` toward the AWAY goal line, AWAY always `-1`); the operator's one-time first-quarter choice only records which side of the on-screen drawing HOME attacks toward, and the drawing mirrors at every quarter boundary (`home_goal_side`). Stored ball spots and line-to-gain never move at a quarter change; OT stays manual-only. | The originally drafted rule flipped the label-based direction itself every quarter, which is internally inconsistent with a coordinate where `0` is always the HOME goal line: a literal flip would have moved a 2nd-quarter HOME gain toward HOME's own goal line. Found and corrected during implementation, before any rehearsal used the incorrect version. | If local overtime rules are approved and OT direction stops being manual-only. |
| September 4, 2026 | Task 8 gap 1: lifecycle follows accepted quarter commands (including quarter Undo): PRE → PRE_GAME, HALF → HALFTIME, FINAL → FINAL, all playing labels → IN_PROGRESS. A successful game-clock Start leaving pregame/halftime enters IN_PROGRESS; End Game sets FINAL and New Game restores PRE_GAME. PRE/HALF entry selects its stopped event preset only when switching countdown kind; an already selected countdown retains its time. | No overlapping lifecycle control; team-name validation now leaves pregame. Expiry never advances lifecycle. | Operator rehearsal. |
| September 4, 2026 | Persist an additive play_clock_cleared flag; retain old blank-zero interpretation for legacy snapshots lacking it. | The old model erased expiry versus clear intent; the renderer cannot recreate it safely. | Recovery compatibility/rehearsal. |
| September 4, 2026 | Task 8 gap 2: publish after accepted commands under the existing serialization lock, retaining ticks for timed refresh/checkpoint work. | Removes the 250 ms scheduler wait; push-count tests prove delivery without a tick. Physical latency remains release evidence. | Target laptop measurement. |
| September 4, 2026 | Task 9 gap 3: 2/4 load stopped 25/40 presets; P starts and S stops the play clock. Space, Q/Shift+Q, ZXCV, NM comma period, Ctrl+Z and Esc retain their documented purposes. | Matches confirmed mouse/preset behavior. Requirements change precedes keyboard code. | Operator/numpad rehearsal. |
| September 4, 2026 | Carry source as restricted metadata in the existing command args envelope; preserve original source and reviewed revision through confirmation. | Distinguishes keyboard/mouse in durable history without widening command() or creating keyboard-only commands. | Input adapter contract changes. |
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
| September 4, 2026 | Do not restore the in-memory Undo stack after recovery. | The operator must verify the board against the real game before resuming (P-005). Offering reversals of commands they cannot see, issued before a crash they may not have witnessed, invites a second error rather than fixing the first. The durable action history remains; only the in-memory shortcut stack is lost. | Revisit if rehearsal shows operators repeatedly need to reverse pre-crash actions. |
| September 4, 2026 | Do not persist `PlayClock.preset_seconds`; allow it to reset to blank on recovery. | It is engine-only bookkeeping and is deliberately absent from the persisted `ClockValue` contract. A recovered Reset therefore blanks the play clock rather than restoring a 25 or 40 the operator never re-selected, and reloading a preset is one click on an always-visible control. | Revisit only if a recovered game must restore the preset without an operator action. |
| September 4, 2026 | Keep the durable action history inside `scoreboard.db` rather than in a separate JSONL event log, superseding the `infrastructure/event_log.py` sketch in the structure document. | P-002 requires the new state and its history row to commit in one transaction; two files cannot guarantee that. The rotating `application.log` still records program-level diagnostics separately. | Revisit only if an external consumer needs a streaming event file. |
| September 4, 2026 | Compose `Start after applying?` in the operator view as an Edit-Current-Time command followed by an optional Start command, rather than adding a `start_after_apply` field to the command model. | It keeps the Task 5 command contract unchanged, defaults to remaining stopped by simply not issuing the second command, and records both steps in the audit trail. | Revisit if the two-revision sequence proves confusing in the history or in rehearsal. |
| September 6, 2026 | Never call into a webview while holding the command lock: snapshot under the lock, deliver after it, and put blocking calls on a host publisher boundary (audit C4). | The installed WebView2 backend has no bounded or non-blocking script call, so a stalled window could otherwise freeze every command. This decision is retained, but the current single-worker/per-batch implementation has a documented stale-offer interleaving and healthy-window delay; C4 is reopened. | Revisit the implementation immediately; later revisit the 2 s stall notice if hardware evidence warrants it. |
| September 6, 2026 | Bound the last-known-good backup to at most one refresh per 2 seconds (first commit, shutdown, and close always refresh; a pending refresh is flushed by the next checkpoint). | A full SQLite copy inside every accepted command ran under the command lock. The policy remains "refresh only after a verified commit"; only the cadence changed. | Revisit if a recovery rehearsal ever finds the backup more than one checkpoint behind the primary. |
| September 6, 2026 | Give the spectator display its own drawer, opened from an always-visible 44 px `Display…` button beside a 44 px `Reopen Display`, and take the selector out of Corrections (audit C5). | Recovering a dark wall is the one thing a volunteer must find in two seconds; it does not belong one panel from destructive Apply buttons at a size below the project's own floor. | Revisit after the physical 1366×768 check and the two-display checklist; the data-folder row still lives in Corrections and is the remaining Settings-surface revisit. |
| September 6, 2026 | Keep team identity out of `GameState`: saved teams are a laptop preference in `teams.json`, applying one is the existing `set_team_name` command, and colours/short names ride along in the view models only (audit F4, presets half). | It gives the weekly retyping problem a one-click fix without a state-schema change, a migration, or a presentation value becoming authoritative. Binding board widgets to team colours is a layout-editor feature and stays deferred. | Revisit when the layout editor gains colour bindings or logos, which would decide whether identity needs a stronger key than the team name. |

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
| September 4, 2026 | Task 8 spectator foundation | Full suite 258/258; 36 browser layout cases; syntax/compileall/pip/diff checks passed. | `tests/integration/test_spectator.py`; `tests/ui/`; `docs/evidence/task8/` | Browser observations only; LED/two-display and end-to-end latency remain pending. |
| September 4, 2026 | Task 9 keyboard/input safety | Full suite 261/261, including real browser to real bridge/storage input tests; compileall/pip/syntax/diff/link checks passed. | `tests/ui/keyboard.cjs`; `tests/integration/test_keyboard_source.py`; Task 9 evidence above | Real OS repeat, numpad and novice rehearsal remain pending. |
| September 5, 2026 | Phase 2 audit of the implemented code against the requirements, backlog, and this roadmap | Every Task 1-9 acceptance criterion met by code; two requirement-level defects found and fixed (unrecorded clock expiration; the application version gating recovery); stale status text in `README.md` and `src/scoreboard/README.md` corrected; five open questions raised for the owner | Audit section above; `docs/PHASE_2_BACKLOG.md` status note | Task 10 may begin from an accurate baseline. A-1 (play-clock behaviour on a ready-for-play game-clock start) needs an answer before live use. |
| September 5, 2026 | Application-version recovery experiment | With the stored version at `0.0.0` and the running build moved to `0.1.0`, `inspect_recovery` reported `UNRECOVERABLE` for both the primary database and its backup. After the fix, the same game is offered with names, scores, quarter, and stopped clocks intact, and the saving version is reported. | `tests/integration/test_recovery.py::ApplicationUpgradeRecoveryTests` | Removed a defect that would have first appeared during Task 11 packaging, in the field, mid-season. |
| September 5, 2026 | Whole-game fake-time rehearsal through the real bridge | Pass. Four quarters of 120 snaps, both countdowns, an undo, a crash and resume in the third quarter, and End Game left the scores, the consumed game time, the lifecycle, and the action history all consistent. Several thousand refresh ticks and their checkpoints reported `SAVED` throughout. | `tests/integration/test_full_game_rehearsal.py` | Partial R-006 evidence only. The two-hour soak, the real clock tolerance, and every hardware behaviour remain release evidence. |
| September 5, 2026 | Real-time 12-minute clock measurement on the development host | Worst absolute error 0.0129 s, final error 0.000179 s, and 0.0060 s cumulative drift across 401 pause/resume cycles, against a 0.25 s tolerance | Measurement above | No per-tick or per-pause accumulation exists in the engine. R-005 still requires the target laptop under a real window. |
| September 5, 2026 | Full automated suite on this host after the audit fixes | 273 Python tests passed. The two `tests/ui/` browser checks errored because Node.js and Playwright are not installed here; by design they fail explicitly rather than skipping. `compileall` and `pip check` passed. | Session output | A clean machine without the browser tooling reports 273 passed and 2 errors. That is the expected shape, not a regression. |
| September 5, 2026 | Operator-chosen data folder | 29 tests pass covering the pointer, resolution order, stale and malformed pointers, validation, all four picker outcomes, and the bridge's no-game-state guarantee. The real dialog was opened from `--choose-data-folder` and cancelled; nothing was written. | `tests/integration/test_data_folder.py`; evidence section above | A completed selection and a game run from a relocated folder remain target-laptop rehearsal items. |
| September 5, 2026 | Task 11 package build and verification on the development host | One-folder PyInstaller build at version 0.1.0: 152 files, 27.3 MB, all eleven view files present, no page referencing a remote resource, and the frozen `--check` exiting 0 with the expected version. A packaged launch opened both windows, logged a clean shutdown, exited 0, and left no orphan process. | `docs/PACKAGING.md`; `tools/build_package.py`; Task 11 evidence above | The offline package path exists. The clean-machine, network-disabled, SmartScreen, and target-laptop checks are still open. |
| September 5, 2026 | Package-data defect found while packaging | The metadata declared only `views/**/*.html`, so a non-editable install shipped the pages without their stylesheets or scripts. A wheel now contains all eleven view files. | `tests/integration/test_packaging.py::PackageDataTests` | A blank LED wall that no existing test could have caught, because every test ran from a source checkout. |
| September 5, 2026 | Frozen no-console failure path | Launching a second copy of the packaged build while the instance lock was held produced a message box titled `Scoreboard is already running`, not a silent exit. | Session output; `src/scoreboard/host/preflight.py` | A windowed build can report a fatal problem to an operator. The missing-WebView2 dialog is proven by test double only; the real absence has not been observed. |
| September 5, 2026 | Application folder replaced mid-game (W-005) | A seeded game survived deleting and rebuilding the entire application folder: Tigers 7, Eagles 3, second quarter, `game_id` 1, with a continuous action history. | Session output; `docs/PACKAGING.md` | An update between two games does not destroy a game in progress. |
| September 5, 2026 | Phase 2 Task 10 display selection, identity, and failure recovery | 73 tests pass against injected screen lists and a faked `webview.create_window`: three-tier matching including resolution, scaling, and device-renumbering changes; no fallback to the primary display; a missing display opening no window while the operator view stays complete and clocks keep running; a simulated disconnect leaving the revision, the database, and a running clock untouched and writing no history row; a reconnection reported but never acted on; a reopened view showing the current revision and a play clock that never stopped; select, forget, and list advancing no revision; and six kinds of damaged `config.json` all reading as "nothing saved". Full suite 385 Python tests pass; the two `tests/ui/` browser checks error because Node.js is absent. `compileall`, `pip check`, and the relative-Markdown-link check passed. | `tests/test_displays.py`; `tests/integration/test_display_selection.py`; Task 10 evidence above | The display policy is settled and cannot reach the game. Every criterion needing a second monitor is outstanding and listed in `docs/DISPLAY_CHECKLIST.md`. |
| September 5, 2026 | Mutation check on the Task 10 tests | Disabling disconnect detection failed two disconnect tests; adding a primary-display fallback failed the missing-display test. Two tests that still passed under mutation were strengthened to assert the loss was actually noticed. | Session output | The tests fail for the reasons they claim, rather than passing by construction. |
| September 5, 2026 | U-001 re-measurement after the health strip changed | At 1366x768 and 1093x614, with the strip in its widest state, nothing scrolls and no live control leaves the viewport; the drawer still overlays and scrolls inside itself. Found `Reopen Display` at 28 px, under the 32 px the Task 7 note recorded; raised to 32 px. | Session output; `docs/UX_AND_LAYOUT.md` section 8 | Chromium at equivalent CSS viewports, as in Task 7 — not WebView2 on a physical 1366x768 display. The 44x44 accessibility target for `Reopen Display` needs the layout re-flowed and remains unmet. |
| September 5, 2026 | Package rebuilt after Task 10 and confirmed to carry it | 152 files, 27.4 MB, version 0.1.0, build-script verification passed. With nothing saved the frozen build opened no spectator window and logged the plain-language reason; with a display saved it logged `DISPLAY_SELECTED ... how=exact` and opened on it; with a corrupt `config.json` it started normally. Exit 0 each time, no orphan process. | `docs/PACKAGING.md`; session output | The pre-Task-10 package is superseded. The clean-machine, offline, SmartScreen, and second-display release checks are still open. |
| September 5, 2026 | Encoding defect found by the pre-commit UTF-8 check, outside Task 10 | `views/startup/startup.js` held a cp1252 em dash (byte 0x97) rather than UTF-8, in the score separator of the recovery screen preview. A browser decoding the file as UTF-8 would have shown the operator `Tigers 7 <?> 3 Eagles` on the one screen that exists to help them decide whether to resume a game. Replaced with a real U+2014; all 81 checked files now decode as UTF-8. | `src/scoreboard/views/startup/startup.js` | Pre-existing since the Task 8 recovery prerequisite and unrelated to display work. Fixed rather than recorded and left, because it is one byte and it is visible to an operator under pressure. |
| September 5, 2026 | Bundle B — clock/board visual clarity | Implemented green game-clock and red play-clock running treatments in both windows, always-visible `PLAY CLOCK` with `—` after a clear, and spectator-only live-quarter wording such as `2nd Quarter`. The compact authoritative quarter and the cleared-versus-expired `0.0` state distinction remain unchanged. Focused spectator and real-browser keyboard tests passed; the isolated full suite passed 405 tests in 46.010 seconds. `compileall`, `pip check`, and `git diff --check` passed. The one-folder package was rebuilt and frozen `--check` verified it at version 0.1.0 (195 files, 29.8 MB). | `src/scoreboard/host/bridge.py`; `src/scoreboard/views/`; `tests/integration/test_spectator.py`; `tests/ui/`; `dist/Scoreboard/` | Browser layout assertions cover the required viewports. Stadium colour/brightness and target-laptop WebView2 observation remain Task 12 evidence. |
| September 5, 2026 | Deep-dive audit: five lightest findings implemented | Guarded the startup spectator open so the refresh loop always starts (C1); moved the folder picker outside the command lock (C2); put both names and scores on the pregame/halftime countdown board (C3); added the `open_logs_folder` host action and its Advanced-drawer button (I3); isolated `DataLocationTests` from the operator's remembered folder (I1 slice). Nine new tests; full suite 712 / 15 failures / 3 errors — identical baseline, nothing new failing. The two lock/guard tests were run with the source change stashed and **fail without the fix**. The halftime board was rendered in a browser against a `HALFTIME` snapshot with both names and scores visible. Not done: the Playwright matrix (no Node here) and a real WebView2 window. | `src/scoreboard/host/app.py`; `src/scoreboard/host/bridge.py`; `src/scoreboard/views/spectator/index.html`, `spectator.css`; `src/scoreboard/views/operator/index.html`, `operator.js`; `tests/integration/test_display_selection.py`, `test_data_folder.py`, `test_logs_folder.py`, `test_persistence.py`, `test_spectator_layout_render.py` | See "Deep-dive audit" for the ten open findings and their owners. |
| September 5, 2026 | Presentation layout editor (v1) | Added the layout schema and validation (`presentation/layout.py`), `layouts.json` persistence, a non-mutating host bridge, the widgetized spectator renderer (`views/shared/board.js`/`board.css`), and a separate editor window. **100 focused Python tests pass**: schema 42, persistence 18, bridge/no-mutation 18, renderer contract 8, editor contract 14. The three browser checks (spectator matrix 2, editor drive 1) passed when written but error on this host, which has no Node.js or Playwright. The browser matrix covers 1280x720, 1366x768, 1920x1080 and 390x844 and **fixed a pre-existing safe-area overflow** in the play-clock block. `compileall`, `pip check`, and `git diff --check` passed. | `src/scoreboard/presentation/layout.py`; `src/scoreboard/infrastructure/layouts.py`; `src/scoreboard/host/layout_bridge.py`; `src/scoreboard/views/layout/`; `src/scoreboard/views/shared/board.js`; `tests/unit/test_layout_schema.py`; `tests/integration/test_layout_persistence.py`; `tests/integration/test_layout_bridge.py`; `tests/integration/test_spectator_layout_render.py`; `tests/integration/test_layout_editor_contract.py`; `tests/ui/` | Closes discovery issue 05 and owner-requested item 3. No hardware, two-display, or WebView2 rendering evidence is claimed; Task 12 and the hardware/stadium evidence gap are unaffected. |
| September 5, 2026 | Presentation layout editor v2 | Rebuilt the same day as a canvas editor against `.scratch/layout-editor-v2/spec.md`: schema v2 (background, up to 24 text/image/box elements, fonts, presets, v1→v2 upgrade path) in `presentation/layout.py`; `rename_layout`/`duplicate_layout` in `infrastructure/layouts.py` and `host/layout_bridge.py`; element reconciliation, background-on-container, and the `handle`/`guide`/`drag`/`resize`-forbidden renderer contract in `views/shared/board.js`/`board.css`; and the split editor (`layout.js`, `editor-state.js`, `editor-canvas.js`, `editor-panels.js`) with undo, multi-select, and library management. **Verified so far:** focused suites pass — schema 95, persistence+bridge 58, renderer contract, editor contract 25. Driven in the preview browser against a stub bridge (add elements, drag/snap, history, presets, library menu, context menu, multi-select, zoom) and in the real pywebview/WebView2 runtime via `WindowHost` (editor opened, elements added, history stepped, background set, `Save` wrote a schema-2 `layouts.json`, practice spectator received the push). A cumulative-delta bug in multi-selection group-drag (`moveGroupBy`) was found and fixed during implementation. Full discovery run after v2 (September 5, 2026, `SCOREBOARD_DATA_DIR` isolated): **703 tests, 16 failures, 3 errors** — the same inventory as the pre-v2 baseline; the one new failure the run surfaced (`test_the_build_script_requires_every_view_file`, because the editor gained three script files) was fixed by adding them to `tools/build_package.py` before this was recorded. | `src/scoreboard/presentation/layout.py`; `src/scoreboard/infrastructure/layouts.py`; `src/scoreboard/host/layout_bridge.py`; `src/scoreboard/views/layout/`; `src/scoreboard/views/shared/board.js`; `src/scoreboard/views/shared/board.css`; `tests/unit/test_layout_schema.py`; `tests/integration/test_layout_persistence.py`; `tests/integration/test_layout_bridge.py`; `tests/integration/test_spectator_layout_render.py`; `tests/integration/test_layout_editor_contract.py`; `.scratch/layout-editor-v2/spec.md` | Not verified: `tests/ui/` Playwright suites (no Node.js on this host), hardware/LED/two-display evidence, WebView2 file-picker behavior for the Image button. Task 12 and the hardware/stadium evidence gap remain unaffected. |
| September 6, 2026 | Presentation layout editor v3 — pre-game and halftime screens | Schema v3 (`screens.pregame`/`screens.halftime`, the eight-widget event registry, per-screen validation and clamp, eight screen presets), the renderer's `build(container, kind)` path with the spectator page drawing the screen chosen by `lifecycle`, the editor's Game / Pre-game / Halftime switcher with per-screen presets and issues, the bridge's `screens`/`screen_presets` state, screen-aware `reset_widget`, and `clocks.event.warmup_display`. **Verified:** focused suites pass (schema 114, editor contract 30, spectator renderer contract 18, layout bridge + persistence + bridge warmup tests); full discovery run **750 tests, 15 failures, 3 errors** — the pre-existing inventory exactly, no regression; real pywebview run via `WindowHost` (editor → Pre-game → Matchup preset → add text → Save wrote schema 3 → practice spectator showed the pregame screen, then the halftime screen with "Warmup follows: 3:00" after a confirmed move to `HALF`). Also fixed the same day: the operator strip's `LAST:` line for a Field Assistant action now reads as plain language (`tests/integration/test_last_action_label.py`, 3 tests) and `clamp_layout` no longer reports a spurious adjustment for a widget that exactly touches the safe-area edge. | `src/scoreboard/presentation/layout.py`; `src/scoreboard/views/shared/board.js`; `src/scoreboard/views/spectator/`; `src/scoreboard/views/layout/`; `src/scoreboard/host/layout_bridge.py`; `src/scoreboard/host/bridge.py`; `tests/unit/test_layout_schema.py`; `tests/integration/test_layout_*`; `tests/integration/test_spectator_layout_render.py`; `tests/integration/test_last_action_label.py`; `.scratch/presentation-screens/spec.md` | Not verified: `tests/ui/` Playwright suites (no Node.js on this host), LED/hardware rendering. |
| September 6, 2026 | Deep-dive audit: I1 and I2 implemented | Rebuilt `.venv` from python.org CPython 3.11.9 (no longer Blender's bundled Python) and installed Node.js 24 LTS with a repo-local Playwright (`npm ci`, pinned 1.62.1) resolved by `tests/ui/browser_support.py` ahead of the old Codex runtime fallback. Rewrote the 12 mechanical legacy pregame/quarter-confirmation test failures to the documented behaviour (follow-ups 01 and 02) and marked the 3 tests blocked on question A-1 as explicit `@unittest.skip`s — correcting an earlier inventory that miscounted the A-1 bucket as four instead of three. Ran the three `tests/ui/` browser suites for the first time since the v2/v3 editor and the C3 halftime-board change, which found and fixed two real product defects: a pregame/halftime team-name overflow (`home_name`/`away_name` at `font_scale` 0.040 in a 0.30-wide box wrapped a 24-character name to four lines and overflowed; fixed to 0.024) and a layout-editor layers-rail click lost to a mousedown/mouseup rebuild race (`editor-panels.js` now morphs rows in place instead of replacing them). Added `tools/check_markdown_links.py` and `.github/workflows/ci.yml`. Full discovery run: **750 tests, 0 failures, 0 errors, 3 skipped** in 51 s; `compileall`, `pip check`, and the link check all pass. | `.venv`; root `package.json`/`package-lock.json`; `tests/ui/browser_support.py`; `tests/unit/test_commands.py`; `tests/integration/test_bridge.py`, `test_recovery.py`, `test_spectator.py`, `test_full_game_rehearsal.py`, `test_host_application.py`; `src/scoreboard/presentation/layout.py`; `src/scoreboard/views/shared/board.js`; `src/scoreboard/views/layout/editor-panels.js`; `tools/check_markdown_links.py`; `.github/workflows/ci.yml`; session output | Question A-1, lint/type-check config, and seeing the workflow run on GitHub remain open. The suite is now a usable Task 12-adjacent gate, with the standing caveat that a skip is not an A-1 answer. |
| Planned September 8, 2026 | Personal Windows laptop → HDMI processor input → full LED wall | Pending | Add photographs, screenshots, and notes | Determines whether Phase 0 can close and confirms the preferred system boundary. |

### Practice-only spectator test window — September 5, 2026

Added an **Advanced → Open test window** control for home practice and
side-by-side spectator-layout checks. It opens a fixed 640×360, bordered 16:9
spectator window with the real read-only snapshot bridge; it is deliberately
separate from the fullscreen production window, selected display, saved
preference, display watch, and health strip. Reopening the practice window
destroys its predecessor before creating a replacement, and operator shutdown
cleans it up with the other owned windows.

- Focused automated verification passed: 124 tests across the host, display,
  and bridge suites. It asserts the test window never resolves a target display
  or mutates configuration, action history, revision, or production health;
  receives live spectator updates; replaces its old handle; and is cleaned up
  at shutdown.
- The browser contract now checks the Advanced drawer opens and closes and its
  button reports success; it passed in headless Edge.

### Quarter and play-clock command refinements — September 5, 2026

- A quarter transition landing on `1st`, `2nd`, `3rd`, `4th`, or `OT` now
  loads a stopped 12:00 game clock only when the resulting value is exactly
  zero (using the clock's safe `<= 0.0` boundary). Nonzero values and PRE,
  HALF, and FINAL remain untouched. A clock-loading transition deliberately
  clears Undo because a quarter-only reversal could not restore the prior
  zero clock. OT follows the existing shared 12:00 default; no overtime rule
  was invented.
- The Play Clock now retains its plain stopped `25`/`40` loads and adds
  visually distinct `25 + START` / `40 + START` controls. Their new atomic
  command validates the same presets, loads, and begins counting down in one
  revision, avoiding a second request with a stale expected revision.
- Focused verification: 117 unit and bridge tests passed, including zero and
  nonzero quarter transitions, halftime, reverse navigation, Undo safety,
  invalid preset rejection without mutation, stopped and already-running
  preset-start behavior, and both mouse-control paths. `compileall` passed.

## Current Status

| Item | Current state |
|---|---|
| Active phase | Phase 2. Tasks 1-11 are implemented; Task 12 remains, together with the hardware evidence Task 10 could not produce here. Phase 0's hardware gate is open in parallel |
| Open phase gate | Personal laptop HDMI test on the complete LED wall |
| Confidence in preferred outcome | Approximately 90%, still unverified |
| Implementation status | Phase 2 Tasks 1-11 are substantially implemented; Task 12 remains. Task 10's policy is verified only against injected screen lists, not real two-display hardware. Current working-tree additions include C5, the presets half of F4, I4's bounded undo history, and F3's crowd-facing status message and countdown end to end. **C4 is reopened as partially implemented:** webview calls no longer hold the command lock, but the September 6 reconciliation found a cross-thread stale-offer race and one shared publisher worker can delay otherwise healthy windows. See [the current-project audit](docs/CURRENT_PROJECT_AUDIT_2026-09-06.md). |
| Automated suite | **Green at 913 tests, 0 failures, 0 errors, 3 skipped** (September 6, 2026, after F3 and I4), in 50.8 s from the repository `.venv` with Node.js on `PATH` and an isolated `SCOREBOARD_DATA_DIR`; `compileall` passed and the link checker found 0 broken relative links across 24 Markdown files. The 3 skips explicitly name open question A-1 and are not a pass on it. The earlier reconciliation run is kept below for lineage. **Green.** The September 6 reconciliation run from a clean temporary Python 3.11.9 environment, with Node.js on `PATH` and an isolated `SCOREBOARD_DATA_DIR`, reported **853 tests, 0 failures, 0 errors, 3 skipped** in 48.448 seconds. `compileall` passed, `uv pip check` found all 17 installed packages compatible, the repository checker found 0 broken relative links across 24 Markdown files, and `git diff --check` passed (line-ending notices only). The 3 skips explicitly name open question A-1 and are not a pass on it. Earlier 750- and 837-test runs remain historical milestones below. The repository-local `.venv` is currently broken because its configured base-interpreter path is stale; it was not used as evidence for this result. |
| Repository status | Work is on `feature/field-status` at `e1e3b04`, tracking `origin/feature/field-status`. The C4/C5/F4 pass and partial F3/implemented I4 pass are uncommitted working-tree work, including their new modules, tests, and active `.scratch/` specifications. The audit preserved every unrelated and in-progress change. |
| Testing follow-ups | All five findings under [`.scratch/testing-followups`](.scratch/testing-followups/spec.md) are resolved and retained as historical issue evidence. The approved pregame-to-first-quarter confirmation workflow is implemented; question A-1 is separate and still open. |
| Deep-dive audit | The September 5 fifteen-finding audit remains the original inventory. As reconciled September 6: C1-C3, C5, F3, I1-I3, and I4 are implemented; C4 is partial/reopened; F4's presets half is implemented while spectator visual identity remains open; F1, F2, F5, and I5 remain open. The point-in-time evidence and safe-removal review are in [the current-project audit](docs/CURRENT_PROJECT_AUDIT_2026-09-06.md). |

### Automated suite failure inventory (resolved September 6, 2026)

Originally recorded September 5, 2026 so a later session could tell a
pre-existing failure from a real regression without stashing and re-running.
On September 6, 2026, as deep-dive audit item I1, the 12 mechanical rows
below were rewritten to the documented behaviour and the 3 rows blocked on
question A-1 became explicit `@unittest.skip`s naming A-1; the browser
Node.js/Playwright errors were resolved by installing the tooling locally
(deep-dive audit item I2). Command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Current result as of September 6, 2026, from a clean temporary Python 3.11.9
environment with Node.js on PATH: **853 tests, 0 failures, 0 errors, 3
skipped** in 48.448 seconds, with `SCOREBOARD_DATA_DIR` isolated. The earlier
rebuilt-environment result was 750/0/0/3, before the current working-tree
features landed. The table below is now a
historical record of what each row was and how it was resolved, not a list
of expected failures to check a new run against.

Earlier discovery runs, kept for lineage: **712 tests, 15 failures, 3
errors** (September 5, 2026, after the deep-dive fixes; 597/15/3 before
them). Re-run the same day after the Field Assistant draft-ownership and
`PRE` corrections: **608 tests, 16 failures, 3 errors** — the same inventory
below, plus the `DataLocationTests` row, which failed on that host whether
or not `SCOREBOARD_DATA_DIR` was set (the default per-user root resolved to
`Scoreboard Logs`, not `Scoreboard`). No Field Assistant test failed. Re-run
again on September 5, 2026 after the volunteer-screen rebuild, the
`pywebviewready` bridge fix, and the `manual` action: **615 tests, 16
failures, 3 errors** — the identical inventory; the seven new Field
Assistant tests all passed.

| Count | Where | Why it failed | Owner | Resolution (September 6, 2026) |
|---|---|---|---|---|
| 2 | `tests/unit/test_commands.py` — `GameClockCommandTests.test_start_matches_the_engine_and_materializes_into_state`, `test_stop_matches_the_engine` | The tests expected a 12:00 first-quarter clock in `PRE`. The unified pregame clock (follow-up issue 01) makes Game Clock Start in `PRE` run the 30:00 countdown instead, so the engine reference was 1800.0 where the test wanted 720.0. | Follow-up 01 | **Rewritten.** Both tests now seed the reference clock from `default_state()` — the 30:00 pregame countdown — and pass. |
| 2 | `tests/unit/test_commands.py` — `ClockCouplingTests.test_game_clock_start_clears_a_running_play_clock`, `test_game_clock_stop_clears_a_running_play_clock_in_the_same_commit` | Whether a game-clock Start or Stop always blanks a running play clock is question **A-1**, still open with the owner and the officials. | Question A-1 | **Skipped, not rewritten.** Marked `@unittest.skip` naming A-1, so they show as skipped, never green. |
| 3 | `tests/integration/test_bridge.py` — the `quarter_forward`, `quarter_back`, and `set_quarter` subtests of `MousePathTests.test_every_command_reaches_the_service_through_the_bridge` | The subtests submitted a bare quarter command from `PRE` and asserted acceptance; follow-up issue 02 made every quarter move require confirmation, so the bridge now correctly returns `CONFIRMATION_REQUIRED` (or `QUARTER_OUT_OF_RANGE` moving back from `PRE`). | Follow-up 02 | **Rewritten.** Quarter commands are now sent with `confirmed: True`. |
| 1 | `tests/integration/test_bridge.py` — `ExpirationHistoryTests.test_game_clock_expiry_clears_a_running_play_clock_durably` | Same A-1 play-clock coupling question as above. | Question A-1 | **Skipped, not rewritten.** Marked `@unittest.skip` naming A-1. |
| 3 | `tests/integration/test_recovery.py` | Three `set_quarter` setup calls asserted `quarter == "2nd"`/`IN_PROGRESS` after a sequence that no longer leaves `PRE`, for the same reason as the bridge quarter subtests. | Follow-ups 01 and 02 | **Rewritten.** All three setup calls now pass `confirmed=True`. |
| 2 | `tests/integration/test_spectator.py` | Same `quarter`/`lifecycle` assertions as the recovery rows above. | Follow-ups 01 and 02 | **Rewritten**, plus two second-order corrections found while rewriting: undoing a confirmed `PRE`→1st move is `NOT_UNDOABLE`, and a Game Clock Start at the end of warmup does not by itself enter `IN_PROGRESS` — only an accepted quarter transition does, per `MVP_REQUIREMENTS.md` §4.3. |
| 1 | `tests/integration/test_full_game_rehearsal.py` | Asserted the event countdown reads `0:00` where the unified pregame clock now reads `30:00`. | Follow-up 01 | **Rewritten.** Pregame setup now uses `game_clock_start`, since the bridge sources the spectator event clock from the game clock while `PRE_GAME`; the countdown-to-`0:00` proof is unchanged. |
| 1 | `tests/integration/test_host_application.py` | Asserted a published game clock of `11:57` where the pregame clock now publishes `29:57`. | Follow-up 01 | **Rewritten** to `29:57`. |
| 3 errors | `tests/ui/test_spectator_browser.py`, `test_keyboard_browser.py`, `test_layout_editor_browser.py` | Node.js and Playwright were not installed on this host. These failed explicitly rather than skipping, by design. Not a code defect. | Development tooling | **Resolved.** Node.js LTS and a repo-local Playwright (`npm ci`) are now installed; all three suites run against the already-installed Microsoft Edge. Running them for the first time since the v2/v3 editor and the C3 halftime-board change surfaced two real product defects, fixed the same day — see the Decision Log entry above and the Improvements table (I1) below. |

Until the deep-dive fixes a sixteenth failure appeared whenever `SCOREBOARD_DATA_DIR` was **not** set: `tests/integration/test_persistence.py::DataLocationTests::test_the_default_root_is_an_absolute_per_user_location` called `resolve_paths()` with no override, and the resolver's documented order is override → environment variable → *the operator's remembered folder* → platform default, so the test was asserting against this machine's live `data-location.json` (`…\Desktop\Scoreboard Logs`). That was a test-isolation defect, not a resolver bug; the test now removes the remembered-folder layer for the call, and the count was 15 with or without the override even before the September 6 rewrite.

**How the 15 split, before the September 6, 2026 rewrite.** Twelve were mechanical: they asserted the pre-follow-up values (`720.0` where the unified pregame clock gave `1800.0`, `11:57` where it gave `29:57`, acceptance where a quarter move now returned `CONFIRMATION_REQUIRED`) and were rewritten to the documented behavior in an afternoon. Three were **blocked on question A-1** — the two `ClockCouplingTests` and `ExpirationHistoryTests.test_game_clock_expiry_clears_a_running_play_clock_durably` — because rewriting them means deciding whether a game-clock Start always blanks the play clock, which is a football-rules question for the owner and the officials, not a code decision. (An earlier revision of this section said four were blocked on A-1, counting "the play-clock half of `test_start_matches_the_engine_and_materializes_into_state`"; on reading, that test has no play-clock assertion, so the correct split is **15 = 12 + 3**, and that test is fully mechanical.) The three A-1 tests are now `@unittest.skip`, not rewritten, so the suite stays green without pretending A-1 is answered.

**None of the original 15 was a regression from the Field Assistant or the
presentation layout editor.** All were reconciling legacy pregame and
quarter expectations with the behavior that follow-ups 01 and 02
deliberately changed, which needed question A-1 answered first for the
three now-skipped tests — hence skips rather than rewrites for those three.


## Deep-dive audit — September 5, 2026 (fifteen findings)

A whole-project review after the Field Assistant, the v2 layout editor, and the local-time and football-state work landed. Four independent audits (core game-day reliability; operator workflow; spectator board and editor; engineering health) were run against the code, and every finding that reached this list was then re-verified by reading the cited code path, not only the report. Planned Phase 3 work (OBS, media, sponsors, animations, physical controller) is deliberately absent from "missing": those are scheduled, not gaps. **The five lightest findings (marked ✅) were implemented the same day; their results are recorded in the Status column.** I1 and I2 followed on September 6, 2026, and C4, C5, and the presets half of F4 later that day (all verified in focused suites, the full discovery run, and a real pywebview run — see each Status column). The remaining findings are open and ordered by priority within their category.

Ranking rule: **Critical** = can wrong the board or strand the operator during a live game. **Missing** = something a Friday night needs that no suite of the app provides. **Improvement** = makes the project safer or faster to change.

### Critical fixes

| # | Finding | Evidence | Weight | Status |
|---|---|---|---|---|
| C1 | A screen-enumeration exception at startup permanently killed the refresh loop. `_operator_loaded` called `open_spectator` unguarded before `start_refresh()`, which has exactly one caller; `available_displays` read `webview.screens` with no guard while the sibling `_read_device_names()` was guarded. Effect: no checkpoints for the whole game and a running clock frozen on both boards between button presses, with nothing in the log. | `host/app.py` `_operator_loaded`, `available_displays` | S | ✅ **Implemented.** `_operator_loaded` now catches the exception, records it as `unhandled_error(context="open_spectator_at_startup")`, marks the display closed with `needs_selection=True` so the health strip offers Reopen/pick, and **always** calls `start_refresh()`. Verified: `tests/integration/test_display_selection.py::StartupGuardTests` (2 tests). The failing-screens test was run with the source change stashed and **errors without the fix** (the exception escapes `_operator_loaded`, which is the bug); the healthy-startup test proves the guard does not swallow a good open. |
| C2 | "Choose folder…" opened a modal OS dialog while holding the command lock — the same `RLock` every score/clock/quarter command and the refresh tick need. For as long as the dialog stayed open the board froze at a stale time while real time advanced. Always-visible button, not gated to pregame. | `host/bridge.py` `choose_data_folder`; `host/app.py:244,257` | S | ✅ **Implemented.** The picker now runs outside the lock; only the bookkeeping afterwards (diagnostics entry, view payload) takes it. Verified: `tests/integration/test_data_folder.py::BridgeFolderTests::test_the_open_picker_does_not_hold_up_the_game` — a "dialog" that submits a real `game_clock_start` from another thread before returning; the command completes inside the 2-second window, is accepted, and the clock is running. Run with the source change stashed, the test **fails without the fix**. |
| C3 | The board showed no score at all during halftime. `spectator.js` hid `#game-board` for `PRE_GAME`/`HALFTIME` and `#event-board` carried only phase, title, countdown, and warmup. For a whole intermission the stadium's only scoreboard was scoreless. No document deferred this. | `views/spectator/index.html`, `spectator.js:23-25` | S | ✅ **Implemented.** The event board now carries both team names and both scores beneath the countdown as plain `data-field` spans (`teams.home.name`, `teams.home.score`, `teams.away.score`, `teams.away.name`), bound by the same `bindFields` pass as everything else — nothing computed on the spectator side. D-001 amended. Verified: `tests/integration/test_spectator_layout_render.py::EventBoardScoreTests` (2 tests) pins the four bindings and that they are bound, not computed; the page still carries no control or forbidden token. The rendering was checked in a browser against a `HALFTIME` snapshot (Decision Log). The Playwright viewport matrix (`spectator.cjs`) was **not** extended or run — no Node.js here. **Update, September 6, 2026:** the Playwright viewport matrix now runs (I2) and, on its first run against these bindings, found that `home_name`/`away_name` used `font_scale` 0.040 in a 0.30-wide box, so a 24-character name (F-010's maximum) wrapped to four lines and overflowed the box at every viewport. Fixed by lowering both to 0.024 in `presentation/layout.py`'s `_EVENT_WIDGET_GEOMETRY` and the `board.js` mirror, which wraps a maximum-length name to two lines inside the box (the game board's own name widgets already used 0.028 in a 0.38 box). `spectator.cjs`'s text-inside-box tolerance was also widened from 0.5px to 1px, because a `Range` rect around inline text sits ~0.8px above its flex box at line-height 1.15 — font ascent, not visible overflow. |
| C4 | Every 100 ms tick previously blocked unboundedly on WebView2 while holding the command lock. | `host/app.py`; `host/publisher.py`; `tests/integration/test_publish_off_lock.py` | M | ⚠️ **Partially implemented; reopened September 6, 2026.** The important isolation is real: immutable batches are built under `_command_lock`, all webview delivery happens after release, commands keep completing during a stalled UI, backup copying is cadence-bounded, and failures are contained/logged. The completion claim was too strong, however. `_publish_lock` protects only the stale-key check/update and is released before per-window offers, so two delivery threads can interleave an older spectator offer after a newer one; the current serial tests do not force that schedule. `WindowPublisher` also uses one worker for all window names, so one blocking delivery delays later offers to healthy windows even though it cannot block core state or persistence. C4 remains open until delivery is ordered atomically per batch or independently per window and a forced-interleaving regression test proves the contract. `publish_layout()` is also still a direct layout-bridge webview call, outside the command lock. |
| C5 | The display-recovery path is the hardest thing on screen to hit. `Reopen Display` is 32 px against the project's own 44 px floor (`operator.css:63-71` concedes it); the display selector and data-folder controls live inside the **Corrections** drawer, one panel from destructive score/time Apply buttons. When the wall goes dark a volunteer must think to open *Corrections*. | `views/operator/operator.css:63-71`, `index.html:123,212`; `docs/UX_AND_LAYOUT.md` §8 | M | ✅ **Implemented (September 6, 2026).** `Reopen Display` is 44 px (`min-height: var(--touch)`), and an always-visible 44 px `Display…` button beside it opens a new **Spectator display** drawer (`#display-drawer`): status chip and detail, a second 44 px Reopen, the saved display with Forget, and the available-display buttons (44 px). The selector rows left the Corrections drawer; a `Reopen Display` that finds no display now opens this drawer instead of Corrections. The data-folder row stays in Corrections (unchanged, still the revisit named in `UX_AND_LAYOUT.md`). Verified: `tests/integration/test_display_drawer_contract.py` (5) and the extended reachability test in `test_display_selection.py`; Playwright/Edge at 1093×614 and 1180×720 (both buttons 44 px, `scrollHeight == clientHeight`, every clock button inside the viewport, header not overflowing, screenshots `c5-1093x614.png`/`c5-1180x720.png` in the scratchpad); and the real pywebview run above (1164×681 window: both buttons 44 px, no overflow, drawer opens with the live display list at 44 px). `UX_AND_LAYOUT.md` §4, §6.8, §8 updated; the 32 px concession is gone. |

### Missing features

| # | Finding | Evidence | Weight | Status |
|---|---|---|---|---|
| F1 | No horn — no audible end-of-period or play-clock-expiry signal anywhere (a search of `src/` for audio, horn, or sound finds nothing). Officials enforce delay-of-game off an audible cue; every commercial scoreboard has one. Excluded from the MVP (F-045) but in **no** Phase 3 workstream — unowned. | `docs/MVP_REQUIREMENTS.md` F-045, §11 | M | Open. Needs an owner decision on the sound source (laptop audio vs. stadium PA) before design. |
| F2 | No overtime workflow. `QUARTER_LABELS` has a single `"OT"` (`domain/state.py:57-65`); no OT2+, no OT period length, and the Field Assistant refuses every action in OT pending local overtime rules (`FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` §7). The operator goes fully manual at the moment pressure peaks. | `domain/state.py`, `domain/field_assistant.py` | M–L | Open. **Blocked on an owner/officials decision** about the local overtime procedure. |
| F3 | No usable crowd-facing `FLAG`, `TIMEOUT`, `INJURY`, or `DELAY` status and no authoritative status countdown. When play stopped the board froze with no explanation; while a penalty was being worked in the Field Assistant the wall still showed the old down and distance. The v2 editor's free text is decorative and pre-positioned, not a live toggle (§10.8). | `domain/state.py`; `domain/clocks.py`; `domain/commands.py`; `application/service.py`; `host/bridge.py`; `presentation/layout.py`; `views/shared/board.js`; `views/operator/*` | M | ✅ **Implemented (September 6, 2026).** `GameState` additively carries `game_status` (one of `FLAG`/`TIMEOUT`/`INJURY`/`DELAY`, or `None`), a `status_clock`, and `status_clock_cleared`; a new `StatusCountdown` engine in `domain/clocks.py` mirrors `PlayClock`'s monotonic/deadline math with 30/60/90-second presets. Four commands — `set_game_status`, `clear_game_status`, `status_clock_start`, `status_clock_stop` — reach it through the normal airlock; `set_game_status` with `seconds` raises the message *and* starts the countdown in **one revision**, the `play_clock_preset_start` precedent. The two `status_message`/`status_clock` game widgets are `OPTIONAL_WIDGET_IDS`, so they are hidden — not drawn as empty boxes — until a status is raised, and the board is unchanged from before F3 in normal play. An always-visible operator crowd row (not a drawer: a message you must open a menu to raise does not get raised during a game) carries a chip, one button per message, `CLEAR`, the countdown, and Start/Stop. **Three deliberate limits:** the wall shows the status word only, with no team name (the default board has no free space that holds `TIMEOUT — ` plus a 24-character name legibly, and `timeout_used` already records which team); the four commands are in **neither** `UNDOABLE_COMMANDS` nor `NON_UNDOABLE_COMMANDS`, so a crowd toggle can never push a scoring mistake out of Undo's reach; and the Field Assistant does not raise `FLAG` automatically, because opening a draft window must not mutate authoritative state. Verified: `tests/unit/test_status_clock.py` (16), crowd-status command/formatting/state/bridge tests, `tests/integration/test_crowd_status_ui.py` (16 source-contract), the `board.js`↔Python mirror contract with the two new ids, and a **real-bridge Playwright/Edge end-to-end run**: pressing `TIMEOUT` cost exactly 1 revision, produced `status.label == "TIMEOUT"` with a running `1:00`, rendered on the operator chip and countdown, and drew both widgets on the spectator board — while clearing the status hid both again. A `set_game_status` inserted between `add_score` and `undo` left the undo depth at 1 and Undo still reversed the score, with the message left standing. Also proved in the **real pywebview/WebView2 runtime** (`.scratch/f3-i4/realrun_f3i4.py`, 17/17 checks): in the shipped 1180x720 window the crowd row exists with no vertical or horizontal overflow (681 = 681), every crowd button clears 36px, C5's 44px Reopen Display is untouched, and clicking `TIMEOUT` raised the message and a running countdown in one revision. Full suite green at **913 tests, 0 failures, 0 errors, 3 skipped**. |
| F4 | No team presets, colours, or logos. Both names are retyped from a blank state every week (F-010); `GameState` carries no team colour, logo, or abbreviation; the v2 editor has *layout* presets but no *team* presets. | `domain/state.py`; `presentation/layout.py` presets | S–M (presets) / L (visual identity) | ✅ **Presets implemented (September 6, 2026); visual identity on the wall deliberately not.** New `teams.json` library (`infrastructure/teams.py`, `host/teams.py`: name ≤ 24, short name ≤ 6, two `#RRGGBB` colours, up to 64 teams, atomic writes, never stops the scoreboard) is surfaced as a **Teams ▸** drawer. Applying one still uses the confirmed `set_team_name` command; library actions advance no game revision. The operator shows each side's matching colours/short name, and all views carry identity metadata for later presentation binding, but nothing on the wall changes yet. Verified by `test_team_library.py` (32), `test_team_presets.py` (14), `test_team_bridge.py` (6), `test_team_presets_ui.py` (10), Playwright/Edge, and a real pywebview development-host run. |
| F5 | No game log or box-score export. The durable action history exists (P-007) but nothing surfaces a printable summary for the paper, PA, or next week's prep. The knowledge base names "Game log" and "Export" explicitly. | `infrastructure/persistence.py` action history | M | Open. I3 (implemented, below) is the first step: the operator can at least now find the log. |

Just below the line: automatic timeout reset at halftime (B-1, silent today — a forgotten reset misreports both teams all second half; S, blocked on B-1), and a second operator / remote control (Phase 4, L).

### Improvements

| # | Finding | Evidence | Weight | Status |
|---|---|---|---|---|
| I1 | The suite is not a release gate: 15 legacy failures, one test that read the operator's live config, three browser checks that cannot run here, and no CI, lint, or type-check anywhere (no `.github/`, no ruff/mypy/pyright config). | "Automated suite failure inventory" above | 11 mechanical rewrites S; A-1 bucket blocked; CI S | ✅ **Implemented (September 6, 2026).** The 12 mechanical failures were rewritten to the documented behaviour (correcting an earlier miscount that called this bucket 11/4 instead of 12/3 — see "Automated suite failure inventory"); the 3 tests blocked on A-1 are now explicit `@unittest.skip`s naming A-1, so they show as skipped, never green. `tests/ui/` now runs against a repo-local Playwright (`npm ci`) launching the already-installed Microsoft Edge; running it for the first time surfaced and fixed two real product defects — the halftime/pregame team-name overflow folded into the C3 row above, and a layout-editor layers-rail click lost to a mousedown/mouseup rebuild race (`editor-panels.js`). New `tools/check_markdown_links.py` and `.github/workflows/ci.yml` (one `windows-latest` job: setup-python 3.11, editable install, `pip check`, `compileall`, setup-node, `npm ci`, the link check, then the full suite) exist but the workflow has **not** yet been seen to run on GitHub — the branch is unpushed. Full discovery run September 6, 2026: **750 tests, 0 failures, 0 errors, 3 skipped** in 51 s. Still open: answering A-1, and lint/type-check config (still no ruff/mypy/pyright). |
| I2 | The dev environment is not reproducible: `.venv/pyvenv.cfg` points at **Blender 4.5's bundled Python**, documented nowhere, and the pins were validated against that build; Node/Playwright resolve only from a Codex runtime cache. | `.venv/pyvenv.cfg`; `tests/README.md` browser section | S (document) / M (rebuild) | ✅ **Implemented (September 6, 2026).** `.venv` was rebuilt from python.org CPython 3.11.9 (`winget install --id Python.Python.3.11 --exact --scope user`, which also installs the `py` launcher at `C:\WINDOWS\py.exe`); `.venv\pyvenv.cfg` now points at the python.org install, not Blender. `pip check` is clean and the pinned set in `pyproject.toml` installed unchanged. Node.js 24 LTS (v24.19.0) was installed via `winget install --id OpenJS.NodeJS.LTS --exact`; a new root `package.json`/`package-lock.json` (private, devDependencies only, Playwright pinned 1.62.1) lets `npm ci` install Playwright into `node_modules/` (gitignored), and `tests/ui/browser_support.py` now resolves it from `node_modules` first, an explicit `NODE_PATH` second, and the old Codex desktop runtime bundle only as a last resort, raising a clear message naming `npm ci` when Playwright is missing entirely. Nothing here ships with the app (W-002 unchanged); documented in `tests/README.md`. A new developer machine now needs: Python 3.11 (python.org) and Node.js LTS, then `py -3.11 -m venv .venv`, `.\.venv\Scripts\python.exe -m pip install -e ".[build]"`, `npm ci` — Edge is already on Windows. |
| I3 | No way for the operator to find the diagnostics log. `diagnostics.py` keeps a bounded rotating log of every accepted command, expiry, display event, and failure, but nothing in the window pointed at it; after a bad night the only path was knowing `%LOCALAPPDATA%\Scoreboard\logs`. | `infrastructure/diagnostics.py`; `views/operator/*` | S | ✅ **Implemented.** `ScoreboardBridge.open_logs_folder()` — a host action that opens the log's folder in Explorer through an injectable opener, advances no revision, leaves a running clock running, writes a `logs_folder_opened` diagnostics note, reports rather than raises when Explorer refuses (and still tells the operator the path), and says so plainly when there is no log file. Surfaced as **Advanced ▸ Diagnostics ▸ Open logs folder** with a hint that opening it changes nothing. Verified: `tests/integration/test_logs_folder.py` (4 tests). The button's click path in `operator.js` follows the existing host-action pattern and was **not** browser-tested here. |
| I4 | One global one-level Undo originally covered scoring, quarter changes, and Field Assistant composite plays alike (F-014); the `LAST:` strip showed only that entry. A second action of any kind — including an accidental shortcut — foreclosed fixing the first, with no view of what was being given up. | `domain/commands.py`; `application/service.py`; `host/bridge.py`; `views/operator/*` | M–L | ✅ **Implemented (September 6, 2026).** `ScoreboardService` keeps an in-memory LIFO stack of at most `MAX_UNDO_DEPTH` (20) reversible entries instead of one; `undo_entry` still returns the newest so every existing caller is untouched, and a new `undo_history` feeds `undo_history`/`undo_depth` in the operator view. Undo is still a new logged forward command: a new `_Transition.pops_undo` flag pops exactly the entry Undo reversed, which is **required** because `UNDO` is itself in `NON_UNDOABLE_COMMANDS` and the generic barrier path would otherwise wipe the very stack a second Undo exists to reach. **The barrier is deliberately kept:** a command that cannot be undone still clears the whole stack and answers `NOT_UNDOABLE`, because letting Undo silently skip past it to reverse something older is the failure mode this finding is about — what was missing was stacking *undoable* actions and being able to see them. The `LAST:` strip became the button that opens a new Undo-history drawer (newest first, next-Undo marked, its own Undo button) with a `×N` depth badge, so no tool-bar button was added to a bar already at its width budget (C5). The stack is in-memory only; recovery restores none of it. Verified: `UndoHistoryTests` and `UndoHistoryViewTests`, `tests/integration/test_crowd_status_ui.py::UndoHistoryUiTests`, and a real-bridge Playwright/Edge run in which two scores stacked newest-first (`AWAY score 0 → 3`, `HOME score 0 → 6`), the drawer marked the first as next, and two Undos walked the board back to 0–0. Regression-proved: with `service.py` stashed the new tests fail. The same real pywebview run above covered I4 too: two scores stacked newest-first, the `LAST:` strip opened the drawer, it marked the next Undo, two Undos walked the board back to 0-0, and the raised crowd message was never spent by either. |
| I5 | Field status has zero keyboard coverage (`keyboard.js:4-22`) — the most frequent per-play update when the Assistant is not used is mouse-only through a drawer — and the same five fields have two different manual-entry UIs (Field drawer one-at-a-time Sets vs. the Assistant's bundled "Fix manually"). A stale Assistant draft is signalled only inside its own window, never in the main health strip. | `views/operator/keyboard.js`; `views/field_assistant/index.html:168-189` | M | Open. |

A smaller v2-editor note recorded here rather than lost: `preview_layout` round-trips to Python on every keystroke and colour-picker tick (`views/layout/layout.js:600-643`), which the v2 spec meant to avoid; debounce it or validate on commit only.

**What the audit found healthy, so it need not be re-audited next time:** the core state machine (commands and ticks serialized under one `RLock`, no interleaving), deadline-based monotonic clock math, atomic persistence with backup, the shared renderer (no throw path on a bad layout, atomic layout swap, last-good layout kept if a pushed one is invalid, no listeners to leak), the editor's zero paths to a game command across all six files, and image bounds enforced on raw base64 length before decoding (2 MB each, 6 MB per layout).

## Owner-requested next scoreboard work

These requests are recorded as follow-up scope, not as evidence that Phase 2 is
complete. The current MVP acceptance work, hardware gate, and fallback
requirements remain in force.

### 1. Human-readable local time — ✅ implemented September 5, 2026

Human-facing timestamps shown during startup/recovery must be converted to
Eastern local time (`America/New_York`), including daylight-saving changes, and
rendered in a clear format such as `September 5, 2026 at 10:41 AM EDT`. This
primarily applies to the first recovery screen's `Last saved` value and any
other operator-visible saved/checkpoint timestamps discovered during the
implementation. Internal elapsed-time calculations remain monotonic, and
machine-readable logs/storage may retain an unambiguous timestamp representation
as long as the operator-facing value is local and easy to read.

See "Phase 2 owner request 1 — human-readable local time" above for evidence.

### 2. Expanded football state and controls — ✅ implemented September 5, 2026

After the local-time presentation is corrected, add authoritative state,
validated commands, operator controls, spectator display fields, persistence,
recovery, and action-history coverage for the football information operators
need during a game:

- ball on / current yard line;
- to go / distance;
- current down;
- timeouts remaining for home and away;
- possession;
- any additional field identified by the requirements review that is necessary
  for a usable football scoreboard, without silently adding statistics or
  production-media features.

The implementation must preserve the existing architecture: Python remains the
authoritative state owner, all mutations use validated commands, both views
render complete snapshots, and optional display failure cannot stop operation.
Rules and defaults that depend on local officials or league practice must be
documented as decisions or provisional values before live use.

See "Phase 2 owner request 2 — expanded football state and controls" above for
evidence, and the B-1 through B-4 open decisions it records for officials/owner
confirmation before live use.

### 3. Presentation layout editor — ✅ v1 delivered September 5, 2026

Requested as separate scoreboard editor work for safely changing text sizes,
positions, colors, and related spectator-only presentation properties, on the
condition that the editor never become an authority for game state and never
block the basic offline scoreboard. Delivered after items 1 and 2, as scoped:
the editor advances no state revision, submits no command, and writes no
action-history row. Full evidence is under "Phase 2 owner request 3 —
presentation layout editor" above; the operator-facing description is
`docs/UX_AND_LAYOUT.md` section 10, and the schema is
`src/scoreboard/presentation/layout.py`. Rebuilt as the v2 canvas editor the
same day, and extended on September 6, 2026 so the pre-game and halftime
screens are editable too (schema v3; "Phase 2 owner request 4" above).

Delivering it early does **not** advance Phase 3 as a whole. Every other
Phase 3 workstream — OBS, cutscenes, media playback, sponsors, the visual
system, and source switching — remains deferred.

### 4. Field Assistant — delivered for rehearsal, September 5, 2026

The owner requested a separate, similarly sized end-of-play Field Assistant to
reduce the burden of manually operating clocks while also updating ball spot,
down, distance, and possession. The existing operator screen and its manual
field-status logic remain the fallback and are unchanged. The rules,
workflow, and test matrix are documented in
[`docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`](docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md),
whose status line now reads implemented (with one recorded amendment) rather
than "proposed design."

**What was built.** A separate, optional `pywebview` window (1180×720,
minimum 1024×600), opened deliberately from a **Field Assistant** button on
the operator toolbar, never replacing the manual field-status drawer.
`domain/field_assistant.py` holds pure rules only (coordinate conversion,
series/line-to-gain, normal play, incomplete pass, penalty ±5/±10/±15
shortcuts with repeat/count/automatic-first/no-play/decline, explicit
turnover, touchdown/try/field-goal/safety/kickoff transitions, and a proposed
turnover on downs); it performs no I/O and touches neither clock. One new
composite command, `finalize_field_action` (undoable), carries the validated
result through `application/service.py` in one expected-revision check, one
durable history row, one revision increment, and one complete published
snapshot; clock values and running flags are explicitly untouched. Two
additive state fields (`assistant_first_quarter_home_direction`,
`assistant_line_to_gain`) and an additive `assistant` snapshot block recover
safely from a pre-Field-Assistant saved game. `host/bridge.py`'s
`FieldAssistantBridge` exposes `get_snapshot`/`preview_field_action`/
`finalize_field_action`; the helper UI shows a draft ball-spot readout
distinct from the current authoritative status, on-screen nudge buttons plus
arrow keys, per-workflow controls, a single Preview-then-Confirm action, and
the stale-draft banner `FIELD STATUS CHANGED ELSEWHERE — RE-SYNC REQUIRED`,
which disables Confirm until the operator re-syncs or discards.

**A rules correction made during implementation.** Section 3.2 of the rules
document originally said the offense direction in the private absolute
coordinate flips every quarter. Because that coordinate is label-based (`0`
is always the HOME goal line, `100` the AWAY goal line — section 3.1), a
literal per-quarter flip was internally inconsistent and would have moved a
2nd-quarter HOME gain toward HOME's own goal line. The implemented rule
instead fixes each team's direction in the label coordinate (HOME always
`+1` toward the AWAY goal line, AWAY always `-1`), and the operator's
first-quarter choice records only which side of the on-screen drawing HOME
attacks toward in the 1st quarter; the drawing mirrors at each quarter
boundary (`home_goal_side`), while stored ball spots and line-to-gain never
move at a quarter change. OT remains manual-only. The rules document's
Amendments note and its FA-02 test-matrix row record the original wording and
the correction; see the Decision Log below.

**Verification performed.** `tests/unit/test_field_assistant.py` covers the
pure rule matrix (FA-01 through FA-18, including the corrected direction
behavior); `tests/unit/test_commands.py` and `tests/unit/test_state.py` add
composite-command, undo, clock-isolation, additive-state, and
old-snapshot-recovery cases; `tests/integration/test_bridge.py`'s
`FieldAssistantBridgeTests` cover read-only preview, stale-draft refusal, and
unchanged manual controls; `tests/integration/test_field_assistant_rehearsal.py`
covers atomicity, undo, recovery, a simulated persistence failure, and a
multi-quarter rehearsal sequence (FA-17/18/21-25/28);
`tests/integration/test_field_assistant_window.py` exercises host window
lifecycle (open/close/reopen, a helper push failure destroying only the
helper, operator shutdown closing it) against pywebview-shaped fakes, not a
real window.

The three Field Assistant modules ran **29 tests** together at delivery —
rules 19, finalize rehearsal 6, window lifecycle 4 — counted from an actual run
on September 5, 2026, not estimated; the corrections recorded below bring that
to 35. Together with the presentation layout
editor's 100, that is the 129 focused tests recorded in commit `274119d`.

**Corrections after first operator use (September 5, 2026).** The window as
first delivered could not finalize anything. The helper re-seeded its draft
ball from the authoritative spot on any refresh push with no accepted preview
and no pointer held down, and the host pushes a complete snapshot ten times a
second, so the ball returned to the persisted spot — `HOME 50` at the start of
a game — within 100 ms of every nudge, arrow key, drag, or yard selection;
Re-sync re-armed the overwrite rather than helping. Separately, the calculator
accepted only the four regulation quarters, while a game's persisted quarter is
`PRE` until the operator advances it, so every preview at the start of a game
failed with "quarter must be a regulation quarter or OT". Both are fixed: the
draft ball is re-seeded only on open, on Re-sync, and after a committed action
(a quarter boundary may re-draw the same spot on the mirrored side, never move
it), and `PRE` is now one of the assistant's quarters, treated as "before the
1st quarter" with the same rules direction and drawing side the 1st quarter
will use, without finalizing ever advancing the quarter. `HALF`, `OT`, and
`FINAL` remain manual-only. Every operator change now also re-previews
automatically, so the Proposed panel always describes the ball on screen, while
Confirm remains a separate press that a stale draft disables. The rules
document's Amendments note records both defects and their fixes, and its
FA-29/FA-30 matrix rows cover them.

**Verification of those corrections.** `tests/unit/test_field_assistant.py`
adds the `PRE`-as-first-quarter and `HALF`/`OT`/`FINAL`-stay-manual cases;
`tests/integration/test_field_assistant_window.py` adds a
`FieldAssistantDraftOwnershipTests` source contract asserting that no refresh
push re-seeds the draft, that exactly four sites arm a re-seed, that operator
changes ask Python for a fresh preview, and that the draft envelope still
carries no calculated football value. The three Field Assistant modules now
run **35 tests** together. The behavior was also exercised in a browser
against the real page with a stubbed bridge: a real mouse drag and the nudge
buttons held their spot across hundreds of simulated 10 Hz pushes, one preview
was requested per drag on release, a mirrored `home_goal_side` push re-drew the
same spot on the other side, a revision change still raised the stale banner
and disabled Confirm, and Re-sync and a committed action each re-seeded from
authority. That is a browser-automation claim on this development host, not a
WebView2 or live-operator claim.

**Second correction, September 5, 2026 — the bridge was never attached, and
the screen is rebuilt for volunteers.** The owner's second attempt still
could not finalize anything: Confirm stayed disabled with no message. A harness
that launches the real application under pywebview/WebView2, opens the helper
through the operator bridge, and presses the actual buttons with
`evaluate_js` showed the cause in one run: `field_assistant.js` listened for
`pywebviewready` on `document`, pywebview dispatches it on `window`, so the
page ran with a null bridge and every preview returned before reaching Python,
while the 10 Hz `applyView` pushes kept the window looking alive. The same
harness run with the old script never enabled Confirm; with the fix it did.
The owner's verdict on the screen itself — too hard for a volunteer with five
minutes of training, no obvious path for kickoffs/punts, no intuitive manual
override — drove a rebuild: one panel at a time (direction asked once in plain
words; "who has the ball" for every series start including kickoff returns;
then "click where the ball ended, press what happened"), the Confirm label
carrying the previewed result, a single **OTHER TEAM'S BALL HERE** for every
explicit change of possession, and a **FIX MANUALLY…** panel backed by a new
`manual` action that Python validates (team, down, distance or Goal, clicked
spot; only the line to gain is derived) and commits through the same atomic
command. The yard numbers, which had drifted off their lines, are positioned
by percentage. The rules document's Amendments entry, its rewritten section 4,
new section 4.6, the `Manual set` transition row, and FA-31 record this.

**Verification of the second correction.** `tests/unit/test_field_assistant.py`
adds FA-31 (`manual`: line to gain per down/team/quarter, goal-to-go, clamping
at the goal line, every rejection); `tests/unit/test_commands.py` adds the
service round trip (preview → finalize, one revision, persisted
possession/down/distance/ball/line-to-gain); `tests/integration/test_field_assistant_window.py`
adds the `window`-level `pywebviewready` contract and the one-panel-at-a-time /
Confirm-label contract. The full discovered suite reports **615 tests, 16
failures, 3 errors** — the documented inventory, no regression. The real-runtime
harness (development host, pywebview 6.2.1 on WebView2, isolated data folder)
drove seven consecutive commits — direction, opening series at HOME 25, a play
to HOME 32 (2nd & 3), a punt to AWAY 20, a manual AWAY 3rd & 4 at AWAY 40, an
AWAY touchdown, a +1 try, and a kickoff return at HOME 30 — with the DOM and the
persisted state agreeing at every revision (final: HOME 0, AWAY 7, REV 7). That
is a WebView2 claim on this development host, not a target-laptop or
live-operator claim.

**Deliberately manual, not implemented:** OT direction, onside/blocked
kicks, defensive try returns, offsetting/multiple penalties, enforcement from
a different spot, automatic possession flips, any clock change, live ball
tracking, networking, OBS, LED, and physical controllers all remain the
documented manual escape hatch.

**Remaining evidence before game-day use.** A physical 1366×768 at
100%/125% visual check and a live operator rehearsal with volunteers have not
been performed. Native WebView2 rendering and the full press-by-press flow
have now been exercised on the development host by the real-runtime harness
described above, not on the target laptop. This is separate
from, and does not advance, Task 12, the Phase 0 HDMI gate, or any other
stadium-readiness item in this document.

## Next Action

**On Tuesday, September 8, 2026, perform the personal-laptop HDMI test and capture the minimum Phase 0 evidence.** That test is on a fixed date, it is the only remaining Phase 0 gate, and the stadium half of Task 10's acceptance depends on it. Nothing else on this list is time-boxed.

Then, in order:

1. **Work [the two-display checklist](docs/DISPLAY_CHECKLIST.md) on a real two-monitor machine.** This is now the largest single gap in Phase 2. Task 10 is implemented and its policy is tested, but nothing has been placed on a second display, no HDMI cable has been unplugged, and no resolution or scaling change has been observed. Every box in that file is open.
2. **Answer question A-1** from the audit — whether a game-clock Start should always blank the play clock, given that the game clock also starts on the ready-for-play. This is a football-rules question for the owner and the officials, not a code decision, and it affects the stadium's only play-clock display. It is the one open item that can visibly mislead the field.
3. **Finish C4 publication ordering.** Preserve the command-lock isolation, prevent a stale per-window offer after a newer batch, isolate healthy-window delivery from a stalled sibling, and add a forced-interleaving regression test.
4. **Rebuild the package from the reconciled working tree, then work `docs/PACKAGING.md` on the target laptop** — clean machine, network disabled, SmartScreen, startup time. The documented September 5 build predates C4/C5/F3/F4/I4 and `dist/` is absent.
5. **Task 12 — sustained rehearsal and recovery acceptance**, which closes Phase 2 together with the stadium display rehearsal.

All four owner-requested items below are delivered: the local-time
presentation and the expanded football fields (items 1 and 2) are implemented
and tested, the presentation layout editor (item 3) shipped v1 on
September 5, 2026, and the Field Assistant (item 4) is delivered for
rehearsal. None of the four advances Task 12 or the hardware and stadium
evidence above, which remain the only ordered work left in this list.

Carried forward as open items, none of which may be treated as completed on the strength of a passing automated suite:

1. **Two-display and stadium behaviour.** Owned by the checklist above. This host exposes one display, so placement, fullscreen on a second screen, unplug and replug, Windows re-enumeration timing, resolution and scaling changes, and the processor's recovery behaviour are all unverified. The two-second display-check cadence was reasoned about, not measured against real re-enumeration.
2. **Recovery rehearsal.** The in-window choice is implemented and tested at the host boundary; native interaction on the target laptop remains release evidence.
3. **The physical 1366×768 check.** The layout has twice been measured in Chromium at the equivalent CSS viewports, most recently after the Task 10 health-strip change, but never on a 1366×768 Windows display at 100% and 125% scaling under WebView2. The 44×44 target for `Reopen Display` is now met (C5, September 6, 2026) and was measured at 44 px in Chromium at both equivalent viewports and in a real WebView2 window on this host; the physical-display check remains open.
4. **Real operating-system failure behaviour.** Interrupted transactions, write failures, and forced termination are proven as code paths against simulated failures; a real power loss or full disk on the target laptop is release evidence.
5. **Keyboard release evidence.** Verify numpad, real Windows repeat timing, novice shortcut rehearsal and focused-window behavior on the target laptop.
6. **Visible latency.** Measure command-to-visible-pixels latency on the target laptop; immediate push counts remove scheduler waiting but do not prove D-004 end-to-end.
7. **Clock tolerance on the target laptop (R-005).** A 12-minute real-time run on the development host finished 0.000179 s from an independent reference with 0.0060 s of drift across 401 pause/resume cycles, so the engine has no accumulation. The tolerance itself must still be established on the production laptop, under the real refresh loop and a real WebView2 window.
8. **Sustained soak (R-006).** The fake-time rehearsal covers a game-length command sequence but no real elapsed time. The two-hour soak and the four-quarter run on the target laptop stay open.
9. **Browser tooling on this host — resolved September 6, 2026.** Node.js LTS and a repo-local Playwright (`npm ci`) are now installed, and all three `tests/ui/` suites (spectator, keyboard, layout editor) run against the already-installed Microsoft Edge through Playwright's `msedge` channel. Running them for the first time since the v2/v3 editor surfaced and fixed a real spectator name-overflow defect (see the C3 and I1 entries above) and a real layout-editor layers-rail click-loss defect (I1). Not done: a real pywebview/WebView2 window run of the layers-rail fix — only the Playwright/Edge run.
