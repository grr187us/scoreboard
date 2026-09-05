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
