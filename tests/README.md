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
| `integration/test_logs_folder.py` | The `open_logs_folder` host action (added September 5, 2026): it opens the folder that holds the diagnostics log through an injected opener, advances no revision, leaves a running clock running, reports rather than raises when Explorer refuses, and says so plainly when there is no log file. |

No test sleeps, reads real wall-clock or monotonic time, or writes outside its temporary directory. Packaged launch, display placement, sustained rehearsal, and the operator visual matrix are release-evidence checklists rather than automated tests.

The fake-time rehearsal is not the Task 12 acceptance run. It proves the layers stay consistent across a game-length command sequence; it cannot measure real clock accuracy, WebView2 behavior, or anything about the target laptop.

## New developer machine setup

1. Install Python 3.11 from python.org (`winget install --id Python.Python.3.11 --exact --scope user` also works, and installs the `py` launcher).
2. `py -3.11 -m venv .venv`
3. `.\.venv\Scripts\python.exe -m pip install -e ".[build]"`
4. Install Node.js LTS (`winget install --id OpenJS.NodeJS.LTS --exact` also works).
5. `npm ci` from the repository root.

Microsoft Edge is already on Windows, so no separate browser install is needed. See "Browser checks" below for how `tests/ui/` finds Playwright, and `.github/workflows/ci.yml` runs this same sequence on `windows-latest` for pushes to `main`/`feature/**` and for pull requests: setup-python 3.11, editable install, `pip check`, `compileall`, setup-node, `npm ci`, `tools/check_markdown_links.py`, then the full discovery run.

Run the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pass `-s tests` and nothing else. Adding `-t .` makes `tests/` the wrong top-level directory and discovery aborts with `Start directory is not importable`.

## The suite is green

As of September 6, 2026 a full run on the rebuilt `.venv` with Node.js on PATH reports **750 tests, 0 failures, 0 errors, 3 skipped** in 51 seconds. The 3 skips are `tests.unit.test_commands.ClockCouplingTests.test_game_clock_start_clears_a_running_play_clock`, `test_game_clock_stop_clears_a_running_play_clock_in_the_same_commit`, and `tests.integration.test_bridge.ExpirationHistoryTests.test_game_clock_expiry_clears_a_running_play_clock_durably` — each is `@unittest.skip` naming question A-1 (whether a game-clock Start should always blank the play clock), a football-rules question for the owner and the officials, not a code decision. Read a skip as "blocked on A-1," never as passing: green does not mean A-1 is answered. Any other failure or error is a regression. The full history of how the suite got here — the 12 mechanical rewrites, the 3 skips, and the two real product defects the browser suites found on their first run — is under "Automated suite failure inventory" in [`../PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md).

Set `SCOREBOARD_DATA_DIR` as shown below when you run the whole suite, so the run never touches a real operator data folder.

Also run `.\.venv\Scripts\python.exe tools\check_markdown_links.py` before committing documentation changes; it checks every relative Markdown link in the repository (skipping `.venv`, `node_modules`, `.scratch`, `build`, and `dist`) and should report 0 broken links.

## Browser checks (Tasks 8-9)

`unittest discover -s tests -v` includes offline browser checks using Node.js,
Playwright, and installed Microsoft Edge. These are development tools only;
the scoreboard runtime remains Python/WebView2 with bundled static files.

Install once per machine, from the repository root:

```powershell
npm ci
```

This reads the root `package.json`/`package-lock.json` (private,
devDependencies only, Playwright pinned to 1.62.1) and installs Playwright
into `node_modules/` (gitignored). The `tests/ui/*.cjs` scripts launch the
Microsoft Edge that is already installed on Windows through Playwright's
`msedge` channel, so no browser binary download is needed.

`tests/ui/browser_support.py` resolves Playwright in this order: the
repo-local `node_modules` first, then an explicit `NODE_PATH` environment
variable pointing at a Node modules directory containing `playwright`, and
only as a last resort the old Codex desktop bundled runtime
(`~/.cache/codex-runtimes/...`), kept for hosts without a local `npm ci`.
Missing tooling everywhere fails explicitly and names `npm ci`; no browser
test is silently skipped.

Set `SCOREBOARD_CAPTURE_DIR` to an evidence output directory to capture the
Task 8 viewport matrix and JSON measurements while running
`python -m unittest tests.ui.test_spectator_browser -v`.

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
