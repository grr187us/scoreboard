# Codex project instructions

This repository is for a high-school football LED scoreboard and future video-production system. Reliability, offline operation, and ease of use by a student or volunteer outrank feature count.

## Read before changing anything

1. Read `PROJECT_ROADMAP.md` completely. It is the living project-management document.
2. Read `High School LED Scoreboard — Project Knowledge Base.md` completely. It is reference material; do not casually rewrite it.
3. Read the requirements, architecture, UX, and active backlog documents relevant to the task.
4. Inspect the working tree and preserve unrelated user changes.

Files under `sources/`, if present, are synced reference material: do not edit, rename, move, or delete them.

## Safety and scope

- Keep the vendor laptop, software, physical controller, and license dongle intact as the emergency fallback.
- Do not bypass licensing, investigate circumvention, or modify the vendor system.
- Do not assume the processor's RJ45-style outputs are ordinary Ethernet.
- Treat HDMI into the existing processor as the preferred hardware boundary until the stadium test provides contrary evidence.
- Do not mark the Phase 0 HDMI gate complete without recorded test evidence.
- Work only within the active phase and the current task's explicit exclusions. Do not pull later media, OBS, networking, or controller work into the MVP.
- Core game operation must remain fully offline; do not add cloud accounts, servers, containers, or database services without a demonstrated need and owner approval.

## Architecture boundaries

Keep these responsibilities independently testable:

- authoritative game state;
- football/game rules and commands;
- game-clock and play-clock timing;
- spectator presentation;
- operator controls;
- configuration;
- persistence and event logging;
- optional integrations such as OBS or physical controllers.

Presentation and integrations must not become authoritative state owners. Optional integration failure must not prevent keyboard/mouse operation of the core scoreboard.

## Implementation discipline

- Prefer mature, lightweight, Windows-compatible dependencies and small reversible decisions.
- Do not add a database server for local MVP state.
- Use a monotonic timing source and derive displayed clock values from elapsed time; do not decrement once per UI callback.
- Route all mutations through explicit validated commands and record meaningful operator actions.
- Treat resets, direct corrections, and game-ending actions as dangerous operations with confirmation or deliberate arming.
- Add meaningful automated verification before marking implementation work complete.
- Test failure and recovery paths in proportion to their game-day risk.
- Keep generated state, logs, media, secrets, virtual environments, and machine-specific settings out of Git.

## Documentation and completion

- Distinguish confirmed facts, hypotheses, provisional defaults, decisions, and questions needing testing.
- Update `PROJECT_ROADMAP.md` when work, evidence, status, or the next action changes.
- Update the relevant requirement/architecture/UX document when a decision changes.
- Do not mark an item complete based only on files existing; record the verification performed.
- Before committing, review the complete diff, validate relative Markdown links, and report every remaining uncommitted file.
- The discovered suite is green as of September 6, 2026 (750 tests, 0 failures, 0 errors, 3 skipped). Run it; the 3 skips are `@unittest.skip`s naming open question A-1 (whether a game-clock Start should always blank the play clock) and are expected, not a pass on that question. Anything else failing or erroring is a regression — see "Automated suite failure inventory" in `PROJECT_ROADMAP.md` for how the suite got here.

## Agent skills

### Issue tracker

Issues live as markdown files under `.scratch/<feature-slug>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, using their default label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. Neither exists yet, which is the expected state — `docs/agents/domain.md` says to proceed silently when they are absent, and the domain-modeling skill creates them lazily when a term or decision is actually resolved. Until then the requirement, architecture, and UX documents under `docs/` remain the authority. See `docs/agents/domain.md`.
