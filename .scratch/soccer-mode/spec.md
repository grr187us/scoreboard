# Soccer mode — specification for approval

**Status:** spec checkpoint, September 15, 2026. No product code has been written. Waiting for the owner's approval.
**Branch:** `feature/soccer-mode`, cut from `post-live-fixes` at `0f5c93d`. First commit `d05ac62` holds the Step 0 baseline tooling.
**Inputs:** `rules_research.md` (cited rules), `seams_audit.md` (line-level audit of every shared file), `design_draft.md`,
`domain_draft.md`, `test_plan.md` — all in this folder. Where a draft and this spec disagree, this spec wins.

## 0. Step 0 result (done)

| Check | Result | Where |
|---|---|---|
| Working tree clean before branching | yes: only `.scratch/soccer-mode/` untracked | `git status` on `post-live-fixes` |
| Full suite on `0f5c93d` | **1353 tests, 0 failures, 0 errors, 3 skipped** (the A-1 skips) in 90.9 s | `baseline/suite_baseline.txt` |
| Football golden run | 48 steps through the real `ScoreboardApplication` + `ScoreboardBridge`, injected monotonic and wall clocks; two runs diff empty (50 files) | `football_golden/golden_run.py`, `diff_golden.py`, `football_golden/baseline/` |
| Frozen-file hashes | SHA-256 of 164 files (`src/scoreboard/**`, `tests/**`, `tools/build_package.py`, `tools/scoreboard.spec`, `pyproject.toml`) | `football_golden/frozen_hashes.py`, `baseline/hashes_all.json` |

Golden run final state: HOME 7, AWAY 0, quarter FINAL, revision 42, 53 history rows. Re-run at every phase boundary:

```bash
export SCOREBOARD_DATA_DIR="$PWD/.scratch/soccer-mode/scratch-data"; export PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe .scratch/soccer-mode/football_golden/golden_run.py --out phaseN
./.venv/Scripts/python.exe .scratch/soccer-mode/football_golden/diff_golden.py baseline phaseN       # must be empty
./.venv/Scripts/python.exe .scratch/soccer-mode/football_golden/frozen_hashes.py --check .scratch/soccer-mode/baseline/hashes_all.json
./.venv/Scripts/python.exe -m unittest discover -s tests                                             # 1353 + new, 0/0/3
git diff --name-status post-live-fixes -- tests/ | grep -v '^A'                                     # must print nothing
```

The hash check reports every changed file. Section 2.4 lists which files are allowed to change (shared seams) and which
must stay byte-identical (frozen); a CHANGED line for a frozen file is a stop.

## 1. Rules research summary (full dossier: `rules_research.md`)

Primary source: the current **NCHSAA 2026-27 Handbook** §4.9 Soccer (the 2025-26 print URL now 404s; NCHSAA has rolled
forward). NFHS rules-book text is gated, so NFHS values come from NFHS's own comparative guide and state restatements
(MHSAA supplement, TASO), marked *secondary*.

| Rule | Value | Source / confidence |
|---|---|---|
| Varsity half | 40:00 (NFHS 7-1: 2×40 or 4×20) | NFHS guide, secondary; NCHSAA silent (AD #5) |
| JV | two 35-minute halves, **no overtime** | NCHSAA §4.9.1(n), (m)(3), primary |
| Halftime | 10:00 unless coaches agree otherwise | NFHS 7-1, secondary (AD #6) |
| Clock | counts **down**; home-school timer is official; a visible scoreboard clock is official time; period ends when the clock reaches 0:00 / the horn | NFHS 6-2 via MHSAA, secondary (AD #1) |
| Clock stops | goal, penalty kick, yellow card, red card, injury/referee's signal; leading team's substitution in the last 5:00 of the 2nd half (state option; NC adoption unconfirmed, AD #2) | NFHS 7-4 via NFHS guide, secondary |
| Intervals | 5:00 before OT1, 2:00 between OT periods | NFHS 7-1, secondary |
| Overtime, conference varsity | **two complete 10-minute periods, not sudden victory**; still tied → **tie** | NCHSAA §4.9.1(m), primary |
| Overtime, non-conference regular season | none; a tie stands | NCHSAA §4.9.1(m)(1), primary |
| Non-conference tournament and playoffs | NFHS tie-breaking procedure (kicks from the mark); **one goal is added to the winner's score**, an asterisk may mark advancement | NCHSAA §4.9.1(m)(2), primary |
| Conference tournament | not named; read as a conference game (2×10, tie stands) — inference (AD #3) | |
| Kicks from the mark | coin toss (visitors call), five kickers each, alternating, no rebound; tied after five → five *different* players, sudden victory; then any five, sudden death | MHSAA/TASO restatements of NFHS, secondary |
| Mercy | **Nine-Goal Rule**: 9-goal differential at halftime or any time in the 2nd half ends the game (no running-clock variant) | NCHSAA §4.9.1(k), primary; OT interaction unstated (AD #8) |
| Cards | 5 yellows = 1-game suspension, every 5 after = post-game ejection; playoffs reset the count and lower the threshold to 3; a red = two yellows; coaches/ADs track, officials report within 24 h | NCHSAA §4.9.1(j), primary |
| Boys vs girls | same rules; boys in fall (first game Aug 10), girls in spring (first game Mar 1) | NCHSAA §4.9.1(c)-(d), primary |
| Timer required | a home-school scorer/timer, or the referee by agreement | NFHS guide, secondary |

**Confirm with the AD** (each has a default in the Setup drawer, section 8): (1) is the scoreboard the official clock;
(2) NC adoption of the late-substitution clock stop; (3) conference-tournament classification; (4) that the older
"5-minute" figure was the pre-overtime interval, not the period; (5) 40:00 varsity halves; (6) 10:00 halftime;
(7) NFHS 2026-27 card-signalling change; (8) whether the Nine-Goal Rule re-triggers in overtime (default: no).

## 2. Architecture

### 2.1 Principle

Every sport-specific thing is a new module beside the football one. Football's modules keep their behaviour through
default arguments. The only `if sport ==` decisions in football code paths are host wiring (which application object
and which view names), named in 2.3. Zero changes to `domain/state.py`, `domain/commands.py`, `domain/clocks.py`,
`domain/rules.py`, `domain/formatting.py`, `application/service.py`, `application/snapshots.py`, `host/bridge.py`,
`host/startup.py`, `host/hotkeys.py`, `infrastructure/config.py`, `infrastructure/teams.py`, `views/operator/*`,
`views/startup/*`, `views/field_assistant/*`, `views/spectator/*`, `views/cutscenes/*`, `views/layout/*`, `views/shared/board.css`.

### 2.2 New modules

| Module | Mirrors | Contents |
|---|---|---|
| `domain/soccer/__init__.py`, `state.py` | `domain/state.py` | `SoccerState`, `CardEvent`, `ShootoutKick`, `PERIOD_LABELS`, `STAT_NAMES`, `CARD_KINDS`, `SOCCER_STATUS_LABELS`, validation, `evolve()`. Reuses `ClockValue`, `StateValidationError`, `TEAM_SIDES`, `MAX_TEAM_NAME_LENGTH`, `setup_prompt_detail` by import. |
| `domain/soccer/commands.py` | `domain/commands.py` | `SoccerCommandType` (own enum — a football test iterates football's `CommandType` and would break), `Command`/`CommandError`/`CommandResult`/`EventIntent`/`UndoEntry` copies, `UNDOABLE`/`NON_UNDOABLE` sets, `validate_command`, factories. |
| `domain/soccer/clocks.py` | `domain/clocks.py` | `SoccerGameClock`, `SoccerStatusCountdown` (copies retyped to `SoccerState`; football's engines `isinstance`-check `GameState`), `event_phase_for` reused by import. |
| `domain/soccer/rules.py` | `domain/rules.py` | `SoccerRules`, `SOCCER_RULE_FIELDS`, `period_seconds()`, `read_soccer_rules`/`write_soccer_rules` over `config.read_section`/`write_section` (soccer's own `config.json`). |
| `domain/soccer/formatting.py` | `domain/formatting.py` | `format_period`, `format_soccer_game_clock(direction)`, stat/card/shootout strings; reuses `format_game_clock`, `ceil_seconds`, `BLANK_DISPLAY`, `format_game_status`, `format_status_clock`. |
| `domain/soccer/shootout.py` | new | Pure kicks-from-the-mark rules: `next_kicker`, `is_decided`, `winner`, `round_of`, `sudden_death`. |
| `application/soccer_service.py` | `application/service.py` | `SoccerService`: same submit/apply/commit skeleton, own handlers and `_commit`, undo stack, `observe_tick`, `period_decision`, `mercy_reached`. |
| `application/soccer_snapshots.py` | `application/snapshots.py` | `state_to_snapshot` / `snapshot_to_state` with a top-level `"sport": "soccer"` and its own `schema_version`. |
| `application/soccer_recovery.py` | `application/recovery.py` | `inspect_soccer_recovery` = `inspect_recovery(soccer_paths, decode=..., stop_clocks=...)`, `resume_recovered_soccer_game`, `start_new_soccer_game`, `soccer_stopped_state`. |
| `infrastructure/soccer_store.py` | subclass | `SoccerGameStore(GameStore)` overriding `_display_key` (soccer has no play clock). Same schema, same file names, under `<root>/soccer/`. |
| `presentation/soccer_layout.py` | `presentation/layout.py` | Soccer widget registry (`SOCCER_WIDGET_IDS`, fields, labels, texts, optional set, groups), `default_soccer_layout`, `validate_soccer_layout`, `clamp_soccer_layout`, `reset_soccer_widget`, `soccer_widget_descriptors`, `soccer_screen_descriptors`, `soccer_preset_descriptors`, `soccer_screen_preset_descriptors`, `soccer_limits`, `SOCCER_FINAL_HIDDEN_WIDGET_IDS`. Same document shape (top-level game screen + `screens.pregame/halftime` on the football **event** registry, which soccer reuses unchanged). |
| `presentation/soccer_cutscenes.py` | `presentation/cutscenes.py` | `SOCCER_CUTSCENE_EVENTS = ("goal",)`, tables, `validate_manifest`, `builtin_pack`, `build_program(..., team)` — same program document shape so `cutscene.js` plays it unchanged. Reuses `CutsceneIssue`, `ManifestValidation`, `_validate_scene`, `STAGE`, `THEME`, `INTRO_IDS` by import. |
| `infrastructure/soccer_cutscene_packs.py` | `infrastructure/cutscene_packs.py` | Same scan/selection functions over the soccer events and `soccer_paths.cutscenes` / `cutscene_selection`. |
| `host/soccer_cutscenes.py` | `host/cutscenes.py` | `SoccerCutsceneDirector` (trigger takes `event, team`), `SoccerCutscenesBridge`. |
| `host/soccer_bridge.py` | `host/bridge.py` | `SoccerBridge` (own airlock, `command`, host actions: rules/save_rules, teams, displays, folders, layouts, cutscenes, open windows), `soccer_operator_view_model`, `soccer_spectator_view_model`, `SoccerFieldAssistantBridge`. Reuses `DisplayLink`, `DisplayStatus`, `SpectatorBridge`, `_json_safe`, `_open_in_explorer`, `TeamPresets`, `PresentationLayouts`. |
| `host/soccer_app.py` | `host/app.py` `ScoreboardApplication` | `SoccerApplication`: lock on `soccer/scoreboard.lock`, `inspect_soccer_recovery`, `PresentationLayouts(soccer_paths, layout_module=soccer_layout)`, `TeamPresets(football_paths)` (shared `teams.json`), `SoccerCutsceneDirector`, `read_soccer_rules`; `resume()/start_new()/_begin()/tick()/_publish()/shutdown()` same shape; exposes `profile` (2.3). |
| `host/soccer_hotkeys.py` | new | `SOCCER_HOTKEY_TABLE = (HOTKEY_TABLE[6], HOTKEY_TABLE[7])` — F21 start, F22 stop, nothing else. `host/hotkeys.py` untouched. |
| `host/sport_picker.py` + `views/sport_picker/` | new | `SportPickerBridge` (`choose_sport`, `last_sport`), `SportPickerHost` (2.5). |
| `views/soccer_startup/` | `views/startup/` | Recovery screen with soccer wording (Period, no play clock). `StartupBridge` reused. |
| `views/soccer_operator/` | `views/operator/` | `index.html`, `soccer_operator.js`, `soccer_operator.css`, `keyboard.js` (section 4). |
| `views/soccer_spectator/` | `views/spectator/` | `index.html`, `soccer_spectator.js`, `soccer_spectator.css`; loads `../shared/board.js`, `../spectator/cutscene.js`, `../spectator/cutscene.css`, `../spectator/cutscenes/builtin.js` (registry + helpers) and `cutscenes/soccer.js` + `soccer.css` (the GOAL scene). |
| `views/soccer_cutscenes/` | `views/cutscenes/` | Two trigger buttons (GOAL HOME / GOAL AWAY), Cancel, packs. |
| `views/soccer_field_assistant/` | `views/field_assistant/` | Section 6. |
| `tests/…` | | Section 9 (`test_plan.md`). |

### 2.3 Shared files and the exact seam

| File | Seam | Football default |
|---|---|---|
| `host/app.py` | (a) new `SportProfile` NamedTuple `(sport, operator_view, startup_view, spectator_view, field_assistant_view, cutscenes_view, field_assistant_bridge, cutscenes_bridge, hotkey_table)` and a `profile` attribute on `ScoreboardApplication` set to the football profile; (b) `_choose_startup` reads `view_url(self.application.profile.operator_view)` and `StartupBridge(...)` opens `profile.startup_view`; (c) `open_spectator`/`open_test_window` read `profile.spectator_view`; (d) `open_field_assistant`/`open_cutscenes` read the profile's view name and bridge factory; (e) `_start_button_box` passes `table=self.application.profile.hotkey_table`; (f) `run()` is split into `begin(startup_choice, interactive)` (everything before `webview.start()`) and `run()` = `begin(); webview.start(); shutdown()`. | Every attribute defaults to today's literal (`"operator"`, `"startup"`, `"spectator"`, `"field_assistant"`, `"cutscenes"`, `FieldAssistantBridge`, `CutscenesBridge`, `HOTKEY_TABLE`); `run()` body is unchanged in effect. This is the one place a sport-shaped decision exists in football code, and it is a profile lookup, not a branch. |
| `__main__.py` | `--sport {football,soccer}` argument. No sport and no `--resume/--new-game` → `SportPickerHost().run()`. `--sport football` or a bare `--resume/--new-game` → today's exact path. `--sport soccer` → `SoccerApplication` + `WindowHost`. `--check`/`--choose-data-folder` unchanged. | Existing shortcuts with `--new-game` behave exactly as today; a bare launch shows the picker (the owner's decision 1). |
| `infrastructure/paths.py` | `ScoreboardPaths.for_sport(sport) -> ScoreboardPaths(self.root / sport)` (new method). `teams` stays on the parent paths object. | No existing property changes. |
| `infrastructure/persistence.py` | `read_stored_game(path, *, decode=snapshot_to_state)`; `StoredGame.state` typed `Any`. | Default reproduces today's call. |
| `application/recovery.py` | `inspect_recovery(paths, *, diagnostics, stamp, decode=snapshot_to_state, stop_clocks=stopped_state)`; `_offer`/`_restored` use `stop_clocks`. | Defaults reproduce today's behaviour; football callers unchanged. |
| `infrastructure/layouts.py` | Every function gains `*, schema=None` (an object with `default_layout`/`validate_layout`; `None` = `presentation.layout`). | Same output when omitted. |
| `host/layout_bridge.py` | `PresentationLayouts(paths, *, diagnostics, link, layout_module=None)`; `layout_module` supplies `widget_descriptors`, `screen_descriptors`, `preset_descriptors`, `screen_preset_descriptors`, `limits`, `validate_layout`, `clamp_layout`, `reset_widget`, `default_layout`; passed through to `layouts_infra` as `schema`. `LayoutEditorBridge` unchanged. | `None` = today's module. |
| `presentation/layout.py` | `_validate_screen(raw, screen_id, *, registry=None, defaults=None, label=None)` (defaults to today's lookups). Nothing else. | Identical output for football calls. |
| `views/shared/board.js` | Add `SOCCER_WIDGET_IDS`/`SOCCER_WIDGET_FIELDS`/`SOCCER_WIDGET_TEXTS`/`SOCCER_OPTIONAL_WIDGET_IDS`/`SOCCER_DEFAULT_LAYOUT` JSON literals (mirrored by a new Python test), `REGISTRIES.soccer`, `registryForKind` gains `if (kind === 'soccer')` before the existing fallback, `build()` accepts `'soccer'`; the two `boardKind === 'game'` gates for `hidden_widgets`/formats become `=== 'game' \|\| === 'soccer'` (soccer's FINAL hide list rides the same path). | Unchanged for `'game'`/`'event'`; existing literals untouched. |
| `tools/build_package.py` | Additive `REQUIRED_FILES` entries for every new view file (the packaging test requires it). | Existing entries untouched. |
| `tools/scoreboard.spec`, `pyproject.toml` | No change (globs already cover `views/**` and `src/**`). | |

Named `if sport` decisions in football files: only the `profile` lookups in `host/app.py` above and the CLI switch in
`__main__.py`. Everything else is a new module or a defaulted keyword.

### 2.4 Frozen and allowed-to-change lists (checked by the hash tool at each phase)

**Byte-identical (a CHANGED line is a stop):** `domain/field_assistant.py`, `domain/state.py`, `domain/commands.py`,
`domain/clocks.py`, `domain/rules.py`, `domain/formatting.py`, `application/service.py`, `application/snapshots.py`,
`host/bridge.py`, `host/startup.py`, `host/hotkeys.py`, `host/cutscenes.py`, `host/teams.py`, `host/publisher.py`,
`host/displays.py`, `presentation/cutscenes.py`, `infrastructure/config.py`, `infrastructure/teams.py`,
`infrastructure/cutscene_packs.py`, `infrastructure/diagnostics.py`, `views/operator/*`, `views/field_assistant/*`,
`views/startup/*`, `views/spectator/*` (including `cutscenes/*`), `views/cutscenes/*`, `views/layout/*`,
`views/shared/board.css`, `views/shared/base.css`, `views/shared/render.js`, every existing file under `tests/`.

**Allowed, additive only:** `host/app.py`, `__main__.py`, `infrastructure/paths.py`, `infrastructure/persistence.py`,
`application/recovery.py`, `infrastructure/layouts.py`, `host/layout_bridge.py`, `presentation/layout.py`,
`views/shared/board.js`, `tools/build_package.py`, docs.

### 2.5 Startup, sport choice, memory of the choice, recovery per sport

```
Scoreboard.exe (no args)
  └─ SportPickerHost: window "Choose sport" (views/sport_picker), 520×360
        [  FOOTBALL  ]   [  SOCCER  ]        "Last time: Soccer" (pre-focused, never auto-chosen)
        choose_sport("football") ─► ScoreboardApplication()  (lock <root>/scoreboard.lock, inspect_recovery(<root>))
        choose_sport("soccer")   ─► SoccerApplication()      (lock <root>/soccer/scoreboard.lock, inspect_soccer_recovery(<root>/soccer))
        then WindowHost(app).begin(startup_choice=None, interactive=True):
             saved game for THAT sport ─► that sport's startup view (Resume / New)     else ─► operator window directly
        picker window destroyed; webview loop continues; shutdown at the end as today.
```

- The last choice is remembered in `<root>/config.json` section `"sport": {"last": "soccer"}` through
  `config.write_section` (read-tolerant like every preference). It only pre-focuses the button. **Owner choice A**
  (default: remember and pre-focus, require a click).
- `InstanceAlreadyRunning` from either constructor is reported by `preflight.report` exactly as `__main__` does today;
  the picker stays open so the operator can pick the other sport or quit.
- Recovery is per sport by construction: each application inspects only its own root. A football crash is never
  offered to soccer and vice versa (test `test_soccer_recovery.py`).
- Both sports may hold locks at once (different files). Two instances at once is not a supported workflow; documented.

### 2.6 Data on disk

```
<root>/                     football, unchanged: scoreboard.db, scoreboard.backup.db, config.json (+ "sport" section),
                            layouts.json, teams.json (shared, schema unchanged), cutscenes.json, cutscenes/, scoreboard.lock, logs/
<root>/soccer/              scoreboard.db, scoreboard.backup.db, config.json ("rules" = SoccerRules, "display", "presentation"),
                            layouts.json, cutscenes.json, cutscenes/ (+ README.txt), scoreboard.lock, logs/application.log
```

Soccer's display preference lives in soccer's `config.json` (OWNER CHOICE B: default separate, so a soccer laptop setup
cannot re-point the football wall; alternative: share football's). Motion preference likewise separate.

## 3. Soccer state, commands, history labels

### 3.1 `SoccerState` (frozen dataclass)

| Field | Type / default | Validation |
|---|---|---|
| `schema_version`, `app_version`, `revision` | `1`, `APP_VERSION`, `0` | as football |
| `home_name`, `away_name` | `"HOME"`, `"AWAY"` | 1–24 trimmed chars |
| `home_score`, `away_score` | `0` | 0–99 |
| `period` | `"PRE"` | one of `PERIOD_LABELS = ("PRE","1st","HALF","2nd","OT1","OT2","SHOOTOUT","FINAL")` |
| `lifecycle` | `"PRE_GAME"` | `PRE_GAME`, `IN_PROGRESS`, `HALFTIME`, `FINAL` (PRE→PRE_GAME, HALF→HALFTIME, FINAL→FINAL, else IN_PROGRESS) |
| `game_clock` | `ClockValue(pregame, False, pregame)` | max ≤ 60:00 (period length is the maximum; countdown engine) |
| `home_shots … away_fouls` (8 ints) | `0` | 0–99 |
| `cards` | `tuple[CardEvent, ...]` `()` | `CardEvent(team, kind ∈ {yellow, red}, player_number 0–99 or None, period, clock_display)`; counts are derived properties |
| `shootout_first_kicker` | `None` | home/away/None |
| `shootout_kicks` | `tuple[ShootoutKick, ...]` `()` | `ShootoutKick(team, round ≥ 1, kicker_number or None, made)` |
| `shootout_winner` | `None` | home/away/None, set only by `finish_shootout` |
| `game_status` | `None` | `SOCCER_STATUS_LABELS = ("INJURY", "DELAY", "WEATHER")` |
| `status_clock`, `status_clock_cleared` | `ClockValue(0, False, 1800)`, `True` | max 30:00 (the NCHSAA lightning wait is 30 minutes) |

Interval periods: `PRE` (KICKOFF IN, `pregame_seconds`) and `HALF` (UNTIL SECOND HALF, `halftime_seconds`) run on the
same game-clock engine exactly as football since September 9. Live periods: `1st`, `2nd` (`half_seconds`), `OT1`, `OT2`
(`overtime_seconds`). `SHOOTOUT` and `FINAL` load no clock (0:00 stopped, hidden on the wall).

### 3.2 Commands (`SoccerCommandType`)

| Command | Args | Undoable | Confirm | LAST label |
|---|---|---|---|---|
| `set_team_name` | team, name | no (pregame only) | local | — |
| `add_goal` | team, player? | **yes** | armed two-step | `HOME goal · 1–0` |
| `correct_goal` | team | yes | drawer | `HOME goal removed · 0–0` |
| `set_score` | team, value | yes | local | `HOME score 1 → 3` |
| `undo` | — | barrier pop | local (names the reversal) | — |
| `period_forward` / `period_back` / `set_period` | (label) | yes unless a clock was stopped or a fresh length loaded (then barrier), exactly football's rule | service confirmation, "Discard remaining pregame/halftime time?" wording | `Period 1st → HALF` |
| `new_game` | — | barrier | service | — |
| `end_game` | — | barrier | local (Game ▸) | — |
| `game_clock_start/stop/reset/correct` | (seconds) | no | reset/correct local | — |
| `add_stat` | team, stat ∈ shots/saves/corners/fouls, step ±1 | yes | no | `HOME shots +1 → 4` |
| `set_stat` | team, stat, value | yes | drawer | `HOME shots 4 → 6` |
| `add_card` | team, kind, player? | yes (compound: whole `cards` tuple) | armed card entry (CONFIRM) | `AWAY yellow #10 · 1st Half 32:14` |
| `remove_card` | team, index | yes (compound) | local | `Card removed: AWAY yellow #10` |
| `set_shootout_first_kicker` | team | yes | no | `Shootout: AWAY kicks first` |
| `shootout_kick` | team, made, kicker? | yes (compound) | no | `Shootout: HOME made #7 · 3–2` |
| `shootout_correct_kick` | index, made | yes (compound) | local | `Shootout kick 4: missed → made` |
| `shootout_remove_last` | — | yes (compound) | local | `Shootout: last kick removed` |
| `finish_shootout` | winner (must equal the derived winner) | barrier | local | `Shootout won by HOME 4–3` |
| `set_game_status` | label, seconds? | neither (F3 rule) | no | — |
| `clear_game_status`, `status_clock_start`, `status_clock_stop` | — | neither | no | — |

Rules baked into handlers:
- `add_goal` is refused in `SHOOTOUT`, `FINAL` and `PRE`/`HALF` (`GOAL_NOT_ALLOWED`); a goal never changes the clock
  unless `SoccerRules.stop_clock_on_goal` is on, in which case the same transition stops it (Undo restores the score
  only; the clock stays stopped — restarting is the operator's decision).
- `add_card` captures `period` and the formatted clock at that moment. No auto-escalation on a second yellow (owner
  choice C; the UI offers a `2ND YELLOW → RED` shortcut that sends yellow then red).
- Kicks-from-the-mark logic (`domain/soccer/shootout.py`): rounds of one kick per side, alternating from
  `first_kicker`; after `shootout_initial_kickers` each, decided as soon as mathematically settled (also earlier within
  the first five); then sudden death (decided after a complete pair when one side leads). `finish_shootout` is refused
  until decided; with `shootout_credit_goal` on (default **on**, NCHSAA §4.9.1(m)(2)) it adds one goal to the winner's
  score in the same transition and sets `lifecycle = FINAL`, `period = FINAL`.
- `period_decision` (PL-5 mirror) is raised by natural expiry in `2nd`, `OT1`, `OT2`; choices computed from the rules:
  after `2nd`: OT1 (if `overtime_periods ≥ 1`) or SHOOTOUT (if enabled and no OT) plus FINAL and Keep; after `OT1`: OT2
  or SHOOTOUT/FINAL; after `OT2`: SHOOTOUT (if enabled) / FINAL / Keep. Each choice is an ordinary confirmed `set_period`.
- `mercy_reached` is a derived view flag (`mercy_differential`, `mercy_applies`); it raises a prompt whose only
  actions are End Game (Game ▸ path) or Keep. Never automatic.

Snapshot: `application/soccer_snapshots.py` writes `{"sport": "soccer", "schema_version": 1, ..., "clocks": {"game": …},
"stats": {...}, "cards": [...], "shootout": {...}, "status": {...}}` and reads additively (missing blocks → defaults).

### 3.3 View-model paths (Python formats, JS copies)

`teams.home.name/score/identity`, `period`, `period_display` (`1st Half`, `Halftime`, `2nd Half`, `OT 1`, `OT 2`,
`Shootout`, `Final`), `lifecycle`, `clocks.game.{display,status,running,seconds,maximum_seconds,full_display,label}`
(`KICKOFF COUNTDOWN` / `HALFTIME COUNTDOWN` / `GAME CLOCK`), `clocks.event.*` (same shape as football),
`soccer.home.{shots,saves,corners,fouls}` and `*_display` (`S 4`, `SV 2`, `COR 3`, `F 1`),
`soccer.home.cards.{yellow,red,display,rows}` (`display` blank at 0 cards, else `Y 2 · R 0`; `yellow_display` `Y 2`),
`soccer.shootout.{active,first_kicker,winner,round,sudden_death,next_team,home_display,away_display,tally_display,home_made,away_made}`
(`● ○ ●`), `status.*` as football, `board.hidden_widgets` (clocks on FINAL and in SHOOTOUT), `mercy_reached`,
`period_decision.{pending,period,token,choices[]}`, `rules`, `rule_fields`, `status_labels`, `last_action`, `can_undo`,
`undo_history`, `undo_depth`, `setup`, `health`, `cutscenes`, `button_box`, `period_labels`.

## 4. Operator screen (`views/soccer_operator/`)

Same six fixed grid rows as football; only the board row flexes. 44 px live controls; crowd/period bars 36 px.

### 4.1 Idle (1st half, nobody armed)

```
┌ SCOREBOARD CONTROL · SOCCER   GAME 40:00 STOPPED   DISPLAY OPEN [Reopen Display][Display…] SAVED Rev 12 ┐
├──────────────────────────┬──────────────────────────────┬───────────────────────────┤
│ HOME                     │ GAME CLOCK                   │ AWAY                      │
│ EAGLES                   │          40:00               │ TIGERS                    │
│ [ GRACE identity stripe ]│         STOPPED              │ [ TMSA identity stripe ]  │
│ NOT CHOSEN            1  │   [  START  ] [  STOP  ]     │ NOT CHOSEN             0  │
│ [   SCORE ▸   ][S 4·SV 2]│ ─────────────────────────    │ [   SCORE ▸   ][S 6·SV 3] │
│ [−]SHOTS 4[+] [−]SAVES 2[+]│ PERIOD   [◀]  1ST HALF  [▶] │ [−]SHOTS 6[+] [−]SAVES 3[+]│
│ [−]CORNERS 3[+][−]FOULS 1[+]│ next: ▶ HALFTIME 10:00     │ [−]CORNERS 5[+][−]FOULS 2[+]│
│ [ YELLOW ][ RED ]  Y 0·R 0│                             │ [ YELLOW ][ RED ]  Y 1·R 0│
├──────────────────────────┴──────────────────────────────┴───────────────────────────┤
│ CROWD  [ — ]  [INJURY] [DELAY] [WEATHER]                                             │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ PERIOD [◀] 1st [▶]                              LAST: HOME shots +1 → 4  [ UNDO… ]   │
├──────────────────────────────────────────────────────────────────────────────────────┤
│ [Teams ▸][Corrections ▸][Setup ▸][Field Assistant][Cutscenes][Shortcut Help][Advanced ▸]      [ Game ▸ ] │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- Centre panel: clock, START/STOP, period ◀ ▶ with the next period and its length as text. No play clock, no extra
  stoppage control: **STOP is the stoppage** (NFHS: the timer stops on the referee's signal). Owner choice D: the
  design draft proposed a combined "STOPPAGE" button; not adopted, one press on STOP already does it.
- Crowd bar words: `INJURY`, `DELAY` (no countdown), `WEATHER` (one press raises the word and starts the configured
  lightning countdown, default 30:00). CLEAR (yellow) appears only while raised; the countdown group with green START /
  red STOP appears only for WEATHER (or while a countdown is still showing), to the right. Same show/hide rules as
  football's September 14 pass.
- Team panel height budget at 1093×614 (board row 356 px): h2 20 + name 24 + stripe 26 + NOT CHOSEN 0/18 + score
  (flex, `clamp(40px, 6vh, 72px)`) + score-controls 44 + stat row 44 + stat row 44 + card row 44 + 7 gaps 42 +
  padding 20 = 308 fixed → ≥ 48 px for the score. Measured, not assumed, in phase 3 (section 10).

### 4.2 Armed (HOME SCORE ▸ pressed) and card entry

```
│ HOME · SCORING           │            │ HOME · CARD              │
│ [      GOAL      ][ ✕ ]  │   or       │ [YELLOW #][__][NO #][CONFIRM][✕]│
```
GOAL applies `add_goal` and disarms (8 s auto-disarm, blur/Escape/drawer/dialog disarm, one team at a time). On
acceptance the page calls `trigger_cutscene("goal", team)` unless the Cutscenes drawer's "Play GOAL automatically"
switch is off; `Shift+C` / the Cutscenes window's CANCEL skips it. YELLOW/RED arm the same fixed block with a
`data-draft` number field, `NO #`, `CONFIRM` (sends `add_card`) and `✕`; `2ND YELLOW → RED` appears in the Corrections
drawer, not on the panel. Heading gains ` · SCORING` / ` · CARD` (text, not colour alone).

### 4.3 SHOOTOUT period

```
│ HOME                     │ SHOOTOUT · ROUND 3 · AWAY TO KICK │ AWAY                    │
│ EAGLES               1   │  HOME  ● ● ○      AWAY  ● ○       │ TIGERS               1  │
│ (score frozen)           │  Kicker # [ __ ]                  │                         │
│ [ SCORE ▸ ] disabled     │ [ HOME MADE ][ HOME MISSED ]      │ [ SCORE ▸ ] disabled    │
│ stat rows as usual       │ [ AWAY MADE ][ AWAY MISSED ]      │                         │
│                          │ [ FIRST KICKER: HOME|AWAY ] (before kick 1)                 │
│                          │ [ FINISH SHOOTOUT… ] (enabled only when decided)            │
```
The shootout panel replaces the clock block inside the same fixed-height centre panel only while `period ==
SHOOTOUT`; nothing floats otherwise. Only the side named by `next_team` has its MADE/MISSED enabled. FINISH SHOOTOUT…
confirms and names the winner and the resulting score (`Home wins 4–3 on kicks; score becomes 2–1`).

### 4.4 Drawers

- **Teams ▸** — identical to football (shared `teams.json`, `set_team_name` pregame-only, soft prompt).
- **Corrections ▸** — HOME/AWAY score `+1 −1 Set Apply…`; per-team stat `Set`; cards list (`#10 · 32:14 · 1st Half
  [Remove…]`), `2ND YELLOW → RED`; game clock `mm:ss Apply…` (must be stopped); period direct set; team names;
  shootout kick list with `Correct…`/`Remove last…`; Saved-to folder row.
- **Setup ▸** — section 8. **Game ▸** — Reset Game Clock…, End Game…, New Game…. **Display…**, **History**,
  **Shortcut Help**, **Advanced ▸** (test window, layout editor → soccer registry, logs) — as football.
- **Cutscenes** — opens the soccer Cutscenes window; the drawer-less "Play GOAL automatically" switch lives in that
  window and in Setup.
- Prompts: `period_decision` dialog (Keep / Overtime / Shootout / Final as offered); `mercy_reached` banner with
  `End Game…` and `Keep playing`.

### 4.5 Keyboard (`views/soccer_operator/keyboard.js`, new table)

| Key | Action |
|---|---|
| `Space` | Game clock Start / Stop (from the rendered snapshot) |
| `G` / `H` | HOME / AWAY goal — press once to arm, again to apply |
| `Q` / `Shift+Q` | Period forward / back (confirmed) |
| `A` `S` `D` `F` | HOME shots / saves / corners / fouls +1; with `Shift` −1 |
| `J` `K` `L` `;` | AWAY shots / saves / corners / fouls +1; with `Shift` −1 |
| `Y` / `Shift+Y` | HOME / AWAY yellow — arms the card entry (CONFIRM/Enter applies) |
| `R` / `Shift+R` | HOME / AWAY red — arms the card entry |
| `I` `E` `W` | Crowd INJURY / DELAY / WEATHER; `X` clears |
| `1` / `2` | Replay GOAL cutscene for HOME / AWAY; `Shift+C` cancel |
| `Ctrl+Z` | Undo (confirmation names the reversal) |
| `Esc` | Close dialog / drawer / disarm |

Button box: `SOCCER_HOTKEY_TABLE` registers only F21 (start) and F22 (stop); F15–F20 are not registered and the page
binds no F-keys, so they do nothing. `HOTKEY_TABLE` and firmware untouched.

## 5. Spectator board, layouts, event screens

### 5.1 Soccer widget registry (`presentation/soccer_layout.py`, mirrored in `board.js`)

| id | field | default visible |
|---|---|---|
| `home_name`, `away_name`, `home_score`, `away_score` | `teams.*` | yes |
| `game_clock_label` (text `GAME CLOCK`), `game_clock_value` | —, `clocks.game.display` | no / yes |
| `period` | `period_display` (format choice: `Standard` `1st Half` / `Short` `1ST`) | yes |
| `status_message`, `status_clock` | `status.display`, `status.clock_display` | yes (optional: hide when blank) |
| `home_shots`, `away_shots`, `home_saves`, `away_saves`, `home_corners`, `away_corners`, `home_fouls`, `away_fouls` | `soccer.<side>.<stat>_display` | **no** |
| `home_yellow`, `away_yellow`, `home_red`, `away_red` | `soccer.<side>.cards.yellow_display` / `red_display` (optional, blank at 0) | **no** |
| `shootout_home`, `shootout_away` | `soccer.shootout.home_display` / `away_display` (optional, blank until a kick) | **no** |

`SOCCER_FINAL_HIDDEN_WIDGET_IDS = ("game_clock_label", "game_clock_value")` on FINAL and during SHOOTOUT;
`hidden_element_prefixes = ("game_clock_",)`. Pregame/halftime screens reuse the football **event** registry unchanged
(`clocks.event.*`), so `screenForLifecycle` works as-is.

### 5.2 Default soccer layout — "Soccer Grid" (from Scoreboard Grid, same palette and fonts)

| widget | x | y | w | h | font | notes |
|---|---|---|---|---|---|---|
| home_name / away_name | 0.04 / 0.68 | 0.09 | 0.28 | 0.11 | 0.07 | bahnschrift_condensed 700, uppercase, `fit_text` |
| home_score / away_score | 0.04 / 0.68 | 0.225 | 0.28 | 0.36 | 0.30 | varsity 700 `#F2F2F2`, `fit_text` |
| game_clock_value | 0.35 | 0.09 | 0.30 | 0.32 | 0.22 | varsity `#F5AE08`, `fit_text` |
| period | 0.35 | 0.45 | 0.30 | 0.14 | 0.09 | varsity `#F2F2F2`, `fit_text` |
| status_message / status_clock | 0.04 / 0.195 | 0.045 | 0.15 / 0.08 | 0.035 | 0.016 | amber |
| home_shots, home_saves (hidden) | 0.045, 0.185 | 0.625 | 0.13 | 0.09 | 0.046 | |
| home_corners, home_fouls (hidden) | 0.045, 0.185 | 0.72 | 0.13 | 0.09 | 0.046 | |
| home_yellow, home_red (hidden) | 0.045, 0.185 | 0.815 | 0.13 | 0.075 | 0.04 | yellow `#FFD500`, red `#FF4B4B` text |
| away_* (hidden) | mirrored: x = 1 − (x + w) | same | | | | |
| shootout_home / shootout_away (hidden) | 0.35 | 0.62 / 0.73 | 0.30 | 0.10 | 0.045 | dots |

Elements: Grid's header rules/tabs, `title` text `HIGH SCHOOL SOCCER`, blue/red team panels with silver banners
(x 0.025/0.665, y 0.085, w 0.31, h 0.635, chamfered), a gold-framed period cell instead of the play-clock panel
(`game_clock_panel`? no — named `period_panel`), and a bottom stat bar only when stat widgets are turned on
(elements are static; the default ships the four-cell bar hidden = not present). All always-visible pairs are disjoint
(computed in `design_draft.md` §4.2). Presets offered in the soccer editor: **Soccer Grid** (default), **Broadcast bar**
(soccer widgets in football's bar geometry), **Classic**. Event screens: Grid-style KICKOFF IN / UNTIL SECOND HALF with
`HALFTIME`/`WARMUP` phase and `Warmup follows: 3:00`; Broadcast Welcome remains a selectable preset with the ticker
copy neutral (`WELCOME TO TIGER STADIUM`, `SCIENCE · WISDOM · PEACE`).

```
┌ Soccer Grid (visible-by-default set) ─────────────────────────────────────┐
│ [INJURY] [0:00]                       HIGH SCHOOL SOCCER                   │
│ ┌ EAGLES ───────┐        40:00            ┌ TIGERS ───────┐                │
│ │               │       (amber)           │               │                │
│ │      1        │      1ST HALF           │      0        │                │
│ └───────────────┘                         └───────────────┘                │
└────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Editor

`views/layout/*` unchanged. `WindowHost.open_layout_editor` hands the active application's `PresentationLayouts`
(soccer's carries `layout_module=soccer_layout`, `paths=<root>/soccer`); the screen descriptor for `game` has kind
`soccer`, so `Board.build(root, 'soccer')` draws the soccer registry. A soccer session never sees football widgets or
writes `<root>/layouts.json` (test 5.4 in `test_plan.md`).

## 6. Soccer Field Assistant (`views/soccer_field_assistant/`, 1180×720, min 1024×600)

```
┌ FIELD ASSISTANT · SOCCER   REV 42   GAME 31:07 RUNNING · 1ST HALF   [Discard draft & reload] ┐
│  HOME — EAGLES                          AWAY — TIGERS                                        │
│  [  SHOT  ][  SAVE  ]                   [  SHOT  ][  SAVE  ]                                 │
│  [ CORNER ][  FOUL  ]                   [ CORNER ][  FOUL  ]                                 │
│  [ YELLOW ][  RED   ]                   [ YELLOW ][  RED   ]                                 │
│  Player # (optional)  [7][8][9]  [4][5][6]  [1][2][3]  [0][⌫][NO #]      # 9                 │
│  Scoreboard now: EAGLES 1 · TIGERS 0 · Shots 4–6 · Saves 2–3 · Corners 3–5 · Fouls 1–2 · Y 0–1│
│  ┌ SHOOTOUT (only in the SHOOTOUT period) ─────────────────────────────────────────────────┐ │
│  │ ROUND 3 · AWAY TO KICK   HOME ● ● ○   AWAY ● ○     [HOME MADE][HOME MISSED][AWAY MADE][AWAY MISSED] │
│  └───────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                        [ Cancel ]  [ CONFIRM → HOME SHOT #9 ]│
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Bridge `SoccerFieldAssistantBridge`: `get_snapshot`, `preview_assist(action)` (read-only: returns the Confirm label
  and the resulting value), `finalize_assist(action, expected_revision)` which submits exactly one ordinary command
  (`add_stat`, `add_card`, `shootout_kick`, `set_shootout_first_kicker`) tagged `source: "field-assistant"`. No
  method can send `add_goal`, `set_score`, or any clock command; the airlock refuses them by construction (test).
- Live sync: pushed the same complete operator view on the same `field_assistant` window slot; adopts every push,
  never disables Confirm because of a change elsewhere (PL-2 behaviour); a refused `STALE_REVISION` shows the toast and
  one more Confirm finishes.
- Owner choice E: GOAL stays operator-only in this pass (the prompt's rule); the shootout kick log is allowed because
  it never changes the score (only `finish_shootout`, an operator action, does).

## 7. GOAL cutscene

- `SOCCER_CUTSCENE_EVENTS = ("goal",)`; `build_program(play_id, event, pack, spectator_view, layout, board_layout, team)`:
  headline `GOAL`, subline the scoring team's **name from the live snapshot** upper-cased, `team` `home`/`away`;
  duration 7 s, no intro, outro 600 ms; theme adds `home_primary`/`away_primary` from the saved team identity (fallback
  navy/red) so the scene keys its colour to the scorer. Owner choice F: team-aware, a deliberate departure from
  football's Tigers-only rule (a visitor's goal must not read TIGERS).
- Scene `views/soccer_spectator/cutscenes/soccer.js` + `soccer.css`: registers `goal`; net-ripple sweep (forwards,
  one-shot), `GOAL` headline slam, team name via `textContent`, ember hold; `innerHTML` only from `GOAL_MARKUP`; no
  `http://`; colours from `--cs-*` custom properties; reduced-motion and late-join hold state. Same director/tick
  lock order: `trigger` reads the spectator view and layouts before taking its own lock.
- Pack folder `<root>/soccer/cutscenes/`, selection `<root>/soccer/cutscenes.json`, README written once.
- Trigger paths: automatic after an accepted `add_goal` (switch, default on), `1`/`2` keys, the soccer Cutscenes window
  buttons; `Shift+C` / CANCEL ends it early.

## 8. Setup drawer — `SoccerRules`

| Field | Label | Kind | Default | Range | Source |
|---|---|---|---|---|---|
| `half_seconds` | Half length | clock | 40:00 (JV: type 35:00) | 5:00–60:00 | NFHS 7-1 / NCHSAA §4.9.1(n) |
| `halftime_seconds` | Halftime countdown | clock | 10:00 | 1:00–60:00 | NFHS 7-1 |
| `warmup_seconds` | Warmup label at | clock | 3:00 | 0–halftime | football precedent |
| `pregame_seconds` | Pregame countdown | clock | 30:00 | 1:00–60:00 | football precedent |
| `overtime_periods` | Overtime periods | count | 2 | 0–2 | NCHSAA §4.9.1(m) (0 for non-conference / JV) |
| `overtime_seconds` | Overtime period length | clock | 10:00 | 1:00–20:00 | NCHSAA §4.9.1(m) |
| `golden_goal` | Golden goal ends overtime | toggle | off | | NCHSAA "not sudden victory" |
| `shootout_enabled` | Kicks from the mark after overtime | toggle | off (regular season) | | NCHSAA §4.9.1(m)(2) playoffs |
| `shootout_initial_kickers` | Kickers per team | count | 5 | 1–11 | NFHS procedure |
| `shootout_credit_goal` | Add one goal to the shootout winner | toggle | on | | NCHSAA §4.9.1(m)(2) |
| `mercy_differential` | Mercy-rule goal differential | count | 9 | 0 (off)–20 | NCHSAA §4.9.1(k) |
| `mercy_applies` | Mercy rule applies | choice | `halftime_and_second_half` | `halftime_and_second_half`, `any_time`, `off` | NCHSAA wording; OT excluded (AD #8) |
| `stop_clock_on_goal` | Stop the clock when a goal is recorded | toggle | on | | NFHS 7-4 (AD #1) |
| `clock_direction` | Game clock counts | choice | `down` | `down`, `up` (display transform only) | NFHS convention |
| `weather_seconds` | WEATHER countdown | seconds | 30:00 | 1–30:00 | NCHSAA lightning policy (30 min) |
| `late_sub_note` | (informational) "Stop the clock for a leading team's substitution in the last 5:00" | note | shown | | NFHS 7-4-3 (AD #2) |

`golden_goal` on: a goal in OT1/OT2 raises the period decision immediately (Final / Keep). Rules apply the next time a
period, a new game or a countdown loads, exactly as football's.

## 9. Test plan and football-regression plan

Full detail in `test_plan.md`. Summary of new files (all additive; no existing test edited):

- Unit: `test_soccer_state.py`, `test_soccer_commands.py`, `test_soccer_clock.py`, `test_soccer_rules.py`,
  `test_soccer_formatting.py`, `test_soccer_shootout.py` (table-driven kicks-from-the-mark matrix),
  `test_soccer_layout_schema.py`, `test_soccer_cutscene_schema.py`.
- Integration: `test_soccer_bridge.py`, `test_soccer_recovery.py` (per-sport isolation, both crashed in one root),
  `test_soccer_persistence_paths.py` (only `<root>/soccer/` written; football hashes unchanged), `test_soccer_full_game_rehearsal.py`
  (kickoff → goals → cards → halftime → 2nd → crash/resume → OT → shootout → end), `test_soccer_operator_ui.py`,
  `test_soccer_crowd_status_ui.py`, `test_soccer_layout_render.py` (JS/Python mirror), `test_soccer_cutscenes_window.py`,
  `test_soccer_field_assistant.py` + `_window.py`, `test_sport_picker_startup.py` (football path byte-identical view
  models with and without the picker), `test_soccer_packaging.py`, `test_soccer_hotkey_table.py` (F21/F22 only).
- Browser (Playwright/Edge): `soccer_keyboard.cjs`, `soccer_u001.cjs` (3 viewports × idle/armed/shootout/alert,
  24-char names, no scroll, buttons inside viewport, 44 px), `soccer_spectator.cjs` (glyph-in-box, all optional
  widgets on and off), `soccer_goal.cjs`, `soccer_editor.cjs` (registry isolation, saves to `soccer/layouts.json`).
- Real runtime: `.scratch/soccer-mode/realrun_football_regression.py` (Football chosen: operator window, crowd raise
  and clear, score and undo, board screenshot) and `.scratch/soccer-mode/realrun_soccer.py` (the whole game in section
  10 of `test_plan.md`, screenshots in `evidence/`).
- Regression gate at every phase (section 0 commands): suite 1353+new / 0 / 0 / 3, empty golden diff, hash check with
  only allowed files changed, no `M`/`D` under `tests/`, and the football real run green.

## 10. Phases and agent split

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | Sport picker, `SoccerApplication` skeleton, paths/persistence/recovery seams, `--sport` CLI | Football golden diff empty; picker → Football is byte-identical; soccer/ folder created only when Soccer is chosen |
| 2 | Soccer domain, service, snapshots, recovery, store, bridge view models; unit + integration + rehearsal tests | as above + soccer suites |
| 3 | Soccer operator page, keyboard, Setup drawer, prompts; U-001 measured at 3 viewports × 4 states | + Playwright U-001 screenshots |
| 4 | Soccer layout registry, board.js seam, Soccer Grid default, presets, event screens, editor wiring | + editor isolation test, board screenshots |
| 5 | GOAL cutscene: presentation/infrastructure/host modules, scene, window, keys, auto-trigger | + goal.cjs |
| 6 | Soccer Field Assistant window and bridge | + FA tests, real run with both windows |
| 7 | `docs/SOCCER.md`, roadmap/architecture/UX updates, package rebuild and ZIP refresh | build verify, `--check` |

Implementation agents (≤ 5, file-owned, hard-coding the names in this spec): A domain+application (phase 2 modules and
their unit/integration tests); B host+startup+paths (phase 1 seams, `SoccerApplication`, `SoccerBridge`, picker);
C operator page + keyboard + FA page (phases 3, 6 views and source-contract tests); D presentation (layout registry,
board.js seam, presets, cutscene modules and scene, phase 4–5 tests); E docs/packaging (phase 7). Integration,
football regression checks, real-runtime harnesses, and every phase commit stay with me.

## 11. Open questions (owner) — each with the default I will take if unanswered

| # | Question | Default |
|---|---|---|
| A | Remember the last sport and pre-focus it on the picker (never auto-choose)? | Yes |
| B | Separate display/motion preferences for soccer (`soccer/config.json`) or share football's? | Separate |
| C | Second yellow: no auto-escalation; `2ND YELLOW → RED` shortcut in Corrections | Yes |
| D | No combined STOPPAGE button; STOP is the stoppage, crowd words INJURY/DELAY/WEATHER only | Yes |
| E | Field Assistant cannot record goals or touch the clock; it may log shootout kicks (score changes only via the operator's FINISH SHOOTOUT) | Yes |
| F | GOAL cutscene celebrates whichever team scored, name from the snapshot, team colours from the saved identity | Yes |
| G | Auto-play the GOAL cutscene on an accepted goal (switchable, `Shift+C` skips) | On |
| H | Score field range 0–99 on the soccer board (football is 0–199) | 0–99 |
| I | Shootout winner credited +1 goal by default (NCHSAA), configurable | On |
| J | Soccer's own `soccer_startup` recovery page rather than editing `views/startup/*` | Own page |
| K | Team names editable pregame only (as football) — soccer keeps the same rule | Same |

Open questions for the AD: section 1's list (1–8), each already defaulted in section 8.
