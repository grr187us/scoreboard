# Proposed Phase 2 Project Structure

**Status:** Approved structure; implementation now fills the Phase 2 boundaries
**Last updated:** September 5, 2026 (added the presentation-layout modules and views, then the Field Assistant rules module, bridge wiring, and helper-window views)

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
├─ docs/                           # the principal design documents; see README.md for the full docs map
│  ├─ MVP_REQUIREMENTS.md
│  ├─ UX_AND_LAYOUT.md
│  ├─ ARCHITECTURE.md
│  ├─ OPEN_SOURCE_REVIEW.md
│  ├─ PROJECT_STRUCTURE.md
│  ├─ PHASE_2_BACKLOG.md
│  ├─ FIELD_ASSISTANT_RULES_AND_WORKFLOW.md  # rules spec, coordinate model, FA-01..FA-28 matrix (added September 5, 2026)
│  ├─ agents/                      # conventions the engineering skills follow in this repo
│  └─ evidence/                    # captured measurements and screenshots, each claimed by a roadmap entry
├─ src/scoreboard/
│  ├─ __init__.py
│  ├─ __main__.py                  # one application launch entry point
│  ├─ domain/
│  │  ├─ state.py                  # immutable/value-oriented game snapshot
│  │  ├─ commands.py               # validated score/quarter/lifecycle transitions
│  │  ├─ clocks.py                 # pure monotonic/deadline calculations
│  │  ├─ formatting.py             # pure display rounding for every clock and football field
│  │  └─ field_assistant.py        # pure Field Assistant rules: coordinates, series/line-to-gain, penalties, transitions; no I/O, no clocks (added September 5, 2026)
│  ├─ presentation/                # added September 5, 2026
│  │  ├─ __init__.py
│  │  └─ layout.py                 # pure spectator-layout schema, defaults, and validation (no I/O)
│  ├─ application/
│  │  ├─ service.py                # serializes commands; revision authority
│  │  ├─ snapshots.py              # versioned view/adapter contract
│  │  └─ recovery.py               # startup choice and safe stopped restore
│  ├─ infrastructure/
│  │  ├─ paths.py                  # Windows per-user data locations
│  │  ├─ persistence.py            # SQLite transactions, backup, action history
│  │  ├─ config.py                 # operator preferences that are not game state: display identity, data-folder choice
│  │  ├─ diagnostics.py            # rotating application diagnostics
│  │  ├─ local_time.py             # display-only UTC-to-Eastern timestamp conversion
│  │  └─ layouts.py                # layouts.json read/write, atomic replace, schema-version fallback (added September 5, 2026)
│  ├─ host/
│  │  ├─ app.py                    # webview lifecycle and shutdown; owns the six window slots
│  │  ├─ startup.py                # separate report/resume/new startup surface
│  │  ├─ preflight.py              # WebView2/runtime prerequisite checks and fatal-launch reporting
│  │  ├─ folders.py                # native Windows folder picker for the data directory
│  │  ├─ bridge.py                 # narrow JS/Python contract; also hosts FieldAssistantBridge (added September 5, 2026)
│  │  ├─ layout_bridge.py          # presentation-layout host bridge; no game-mutating method (added September 5, 2026)
│  │  └─ displays.py               # enumeration, selection, reopen/fullscreen
│  ├─ views/
│  │  ├─ shared/                   # base.css tokens/reset, render.js helpers, board.js/board.css widget renderer (added September 5, 2026)
│  │  ├─ operator/                 # index.html, operator.css, operator.js, keyboard.js
│  │  ├─ startup/                  # recovery preview and explicit choices
│  │  ├─ layout/                   # presentation layout editor: index.html, layout.css, layout.js (added September 5, 2026)
│  │  ├─ field_assistant/          # helper window: index.html, field_assistant.js, field_assistant.css (added September 5, 2026)
│  │  └─ spectator/                # 16:9 game/event page, proportional CSS and renderer
│  └─ integrations/                # empty/uncreated until a later phase needs it
│     ├─ obs.py                    # future output adapter, not MVP
│     └─ controller.py             # future optional input adapter, not MVP
└─ tests/
   ├─ README.md
   ├─ test_displays.py             # host display-selection helpers that need no window
   ├─ unit/                        # domain/application deterministic tests
   ├─ integration/                 # persistence, bridge, recovery, layout, and Field Assistant tests
   └─ ui/                          # contract/smoke tests where justified
```

An earlier version of this tree proposed a `tests/fixtures/` directory. It was never created and nothing depends on it; tests build their inputs in-process under an injected fake clock, so the entry has been dropped rather than left as a phantom.

The `integrations/` files are illustrative and should **not** be created in Phase 2 unless their deferred features become active.

## 3. Component responsibilities

| Component | Owns | Must not own |
|---|---|---|
| `domain/state.py` | Valid state values and invariants | Files, UI objects, timers, OBS |
| `domain/commands.py` | Pure transitions and reversible-command data | Persistence or key bindings |
| `domain/clocks.py` | Deadline/remaining calculations against injected monotonic time | UI refresh cadence or wall time |
| `domain/formatting.py` | Pure upward display rounding for every clock readout | Stored time, state, or persistence policy |
| `domain/field_assistant.py` | Pure Field Assistant rules: coordinate conversion, series/line-to-gain, penalty and transition calculations | Files, UI objects, clocks, persistence, or the composite command's revision check |
| `presentation/layout.py` | Spectator-widget/layout schema, defaults, and validation, including the safe-area policy | Files, UI objects, timers, or authoritative game state |
| `application/service.py` | Command order, state revision, snapshots, publication | Rendering or OS display APIs |
| `application/recovery.py` | Validated startup restore as stopped, owner choice | Silent auto-resume |
| `infrastructure/persistence.py` | One SQLite transaction per accepted command, the last-known-good backup, the append-only action history, and the single-instance lock | Deciding game rules or producing a revision |
| `infrastructure/layouts.py` | `layouts.json` read/write, atomic replace, schema-version fallback | Deciding widget geometry or producing a state revision |
| `infrastructure/config.py` | Non-game operator preferences: display identity and geometry, data-folder choice | Game state or a state revision |
| `host/preflight.py` | Runtime and WebView2 prerequisite checks, and fatal-launch reporting | Game state or window lifecycle |
| `host/folders.py` | The native Windows folder-picker dialog | Game state or persistence policy |
| `host/bridge.py` | JSON-compatible command/snapshot boundary; also `FieldAssistantBridge`'s `get_snapshot`/`preview_field_action`/`finalize_field_action` | Duplicate game state |
| `host/layout_bridge.py` | Read/validate/save/publish spectator layouts | Any game-mutating method |
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
├─ layouts.json                    # saved spectator-board presentation layouts (added September 5, 2026)
├─ scoreboard.db                   # recoverable state + append-only action history
├─ scoreboard.backup.db            # automatically refreshed last-known-good copy
├─ scoreboard.lock                 # single-instance lock (R-004)
├─ scoreboard.invalid-*.db         # only when a corrupt file is preserved (P-006)
└─ logs/
   └─ application.log              # bounded rotating diagnostics (P-008)
```

The game's durable action history lives in `scoreboard.db`, not in a separate JSONL file: one transaction must commit the new state and its history row together (P-002), which two files cannot guarantee. The rotating `application.log` records what the *program* did and is allowed to roll over; the action history records what happened in the *game* and never is.

`layouts.json` is its own file, separate from both `config.json` and `scoreboard.db` (added September 5, 2026): a damaged layout library must not be able to cost the operator a saved game, and a damaged game must not be able to cost the operator a saved layout. It is read/written with the same atomic temp-file-plus-`os.replace` policy and the same "a preference file may never stop the scoreboard" contract as `config.json`.

Tests use isolated temporary directories and never read or overwrite the operator's real state.

## 6. Test organization

Tests should normally sit at the lowest layer that can prove the behavior:

- Clock drift, pause/resume, expiry, score bounds, quarter behavior: unit tests with fake time.
- Field Assistant rules (coordinate conversion, series and line-to-gain, penalties, transitions) and the presentation-layout schema (widget shape, safe-area policy, strict-validate-with-fallback): pure unit tests with no I/O and no clock, following the same pattern as the domain-state tests above.
- Atomic replace, corrupt-primary fallback, and event ordering: integration tests with temporary directories.
- `layouts.json` atomic replace and schema-version fallback, the `PresentationLayouts`/`LayoutEditorBridge` publish-on-change guarantees, and the `finalize_field_action` composite command through the real bridge — one revision, one history row, one snapshot, undone as one action: integration tests with temporary directories, on the same terms as the persistence and bridge bullets.
- Bridge payload and stale revision behavior: contract/integration tests.
- Button hierarchy, focus suppression, display placement, fullscreen, disconnect/reopen: narrow automated UI checks plus documented Windows manual tests. `tests/ui/` runs Edge via development-only Playwright; the keyboard harness sends browser requests to a real bridge backed by an isolated temporary SQLite store, and the same pattern now drives the widgetized spectator board (`spectator.cjs`) and the presentation-layout editor page (`layout_editor.cjs`) against a stub `window.pywebview.api` built from real `PresentationLayouts.state()` payloads.
- Packaging, offline launch, sustained rehearsal: release acceptance scripts/checklists, not unit tests.

The per-file boundary table is in [`../tests/README.md`](../tests/README.md); it is the authority when it and this summary disagree.

## 7. Creation sequence

1. Task 1 creates only `pyproject.toml`, entry point, host proof modules, minimal view files, and the test files needed for that proof.
2. Tasks 2–6 add domain/application/infrastructure modules as each responsibility becomes real.
3. Tasks 7–10 fill operator/spectator/keyboard/display modules against stable command contracts.
4. Packaging files appear in Task 11 after runtime behavior is stable.
5. Integration modules remain absent until a later phase authorizes them.
