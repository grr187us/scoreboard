# Test boundary

Tests sit at the lowest layer that can prove the behavior, as described in `../docs/PROJECT_STRUCTURE.md` section 6.

| Location | Scope |
|---|---|
| `unit/` | Pure domain and application behavior: state validation, clock math, display formatting, and command transitions, all under an injected fake monotonic clock. |
| `integration/` | Persistence, recovery, diagnostics, and the view bridge, each inside its own temporary data directory with injected fake wall and monotonic clocks. |
| `integration/test_full_game_rehearsal.py` | One whole game through the real bridge: pregame countdown, four quarters of snap-by-snap play, halftime with the warmup boundary, an undo, a crash and resume in the third quarter, and End Game. It takes roughly 30 seconds because it is also a persistence soak — several thousand refresh ticks and their checkpoints. |
| `test_displays.py` | Host display-selection helpers that need no window. |
| `unit/test_layout_schema.py` | Pure presentation-layout schema and validation (added September 5, 2026): the coordinate model, the safe-area policy, the twelve-property widget shape, `LayoutValidation`/`LayoutIssue`, and the strict-validate-with-fallback rule — no I/O. |
| `integration/test_layout_persistence.py` | `layouts.json` read/write, atomic replace, schema-version fallback, and the "never touch `config.json`/`scoreboard.db`" boundary, each inside its own temporary data directory. |
| `integration/test_layout_bridge.py` | `PresentationLayouts` and its host wiring: save/select/delete/reset, publish-on-change, and the guarantee that a layout action advances no state revision, submits no command, and writes no action-history row. |
| `integration/test_spectator_layout_render.py` | Pure-Python contract test that `board.js`'s `WIDGET_IDS`/`WIDGET_FIELDS`/`WIDGET_TEXTS`/`OPTIONAL_WIDGET_IDS`/`DEFAULT_LAYOUT` literals parse as JSON and match the Python constants exactly, and that the spectator page and its scripts stay free of controls and forbidden tokens. |
| `integration/test_layout_editor_contract.py` | The editor page exposes a control for every editable widget property, builds its widget list from `widget_descriptors()` rather than a hard-coded id, and contains no `data-command`, `api.command`, or `CommandType` reference. |
| `unit/test_field_assistant.py` | Pure Field Assistant rules (added September 5, 2026): the FA-01 through FA-18 matrix — coordinate round-trip, the corrected fixed-per-team direction with a mirrored on-screen goal side, series/line-to-gain, normal play, incomplete pass, fourth-down proposal, goal-line exceptions, penalty shortcuts and outcomes, explicit turnover, touchdown/try/field-goal/safety/kickoff transitions, (FA-30) `PRE` calculating exactly as the 1st quarter does while `HALF`/`OT`/`FINAL` stay manual, and (FA-31) the `manual` escape hatch — stated team/down/distance with only the line to gain derived, goal-to-go, clamping at the goal line, and every rejection — with no I/O and no clock. |
| `integration/test_field_assistant_rehearsal.py` | The `finalize_field_action` composite command through the real bridge (FA-17/18/21-25/28): one revision/one history row/one published snapshot per finalize, undo restoring every changed field and score as one action, clock values and running flags left untouched, active-series recovery, a simulated persistence failure leaving no partial state, and a multi-quarter rehearsal sequence. |
| `integration/test_field_assistant_window.py` | Host window lifecycle for the Field Assistant helper (FA-25..27) against pywebview-shaped fakes: deliberate open at 1180×720/min 1024×600, isolated close/reopen reading the latest snapshot, a helper push failure destroying only the helper, and operator shutdown closing it with the other owned windows. It also carries the FA-29 draft-ownership source contract: the helper never re-seeds its draft ball from a refresh push, only open/Re-sync/a committed action arm a re-seed, operator changes ask Python for a fresh preview, and the draft envelope still carries no calculated football value (the `manual` escape hatch copies the operator's pressed down/distance verbatim). Added September 5, 2026: the bridge must be attached on the `window`-level `pywebviewready` event (a `document` listener never fires, which left the first build unable to enable Confirm), and the volunteer screen shows one `data-panel` at a time with the Confirm label carrying the previewed result. |

No test sleeps, reads real wall-clock or monotonic time, or writes outside its temporary directory. Packaged launch, display placement, sustained rehearsal, and the operator visual matrix are release-evidence checklists rather than automated tests.

The fake-time rehearsal is not the Task 12 acceptance run. It proves the layers stay consistent across a game-length command sequence; it cannot measure real clock accuracy, WebView2 behavior, or anything about the target laptop.

Run the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pass `-s tests` and nothing else. Adding `-t .` makes `tests/` the wrong top-level directory and discovery aborts with `Start directory is not importable`.

## The suite is not green

As of September 5, 2026 a full run reports **597 tests, 15 failures, 3 errors**. That is the expected result on this repository right now, not a broken checkout. Every failure is a legacy pregame or quarter expectation that testing follow-ups 01 and 02 deliberately changed, and every error is a `tests/ui/` browser check on a host without Node.js and Playwright. The complete inventory, failure by failure with the reason and the owner of each, is under "Automated suite failure inventory" in [`../PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md).

Check a new failure against that inventory before calling it a regression. Set `SCOREBOARD_DATA_DIR` as shown below when you run the whole suite; without it a sixteenth test fails, because `DataLocationTests` asserts the default per-user root is named `Scoreboard` and this machine resolves it to `Scoreboard Logs`.


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

Node.js and Playwright resolve from the Codex runtime bundle rather than a
project-local install. If `tests.ui.*` cannot find them, set the following
before running the suite:

```bash
N="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node"
export PATH="$N/bin:$PATH"
export NODE_PATH="$N/node_modules"
```

Also set `SCOREBOARD_DATA_DIR` for a full suite run (for example, to the
platform default) so tests never touch a real operator data folder:

```bash
export SCOREBOARD_DATA_DIR="C:/Users/505gr/AppData/Local/Scoreboard"
./.venv/Scripts/python.exe -m unittest tests.ui.test_spectator_browser -v
```

### Presentation layout editor (added September 5, 2026)

`ui/test_spectator_browser.py` + `ui/spectator.cjs` extend the existing
viewport matrix to the widgetized board: selectors moved to
`[data-widget="..."]`, and new cases cover applying a custom layout through
`window.applyLayout`, an invalid/partial layout leaving the previous good one
in place, and an optional field's widget hiding when its value is absent.

`ui/test_layout_editor_browser.py` + `ui/layout_editor.cjs` drive the editor
page against a stub `window.pywebview.api` built from real
`PresentationLayouts.state()` payloads, following the same pattern
`test_spectator_browser.py` uses: the widget list populates, selecting a
widget fills the property panel, changing `x` moves the preview widget, an
out-of-safe-area value shows an error naming the widget and disables Save,
`Reset this widget` restores the default values, the page does not scroll at
1280×720, and no element carries `data-command`.
