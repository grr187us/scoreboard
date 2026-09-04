# High School Football LED Scoreboard

This repository is the pre-implementation foundation for a reliable, offline-capable football scoreboard and future stadium video-production system. The immediate product is intentionally small: a Windows application that a student or volunteer can operate under game pressure and display fullscreen through the stadium's existing HDMI video processor.

No working scoreboard application exists in this repository yet. Phase 1 defines what to build, why, and how it will be verified; feature implementation begins in Phase 2.

## Current status

- **Phase 0 — discovery and feasibility:** substantially complete, with the critical stadium HDMI test still open.
- **Phase 1 — repository, requirements, layout, and architecture:** documentation foundation created; owner decisions and field evidence remain open.
- **Phase 2 — core MVP:** not started.
- **Production media, OBS, networking, and hardware-controller work:** deferred.

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

The Phase 2 MVP will provide:

- Editable home and away team names and scores.
- Home and away scoring controls for `+1`, `+2`, `+3`, and `+6`, plus safe correction.
- Manual quarter control.
- A crucial countdown game clock.
- A crucial independent play clock with 25-second and 40-second presets.
- Mouse and keyboard operation.
- Separate operator and fullscreen spectator views.
- Offline operation, local recovery state, and an event log.
- A repeatable Windows launch/package path.

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
| `src/scoreboard/` | Reserved application package boundary; no feature code yet |
| `tests/` | Test strategy and future automated tests |
| `assets/` | Versioned, redistributable static presentation assets |

## Development organization

- Keep changes small enough to review and test in one Codex session.
- Use short feature branches once implementation begins; protect `main` from unverified work.
- Update the roadmap and relevant design document when evidence or decisions change.
- Do not copy third-party code until its license and compatibility are documented.
- Prefer a clean, reversible implementation over premature production features.

## Setup and run

Phase 2 Task 1 provides a narrow, installable Windows multi-window proof. It is not a scoreboard yet: it opens only operator/spectator placeholder pages and display-host controls. Setup, exact pins, offline behavior, and the manual proof checklist are in [the Task 1 runtime proof](docs/PHASE_2_TASK_1_RUNTIME_PROOF.md).

## Licensing

No license has been selected for this repository. Until the owner chooses repository visibility and a license, do not assume permission to redistribute this project's code. Third-party findings in the open-source review do not import any third-party code into this repository.
