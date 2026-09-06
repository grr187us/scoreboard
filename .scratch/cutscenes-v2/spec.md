# Cutscenes v2 — spec (home-only, redesigned graphics, penalty flag)

Status: active implementation spec (September 6, 2026). Three Opus agents
build against disjoint file ownership (section 9). Where this spec is silent,
`.scratch/cutscenes/spec.md` (v1) still applies, and so do its house rules:
Python owns every value, JavaScript copies; strict validation with a
plain-language fallback; nothing fetched from a network; no optional window
has a path to a game command; a failure in any cutscene surface never reaches
clocks, persistence, or the operator's controls.

## 0. What the owner asked for (verbatim intent)

1. Cutscenes are **always for the Tigers (home)**, never the away team.
   Remove the home/away choice everywhere (window, hotkeys, API).
2. The **claw strike intro "looks pretty lame"** — make it look cool.
3. The **touchdown scene "looks like 2010 PowerPoint clip art"**; the first
   down is no better. Redesign both with **TMSA colours and the TMSA logo**.
   Broadcast-package quality, not clip art.
4. **Drop the score** from the touchdown scene. The score stays on the
   Broadcast bar under the stage (it already does; nothing to do there).
5. **Add a penalty cutscene**: "flag on the play", team-agnostic, about 7 s.

## 1. Design direction (read this before writing a single keyframe)

The wall is a 1920×1080 LED board seen from bleachers. Reference language is
the modern NFL broadcast package (Fox/ESPN 2023–2026): **hard diagonal slabs
and chevrons in team colours**, a **light sweep** across type, **staggered
kinetic type** (letters or words wiping/sliding in under a mask, not a whole
word scaling from nothing), **a crest/logo that arrives with weight**, a
**burst moment** (confetti, sparks, rays) that opens once and settles, and a
**calm readable hold** for the last 40 % of the scene. Everything has depth:
layered panels with drop shadows, a subtle carbon/stripe texture, a vignette.
Nothing strobes. Nothing alternates colours quickly (brand README rule).

Palette (`program.theme`, published as `--cs-*` custom properties):
navy `#071B3A`, navy_elevated `#0D2B5A`, blue `#17468C`, red `#C8242B`,
blue_light `#2C62AB`, white, mist `#DDE7F4`, ink `#030711`, gold `#FFB703`,
and new **flag `#FFD500`** (penalty yellow). No hex in a scene file — only
`var(--cs-…)`. Gold is an accent (rules, sweeps), never a panel fill.

Type: system fonts only (nothing is loaded). Headline stack, in this order:
`'Bahnschrift', Impact, 'Arial Black', Arial, sans-serif` with
`font-weight: 700; font-stretch: 75%` (Bahnschrift is a variable font on
Windows 10/11 and honours `font-stretch`; Impact/Arial Black are the fallback
on a machine without it). Verify in a screenshot that the condensed axis is
in effect; if Bahnschrift renders wide, drop to Impact. Italic (`skewX(-8deg)`
on the container) reads "sport" — use it on headlines.

Logo: `views/spectator/cutscenes/tmsa-logo.png` (218×174, the official
reference: blue tiger head over a red `TMSA` wordmark on white, with a blue
triangle at the left edge and a red diagonal bar at the right edge). Show it
**inside a crest**: a white rounded-rectangle or shield panel, with the image
positioned/scaled by CSS so only the tiger head + `TMSA` show (crop the edge
bars with `overflow: hidden` and `object-position`; measure the crop in a
screenshot). Give the crest a navy inner stroke and a soft drop shadow. It is
a low-resolution raster, so keep it at most ~30 % of stage height and let a
`filter: drop-shadow(...)` soften the edge. Never stretch it. Load it with a
plain `<img>` whose `src` is the page-relative path `cutscenes/tmsa-logo.png`
(the spectator page is served from `file:///…/views/spectator/index.html`,
and a page-relative subresource is exactly what WebView2 allows).

Sizing: every length is `calc(var(--stage-w) * f)` / `calc(var(--stage-h) * f)`
(the player publishes both in px). Nothing in `vw`/`vh`. Screenshot at
1920×1080 **and** at 640×360 (the practice window); both must read.

## 2. Python — `presentation/cutscenes.py` and friends (Agent A)

### 2.1 Constants (exact names/values; other agents hard-code them)

```python
CUTSCENE_EVENTS = ("first_down", "touchdown", "penalty")
EVENT_LABELS = {"first_down": "First down", "touchdown": "Touchdown", "penalty": "Penalty"}
EVENT_HEADLINES = {"first_down": "FIRST DOWN", "touchdown": "TOUCHDOWN", "penalty": "FLAG ON THE PLAY"}
#: The side a cutscene is for. Always the home team (the Tigers); a penalty
#: is nobody's -- it only says a flag is down.
EVENT_TEAM = {"first_down": "home", "touchdown": "home", "penalty": None}
DEFAULT_DURATION_SECONDS = {"first_down": 7.0, "touchdown": 10.0, "penalty": 7.0}
INTRO_IDS = ("claw_scratch", "none")
INTRO_DURATION_MS = {"claw_scratch": 1600, "none": 0}
#: The intro each event's built-in pack uses, and the manifest default when
#: a pack omits `intro`: the claws are Tigers-branded, a flag is not.
EVENT_DEFAULT_INTRO = {"first_down": "claw_scratch", "touchdown": "claw_scratch", "penalty": "none"}
BUILTIN_SCENE_IDS = {"first_down": "first_down", "touchdown": "touchdown", "penalty": "penalty"}
THEME = {... v1 keys unchanged ..., "flag": "#FFD500"}
```

Removed: `EVENT_DEFAULT_TEAM`, `TEAM_SIDES` (and from `__all__`). Everything
else in 2.1 of v1 (STAGE, OUTRO, MEDIA_EXTENSIONS, FIT_MODES, MIN/MAX,
MANIFEST_SCHEMA_VERSION) is unchanged.

### 2.2 Manifest validation

Unchanged except: `intro` missing → `EVENT_DEFAULT_INTRO[event]` (not a
fixed `"claw_scratch"`); `event` may be `"penalty"`; a builtin scene id may
be `"penalty"`. `builtin_pack(event)` uses `EVENT_DEFAULT_INTRO[event]`.

### 2.3 `build_program` — no `team` parameter

```python
def build_program(*, play_id, event, pack, spectator_view, layout) -> dict
```

- `program["team"]` = `EVENT_TEAM[event]` (`"home"` or `None`).
- `texts` = `{"headline", "subline", "team_name"}` — **`score` is gone**.
  For a home event: `team_name = "Tigers"` regardless of the configurable
  scoreboard home-team name, and `subline = "TIGERS"`. This prevents the
  default scoreboard label `HOME` from leaking into permanent school
  graphics. For `penalty`:
  `team_name = ""`, `subline = "PENALTY"`.
- Everything else (stage, layout copy renamed `"Cutscene"`, intro/outro
  inside the duration, media `fallback`) unchanged.

`event_descriptors()`: the `default_team` key becomes `team` (`"home"`/`None`).

### 2.4 Host and bridge

- `CutsceneDirector.trigger(event)` — the `team` parameter is removed.
  Unknown event → `{"ok": False, "message": ...}` as before. The
  `CUTSCENE_STARTED` note keeps its `team=program["team"]` field.
- `CutscenesBridge.trigger(event)`; `ScoreboardBridge.trigger_cutscene(event)`.
- `status()` keeps its `team` key (copied from the program).
- `infrastructure/cutscene_packs.py`: the README text written into the
  `cutscenes` folder lists all three events and says `intro` may be
  `"claw_scratch"` or `"none"` and defaults per event (penalty → none).
  Everything else unchanged.

### 2.5 Cutscenes window — `views/cutscenes/*`

- **Delete the team row** (`#team-home`/`#team-away`, `selectedTeam`,
  `teamExplicit`, `fillTeamNames`). `render` still copies `model.cutscenes`.
- Three big buttons, in this order: `#trigger-first-down`
  (`data-event="first_down"`, blue), `#trigger-touchdown`
  (`data-event="touchdown"`, red), `#trigger-penalty`
  (`data-event="penalty"`, label `PENALTY`, background `#FFD500`, ink text,
  border gold). Each calls `api.trigger(event)`.
- Packs: a third `<select data-pack-for="penalty">`; `renderState` renders
  all three.
- Window hotkeys: `D` first down, `T` touchdown, `F` penalty, `Shift+C`
  cancel. `Shift+T` is gone.
- Everything else in v1 §7.1 (status line copied from
  `playing.remaining_display`, `window.applyView`, `pywebviewready` on
  `window`, no command path) unchanged.

### 2.6 Operator hotkeys — `views/operator/keyboard.js`

Replace the four cutscene bindings with exactly:

```js
{key: 'd', label: 'D', action: 'Cutscene: First down', host: 'trigger_cutscene', args: ['first_down']},
{key: 't', label: 'T', action: 'Cutscene: Touchdown', host: 'trigger_cutscene', args: ['touchdown']},
{key: 'f', label: 'F', action: 'Cutscene: Penalty flag', host: 'trigger_cutscene', args: ['penalty']},
{key: 'c', shift: true, label: 'Shift+C', action: 'Cancel cutscene', host: 'cancel_cutscene'}
```

`F` is free today (check `keyboard.js`; `P` is taken). Update
`tests/ui/keyboard.cjs`'s pinned table and any binding count.

### 2.7 Tests Agent A owns (update, do not delete coverage)

`tests/unit/test_cutscene_schema.py` (constants sanity net; `build_program`
without `team`; penalty texts; the **mirror test now scans every `*.js` file
in `views/spectator/cutscenes/`** for `register('<id>'` for `claw_scratch`
and every `BUILTIN_SCENE_IDS` value — the scenes live in two files now),
`tests/integration/test_cutscene_packs.py`, `test_cutscene_director.py`
(no team argument; penalty program has `team None`),
`test_cutscene_bridge.py`, `test_cutscenes_window.py`,
`test_cutscenes_ui_contract.py` (three trigger buttons, **no** team
toggles — assert `data-team` is absent, three `data-pack-for`, the four
bindings above), `tests/ui/keyboard.cjs`, `test_keyboard_source.py` if it
pins anything. Rows in `tests/README.md` for these files: edit in place.

### 2.8 Docs Agent A owns

`docs/UX_AND_LAYOUT.md` §12 (home-only, three events, keys D/T/F/Shift+C,
penalty timeline has no claw intro, the touchdown shows no score),
`docs/ARCHITECTURE.md` cutscene paragraphs (three events, `EVENT_TEAM`),
`docs/PROJECT_STRUCTURE.md` (`cutscenes/tigers.js`, `tigers.css`,
`tmsa-logo.png`), `PROJECT_ROADMAP.md` (a short "Cutscenes v2 — graphics
redesign, home-only, penalty flag, September 6, 2026" entry under the v1
one; leave the `## Next Action` line for the orchestrator to finalize),
`AGENTS.md` test count only if you know the final number (else leave it).
Run `tools/check_markdown_links.py`.

## 3. Player — `views/spectator/cutscene.js` (Agent B)

Mostly unchanged. Required:

- `applyTheme` publishes `--cs-flag` too (add `'flag'` to the names list).
- The intro for a **fresh** program is 1600 ms now (from the program; the
  player never hard-codes it). `MORPH_AT_FRACTION` may move (0.45–0.55 reads
  best when the tears "rip open" onto the bar underneath — see 4.1); pick by
  screenshot.
- Keep the resume/replace/safety-net behaviour and the `state()` seam
  exactly as v1 §6.2. Keep the spectator-page load order:
  `render.js`, `board.js`, `spectator.js`, `cutscenes/builtin.js`,
  `cutscenes/tigers.js`, `cutscene.js` (the orchestrator already added the
  two `tigers.*` lines to `index.html`; do not reorder them).

## 4. Intro and penalty — `views/spectator/cutscenes/builtin.js` + `cutscene.css` (Agent B)

`builtin.js` keeps the registry (`ScoreboardCutsceneScenes`), the helpers
(`sceneRoot`, `addText`, `simpleScene`, `textOf`), **`claw_scratch`**, and
the new **`penalty`**. **Remove `first_down` and `touchdown` from this file
and their CSS from `cutscene.css`** — they move to Agent C's `tigers.js` /
`tigers.css`. Expose the helpers for Agent C on the registry object:
`ScoreboardCutsceneScenes.helpers = { sceneRoot, addText, textOf, simpleScene }`
(Agent C hard-codes these four names).

### 4.1 `claw_scratch` — 1600 ms, full canvas, over any board

What is wrong today: four thin, evenly spaced, identical curved strokes with
a soft red glow. They read as neon streaks, not as something that hit the
board. Make it read as a **strike**:

| t (ms) | What |
|---|---|
| 0–120 | A dark **paw silhouette** (inline SVG: a rounded pad + four toes with unsheathed claws, drawn as one filled path; no operator text) swipes diagonally from upper-left off-canvas to lower-right off-canvas in ~180 ms with a `blur()` motion trail (two ghost copies at 35 %/15 % opacity offset back along the path). It should be large: ~55 % of canvas height. |
| 60–380 | Four **gouges** appear in the paw's wake, staggered ~60 ms, **not** evenly spaced (spacing 11 %, 9 %, 13 % of width) and **not** identical (different lengths, one shorter and one that starts later). Each gouge is a **filled tapered wedge**, not a stroke: an SVG path shaped like a torn slit — pointed at both ends, widest a third of the way in, with a jagged inner edge (5–7 small notches). Draw it on with a `clip-path`/`mask` wipe along its own length (or `stroke-dasharray` on a thick path plus the filled shape behind it), so it *tears* rather than fades in. Fill: a white-hot core that decays within ~250 ms to a **glowing red rip** (`--cs-red` → `--cs-gold` inner gradient, as if light is behind the board), with a 1–2 px `--cs-ink` outline so it reads on a bright board. |
| 60 | One **impact flash**: the whole stage goes white at 45 % opacity and decays over 140 ms. Once only. Plus a heavier, shorter `#canvas` shake (amplitude ~1.2 %, 360 ms, `.shake` class — keep the class name; the player removes it). |
| 60–700 | **Debris**: 14–20 small fragments (navy/white/red rectangles and triangles, `--cs-*` only) flung from the gouges along the swipe direction, each with its own transform keyframes (`translate` + `rotate`), fading by 700 ms. |
| ~45 % (the player's `MORPH_AT_FRACTION`) | The board underneath morphs to the bar; from here the gouges **widen** slightly (scaleY 1 → 1.35 about their own axis) and their red glow brightens, as if the strike opened the board to the scene behind it. |
| 1100–1600 | The gouges and the dim wash fade out together, ending exactly at `program.intro.duration_ms` (read it from the program as today via `--cs-intro-ms`). |

Rules: the `.intro` stage keeps a dim wash (`rgba(3,7,17,.28)`) so a white
core reads on any board. Only one innerHTML assignment per static markup
constant (see 4.3). The paw and gouge shapes are static SVG strings with no
operator text. It must look right over the default game board and over the
pregame screen (the capture helper shows both).

### 4.2 `penalty` — 7 s, team-agnostic, on the stage over the bar, no intro

Nobody's colours but the flag's. Composition:

| t (ms) | What |
|---|---|
| 0–700 | The **flag** (inline SVG: a yellow cloth — a wavy quadrilateral with 2–3 fold lines in a darker yellow, plus a small weighted knot — `--cs-flag` and `--cs-ink` only) is thrown in from upper-left off-stage: an arc (`translate` keyframes with a parabola), spinning ~540°, scaling from 0.6 to 1, and **lands** at ~700 ms at 30 % from the left, 60 % down, with a small bounce and a dust puff (3 soft ellipses fading). |
| 350–900 | Two **diagonal yellow slabs** (`--cs-flag`) slide in from the right, one behind the other with a `--cs-ink` shadow gap, forming the panel the words sit on; a thin white rule sweeps under them. |
| 650–1200 | Headline `program.texts.headline` (`FLAG ON THE PLAY`) in `--cs-ink` on the yellow slab, **two lines** (`FLAG` huge, `ON THE PLAY` below in condensed caps) — split on the first space in JS is *not* allowed (that is formatting); instead render `headline` as one text node and let CSS wrap it inside a fixed-width box with `text-wrap: balance` and a large first-word via `::first-line` sizing. `subline` (`PENALTY`) as a small ink tag above the slab. |
| 1200–5500 | Hold. The flag's shadow breathes very slowly; a diagonal hatch texture at 6 % opacity drifts on the navy background. |
| 5500–7000 | Outro is the player's fade (600 ms inside the duration); nothing to do. |

Background: `--cs-navy` to `--cs-ink` radial vignette. No red, no blue
panels — the flag must not look like either team's graphic.

### 4.3 Contract rules Agent B keeps and re-pins in `test_cutscene_player_contract.py`

- The spectator page loads `cutscene.css`, `cutscenes/tigers.css`,
  `cutscenes/builtin.js`, `cutscenes/tigers.js`, `cutscene.js`, in that
  order relative to each other and after `spectator.js`.
- Scene files: every `innerHTML` assignment's right-hand side is an
  identifier ending in `_MARKUP` (regex over `builtin.js` **and**
  `tigers.js`); every word comes through `textContent`; no `#rrggbb`; none
  of `fetch(`, `XMLHttpRequest`, `api.command`, `pywebview`, `http://`,
  `https://`, `@import`, `new Image(`. An `<img>` created with
  `createElement('img')` whose `src` is `cutscenes/tmsa-logo.png` is
  **allowed** (assert the literal path appears in `tigers.js` and that no
  other `.src =` assignment in either scene file names anything else).
- `cutscene.css` and `tigers.css`: `--stage-w`/`--stage-h` sizing, no
  `vw`/`vh`, no `@import`, no `@font-face`, no `url(http`; a
  `url(cutscenes/…)` is allowed.
- `builtin.js` registers `claw_scratch` and `penalty`; `tigers.js`
  registers `first_down` and `touchdown` (literal `register('…'` calls).
- `cutscene.js` publishes `--cs-flag`.

### 4.4 Browser test — `tests/ui/cutscene_player.cjs` + `test_cutscene_player_browser.py`

Update the fixture programs to the v2 shape (`texts` without `score`,
`theme.flag`, `team` `"home"`/`null`). Keep every ending-path assertion from
v1. Add: a `penalty` program with `intro: {id: 'none', duration_ms: 0}`
mounts `[data-scene="penalty"]` immediately and the override layout is up;
the claw intro's stage carries the paw/gouge/debris nodes (assert by class
names you define). Drop the `.cs-td-score` assertion (no score). The replace
case may still use `first_down` (Agent C provides it; run the browser test
again at the end of your work).

## 5. Verification every graphics agent (B and C) must do — this is the deliverable

A scene that was never looked at is not done. Loop at least three times:

1. Build a capture script in **your own scratch folder** from
   `C:\Users\505gr\AppData\Local\Temp\claude\C--Users-505gr-OneDrive-Desktop-Scoreboard\d77a88a9-3926-4f95-ab62-d5245c457005\scratchpad\capture_scenes.cjs`
   and `make_stub.py` (same folder; it writes `__stub_programs.js` with v2
   programs against the real Broadcast preset — run it with
   `.\.venv\Scripts\python.exe make_stub.py <out dir>`). Playwright is local:
   `require('C:/Users/505gr/OneDrive/Desktop/Scoreboard/node_modules/playwright')`,
   `chromium.launch({channel: 'msedge', headless: true})`. Load the page
   from `file://`, stub `window.pywebview.api` exactly as the script does.
2. Screenshot **frames**, not one frame: for your scene, capture at ~6
   moments (e.g. 150, 400, 800, 1500, 3000, 6000 ms after `applyCutscene`)
   at 1920×1080, plus two frames at 640×360. Name them by scene and ms.
3. **Read the PNGs** (the Read tool renders images) and judge them against
   section 1. Write down what is weak, fix it, capture again. Do not stop
   at "it renders".
4. Run the suite parts you own (section 8) green.

Put nothing under `src/scoreboard/views` that is not shipped code (no stub
file left in the views tree).

## 6. Tigers scenes — `views/spectator/cutscenes/tigers.js` + `tigers.css` (Agent C)

`tigers.js` is an IIFE that reads
`var registry = window.ScoreboardCutsceneScenes; var h = registry.helpers;`
(`sceneRoot`, `addText`, `textOf`, `simpleScene` — Agent B exposes these;
until B lands, copy the four helpers *locally* under the same names so your
file runs on its own, then switch to `h.*` if `registry.helpers` exists —
`var h = registry.helpers || localHelpers;`). Register with literal calls
`register('first_down', …)` and `register('touchdown', …)`. Each scene root
carries `data-scene="<id>"`. Words only from `program.texts.headline`,
`.subline`, `.team_name`; colours only from `--cs-*`; sizes only from
`--stage-w`/`--stage-h`. The logo `<img>` (section 1) is created with
`createElement('img')`, `alt=''`, `src = 'cutscenes/tmsa-logo.png'`.

### 6.1 `first_down` — 7 s

The idea: **moving the chains**. The broadcast **yellow first-down line**
sweeping across a field graphic is the hero image.

| t (ms) | What |
|---|---|
| 0–500 | Background: a navy field in slight perspective — white yard lines every ~9 % of width, receding upward (a `perspective`/`rotateX` plane or a pre-skewed gradient), hash marks, a faint `--cs-blue` vignette. It **rushes forward** (translate toward the viewer, looping seamlessly) for the first 2 s then eases to a slow drift. |
| 200–700 | A **red diagonal slab** (`--cs-red`, skewed −12°) slams in from the left across the upper third with a `--cs-ink` shadow slab behind it; a thinner `--cs-blue` slab slides in under it from the right. These are the panels the type sits on. |
| 500–1000 | The **yellow line**: a `--cs-gold` bar, ~1.2 % of stage height, sweeps left→right across the field just below the panels, with a bright white leading edge and a short trailing glow. It stops at ~78 % of the width with a small overshoot. This is the "first down marker" — keep it on screen through the hold. |
| 600–1200 | Headline `FIRST DOWN`: words wipe in from behind the red slab (clip-path reveal left→right), white with `--cs-ink` shadow, italic condensed, ~28 % of stage height. A **light sweep** (a skewed white gradient at 35 % opacity) crosses it once at ~1300 ms. |
| 1000–1500 | The **crest** (section 1) drops in at the left of the panels (from above, small overshoot) at ~26 % stage height; the subline `program.texts.subline` (`TIGERS`) rises into the blue slab, tracked +0.18 em, `--cs-mist`. |
| 1500–6400 | Hold: the field drifts, the yellow line's glow breathes gently (opacity .85↔1 over 2.4 s). |

### 6.2 `touchdown` — 10 s, the biggest moment of the game

No score anywhere in this scene. Composition (three beats, then a hold):

| t (ms) | What |
|---|---|
| 0–350 | **Beat 1 — the hit.** Two huge diagonal slabs, `--cs-blue` from the left and `--cs-red` from the right, slam together at the centre (skewed −14°, overlapping with a `--cs-ink` gap line), with a `--cs-white` impact flash line along the seam that decays in 200 ms. The whole stage does a 1 % camera push (scale 1.0→1.03) over 400 ms. |
| 300–1300 | **Beat 2 — the word.** `TOUCHDOWN` in condensed italic caps at ~32 % of stage height, letters wiping in one after another (each letter its own `<span>` inside the text node's box is *not* allowed — a team name would be operator text; the headline is Python's constant, but keep one rule: render the headline as one text node and animate the reveal with a moving `clip-path` inset instead of per-letter spans). White fill, `--cs-ink` extrude (stacked `text-shadow`s) and a `--cs-gold` outline (`-webkit-text-stroke`), then a **light sweep** across it at ~1200 ms. |
| 900–2200 | **Beat 3 — the burst.** From behind the word: **confetti** — 70–90 small rectangles in `--cs-red`, `--cs-blue`, `--cs-white`, `--cs-gold` (gold sparingly), each its own `translate/rotate` keyframes, launched upward and outward in a fan then falling with drift, staggered by `animationDelay`, gone by 4.5 s. Plus 10–12 **rays** of `--cs-gold`/`--cs-white` opening once behind the slabs (like v1's but fewer, wider, and fading to 20 %). |
| 1300–2000 | The **crest** (section 1) arrives at the lower-left of the word with weight (scale 1.4→1 with a small settle), ~30 % stage height; the **subline** `TIGERS` slides in on a `--cs-ink` tag to its right, tracked +0.2 em, then `program.texts.team_name` is **not** shown a second time (the subline already carries it). |
| 2000–9400 | Hold: slabs drift 1–2 % in opposite directions over 8 s, rays breathe, confetti finishes falling. The word never moves after it lands. |

Texture: a diagonal hatch/carbon at 5–7 % opacity over the slabs (a
`repeating-linear-gradient`), and a vignette to `--cs-ink` at the corners.

### 6.3 Practice-window check

At 640×360, drop-shadow and blur radii scale from `--stage-w` (they are
device px in `filter`), and the crest stays ≥ 18 % of stage height so the
tiger head is still recognisable.

## 7. Shared preview helper (orchestrator provides)

`make_stub.py` in the orchestrator's scratchpad (path in section 5) writes
`__stub_programs.js`: `window.__STUB = { view, programs: {first_down,
touchdown, penalty} }` with v2-shaped programs (section 2.3 shape, the real
Broadcast preset layout, `theme` including `flag`, `intro` 1600/none). Agents
B and C use it as-is; it does not import `build_program`, so Agent A's
signature change cannot break it.

## 8. Test commands (from the repo root, PowerShell)

```powershell
$env:SCOREBOARD_DATA_DIR = "$env:TEMP\scoreboard-tests"
.\.venv\Scripts\python.exe -m unittest tests.unit.test_cutscene_schema tests.integration.test_cutscene_packs tests.integration.test_cutscene_director tests.integration.test_cutscene_bridge tests.integration.test_cutscenes_window tests.integration.test_cutscenes_ui_contract -v   # Agent A
.\.venv\Scripts\python.exe -m unittest tests.integration.test_cutscene_player_contract tests.ui.test_cutscene_player_browser tests.integration.test_spectator_layout_render -v   # Agents B, C
.\.venv\Scripts\python.exe -m unittest tests.integration.test_keyboard_source tests.ui.test_keyboard_browser -v   # Agent A
```

The orchestrator runs the full suite and the real pywebview harness at the
end.

## 9. File ownership (disjoint; do not edit files you do not own)

| Agent | Owns |
|---|---|
| A (Opus, "python + window + docs") | `src/scoreboard/presentation/cutscenes.py`, `src/scoreboard/infrastructure/cutscene_packs.py`, `src/scoreboard/host/cutscenes.py`, `src/scoreboard/host/bridge.py`, `src/scoreboard/host/app.py` (only if a signature forces it), `src/scoreboard/views/cutscenes/*`, `src/scoreboard/views/operator/keyboard.js`, `src/scoreboard/views/operator/operator.js` (only if needed), `tests/unit/test_cutscene_schema.py`, `tests/integration/test_cutscene_packs.py`, `test_cutscene_director.py`, `test_cutscene_bridge.py`, `test_cutscenes_window.py`, `test_cutscenes_ui_contract.py`, `test_keyboard_source.py`, `tests/ui/keyboard.cjs`, its rows in `tests/README.md`, `docs/*.md`, `PROJECT_ROADMAP.md`, `AGENTS.md` |
| B (Opus, "intro + penalty + player") | `src/scoreboard/views/spectator/cutscene.js`, `cutscene.css`, `cutscenes/builtin.js`, `tests/ui/cutscene_player.cjs`, `tests/ui/test_cutscene_player_browser.py`, `tests/integration/test_cutscene_player_contract.py`, its rows in `tests/README.md` |
| C (Opus, "Tigers scenes") | `src/scoreboard/views/spectator/cutscenes/tigers.js`, `cutscenes/tigers.css` (both exist as placeholders), `cutscenes/tmsa-logo.png` (already in place; do not replace it) |

`src/scoreboard/views/spectator/index.html` is already updated by the
orchestrator and is owned by nobody in this round. `tests/README.md` is the
one shared file: each agent edits only its own rows.
