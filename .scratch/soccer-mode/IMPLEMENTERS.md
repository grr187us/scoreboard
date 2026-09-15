# Soccer mode: implementation context (approved spec, September 15, 2026)

Read, in order: `.scratch/soccer-mode/spec.md` (approved; it is the contract), `AGENTS.md`,
`.scratch/soccer-mode/CONTEXT_FOR_AGENTS.md` (code facts; ignore its "documents only" rule, that phase is over).
The drafts (`domain_draft.md`, `design_draft.md`, `seams_audit.md`, `test_plan.md`) hold detail the spec
summarises; where they disagree with the spec, the spec wins.

## Hard rules (every agent)

1. **Football is frozen.** You may create new files and edit ONLY the files listed under your ownership below.
   Never touch any file under `src/scoreboard/domain/*.py` (top level), `application/service.py`, `snapshots.py`,
   `host/bridge.py`, `host/startup.py`, `host/hotkeys.py`, `host/cutscenes.py`, `presentation/cutscenes.py`,
   `views/operator/`, `views/spectator/`, `views/startup/`, `views/field_assistant/`, `views/cutscenes/`,
   `views/layout/`, `views/shared/board.css`, or ANY existing file under `tests/`. If your task seems to need one
   of these, stop, write the reason into your final report, and leave it unchanged.
2. Shared files you are allowed to edit (named per agent) get **additive, defaulted seams only**: a new keyword
   argument whose default reproduces today's behaviour, a new function, a new constant. Never rename, reorder,
   or change an existing default.
3. Never run `git commit`, `git switch`, `git stash`, `git checkout --`, or `git reset`. Do not touch
   `.scratch/soccer-mode/football_golden/` or `baseline/`.
4. Python: `./.venv/Scripts/python.exe` (Bash) or `.\.venv\Scripts\python.exe`. Never bare `python`.
5. Tests: `SCOREBOARD_DATA_DIR="$PWD/.scratch/soccer-mode/agent-data/LETTER" PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m unittest tests.unit.test_soccer_x`
   (never `-t .`, never the owner's live folder `C:\Users\505gr\OneDrive\Desktop\Scoreboard Logs`). Run the full
   suite once at the end (`-m unittest discover -s tests`) and report the totals. Baseline is 1353 / 0 / 0 / 3 skipped;
   your new tests add to 1353; nothing may fail.
6. Node/Playwright (agents C, D, F only): `export PATH="/c/Program Files/nodejs:$PATH"`; Edge channel;
   `.cjs` scripts under `tests/ui/` run through `tests/ui/browser_support.py`. Read `tests/ui/test_keyboard_browser.py`
   and `tests/ui/keyboard.cjs` first and copy the pattern.
7. Write scripts to files; do not put big Python in a `-c` string. Console is cp1252: `PYTHONIOENCODING=utf-8`.
8. Every new Python module starts with a docstring naming the football module it mirrors and the spec section.
   Copy football's style: frozen dataclasses, `Final` constants, `__all__`, comments that say why.
9. Tests mirror football's conventions (`tests/integration/support.py` `TemporaryDataDirectoryTest`,
   `FakeMonotonic`, source-contract tests that read the JS/CSS files as text). Table-driven where sensible.
10. Report at the end: files created/edited, tests added, the suite totals you observed, anything you could
    not do and why, and any interface decision another agent must know. Keep the report under 60 lines.

## Ownership

| Agent | Owns (create/edit) | Must not create |
|---|---|---|
| **A** domain + application | `src/scoreboard/domain/soccer/` (all), `src/scoreboard/application/soccer_service.py`, `soccer_snapshots.py`, `soccer_recovery.py`, `src/scoreboard/infrastructure/soccer_store.py`; seams in `infrastructure/persistence.py` (`read_stored_game(path, *, decode=snapshot_to_state)`, and if a subclass override is not enough, `GameStore(..., encode=state_to_snapshot)`) and `application/recovery.py` (`inspect_recovery(..., decode=..., stop_clocks=...)`); tests `tests/unit/test_soccer_state.py`, `test_soccer_commands.py`, `test_soccer_clock.py`, `test_soccer_rules.py`, `test_soccer_formatting.py`, `test_soccer_shootout.py`, `tests/integration/test_soccer_service.py`, `test_soccer_persistence.py`, `test_soccer_recovery.py`, `test_soccer_full_game_rehearsal.py`; `.scratch/soccer-mode/api_domain.md` (write it FIRST, see below) | anything under `host/`, `views/`, `presentation/` |
| **B** host + startup | `src/scoreboard/host/app.py` (SportProfile seam only), `src/scoreboard/__main__.py` (`--sport`), `src/scoreboard/infrastructure/paths.py` (`for_sport`), `src/scoreboard/host/soccer_app.py`, `host/soccer_bridge.py`, `host/soccer_hotkeys.py`, `host/sport_picker.py`, `views/sport_picker/`, `views/soccer_startup/`; tests `tests/integration/test_sport_picker_startup.py`, `test_soccer_hotkey_table.py`, `test_soccer_bridge.py`, `test_soccer_host_application.py`, `tests/unit/test_soccer_view_models.py`; `.scratch/soccer-mode/api_bridge.md` (write when the view model shape is final) | domain, presentation, operator views |
| **C** operator page | `src/scoreboard/views/soccer_operator/` (index.html, soccer_operator.js, soccer_operator.css, keyboard.js); tests `tests/integration/test_soccer_operator_ui.py`, `test_soccer_crowd_status_ui.py`, `test_soccer_keyboard_source.py`, `tests/ui/soccer_keyboard.cjs`, `soccer_u001.cjs`, `test_soccer_keyboard_browser.py`, `test_soccer_u001_browser.py`, `tests/ui/soccer_bridge_server.py`; preview stub `.scratch/soccer-mode/preview/` | any Python under `src/` |
| **D** presentation | `src/scoreboard/presentation/soccer_layout.py`; seams in `presentation/layout.py` (`_validate_screen` registry/defaults kwargs only), `infrastructure/layouts.py` (`schema=` kwarg), `host/layout_bridge.py` (`layout_module=` kwarg); `views/shared/board.js` (additive SOCCER_* literals + registry seam, per spec 2.3); `views/soccer_spectator/index.html`, `soccer_spectator.js`, `soccer_spectator.css`; tests `tests/unit/test_soccer_layout_schema.py`, `test_soccer_grid_preset.py`, `tests/integration/test_soccer_layout_bridge.py`, `test_soccer_spectator_layout_render.py`, `test_soccer_spectator.py`, `tests/ui/soccer_spectator.cjs`, `test_soccer_spectator_browser.py`, `soccer_editor.cjs`, `test_soccer_editor_browser.py` | cutscene files |
| **F** cutscenes | `src/scoreboard/presentation/soccer_cutscenes.py`, `infrastructure/soccer_cutscene_packs.py`, `host/soccer_cutscenes.py`, `views/soccer_spectator/cutscenes/soccer.js`, `soccer.css`, `views/soccer_cutscenes/`; tests `tests/unit/test_soccer_cutscene_schema.py`, `tests/integration/test_soccer_cutscene_director.py`, `test_soccer_cutscene_packs.py`, `test_soccer_cutscenes_window.py`, `test_soccer_cutscene_scene_contract.py`, `tests/ui/soccer_goal.cjs`, `test_soccer_goal_browser.py` | the spectator index.html (D owns it; tell D in your report which script/link tags it must include) |
| **G** field assistant | `src/scoreboard/host/soccer_field_assistant.py` (`SoccerFieldAssistantBridge`), `views/soccer_field_assistant/`; tests `tests/integration/test_soccer_field_assistant.py`, `test_soccer_field_assistant_window.py`, `test_soccer_field_assistant_ui_contract.py` | soccer_bridge.py (B owns; you receive a `SoccerBridge` instance) |

`tools/build_package.py` `REQUIRED_FILES` and docs are done by the integrator after the agents finish.
Every agent lists its new view files in its report so the integrator can add them.

## Interface contracts (write code to these names; if you must deviate, say so in `api_*.md` and the report)

### Domain (`scoreboard.domain.soccer`)

Agent A publishes `.scratch/soccer-mode/api_domain.md` within its first 20 minutes with the real signatures;
everyone else polls for that file (`ls`) before depending on it and codes against spec 3 until then.

- `state.py`: `SoccerState` (fields per spec 3.1), `CardEvent(team, kind, player_number, period, clock_display)`,
  `ShootoutKick(team, round, kicker_number, made)`, `PERIOD_LABELS`, `LIVE_PERIODS = ("1st","2nd","OT1","OT2")`,
  `INTERVAL_PERIODS = ("PRE","HALF")`, `STAT_NAMES = ("shots","saves","corners","fouls")`, `CARD_KINDS`,
  `SOCCER_STATUS_LABELS = ("INJURY","DELAY","WEATHER")`, `lifecycle_for_period(label)`, `SoccerState.evolve(**changes)`,
  derived properties `home_yellow`, `home_red`, `away_yellow`, `away_red`, `shootout_home_made`, `shootout_away_made`.
- `commands.py`: `SoccerCommandType(str, Enum)` with `.value` equal to the snake_case names in spec 3.2;
  `SoccerCommand` (mirror of `Command`: `type`, `args`, `expected_revision`, `source`), `SoccerCommandError`,
  `SoccerCommandResult`, `SoccerUndoEntry`, `SOCCER_UNDOABLE_COMMANDS`, `SOCCER_NON_UNDOABLE_COMMANDS`,
  `SOCCER_ALLOWED_ARGUMENTS: dict[SoccerCommandType, frozenset[str]]`,
  `build_soccer_command(name, args, expected_revision, *, source="operator")` (the airlock, mirror of
  `host.bridge.build_command`), `validate_soccer_command`.
- `clocks.py`: `SoccerGameClock.from_state(state, monotonic_clock=)`, `SoccerStatusCountdown.from_state(...)`;
  same method names as football's `GameClock`/`StatusCountdown`.
- `rules.py`: `SoccerRules` (spec section 8 fields), `default_soccer_rules()`, `SOCCER_RULE_FIELDS`,
  `SoccerRules.period_seconds(label)`, `read_soccer_rules(paths)`, `write_soccer_rules(paths, rules)`,
  `soccer_rules_from_mapping(raw)`, `soccer_rules_to_mapping(rules)`.
- `formatting.py`: `format_period(label)` giving `1st Half` etc., `format_period_short`,
  `format_soccer_clock(value, direction, maximum)`, `format_stat(name, value)`, `format_cards(yellow, red)`,
  `format_shootout_dots(kicks, team)`.
- `shootout.py`: pure functions `next_kicker(kicks, first_kicker, initial_kickers)`, `is_decided(...)`,
  `winner(...)`, `current_round(...)`, `in_sudden_death(...)`.

### Application

`SoccerService(*, state=None, monotonic_clock=None, rules=None)` with the same accessor names as
`ScoreboardService` minus play-clock ones, plus `mercy_reached: bool`, `period_decision() -> dict`,
`submit(SoccerCommand)`, `observe_tick(now) -> SoccerTickObservation` (mirror football's `TickObservation` fields
minus play clock). `initial_soccer_state(rules, *, revision=0)`. `soccer_snapshots.state_to_snapshot` /
`snapshot_to_state` (top-level `"sport": "soccer"`). `SoccerGameStore.open(paths, ...)` same signature as
`GameStore.open`. `soccer_recovery.inspect_soccer_recovery(paths, *, diagnostics=None, stamp=None) -> RecoveryReport`,
`resume_recovered_soccer_game(...)`, `start_new_soccer_game(...)` mirroring football's signatures exactly.

### Host

`SoccerApplication(paths=None, *, monotonic_clock=None, diagnostics=None, acquire_lock=True)`; `paths` is the
**root** `ScoreboardPaths`; it derives `self.paths = root.for_sport("soccer")` and keeps `self.root_paths` for
`teams.json`. Same public surface as `ScoreboardApplication` (`can_resume`, `recovery_payload`, `resume`,
`start_new`, `tick`, `set_publisher`, `set_field_assistant_active`, `set_cutscenes_active`, `set_display_watch`,
`start_refresh`, `stop_refresh`, `display`, `layouts`, `teams`, `rules`, `cutscenes`, `shutdown`,
`reopen_spectator`, `close_spectator`, `spectator_opened/closed`, `profile`).
`SoccerBridge` mirrors `ScoreboardBridge` (`command(name, args, expected_revision, *, source="operator")`,
`snapshot`, `operator_view_model`, `spectator_view_model`, `rules`, `save_rules`, teams, displays, folders,
layouts, `trigger_cutscene(event, team)`, `open_field_assistant`, `open_cutscenes`, history). View-model paths
per spec 3.3. Agent B publishes `.scratch/soccer-mode/api_bridge.md` with the exact `operator_view_model()`
JSON shape (one full example) as soon as it is stable; agents C and G build against it (and against spec 3.3
until it exists). `SportProfile` per spec 2.3; football's `ScoreboardApplication.profile` is the football
profile and nothing in football's path changes.

### Presentation

`soccer_layout` exports per spec 2.2/5.1; the layout document shape is identical to football's v3
(`schema_version` 3, `widgets`, `elements`, `screens.pregame`, `screens.halftime`) so `infrastructure/layouts.py`
can persist it with a `schema=` object exposing `default_layout()`, `validate_layout(raw)`, `clamp_layout`,
`reset_widget`, `widget_descriptors()`, `screen_descriptors()`, `preset_descriptors()`,
`screen_preset_descriptors()`, `limits()`. Board kind for the soccer game screen is `"soccer"`; event screens keep
kind `"event"` and the football event registry unchanged.

### Cutscenes

`soccer_cutscenes.build_program(play_id, event, pack, spectator_view, layout, board_layout, *, team)` returns a
program document with the same keys `views/spectator/cutscene.js` already reads (copy football's `build_program`
output shape exactly; read `presentation/cutscenes.py`). `SoccerCutsceneDirector(paths, *, diagnostics, monotonic,
read_spectator_view, read_board_layout)`; `trigger(event, team)`; `SoccerCutscenesBridge(director, operator)`.

### Field assistant

`SoccerFieldAssistantBridge(operator: SoccerBridge)` with `get_snapshot()`, `preview_assist(action: dict)`,
`finalize_assist(action: dict, expected_revision: int)`; actions `{"kind": "stat"|"card"|"shootout_kick"|"first_kicker", "team": ..., ...}`.
It submits through `operator.command(name, args, expected_revision, source="field-assistant")`.
