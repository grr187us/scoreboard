# Soccer mode: design draft (operator, drawers, keyboard, spectator, Field
# Assistant, GOAL cutscene)

Author: design-draft agent, September 15, 2026. Scope: this file only, per
`CONTEXT_FOR_AGENTS.md`. Every wireframe is ASCII, ≤80 columns. Choices the
owner might reverse are marked **OWNER CHOICE** with a recommended default.
Football patterns copied verbatim are cited to the file/line they come from.

Sources read: `views/operator/index.html`, `operator.js`, `operator.css`,
`keyboard.js`; `views/field_assistant/index.html` + `.js`; `docs/UX_AND_LAYOUT.md`
§§2,4,5-5d,6,8,11,12; `presentation/layout.py` `_grid_preset_layout` (line
3433), `WIDGET_IDS`/`EVENT_WIDGET_IDS`; `views/cutscenes/index.html` and
`views/spectator/cutscenes/builtin.js`.

---

## 0. Shared conventions carried over from football unchanged

- Fixed page grid, only the board row flexes (`operator.css` lines 8-13,
  26). Same six-row skeleton: health, alert, board, crowd bar, period bar,
  tools.
- Two-step armed scoring: `SCORE ▸` arms, 8 s auto-disarm
  (`ARM_SECONDS = 8`, `operator.js` line 36), a point/goal press applies and
  disarms, `✕` cancels. Disarms on blur, Escape, opening any drawer, or a
  dialog opening — identical to `armScore`/`disarmScore` in `operator.js`.
- Undo asks first, naming what it reverses in Python's own words
  (`Reverses: ` + `last_action.label`, `operator.js` line 574).
- `Game ▸` drawer is the only place New Game / End Game / Reset Clock live.
- Soft NOT CHOSEN team prompt: text first, warm border on `Teams ▸`, opens
  itself exactly twice (after New Game, and on first paint of a pregame
  board with placeholder names) — `renderSetup` (`operator.js` line 136).
- Crowd bar rules (September 14, 2026 pass, `operator.css` lines 401-448,
  `renderCrowdStatus` `operator.js` line 423): CLEAR (yellow) shows only
  while a message is raised; the countdown and its green START / red STOP
  show only when the raised message carries a countdown; both sit to the
  right of the message buttons so appearing never moves a button the
  operator is reaching for.
- 44 px minimum touch target for every live control; crowd bar and
  period/quarter-equivalent bar controls use the 36 px floor instead,
  exactly like football's crowd/quarter bars (`operator.css` lines 340-343,
  464-467).
- No page scroll at 1093×614, 1180×720, 1366×768 (U-001). Football's
  measured board row at 1093×614 is 356 px (`UX_AND_LAYOUT.md` line 663).

---

## 1. Soccer operator screen

### 1.1 Team panel row-height budget (1093×614, U-001)

Football's team panel at 356 px board row holds, top to bottom: `h2` (~20 px)
+ team-name (24 px) + identity stripe (0 or 26 px) + NOT CHOSEN (0 or 18 px)
+ score (flex, clamps 48-84 px) + score-controls block (52 px min), six items,
five 6 px gaps, 10 px panel padding top+bottom (20 px). Soccer's team panel
must additionally hold: 2 compact stat rows (shots+saves, corners+fouls) and
1 card row (YELLOW/RED). That is 3 more fixed rows of 44 px plus 3 more 6 px
gaps = 132 + 18 = 150 px of new fixed content football's panel does not carry.

**OWNER CHOICE — recommended default: shrink the score.** Football's score
is allowed to clamp up to 84 px because nothing else competes for the
panel's flexible space. Soccer's score competes with 150 px of new fixed
rows, so its clamp is recommended at `clamp(30px, 4.5vh, 56px)` instead of
football's `clamp(48px, 9vh, 84px)`. Budget at 1093×614 (356 px board row,
20 px panel padding, six 6 px gaps = 36 px):

```
h2                         20 px
team-name                  24 px
stripe (when shown)         0 px (hidden by default, same as football)
NOT CHOSEN (when shown)     0 px
score (flexible)          ~62 px  <- clamp(30,4.5vh,56) fits at 614px tall
score-controls              44 px (was 52 in football; see 1.2)
stat row 1 (SHOT / SAVE)    44 px
stat row 2 (CORNER / FOUL)  44 px
card row (YELLOW / RED)     44 px
padding + 6 gaps            56 px
-----------------------------------
total                      338 px (fits inside 356 px, 18 px to spare)
```

This must be re-measured in the real Chromium/pywebview runtime exactly as
football's was (`UX_AND_LAYOUT.md` line 655) before it ships; these numbers
are an estimate that leaves an 18 px margin at the tightest viewport.

### 1.2 Score controls (armed scoring)

Same fixed-height-block swap as football (`operator.css` lines 208-233):
idle row is `SCORE ▸` + a compact shot-tally readout (not a timeout —
soccer's team panel has no timeout concept); armed row is `GOAL` + `✕`
(soccer has no point value choice — a goal is always 1). Recommended
control height 44 px, not football's 52 px, to make room in 1.1's budget.

```
idle:   [        SCORE ▸        ][  SHOTS 4  ]
armed:  [          GOAL          ][    ✕     ]
```

### 1.3 Card controls — OWNER CHOICE

**Recommended: one-tap card buttons that open a small inline number pad to
the right, appearing exactly like the crowd bar's countdown group
(`operator.css` lines 384-392, "appearing controls sit to the right,"
`CONTEXT_FOR_AGENTS.md` line 91).** `YELLOW` and `RED` sit in the card row;
pressing one raises a 3-digit inline keypad chip in the same row (never a
drawer — a card must be logged in the seconds after the whistle, and a
drawer already asks too much of a volunteer under pressure, the same
argument that keeps the crowd bar off the drawer pattern,
`UX_AND_LAYOUT.md` line 465). `NO #` is offered as a keypad button so a
number is never required. `CONFIRM` commits `card_yellow`/`card_red`;
`✕` cancels with nothing sent. This mirrors football's arm-then-apply
pattern (arm = press YELLOW/RED, apply = CONFIRM) rather than a bare
one-tap, because a card is not reversible the way a stat nudge is (it
should get the same "second press to be sure" shape as scoring, not the
zero-step shape of a shot/save nudge).

Rejected alternative: a full sub-drawer per card (too slow — a card must
be recorded before the restart, unlike a substitution). Rejected
alternative: one-tap with no number ever (loses NCHSAA's 5/10/15-yellow
suspension tracking, `CONTEXT_FOR_AGENTS.md` line 108, which needs a
kicker/player number to be useful later even if not enforced by software
in this pass).

```
card row, idle:
[  YELLOW  ][  RED  ]

card row, YELLOW armed (number pad appears to the right, U-001 height
unchanged -- same fixed-height-block swap as scoring):
[ YELLOW·armed ][7][8][9][NO #][✕]
                [4][5][6]
                [1][2][3][CONFIRM]
```

Given the 44 px single-row budget in 1.1, the keypad cannot literally grow
upward without breaking U-001 (only the board row may flex). **Revised
recommendation to fit the budget:** the keypad is a single-row strip of
three preset quick-digits are impractical for arbitrary jersey numbers, so
instead the row grows into the space score-controls would use if idle would
grow using the same disarm-swaps-content approach as football's own score
block — i.e. arming a card **also** takes over the score-controls block
(mutually exclusive with arming a goal; both use the identical fixed-height
region), showing a single `#` number field (typed, `data-draft="true"`,
F-016 rule: typing changes nothing until Confirm) plus `NO #`/`CONFIRM`/`✕`.
This keeps one shared fixed-height "the operator is doing something
active" block per panel, exactly as football keeps one block for scoring,
and costs no extra row:

```
score-controls block, YELLOW armed for HOME:
[ YELLOW #: [__] ][ NO # ][ CONFIRM ][ ✕ ]
```

### 1.4 Centre panel — clock + period + stoppage

No play clock. The freed column width is used for: game clock START/STOP
(unchanged shape), period ◀ ▶, and a **STOPPAGE** quick group — **OWNER
CHOICE, recommended default:** one atomic button, `STOPPAGE`, that stops
the game clock and raises the crowd word `STOPPAGE` in one press (the same
atomic "load and start" shape as football's crowd `TIMEOUT` button,
`operator.js` line 175/`index.html` line 175), because NFHS 7-4 stops the
clock for an injury, a card, a goal, or the referee's signal
(`CONTEXT_FOR_AGENTS.md` line 99) and an operator should not have to
press two controls to do both at once. A plain `RESTART` button undoes
neither the clock stop nor the crowd word by itself — the operator presses
`START` on the clock and `CLEAR` on the crowd bar separately, exactly as
football already separates "stop the clock" from "clear the message."
This is a new command (`stoppage`) beyond football's crowd vocabulary; it
is not a `set_game_status` alias because it must also touch the clock,
which no crowd-bar command does today (crowd messages "stay out of Undo,"
`CONTEXT_FOR_AGENTS.md` line 97 — but a clock stop like this one **is**
already undoable via the existing `game_clock_stop`/`start` history, so
`stoppage`'s clock-stop half is undoable and its crowd-word half is not,
matching football's own split between `timeout_used` (undoable) and the
crowd `TIMEOUT` button (not undoable)).

```
┌ CENTRE PANEL ─────────────────────────────┐
│ GAME CLOCK                                │
│           45:00                           │
│           STOPPED                         │
│      [ START ]  [ STOP ]                  │
│ ────────────────────────────────────────  │
│ PERIOD   [ ◀ ]   1ST HALF   [ ▶ ]         │
│ [        STOPPAGE (stop clock + flag)   ] │
└────────────────────────────────────────────┘
```

### 1.5 Wireframe — idle (no team armed, not SHOOTOUT)

```
┌ SCOREBOARD CONTROL  GAME 45:00 STOPPED  DISPLAY OPEN [Reopen][Display…]──┐
│ SAVED  Rev 42                                                            │
├───────────────────┬──────────────────────────────┬──────────────────────┤
│ HOME               │ GAME CLOCK                    │ AWAY                │
│ EAGLES              │        45:00                  │ TIGERS              │
│ NOT CHOSEN      1   │        STOPPED                │ NOT CHOSEN      0   │
│ [ SCORE▸ ][SHOTS 4] │   [ START ]    [ STOP ]        │[SCORE▸][SHOTS 6]   │
│ [ − ][SAVE 2][ + ]  │ ──────────────────────────    │[ − ][SAVE 3][ + ]  │
│ [−][CORNER 3][+]    │ PERIOD [◀] 1ST HALF [▶]        │[−][CORNER 5][+]    │
│ [−][FOUL 1][+]      │ [    STOPPAGE (clock+flag)  ]  │[−][FOUL 2][+]      │
│ [ YELLOW ][ RED ]   │                                │[ YELLOW ][ RED ]   │
├─────────────────────┴────────────────────────────────┴───────────────────┤
│ CROWD  [—]  [GOAL][INJURY][DELAY][WEATHER][OFFICIALS' T.O.]              │
├────────────────────────────────────────────────────────────────────────┤
│ PERIOD [◀] 1ST HALF [▶]     LAST: nothing yet          [ UNDO… ]         │
├────────────────────────────────────────────────────────────────────────┤
│[Teams▸][Corrections▸][Setup▸][Cutscenes][Field Assistant][Shortcut Help] │
│[Advanced▸]                                                   [ Game ▸ ] │
└────────────────────────────────────────────────────────────────────────┘
```

Note: the crowd bar's four message words are `GOAL` / `INJURY` / `DELAY` /
`WEATHER` / `OFFICIALS' TIME OUT` — see 1.7. The bottom bar reuses the
QUARTER-bar shape but is labelled `PERIOD`; the ◀ ▶ and LAST/UNDO controls
are identical in behaviour to football's quarter bar (`operator.js` lines
456-482, `describeUndo`).

### 1.6 Wireframe — HOME armed (`SCORE ▸` pressed)

Only the HOME team panel's score-controls block changes; nothing else on
the page moves (same swap-inside-fixed-block rule as football,
`operator.css` lines 205-207).

```
┌───────────────────┬──────────────────────────────┬──────────────────────┐
│ HOME · SCORING      │ GAME CLOCK                    │ AWAY                │
│ EAGLES              │        45:00                  │ TIGERS              │
│ NOT CHOSEN      1   │        STOPPED                │ NOT CHOSEN      0   │
│ [   GOAL   ][ ✕ ]   │   [ START ]    [ STOP ]        │[SCORE▸][SHOTS 6]   │
│ [ − ][SAVE 2][ + ]  │ ──────────────────────────    │[ − ][SAVE 3][ + ]  │
│ [−][CORNER 3][+]    │ PERIOD [◀] 1ST HALF [▶]        │[−][CORNER 5][+]    │
│ [−][FOUL 1][+]      │ [    STOPPAGE (clock+flag)  ]  │[−][FOUL 2][+]      │
│ [ YELLOW ][ RED ]   │                                │[ YELLOW ][ RED ]   │
└─────────────────────┴────────────────────────────────┴───────────────────┘
```

A `GOAL` press applies and disarms, exactly like football's point press
(`operator.js` lines 819-823: `if (name === 'add_score') disarmScore();`),
and triggers the soccer GOAL cutscene per §6.

### 1.7 SHOOTOUT period — shootout panel appears only then

Nothing floats when unused (the Sept 14, 2026 principle,
`CONTEXT_FOR_AGENTS.md` line 133). When `period == "SHOOTOUT"`, the centre
panel's clock block is replaced (same swap-inside-fixed-block rule) by a
shootout panel: round counter, kicker-number entry, and MADE/MISSED per
team, with a running tally. The game clock is not shown during the
shootout (NFHS kicks from the mark run untimed — see `rules_research.md`
for confirmation); `GAME CLOCK` label is swapped for `SHOOTOUT`.

```
┌───────────────────┬──────────────────────────────┬──────────────────────┐
│ HOME               │ SHOOTOUT — ROUND 3             │ AWAY                │
│ EAGLES         5(2)│  HOME ●●○  |  AWAY ●○○         │ TIGERS         5(1) │
│ NOT CHOSEN          │  Kicker # [ 9 ]                │ NOT CHOSEN          │
│ [ SCORE▸ ][SHOTS 4] │  [ HOME MADE ][ HOME MISSED ]  │[SCORE▸][SHOTS 6]   │
│ [ − ][SAVE 2][ + ]  │  [ AWAY MADE ][ AWAY MISSED ]  │[ − ][SAVE 3][ + ]  │
│ [−][CORNER 3][+]    │                                │[−][CORNER 5][+]    │
│ [−][FOUL 1][+]      │  [ END SHOOTOUT… ]             │[−][FOUL 2][+]      │
│ [ YELLOW ][ RED ]   │                                │[ YELLOW ][ RED ]   │
└─────────────────────┴────────────────────────────────┴───────────────────┘
```

`5(2)` reads "regulation score 5, shootout makes 2 so far" — same
compact-readout instinct as football's `TIMEOUT · 3`. `●●○` are the same
filled/hollow dot idiom the Scoreboard Grid preset already uses for
timeouts (`layout.py` `display_format: "dots"`, line 3487), reused here for
made/missed-so-far in the current round (not a rule value, purely a glance
aid). `END SHOOTOUT…` is a local-confirm control (like `end_game`) that
records the winner once a side is mathematically decided; it is **not**
inside the `Game ▸` drawer because it is a normal part of finishing this
period, not a lifecycle danger action — but it does confirm, because it is
irreversible in the way a quarter change is.

`SCORE ▸`/`GOAL` still exists on the team panels during SHOOTOUT for the
rare case a card or a regulation-adjacent correction is needed, but the
`GOAL` command should be refused by the bridge during SHOOTOUT (regulation
score is frozen; shootout makes are tracked separately) — flagged as an
**open question for the owner and the spec's command list**, not decided
here.

---

## 2. Drawers

All drawers keep football's overlay/scroll-inside-itself shape
(`operator.css` lines 691-709) and the `data-draft="true"` / Apply-asks-old-
and-new-value pattern (F-016).

### 2.1 Teams — identical shape to football's (`index.html` lines 373-418):
now/list/save-a-team rows, unchanged behaviour, soccer's own `teams.json`
read (shared file, schema unchanged per the hard rule).

### 2.2 Corrections

```
┌───────────────────────── CORRECTIONS ─────────────────────────────────┐
│ HOME score: 1  [+1][-1]  Set [ 1 ] [Apply…]                            │
│ AWAY score: 0  [+1][-1]  Set [ 0 ] [Apply…]                            │
│ HOME shots 4 [+1][-1] Set[__][Apply] | saves 2 corners 3 fouls 1       │
│ AWAY shots 6 [+1][-1] Set[__][Apply] | saves 3 corners 5 fouls 2       │
│ HOME cards: yellow 0 [+1][-1][Correct…] red 0 [+1][-1][Correct…]       │
│ AWAY cards: yellow 1 [+1][-1][Correct…] red 0 [+1][-1][Correct…]       │
│ Game clock: [45]:[00]   (must be stopped)          [Apply…]            │
│ Period: [PRE|1ST|HALF|2ND|OT1|OT2|SHOOTOUT|FINAL]  [Apply…]            │
│ Team names: [_______][Apply…]  [_______][Apply…]                       │
│ Saved to  <folder path>  [Choose folder…][Use standard folder]         │
│                                                             [Close]     │
└──────────────────────────────────────────────────────────────────────┘
```

A card *correction* (fixing a mis-logged card, not issuing a new one) is a
direct set inside this drawer, confirmed like a score set — the same
argument football uses for why a drawer's own presence is protection
enough for `+1`/`-1` stat nudges (`UX_AND_LAYOUT.md` line 197-204), but a
card is rarer and higher-stakes than a stat, so `Correct…` opens the local
confirm every score-set control already uses.

### 2.3 Setup (soccer rules) — see §5 for the full field list with defaults.
Same shape as football's Setup drawer (`index.html` lines 429-505):
minutes:seconds pairs, plain-number fields, on/off toggles, `Restore
defaults` / `Save rules` / `Close`, `api.save_rules()` host action (no
revision, no history row).

### 2.4 Game — identical shape to football's (`index.html` lines 604-634):
Reset Game Clock…, End Game…, New Game…, all danger-styled, all confirmed.

### 2.5 Display, Cutscenes-window-opener, Shortcut Help, History, Advanced
— identical shape and behaviour to football's; only the Shortcut Help
table's rows change (§3) and Advanced's layout-editor button opens the
soccer widget registry when launched from soccer mode (per
`CONTEXT_FOR_AGENTS.md` line 79-80, the editor is shared code, no behaviour
change for football).

---

## 3. Keyboard bindings (fresh table — `views/soccer_operator/keyboard.js`,
not a copy of football's `views/operator/keyboard.js`)

| Key | Action |
|---|---|
| `Space` | Game clock Start / Stop |
| `G` | Home goal — press once to arm, again to apply |
| `H` | Away goal — press once to arm, again to apply |
| `Q` | Period forward |
| `Shift+Q` | Period back |
| `A` / `Shift+A` | Home shots +1 / −1 |
| `S` / `Shift+S` | Home saves +1 / −1 |
| `D` / `Shift+D` | Home corners +1 / −1 |
| `F` / `Shift+F` | Home fouls +1 / −1 |
| `J` / `Shift+J` | Away shots +1 / −1 |
| `K` / `Shift+K` | Away saves +1 / −1 |
| `L` / `Shift+L` | Away corners +1 / −1 |
| `;` / `Shift+;` | Away fouls +1 / −1 |
| `Y` | Home yellow card — arms the card panel (§1.3) |
| `Shift+Y` | Away yellow card — arms the card panel |
| `R` | Home red card — arms the card panel |
| `Shift+R` | Away red card — arms the card panel |
| `T` | STOPPAGE (stop clock + raise the crowd word) |
| `Ctrl+Z` | Undo — opens the same confirmation as the button |
| `Escape` | Close dialog / drawer / disarm |
| `1` | Cutscene: GOAL (home) — see note below |
| `Shift+1` | Cutscene: GOAL (away) |

**Conflict check against the soccer cutscene key(s) proposed in §6.** `1`/
`Shift+1` are free letters not used by any binding above (football used
`D T O F L` for its five cutscenes; soccer's `D`, `F`, `T` are already
claimed by stat nudges and STOPPAGE above, so the GOAL cutscene trigger is
deliberately moved off the letter row to the number row to avoid a clash
— **OWNER CHOICE**, recommended default `1`/`Shift+1`, since soccer has
only one built-in cutscene in this pass (§6) versus football's five).

**OWNER CHOICE on card keys.** Recommended default above is a plain letter
for home, `Shift+`letter for away, exactly like the shots/saves/corners/
fouls +1/−1 pattern, rather than reusing Ctrl (already Undo) or Alt
(browser/OS reserved in many shells). `Y`/`R` are free: football does not
bind them (its `Y`/`R` do nothing today). No collision with football's
table since this is a wholly separate file (`views/soccer_operator/
keyboard.js`), loaded only by the soccer operator page.

No collisions exist between this table and football's `HOTKEY_TABLE`
(`host/hotkeys.py`, F15-F22): the button box is unchanged in soccer mode
per the owner's decision 5 (`FABLE_PROMPT.md` line 32) — F21/F22 still
start/stop the game clock, every other box key does nothing, and this
table adds no F-key bindings of its own.

---

## 4. Default soccer spectator layout (Scoreboard Grid derivative)

### 4.1 Widget registry (new, `SOCCER_WIDGET_IDS`, soccer's own `layout.py`
module beside football's, per the hard rule "new soccer modules beside the
football ones")

| id | Shows | Default visible |
|---|---|---|
| `home_name` / `away_name` | Team name | Yes |
| `home_score` / `away_score` | Score | Yes |
| `game_clock_value` (`game_clock_label` hidden) | Running/stopped clock | Yes |
| `period` | Period label (1ST HALF, HALF, 2ND HALF, OT1, OT2, SHOOTOUT, FINAL) | Yes |
| `home_shots` / `away_shots` | Shots | **No** |
| `home_saves` / `away_saves` | Saves | **No** |
| `home_corners` / `away_corners` | Corners | **No** |
| `home_fouls` / `away_fouls` | Fouls | **No** |
| `home_yellow` / `away_yellow` | Yellow cards | **No** |
| `home_red` / `away_red` | Red cards | **No** |
| `shootout_home` / `shootout_away` | Shootout tally row (made/attempted) | **No** (shown by the operator once a shootout starts, same manual-choice precedent as football's `home_timeouts`) |
| `status_message` / `status_clock` | Crowd message + countdown | Yes |

Sixteen optional widgets stay hidden by default so the default board stays
as clean as football's (`FABLE_PROMPT.md` line 141), exactly mirroring
football's `home_timeouts`/`away_timeouts`/`game_clock_label` precedent
(`UX_AND_LAYOUT.md` line 734).

### 4.2 Geometry (16:9 canvas, 4% safe area, Scoreboard Grid palette:
`#030A12` bg, `#071321` panels, `#F2F2F2` text, `#F5AE08` clock, banners
`#08439A`/`#A50021`; `bahnschrift_condensed` labels, `varsity` (Graduate)
digits, `fit_text: true` on names/scores/clock/period, following
`_grid_preset_layout` line 3433 conventions exactly)

| widget | x | y | width | height | font_scale |
|---|---|---|---|---|---|
| home_name | 0.04 | 0.09 | 0.28 | 0.11 | 0.07 |
| away_name | 0.68 | 0.09 | 0.28 | 0.11 | 0.07 |
| home_score | 0.04 | 0.225 | 0.28 | 0.33 | 0.30 |
| away_score | 0.68 | 0.225 | 0.28 | 0.33 | 0.30 |
| game_clock_value | 0.35 | 0.09 | 0.30 | 0.32 | 0.22 |
| period | 0.35 | 0.45 | 0.30 | 0.13 | 0.09 |
| status_message | 0.04 | 0.045 | 0.15 | 0.035 | 0.016 |
| status_clock | 0.195 | 0.045 | 0.08 | 0.035 | 0.016 |
| home_shots (hidden) | 0.045 | 0.625 | 0.13 | 0.09 | 0.046 |
| home_saves (hidden) | 0.185 | 0.625 | 0.13 | 0.09 | 0.046 |
| home_corners (hidden) | 0.045 | 0.72 | 0.13 | 0.09 | 0.046 |
| home_fouls (hidden) | 0.185 | 0.72 | 0.13 | 0.09 | 0.046 |
| home_yellow (hidden) | 0.045 | 0.815 | 0.13 | 0.075 | 0.04 |
| home_red (hidden) | 0.185 | 0.815 | 0.13 | 0.075 | 0.04 |
| away_shots/saves/corners/fouls/yellow/red | mirrored at x = 1 − (x+width) of the home equivalents | same y/h/scale | | | |
| shootout_home (hidden) | 0.35 | 0.60 | 0.30 | 0.10 | 0.045 |
| shootout_away (hidden) | 0.35 | 0.71 | 0.30 | 0.10 | 0.045 |

**Overlap check (only visible-by-default widgets participate; the hidden
stat/shootout widgets are excluded from the check per `layout.py`'s own
rule that hidden widgets are not validated for overlap, and because they
are never visible together with each other in a way that matters — the
operator turns on what they want):**

- home_name (0.04,0.09,0.28,0.11) vs home_score (0.04,0.225,0.28,0.33): y
  ranges [0.09,0.20] and [0.225,0.555] — no overlap.
- game_clock_value (0.35,0.09,0.30,0.32) vs period (0.35,0.45,0.30,0.13):
  y ranges [0.09,0.41] and [0.45,0.58] — no overlap (0.04 gap).
- home_score (0.04,0.225,0.28,0.33) vs game_clock_value (0.35,0.09,0.30,
  0.32): x ranges [0.04,0.32] and [0.35,0.65] — no overlap (0.03 gap).
- status_message (0.04,0.045,0.15,0.035) vs status_clock (0.195,0.045,
  0.08,0.035): x ranges [0.04,0.19] and [0.195,0.275] — no overlap.
- home_name vs status_message: y ranges [0.09,0.20] and [0.045,0.08] — no
  overlap (0.01 gap).

No pair of always-visible widgets intersects at all, so the 25%-of-
smaller-area rule (`SERIOUS_OVERLAP_RATIO`, `layout.py` line 112) is
satisfied trivially. When an operator turns on the optional stat row, it
sits below the timeouts row's y-band in football's own grid preset
(0.625-0.89), clear of the score (ends at 0.555) and the period band (ends
at 0.58) — no operator-chosen combination of the 16 optional widgets
overlaps `home_score`/`away_score`/`game_clock_value`/`period` because all
optional widgets start at y ≥ 0.60.

### 4.3 Drawn wireframe (visible-by-default set)

```
┌ 16:9 canvas, #030A12 bg, 4% safe area ─────────────────────────────────┐
│ [GOAL]        [1:00]                                                   │
│  EAGLES                              TIGERS                            │
│                                                                         │
│    1               45:00               0                               │
│                   1ST HALF                                             │
│                                                                         │
│         (optional stat/card/shootout rows, hidden by default)          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Pre-game (`KICKOFF IN`) and Halftime (`UNTIL SECOND HALF`) event
screens

Reuse the existing event-screen engine and `EVENT_WIDGET_IDS` registry
unchanged (`home_name`, `home_score`, `away_name`, `away_score`,
`event_phase`, `event_title`, `event_clock`, `warmup` — `layout.py` line
376). Only the wording differs (Python-supplied strings, never
JavaScript-authored, per 10.1/10.5 of `UX_AND_LAYOUT.md`):

```
Pre-game (Grid-style variant, ticker optional per §prompt):
┌─────────────────────────────────────────────────────────────────────┐
│                         KICKOFF IN                                   │
│                          25:00                                       │
│         EAGLES   0            vs            0   TIGERS               │
│   (optional ticker: "WELCOME TO TIGER STADIUM" -- OWNER CHOICE:      │
│    recommend OFF by default for soccer's first pass, since no        │
│    soccer-specific announcement copy has been drafted yet)           │
└─────────────────────────────────────────────────────────────────────┘

Halftime:
┌─────────────────────────────────────────────────────────────────────┐
│                       UNTIL SECOND HALF                               │
│                    HALFTIME   10:00                                   │
│         EAGLES   1            vs            0   TIGERS               │
│              Warmup follows: 3:00                                     │
└─────────────────────────────────────────────────────────────────────┘
```

Both use the Scoreboard Grid palette (banners `#08439A`/`#A50021`,
`#F5AE08` countdown, `bahnschrift_condensed`/`varsity`), matching
`_grid_event_screen` (referenced at `layout.py` line 3532) rather than
Broadcast Welcome's navy-crest look, because the owner's soccer request
did not ask for a rebrand — Broadcast Welcome's ticker/crest stay
**optional**, off by default (see above), reachable the same way football
reaches it (choose that preset in the layout editor).

---

## 5. Soccer Field Assistant window (1180×720, matching football's
`WindowHost` sizing convention, `UX_AND_LAYOUT.md` line 1105)

### 5.1 What it can and cannot do

Big per-team buttons: `SHOT`, `SAVE`, `CORNER`, `FOUL`, `YELLOW`, `RED`,
each with an optional player-number keypad (same inline-number idiom as
§1.3, reused here so the operator page and the assistant do not disagree
about how a card is recorded). A preview/confirm step exactly like
football's (`preview_field_action`/`finalize_field_action`,
`field_assistant.js` lines 369-405): pressing a big button asks Python for
a preview at once, and the Confirm button's own label states the result
(`CONFIRM → HOME SHOT #9 recorded`), never a separate "Preview" step.

**It must not be able to change the score or the clock.** — **OWNER
CHOICE, recommended default: GOAL stays operator-only**, exactly as the
prompt frames it (`FABLE_PROMPT.md` line 163). Rationale: football's own
Field Assistant already keeps score-affecting actions (touchdown, field
goal, safety) *inside* the assistant but always with the
`score_recorded`/`add_score` checkbox so a score entered on the main panel
is never double-counted (`field_assistant.js` lines 288-292); soccer's
prompt is more restrictive ("must not be able to change the score or the
clock unless the spec says so and I approve it"), so unlike football this
first pass omits scoring entirely from the assistant and leaves GOAL as a
main-operator-panel-only, cutscene-triggering action. This is a narrower
surface than football's assistant and is flagged for the owner to
confirm or loosen in the spec checkpoint.

Live sync via the same push path football's assistant uses
(`window.applyView`, 10 Hz host refresh, `field_assistant.js` line 581).

### 5.2 Wireframe — idle

```
┌ FIELD ASSISTANT   REV 42   GAME 45:00 STOPPED ── [Discard draft&reload]─┐
│                                                                          │
│   HOME — EAGLES                        AWAY — TIGERS                    │
│  [ SHOT ][ SAVE ]                     [ SHOT ][ SAVE ]                  │
│  [CORNER][ FOUL ]                     [CORNER][ FOUL ]                  │
│  [YELLOW][ RED  ]                     [YELLOW][ RED  ]                  │
│                                                                          │
│  Scoreboard now: EAGLES 1 · TIGERS 0 · 1ST HALF · 45:00 STOPPED         │
│  Shots 4-6 · Saves 2-3 · Corners 3-5 · Fouls 1-2 · Cards Y1-Y0          │
│                                                                          │
│  ┌ SHOOTOUT KICK LOG (shown only in period == SHOOTOUT) ─────────────┐ │
│  │ Round 1: HOME made(#9)   AWAY missed(#4)                          │ │
│  │ Round 2: HOME made(#7)   AWAY made(#11)                           │ │
│  │ [ HOME MADE ][ HOME MISSED ]   [ AWAY MADE ][ AWAY MISSED ]        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                       [ Cancel ]   [ CONFIRM ] (disabled)│
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Wireframe — stat pressed (preview state, e.g. HOME SHOT)

```
│  HOME — EAGLES                        AWAY — TIGERS                     │
│  [ SHOT*][ SAVE ]                     [ SHOT ][ SAVE ]                  │
│  [CORNER][ FOUL ]                     [CORNER][ FOUL ]                  │
│  [YELLOW][ RED  ]                     [YELLOW][ RED  ]                  │
│  Player # (optional): [ 9 ]  [ NO # ]                                   │
│                                                                          │
│  Scoreboard now: EAGLES 1 · TIGERS 0 · 1ST HALF · 45:00 STOPPED         │
│                                       [ Cancel ]  [CONFIRM → HOME SHOT] │
└──────────────────────────────────────────────────────────────────────────┘
```

`*` marks the pressed/selected button, same `aria-pressed`/highlighted-
button idiom football's assistant uses (`field_assistant.js`
`setPressed`).

### 5.4 Wireframe — YELLOW card pressed with number

```
│  [YELLOW*][ RED  ]     Player #: [ 9 ]  [ NO # ]                        │
│                                       [ Cancel ] [CONFIRM → HOME YELLOW │
│                                                    CARD #9]              │
```

### 5.5 Wireframe — SHOOTOUT state (the kick log panel replaces the field
column entirely once `period == "SHOOTOUT"`, the assistant has no field
drawing to show)

```
┌ FIELD ASSISTANT   REV 61   SHOOTOUT ── [Discard draft & reload]────────┐
│  HOME 5(2) — EAGLES               AWAY 5(1) — TIGERS      ROUND 3      │
│  Kicker # [ 9 ]                                                        │
│  [ HOME MADE ][ HOME MISSED ]     [ AWAY MADE ][ AWAY MISSED ]          │
│                                                                          │
│  Round 1: HOME made(#9)     AWAY missed(#4)                            │
│  Round 2: HOME made(#7)     AWAY made(#11)                             │
│  Round 3: HOME ?            AWAY ?                                     │
│                                       [ Cancel ]  [CONFIRM → HOME MADE] │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 6. GOAL cutscene

A built-in scene in the existing director/pack format
(`presentation/cutscenes.py` `CUTSCENE_EVENTS`, `host/cutscenes.py`
`CutsceneDirector`), registered in a **soccer-only** scene registry file —
per the hard rule, this lives at `views/soccer_spectator/cutscenes/` (or
equivalently a soccer-prefixed sibling of `views/spectator/cutscenes/
builtin.js`), never inside `builtin.js`/`tigers.js`/`crowd.js`, so the
existing test that scans every `*.js` under `views/spectator/cutscenes/`
and asserts exactly the five football ids keeps passing untouched
(`CONTEXT_FOR_AGENTS.md` line 75-76).

**Event id:** `goal`. **Duration:** 7 seconds (within the requested 6-8 s
window). **Headline:** `GOAL`. **Subline argument — flagged for the
owner:** the scoring team's name, taken from the live snapshot with an
explicit `home`/`away` argument at trigger time (`trigger_cutscene('goal',
{team: 'home'})` from the operator's armed-GOAL press, or the keyboard's
`1`/`Shift+1`), **not** a fixed school identity. This is a deliberate
departure from football, where every cutscene is unconditionally the home
team's (`views/cutscenes/index.html` lines 17-22: "there is no home/away
choice... the wall is the Tigers' wall... always theirs"). Soccer needs
the opposite: a visiting team's goal must celebrate the visiting team, not
be silently relabeled HOME. **This changes the cutscene trigger contract**
(one new required argument, `team`) versus football's argument-less
triggers, and is the one place this design draft asks the spec to record
a genuine architectural difference, not just new content — confirmed
against `FABLE_PROMPT.md`'s own text ("note this differs from football's
home-only rule and flag it for the owner").

Scene-file rules honoured exactly as football's are: no `http://`
anywhere in the file; all `innerHTML` assignments come from a single
`GOAL_MARKUP` constant (mirroring football's `CLAW_MARKUP` idiom,
`builtin.js` line 234); all dynamic text (team name) is set via
`textContent`, never concatenated into `innerHTML`; every delayed one-shot
animation (the net-ripple flash, the headline slide-in) runs forwards
only, using the director's existing tick/lock ordering
(`CONTEXT_FOR_AGENTS.md` line 73, "the director/tick lock-ordering trap");
no brand hex literals — colors come from the same CSS custom properties
football's scenes use.

```
┌ GOAL cutscene, 7 s, full-bleed spectator canvas ──────────────────────┐
│  t=0.0-0.6s   net-ripple flash sweeps in from goal-mouth (forward)     │
│  t=0.4-2.0s   headline "GOAL" slides up and holds, huge, centred       │
│  t=1.0-1.0    <team> name (from snapshot, home OR away) fades in below │
│               the headline via textContent, never innerHTML           │
│  t=2.0-6.5s   headline + team name hold; background colour keyed off   │
│               the scoring side (home/away), not a fixed school colour │
│  t=6.5-7.0s   fade out, hands control back to the director             │
└──────────────────────────────────────────────────────────────────────┘
```

Triggered from the soccer GOAL flow the same way football triggers its
scenes: the operator's confirmed `GOAL` press calls `trigger_cutscene`
immediately after the command is accepted (mirroring
`operator.js`'s `if (name === 'add_score')` handling, generalised to call
the host trigger on acceptance), and the operator retains the existing
`Shift+C`-style cancel-in-progress control from the Cutscenes window
(`views/cutscenes/index.html` line 27, `cancel_cutscene`), unchanged in
shape, wired to the soccer trigger set instead of football's five events.

---

## Summary of OWNER CHOICE items in this draft

1. §1.1/1.2 — shrink the team-panel score clamp and score-controls height
   to 44 px (from football's 52 px) to fit stat rows + cards in budget.
   *Recommended: yes, shrink; re-measure in the real runtime before ship.*
2. §1.3 — card entry: one-tap arm into the shared score-controls block
   with an optional typed number, `NO #`/`CONFIRM`/`✕`. *Recommended:
   yes, matching goal's arm-then-apply shape rather than a bare one-tap
   or a full drawer.*
3. §1.4 — a single atomic `STOPPAGE` button (stop clock + raise crowd
   word) instead of separate controls. *Recommended: yes.*
4. §1.7 — whether `GOAL` should be refused by the bridge during
   SHOOTOUT. *Recommended: yes, refuse it; flagged as an open command-list
   question, not decided here.*
5. §3 — GOAL cutscene keyboard binding on `1`/`Shift+1` rather than a
   letter, to avoid colliding with the stat-nudge letters. *Recommended:
   yes.*
6. §4.4 — Broadcast Welcome ticker/crest left OFF by default for soccer's
   first pass (no soccer announcement copy drafted yet), Scoreboard Grid
   styling used instead. *Recommended: yes, revisit once the owner wants
   soccer-specific ticker copy.*
7. §5.1 — GOAL stays operator-only; the Field Assistant cannot record a
   goal or touch the clock at all in this first pass, narrower than
   football's own assistant. *Recommended: yes, per the prompt's explicit
   restriction; revisit only if the owner approves loosening it.*
8. §6 — the GOAL cutscene subline argument is the scoring team from the
   live snapshot (`home`/`away`), a genuine departure from football's
   home-only rule. *Recommended: yes — flagged explicitly for the owner
   per the prompt's own instruction.*
