# Test boundary

Tests sit at the lowest layer that can prove the behavior, as described in `../docs/PROJECT_STRUCTURE.md` section 6.

| Location | Scope |
|---|---|
| `unit/` | Pure domain and application behavior: state validation, clock math, display formatting, and command transitions, all under an injected fake monotonic clock. |
| `integration/` | Persistence, recovery, diagnostics, and the view bridge, each inside its own temporary data directory with injected fake wall and monotonic clocks. |
| `integration/test_full_game_rehearsal.py` | One whole game through the real bridge: pregame countdown, four quarters of snap-by-snap play, halftime with the warmup boundary, an undo, a crash and resume in the third quarter, and End Game. It takes roughly 30 seconds because it is also a persistence soak — several thousand refresh ticks and their checkpoints. |
| `test_displays.py` | Host display-selection helpers that need no window. |
| `unit/test_layout_schema.py` | Pure presentation-layout schema and validation: coordinate model, safe-area policy, widget shape, and strict-validate-with-fallback rule — no I/O. It also covers F3's **layout-only groundwork** for `status_message`/`status_clock`: geometry, the Status rail group, upgrade warnings, and hiding on an absent value. It does not prove authoritative status state, commands, bridge values, or operator controls; those do not exist yet. |
| `integration/test_layout_persistence.py` | `layouts.json` read/write, atomic replace, schema-version fallback, and the "never touch `config.json`/`scoreboard.db`" boundary, each inside its own temporary data directory. |
| `integration/test_layout_bridge.py` | `PresentationLayouts` and its host wiring: save/select/delete/reset, publish-on-change, and the guarantee that a layout action advances no state revision, submits no command, and writes no action-history row. |
| `integration/test_spectator_layout_render.py` | Pure-Python renderer contract for the JavaScript/Python layout literals and the control-free spectator page. It includes the two F3 layout slots but explicitly permits them to be empty while authoritative F3 is unfinished. |
| `integration/test_layout_editor_contract.py` | The editor page exposes a control for every editable widget property, builds its widget list from `widget_descriptors()` rather than a hard-coded id, and contains no `data-command`, `api.command`, or `CommandType` reference. |
| `unit/test_field_assistant.py` | Pure Field Assistant rules (added September 5, 2026): the FA-01 through FA-18 matrix — coordinate round-trip, the corrected fixed-per-team direction with a mirrored on-screen goal side, series/line-to-gain, normal play, incomplete pass, fourth-down proposal, goal-line exceptions, penalty shortcuts and outcomes, explicit turnover, touchdown/try/field-goal/safety/kickoff transitions, (FA-30) `PRE` calculating exactly as the 1st quarter does while `HALF`/`OT`/`FINAL` stay manual, and (FA-31) the `manual` escape hatch — stated team/down/distance with only the line to gain derived, goal-to-go, clamping at the goal line, and every rejection — with no I/O and no clock. |
| `integration/test_field_assistant_rehearsal.py` | The `finalize_field_action` composite command through the real bridge (FA-17/18/21-25/28): one revision/one history row/one published snapshot per finalize, undo restoring every changed field and score as one action, clock values and running flags left untouched, active-series recovery, a simulated persistence failure leaving no partial state, and a multi-quarter rehearsal sequence. |
| `integration/test_logs_folder.py` | The `open_logs_folder` host action (added September 5, 2026): it opens the folder that holds the diagnostics log through an injected opener, advances no revision, leaves a running clock running, reports rather than raises when Explorer refuses, and says so plainly when there is no log file. |
| `integration/test_team_library.py` | `teams.json` read/write, atomic replace, schema-version fallback, and the "never touch `config.json`/`layouts.json`/`scoreboard.db`" boundary (added September 6, 2026): round-trip, one bad stored entry dropped while siblings load, a later duplicate name dropped, the 64-team cap, colour/short-name validation and derivation, and `TeamLibrary.find()`/`sorted()`. |
| `integration/test_team_presets.py` | `TeamPresets` (added September 6, 2026): identity lookup by current team name for both sides, `state()`/`save()`/`delete()` messages and diagnostics notes (`TEAM_LIBRARY_FELL_BACK`, `TEAM_PRESET_SAVED`, `TEAM_PRESET_DELETED`, `TEAM_PRESET_REFUSED`), a refused save/delete returning `ok: False` with the issue message, and a failed disk write keeping the previous in-memory library. |
| `integration/test_publish_off_lock.py` | C4: proves a blocked window push does not hold `_command_lock`, serial stale-batch rejection, bridge error containment, and off-lock `on_accepted`. **Known gap:** it does not force two `_deliver` calls to interleave between the key check and their per-window offers, so it does not yet prove cross-thread stale-proof delivery. |
| `integration/test_window_publisher.py` | `WindowPublisher` (added September 6, 2026): `offer()` delivers inline before `start()`; once started, a delivery blocked mid-flight leaves only the latest of several further offers for the same window to be delivered after release; `on_stall`/`on_recovered` each fire exactly once around one blocked delivery under an injected monotonic; `stop()` returns within its timeout against a stuck delivery; and a raising `deliver` callable never kills the delivery thread. |
| `integration/test_display_drawer_contract.py` | C5 (added September 6, 2026): `Reopen Display` is a 44 px target, the display selector lives in its own drawer with host actions only, and `reopen_display` falls back to that drawer rather than Corrections. |
| `integration/test_team_bridge.py` | F4 (added September 6, 2026): `teams()`/`save_team()`/`delete_team()` on the operator bridge advance no revision, submit no command, and write no history row; every operator and spectator view carries each side's saved identity or `null`; a bridge built without a library still answers plainly. |
| `integration/test_team_presets_ui.py` | F4 (added September 6, 2026): source contract for the Teams drawer — the tool-bar entry, the form ids, apply buttons that are ordinary `set_team_name` command controls, `api.teams()/save_team()/delete_team()` as host actions, and no team name computed anywhere but from a preset. |
| `integration/test_crowd_status_ui.py` | F3 and I4's operator surfaces (added September 6, 2026), as a source contract like `test_display_drawer_contract.py`: every crowd message has an always-visible button outside every drawer, the crowd row sends only the four status commands and asks for no confirmation, `TIMEOUT` starts its 60-second countdown in one press, the crowd row is a fixed grid row so the board stays the only flexing one, the `LAST:` strip opens the Undo history, the history renders only labels Python produced and marks the next Undo, and it offers no way to reach past a newer entry. The U-001 visual fit it deliberately does not attempt is measured by hand with Playwright/Edge and recorded in `docs/UX_AND_LAYOUT.md` section 8. |
| `unit/test_status_clock.py` | F3's `StatusCountdown` engine (added September 6, 2026), mirroring `test_play_clock.py`'s coverage: load/start/stop/clear, monotonic deadline math, never below zero, stopping at zero, a delayed callback creating no drift, and a non-preset value rejected without changing state. It has no `correct` and no `reset` by design — the operator reloads a preset instead — which this file also pins. |

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

As of the September 6, 2026 reconciliation a clean temporary Python 3.11.9 environment with Node.js on `PATH` reports **853 tests, 0 failures, 0 errors, 3 skipped** in 48.448 seconds. The repository-local `.venv` on this machine points to a stale base-interpreter path and was not used as evidence. The 3 skips are `tests.unit.test_commands.ClockCouplingTests.test_game_clock_start_clears_a_running_play_clock`, `test_game_clock_stop_clears_a_running_play_clock_in_the_same_commit`, and `tests.integration.test_bridge.ExpirationHistoryTests.test_game_clock_expiry_clears_a_running_play_clock_durably` — each explicitly names question A-1. Read a skip as "blocked on A-1," never as passing. Any other failure or error is a regression. The history is under "Automated suite failure inventory" in [`../PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md).

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
