# Prompt for Fable: add high-school soccer (NCHSAA) to the Scoreboard app

## Your role and the goal

You are working in `C:\Users\505gr\OneDrive\Desktop\Scoreboard`, a Windows, offline, pywebview app that runs a high-school LED scoreboard. It is used live at football games. The athletic director asked for a version where the operator **chooses American football or soccer** when the app starts.

Your job is to add a complete **high-school soccer mode, played under NCHSAA (North Carolina) rules**, to the same app. Keep:

- the scoreboard engine;
- the spectator board renderer;
- the presentation layout editor;
- the cutscene director;
- persistence, recovery and the display handling.

Build soccer-specific game logic, operator controls, board widgets, a GOAL cutscene, pre-game and halftime screens, and a soccer Field Assistant.

**The football app must not change at all.** That is the single most important constraint in this task (see "Football is frozen" below). A school runs football on this app every Friday night; a regression there is worse than soccer being late.

## Decisions already made by the owner (do not re-ask)

1. **One app with a sport picker.** On launch the operator chooses Football or Soccer. Football must behave exactly as it does today once chosen. One package, one install.
2. **Soccer tracks all of the following:**
   - Core: score, game clock, period (halves, overtime, shootout), team names and colours.
   - Per-team shots, saves and corners.
   - Per-team fouls, plus yellow and red cards.
   - A kick-by-kick penalty-kick shootout tally.
3. **Rules come from research.** Research current NCHSAA and NFHS soccer rules yourself. Every rule value (half length, clock direction and stoppages, overtime format, shootout format, any mercy or goal-differential rule, and anything else you find) becomes a **configurable rule in the soccer Setup drawer**, with cited sources. Any value you cannot verify from a primary source is marked *confirm with the AD* and listed as an open question.
4. **Soccer versions of these extras in this first pass:**
   - A GOAL cutscene.
   - The pre-game and halftime event screens.
   - A soccer Field Assistant window.
5. **Button box.** No soccer remap was requested. Default: in soccer mode the F21/F22 rocker still starts and stops the game clock, and every other box key does nothing. Do not change the firmware or the football `HOTKEY_TABLE`. If this can't be done without touching football behaviour, stop and ask.

## Step 0: branch and baseline (do this before writing anything)

1. Confirm the tree is clean: `git status` on `post-live-fixes`. The only expected untracked item is `.scratch/soccer-mode/` (this prompt). If anything else is uncommitted, stop and tell me.
2. Create the branch **from `post-live-fixes`**, not `main`: `git switch -c feature/soccer-mode post-live-fixes`. `post-live-fixes` is 10 commits ahead of `main` and holds the fixes from the first live game; `main` does not have them.
3. Record the football baseline on that commit, and keep it as the regression oracle for the whole task:
   - **Suite count.** Run the full suite and record the count. The expected count is 1353 tests, 0 failures, 0 errors, and 3 skips. Those 3 skips are deliberate `@unittest.skip` markers tied to open question A-1.
   - **Scripted football golden run.** Write a script under `.scratch/soccer-mode/football_golden/`. It drives a football game through the real `ScoreboardApplication` and bridge: new game, team names, quarter changes, scores, a touchdown and try, down, distance and ball on (including nudges), timeouts, both clocks with an injected monotonic clock, a crowd status, Undo, halftime and end game. For each step, save the operator view model JSON, the spectator view model JSON and the history rows. Re-run it at every phase and diff against the baseline. **Any diff is a football regression.**
   - **Frozen-file hashes.** List the football-only source files and record their SHA-256 hashes. Re-check them at every phase.
4. Commit the baseline tooling as the branch's first commit.

## Football is frozen: what "not changed at all" means here

- With Football chosen, everything must be identical to today. That covers:
  - every operator control, keyboard binding, button-box key and window;
  - every view model field, history row, database file and layout file;
  - what the spectator board draws.
  
  The golden-run diff proves this.
- The existing test suite passes **without editing any existing test**. You may add new test files. If an existing test must change because a shared seam moved, stop and explain why before doing it.
- **Football-only files stay byte-identical.** These include:
  - `domain/field_assistant.py`;
  - `views/field_assistant/*`;
  - `views/operator/*`;
  - `host/hotkeys.py`'s table;
  - the football cutscene scenes.
  
  Verify with the hashes from Step 0.
- **Shared files** get the smallest possible *additive* seam, with football as the default path. Expect this for `host/app.py`, `application/service.py`, `host/bridge.py`, `domain/state.py`, `presentation/layout.py`, `presentation/cutscenes.py`, `infrastructure/paths.py`, `views/startup/*` and `__main__.py`. Prefer new soccer modules beside the football ones over branching inside football functions. For example, `domain/soccer/` holds state, commands, clocks and rules, and there is a soccer service, a soccer bridge and `views/soccer_operator/`. Keep an `if sport == ...` inside a football code path to a last resort, and name each one in the spec.
- **Football data stays where it is.** Existing data files keep their current paths and formats: the database, backup, `config.json`, `layouts.json`, the cutscene selection, and whatever recovery reads. Soccer gets its own database, backup, rules and config, layouts and cutscene selection, under a `soccer/` subfolder of the same data root. The saved-team library (`teams.json`) is shared, since it holds the same schools and colours, but soccer must not change its schema. If sharing would force a football change, keep a separate soccer copy and say so.
- **Recovery is per sport.** Resuming a crashed football game must never offer, load or overwrite a soccer game, and the reverse also holds.

## Read first (all of it, before designing)

- `AGENTS.md`: the project rules. Its rules apply to you, including:
  - offline only;
  - confirm dangerous operations;
  - route every mutation through validated commands;
  - use a monotonic clock;
  - update `PROJECT_ROADMAP.md`;
  - never mark work done without recorded verification.
- `PROJECT_ROADMAP.md` in full, and `High School LED Scoreboard — Project Knowledge Base.md` as reference.
- `docs/ARCHITECTURE.md`, `docs/MVP_REQUIREMENTS.md`, `docs/UX_AND_LAYOUT.md` (especially sections 5–8 and 10), `docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`, `docs/POST_LIVE_FIXES.md`, `docs/PACKAGING.md`, `docs/PROJECT_STRUCTURE.md`.
- The code paths you will mirror:
  - **Domain:** `domain/state.py`, `domain/commands.py`, `domain/clocks.py`, `domain/rules.py`, `domain/formatting.py`.
  - **Application:** `application/service.py`, `application/snapshots.py`, `application/recovery.py`.
  - **Host:** `host/bridge.py`, `host/app.py` (`run`, `_choose_startup`), `host/startup.py`, `host/cutscenes.py`, `host/publisher.py`.
  - **Presentation:** `presentation/layout.py` (`WIDGET_IDS`, `WIDGET_FIELDS`, `EVENT_WIDGET_IDS`, `SCREEN_IDS`, presets), `presentation/cutscenes.py` (`CUTSCENE_EVENTS`).
  - **Infrastructure:** `infrastructure/paths.py`, `infrastructure/persistence.py`, `infrastructure/layouts.py`, `infrastructure/teams.py`.
  - **Views:** `views/operator/*`, `views/spectator/*`, `views/shared/board.js`, `views/layout/*`, `views/cutscenes/*`, `views/field_assistant/*`, `views/startup/*`.

## Owner design decisions already baked into football (carry them into soccer)

Soccer should feel like the same product. Copy these patterns rather than inventing new ones:

- **Undo and dangerous actions.** Two-step armed scoring: SCORE ▸ then GOAL, with an 8 s auto-disarm. Undo asks for confirmation first. Direct corrections and game-ending actions are confirmed. New Game, End Game and Reset Clock live in a `Game ▸` drawer, never exposed on the main screen.
- **Team prompt.** A soft team-selection prompt appears after New Game and at launch, and shows NOT CHOSEN on the panels.
- **Crowd bar** (September 14, 2026 UI pass):
  - CLEAR is yellow and shows only while a message is raised.
  - A countdown and its green START and red STOP show only when that message has a countdown.
  - Controls that appear sit to the right, so nothing the operator is reaching for moves.
- **Stat nudges.** One-tap +/− nudges send only a step; Python computes the value. The page never computes a game value; it renders strings Python formatted.
- **Legibility.** Text on team colours picks white or dark ink by contrast. Every live control is a 44 px touch target, and state is never shown by colour alone.
- **No scrolling (U-001).** The operator page must not scroll at 1093×614, 1180×720 or 1366×768 CSS pixels. The board row is the only flexible grid row. Measure this; do not assume it.
- **Crowd messages stay out of Undo.** They must never push a scoring mistake out of reach.

## Soccer scope

### Game model and rules

1. **Research NCHSAA and NFHS soccer.** Use the current NCHSAA handbook and soccer regulations, and the NFHS Soccer Rules Book summaries. Record each rule with its source URL and date retrieved in `.scratch/soccer-mode/rules_research.md`. At minimum cover:
   - varsity and JV half length;
   - whether the stadium clock counts down or up, and when it stops (goals, penalty kicks, cards, injuries, the referee's signal);
   - halftime length;
   - overtime (number and length of periods, golden goal or full periods, regular season vs playoffs);
   - tie-breaking kicks from the mark (rounds, sudden death, who kicks);
   - any goal-differential or mercy rule;
   - whether a clock operator is required and who controls stoppages.
   
   Note where boys' and girls' rules differ.
2. **Soccer rules in their own Setup drawer.** Save them with a host action like football's `rules()` / `save_rules()` and store them in soccer's own config. Rules apply the next time a period or game loads, just as football's do.
3. **Soccer state** (its own dataclass, validated the same way as `GameState`):
   - team names and scores;
   - the period label (for example PRE, 1st half, HALF, 2nd half, overtime periods, SHOOTOUT, FINAL);
   - lifecycle;
   - the game clock (direction per the researched rules);
   - per-team shots, saves, corners, fouls, yellow cards and red cards;
   - the shootout tally: an ordered kick list per team with made/missed, the round, and whether sudden death applies;
   - the crowd status and its countdown, with soccer words to research (for example INJURY, DELAY, WEATHER).
4. **Soccer commands.** Each is validated, recorded in history and undoable where football's equivalent is. The goal command is armed and undoable. Stat increments and corrections are simple steps. Card commands are per team, and a player number is optional if you propose it. Shootout commands record kicks, correct them and finish the shootout. Period and clock commands follow the researched rules. New Game and End Game go through the `Game ▸` drawer.
5. **Persistence, recovery and snapshots** work for soccer with the same guarantees football has.

### Soccer operator (control) screen

Create a new page, for example `views/soccer_operator/`. Do not add modes to the football operator page. Same visual language and fixed grid. For each area below, the prompt says where it goes, what it contains and how it behaves:

- **Team panels** (home and away). They mirror football's: score, identity stripe, NOT CHOSEN, SCORE ▸ / GOAL two-step, and compact +/− stat rows for shots, saves, corners and fouls. Yellow and red card controls follow the design you propose in the spec.
- **Centre panel.** It holds the game clock rectangle with Start and Stop, and the period with ◀ ▶. Soccer has no play clock, so use the freed space deliberately for stoppage-related controls if the research calls for any.
- **Crowd bar.** Soccer messages, same show-and-hide rules as football.
- **Quarter-bar equivalent.** The period, the LAST action strip and UNDO….
- **Shootout panel.** It appears only in the SHOOTOUT period: kick-by-kick made/missed per team with a running tally, following the Sept 14 principle of nothing floating when unused.
- **Drawers.** Teams, Corrections, Setup (the soccer rules), Game, Display, Cutscenes, Field Assistant and Shortcut Help, all with soccer contents.
- **Keyboard.** Propose soccer keyboard bindings in the spec, keeping football's arm-then-apply pattern. Do not reuse football's `keyboard.js`.

### Spectator board and layout editor

- **Keep the layout editor code shared and unchanged in behaviour for football.** Soccer gets its own widget registry: home and away name and score, game clock value and label, period, shots, saves, corners, fouls, yellow and red cards per team, a shootout tally widget, status message and status clock.
  - Stats and cards are optional widgets, hidden by default, so the default board stays clean.
  - Soccer layouts are stored separately. The editor shows the soccer registry when opened from soccer mode.
- **Default soccer layout.** Derive it from the owner's Scoreboard Grid look: varsity digits, amber `#F5AE08` clock, `#F2F2F2` scores, and the bundled fonts. Screenshot it with long team names (24-character maximum) and verify glyphs stay inside their boxes. Validation checks boxes, not text extent.
- **Soccer pre-game and halftime event screens.** Kickoff countdown and halftime countdown, using the existing event-screen engine and widget registry, with soccer wording.

### GOAL cutscene

- Add a soccer cutscene event list. Keep football's `CUTSCENE_EVENTS` and scene files untouched.
- Build a built-in GOAL scene that works with the same director and pack format.
- Follow the existing scene-file rules:
  - no `http://`;
  - `innerHTML` only from `*_MARKUP` constants;
  - delayed one-shot animations run forwards, never both directions;
  - the director/tick lock ordering described in the cutscene docs.
- Trigger it from the soccer GOAL flow the same way football triggers its scenes, including the operator's ability to skip it.

### Soccer Field Assistant

- Build a separate window, for example `views/soccer_field_assistant/`, for a sideline helper. Propose its design in the spec. Suggested starting point:
  - big buttons to log shot, save, corner, foul, yellow and red card per team, with an optional player number;
  - a preview/confirm step before committing, like football's;
  - the shootout kick log;
  - live sync with the operator page, using the push path football's assistant uses.
- It must not be able to change the score or the clock unless the spec says so and I approve it.

## Stop for approval: spec checkpoint

Before implementation, after Step 0, research and reading, write `.scratch/soccer-mode/spec.md`. It must contain:

1. The rules research summary, with sources and the confirm-with-AD list.
2. The architecture:
   - every shared file you will touch and the exact seam;
   - every new module;
   - the data layout on disk;
   - how the sport is chosen at startup, whether the last choice is remembered, and how recovery offers a crashed game per sport.
3. The soccer state, the command list with arguments, which commands are undoable, and the history labels.
4. ASCII wireframes of the soccer operator screen (idle, armed, shootout), the default spectator layout, the event screens and the Field Assistant.
5. Keyboard bindings, button-box behaviour, and the Setup drawer rule list with defaults.
6. The test plan and the football-regression plan.
7. Open questions for me and for the AD, each with your recommended default.

**Then stop and wait for my approval.** Do not write product code before I approve the spec.

## Implementation phases (after approval)

Commit at the end of each phase on `feature/soccer-mode`. Re-run the football golden diff, the frozen-file hashes and the full suite at every phase boundary, and paste the results into the commit message body.

1. **Sport picker and data separation.** The startup page offers Football or Soccer, then Resume or New for that sport. With Football chosen, the golden diff is empty and the paths are unchanged.
2. **Soccer domain, service, bridge, persistence and recovery.** Unit and integration tests mirror the football ones: state validation, each command, clock behaviour under an injected monotonic clock, rules, formatting, recovery, and a full soccer game rehearsal test like `tests/integration/test_full_game_rehearsal.py`.
3. **Soccer operator page, its keyboard and the Setup drawer.** Include source-contract tests like `tests/integration/test_operator_refresh_ui.py` and `test_crowd_status_ui.py`.
4. **Soccer widget registry, default layout, event screens and layout editor wiring.**
5. **GOAL cutscene.**
6. **Soccer Field Assistant.**
7. **Docs and packaging:**
   - a new `docs/SOCCER.md` (rules, workflow, operator guide);
   - updates to `PROJECT_ROADMAP.md`, `docs/ARCHITECTURE.md` and `docs/UX_AND_LAYOUT.md` covering the soccer additions only;
   - a rebuilt package per `docs/PACKAGING.md`, with the `dist\Scoreboard-0.1.0.zip` refresh step it describes.

If you split work across subagents, write the shared spec first, give each agent an exclusive list of files it owns and the exact names and defaults the others will hard-code, and cap it at 5 agents. Keep integration, the football regression checks and final verification yourself. A usage-limit error kills running agents mid-write: before re-spawning, inventory exactly what landed.

## Verification you must perform and record (not only unit tests)

- **Football regression:**
  - the full suite at the baseline count, 0 failures, same 3 A-1 skips, with no existing test edited;
  - an empty golden-run diff;
  - unchanged frozen-file hashes;
  - one real pywebview run with Football chosen that opens the operator window, raises and clears a crowd message, scores and undoes, and shows the football board.
- **Soccer, in the real pywebview runtime** (not only a stub bridge). Copy the pattern from `.scratch/post-live-fixes/realrun_pl3.py` and `.scratch/control-ui-pass/realrun_ui_pass.py`: `ScoreboardApplication` + `WindowHost`, `threading.Timer(3, drive)`, `host.run(startup_choice=...)`, drive with `window.evaluate_js("JSON.stringify(...)")`, read `app.service.state`, capture windows with `.scratch/post-live-fixes/shot.py`. Script a whole game:
  - pick Soccer;
  - choose teams;
  - kickoff;
  - a goal with the cutscene;
  - stats and cards from both the operator page and the Field Assistant;
  - halftime screen;
  - second half;
  - overtime;
  - shootout to a winner;
  - Undo at several points;
  - End Game;
  - relaunch and Resume after a simulated crash.
  
  Save screenshots to `.scratch/soccer-mode/evidence/`.
- **U-001 fit.** Use Playwright/Edge against the real bridge (see `tests/ui/bridge_server.py` and `.scratch/control-ui-pass/`). Measure no page scroll and no row overflow on the soccer operator page at 1093×614, 1180×720 and 1366×768, idle, armed, in the shootout and with an alert showing, with 24-character team names. Screenshot every state.
- **Spectator and editor.** Screenshot the default soccer layout, the event screens and the GOAL scene. Confirm that switching the editor between sports never shows or saves the other sport's widgets.

## Environment facts and traps on this machine

- **Python.** `.\.venv\Scripts\python.exe` (CPython 3.11.9). There is no bare `python` on PATH in the Bash tool.
- **Test command.** `SCOREBOARD_DATA_DIR=<isolated scratch folder> ./.venv/Scripts/python.exe -m unittest discover -s tests`. Never add `-t .`. Never point it at the owner's live data folder `C:\Users\505gr\OneDrive\Desktop\Scoreboard Logs`.
- **Node.** Node 24 is at `C:\Program Files\nodejs` but not on the Bash PATH; run `export PATH="/c/Program Files/nodejs:$PATH"` first. Playwright is a repo devDependency (`node_modules/`), and browser scripts use the `msedge` channel. A script outside the repo needs `NODE_PATH=<repo>/node_modules`.
- **Console encoding.** The console is cp1252: run harnesses with `PYTHONIOENCODING=utf-8`, or a ✓ in the output crashes `print`.
- **Page-revision race.** A Python-side `bridge.command(...)` followed immediately by a page click sends a stale revision and is refused `STALE_REVISION` (and recorded). Sleep about 0.5–1 s after Python-side commands before clicking. In a headless Playwright page over a stdin bridge there are no pushes at all: seed state before `page.goto` and drive by page clicks.
- **Bash heredocs.** Heredocs break when a Python body mixes `'''` with `\u` escapes. Write scripts to a file and run them. Never write `tools\build_package.py` inside a Python string, because `\b` becomes a backspace.
- **Stale test assets.** `tests/integration/test_display_drawer_contract.py` bans the literal `32px` in `operator.css`; expect similar pins. The preview server caches aggressively, so cache-bust with a query string.
- **Screen sizes.** The practice spectator window is 640×360. Use Playwright over the real spectator page for readable board screenshots.

## Rules of engagement

- **Branch and git:**
  - Work only on `feature/soccer-mode`.
  - Never commit to, merge into or rebase `post-live-fixes` or `main`.
  - Never force-push.
  - Push the branch only when I ask.
- **Stopping points:**
  - If a requirement can only be met by changing football behaviour, stop and ask. Do not find a clever way around it.
  - If the rules research is ambiguous, pick the NFHS default, make it configurable, flag it, and keep going (after the spec is approved).
- **Honest reporting.** Report what you verified with numbers and file paths. Say plainly what you did not verify or what is still owed, especially anything the AD or a real game must confirm.
