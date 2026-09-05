# Application package

The boundaries proposed in `../../docs/PROJECT_STRUCTURE.md` are now filled in. Each layer is independently testable and depends only inward.

| Package | Owns | Must not contain |
|---|---|---|
| `domain/` | State values and invariants, command shapes, clock mathematics against injected monotonic time, display rounding | Files, windows, wall-clock time, persistence |
| `application/` | The serialized command service (the only writer of the authoritative revision), snapshots, and the startup recovery choice | Rendering, OS display APIs, silent auto-resume |
| `infrastructure/` | Per-user Windows data locations, SQLite transactions with a last-known-good backup, the append-only action history, the rotating diagnostic log | Game rules or clock mathematics |
| `host/` | The webview process, both windows, and the narrow JSON bridge JavaScript talks to | Duplicate game state |
| `views/` | Operator and spectator pages that render the view model Python sends | Any computed score, clock, phase, or revision |

Two rules hold the design together and should be checked in review:

- the service is the only component that advances a state revision, and nothing outside `domain/` re-implements clock arithmetic;
- every displayed clock string is produced in Python by `domain/formatting.py`, so the operator readout, the spectator board, and the persisted checkpoint cannot disagree about what is on the board.
