# Soccer mode: test plan

Companion to `spec.md` (architecture) and `rules_research.md` (rule sources). This
document is the only thing this agent owns; it is written to let an implementing
agent write soccer tests without re-deriving their shape. It assumes the seam
names in `CONTEXT_FOR_AGENTS.md`: `domain/soccer/`, `application/soccer_service.py`
(or similar), `host/soccer_bridge.py`, `views/soccer_operator/`,
`views/soccer_spectator/` (if the spectator page needs a soccer twin -- see open
question in section 1), `<root>/soccer/` data root. Where the spec settles on a
different exact module name, keep the test file names in the table below (they
mirror football's file-per-module convention) and re-point the `import` lines.

Every new soccer test file is additive. **No existing test file under `tests/`
may be edited.** The proof mechanism is spelled out in section 2.

---

## 1. New test files, mirrored one-to-one against football

| New soccer file | Mirrors | Assertions to write |
|---|---|---|
| `tests/unit/test_soccer_state.py` | `tests/unit/test_state.py` (frozen `GameState` validation) | Construct `SoccerState` (or whatever dataclass name the spec picks) directly, no I/O, no clock: (a) it is a frozen dataclass, `evolve(**changes)` returns a new instance with `revision` incremented by exactly 1 and every unspecified field unchanged; (b) validation rejects a negative score, a period label outside the configured set (`PRE`, `1st`, `HALF`, `2nd`, `OT1`, `OT2`, ..., `SHOOTOUT`, `FINAL` -- exact set from `rules_research.md`), a negative stat (shots/saves/corners/fouls per team), a yellow/red card count going negative, and a `game_status` outside the soccer `GAME_STATUS_LABELS` tuple (mirror `state.py:414`'s pattern) or a status with a countdown value that is not one of the configured presets; (c) the shootout tally is an ordered, immutable sequence of kick records (`team`, `made: bool`, `round`, optional `player_number`) and constructing one out of round order (round 2 kick before any round 1 kick for that team) is rejected -- decide in the spec whether the dataclass itself enforces order or the command layer does, and test at whichever layer owns it; (d) a `SoccerState` is JSON round-trippable through whatever `to_dict`/snapshot helper the spec defines (this pins the contract `application/soccer_snapshots.py` will rely on, see `test_soccer_persistence_paths.py` below); (e) `GAME_STATUS_LABELS`-equivalent constant for soccer is exported and does not import or alias football's tuple (proves the seam is additive, not a shared mutable global) -- `assertIsNot` the two tuple objects and diff their contents to prove soccer's has at least the injury/delay/weather words `rules_research.md` recommends. |
| `tests/unit/test_soccer_commands.py` | `tests/unit/test_commands.py` | One test per soccer command's happy path and its rejections, mirroring football's per-command test-class style: `set_team_name`, `add_goal` (armed, two-step, undoable -- assert it is a member of the soccer `UNDOABLE_COMMANDS` frozenset, distinct object from football's, per `commands.py:149`), `correct_score`, stat nudges (`nudge_shots`, `nudge_saves`, `nudge_corners`, `nudge_fouls` or whatever verb the spec settles on -- one +1/-1 test each, clamped at 0, never negative), `add_card` (`team`, `colour` in `{yellow, red}`, optional `player_number`; a second yellow for the same optional player number does not auto-escalate to red unless the spec says NCHSAA's second-yellow rule is implemented as a command-level rule -- if it's not automated in phase 1, assert it explicitly is *not* auto-escalated, so a later change is a deliberate diff against this test), shootout commands (`shootout_record_kick` with `team`/`made`, `shootout_correct_kick` reversing the last kick for a team without touching the other team's list, `shootout_finish` only accepted once a winner is mathematically decided -- test the exact one you can't-yet-win / can't-yet-lose boundary case from 5 kicks each, and the sudden-death continuation), `set_period` (mirrors `set_quarter`, same `confirmed` two-step for any period change that discards remaining time), clock commands re-used or soccer-specific (see `test_soccer_clock.py`), `new_game`/`end_game` (Game drawer only, same danger/confirm shape as football). For each command, assert membership in exactly one of the soccer `UNDOABLE_COMMANDS` / `NON_UNDOABLE_COMMANDS` frozensets (crowd-status-equivalent commands in neither, per `CONTEXT_FOR_AGENTS.md`), and that `_ALLOWED_ARGUMENTS`-equivalent validation in the soccer bridge rejects an unknown argument name the same way football's does (copy `test_bridge.py`'s pattern for that one assertion if football has it separately). |
| `tests/unit/test_soccer_clock.py` | `tests/unit/test_game_clock.py`, `tests/unit/test_play_clock.py`, `tests/unit/test_status_clock.py` | Soccer has one authoritative clock (no play clock) so this file covers only the game clock's soccer-specific behaviour: direction (count down or up -- per whatever `rules_research.md` concludes; if it's the NFHS-typical stopped/running countdown, mirror `test_game_clock.py` outright; if soccer's stadium clock counts *up* per the research, add a `direction` field to the clock or a soccer-only clock class and test that elapsed time accumulates rather than being subtracted, still off the same monotonic-deadline math so a paused clock never drifts), `maximum_seconds` per period label from `SoccerRules.period_seconds(label)` (half length, overtime period length, no maximum during `SHOOTOUT` since the shootout has no clock), start/stop/correct/reset parity with football's engine (same rounding-up-to-whole-seconds `format_game_clock` reuse -- confirm in the spec whether soccer reuses `domain/formatting.py`'s function verbatim or needs a count-up variant, and test whichever is chosen), and the status/crowd countdown reusing `StatusCountdown` unmodified (import the football class directly and prove soccer's crowd bar commands drive the same engine with soccer's own preset seconds, e.g. an injury assessment window if research finds one). |
| `tests/unit/test_soccer_rules.py` | `tests/unit/test_game_rules.py` | `SoccerRules` frozen dataclass: every field `rules_research.md` lists (half length varsity/JV, halftime length, overtime period count and length, golden-goal on/off per competition level, shootout format, mercy-rule goal differential and when it applies, whether a clock operator/on-field official controls stoppages -- store as a note field or omit per spec), `RULE_FIELDS`-equivalent tuple drives the Setup drawer the same way `RULE_FIELDS` does for football (one test enumerating it and asserting every field name it names is also a `SoccerRules` attribute, mirroring however `test_game_rules.py` proves that symmetry for football), `from_payload` ignoring unknown keys and naming the refused rule by field name (copy football's exact error-shape test), `period_seconds(label)` returning the half length for `1st`/`2nd`, halftime length for `HALF`, the configured overtime length for `OT1`/`OT2`/... (test each), and `None`/an explicit "no clock" sentinel for `SHOOTOUT`; defaults documented and cited (the numbers must match `rules_research.md`'s primary-source figures, not a placeholder -- assert against the literal values, e.g. `40 * 60` for a varsity half if that is what the research settles on, so a later accidental edit to the constant fails this test); `set_rules` (or `save_rules`) is not retroactive -- a change mid-half does not alter the currently loaded clock length until the next period load, mirroring football's identical rule; New Game uses the rules in force at the time, same as football. |
| `tests/unit/test_soccer_formatting.py` | `tests/unit/test_formatting.py` | Pure string-formatting helpers unique to soccer: score/period/clock display strings if soccer needs any that differ from football's reused `domain/formatting.py` functions (e.g. a shootout running-tally string like `"3-2"` or a made/missed glyph string per kick), stat display strings (shots/saves/corners as plain integers, no comma grouping needed but test the boundary of a 2-digit stat), and the card-count display (e.g. `"2Y"` / `"1R"` or however the spec renders it) -- assert Python produces the exact string the JS will render verbatim (per the "Python formats, JS only renders" rule), and that every formatter is a pure function of its inputs with no wall-clock or monotonic read. |
| `tests/unit/test_soccer_shootout.py` | (new football has no shootout; nearest analogue is the whole `test_field_assistant.py` FA matrix style: an exhaustive scenario table) | A dedicated matrix file because the shootout state machine is the one genuinely new piece of game logic: (1) round-by-round alternation, home kicks first only if research says visitors call heads/tails and the coin toss result is recorded somewhere -- if the coin toss is operator-entered, test that entry command too; (2) the "mathematically decided" cutoff after each of the 5 base rounds (e.g. 3-0 after 3 kicks each ends it at kick 4 of 10, not kick 10) computed generically, not hard-coded per round, and a table-driven test across every made/missed combination from 5 kicks with a decided-early case, a full-5-and-tied case, and a sudden-death case; (3) sudden-death pairs continue by round, ends the instant one side is ahead after a completed pair, and never lets an odd (incomplete) pair decide it; (4) a correction to an earlier kick recomputes whether the shootout is still open (e.g. correcting a made kick to missed reopens a shootout the state machine had called); (5) the shootout tally survives Undo like any other undoable command, restoring exactly the popped kick and no other; (6) a kick recorded with a player number renders in history with that number if the spec's history-label design says so, and works identically when the number is omitted. |
| `tests/integration/test_soccer_bridge.py` | `tests/integration/test_bridge.py` | `SoccerBridge.command(name, args, expected_revision)` airlock: unknown command name rejected, unknown argument name rejected (`_ALLOWED_ARGUMENTS`-equivalent), stale revision rejected with `STALE_REVISION` (same shape as football's), `operator_view_model()`/`spectator_view_model()` produce every string pre-formatted (no raw numbers the JS would have to format), `CONFIRMATION_REQUIRED` round-trip for every command the spec marks as needing confirmation (period change discarding time, New/End Game), and that every accepted command writes exactly one history row with `result` in `("ACCEPTED", "REJECTED")`, a `state_revision`, `wall_clock`, and `app_version`, in the **soccer** database, never in the football one (see `test_soccer_persistence_paths.py` for the stronger cross-file proof). Also: host actions (rules/save_rules, teams, displays, cutscenes) advance no revision, submit no command, write no history row -- same three-way assertion `test_game_rules_bridge.py`/`test_team_bridge.py` make for football, copied verbatim in shape. |
| `tests/integration/test_soccer_recovery.py` | `tests/integration/test_recovery.py` | Same P-004/P-005/P-006 matrix as football's file, run against soccer's own `GameStore`/database, **plus** the isolation guarantee that is soccer-specific and does not exist in football's file at all: (a) a crashed **football** game on disk must never be offered, loaded, or overwritten when `inspect_recovery` is called against the **soccer** paths, and vice versa -- construct both a football and a soccer game in the same temp data root (football under `<root>/`, soccer under `<root>/soccer/`), crash both, then call each sport's `inspect_recovery` and assert it only ever sees its own files (`report.state.home_name` etc. never leaks the other sport's team names) and that `report.choices`/`can_resume` for each sport is computed purely from that sport's own primary/backup files; (b) corrupting the football database and calling soccer's `inspect_recovery` produces a clean "nothing to recover" (or "new game only") result, not an `UNRECOVERABLE`/`BACKUP` result borrowed from football's corruption; (c) resuming soccer never touches football's lock file or vice versa (two `ScoreboardPaths`-equivalent objects, two separate `scoreboard.lock`s, and a test that acquiring soccer's instance lock does not block acquiring football's in the same process); (d) the application-upgrade recovery case (`ApplicationUpgradeRecoveryTests` in football's file) repeated once for soccer's own `app_version` stamping, to prove the seam that reads `app_version` from the snapshot is shared code exercised correctly for both sports rather than a football-only path. |
| `tests/integration/test_soccer_persistence_paths.py` | (new; the closest football analogue is the "never touch X" boundary assertions scattered through `test_layout_persistence.py`, `test_team_library.py`, `test_cutscene_packs.py`) | The disk-layout contract from `CONTEXT_FOR_AGENTS.md`: (a) starting a soccer game writes `scoreboard.db`, `scoreboard.backup.db`, `config.json`, `layouts.json`, `cutscenes.json`, and a `cutscenes/` folder **under `<root>/soccer/`**, never at `<root>/` directly -- enumerate `<root>`'s immediate children before and after and assert the only new top-level entry is the `soccer/` directory (or whatever files `teams.json`-sharing requires at the top level, per the spec); (b) `teams.json` is read from the shared top-level path by both sports and its schema/hash is unaffected by a soccer-only write session (start a soccer game, save/delete a soccer team preset, then hash `teams.json` and diff against a hash taken before any soccer code ran with the same team data -- prove soccer's team library calls are the *same* `infrastructure/teams.py` functions football uses, not a soccer-only reimplementation that could drift the schema); (c) with **no soccer game ever started**, every existing football file's SHA-256 is identical to the frozen-file baseline from `.scratch/soccer-mode/baseline/` (this is the persistence half of the frozen-file-hash proof in section 2; the golden-run diff is the behavioural half); (d) deleting or corrupting everything under `<root>/soccer/` never raises out of any football code path and never touches a single byte under `<root>/` outside `soccer/` (write garbage into `<root>/soccer/scoreboard.db`, then run a full football game through the real bridge in the same temp root and assert the football files' hashes are unaffected). |
| `tests/integration/test_soccer_full_game_rehearsal.py` | `tests/integration/test_full_game_rehearsal.py` | One whole fake-time soccer game through the real soccer bridge, same structure as football's file (`send`/`advance`/helper methods), but the script is: kickoff (period `1st` loaded, clock direction per research), a run of simulated play with periodic stat nudges (shots/saves/corners/fouls) on both teams, at least one card per team (a yellow that does *not* escalate, plus a red), two goals (armed `add_goal` then applied, one per team, mirroring `score()`'s two-step confirm helper), an operator mis-click and its Undo restoring the exact prior score, halftime (period `HALF`) loaded from the game clock the same way football's is, second half (`2nd`), a crash-and-resume partway through the second half using the same `store.close()` pattern as football's `crash_and_resume()` (no shutdown record), overtime (`OT1`, possibly `OT2` if the research's overtime format needs two periods to test the "keep going" branch), a shootout to a decided winner exercising `test_soccer_shootout.py`'s state machine end-to-end through the bridge rather than the pure domain layer, a scoreboard correction after the shootout, then `end_game`. Assertions mirror football's `assert_board_matches_the_field`/`assert_history_explains_the_game`: final scores match the tracked expected totals, lifecycle is `FINAL`, every clock is stopped and within its configured bounds, the shootout tally in the final view model matches the kick sequence driven, the history's sequence numbers are gap-free and monotonic across the simulated crash, and every soccer-specific command name appears at least once in the history (list them explicitly, mirroring football's `for required in (...)` block). |
| `tests/integration/test_soccer_operator_ui.py` | `tests/integration/test_operator_refresh_ui.py`, `tests/integration/test_display_drawer_contract.py` | Source-contract tests (no browser) against `views/soccer_operator/index.html`/`.js`/`.css`/`keyboard.js`: two-step arm-then-apply for `add_goal` mirroring football's `.score-controls`/`SCORING`/`ARM_SECONDS` tests exactly (same hidden-not-display toggle, same fixed-height block, same window-blur/Escape/drawer-open disarm triggers); the shootout panel appears **only** inside a `#shootout-panel`-equivalent block gated on `period === 'SHOOTOUT'` in the render function (grep the render function's source for the gate, do not just check markup presence, since the September 14 principle is "nothing floating when unused" the same way the crowd bar's countdown is gated); the crowd bar reuses football's exact show/hide rules (CLEAR yellow only while raised, START/STOP only with a countdown) -- assert the soccer CSS carries the same three colour rules `test_crowd_status_ui.py` pins for football (`#ffc845`/`#2e9e6a`/`#c43d3d,` or the soccer-specific hex if the spec deliberately changes them, in which case assert the *soccer* value instead and note the deviation); the Game drawer holds exactly the soccer lifecycle commands (`end_game`, `game_clock_reset`/-equivalent, `new_game`) each marked `class="danger"`; Undo has `data-confirm="local"` on both the strip and drawer controls and the dialog quotes `model.last_action.label` the same way football's does; the tool bar sends no `data-command` at all; the file's own header names its own "kinds of ephemeral view state" the way football's does (arm timers, drawer-open state, dismissed-dialog tokens, etc. -- whatever the soccer page actually has) so a future editor is told the same discipline was followed; and the U-001 visual fit is explicitly *not* attempted here (note that in the file's docstring, exactly as `test_crowd_status_ui.py`'s docstring does), deferring to section 4's Playwright plan. |
| `tests/integration/test_soccer_crowd_status_ui.py` | `tests/integration/test_crowd_status_ui.py` | Same structure as football's file, against the soccer operator source, for soccer's own crowd-status word list (from `rules_research.md`, expected candidates: `INJURY`, `DELAY`, `WEATHER`, and whatever else the research turns up -- do not hard-code football's `FLAG`/`TIMEOUT`/`INJURY`/`DELAY` set, import soccer's own constant and iterate it): every label has an always-visible button outside every drawer, `clear_game_status`/`status_clock_start`/`status_clock_stop`-equivalent commands are reachable by mouse with no confirmation, any soccer status with a countdown (if research finds one, e.g. an injury-assessment clock) starts it in one press the same way football's `TIMEOUT` does, the crowd row sends only its own four-or-so commands and no scoring/card command ever appears in it, the row renders only Python-sent values (`status.display`, `status.clock_display`), and the row is a fixed (`auto`) grid row so the board is still the only flexing row -- assert the soccer page's `body { grid-template-rows: ... }` rule names an explicit row for the crowd bar just as football's does (the exact row list will differ if soccer's layout has no separate quarter-bar-equivalent row; write the assertion against whatever the spec's wireframe says, not football's literal string). |
| `tests/unit/test_soccer_layout_schema.py` | `tests/unit/test_layout_schema.py` | Pure schema tests for the soccer widget registry additions to `presentation/layout.py` (or a soccer-specific registry module if the spec keeps it fully separate -- follow whichever the architecture section of `spec.md` picks): every soccer widget id (`home_name`, `away_name`, `home_score`, `away_score`, `game_clock_value`, `game_clock_label`, `period`, `home_shots`, `away_shots`, `home_saves`, `away_saves`, `home_corners`, `away_corners`, `home_fouls`, `away_fouls`, `home_yellow_cards`, `away_yellow_cards`, `home_red_cards`, `away_red_cards`, `shootout_tally`, `status_message`, `status_clock`) exists in a `SOCCER_WIDGET_IDS`-equivalent tuple with matching `WIDGET_FIELDS`/`WIDGET_TEXTS` entries; the stat and card widgets are listed in a soccer `OPTIONAL_WIDGET_IDS`-equivalent set and are hidden by default in the soccer default layout (assert the default layout's `visible` flag for each of them is `False` while the core widgets default `True`); the coordinate model, safe-area policy, and strict-validate-with-fallback rule are all reused unmodified from football's (construct a soccer document with an out-of-safe-area widget and assert the same validation error shape football's schema produces, proving no soccer-only relaxation crept in); `SCREEN_IDS`-equivalent for soccer covers `game`/`pregame`/`halftime` exactly as football's does (or fewer if the spec drops one); and — critically — the football `WIDGET_IDS`/`WIDGET_REGISTRIES` constants are unchanged objects (`assertIs` against a value captured before soccer's module is imported, to prove the soccer registry is additive, not mutating a shared dict in place). |
| `tests/integration/test_soccer_layout_render.py` | `tests/integration/test_spectator_layout_render.py` | The JS/Python registry mirror test for soccer's board renderer, in the same style as football's file: lift the soccer widget-id/field/text literals out of whichever `.js` file hosts them (`views/shared/board.js` if the registry is added there behind a `kind: 'soccer'` the same way `REGISTRIES = {game, event}` works today, or a new `views/soccer_shared/board.js` if the spec keeps it fully separate — pin whichever the architecture section says) and diff them against the Python soccer registry, id for id, field for field; assert the pure-Python renderer contract (no control markup, no `data-command`/`api.command`/`CommandType` token) holds for the soccer board exactly as `test_layout_editor_contract.py` proves for football's editor; and if the spec's decision is "soccer reuses `views/spectator/spectator.js` with a `kind` switch" rather than a separate `views/soccer_spectator/`, add the specific assertion that football's `#game-board`/`#event-board` construction path is untouched when `kind !== 'soccer'` (grep the source for the branch and assert it defaults to football's existing behavior with no `kind` argument, so an old caller cannot regress). |
| `tests/unit/test_soccer_cutscene_schema.py` | `tests/unit/test_cutscene_schema.py` | Pure schema tests for the soccer cutscene event list: a `SOCCER_CUTSCENE_EVENTS`-equivalent tuple containing at minimum `goal` (and any others the spec adds, e.g. `card` or `shootout_winner` — only test what the spec actually commits to; do not invent events the implementer didn't build); `validate_manifest`/`builtin_pack`/`normalize_pack`/`build_program` reused from `presentation/cutscenes.py` unmodified except for an additive soccer event table (assert football's `CUTSCENE_EVENTS` tuple is unchanged — same `assertIs`-on-a-captured-reference pattern as the layout test); the soccer `build_program` for `goal` takes a `team` argument if soccer (unlike football's fixed home-branding Tigers scheme) needs to show which side scored — decide explicitly in the spec whether soccer cutscenes are also home-only-branded or team-aware, and test whichever was chosen, quoting the spec's decision in the test's docstring; per-event intro defaults, `EVENT_SUBLINE`-equivalent wording, and `CUTSCENE_STYLE_KEYS` colour-copying from the active soccer layout (Bug 1's fix, mirrored) all get one test each; and a scene-file registry mirror test scanning every `*.js` under the soccer cutscene scene directory (e.g. `views/soccer_spectator/cutscenes/`, per `CONTEXT_FOR_AGENTS.md`'s note that a soccer scene file "must live elsewhere") asserting it registers exactly the soccer event ids and that football's five-id assertion in `test_cutscene_schema.py` is untouched (i.e. do not add the soccer scene directory to football's scan, and add a new scan of the soccer directory here instead). |
| `tests/integration/test_soccer_cutscenes_window.py` | `tests/integration/test_cutscenes_window.py`, `tests/integration/test_cutscene_director.py`, `tests/integration/test_cutscene_bridge.py` | Host wiring for the soccer `CutsceneDirector`/`CutscenesBridge` instance (a second instance of the same classes football uses, constructed with soccer's own `read_board_layout` and pack directory, if the architecture keeps the director class shared — the likely and simplest choice per `CONTEXT_FOR_AGENTS.md`'s "additive seam, football as default path" guidance): triggering the soccer `goal` event publishes one program of the right shape to the soccer spectator window only, never to football's operator/spectator if both happen to be open in the same test process (construct both a football and a soccer director sharing no state and assert triggering one never calls the other's `publish`/`open_window`); the operator bridge's `cutscenes.available`/`.playing` badge behaves identically to football's (idle `None`, triggered event copied verbatim); an invalid event is rejected without changing the badge; a raising `publish`/`end` is contained and logged the same way; and the scene mounts against soccer's Scoreboard-Grid-derived default layout colours per the Bug-1-style fix, proved the same way `test_cutscenes_window.py`'s final test proves it for football (trigger through the real, fully-wired soccer application, not a fake). |
| `tests/unit/test_soccer_field_assistant_window.py` | `tests/integration/test_field_assistant_window.py`, `tests/unit/test_field_assistant.py` | Two halves, mirroring football's split between a pure-rules unit file and a host-wiring integration file — name this file to match whichever the spec's `views/soccer_field_assistant/` design lands on, and split it into `test_soccer_field_assistant.py` (pure rules: shot/save/corner/foul/card logging with an optional player number, a preview/confirm step before commit, and the explicit guarantee from the prompt that it **cannot** change the score or the game clock unless the approved spec says otherwise — assert calling any score- or clock-mutating method on the soccer Field Assistant bridge raises or is rejected, the same defensive test football's FA-suite does not need since football's Assistant already has score/clock powers by design) and `test_soccer_field_assistant_window.py` (host wiring: pywebview-shaped fakes per `test_cutscenes_window.py`'s style, opening the window is deliberate and sized independently of football's Field Assistant window, its `js_api` is a live soccer bridge, reopening replaces and destroys the previous window, closing forgets it, live-sync push path re-uses football's `WindowPublisher`, and finalizing a shot/save/card writes exactly one history row per finalize the same way `test_field_assistant_rehearsal.py` proves for football's composite commands). |
| `tests/integration/test_sport_picker_startup.py` | `tests/integration/test_startup.py`, `tests/integration/test_host_application.py` | The sport-picker seam in `host/app.py`/`views/startup/`: the startup page offers Football or Soccer before Resume/New (mirror `test_startup.py`'s `StartupSurfaceTests` structure, adding a `sport` argument or a distinct `StartupBridge` method per sport, per whatever the spec's architecture section names); choosing Football produces byte-identical behaviour to today's `host.run(startup_choice="new")` path with no sport argument at all (parametrize football's own `test_host_application.py` `StartupTests`/`RecoveryChoiceTests` classes to run once with the sport-picker code path active and once through the pre-existing entry point, asserting the two produce identical view-model JSON — this is the automated half of the golden-run proof, narrower but faster than the full script in section 2); choosing Soccer builds a `ScoreboardApplication`-equivalent pointed at `<root>/soccer/` (or however the spec structures the soccer host object) with its own recovery/lock/service, independent of any concurrently-open football application object in the same process (construct both, crash and resume each independently, assert no cross-talk exactly as `test_soccer_recovery.py` does at the persistence layer, but here at the host-application layer including the instance lock); and if "the last choice is remembered" is a decided feature (open question — see spec), test that a stored preference is offered as a default but never auto-selected without an explicit click/keypress, mirroring football's "nothing auto-resumes" P-005 discipline in `ExplicitChoiceTests`. |
| `tests/integration/test_soccer_packaging.py` | `tests/integration/test_packaging.py` | Whatever football's packaging test currently proves (read it before writing this one — not in this agent's read list, so the implementing agent should skim it first), repeated for the soccer views/assets: every soccer page asset is bundled and referenced by a `file:///` URL with no remote reference (mirror `test_host_application.py`'s `BundledAssetTests`, extended with soccer's operator/spectator/field-assistant HTML), the packaged build's manifest (per `docs/PACKAGING.md`) includes every new soccer file under `src/scoreboard/views/soccer_*` and `src/scoreboard/domain/soccer/` (or wherever the spec puts them), and the rebuilt `dist\Scoreboard-0.1.0.zip` (phase 7) still contains every football file unchanged (hash the football entries inside the zip against the frozen-file baseline). |
| `tests/ui/soccer_keyboard.cjs` (+ a `tests/ui/test_soccer_keyboard_browser.py` runner mirroring `test_keyboard_browser.py`) | `tests/ui/keyboard.cjs` | Same shape as football's keyboard harness: spin up `tests/ui/soccer_bridge_server.py` (see section 4) instead of `tests/ui/bridge_server.py`, stub `window.pywebview.api` the same way, drive the soccer keyboard bindings the spec proposes (own mapping table, not football's — do not assume Z/X/C/V map to goal points the way they map to touchdown points; a goal is a single point value so the arm-then-apply pattern likely needs just one key per team plus Undo, cards, and period forward/back — write the map array once the spec's keyboard section is approved), assert every command dispatched matches `[commandName, argsWithSource, revision]` the same way football's `map` array does, prove editable fields swallow every shortcut (copy the loop verbatim against the soccer page's own input/textarea/select/contenteditable elements), prove the CONFIRMATION_REQUIRED round-trip for period changes and Undo the same way football's does, and prove the live-controls-fit check at the three viewports (1093×614, 1180×720, 1366×768 — note football's harness only tries 1366×768 and 1093×614; add 1180×720 explicitly per this task's U-001 list) for both idle and armed states, plus a `SHOOTOUT`-period state (push a view model with `period: 'SHOOTOUT'` and assert the shootout panel's buttons also fit, since that panel does not exist in football's harness at all). |
| `tests/ui/soccer_spectator.cjs` (+ `tests/ui/test_soccer_spectator_browser.py`) | `tests/ui/spectator.cjs` | Same `measureWidgets`-style glyph-in-box checks (see section 5), against the soccer spectator page/registry, across the same viewport matrix football's `spectator.cjs` uses (1920×1080, 1366×768, 1280×720, 640×360, 390×844), with 24-character team names (per the prompt's explicit ask) and every stat/card widget both hidden (default layout) and shown (a layout that turns every optional widget on, to prove they *can* fit when enabled even though they are off by default). |
| `tests/ui/soccer_goal.cjs` (+ `tests/ui/test_soccer_goal_browser.py`) | `tests/ui/turnover.cjs`/`tests/ui/touchdown.cjs` (five-second scene harnesses) | The GOAL cutscene exercised the same way football's per-scene harnesses exercise `turnover`/`touchdown`: three viewport sizes, text clearance for the scoring team's name (including the 24-character case), live clock pushes during the scene, cancellation, replacement by a second trigger, natural end restoring the operator's layout, late join (a client that starts watching mid-scene), reduced motion, and canvas-failure fallback. Use `SCOREBOARD_CAPTURE_DIR` for optional screenshots exactly as the football scene harnesses do. |

### Files this table does not add, and why

- No `tests/unit/test_soccer_hotkeys.py`: the prompt's decision 5 is that the button box gets **no soccer remap** and `host/hotkeys.py`'s `HOTKEY_TABLE` is frozen (a football-only file per `CONTEXT_FOR_AGENTS.md`). The one soccer-relevant assertion — "F21/F22 still start/stop the game clock in soccer mode, every other key does nothing" — belongs in `test_soccer_full_game_rehearsal.py` or `test_sport_picker_startup.py` as a single behavioural check against the real button-box hook wired to a soccer bridge, not a new hotkeys unit file, since the table itself does not change.
- No soccer twin of `test_publish_off_lock.py`/`test_window_publisher.py`: those prove generic infrastructure (`WindowPublisher`, the command-lock/publish-lock ordering) that soccer reuses unmodified. Add one assertion inside `test_soccer_cutscenes_window.py` (or a short new `test_soccer_window_publisher.py` only if the implementer finds soccer needs a second `WindowPublisher` instance with distinguishable behaviour) rather than duplicating the whole suite.
- No soccer twin of `test_display_selection.py`/`test_display_close.py`/`test_display_drawer_contract.py`: display selection and closing are sport-agnostic host actions. Confirm this assumption explicitly with **one** integration test (fold it into `test_sport_picker_startup.py`) that closes/reopens the spectator display while a soccer game is active and asserts the same health/detail sentences football gets, then rely on the existing football tests for the rest.

---

## 2. Football-regression plan at every phase boundary

Run this exact sequence after each of the seven implementation phases, before committing that phase.

### 2.1 Full suite at 1353/0/0/3, no existing test edited

```bash
export SCOREBOARD_DATA_DIR="$(pwd)/.scratch/soccer-mode/scratch-data"   # never the owner's real data dir
export PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -m unittest discover -s tests -v 2>&1 | tee .scratch/soccer-mode/evidence/phaseN-suite.txt
```

Expect the tail line to read `Ran <1353 + new soccer count> tests ... OK (skipped=3)`. The **1353** football
tests must all still be present and passing; the only permitted growth is the new soccer files from section 1.

Proof that no existing test file was edited, exactly as `CONTEXT_FOR_AGENTS.md` prescribes:

```bash
git diff --name-status post-live-fixes -- tests/ | grep -v '^A'
```

This must print **nothing**. Any line starting with `M` (modified) or `D` (deleted) is a violation of the
"never edit an existing test" rule and blocks the phase commit. Run
`git diff --stat post-live-fixes -- tests/` alongside it for a human-readable summary to paste into the phase's
commit message body.

### 2.2 The golden-run diff (`.scratch/soccer-mode/football_golden/`)

The Step-0 baseline tooling (not owned by this document, but consumed by this plan) writes one script that
drives a whole football game through the real `ScoreboardApplication`/bridge and dumps, per step: the operator
view model JSON, the spectator view model JSON, and the history rows read back from `scoreboard.db`. At every
phase boundary:

```bash
./.venv/Scripts/python.exe .scratch/soccer-mode/football_golden/run.py \
    --out .scratch/soccer-mode/football_golden/phaseN.json
diff .scratch/soccer-mode/football_golden/baseline.json \
     .scratch/soccer-mode/football_golden/phaseN.json
```

The diff must be empty. If it is not, the phase introduced a football behavioural change and must not be
committed until the seam is fixed to be truly additive (per `CONTEXT_FOR_AGENTS.md`'s "football default path"
rule) or, if a shared seam genuinely had to move, the implementer stops and asks per the prompt's rules of
engagement — this plan does not authorize silently updating the golden baseline.

### 2.3 Frozen-file hashes

```bash
./.venv/Scripts/python.exe -c "
import hashlib, pathlib
files = pathlib.Path('.scratch/soccer-mode/baseline/frozen_files.txt').read_text().splitlines()
for f in files:
    print(hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest(), f)
" > .scratch/soccer-mode/baseline/phaseN_hashes.txt
diff .scratch/soccer-mode/baseline/hashes.txt .scratch/soccer-mode/baseline/phaseN_hashes.txt
```

The frozen list (from Step 0) must include at minimum: `domain/field_assistant.py`, everything under
`views/field_assistant/`, everything under `views/operator/`, `host/hotkeys.py`, and every football cutscene
scene file under `views/spectator/cutscenes/`. Any diff here is a hard stop, independent of whether the golden
run also caught it — the hash check catches whitespace-only or comment-only edits the behavioural golden run
might not exercise.

### 2.4 One real pywebview football run

Mirror `.scratch/post-live-fixes/realrun_pl3.py` exactly, but call it `.scratch/soccer-mode/realrun_football_regression.py`
(this agent does not write it — the implementing agent does, per this spec) with this script, run at every phase
boundary:

1. `ScoreboardApplication(paths, diagnostics=NullDiagnostics())` + `WindowHost(application)`, `threading.Timer(3.0, drive)`, `host.run(startup_choice="new")` (or, once the sport picker lands in phase 1, `host.run(startup_choice=None)` through the real Football/New path via `evaluate_js` clicks on the startup page — switch the harness over on the phase-1 boundary and note the switch in that phase's commit message).
2. `drive()` waits for `#home-arm` to exist (same `wait_for` helper as `realrun_pl3.py`), then:
   - opens the operator window and resizes it to a known CSS viewport (reuse `size_viewport`);
   - raises a crowd message (`click('#crowd-flag')`) and clears it (`click('#crowd-clear')`), checking `state().game_status` each way;
   - arms and scores a touchdown (`click('#home-arm')`, wait for the armed panel, click the `+6` control), then Undo with the confirm dialog (`click('#undo')`, `click('#confirm-accept')`), checking the score reverts;
   - captures one screenshot with `shot.capture_hwnd` proving the board renders the football layout (team names, score, clock) exactly as before;
   - sleeps ~0.5-1 s after every Python-side `bridge.command(...)` or state mutation before the next page click, per the page-revision race note in `CONTEXT_FOR_AGENTS.md`.
3. `main()` prints `PASS`/`FAIL` lines and a summary count in the same style as `realrun_pl3.py`'s `check`/`RESULTS` pattern; a non-zero exit fails the phase.

Run with `PYTHONIOENCODING=utf-8` and never against `SCOREBOARD_DATA_DIR` pointed at the owner's live folder — use a fresh `tempfile.TemporaryDirectory` exactly as `realrun_pl3.py` does.

---

## 3. Soccer real-runtime whole-game harness (`.scratch/soccer-mode/realrun_soccer.py`)

Structure this file exactly like `.scratch/post-live-fixes/realrun_pl3.py` /
`.scratch/control-ui-pass/realrun_ui_pass.py`: a `RESULTS` list, a `check(ok, label, detail)` helper, a
`wait_for(predicate, seconds, step)` poller, a `size_viewport` helper reused verbatim (import it from
`.scratch/post-live-fixes/realrun_pl3.py` or hoist it into a shared `.scratch/soccer-mode/_harness_common.py` this
agent does not own but should recommend in the spec), and a `drive(host)` function run from a
`threading.Timer(3.0, ...)` against a real `host.run(...)`.

### 3.1 The script of the whole game

1. **Launch and pick Soccer.** `host.run(startup_choice=None)` against the real startup page; `drive()` waits for the sport-picker controls, clicks Soccer, then New (not Resume, since this is a fresh temp dir).
2. **Choose teams.** Drive the Teams drawer the same way `realrun_ui_pass.py` seeds teams via `bridge.save_team(...)` + `set_team_name` — but do at least the *first* team choice through real page clicks (open the drawer, fill a name input, click apply) to prove the drawer's DOM contract works, then use direct bridge calls for the rest to keep runtime down, exactly as `realrun_ui_pass.py` mixes both styles.
3. **Kickoff.** Click the soccer clock Start; assert `state().period` (or equivalent) is `1st` and the clock is running, direction per whatever `test_soccer_clock.py` pinned.
4. **A goal with the cutscene.** Arm and apply a goal for the home team via the operator page; wait for `state().home_score` (or the soccer equivalent field name) to increment; assert the operator's cutscene badge shows the `goal` event playing (`api.get_snapshot()` or a DOM read of the badge text) and capture a screenshot of the spectator window mid-scene using `shot.capture_hwnd` on the spectator's hwnd (open it via whatever host method opens the practice/spectator window, mirroring `host.operator_window`/`open_test_window`).
5. **Stats and cards from both the operator page and the Field Assistant window.** From the operator page: click a shot/save/corner/foul nudge for each team and a yellow card for one team; assert `state()` reflects each. From the Field Assistant window: open it (`host.open_soccer_field_assistant()` or whatever the wiring test names it), log a corner and a red card through its controls, and assert the same `state()` object changed — proving both surfaces write through the one authoritative service.
6. **Halftime screen on the practice spectator window.** Advance the period to `HALF`; open (or reuse) the 640×360 practice spectator window; capture a screenshot; assert via `evaluate_js` that the halftime event screen (not the live board) is showing, by checking for a data attribute or widget the halftime screen uniquely carries (mirror however `test_event_screens_browser.py`/`event_screens.cjs` identify the halftime screen for football).
7. **Second half.** Advance to `2nd`; one more goal for the away team, applied and confirmed the normal way (no need to re-verify the cutscene, already covered in step 4).
8. **Overtime.** Force a tied score via a correction if the simulated goals didn't tie it, advance the period to `OT1` (and `OT2` if the research's format needs the second-period branch exercised), assert the clock loads the configured overtime length.
9. **Shootout to a winner.** Advance the period to `SHOOTOUT`; drive the shootout panel's made/missed buttons for both teams through a full 5-round-plus-sudden-death sequence via real page clicks (this is the one piece of new UI that most needs a real-runtime proof, since `test_soccer_shootout.py` only proves the domain logic); assert the panel shows a winner and no further kick buttons are clickable (or are disabled) once decided.
10. **Undo at several points.** At minimum: undo the last shootout kick correction and check the tally reverts; undo the away-team second-half goal and check the score and period_decision state revert together (mirroring `assert_board_matches_the_field`'s revision-forward invariant); undo a stat nudge.
11. **End Game.** Click through the Game drawer's End Game control with its confirm dialog; assert `lifecycle == 'FINAL'`.
12. **Relaunch and Resume after a simulated crash.** Two options, pick the first unless it proves impractical during implementation (record which was used and why in the harness's own docstring):
    - **Preferred: destroy-and-reconstruct in-process.** `operator_window.destroy()` the open windows, then — **without** calling `application.shutdown()` (a real shutdown records a clean `SHUTDOWN` checkpoint kind, which is not what a crash looks like; football's `crash_and_resume()` proves this exact distinction by calling `store.close()` directly instead of going through the service's shutdown path) — call `store.close()` on the soccer store directly (reach it via whatever attribute the soccer application exposes, mirroring `application.store` if that is football's pattern) to drop the write handle mid-session. Then construct a **fresh** `ScoreboardApplication`-equivalent object (or the soccer host object the spec's architecture names) on the **same** `paths`, in the **same process**, and call `inspect_recovery`/`resume()` on it exactly as `test_host_application.py`'s `RecoveryChoiceTests` does at the unit level, but here through the real `WindowHost.run(startup_choice=None)` path so the startup page's real Resume button is exercised, not just the Python API.
    - **Fallback if in-process reconstruction proves unworkable** (e.g. a native Win32 window handle or WebView2 environment cannot be safely torn down and rebuilt in one process without leaking): spawn the whole harness as a **child process** via `subprocess.Popen` pointed at the same temp `paths`, kill it with `proc.terminate()` (not a graceful shutdown) mid-game at the point step 12 begins, then launch a second child process pointed at the same `paths` and drive its startup page's Resume choice, reading its stdout for the same JSON snapshot protocol `tests/ui/bridge_server.py` uses over stdin/stdout so the parent script can still assert on state without a shared Python object.
13. Assert the resumed game shows the same score, period, cards, and shootout tally as just before the simulated crash (same staleness-bound checks as football's `test_a_restart_restores_the_game_with_every_clock_stopped`/`test_restored_clocks_hold_the_last_checkpointed_displayed_second`).

### 3.2 Checks recorded and evidence

Every `check(...)` call follows the `(bool, label, detail)` shape and the script prints a final
`N/M checks passed in the real pywebview runtime` line, matching `realrun_pl3.py`'s summary format exactly, so
this harness's output can be pasted into a phase commit message the same way.

Screenshots, one per numbered step above at minimum, saved to `.scratch/soccer-mode/evidence/` with a
`soccer-NN-<step-name>-<viewport>.png` naming convention (mirroring `realrun_pl3.py`'s `pl3-NN-*` and
`realrun_ui_pass.py`'s `ui-<width>-N-*` conventions): kickoff, goal-cutscene-mid-scene, stats-and-cards-operator,
stats-and-cards-field-assistant, halftime-spectator, shootout-panel-mid-sequence, shootout-decided, undo-dialog,
end-game-final-board, resume-after-crash.

---

## 4. U-001 fit plan (Playwright/Edge against the real bridge)

### 4.1 `tests/ui/soccer_bridge_server.py` (new twin of `tests/ui/bridge_server.py`)

Football's `bridge_server.py` hard-codes a football game: `bridge.command('new_game', ...)` +
`bridge.command('set_quarter', {'label': '1st', ...})` inside its `'reset'` operation, and its `ScoreboardApplication`
is unconditionally the football one. A soccer twin needs the equivalent seam, so:

```python
# tests/ui/soccer_bridge_server.py — same stdin/stdout JSON-line protocol,
# same tempfile.TemporaryDirectory isolation, same monotonic_clock=lambda: 1000.0,
# but:
#   - constructs whatever the soccer host/application object is named
#     (per spec.md's architecture section) instead of ScoreboardApplication
#   - its 'reset' operation calls the soccer new_game + set_period('1st')
#     commands instead of football's set_quarter
#   - its 'pregame' operation loads whatever soccer's pregame period label is
#   - a new 'shootout' operation seeds a state already in the SHOOTOUT period
#     with a partial kick tally, so soccer_keyboard.cjs/soccer bridge browser
#     tests can reach that state in one round trip instead of driving 90+
#     minutes of simulated clock through page clicks
```

Every other line of the protocol (`command`, `history`, default `snapshot`) is identical in shape to football's
file; copy it verbatim except for the sport-specific object construction and the `'reset'`/`'pregame'`/`'shootout'`
seed commands.

### 4.2 Viewports, states, and measurements

Run a Playwright script (`tests/ui/soccer_u001.cjs` + a `tests/ui/test_soccer_u001_browser.py` runner, in the
same two-file pattern as every other `tests/ui/*.cjs` harness) against `tests/ui/soccer_bridge_server.py`, at:

- **Viewports:** 1093×614, 1180×720, 1366×768 (all three named explicitly in the prompt's U-001 ask; note football's own `keyboard.cjs` only exercises two of these three today — do not narrow soccer's coverage to match, add the third).
- **States:** idle (fresh reset), armed (one team's goal panel armed, mirroring `keyboard.cjs`'s armed-panel loop), shootout (seeded via the `'shootout'` bridge-server operation above, with the shootout panel visible), alert showing (trigger a rejected command — e.g. attempt a nudge below zero — and assert the `#alert`-equivalent element is visible while measuring).
- **Team names:** a 24-character name on both sides for every state above (`"Twenty-Four Character Team A"` trimmed/adjusted to exactly 24 chars, and a second, different 24-character string for the away team so truncation bugs can't hide behind a repeated string).

For each of the 3 viewports × 4 states × (24-char names always on) combination, assert:

```js
document.documentElement.scrollHeight === document.documentElement.clientHeight  // no vertical scroll
document.documentElement.scrollWidth  === document.documentElement.clientWidth   // no horizontal scroll
// every visible button's bounding rect is fully inside the viewport, mirroring
// keyboard.cjs's `outside` computation at the end of its file:
Array.from(document.querySelectorAll('button:visible')).every(b => {
  const r = b.getBoundingClientRect();
  return r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 0.5 && r.bottom <= innerHeight + 0.5;
})
// every live-control button (everything outside .crowd-bar and .quarter-bar-equivalent,
// which football pins at 36px) is >= 44px tall; crowd/period-bar buttons >= 36px,
// mirroring test_crowd_status_ui.py's `min-height: 36px` pin and keyboard.cjs's
// 44px default assumption for everything else
```

Screenshot every one of the 12 combinations (3 viewports × 4 states) with `page.screenshot`, saved under
`SCOREBOARD_CAPTURE_DIR` (or, for permanent evidence, directly into `.scratch/soccer-mode/evidence/u001/`) as
`u001-<width>x<height>-<state>.png`.

---

## 5. Spectator/editor checks

### 5.1 Default soccer layout, 24-character names

`tests/ui/soccer_spectator.cjs` (section 1's table entry) reuses `spectator.cjs`'s `measureWidgets`-style glyph-ink
box check verbatim in structure (see the `inkRect`/`measureWidgets` code read from `grid.cjs`/`spectator.cjs`
above): for every visible widget with non-empty text, compute the actual glyph ink rectangle via
`document.createRange().selectNodeContents(...)` plus `CanvasRenderingContext2D.measureText` (not the CSS line
box, which can overhang a `fit_text` box on purpose), and assert that ink rectangle sits inside both the widget's
own box and the 4% safe area, with no two widgets' ink rectangles overlapping. Do this once with the default
layout's stat/card widgets hidden (the default state) and once with a layout that turns every optional widget on,
both at 24-character team names, across all five viewports football's `spectator.cjs` uses.

### 5.2 Event screens

Reuse the pregame/halftime engine the same way football's `test_event_screens_browser.py`/`event_screens.cjs`
does: soccer's own kickoff-countdown and halftime-countdown wording pushed through the same widget registry,
checked at the same three viewports football's event-screen harness uses (1920×1080, 1366×768, 640×360), with
normal and 24-character names, and the same glyph-in-box / no-overlap / ticker-contains-every-line checks. Add
soccer's own halftime countdown boundary values (900s/etc. — pull the exact boundary seconds from whatever
`SoccerRules` settles on for halftime length and the warmup threshold, mirroring the football file's boundary
list rather than copying its literal 900/181/180/0 seconds, which are football's numbers).

### 5.3 The GOAL scene

Already covered by `tests/ui/soccer_goal.cjs` in section 1's table; cross-reference it here as the third
"spectator/editor" deliverable this section asks for.

### 5.4 Editor isolation between sports

A new integration test (fold into `tests/integration/test_soccer_layout_render.py` or split into
`tests/integration/test_soccer_layout_editor_contract.py` if the file grows unwieldy — implementer's call, note
the choice in the spec) proving:

- Opening `views/layout/` (the shared editor) with a soccer context (however the spec wires "which sport is this
  editor session for" — likely a query-string or launch argument on `view_url`) causes `layout_state()` to return
  **only** soccer's widget descriptors, screens, and presets — assert `set(payload['widgets'])` has zero overlap
  with football's `WIDGET_IDS` beyond any genuinely shared ids the spec's registry design intentionally shares
  (e.g. `status_message`/`status_clock` if those are truly identical widgets — call this out explicitly if the
  overlap set is non-empty, and assert it is *exactly* that set, not "whatever happens to match").
- Saving from that soccer-context editor session writes to `<root>/soccer/layouts.json` (verify by hash/mtime
  that `<root>/layouts.json`, football's file, is untouched — byte-for-byte identical hash before and after the
  soccer save, mirroring `test_soccer_persistence_paths.py`'s style).
- Opening the editor in a **football** context immediately afterward still shows exactly football's registry
  and saves back to `<root>/layouts.json`, proving the sport switch is per-session state, not a global that a
  soccer save could have flipped.

---

## 6. What stays "owed" after implementation

Even with every test in sections 1-5 green, record these as explicitly unverified in the phase-7 completion
notes (per `CONTEXT_FOR_AGENTS.md`'s "never mark work done without recorded verification" and the prompt's
"honest reporting" rule):

- **AD (athletic director) confirmations.** Every rule value in `rules_research.md` marked *confirm with the
  AD* — half lengths, overtime format, mercy rule, shootout format, and any boys'/girls' rule difference this
  research could not verify from a primary source — is a configured default the tests above prove is
  *applied correctly*, not that it is *correct for this school's actual competition level and conference*.
- **Physical LED board.** No automated test drives the real LED processor/controller. The spectator-page
  measurements in sections 4-5 prove the web canvas is correct; they say nothing about how the vendor
  processor scales, colour-corrects, or refreshes that same content on the physical board.
- **Target laptop.** The real-runtime harness in section 3 runs on whatever machine executes the test suite,
  not the stadium laptop. WebView2 version, GPU driver quirks, and sustained-session behaviour (a whole real
  two-hour match, not a fake-time rehearsal) remain unverified until run there, exactly as
  `tests/README.md` already caveats for football's `test_full_game_rehearsal.py`.
- **Physical button box.** Section 3's assertion that "F21/F22 still start/stop the clock, every other key does
  nothing" is proved against the synthetic `KeyboardEvent` dispatch `keyboard.cjs`/`soccer_keyboard.cjs` use to
  simulate the macro pad (per the comment in `keyboard.cjs` about F13-F24 needing synthetic events since
  Playwright's keyboard only knows F1-F12). It does not prove the physical USB button box, its firmware, or its
  RegisterHotKey wiring (`host/hotkeys.py`, PL-1) behaves the same way in soccer mode on the actual hardware.
- **A full real shootout on the physical clock/board.** The shootout state machine is proved in fake time
  (`test_soccer_shootout.py`) and in a scripted real-pywebview run (section 3), but never against a live
  penalty-kick shootout's actual pacing, referee signals, or the operator's real reaction time under game
  pressure.
