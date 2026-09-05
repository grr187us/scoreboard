# Proposed Phase 2 Project Structure

**Status:** Approved structure; implementation now fills the Phase 2 boundaries
**Last updated:** September 5, 2026

## 1. Principle

Create folders when a task puts real code or assets in them. Do not pre-create a large empty tree. The current repository contains the implemented Phase 2 domain, application, infrastructure, host, view, and test boundaries; deferred integrations remain uncreated.

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
│  │  ├─ clocks.py                 # pure monotonic/deadline calculations
│  │  └─ formatting.py             # pure display rounding for every clock and football field
│  ├─ application/
│  │  ├─ service.py                # serializes commands; revision authority
│  │  ├─ snapshots.py              # versioned view/adapter contract
│  │  └─ recovery.py               # startup choice and safe stopped restore
│  ├─ infrastructure/
│  │  ├─ paths.py                  # Windows per-user data locations
│  │  ├─ persistence.py            # SQLite transactions, backup, action history
│  │  ├─ diagnostics.py            # rotating application diagnostics
│  │  └─ local_time.py             # display-only UTC-to-Eastern timestamp conversion
│  ├─ host/
│  │  ├─ app.py                    # webview lifecycle and shutdown
│  │  ├─ startup.py                # separate report/resume/new startup surface
│  │  ├─ bridge.py                 # narrow JS/Python contract
│  │  └─ displays.py               # enumeration, selection, reopen/fullscreen
│  ├─ views/
│  │  ├─ shared/                   # base.css tokens/reset, render.js helpers
│  │  ├─ operator/                 # index.html, operator.css, operator.js, keyboard.js
│  │  ├─ startup/                  # recovery preview and explicit choices
│  │  └─ spectator/                # 16:9 game/event page, proportional CSS and renderer
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
| `domain/formatting.py` | Pure upward display rounding for every clock readout | Stored time, state, or persistence policy |
| `application/service.py` | Command order, state revision, snapshots, publication | Rendering or OS display APIs |
| `application/recovery.py` | Validated startup restore as stopped, owner choice | Silent auto-resume |
| `infrastructure/persistence.py` | One SQLite transaction per accepted command, the last-known-good backup, the append-only action history, and the single-instance lock | Deciding game rules or producing a revision |
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

On Windows the root is `SHGetKnownFolderPath(FOLDERID_LocalAppData)` + `Scoreboard`, resolved through the platform API rather than a hard-coded or repository-relative path. A relative path is refused outright.

```text
Scoreboard/
├─ config.json                     # created when Task 7+ needs it
├─ scoreboard.db                   # recoverable state + append-only action history
├─ scoreboard.backup.db            # automatically refreshed last-known-good copy
├─ scoreboard.lock                 # single-instance lock (R-004)
├─ scoreboard.invalid-*.db         # only when a corrupt file is preserved (P-006)
└─ logs/
   └─ application.log              # bounded rotating diagnostics (P-008)
```

The game's durable action history lives in `scoreboard.db`, not in a separate JSONL file: one transaction must commit the new state and its history row together (P-002), which two files cannot guarantee. The rotating `application.log` records what the *program* did and is allowed to roll over; the action history records what happened in the *game* and never is.

Tests use isolated temporary directories and never read or overwrite the operator's real state.

## 6. Test organization

Tests should normally sit at the lowest layer that can prove the behavior:

- Clock drift, pause/resume, expiry, score bounds, quarter behavior: unit tests with fake time.
- Atomic replace, corrupt-primary fallback, and event ordering: integration tests with temporary directories.
- Bridge payload and stale revision behavior: contract/integration tests.
- Button hierarchy, focus suppression, display placement, fullscreen, disconnect/reopen: narrow automated UI checks plus documented Windows manual tests. `tests/ui/` runs Edge via development-only Playwright; the keyboard harness sends browser requests to a real bridge backed by an isolated temporary SQLite store.
- Packaging, offline launch, sustained rehearsal: release acceptance scripts/checklists, not unit tests.

## 7. Creation sequence

1. Task 1 creates only `pyproject.toml`, entry point, host proof modules, minimal view files, and the test files needed for that proof.
2. Tasks 2–6 add domain/application/infrastructure modules as each responsibility becomes real.
3. Tasks 7–10 fill operator/spectator/keyboard/display modules against stable command contracts.
4. Packaging files appear in Task 11 after runtime behavior is stable.
5. Integration modules remain absent until a later phase authorizes them.
