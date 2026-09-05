# Test boundary

Tests sit at the lowest layer that can prove the behavior, as described in `../docs/PROJECT_STRUCTURE.md` section 6.

| Location | Scope |
|---|---|
| `unit/` | Pure domain and application behavior: state validation, clock math, display formatting, and command transitions, all under an injected fake monotonic clock. |
| `integration/` | Persistence, recovery, diagnostics, and the view bridge, each inside its own temporary data directory with injected fake wall and monotonic clocks. |
| `test_displays.py` | Host display-selection helpers that need no window. |

No test sleeps, reads real wall-clock or monotonic time, or writes outside its temporary directory. Packaged launch, display placement, sustained rehearsal, and the operator visual matrix are release-evidence checklists rather than automated tests.

Run the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```


## Browser checks (Tasks 8-9)

`unittest discover -s tests -v` includes offline browser checks using Node.js,
Playwright, and installed Microsoft Edge. These are development tools only;
the scoreboard runtime remains Python/WebView2 with bundled static files.
Set `NODE_PATH` to a Node modules directory containing `playwright` if it is not
already resolvable. The Codex desktop bundled runtime is detected as a fallback.
Missing tooling fails explicitly; no browser tests are silently skipped.

Set `SCOREBOARD_CAPTURE_DIR` to an evidence output directory to capture the
Task 8 viewport matrix and JSON measurements while running
`python -m unittest tests.ui.test_spectator_browser -v`.
