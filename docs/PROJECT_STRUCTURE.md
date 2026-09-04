# Proposed Phase 2 Project Structure

**Status:** Approved structure proposal; only boundary README files exist today
**Last updated:** September 4, 2026

## 1. Principle

Create folders when a task puts real code or assets in them. Do not pre-create a large empty tree. The current repository contains only `src/scoreboard/`, `tests/`, and `assets/` boundary notes because application implementation has not begun.

The proposed structure follows the dependency rule:

```text
views / host / integrations
          │
          ▼
 application commands + snapshots
          │
          ▼
 domain state + clock logic
```

Domain modules do not import webview, filesystem, Windows, or integration modules. Persistence consumes/produces versioned snapshots through application interfaces; it does not mutate domain objects behind the command service.

## 2. Proposed tree

```text
scoreboard/
├─ README.md
├─ AGENTS.md
├─ PROJECT_ROADMAP.md
├─ High School LED Scoreboard — Project Knowledge Base.md
├─ pyproject.toml                   # Phase 2 task 1: runtime/dev dependencies
├─ .gitignore
├─ assets/
│  ├─ README.md                    # ownership and licensing policy
│  ├─ fonts/                       # only bundled/licensed fonts when selected
│  └─ themes/default/              # spectator CSS variables/assets when real
├─ docs/
│  ├─ MVP_REQUIREMENTS.md
│  ├─ UX_AND_LAYOUT.md
│  ├─ ARCHITECTURE.md
│  ├─ OPEN_SOURCE_REVIEW.md
│  ├─ PROJECT_STRUCTURE.md
│  └─ PHASE_2_BACKLOG.md
├─ src/scoreboard/
│  ├─ __init__.py
│  ├─ __main__.py                  # one application launch entry point
│  ├─ domain/
│  │  ├─ state.py                  # immutable/value-oriented game snapshot
│  │  ├─ commands.py               # validated score/quarter/lifecycle transitions
│  │  └─ clocks.py                 # pure monotonic/deadline calculations
│  ├─ application/
│  │  ├─ service.py                # serializes commands; revision authority
│  │  ├─ snapshots.py              # versioned view/adapter contract
│  │  └─ recovery.py               # startup choice and safe stopped restore
│  ├─ infrastructure/
│  │  ├─ paths.py                  # Windows per-user data locations
│  │  ├─ persistence.py            # atomic JSON + backup
│  │  ├─ event_log.py              # append-only JSONL events
│  │  └─ diagnostics.py            # rotating application diagnostics
│  ├─ host/
│  │  ├─ app.py                    # webview lifecycle and shutdown
│  │  ├─ bridge.py                 # narrow JS/Python contract
│  │  └─ displays.py               # enumeration, selection, reopen/fullscreen
│  ├─ views/
│  │  ├─ shared/                   # reset, base styles, renderer utilities
│  │  ├─ operator/                 # HTML/CSS/JS control UI
│  │  └─ spectator/                # HTML/CSS/JS display-only UI
│  └─ integrations/                # empty/uncreated until a later phase needs it
│     ├─ obs.py                    # future output adapter, not MVP
│     └─ controller.py             # future optional input adapter, not MVP
└─ tests/
   ├─ README.md
   ├─ unit/                        # domain/application deterministic tests
   ├─ integration/                 # persistence, bridge, and recovery tests
   ├─ ui/                          # contract/smoke tests where justified
   └─ fixtures/                    # versioned snapshots and fake-clock inputs
```

The `integrations/` files are illustrative and should **not** be created in Phase 2 unless their deferred features become active.

## 3. Component responsibilities

| Component | Owns | Must not own |
|---|---|---|
| `domain/state.py` | Valid state values and invariants | Files, UI objects, timers, OBS |
| `domain/commands.py` | Pure transitions and reversible-command data | Persistence or key bindings |
| `domain/clocks.py` | Deadline/remaining calculations against injected monotonic time | UI refresh cadence or wall time |
| `application/service.py` | Command order, state revision, snapshots, publication | Rendering or OS display APIs |
| `application/recovery.py` | Validated startup restore as stopped, owner choice | Silent auto-resume |
| `infrastructure/persistence.py` | Atomic file replacement, backup, schema I/O | Deciding game rules |
| `infrastructure/event_log.py` | Structured append-only command/system events | High-frequency tick spam |
| `host/bridge.py` | JSON-compatible command/snapshot boundary | Duplicate game state |
| `host/displays.py` | Enumeration, display preference, reopen/fullscreen | HDMI switching or LED protocol |
| operator view | Input intent, forms, feedback, ephemeral UI state | Authoritative scores/clocks |
| spectator view | Responsive rendering of complete snapshots | Commands or persistence |
| future adapters | Translate external inputs/outputs | Authority over state |

## 4. Static assets

- HTML/CSS/JS needed at runtime lives with the corresponding view so packaging rules are obvious.
- Shared fonts/images belong under `assets/` only after ownership/license is recorded.
- No CDN or internet-fetched runtime assets are permitted.
- Logos and game-day custom content require a separate per-user configuration/data location; they should not be committed casually.
- Generated animations, recordings, and replay media remain ignored.

## 5. Runtime data (outside the repository)

The application resolves a per-user Windows data directory and creates runtime subdirectories there. Repository source paths must never be used for live state.

```text
Scoreboard/
├─ config.json
├─ current-state.json
├─ current-state.backup.json
└─ logs/
   ├─ application.log
   └─ game-*.jsonl
```

Tests use isolated temporary directories and never read or overwrite the operator's real state.

## 6. Test organization

Tests should normally sit at the lowest layer that can prove the behavior:

- Clock drift, pause/resume, expiry, score bounds, quarter behavior: unit tests with fake time.
- Atomic replace, corrupt-primary fallback, and event ordering: integration tests with temporary directories.
- Bridge payload and stale revision behavior: contract/integration tests.
- Button hierarchy, focus suppression, display placement, fullscreen, disconnect/reopen: narrow automated UI checks plus documented Windows manual tests.
- Packaging, offline launch, sustained rehearsal: release acceptance scripts/checklists, not unit tests.

## 7. Creation sequence

1. Task 1 creates only `pyproject.toml`, entry point, host proof modules, minimal view files, and the test files needed for that proof.
2. Tasks 2–6 add domain/application/infrastructure modules as each responsibility becomes real.
3. Tasks 7–10 fill operator/spectator/keyboard/display modules against stable command contracts.
4. Packaging files appear in Task 11 after runtime behavior is stable.
5. Integration modules remain absent until a later phase authorizes them.
