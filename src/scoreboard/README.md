# Application package

The boundaries proposed in `../../docs/PROJECT_STRUCTURE.md` are now filled in. Each layer is independently testable and depends only inward.

| Package | Owns | Must not contain |
|---|---|---|
| `domain/` | State values and invariants, command shapes, clock mathematics against injected monotonic time, display rounding | Files, windows, wall-clock time, persistence |
| `application/` | The serialized command service (the only writer of the authoritative revision), bounded in-memory Undo history, snapshots, and startup recovery choice | Rendering, OS display APIs, silent auto-resume |
| `infrastructure/` | Per-user Windows data resolution, SQLite transactions with a last-known-good backup, append-only action history, non-game preferences, layouts, saved teams, and rotating diagnostics | Game rules or clock mathematics |
| `host/` | The webview process, operator/spectator/startup/helper/editor/practice window slots, narrow JSON bridges, display management, and off-command-lock publication | Duplicate game state; C4's open cross-thread ordering limitation is documented in `../../docs/ARCHITECTURE.md` |
| `views/` | Operator, spectator, startup, Field Assistant, and layout-editor pages that render Python-owned view models | Any authoritative score, clock, phase, or revision |

Two rules hold the design together and should be checked in review:

- the service is the only component that advances a state revision, and nothing outside `domain/` re-implements clock arithmetic;
- every displayed clock string is produced in Python by `domain/formatting.py`, so the operator readout, the spectator board, and the persisted checkpoint cannot disagree about what is on the board.
