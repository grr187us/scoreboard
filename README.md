# High School Football LED Scoreboard

This repository is the pre-implementation foundation for a reliable, offline-capable football scoreboard and future stadium video-production system. The immediate product is intentionally small: a Windows application that a student or volunteer can operate under game pressure and display fullscreen through the stadium's existing HDMI video processor.

A working scoreboard now runs from this repository on a development Windows host: authoritative state, both clocks, the event countdowns, persistence and recovery, the operator window, and the fullscreen spectator window. It also builds into an offline Windows package. It is **not** yet a release: display selection and the sustained rehearsal are unbuilt, and no result on the stadium wall has been recorded.

## Current status

- **Phase 0 — discovery and feasibility:** substantially complete, with the critical stadium HDMI test still open.
- **Phase 1 — repository, requirements, layout, and architecture:** documentation foundation created; owner decisions and field evidence remain open.
- **Phase 2 — core MVP:** in progress. Backlog Tasks 1–9 and 11 are implemented and verified locally; Task 10 (display selection and failure recovery) and Task 12 (sustained rehearsal) are not started.
- **Production media, OBS, networking, and hardware-controller work:** deferred.

`PROJECT_ROADMAP.md` is the authority on status and evidence. Nothing here may be treated as release-ready on the strength of a passing automated suite; the open hardware and rehearsal evidence is listed there.

The local repository uses `main` and is intended to synchronize with `https://github.com/grr187us/scoreboard.git`.

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
| Display selection, persisted identity, and disconnect recovery | Task 10, not started |
| A repeatable offline Windows package and one-action launch | Built; see [Packaging](docs/PACKAGING.md). Rebuild required after Task 10. |
| Sustained rehearsal and recovery acceptance | Task 12, not started |

Detailed, testable behavior is in [MVP requirements](docs/MVP_REQUIREMENTS.md).

## Intentionally deferred

The MVP does not include OBS as a required runtime, media playback, replay, animations, down/distance, possession, timeouts, advanced statistics, roster management, sponsors, multiple operators, cloud services, automated HDMI switching, the physical USB controller, license-dongle investigation, or direct LED protocol work.

## Architecture direction

Phase 2 should use one Python application process as the authority for state, rules, clocks, persistence, and commands. It will host two HTML/CSS/JavaScript views in managed Windows webview windows: an operator view and a spectator view. OBS remains an optional future read-only presentation consumer, never the owner of game state.

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
| `docs/HANDOFF_TASK_10.md` | Session handoff for the next implementation task |
| `tools/` | Build and measurement scripts; nothing here ships in the package |
| `src/scoreboard/` | The application: `domain/`, `application/`, `infrastructure/`, `host/`, and the `views/` pages |
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

That launches the recovery screen or the operator window, and opens the fullscreen spectator window on the selected display. It is a developer launch from a checkout, not the offline package, and it requires Python and the pinned dependencies on the machine. To build the package an operator can run without any of that, see [Packaging](docs/PACKAGING.md).

Run the automated suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The two `tests/ui/` checks additionally need Node.js, Playwright, and Edge; they fail explicitly rather than skipping when that tooling is absent, so a machine without it reports errors on those two tests and passes the rest.

## Licensing

No license has been selected for this repository. Until the owner chooses repository visibility and a license, do not assume permission to redistribute this project's code. Third-party findings in the open-source review do not import any third-party code into this repository.
