# Cutscenes v3 — spec (two more scenes: MAKE SOME NOISE and TURNOVER)

Status: active implementation spec (September 6, 2026). Three Fable 5.1 agents
build against disjoint file ownership (section 7). Where this spec is silent,
`.scratch/cutscenes-v2/spec.md` (v2) applies, and under it
`.scratch/cutscenes/spec.md` (v1). The house rules never change: **Python
owns every value, JavaScript copies**; strict validation with a plain-language
fallback; nothing fetched from a network; no optional window has a path to a
game command; a failure in any cutscene surface never reaches clocks,
persistence, or the operator's controls.

## 0. What the owner asked for (verbatim intent)

> implement 2 additional cut scenes. a "make some noise" cut scene that lasts
> about 5 seconds, and one of your choosing. … it needs to look like it was
> made in 2026, not the 2010s.

The orchestrator's choice for the second scene is **TURNOVER** — the Tigers
take the ball away. It is the defensive counterpart of TOUCHDOWN, it is a
real moment the crowd reacts to, and it earns the claw intro.

## 1. Design direction — read v2 section 1 first, then this

Everything in v2 §1 stands: 1920×1080 LED wall seen from bleachers; the
2023–2026 NFL broadcast-package language (hard diagonal slabs and chevrons
in team colours, one light sweep, staggered kinetic type revealed under a
moving mask, a crest that arrives with weight, one burst that opens and
settles, a calm readable hold for the last 40 %); depth (layered panels,
drop shadows, a 5–7 % hatch texture, a vignette); **nothing strobes and
nothing alternates colours quickly**. Palette only via `var(--cs-*)`
(`navy`, `navy-elevated`, `blue`, `red`, `blue-light`, `white`, `mist`,
`ink`, `gold`, `flag`) — no hex in a scene file; gold is an accent, never a
panel fill. Type: `'Bahnschrift', Impact, 'Arial Black', Arial, sans-serif`,
`font-weight: 700; font-stretch: 75%`, `skewX(-8deg)` on headline containers
(Bahnschrift is installed on this machine; check the condensed axis in a
screenshot). Every length is `calc(var(--stage-w) * f)` /
`calc(var(--stage-h) * f)`; nothing in `vw`/`vh`. Screenshot at 1920×1080
**and** at 640×360.

What "2026, not 2010" means in practice, so nobody ships clip art: no
centred word scaling up from nothing with a bounce; no even starburst of
thin rays; no drop shadow with a 45° offset; no rainbow; no beveled text.
Instead: asymmetric composition, slabs that overlap on a skewed seam, type
that is revealed (clip-path) not scaled, restrained motion after the first
1.5 s, one accent colour used sparingly, real texture and vignette.

The two new scenes must also look like *siblings* of the v2 `first_down`
and `touchdown` in `tigers.js`/`tigers.css` (same crest helper, same slab
language, same type stack) — read those two scenes before drawing a pixel.

## 2. Python — `presentation/cutscenes.py` and friends (Agent A)

### 2.1 Constants (exact names/values; other agents hard-code them)

```python
CUTSCENE_EVENTS = ("first_down", "touchdown", "turnover", "penalty", "make_some_noise")
EVENT_LABELS = {
    "first_down": "First down", "touchdown": "Touchdown", "turnover": "Turnover",
    "penalty": "Penalty", "make_some_noise": "Make some noise",
}
EVENT_HEADLINES = {
    "first_down": "FIRST DOWN", "touchdown": "TOUCHDOWN", "turnover": "TURNOVER",
    "penalty": "FLAG ON THE PLAY", "make_some_noise": "MAKE SOME NOISE",
}
EVENT_TEAM = {
    "first_down": "home", "touchdown": "home", "turnover": "home",
    "penalty": None, "make_some_noise": "home",
}
#: The subline under the headline, as a template. `{team}` is the home
#: team's name upper-cased (as given by the view, "" when absent); the
#: result is stripped so an empty name never leaves a leading space.
EVENT_SUBLINE = {
    "first_down": "{team}", "touchdown": "{team}", "turnover": "{team} BALL",
    "penalty": "PENALTY", "make_some_noise": "{team} FANS",
}
DEFAULT_DURATION_SECONDS = {
    "first_down": 7.0, "touchdown": 10.0, "turnover": 7.0,
    "penalty": 7.0, "make_some_noise": 5.0,
}
EVENT_DEFAULT_INTRO = {
    "first_down": "claw_scratch", "touchdown": "claw_scratch", "turnover": "claw_scratch",
    "penalty": "none", "make_some_noise": "none",
}
BUILTIN_SCENE_IDS = {
    "first_down": "first_down", "touchdown": "touchdown", "turnover": "turnover",
    "penalty": "penalty", "make_some_noise": "make_some_noise",
}
```

`INTRO_IDS`, `INTRO_DURATION_MS`, `THEME` (with `flag`), `STAGE`, `OUTRO`,
`MEDIA_EXTENSIONS`, `FIT_MODES`, `MIN/MAX`, `MANIFEST_SCHEMA_VERSION` are
unchanged from v2. Add `EVENT_SUBLINE` to `__all__`.

Why `make_some_noise` has no intro: at 5 s a 1.6 s claw strike would eat a
third of the scene, and a crowd prompt wants to be on the wall *now*.
Why `turnover` has the claw: a takeaway is the most Tigers thing a defence
can do.

### 2.2 `build_program` texts

`texts = {"headline", "subline", "team_name"}` as v2, with

```python
"subline": EVENT_SUBLINE[event].format(team="TIGERS")
```

so: first_down/touchdown → `TIGERS`, turnover → `TIGERS BALL`,
make_some_noise → `TIGERS FANS`, penalty → `PENALTY`. The word `TIGERS` is
fixed school branding, not the configurable home-team name; even a fresh
scoreboard whose normal label is `HOME` must render `TIGERS` here. Penalty
remains team-neutral with `team_name = ""`.

### 2.3 Host, bridge, packs

No signature changes. `CutsceneDirector.trigger(event)` accepts the two new
events because it checks `CUTSCENE_EVENTS`. `infrastructure/cutscene_packs.py`:
the README text lists all five events, says `intro` defaults per event
(`claw_scratch` for first_down/touchdown/turnover, `none` for penalty and
make_some_noise), and lists the five builtin scene ids.

### 2.4 Cutscenes window — `views/cutscenes/*`

Five big buttons in this order (ids, `data-event`, label, colours):

| id | data-event | label | background | border | text |
|---|---|---|---|---|---|
| `#trigger-first-down` | `first_down` | FIRST DOWN | `#17468C` | `#2C62AB` | white |
| `#trigger-touchdown` | `touchdown` | TOUCHDOWN | `#C8242B` | `#FFB703` | white |
| `#trigger-turnover` | `turnover` | TURNOVER | `#071B3A` | `#C8242B` | white |
| `#trigger-penalty` | `penalty` | PENALTY | `#FFD500` | `#FFB703` | `#030711` |
| `#trigger-make-some-noise` | `make_some_noise` | MAKE SOME NOISE | `#2C62AB` | `#FFB703` | white |

(Hex is fine in the *window's* CSS — it is operator UI, not the wall; the
wall's scenes still take colours only from `--cs-*`.) Five
`<select data-pack-for="…">`, `renderState` renders all five. Window hotkeys:
`D` first down, `T` touchdown, `O` turnover, `F` penalty, `L` make some
noise ("get Loud"), `Shift+C` cancel. The window stays `520x640` (min
`420x520`): drop `.trigger { min-height }` to `64px` and its font to `22px`
if needed so all five buttons **and** the collapsed Packs summary fit
without scrolling — prove it with a 520×640 Playwright screenshot of
`views/cutscenes/index.html` (stub `window.pywebview.api` with
`get_snapshot`/`state` returning minimal objects) and read the PNG.

### 2.5 Operator hotkeys — `views/operator/keyboard.js`

Exactly these six `host` bindings, in this order:

```js
{key: 'd', label: 'D', action: 'Cutscene: First down', host: 'trigger_cutscene', args: ['first_down']},
{key: 't', label: 'T', action: 'Cutscene: Touchdown', host: 'trigger_cutscene', args: ['touchdown']},
{key: 'o', label: 'O', action: 'Cutscene: Turnover', host: 'trigger_cutscene', args: ['turnover']},
{key: 'f', label: 'F', action: 'Cutscene: Penalty flag', host: 'trigger_cutscene', args: ['penalty']},
{key: 'l', label: 'L', action: 'Cutscene: Make some noise', host: 'trigger_cutscene', args: ['make_some_noise']},
{key: 'c', shift: true, label: 'Shift+C', action: 'Cancel cutscene', host: 'cancel_cutscene'}
```

`O` and `L` are free today (check the binding table; `N`/`M` are away
scores, `P`/`S` are the play clock). Update the pinned shortcut-help table
in `tests/ui/keyboard.cjs`.

### 2.6 Tests Agent A owns (update, never delete coverage)

- `tests/unit/test_cutscene_schema.py`: constants sanity net for five
  events (every per-event table covers exactly `CUTSCENE_EVENTS`;
  `EVENT_SUBLINE` present and in `__all__`; the exact durations/intros
  above); `build_program` sublines for turnover/make_some_noise with a
  named team and with an empty name; the mirror test already scans every
  `*.js` under `views/spectator/cutscenes/` — it now finds five ids plus
  `claw_scratch`.
- `tests/integration/test_cutscene_packs.py`, `test_cutscene_director.py`,
  `test_cutscene_bridge.py`: one case each that the two new events trigger,
  carry `team "home"`, and the right label/duration (mirror the existing
  penalty cases).
- `tests/integration/test_cutscenes_ui_contract.py`: five trigger buttons,
  five `data-pack-for`, the six bindings above (count of `trigger_cutscene`
  lines is 5), still no `data-team`.
- `tests/integration/test_cutscene_player_contract.py` and
  `tests/ui/cutscene_player.cjs` / `test_cutscene_player_browser.py`
  (Agent A owns these in v3 so the scene agents never touch a test the other
  one depends on): the spectator page loads `cutscene.css`,
  `cutscenes/tigers.css`, `cutscenes/crowd.css`, then `cutscenes/builtin.js`,
  `cutscenes/tigers.js`, `cutscenes/crowd.js`, `cutscene.js`, in that
  relative order after `spectator.js` (the orchestrator adds the two
  `crowd.*` lines to `index.html`; nobody else edits it). The scene-file
  source rules (every `innerHTML` right-hand side is an identifier ending
  in `_MARKUP`; words through `textContent`; no `#rrggbb`; none of `fetch(`,
  `XMLHttpRequest`, `api.command`, `pywebview`, `http://`, `https://`,
  `@import`, `new Image(`; the only `.src =` assignment names
  `cutscenes/tmsa-logo.png`) apply to **all three** scene files; the CSS
  rules (`--stage-w`/`--stage-h`, no `vw`/`vh`, no `@import`, no
  `@font-face`, no `url(http`) apply to `crowd.css` too. Registration:
  `builtin.js` → `claw_scratch`, `penalty`; `tigers.js` → `first_down`,
  `touchdown`, `turnover`; `crowd.js` → `make_some_noise`. In the browser
  test, `ScoreboardCutsceneScenes.ids()` is exactly
  `['claw_scratch', 'penalty', 'first_down', 'touchdown', 'turnover', 'make_some_noise']`
  (registration order = load order), and add one case: a `make_some_noise`
  program with `intro: {id: 'none', duration_ms: 0}` mounts
  `[data-scene="make_some_noise"]` immediately with the override layout up,
  and its `.cs-mn-headline span` text is the program's headline verbatim.
  Keep every ending-path assertion. Run the browser test at the very end of
  your work, after B and C have landed (their files are what it exercises);
  if it fails only because a scene is still missing, say so in your report
  rather than weakening the test.
- `tests/README.md` rows for every file above: edit in place.
- `tools/build_package.py`: add `cutscenes/crowd.js` and `cutscenes/crowd.css`
  to `REQUIRED_FILES` next to the `tigers.*` entries (v2 added those and the
  `*.png` pattern in `pyproject.toml`; nothing else to do there).

What the v2 versions of these tests pin today, so you extend rather than
re-derive (read them first):

- `test_cutscene_player_contract.py` has a per-file table
  `SCENE_IDS = {BUILTIN_JS: ("claw_scratch", "penalty"), TIGERS_JS: ("first_down", "touchdown")}`
  and checks every scene-file rule over that table; `SceneCssTests` runs
  over `(CUTSCENE_CSS, TIGERS_CSS)`. Add `CROWD_JS`/`CROWD_CSS`, put
  `"turnover"` under `TIGERS_JS` and `("make_some_noise",)` under
  `CROWD_JS`, and add `CROWD_CSS` to the CSS table. The
  `test_the_logo_is_the_only_thing_any_scene_loads` test currently says only
  `tigers.js` names the crest: relax it to "every `.src =` in any scene file
  names `cutscenes/tmsa-logo.png`" and assert both `tigers.js` and
  `crowd.js` contain the literal (the crowd scene shows the crest too).
  Also extend the index.html load-order test to the two `crowd.*` lines.
- `tests/ui/cutscene_player.cjs` asserts `ScoreboardCutsceneScenes.ids()`
  equals `['claw_scratch', 'penalty', 'first_down', 'touchdown']` and that
  `Object.keys(helpers).sort()` is `['addText', 'sceneRoot', 'simpleScene', 'textOf']`;
  its check 7 is the no-intro penalty case — model the new
  `make_some_noise` case on it (it may be check 8, appended to the pinned
  list in `test_cutscene_player_browser.py`).
- `test_cutscene_schema.py`'s mirror test already scans every `*.js` under
  `views/spectator/cutscenes/`.

Test commands (PowerShell, from the repo root; `node` is **not on PATH in
either shell** — prepend it as below before anything that runs Playwright):

```powershell
$env:PATH = "C:\Program Files
odejs;$env:PATH"
$env:SCOREBOARD_DATA_DIR = "$env:TEMP\scoreboard-tests-v3"
.\.venv\Scripts\python.exe -m unittest tests.unit.test_cutscene_schema tests.integration.test_cutscene_packs tests.integration.test_cutscene_director tests.integration.test_cutscene_bridge tests.integration.test_cutscenes_window tests.integration.test_cutscenes_ui_contract tests.integration.test_cutscene_player_contract tests.ui.test_cutscene_player_browser tests.ui.test_keyboard_browser tests.integration.test_spectator_layout_render -v
```

### 2.7 Docs Agent A owns

`docs/UX_AND_LAYOUT.md` §12 (five events, keys D/T/O/F/L/Shift+C, the 5 s
crowd prompt with no intro, the turnover with the claw, the sublines),
`docs/ARCHITECTURE.md` cutscene paragraphs (five events, `EVENT_SUBLINE`),
`docs/PROJECT_STRUCTURE.md` (`cutscenes/crowd.js`, `crowd.css`),
`PROJECT_ROADMAP.md` (a short "Cutscenes v3 — MAKE SOME NOISE and TURNOVER,
September 6, 2026" entry under the v2 one; leave `## Next Action` alone),
the packs README text in `cutscene_packs.py`. Run
`.\.venv\Scripts\python.exe tools\check_markdown_links.py`.

## 3. `turnover` — `views/spectator/cutscenes/tigers.js` + `tigers.css` (Agent B)

Register with a literal `register('turnover', …)` call, root
`data-scene="turnover"`, class `cs-turnover`, headline box class
`cs-to-headline`, subline `cs-to-subline`. Reuse the file's existing
helpers (`h.simpleScene`, `h.addText`, `h.textOf`, `addBox`,
`setStageLength`, `sequence`/`spread`, `addCrest`). Words only from
`program.texts.headline` (`TURNOVER`), `.subline` (`TIGERS BALL`). 7 s
total: claw intro 1600 ms (v2's, unchanged), scene 5400 ms including the
player's 600 ms outro.

The idea: **possession flips.** The one image that says "turnover" on a
broadcast is the possession arrow reversing.

| t (ms, from scene mount) | What |
|---|---|
| 0–450 | Background `--cs-navy` → `--cs-ink` with the hatch and vignette. A **chevron train** — six large `--cs-blue-light` chevrons (`>`) in a row across the middle third, drawn with `clip-path` polygons, pointing right — rushes in from the left. |
| 450–600 | The **flip**: the train snaps to `--cs-red` chevrons pointing left (`scaleX(-1)` on the row, a 120 ms `--cs-white` flash line through the row that decays, a heavier one-off 1 % camera shake on the root). From here the chevrons march steadily left through the hold at ~20 % opacity behind the type. This is the turnover moment; make it hit. |
| 350–800 | A `--cs-ink` shadow slab then a `--cs-red` slab slam in from the **right** (the mirror of first_down's left entry), skewed −12°, across the upper 55 % of the stage; a thin `--cs-blue` slab slides under it from the left. |
| 300–950 | A **football** (inline SVG constant `FOOTBALL_MARKUP`: a prolate ellipse in `--cs-ink` with a `--cs-white` lace line and two end stripes — no operator text) tumbles from off-stage right to the left third along a shallow arc, spinning ~720°, with a `--cs-red` motion trail (two ghost copies at 35 %/15 %), and **lands** at ~950 ms with a small bounce and eight `--cs-gold` sparks that fly out once and fade by 1500 ms. |
| 700–1300 | Headline `TURNOVER` wipes in **right→left** under a moving `clip-path` inset (the reverse of the other scenes' left→right, matching the flip), one text node, ~30 % of stage height, white, `--cs-ink` extrude (stacked text-shadows), `--cs-red` `-webkit-text-stroke`. One light sweep across it at ~1400 ms. |
| 1100–1700 | The **crest** (`addCrest`, 0.26) drops in at the lower left beside the ball; the subline `TIGERS BALL` slides in on a `--cs-ink` tag to its right, tracked +0.2 em, in `--cs-gold` (the one accent use). |
| 1700–4800 | Hold: chevrons drift left, the ball rocks ±2° slowly, the slabs drift 1 % apart. The word never moves after it lands. |
| 4800–5400 | The player's outro fade; nothing to do. |

Practice-window check (640×360): the ball and the crest must still read;
filter radii scale from `--stage-w`.

## 4. `make_some_noise` — `views/spectator/cutscenes/crowd.js` + `crowd.css` (Agent C)

New files (both exist as placeholders written by the orchestrator; replace
their contents). `crowd.js` is an IIFE in exactly the shape of `tigers.js`:
`var registry = window.ScoreboardCutsceneScenes; if (!registry) return; var
h = registry.helpers || localHelpers;` with the four local helper copies
(`sceneRoot`, `addText`, `textOf`, `simpleScene`) under the same names, plus
its own `addBox`/`setStageLength`/`sequence`/`spread` copies, and its own
`addCrest` (copy `tigers.js`'s crest builder and its crop constants
verbatim — the crest must look identical across scenes; the `<img>` is
created with `createElement('img')`, `alt=''`,
`src = 'cutscenes/tmsa-logo.png'`). Register with a literal
`register('make_some_noise', …)`, root `data-scene="make_some_noise"`, class
`cs-noise`, headline box `cs-mn-headline`, subline `cs-mn-subline`. Only
static `*_MARKUP` constants may be assigned to `innerHTML`.

5 s total, **no intro**: the stage appears at t = 0 while the board morphs to
the bar underneath (600 ms), so the first 300 ms must already look
intentional (the slabs are landing) rather than empty.

The idea: **a live level meter.** The wall is telling the crowd it is
listening.

| t (ms) | What |
|---|---|
| 0–350 | Background `--cs-navy` → `--cs-ink`, hatch, vignette. A `--cs-red` slab (skew −12°) slams in from the left over an ink shadow slab, covering the left ~58 %; a `--cs-blue` slab slides in from the right under it, covering the right ~42 %. |
| 0–4400 | **Bass rings**: three thin `--cs-white` rings (border only) expand from behind the word, one every 500 ms (120 BPM), each scaling .3→1.7 over 900 ms while its opacity falls smoothly .28→0. Looping. Soft, never a flash. |
| 250–1000 | Headline `MAKE SOME NOISE` as **one text node** inside a fixed-width box on the red slab so it wraps to three lines (`MAKE` / `SOME` / `NOISE`) — CSS does the breaking (`width` chosen so two words never fit on a line; `text-wrap: balance`); each line ~20 % of stage height, italic condensed, white with `--cs-ink` extrude. Reveal with a moving `clip-path` inset top→bottom so the lines arrive in order. One light sweep at ~1300 ms. |
| 1000–4400 | The word **punches** on the beat: `scale(1)→(1.035)→(1)` over 500 ms, ease-out, looping — felt, not seen. |
| 500–4400 | The **meter** on the blue slab: 12 vertical bars, each a `--cs-blue-light`→`--cs-white` gradient with a `--cs-gold` peak cap, each with its own bounce keyframes (height 15 %↔95 % of the meter box, periods 380–720 ms, delays from `sequence(seed)`), caps falling slower than the bars. Big, chunky, readable from the bleachers; it should read as a live audio meter reacting to the crowd. |
| 900–1400 | Subline `TIGERS FANS` on a `--cs-ink` tag under the word, tracked +0.2 em, `--cs-mist`; the crest (0.22) at the lower left of the red slab, arriving with weight. |
| 1400–4400 | Hold: rings, meter, punch continue; nothing else moves. |
| 4400–5000 | The player's outro; nothing to do. |

Rules: no colour cycling, no full-stage flash; the meter and rings are the
only continuous motion. At 640×360 the three words and the meter must still
read; the crest stays ≥ 18 % of stage height.

## 5. Verification every scene agent (B and C) must do — this is the deliverable

A scene that was never looked at is not done. Loop at least three times:

1. Build a capture script in **your own scratch folder** from
   `C:\Users\505gr\AppData\Local\Temp\claude\C--Users-505gr-OneDrive-Desktop-Scoreboard\4da59d16-9985-4bc4-9a98-7235cd6d0580\scratchpad\preview\capture_scenes.cjs`
   and `make_stub.py` (same folder; it writes `__stub_programs.js` with
   v3 programs for all five events against the real Broadcast preset — run
   it with `.\.venv\Scripts\python.exe make_stub.py <your out dir>`).
   Playwright is local:
   `require('C:/Users/505gr/OneDrive/Desktop/Scoreboard/node_modules/playwright')`,
   `chromium.launch({channel: 'msedge', headless: true})`. Load the page
   from `file://`, stub `window.pywebview.api` exactly as the script does.
   **Run node from PowerShell** (`& "C:\Program Files\nodejs\node.exe" …`);
   Git Bash does not have it on PATH.
2. Screenshot **frames**, not one frame: ~6 moments (e.g. 150, 450, 900,
   1500, 3000, 4400 ms after `applyCutscene` — for `turnover` add 1600 to
   skip the intro, and also grab one intro frame) at 1920×1080, plus two
   frames at 640×360. Name them by scene and ms.
3. **Read the PNGs** (the Read tool renders images) and judge them against
   section 1. Write down what is weak, fix it, capture again. Do not stop
   at "it renders".
4. Run the contract tests you can (section 2.6's command minus the browser
   test, or with it — it may fail on the other agent's not-yet-landed scene;
   say so).

Put nothing under `src/scoreboard/views` that is not shipped code (no stub
file in the views tree).

## 6. What the orchestrator does

Adds the two `crowd.*` lines to `views/spectator/index.html`, writes the
placeholder `crowd.js`/`crowd.css`, provides `make_stub.py`, runs the full
suite, the real pywebview harness (all five events from the operator
keyboard and the window), and reviews the diff.

## 7. File ownership (disjoint; do not edit files you do not own)

| Agent | Owns |
|---|---|
| A (Fable 5.1, "python + window + keyboard + tests + docs") | `src/scoreboard/presentation/cutscenes.py`, `src/scoreboard/infrastructure/cutscene_packs.py`, `src/scoreboard/host/cutscenes.py` (only if needed), `src/scoreboard/host/bridge.py` (only if needed), `src/scoreboard/views/cutscenes/*`, `src/scoreboard/views/operator/keyboard.js`, every test file named in §2.6, `tests/README.md`, `tools/build_package.py`, `docs/*.md`, `PROJECT_ROADMAP.md`, `AGENTS.md` (test count only if known) |
| B (Fable 5.1, "turnover") | `src/scoreboard/views/spectator/cutscenes/tigers.js`, `tigers.css` |
| C (Fable 5.1, "make some noise") | `src/scoreboard/views/spectator/cutscenes/crowd.js`, `crowd.css` |

`src/scoreboard/views/spectator/index.html`, `cutscene.js`, `cutscene.css`,
`cutscenes/builtin.js`, `tmsa-logo.png` are owned by nobody this round: do
not edit them. If one of them blocks you, say exactly what in your report.
