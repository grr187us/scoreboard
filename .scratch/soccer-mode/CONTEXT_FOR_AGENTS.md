# Soccer mode: shared context for research/design agents (September 15, 2026)

Read `.scratch/soccer-mode/FABLE_PROMPT.md` first: it is the owner's brief and its rules bind you.
Then `AGENTS.md`. You are producing **research and design documents only** for the spec checkpoint.

## Hard rules for every agent

- **Do not create, edit, or delete anything under `src/`, `tests/`, `tools/`, `docs/`, or the repo root.**
  Football is frozen. Only write inside the file(s) you own under `.scratch/soccer-mode/`.
- Do not run `git commit`, `git switch`, `git stash`, or anything that changes the working tree state.
  Branch is `feature/soccer-mode`; leave it there.
- Python is `./.venv/Scripts/python.exe` (Bash) / `.\.venv\Scripts\python.exe` (PowerShell). No bare `python`.
- Never point `SCOREBOARD_DATA_DIR` at `C:\Users\505gr\OneDrive\Desktop\Scoreboard Logs` (the owner's live data).
  Use an isolated scratch folder under `.scratch/soccer-mode/` or a temp dir.
- Console is cp1252: run any harness with `PYTHONIOENCODING=utf-8`.
- Baseline suite (recorded September 14, 2026 on this branch's first commit `0f5c93d`):
  **1353 tests, 0 failures, 0 errors, 3 skipped** (`.scratch/soccer-mode/baseline/suite_baseline.txt`).
  The 3 skips are `@unittest.skip` markers naming open question A-1. Never edit an existing test.

## What the app is (facts established by reading the code)

- Package `src/scoreboard/`. Layers: `domain/` (state, commands, clocks, rules, formatting, field_assistant),
  `application/` (service, snapshots, recovery), `infrastructure/` (paths, persistence, config, layouts, teams,
  cutscene_packs, diagnostics), `presentation/` (layout schema, cutscene program builder), `host/` (app, bridge,
  startup, cutscenes, layout_bridge, teams, hotkeys, publisher, displays), `views/` (operator, spectator,
  layout, field_assistant, cutscenes, startup, shared).
- `GameState` (`domain/state.py`) is a frozen dataclass; `evolve(**changes)` advances the revision.
  `ScoreboardService` (`application/service.py`) is the only writer; `submit(Command)` → `CommandResult`.
  Handlers return `_Transition(event, changes, game_clock, play_clock, status_clock, undo, clears_undo, ...)`.
  Undo is a bounded LIFO of `UndoEntry` (max 20); `UNDOABLE_COMMANDS`/`NON_UNDOABLE_COMMANDS` are frozensets in
  `domain/commands.py`; crowd-status commands are in neither (they never touch undo).
- Clocks: `GameClock`, `PlayClock`, `StatusCountdown` in `domain/clocks.py`, all monotonic-deadline countdowns
  over an injected `monotonic_clock`. `format_game_clock` rounds UP to whole seconds `M:SS`.
  The game clock's `maximum_seconds` carries the period length; `GameRules.period_seconds(label)` decides what a
  quarter change loads. PRE and HALF run interval countdowns on the same engine.
- `GameRules` (`domain/rules.py`) is a frozen dataclass stored in `config.json` under `"rules"`;
  `RULE_FIELDS` drives the Setup drawer; bridge `rules()` / `save_rules()` are host actions (no revision).
- Persistence: `GameStore` (SQLite `scoreboard.db` + `scoreboard.backup.db`), `record_command` writes state +
  history row in one transaction; `checkpoint` once per displayed second; `snapshot_to_state`/`state_to_snapshot`
  in `application/snapshots.py` (additive keys, older snapshots recover). `inspect_recovery(paths)` returns a
  `RecoveryReport`; `resume_recovered_game` / `start_new_game` build a service.
- Host: `ScoreboardApplication(paths, monotonic_clock=..., diagnostics=...)` takes the instance lock,
  `inspect_recovery`, creates `PresentationLayouts`, `TeamPresets`, `CutsceneDirector`, reads rules.
  `resume()` / `start_new()` → `_begin()` opens the `GameStore`, builds `ScoreboardBridge`.
  `WindowHost(application)` creates pywebview windows: `run(startup_choice=None, interactive=False)` shows
  `views/startup` (StartupBridge: get_recovery / resume_recovered_game / start_new_game) when a game exists,
  else `_choose_startup("new")`; `_choose_startup` creates the operator window (`view_url("operator")`),
  `_operator_loaded` opens the spectator, starts the publisher, refresh loop (10 Hz), and the button-box hook
  (`host/hotkeys.py` `HOTKEY_TABLE`: F15..F22 → play-clock presets, clear, start; F21/F22 game clock start/stop).
- Bridge (`host/bridge.py`): `ScoreboardBridge.command(name, args, expected_revision)` is the airlock
  (`_ALLOWED_ARGUMENTS`, `build_command`); `operator_view_model` / `spectator_view_model` produce every string
  (Python formats, JS only renders). Host actions (displays, folders, layouts, teams, rules, cutscenes) advance
  no revision. `FieldAssistantBridge` has get_snapshot / preview_field_action / finalize_field_action /
  set_assistant_direction. `SpectatorBridge` is read-only plus `close_display`.
- Presentation layout (`presentation/layout.py`, ~4400 lines): schema v3 documents with a top-level game screen
  plus `screens.pregame` / `screens.halftime`. Registries: `WIDGET_IDS`/`WIDGET_FIELDS`/`WIDGET_TEXTS`/
  `OPTIONAL_WIDGET_IDS`/`WIDGET_GROUPS` (game) and `EVENT_WIDGET_*` (event); `WIDGET_REGISTRIES = {"game", "event"}`;
  `SCREEN_IDS = ("game","pregame","halftime")`, `SCREEN_KINDS`. `_validate_screen(raw, screen_id)` looks the registry
  up by screen id. Presets: `preset_descriptors()` (classic, broadcast, big_score, tigers, stadium, grid) and
  `screen_preset_descriptors()`. The Scoreboard Grid preset (`_grid_preset_layout`) is the owner's look:
  `#030A12` bg, `#071321` panels, `#F2F2F2` lettering, `#F5AE08` amber clock, `#08439A` blue / `#A50021` red
  banners, Bahnschrift Condensed labels, `varsity` (Graduate) digits, `fit_text` on names/scores/clocks.
- Renderer `views/shared/board.js` mirrors the Python registries as strict JSON literals (`WIDGET_IDS`,
  `WIDGET_FIELDS`, ..., `EVENT_*`, `DEFAULT_LAYOUT`, `DEFAULT_SCREENS`); tests lift those literals and compare them
  to Python. `REGISTRIES = {game, event}`, `build(container, kind)`, `applyLayout`, `applyModel`,
  `screenForLifecycle(lifecycle)` (PRE_GAME→pregame, HALFTIME→halftime, else game). The spectator page
  (`views/spectator/spectator.js`) builds `#game-board` (game) and `#event-board` (event).
- Layout editor (`views/layout/`) is driven by `layout_state()` payload: `screens` descriptors (id, label, kind,
  widgets, widget_groups), `presets`, `screen_presets`, `limits`; `Board.build(boardRoot, descriptor.kind)`.
- Cutscenes: `presentation/cutscenes.py` (`CUTSCENE_EVENTS`, `EVENT_TEAM`, `EVENT_SUBLINE`, `build_program`),
  `infrastructure/cutscene_packs.py` (scans `<data>/cutscenes/`, `cutscenes.json`), `host/cutscenes.py`
  (`CutsceneDirector`, `CutscenesBridge`), spectator player `views/spectator/cutscene.js`, scene registry
  `views/spectator/cutscenes/builtin.js` (+ tigers.js, crowd.js). Scene-file rules: no `http://`, `innerHTML`
  only from `*_MARKUP` constants, text via `textContent`, no brand hex, delayed one-shot animations run forwards.
  Tests scan every `*.js` under `views/spectator/cutscenes/` and assert exactly the five football ids are
  registered — a soccer scene file must live elsewhere (e.g. `views/soccer_spectator/cutscenes/`).
- Data files (`infrastructure/paths.py` `ScoreboardPaths`): `scoreboard.db`, `scoreboard.backup.db`,
  `config.json`, `layouts.json`, `teams.json`, `cutscenes.json`, `cutscenes/`, `scoreboard.lock`, `logs/`.
  Soccer gets `<root>/soccer/` for db/backup/config/layouts/cutscenes; `teams.json` is shared read-only in schema.
- Operator page (`views/operator/`): fixed grid rows `auto auto minmax(0,1fr) auto auto auto`
  (health, alert, board, crowd bar, quarter bar, tools); team panels with `SCORE ▸` arm (8 s auto-disarm) and
  `TIMEOUT · N`; clocks panel with game clock START/STOP + nudge strip + play clock; crowd bar (FLAG/TIMEOUT/
  INJURY/DELAY, CLEAR yellow only while raised, countdown + green START/red STOP only for TIMEOUT); quarter bar
  (◀ label ▶, TRY PENDING, LAST: strip → history drawer, UNDO…); tools (Teams ▸, Corrections ▸, Setup ▸,
  Field ▸, Field Assistant, Cutscenes, Shortcut Help, Advanced ▸, Game ▸). Drawers overlay and scroll inside.
  U-001: no page scroll at 1093×614, 1180×720, 1366×768. Buttons 44 px (crowd/quarter bars 36 px).
- Keyboard (`views/operator/keyboard.js`): Space clock toggle, 2/4 presets, P/S play clock, Q/Shift+Q quarter,
  ZXCV / NM,. scores (arm then apply), Ctrl+Z undo (confirm), D/T/O/F/L cutscenes, Shift+C cancel, Esc.
- Real-runtime harness pattern: `.scratch/post-live-fixes/realrun_pl3.py` + `shot.py` (ctypes window capture);
  Playwright/Edge against the real bridge: `tests/ui/bridge_server.py` + `tests/ui/keyboard.cjs`.
  Node is at `C:\Program Files\nodejs` (not on Bash PATH: `export PATH="/c/Program Files/nodejs:$PATH"`).

## Rules research established so far (verify and cite; do not treat as final)

- NFHS Rule 7-1: two 40-minute halves (or four 20-minute quarters); halftime 10 minutes unless coaches agree
  otherwise; 5 minutes before the first overtime, 2 minutes between overtime periods; overtime is a state
  association decision, maximum 20 minutes total.
- NFHS Rule 7-4 (wording quoted in a 2011 forum post; re-verify): clock stopped for injury, penalty kick,
  caution, disqualification, after a goal, when the referee orders it; 7-4-3: substitution by the leading team in
  the last five minutes of the second half. NFHS 6-2: home school timer is the official timer; visible clock
  counts down; the period ends on the horn (no added time).
- NCHSAA (2023-24 handbook + ncfsra.com summary; re-verify against the 2025-26 handbook): varsity conference
  ties → two complete 10-minute periods, no golden goal; regular season still tied → tie. Non-conference
  tournament and NCHSAA playoffs → NFHS tie-breaking procedure (kicks from the mark) after overtime. JV: two
  35-minute halves, no overtime. Mercy rule: 9-goal differential at halftime or any time after ends the match.
- NFHS kicks from the mark (NISOA 2011/2016 restatements): coin toss (visitors call), five kickers per team
  alternating, if tied five different players sudden victory, then any five sudden death.
- NCHSAA yellow-card tracking (nchsaa.org/yellow-card-tracking): 5 yellows = 1-game suspension, 10 = ejection,
  15 = second ejection; a non-ejection red counts as two yellows; coaches track and report.
- Boys play in fall, girls in spring; same rules (confirm).
