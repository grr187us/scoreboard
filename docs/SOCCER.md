# Soccer mode

**Status:** implemented on `feature/soccer-mode` (spec checkpoint `.scratch/soccer-mode/spec.md`,
September 15, 2026). Developer-verified only; **not yet run by the owner**, and the rules
research below still has AD confirmations outstanding. Treat everything here as accurate to the
code, not as game-day-proven the way the football path is.

This document is the operator- and maintainer-facing guide to soccer mode. For the architecture
decision behind the sport-profile seam, see [ARCHITECTURE.md](ARCHITECTURE.md) "Sport profiles and
soccer modules". For soccer's operator-workflow differences from football, see
[UX_AND_LAYOUT.md](UX_AND_LAYOUT.md) "Soccer operator differences".

## 1. What soccer mode is

Soccer mode is a second, parallel sport built beside football in the same application: its own
state, commands, clock rules, operator screen, spectator board, and GOAL cutscene, sharing only
what genuinely applies to both games (the saved-team library, the presentation-layout engine's
validation helpers, the webview host, and the publication/backup machinery). Football's own files
are unchanged — see section 8, "What is frozen," below.

## 2. Launching soccer mode

- **A bare launch** (double-clicking the shortcut, or `Scoreboard.exe` with no arguments and no
  `--resume`/`--new-game`) opens a small **"Choose sport"** window first, with **FOOTBALL** and
  **SOCCER** buttons. Neither is auto-chosen; the button matching the last sport played is
  pre-focused so Enter repeats it, but a click is always required.
- **`Scoreboard.exe --sport soccer`** skips the picker and opens straight into soccer's recovery
  screen (or the operator window, if there is nothing to recover).
- **`Scoreboard.exe --sport football`** does the same for football.
- **A bare `--resume` or `--new-game`, with no `--sport`,** behaves exactly as it always has:
  Football, no picker. Existing shortcuts and the button box are unaffected.
- The last sport chosen is remembered in the root `config.json`, section `"sport"`
  (`{"last": "football"}` or `{"last": "soccer"}`), written by
  `scoreboard.host.sport_picker.write_last_sport` and read by `read_last_sport`. A damaged or
  missing section reads as "nothing remembered," never an error.

## 3. Where soccer data lives

Soccer's data lives entirely under a `soccer/` subfolder of the same root the football game
already uses (`%LOCALAPPDATA%\Scoreboard`, or wherever the operator chose — see
[PACKAGING.md](PACKAGING.md) "Choosing where the game is saved"):

```text
<root>/                     Football's files, unchanged: scoreboard.db, config.json (+ "sport"
                             section), layouts.json, teams.json, cutscenes.json, cutscenes/, logs/
<root>/soccer/               scoreboard.db, scoreboard.backup.db, scoreboard.lock,
                             config.json ("rules" = SoccerRules, "display", "presentation"),
                             layouts.json, cutscenes.json, cutscenes/ (+ README.txt),
                             logs/application.log
```

- **`teams.json` is the one shared file.** Saved team presets (name, short name, colours) are the
  same library for both sports — `SoccerApplication.teams` is built from the *root* paths object,
  not the soccer subfolder — so a team saved while running Football is available immediately in
  Soccer and vice versa.
- Everything else soccer touches — its own `config.json` (timing rules, display preference,
  presentation/motion preference), `layouts.json`, `cutscenes.json`, its own `cutscenes/` pack
  folder, its own SQLite database and backup, its own instance lock, and its own log file — is
  separate from football's copy. A soccer laptop setup cannot re-point the football wall, and a
  damaged soccer file cannot cost the operator a football game or vice versa.
- **Recovery is per sport.** `SoccerApplication` takes its own instance lock
  (`<root>/soccer/scoreboard.lock`) and inspects only `<root>/soccer/` for a game to recover
  (`inspect_soccer_recovery`). A football crash is never offered to a soccer launch, and a soccer
  crash is never offered to a football launch. Both sports may hold their locks at the same time;
  running two instances of the *same* sport at once is refused exactly as football refuses it
  today, with the picker staying open so the operator can choose the other sport.

## 4. The operator screen

The soccer operator page (`views/soccer_operator/`) is a fresh page with the same six-row layout
shape as football's, not a themed copy: HOME panel, centre clock/period panel, AWAY panel, a crowd
bar, a period/undo bar, and the action row.

### 4.1 Team panels

Each team panel shows the team name, its saved identity stripe (if one is chosen from Teams ▸),
the score, a **SCORE ▸** button, four stat nudges (`SHOTS`, `SAVES`, `CORNERS`, `FOULS`, each with
`−`/`+`), and **YELLOW**/**RED** card buttons with a running `Y n · R n` count.

- **SCORE ▸ then GOAL.** Pressing **SCORE ▸** arms that team's scoring block (a "· SCORING"
  suffix appears on the panel heading); the block then shows a **GOAL** button and a `✕` to cancel.
  Pressing **GOAL** submits `add_goal` for that team and disarms. Arming auto-disarms after eight
  seconds of inactivity, and blurring the window, pressing Escape, or opening a drawer/dialog also
  disarms it. Only one team can be armed at a time.
- **Cards with number entry.** **YELLOW** or **RED** arms that same panel slot as a card-entry
  block (heading suffix "· CARD"): a player-number field, a **NO #** button to clear it, and a
  **CONFIRM** button that sends `add_card` with the team, the card kind, and the typed number (or
  `null` if none was entered). `✕` cancels. There is no automatic second-yellow-to-red escalation
  — a second yellow just records as a second yellow — but the Corrections drawer offers a
  **2ND YELLOW → RED** shortcut per team that sends a yellow then a red in one press.
- **Stats nudges** apply `add_stat` with `step: ±1` immediately, no confirmation, exactly like
  football's down/distance nudges.

### 4.2 Clock and period panel

- **GAME 40:00 STOPPED** and a **START**/**STOP** pair are the only clock controls. There is no
  play clock and no separate stoppage button: **STOP is the stoppage** (the owner's decision —
  NFHS convention has the referee's signal stop the clock, and one press on STOP already models
  that; a combined "STOPPAGE" button from an earlier design draft was not adopted).
- **PERIOD ◀ ▶** advances or reverses the period (`period_forward`/`period_back`, both confirmed),
  with the next period and its configured length shown as text.
- **The SHOOTOUT panel** replaces the clock block, in the same fixed-height space, only while
  `period == "SHOOTOUT"`. It shows the round, whose turn it is to kick, a dot tally for each side, a
  kicker-number field, **HOME MADE**/**HOME MISSED**/**AWAY MADE**/**AWAY MISSED** buttons (only the
  side named by `next_team` is enabled), a **HOME**/**AWAY** first-kicker choice shown once before
  the first kick, and **FINISH SHOOTOUT…**, enabled only once the shootout is mathematically
  decided. Confirming names the winner and the resulting score.

### 4.3 Crowd bar

**INJURY**, **DELAY**, and **WEATHER** raise a crowd status message with no other stoppage wording
(no "TIMEOUT" or "OFFICIALS' T.O." — those are football-only words). **CLEAR** appears only while a
message is raised. **WEATHER** additionally starts a countdown (default 30:00, the NCHSAA lightning
wait); the countdown's own **START**/**STOP** group appears only while WEATHER is raised or a
countdown is still showing, framed to the right of the four message buttons so nothing shifts
position when they appear — the same show/hide pattern football's crowd bar uses.

### 4.4 Period decision and mercy prompts

- **Period decision dialog.** Natural clock expiry in `2nd`, `OT1`, or `OT2` raises a dialog whose
  choices come from Python (`period_decision.choices`): after `2nd`, Overtime (if configured) or
  Shootout (if enabled and there is no overtime), plus Final and Keep; after `OT1`, OT2 or
  Shootout/Final; after `OT2`, Shootout/Final/Keep. Each choice is an ordinary confirmed
  `set_period`.
- **Mercy banner.** Reaching the configured mercy-rule differential raises a banner with exactly
  two actions: **Keep playing**, or **End Game…** (the same Game ▸ action as everywhere else). It
  is never automatic and never ends the game on its own.

### 4.5 Drawers and Game ▸

- **Teams ▸** — identical to football: the shared `teams.json` library, `set_team_name` restricted
  to pregame, and the same soft "not chosen yet" prompt.
- **Corrections ▸** — per-team score `+1`/`−1`/typed value with **Apply…**; per-team stat **Set**;
  a list of recorded cards (`#10 · 32:14 · 1ST`, each with **Remove…**) plus the
  **2ND YELLOW → RED** shortcut described above; the game clock's typed correction (clock must be
  stopped first) and **Apply…**; a direct period-label set; team names; a shootout kick list with
  **Correct…** and **Remove last…**; and the **Saved to** folder row with **Choose folder…**
  (identical contract to football's — see [PACKAGING.md](PACKAGING.md)).
- **Setup ▸** — see section 9.
- **Game ▸** — **Reset Game Clock…**, **End Game…**, **New Game…**, the same danger-confirmed
  triad football uses.
- **Field Assistant**, **Cutscenes**, **Shortcut Help**, **Advanced ▸** (test window, logs, layout
  editor) — open soccer's own versions of each window (sections 5–7 below).
- **UNDO…** — confirmed, and names the reversal before applying it, exactly like football's.

## 5. Keyboard shortcuts

`views/soccer_operator/keyboard.js` is a fresh table, not football's `keyboard.js` reused — soccer
has no play clock, no down/distance, and a different scoring/card/crowd vocabulary. The binding
list, exactly as shipped:

| Key | Action |
|---|---|
| `Space` | Game clock Start / Stop |
| `G` | HOME goal — press once to arm, again to apply |
| `H` | AWAY goal — press once to arm, again to apply |
| `Q` | Period forward (confirmed) |
| `Shift+Q` | Period back (confirmed) |
| `A` / `Shift+A` | HOME shots +1 / −1 |
| `S` / `Shift+S` | HOME saves +1 / −1 |
| `D` / `Shift+D` | HOME corners +1 / −1 |
| `F` / `Shift+F` | HOME fouls +1 / −1 |
| `J` / `Shift+J` | AWAY shots +1 / −1 |
| `K` / `Shift+K` | AWAY saves +1 / −1 |
| `L` / `Shift+L` | AWAY corners +1 / −1 |
| `;` / `Shift+;` | AWAY fouls +1 / −1 |
| `Y` | HOME yellow card — arms the card panel (CONFIRM/Enter applies) |
| `Shift+Y` | AWAY yellow card — arms the card panel |
| `R` | HOME red card — arms the card panel |
| `Shift+R` | AWAY red card — arms the card panel |
| `I` | Crowd INJURY |
| `E` | Crowd DELAY |
| `W` | Crowd WEATHER |
| `X` | Clear crowd message |
| `Ctrl+Z` | Undo the last reversible command (confirmed, names the reversal) |
| `1` | Replay the GOAL cutscene for HOME |
| `2` | Replay the GOAL cutscene for AWAY |
| `Shift+C` | Cancel a playing cutscene |
| `Esc` | Close dialog / drawer / disarm |

## 6. The button box (physical F-keys)

`host/soccer_hotkeys.py`'s `SOCCER_HOTKEY_TABLE` registers only **F21** (game clock start) and
**F22** (game clock stop) for a soccer session — the same two rows football's `HOTKEY_TABLE` uses
for its start/stop rocker, taken by command name so a reorder of football's table cannot silently
change which physical button soccer registers. **F15 through F20 are not registered** while
soccer is running, and the soccer operator page's own `keyboard.js` binds no F-keys either, so
those six buttons simply do nothing during a soccer session. Football's `host/hotkeys.py` and the
firmware/pin map are completely untouched; a soccer launch does not reflash or reconfigure the box.

## 7. Setup drawer — soccer rules

Every row is a field of `domain.soccer.rules.SoccerRules`, stored in soccer's own `config.json`
under the `"rules"` section (`read_soccer_rules`/`write_soccer_rules`), applied the next time a
period, a new game, or a countdown loads — never retroactively, the same rule football's own
`GameRules`/Setup drawer follows. The table below is `SOCCER_RULE_FIELDS`
(`src/scoreboard/domain/soccer/rules.py`) exactly, in the order the drawer renders them:

| Field | Label | Kind | Default | Allowed range | Rule source |
|---|---|---|---|---|---|
| `half_seconds` | Half length | clock | 40:00 | 5:00–60:00 | NFHS Rule 7 (2×40 or 4×20); NCHSAA is silent and plays the NFHS default |
| `halftime_seconds` | Halftime countdown | clock | 10:00 | 1:00–60:00 | NFHS Rule 7 default; NCHSAA is silent |
| `warmup_seconds` | Warmup label at | clock | 3:00 | 0:00 up to just under the halftime length | football precedent (no soccer-specific rule) |
| `pregame_seconds` | Pregame countdown | clock | 30:00 | 1:00–60:00 | football precedent |
| `overtime_periods` | Overtime periods | count | 2 | 0–2 | NCHSAA §4.9.1(m) (0 for non-conference regular season or JV) |
| `overtime_seconds` | Overtime period length | clock | 10:00 | 1:00–20:00 | NCHSAA §4.9.1(m): two complete 10-minute periods, not sudden victory |
| `golden_goal` | Golden goal ends overtime | toggle | off | — | NCHSAA overtime is explicitly "not sudden victory"; default matches |
| `shootout_enabled` | Kicks from the mark after overtime | toggle | off | — | NCHSAA §4.9.1(m)(2), on only for non-conference tournament/playoff games |
| `shootout_initial_kickers` | Shootout kickers | count | 5 | 1–11 | MHSAA/TASO restatement of the NFHS procedure |
| `shootout_credit_goal` | Add one goal to the shootout winner | toggle | on | — | NCHSAA §4.9.1(m)(2): "One goal is added to the winning team's score" |
| `mercy_differential` | Mercy-rule goal differential | count | 9 | 0 (off)–20 | NCHSAA §4.9.1(k), the "Nine-Goal Rule" |
| `mercy_applies` | Mercy rule applies | choice | `halftime_and_second_half` | `halftime_and_second_half`, `any_time`, `off` | NCHSAA §4.9.1(k) wording ("by halftime or at any time in the second half") |
| `stop_clock_on_goal` | Stop the clock when a goal is recorded | toggle | on | — | NFHS Rule 7-4 (clock stops on a goal) |
| `clock_direction` | Game clock counts | choice | `down` | `down`, `up` | NFHS-wide convention; `up` is a display transform only |
| `weather_seconds` | WEATHER countdown | clock (seconds) | 30:00 | 0:01–30:00 | NCHSAA lightning-delay policy (30 minutes) |
| `late_sub_note` | "Stop the clock for a leading team's substitution in the last 5:00 (NFHS 7-4-3)" | note (informational, no toggle) | — | — | NFHS 7-4-3; whether NC has adopted it is unconfirmed (see "Confirm with the AD" below) |

**Confirm with the AD** — from `.scratch/soccer-mode/rules_research.md`, each already defaulted
above so the drawer is usable before the answer arrives:

1. Is the scoreboard clock actually the NCHSAA-recognized "official" clock, or does the referee's
   own watch govern regardless of the display? *Default: treat the board as a best-effort display
   only; never claim authority over a dispute.*
2. Has North Carolina adopted the NFHS option to stop the clock for a leading team's late
   substitution (final 5:00 of the second half, and possibly overtime)? *Default: the `late_sub_note`
   row is informational only — there is no automatic clock stop for this, and no toggle to model it
   yet.*
3. How is a conference **tournament** game classified — as a conference game (2×10 overtime, tie
   stands) or as tournament play (kicks from the mark)? *Default: treated the same as a conference
   regular-season game.*
4. Is the current 10-minute conference-overtime figure correct, versus an older 5-minute figure a
   referee-association bulletin may have cited? *Default: trust the current handbook's 10 minutes.*
5. Exact varsity half length (40:00) for NCHSAA specifically, since the handbook defers to the NFHS
   book without restating it. *Default: 40:00, per NFHS.*
6. Exact halftime length (10:00), same gap as #5. *Default: 10:00, per NFHS.*
7. Has NCHSAA adopted the NFHS 2026-27 card-signalling process change in a way that affects when an
   operator should log a card? *Default: no workflow change; log a card when the official shows it.*
8. Does the Nine-Goal mercy rule re-trigger during overtime, since its text says "the second half"?
   *Default: no — `mercy_applies` never fires in `OT1`/`OT2` regardless of the chosen option.*

## 8. Spectator board and layout editor

- **Default layout: "Soccer Grid."** The same palette, fonts (Bahnschrift Condensed for labels,
  the bundled varsity/Graduate stack for digits), header rules, and chamfered panel styling as
  football's Scoreboard Grid, retargeted to soccer's own widget set: team panels with a score, an
  amber game clock, and a gold-framed period readout in place of football's play-clock panel.
  Two other built-in presets ship alongside it: **Broadcast bar** (soccer widgets in football's
  Broadcast-bar geometry) and **Classic** (plain, unstyled geometry).
- **Optional widgets, hidden by default:** the four stat pairs (`home_shots`/`away_shots`,
  `home_saves`/`away_saves`, `home_corners`/`away_corners`, `home_fouls`/`away_fouls`), the four
  card counts (`home_yellow`/`away_yellow`/`home_red`/`away_red`, blank at zero), and the two
  shootout tallies (`shootout_home`/`shootout_away`, blank until a kick). An operator turns any of
  these on from the layout editor exactly as football's optional widgets work.
- **The game clock hides on FINAL and during the shootout.** `SOCCER_FINAL_HIDDEN_WIDGET_IDS`
  (`game_clock_label`, `game_clock_value`) are added to `board.hidden_widgets` whenever
  `lifecycle == "FINAL"` **or** `period == "SHOOTOUT"` — period itself keeps showing "FINAL" or
  "SHOOTOUT" so the wall still reads correctly.
- **Pregame and halftime screens are football's own, unchanged.** A soccer layout's
  `screens.pregame`/`screens.halftime` are validated and rendered by football's existing event-
  screen registry and presets (Grid-style KICKOFF IN / UNTIL SECOND HALF, Broadcast Welcome, and
  the rest of the gallery in [UX_AND_LAYOUT.md](UX_AND_LAYOUT.md) section 10) — soccer contributes
  no new event-screen code at all.
- **The editor is registry-isolated.** Opening the layout editor from a soccer session hands it
  `PresentationLayouts(layout_module=soccer_layout, paths=<root>/soccer)`; the game screen's kind
  is `"soccer"`, so the editor draws the soccer widget registry and saves to
  `<root>/soccer/layouts.json`. A soccer session never sees a football widget, and vice versa.

## 9. The GOAL cutscene

- One event, `goal`, triggered automatically after an accepted `add_goal` (a **"Play GOAL
  automatically"** switch in the Cutscenes window, default **on**), by pressing `1`/`2` on the
  operator keyboard (section 5), or from the GOAL HOME / GOAL AWAY buttons in the soccer Cutscenes
  window itself. `Shift+C`, or the Cutscenes window's CANCEL, ends it early.
- **Unlike football's fixed "Tigers" branding, the GOAL scene is team-aware.** The headline is
  always `GOAL`; the subline and `team_name` are the *scoring team's own name*, read live from the
  spectator snapshot and upper-cased — a visitor's goal never reads "TIGERS." Team colours come from
  that team's saved identity (Teams ▸), falling back to navy for home / red for away when no
  identity is saved.
- Duration 7 seconds, no intro, 600 ms outro. The scene file
  (`views/soccer_spectator/cutscenes/soccer.js`/`.css`) follows the same rules every cutscene in
  this codebase follows: `innerHTML` is written only from a fixed `GOAL_MARKUP` constant, no
  `http://` reference anywhere, colours read from `--cs-*` custom properties, and the scene degrades
  cleanly under reduced motion and for a late-joining spectator window.
- Packs live under `<root>/soccer/cutscenes/`, one manifest per folder exactly like football's;
  selection per event is stored in `<root>/soccer/cutscenes.json`; a `README.txt` explaining the
  manifest shape is written into the packs folder the first time it is created.

**Discrepancy noted, not fixed:** the design spec (section 4.4) says the "Play GOAL automatically"
switch lives "in that window and in Setup." The shipped Setup drawer (`views/soccer_operator/
index.html`) has no such switch — the toggle exists only in the Cutscenes window
(`host/soccer_cutscenes.py`'s `set_auto_trigger`/`auto_trigger_enabled`, surfaced in
`views/soccer_cutscenes/index.html`).

## 10. The soccer Field Assistant

`SoccerFieldAssistantBridge` (`host/soccer_field_assistant.py`) is a narrow, JSON-only helper
window bridge, mirroring football's Field Assistant contract exactly:

- **What it can do:** `get_snapshot`, `preview_assist(action)` (read-only, advances nothing), and
  `finalize_assist(action, expected_revision)`, which submits exactly one ordinary, already-
  validated command — `add_stat`, `add_card`, `shootout_kick`, or `set_shootout_first_kicker` —
  tagged `source: "field-assistant"` for the action history.
- **What it cannot do, by construction, not by convention:** it has no method that can ever reach
  `add_goal`, `set_score`, or any clock/period command. `map_assist_action` only ever returns one
  of the four command names above; there is no code path from this bridge to a scoring or clock
  mutation. Scoring stays operator-only; the assistant may log a shootout kick, because that never
  changes the score by itself — only the operator's own **FINISH SHOOTOUT…** press does.
- **Live sync** follows the same September 14, 2026 football fix (PL-2): the helper adopts every
  push from the host rather than flagging a stale draft, and a genuine revision race is refused
  once with `STALE_REVISION` rather than silently merged.

## 11. What is frozen, and how the football gate is checked

Soccer mode is additive by construction. The spec's frozen list
(`.scratch/soccer-mode/spec.md` section 2.4) names every football file that must stay
byte-identical: `domain/state.py`, `domain/commands.py`, `domain/clocks.py`, `domain/rules.py`,
`domain/formatting.py`, `application/service.py`, `application/snapshots.py`, `host/bridge.py`,
`host/startup.py`, `host/hotkeys.py`, `host/cutscenes.py`, `host/teams.py`, `host/publisher.py`,
`host/displays.py`, `presentation/cutscenes.py`, `infrastructure/config.py`,
`infrastructure/teams.py`, `infrastructure/cutscene_packs.py`, `infrastructure/diagnostics.py`,
every file under `views/operator/`, `views/field_assistant/`, `views/startup/`,
`views/spectator/` (including its `cutscenes/`), `views/cutscenes/`, `views/layout/`,
`views/shared/board.css`, `views/shared/base.css`, `views/shared/render.js`, and every existing
file under `tests/`. A short, explicit list of shared files is allowed to change, *additively
only*: `host/app.py` (the new `SportProfile` seam), `__main__.py` (the `--sport` switch),
`infrastructure/paths.py` (`for_sport`), `infrastructure/persistence.py`,
`application/recovery.py`, `infrastructure/layouts.py`, `host/layout_bridge.py`,
`presentation/layout.py`, `views/shared/board.js`, `tools/build_package.py`, and docs.

This is checked mechanically, not by inspection: `.scratch/soccer-mode/football_golden/
frozen_hashes.py` hashes every file in the frozen list against a recorded baseline
(`hashes_all.json`), and `.scratch/soccer-mode/football_golden/golden_run.py` replays a fixed
48-step football game through the real `ScoreboardApplication`/`ScoreboardBridge` with injected
clocks; `diff_golden.py` requires the replay to be byte-identical to the recorded baseline. Both
checks, plus a full-suite run and a `git diff --name-status` check that nothing under `tests/` was
modified (only added), are meant to run at every phase boundary — see spec section 0 for the exact
commands.

## 12. Known limits / not yet verified by the owner

- **The owner has not run a soccer game on the app.** Every claim above is developer-verified
  against the source and the design spec, not against a live rehearsal.
- **The "Play GOAL automatically" switch lives only in the Cutscenes window** (the spec also
  mentioned the Setup drawer); one place is enough for a switch that is on by default.
- **All eight "Confirm with the AD" rules questions in section 7** are running on their documented
  default and have not been confirmed by North Carolina's actual state-association guidance for
  this program.
- **No target-laptop, stadium, or physical button-box evidence exists for soccer mode** — only the
  development-host golden-run/hash/suite checks in section 11. Every open item in
  [PACKAGING.md](PACKAGING.md) "Release checks that still need a person" and
  [DISPLAY_CHECKLIST.md](DISPLAY_CHECKLIST.md) applies equally to a soccer launch of the same
  package, since both sports share one executable.
- **No soccer-specific Playwright/browser suite run, and no real `pywebview` rehearsal, are
  recorded as complete** as of this document; see the phase 3-6 gates in
  `.scratch/soccer-mode/spec.md` section 10 for what each phase's own agent was expected to
  capture, and confirm against `PROJECT_ROADMAP.md`'s soccer entry for what has actually run.
