# High School Football LED Scoreboard

This repository contains the Phase 2 implementation of a reliable, offline-capable football scoreboard and future stadium video-production system. The immediate product is intentionally small: a Windows application that a student or volunteer can operate under game pressure and display fullscreen through the stadium's existing HDMI video processor.

A working scoreboard now runs from this repository on a development Windows host: authoritative state, both clocks, the event countdowns, persistence and recovery, the operator window, the fullscreen spectator window, the Field Assistant helper window, and the presentation layout editor. It also builds into an offline Windows package. It is **not** yet a release: display selection is implemented but lacks real two-display evidence, the sustained rehearsal is open, and no result on the stadium wall has been recorded.

## Current status

- **Phase 0 — discovery and feasibility:** substantially complete, with the critical stadium HDMI test still open.
- **Phase 1 — repository, requirements, layout, and architecture:** documentation foundation created; owner decisions and field evidence remain open.
- **Phase 2 — core MVP:** implementation tasks 1–11 are substantially implemented, plus three owner-requested additions delivered after them (spectator local time, the expanded football state fields, and the presentation layout editor) and the Field Assistant. The current Bundle A workflow passes focused verification. The full discovered suite runs 712 tests with 15 failures and 3 errors: the 3 errors are the `tests/ui/` browser checks on a machine without Node and Playwright, and the 15 failures are all legacy pregame/quarter expectations that the unified pregame clock (`.scratch/testing-followups/issues/01`) deliberately changed and that have not yet been rewritten. **No failure is a regression from the Field Assistant or the layout editor**, but the suite cannot be called green and reconciling it is the first thing standing between here and Task 12. Task 10's two-display and stadium acceptance evidence remain open. A fifteen-finding deep-dive audit on September 5, 2026 is recorded in `PROJECT_ROADMAP.md` under "Deep-dive audit"; the five lightest findings were fixed the same day.
- **Production media, OBS, networking, and hardware-controller work:** deferred.

`PROJECT_ROADMAP.md` is the authority on status and evidence. Nothing here may be treated as release-ready on the strength of a passing automated suite; the open hardware and rehearsal evidence is listed there.

The local repository uses `main` as the protected integration branch. Current implementation work is on `feature/field-status` and synchronizes with `https://github.com/grr187us/scoreboard.git`. `phase-2-audit` and `feature/layout-editor` are earlier branches retained for history.

## Confirmed versus unverified

### Confirmed

- The vendor Windows 11 laptop sends HDMI to a processor/switcher with four HDMI inputs.
- Two RJ45-style output links serve different halves of the LED wall.
- The vendor physical controller connects by USB.
- The vendor system, controller, software, and license dongle are protected fallback equipment and must remain intact.

### Unverified

- A personal Windows laptop can drive a stable, correctly mapped image across the complete LED wall.
- The processor model, Windows-reported resolution and refresh rate, scaling, cropping, and reconnect behavior.
- The production laptop and the final display geometry.

The RJ45-style connectors must not be treated as ordinary Ethernet without evidence. The preferred boundary is normal HDMI into the existing processor; direct LED protocol work is unnecessary unless the HDMI test disproves that model.

## Phase 0 HDMI gate

The personal-laptop stadium test planned for **September 8, 2026** remains the final Phase 0 gate. The test must record:

1. Whether Windows detects the processor as a display.
2. Whether one desktop/test pattern spans the entire wall correctly.
3. Resolution, active signal resolution, refresh rate, scaling, and orientation.
4. Cropping, stretching, seams, offsets, or unused pixels.
5. Stability during normal use and recovery after safe input reselection/reconnection.
6. Processor manufacturer/model and connection photographs.

Phase 0 must not be marked complete until that evidence is supplied.

## MVP scope

The Phase 2 MVP provides, or will provide:

| Capability | State |
|---|---|
| Editable home and away team names and scores | Built |
| Scoring controls for `+1`, `+2`, `+3`, `+6`, plus corrections and one-level undo | Built |
| Manual quarter control with running-clock confirmation | Built |
| Countdown game clock on a monotonic deadline | Built |
| Independent play clock with 25-second and 40-second presets | Built |
| Pregame and halftime/warmup event countdowns | Built |
| Mouse and keyboard operation with generated shortcut help | Built |
| Separate operator and fullscreen spectator views | Built |
| Offline operation, local recovery state, and a durable action history | Built |
| A folder picker for choosing where the game and logs are saved | Built |
| Display selection, persisted identity, and disconnect recovery | Built and tested against injected screen lists; real two-display evidence remains open |
| A repeatable offline Windows package and one-action launch | Built at version 0.1.0 after Task 10; clean-machine and target-laptop checks remain open |
| Down, distance, possession, field position, and timeouts remaining | Built and tested; owner/officials decisions on the timeout default and halftime reset remain open |
| Human-readable Eastern-time recovery timestamps | Built and tested |
| Field Assistant: a separate helper window that proposes down, distance, spot, penalty, turnover, and scoring outcomes and commits them as one reviewable action | Built and tested against the FA-01 to FA-28 matrix; no game-day rehearsal evidence yet |
| Presentation layout editor (v2): a separate canvas-style window that positions, styles, and saves spectator-board widgets plus free text/image/box elements, with undo, multi-select, and layout presets, without touching game state | Built and tested against focused suites and both a stub-bridge preview and the real pywebview runtime; owner sign-off on the default layout, a stadium-resolution legibility check, and the Playwright browser suite (no Node.js on this host) remain open |
| Sustained rehearsal and recovery acceptance | Task 12, not started |

Detailed, testable behavior is in [MVP requirements](docs/MVP_REQUIREMENTS.md).

## Intentionally deferred

The MVP does not include OBS as a required runtime, media playback, replay, animations, advanced statistics, roster management, sponsors, multiple operators, cloud services, automated HDMI switching, the physical USB controller, license-dongle investigation, or direct LED protocol work.

Two items previously listed here have since been delivered at the owner's direct request, ahead of the phase in which they were originally filed: the **presentation layout editor** (research issue `.scratch/testing-followups/issues/05-presentation-layout-editor-discovery.md`, filed as Phase 3) and **penalty handling**, which now exists only inside the Field Assistant as a proposal the operator accepts — the scoreboard still stores no penalty state of its own. Neither delivery advances Phase 3, Task 12, or the Phase 0 HDMI gate.

## Architecture direction

Phase 2 uses one Python application process as the authority for state, rules, clocks, persistence, and commands. It hosts HTML/CSS/JavaScript views in managed Windows webview windows, all fed from the same published snapshot:

| Window | Page | Size |
|---|---|---|
| Startup / recovery | `views/startup/` | 800×650 |
| Operator | `views/operator/` | 1180×720, minimum 1024×600 |
| Spectator | `views/spectator/` + `views/shared/board.*` | borderless fullscreen on the selected display |
| Spectator practice preview | the same spectator page | windowed, not tied to a display |
| Field Assistant | `views/field_assistant/` | 1180×720, minimum 1024×600 |
| Presentation layout editor | `views/layout/` | 1220×780, minimum 980×620 |

The spectator windows are read-only. The Field Assistant first calls `preview_field_action` to show a proposed down, distance, spot, and score outcome, and commits it only through `finalize_field_action` against an expected state revision — one command, one history row, one snapshot, undone as one action. The layout editor changes presentation only: it advances no state revision, submits no command, and writes no action-history row. OBS remains an optional future read-only presentation consumer, never the owner of game state.

See [Architecture](docs/ARCHITECTURE.md) and [Proposed project structure](docs/PROJECT_STRUCTURE.md) for the decision and boundaries.

## Repository map

| Path | Purpose |
|---|---|
| `High School LED Scoreboard — Project Knowledge Base.md` | Read-only project reference and historical context |
| `PROJECT_ROADMAP.md` | Living status, decisions, questions, and next action |
| `AGENTS.md` | Durable instructions for future Codex sessions |
| `docs/MVP_REQUIREMENTS.md` | Testable MVP behavior and acceptance criteria |
| `docs/UX_AND_LAYOUT.md` | Operator workflow and initial wireframes |
| `docs/ARCHITECTURE.md` | Option comparison and Phase 2 architecture decision record |
| `docs/OPEN_SOURCE_REVIEW.md` | Evidence-based review of candidate projects |
| `docs/PROJECT_STRUCTURE.md` | Minimal Phase 2 boundaries and proposed tree |
| `docs/PHASE_2_BACKLOG.md` | Ordered, bounded implementation tasks |
| `docs/PACKAGING.md` | How the offline Windows package is built, installed, and verified |
| `docs/DISPLAY_CHECKLIST.md` | The manual two-display and stadium checks that Task 10 still owes |
| `docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` | The Field Assistant's football rules, operator workflow, and the FA-01 to FA-28 requirement matrix |
| `docs/agents/` | Conventions the engineering skills follow in this repo: the `.scratch/` issue tracker, triage labels, and domain docs |
| `docs/evidence/` | Captured measurements and screenshots, each claimed by a roadmap entry |
| `docs/PHASE_2_TASK_1_RUNTIME_PROOF.md` | Environment setup, dependency pins, and the original multi-window proof |
| `.scratch/` | Local issue tracker: one directory per effort, `spec.md` plus numbered issue files |
| `tools/` | Build and measurement scripts; nothing here ships in the package |
| `src/scoreboard/` | The application: `domain/`, `application/`, `infrastructure/`, `presentation/`, `host/`, and the `views/` pages |
| `tests/` | `unit/` domain and clock behaviour, `integration/` persistence, recovery, bridge and rehearsal, `ui/` optional browser checks |
| `assets/` | Versioned, redistributable static presentation assets |

## Development organization

- Keep changes small enough to review and test in one Codex session.
- Use short feature branches once implementation begins; protect `main` from unverified work.
- Update the roadmap and relevant design document when evidence or decisions change.
- Do not copy third-party code until its license and compatibility are documented.
- Prefer a clean, reversible implementation over premature production features.

## Setup and run

Environment setup, exact dependency pins, offline behavior, and the original multi-window proof checklist are in [the Task 1 runtime proof](docs/PHASE_2_TASK_1_RUNTIME_PROOF.md). With that virtual environment in place, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scoreboard
```

That launches the recovery screen or the operator window, and opens the fullscreen spectator window on the selected display. The operator window opens the Field Assistant, the layout editor, and the windowed practice preview on demand; each is a separate webview the operator can close without affecting the game. It is a developer launch from a checkout, not the offline package, and it requires Python and the pinned dependencies on the machine. To build the package an operator can run without any of that, see [Packaging](docs/PACKAGING.md).

Run the automated suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The three `tests/ui/` checks — spectator board, keyboard, and layout editor — additionally need Node.js, Playwright, and Edge; they fail explicitly rather than skipping when that tooling is absent, so a machine without it reports errors on those three tests and runs the rest.

## Licensing

No license has been selected for this repository. Until the owner chooses repository visibility and a license, do not assume permission to redistribute this project's code. Third-party findings in the open-source review do not import any third-party code into this repository.
