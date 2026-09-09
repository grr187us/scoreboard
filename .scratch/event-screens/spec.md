# Pre-game and halftime default screens ("Broadcast Welcome") — shared spec

Status: in progress (September 8, 2026, branch `improvements`). Orchestrated by the
session lead; four file-owned agents build against this document. Where this spec is
silent, keep the v2/v3 behaviour and house rules (`.scratch/layout-editor-v2/spec.md`,
`.scratch/presentation-screens/spec.md`) and the repo doctrine in `docs/UX_AND_LAYOUT.md`.

Source design: the owner's handoff (reproduced verbatim in section 9 below). The design
file `Scoreboard Views.dc.html` was **not available** in this session; the tables in the
handoff are the source of truth.

## 0. Goal, in one paragraph

Replace the built-in default pre-game and halftime screens (`default_screen("pregame")`,
`default_screen("halftime")`) with the "Broadcast Welcome" direction (1a/1b), and register
"Kickoff Clock" (1c/1d) and "Fifty Yard Line" (1e/1f) as selectable screen presets. To draw
them the layout engine gains: a bundled condensed face (Barlow Condensed), validated gradient
fills on boxes, a bounded named-animation property with a global motion kill switch, rotation,
vertical text, a dashed border style, a `bleed` flag for boxes, a bundled crest image, and a
new `ticker` element type. Everything stays presentation-only: no revision, no command, no
history row, nothing fetched at run time.

## 1. Hard rules (verbatim from the repo)

- **No network at game time.** Fonts and images ship inside `src/scoreboard/views/shared/`.
  Already placed by the lead (do not re-download):
  `views/shared/fonts/BarlowCondensed-Medium.ttf` (500), `BarlowCondensed-SemiBold.ttf` (600),
  `BarlowCondensed-Bold.ttf` (700), `Barlow-OFL.txt` (SIL OFL 1.1, from
  github.com/google/fonts `ofl/barlowcondensed`), and `views/shared/img/tigers-crest.png`
  (copy of `brand-baseline/official-logo-reference.png`, 218×174, supplied by the owner on
  September 4, 2026).
- **The layout editor must not touch game state.** No `command`, no revision bump, no history
  row (`docs/ARCHITECTURE.md`). The motion switch is a *host preference* (config.json), like
  the display preference.
- **4 % safe area** for every glyph (`docs/UX_AND_LAYOUT.md` 10.6). Text elements and widgets
  must validate inside it. Boxes/images may bleed to the canvas edge; a `bleed: true` box may
  cross the canvas edge (new, section 2.7). A ticker's glyphs pass through the horizontal
  inset while scrolling — that is inherent to a marquee and is documented, not fixed.
- **LED rules** (`brand-baseline/palette.json`): no fast orange/navy alternation (minimum
  durations below enforce it), home/away never distinguished by colour alone (the HOME /
  VISITOR eyebrows on 1c/1d, the names everywhere else).
- Minimum type on these screens is `font_scale` 0.0188. Never go below it when reflowing.
- Never run `npm`/`pip install`. Node: `export PATH="/c/Program Files/nodejs:$PATH"` in Bash.
- Test command (repo root, Bash):
  `SCOREBOARD_DATA_DIR="$TMP/sb-test" ./.venv/Scripts/python.exe -m unittest tests.unit.test_layout_schema -v`
  (never `-t .`). Full suite: `-m unittest discover -s tests -v` (~60–90 s).
- `tests/integration/test_spectator_layout_render.py` compares `board.js`'s JSON literals
  (`DEFAULT_LAYOUT`, `DEFAULT_SCREENS`, `FONT_FAMILIES`, …) to Python **byte-for-byte as
  JSON**. **The lead regenerates those literals after Agent A lands** — Agents B/C must not
  hand-edit them (B may add the new `BUNDLED_IMAGES` literal and `ELEMENT_DEFAULTS.ticker`).

## 2. Schema additions (`src/scoreboard/presentation/layout.py`) — Agent A

`LAYOUT_SCHEMA_VERSION` stays **3**: every new property has a default, so a stored v3
document without them validates with no warning and renders as before. (`ticker` is a new
element *type*; an older build would refuse a layout that uses one — acceptable, forward
compatibility is not promised.)

### 2.1 Constants (exact names; every agent hard-codes these)

```python
ELEMENT_TYPES = ("text", "image", "box", "ticker")

FONT_FAMILIES adds, right after "bahnschrift_condensed":
    "barlow_condensed": "'Barlow Condensed', 'Bahnschrift Condensed', Bahnschrift, Impact, sans-serif",
and right after "varsity":
    "graduate": "Graduate, Impact, 'Arial Black', sans-serif",
FONT_FAMILY_LABELS: "barlow_condensed": "Barlow Condensed (bundled)", "graduate": "Graduate (bundled)"

ANIMATION_PRESETS = ("none", "sweep", "drift", "scroll_x", "marquee", "blink_soft")
ANIMATION_MIN_SECONDS = {"sweep": 8.0, "drift": 6.0, "scroll_x": 10.0, "marquee": 20.0, "blink_soft": 1.0}
MAX_ANIMATION_SECONDS = 120.0

FILL_KINDS = ("linear", "radial", "stripes")
MIN_FILL_STOPS, MAX_FILL_STOPS = 2, 4
BORDER_STYLES = ("solid", "dashed")
ORIENTATIONS = ("horizontal", "vertical", "vertical_flipped")
MAX_ROTATE_DEGREES = 180.0            # rotate_degrees in [-180, 180]
BLEED_MIN, BLEED_MAX, BLEED_MAX_SIZE = -0.5, 1.5, 2.0

TICKER_MODES = ("scroll", "rotate")
MAX_TICKER_LINES = 8
MAX_TICKER_LINE_LENGTH = 80
TICKER_SPEED_RANGE = {"scroll": (20.0, 120.0), "rotate": (3.0, 60.0)}   # seconds per loop / per line
TICKER_SEPARATOR = "  •  "      # what a scrolling/static ticker puts between lines

BUNDLED_IMAGES = {"tigers-crest": "shared/img/tigers-crest.png"}       # path relative to views/
BUNDLED_IMAGE_LABELS = {"tigers-crest": "TMSA Tigers crest"}
```

`limits()` gains: `animation_presets`, `animation_min_seconds` (dict), `max_animation_seconds`,
`fill_kinds`, `max_fill_stops`, `border_styles`, `orientations`, `max_rotate_degrees`,
`bleed_min`, `bleed_max`, `bleed_max_size`, `ticker_modes`, `max_ticker_lines`,
`max_ticker_line_length`, `ticker_speed_range` (dict of 2-lists), `bundled_images`
(`[{"id", "label", "path"}]`). Export every new constant in `__all__`.

### 2.2 New properties and where they apply

| property | widgets | text | image | box | ticker | default | validation |
|---|---|---|---|---|---|---|---|
| `border_style` | ✓ | ✓ | ✓ | ✓ | ✓ | `"solid"` | in `BORDER_STYLES` (code `BORDER_STYLE`) |
| `animation` | ✓ | ✓ | ✓ | ✓ | — | `None` | see 2.3 (code `ANIMATION`) |
| `orientation` | ✓ | ✓ | — | — | — | `"horizontal"` | in `ORIENTATIONS` (code `ORIENTATION`) |
| `rotate_degrees` | — | ✓ | ✓ | ✓ | — | `0.0` | finite, `[-180, 180]`, rounded (code `ROTATE`) |
| `fill` | — | — | — | ✓ | — | `None` | see 2.4 (code `FILL`) |
| `bleed` | — | — | — | ✓ | — | `False` | bool (code `BLEED`); see 2.7 |
| `fit_text` | ✓ (exists) | ✓ **new** | — | — | — | `False` | bool (code `FIT_TEXT`) |
| `lines`, `mode`, `speed_seconds` | — | — | — | — | ✓ | see 2.5 | see 2.5 |

Add them to `_KNOWN_WIDGET_PROPERTIES`, `_TEXT/_IMAGE/_BOX_ELEMENT_PROPERTIES`, a new
`_TICKER_ELEMENT_PROPERTIES`, `_STYLE_DEFAULTS` (`border_style`, `animation`, `orientation` —
note `_STYLE_DEFAULTS` is copied onto every default widget, so `default_layout()` changes and
the lead regenerates the JS literal), and `_CLAMP_PASSTHROUGH_PROPERTIES` (all of the above
plus the already-missing `display_format` and `fit_text`). `_clamp_element` already passes
non-geometry through.

### 2.3 `animation`

`None`, or `{"preset": <ANIMATION_PRESETS minus "none">, "duration_seconds": <number>}`.
Normalized: `None` when absent, `null`, or `preset == "none"`; otherwise exactly those two
keys with `duration_seconds` rounded to 4 dp and required to be
`ANIMATION_MIN_SECONDS[preset] <= d <= MAX_ANIMATION_SECONDS` (error otherwise, the whole
property falls back to the default). Any other shape is an error `ANIMATION`.

### 2.4 `fill` (box elements only)

`None` or one of three descriptors; *only numbers and hex colours* ever reach the document —
the CSS string is built by `board.js` from the validated numbers, never stored.

```
{"kind": "linear", "angle": 0..360, "stops": [stop, ...]}           # 2–4 stops
{"kind": "radial", "center_x": 0..1, "center_y": 0..1,
                   "radius_x": 0.05..2.0, "radius_y": 0.05..2.0, "stops": [stop, ...]}
{"kind": "stripes", "angle": 0..360, "color": "#RRGGBB", "opacity": 0..1,
                    "on": 0.001..0.5, "off": 0.0..1.0}               # fractions of canvas WIDTH
stop = {"color": "#RRGGBB", "opacity": 0..1, "at": 0..1}            # "at" non-decreasing
```

Normalize colours through `_normalize_color`, numbers through `_round_coordinate`. A `fill`
that is present wins over `background` in the renderer; `background` stays as the flat colour
fallback and is still validated exactly as today.

### 2.5 `ticker` element

Base element properties (id/type/visible/x/y/width/height/z_index/opacity), the fill/border
set (`background`, `background_opacity`, `border_color`, `border_width`, `border_style`,
`corner_radius`, `corner_cut`, `cut_corners`), the text style set (`color`, `font_scale`,
`font_family`, `font_weight`, `letter_spacing`, `text_transform`, `text_effect`,
`text_align`, `vertical_align`, `padding` — same defaults and validators as a text element),
plus:

- `lines`: list of 1..`MAX_TICKER_LINES` strings, each 1..`MAX_TICKER_LINE_LENGTH` characters
  after `strip()`, no control characters, no newlines. Missing/empty → error `TICKER_LINES`.
- `mode`: in `TICKER_MODES`, default `"scroll"` (code `TICKER_MODE`).
- `speed_seconds`: finite, within `TICKER_SPEED_RANGE[mode]`, default `30.0` (scroll) /
  `5.0` (rotate) (code `TICKER_SPEED`).

Bounds: like a **box** (inside the canvas, not the safe area). Minimum size: widget minimum
(0.02 × 0.02). `element_label()` for a ticker: `Ticker "<first line, truncated to 24>"`.
Not eligible for `animation`, `orientation`, `rotate_degrees`, `fill`, `bleed`
(unknown-property warning, as for any other type).

### 2.6 Image `src`

`_validate_image_src` additionally accepts `asset:<key>` where `<key>` matches
`^[a-z0-9-]{1,40}$` and is in `BUNDLED_IMAGES`; decoded size counts as 0 bytes. Unknown key
→ error `IMAGE_SRC` ("… is not a bundled image"). Data URIs behave exactly as today.

### 2.7 `bleed` (box elements only)

When `bleed` is `true`: `x`, `y` may be in `[BLEED_MIN, BLEED_MAX]`, `width`/`height` in
`[minimum, BLEED_MAX_SIZE]`, and the box must still intersect the canvas
(`x < 1`, `x + width > 0`, `y < 1`, `y + height > 0`; error `OUTSIDE_CANVAS` otherwise).
When `false` (default) the existing canvas rule applies unchanged. `_clamp_element` uses the
same widened bounds for a bleed box. Rationale: rotated bars, the light sweep, and the
yard-line loop all need to overhang the canvas; the board sections clip (`overflow: hidden`,
Agent B).

### 2.8 Default event screens and presets

- `_EVENT_WIDGET_GEOMETRY` becomes **per screen** — pregame and halftime differ now. Keep a
  `_CLASSIC_EVENT_WIDGET_GEOMETRY` (the current table, unchanged numbers) for the "Classic"
  preset. `default_screen(screen_id)` **returns the Broadcast Welcome screen**
  (`_welcome_event_screen(screen_id)`), and `default_screen_widget(screen_id, id)` returns
  that screen's widget default (so "Reset this widget" and missing-widget fill both land on the
  new default). `default_layout()["screens"]` therefore changes.
- Screen preset ids and order (both lists exactly 9 long; test asserts the lists):
  pregame: `pregame_welcome` "Broadcast Welcome", `pregame_kickoff_clock` "Kickoff Clock",
  `pregame_fifty` "Fifty Yard Line", `pregame_classic` "Classic", `pregame_matchup`,
  `pregame_broadcast`, `pregame_tigers`, `pregame_stadium`, `pregame_grid`.
  halftime: `halftime_welcome`, `halftime_kickoff_clock`, `halftime_fifty`, `halftime_classic`,
  `halftime_score_first`, `halftime_broadcast`, `halftime_tigers`, `halftime_stadium`,
  `halftime_grid`. Descriptions: welcome "The built-in default: a broadcast-style welcome with
  the countdown, matchup and an announcement ticker." / kickoff "Numeral-first: the countdown
  fills the board over rotated team bars." / fifty "A scrolling field with end-zone bands and
  a framed countdown." / classic "The original centred countdown arrangement."
- `pregame_classic`/`halftime_classic` = `_classic_event_screen(screen_id)` (black, no
  elements, classic geometry; identical to today's `default_screen` output).
- Every preset must validate `ok` with **zero warnings** via `_normalized_screen_preset`
  (existing test), and every element id must be unique per screen.
- Element ids the browser test targets (must exist with these ids where the screen has the
  feature): `ticker` (the ticker element, every screen), `light_sweep` (welcome, both),
  `top_glow` (welcome), `crest` (the image element, pregame screens), `crest_plate`,
  `opponent_slot` (the dashed box, pregame screens), `opponent_caption` (its text), `yard_lines`
  (fifty), `home_bar`/`away_bar` (kickoff clock team bars). Choose the other ids freely, lower
  snake case.
- **Type choices (pinned):** headlines/labels `font_family: "barlow_condensed"`; numerals
  (`event_clock`, scores, "VS", ghost "50") `font_family: "graduate"` with `font_weight: 700`
  (Graduate has one weight; 700 gives synthetic bold as the Grid preset does). This is the
  explicit decision on Jersey M54: it is **not** bundled and the new screens do **not** use the
  `varsity` stack, so the look is deterministic.
- Units: the handoff authored at 1280×720. px → fraction of canvas **width**: 3px 0.0023,
  4px 0.0031, 5px 0.0039, 16px 0.0125, 18px 0.0141, 20px 0.0156, 22px 0.0172. A hairline
  box's *height* is a fraction of canvas height (4px → 0.0056). `MIN_BOX_THICKNESS` is 0.002.
- Safe area: any **text** element or widget the handoff places above y 0.04 or below
  y 0.96 (e.g. the eyebrow at y 0.026) moves to the nearest legal position at the same size.
  Boxes may stay where the handoff puts them.
- Ticker element geometry: `x 0, y 0.89, width 1.0, height 0.10` (fifty: inset per handoff),
  `vertical_align middle`, so the glyph ink stays above the 0.96 line at `font_scale` 0.025.
- `nowrap` in the handoff = `fit_text: true` (widgets and text elements): it forces a single
  line and shrinks only if needed. Apply it to every name, numeral, `event_title`,
  `event_clock`, the warm-up chip texts, and every "must be single-line" item.
- View-model strings are **not** changed (out of scope): the halftime title reads
  "UNTIL SECOND HALF", the warm-up line "Warmup follows: 3:00" (use `text_transform:
  "uppercase"` where the design shows caps), `event_phase` reads "HALFTIME" then "WARMUP".
- Announcement defaults (all editable): pregame `["WELCOME TO TIGER STADIUM", "SENIOR NIGHT —
  HONORING THE CLASS OF 2027", "CONCESSIONS OPEN BEHIND THE HOME STANDS", "NATIONAL ANTHEM AT
  6:55", "SCIENCE · WISDOM · PEACE"]`; halftime `["SENIOR NIGHT — HONORING THE CLASS OF 2027",
  "TIGER BAND TAKES THE FIELD", "50/50 RAFFLE DRAWING AT THE START OF THE 3RD", "SCIENCE ·
  WISDOM · PEACE"]`. Keep each under 60 characters.
- The opponent slot is a **box** (`border_style: "dashed"`, `border_width: 0.0023`,
  `border_color: "#DDE7F4"`, hatch `fill: {"kind": "stripes", "angle": 45, "color": "#DDE7F4",
  "opacity": 0.14, "on": 0.002, "off": 0.008}`) plus a text `opponent_caption`
  (`"OPPONENT\nLOGO"`, `consolas`, 0.0188, `#DDE7F4`). The operator adds their own art with
  *Add image* over it. Never invent an opponent mark.
- The crest is a white box `crest_plate` (`corner_cut` 0.0125) with an image element `crest`
  (`src: "asset:tigers-crest"`, `fit: "contain"`) inset ~10 % on each side.

### 2.9 Motion switch plumbing (Agent A owns the Python side)

- `scoreboard.infrastructure.config`: `PRESENTATION_SECTION = "presentation"`; the section is
  `{"motion": bool}`; absent/invalid → motion **on**.
- `LayoutLink.publish_motion(self, enabled: bool) -> None` (no-op default).
- `PresentationLayouts.motion_enabled() -> bool`; `set_motion(enabled: Any) -> dict` — a
  non-bool answers `{"ok": False, "message": "Motion must be on or off.", ...state}` and
  writes nothing; a bool writes the section, sets `self._message = "Motion is on/off."`, calls
  `self._link.publish_motion(enabled)` inside the same try/except pattern as `_publish`, and
  returns `state()` with `"ok": True`. `state()["motion"]` is always present.
- `LayoutEditorBridge.set_motion(enabled)` forwards. Still no `command` method.
- `SpectatorBridge.__init__(..., read_motion: Callable[[], bool] | None = None)` and
  `get_motion() -> bool` (default `True`).
- `host/app.py`: `WindowHost.publish_motion(enabled)` evaluates
  `window.applyMotion && window.applyMotion(true|false)` on the spectator, test and layout
  windows (mirror `publish_layout`); wire `application.layouts.link.publish_motion =
  self.publish_motion`; pass `read_motion=self.application.layouts.motion_enabled` wherever a
  `SpectatorBridge` is built; call `self.publish_motion(self.application.layouts.motion_enabled())`
  right after each existing `publish_layout(...)`-on-open call.
- Tests (Agent A): `set_motion` advances no revision and writes no history row (extend
  `tests/integration/test_layout_bridge.py` in the style of the existing "advance no revision"
  tests); the config round-trip; the bridge exposes `get_motion`; every new payload is JSON-safe.

### 2.10 Packaging (Agent A)

`tools/build_package.py` `REQUIRED_FILES` gains the three Barlow TTFs, `Barlow-OFL.txt` and
`shared/img/tigers-crest.png`; `pyproject.toml` package-data gains `"views/**/img/*.png"`;
`tests/integration/test_packaging.py` must cover the new files the same way it covers
Graduate. `assets/README.md` records provenance for both (font: Barlow, Jeremy Tribby, SIL OFL
1.1, source google/fonts; crest: owner-supplied reference, rights to be confirmed with the
school before public use — same wording as `brand-baseline/README.md`).

## 3. Renderer (`views/shared/board.css`, `board.js`, `views/spectator/spectator.js`, `spectator.css`) — Agent B

### 3.1 CSS hooks (pinned names)

- Fonts: three `@font-face` blocks for `font-family: "Barlow Condensed"` weights 500/600/700
  (`font-display: block`, `url("fonts/BarlowCondensed-Medium.ttf")` etc.).
- `--bs` → `border-style: var(--bs, solid)` on `.widget` and `.element`.
- `--rot` → `.element { rotate: calc(var(--rot, 0) * 1deg); }` (the individual `rotate`
  property, so keyframe `transform`s compose with it).
- `data-orientation` on the node: `[data-orientation="vertical"] > .widget-text
  { writing-mode: vertical-rl; }`, `[data-orientation="vertical_flipped"] > .widget-text
  { writing-mode: vertical-rl; rotate: 180deg; }`.
- Fill: `applyPaint` sets `--bg` to the gradient string built from a validated `fill`
  (2.4) — `linear-gradient(<angle>deg, rgba() <at>%, …)`,
  `radial-gradient(<rx*100>% <ry*100>% at <cx*100>% <cy*100>%, …)`,
  `repeating-linear-gradient(<angle>deg, rgba() 0 calc(var(--canvas-width) * on),
  transparent calc(var(--canvas-width) * on) calc(var(--canvas-width) * (on+off)))`.
  A stripes fill also sets `--sx` = `on + off` (the scroll period). A `fill` of unknown shape
  falls back to `background`.
- Animation: `data-anim="<preset>"` and `--anim-s: <seconds>s` on the node. Keyframes
  (exact names): `sb-sweep`, `sb-drift`, `sb-scroll-x`, `sb-marquee`, `sb-blink`.
  - `[data-anim="sweep"] { animation: sb-sweep var(--anim-s) linear infinite; }` with
    `from { transform: translateX(-120%) skewX(-18deg) } to { transform: translateX(calc(var(--canvas-width) * 1.3)) skewX(-18deg) }`.
  - `drift`: `ease-in-out infinite alternate`, `from translateY(-8%) to translateY(8%)`.
  - `scroll_x`: `linear infinite`, `from translateX(0) to translateX(calc(-1 * var(--canvas-width) * var(--sx, 0.0833)))`.
  - `marquee` (generic node): `linear infinite`, `translateX(0) → translateX(-50%)` on
    `> .widget-text`.
  - `blink_soft`: `steps(1, end) infinite`, `0% { opacity: 1 } 50% { opacity: .5 }`, applied to
    `.clock-colon` spans when the node has `data-colon="1"`, else to `> .widget-text`.
- **Kill switch:** `[data-motion="off"] [data-anim], [data-motion="off"] [data-anim] *,
  [data-motion="off"] .ticker-track { animation: none !important; transform: none !important; }`
  and the same block under `@media (prefers-reduced-motion: reduce)`. The attribute lives on
  the **container** passed to `applyLayout` (`#canvas` on both pages).
- Ticker: `.element-ticker { overflow: hidden; }`, `.ticker-track { display: flex;
  white-space: nowrap; width: max-content; }`, scroll mode
  `[data-ticker-mode="scroll"] .ticker-track { animation: sb-marquee var(--anim-s) linear infinite; }`,
  rotate/static: single run, `.ticker-run` with `transition: opacity .4s`, `.ticker-fade { opacity: 0 }`.
- `spectator.css`: `#game-board, #event-board { overflow: hidden; }` (clips bleed boxes).

### 3.2 board.js behaviour

- `ELEMENT_DEFAULTS.ticker` and `var BUNDLED_IMAGES = {"tigers-crest": "shared/img/tigers-crest.png"};`
  (pure JSON literal, `var NAME = {...};` form — the lead adds a contract test that compares it
  to Python). An `asset:<key>` src resolves to `'../' + BUNDLED_IMAGES[key]` (both pages sit one
  level below `views/`). `isValidElementEntry` accepts `asset:` srcs and the `ticker` type.
- `applyPaint`: `--bs`, `fill` → `--bg`, `--sx`. `applyTextStyle`: `dataset.orientation`.
  `applyElementStyle`: `--rot`; `fit_text` on text elements (`dataset.fitText`, `_fitKey = null`,
  fit after layout); ticker build (3.3). New `applyMotionAttributes(node, source, fallback)`:
  sets `dataset.anim`/`--anim-s` **only when the value changed** (never restart a running
  animation on a layout push); removes them when `animation` is null.
- `setWidgetText`: when the new text has the same number of `:`-separated parts as the current
  content, update the text nodes in place and **keep the existing `.clock-colon` spans**; set
  `data-colon="1"`/remove it. This is what stops the colon blink restarting every second.
- `fitWidgetText`: when `dataset.orientation` is a vertical mode, use the range rect for both
  axes (skip the canvas ink height). `refitAllWidgetText` also covers
  `.element-text[data-fit-text="1"]` and static ticker runs.
- `ScoreboardBoard.setMotion(container, enabled)`: sets/removes `data-motion="off"` on
  `container`, then re-applies every ticker under it (3.3) and refits text. Exported.
- Animations are attached to nodes that persist: widgets are built once; elements are
  reconciled in place by id. `applyModel` (the per-second path) must never touch an element
  node or an animation attribute.

### 3.3 Ticker rendering

Node: `<div class="widget element element-ticker" data-element data-element-type="ticker"
data-ticker-mode="scroll|rotate|static">` containing `<div class="ticker-track">` with one or
two `<span class="widget-text ticker-run">`.

- Key `node._tickerKey = lines.join("\n") + "|" + mode + "|" + speed + "|" + motion`; rebuild
  the track only when the key changes (so a layout push with the same ticker never restarts it).
- **scroll + motion on:** two identical runs, text `lines.join(SEP) + SEP` where
  `SEP = "  •  "`; `--anim-s = speed_seconds`.
- **rotate + motion on:** one run showing `lines[i]`; `node._tickerTimer = setInterval(...)`
  every `speed_seconds * 1000` ms: add `.ticker-fade`, after 400 ms swap the text and remove
  the class. Clear the timer whenever the node is rebuilt, removed (in `reconcileElements`'s
  stale branch), or motion goes off.
- **motion off (or `prefers-reduced-motion`):** `data-ticker-mode="static"`, one run with
  `lines.join(SEP)`, no timer, `white-space: nowrap`, shrink-to-fit via `fitWidgetText` so the
  whole line is legible. No information may live only in a moving element.

### 3.4 spectator.js

`window.applyMotion = function (enabled) { B.setMotion(canvas, enabled !== false); }`. On
ready, if `typeof api.get_motion === 'function'`, resolve it into `window.applyMotion`. Nothing
else changes; the boards keep being rebuilt only on layout pushes.

### 3.5 Browser test (Agent B writes; the lead runs it after integration)

`tests/ui/event_screens.cjs` + `tests/ui/test_event_screens_browser.py`, modelled on
`stadium.cjs`/`test_stadium_browser.py`:

- Screens: the default layout's pregame/halftime (welcome) plus the `*_kickoff_clock` and
  `*_fifty` presets applied into a copy of `default_layout()`.
- Models: pregame `GameState()` (defaults, 0–0, warmup hidden); pregame with 24-character
  names; halftime at 900 s, 181 s, 180 s (phase flips to WARMUP), 0 s (0:00), with scores
  199/199 and 24-character names; halftime with scores 7/3 and normal names.
- Viewports 1920×1080, 1366×768, 640×360; motion on and off (`window.applyMotion(false)`).
- Assertions: every visible widget / text element's glyph rect inside its box and inside the
  4 % inset (skip nodes inside a ticker and nodes whose `data-anim` is sweep/drift/scroll_x);
  no two text rects overlap (same skip list); each `home_bar`/`away_bar` has
  `scrollWidth <= clientWidth`; the ticker's text contains every line; with motion off the
  board root has **no running animations** (`getAnimations()` filtered to the board is empty
  or every entry is `idle`/`paused`); with motion on, two `applyView` calls 1100 ms apart keep
  the **same** `Animation` object for `light_sweep`/`ticker` with a strictly increasing
  `currentTime`, and `event_clock` has `.clock-colon` with a running `sb-blink` animation whose
  object survives a text change; the page never scrolls; no page errors.
- When `SCOREBOARD_CAPTURE_DIR` is set, screenshot `<screen>-<motion>-<width>.png` for the
  representative case of every screen at every viewport.
- The Python side asserts the case count and round-trips each preset through
  `PresentationLayouts.save` exactly as `test_stadium_browser.py` does.

Add the v2-style source markers the lead will grep for to
`tests/integration/test_spectator_layout_render.py`'s marker list: `data-anim`, `ticker-track`,
`asset:`, `setMotion`.

## 4. Editor (`views/layout/*`) — Agent C

- Toolbar: a **Motion** toggle button `id="motion-toggle" data-action="toggle_motion"
  aria-pressed`, between the history group and the add group. On `adoptState`, set
  `#canvas`'s `data-motion` from `state.motion` (absent → on) and the button's `aria-pressed`.
  Handler: if `app.api.set_motion` is a function, call `set_motion(!current)` and adopt the
  returned state (it is a full `layout_state` payload plus `ok`); otherwise flip the preview
  attribute locally. Label "Motion on"/"Motion off". Tooltip says it pauses every animation on
  the wall too.
- **Add ticker** button `data-action="add_ticker"` in the add group (`S.makeTickerElement`:
  x 0, y 0.89, w 1.0, h 0.10, lines `["NEW ANNOUNCEMENT"]`, mode scroll, speed 30, background
  `#0D2B5A`, colour `#DDE7F4`, `barlow_condensed` 500, 0.025, letter_spacing 0.16, z 10).
- `S.kindOf` returns `'ticker'`; rail icon for it; `elementLabel` shows its first line;
  duplicate/delete/hide/restack/nudge/drag/marquee-select/undo all work for it. Bounds for a
  ticker: canvas (like a box). Bounds for a `bleed` box: `[-0.5, 1.5]` on both axes.
- Inspector controls (all `data-prop` names are pinned — the contract test enumerates them):
  - Text section also shows for `ticker`; `fit_text` checkbox shows for widgets **and text
    elements**; `data-prop="orientation"` choice group (widgets and text).
  - Fill & border: `data-prop="border_style"` select; for boxes `data-prop="bleed"` checkbox
    and a **Fill effect** group: `data-prop="fill_kind"` select (none/linear/radial/stripes),
    `data-prop="fill_angle"`, `data-prop="fill_color_a"`, `data-prop="fill_opacity_a"`,
    `data-prop="fill_color_b"`, `data-prop="fill_opacity_b"`, `data-prop="fill_on"`,
    `data-prop="fill_off"` (percent of board width). The editor writes a two-stop descriptor
    (`at` 0 and 1) for linear/radial (radial keeps `center_x .5, center_y 0, radius_x .6,
    radius_y 1` unless the document already has values — preserve extra stops/values the
    editor cannot show), and the stripes descriptor from colour/opacity/on/off. Show only the
    fields the chosen kind uses.
  - `data-prop="rotate_degrees"` number (text/image/box).
  - **Motion** section `id="sec-motion"` (widgets, text, image, box): `data-prop="animation_preset"`
    select from `limits.animation_presets`, `data-prop="animation_seconds"` number; the editor
    writes `animation: null` for "none", else `{preset, duration_seconds}` with the seconds
    input clamped to `[limits.animation_min_seconds[preset], limits.max_animation_seconds]`.
  - **Ticker** section `id="sec-ticker"`: `data-prop="lines"` textarea (one line per row,
    split on newline, trim, drop empties), `data-prop="mode"` choice, `data-prop="speed_seconds"`
    number (label changes: "Seconds per loop" / "Seconds per line").
  - Image section: `data-prop="asset"` select — "Uploaded image" plus one entry per
    `limits.bundled_images`; choosing a bundled image sets `src = "asset:<id>"` and shows the
    bundled file in the thumbnail (`../` + path); "Replace image…" still uploads a data URI.
- Update `EDITABLE_PROPERTIES` in `tests/integration/test_layout_editor_contract.py` to the new
  full set, `test_it_offers_the_three_element_types` → four (`add_ticker`), and keep every
  other contract test green (`toggle_motion` must not read as a game command; do not name any
  `CommandType`). If `tests/ui/layout_editor.cjs` needs a drift fix, make it; do not widen it.
- The preview reuses `board.css`/`board.js` unchanged (Agent B's files); the editor sets
  `data-motion` on `#canvas` only. Hidden items still draw at reduced opacity as today.

## 5. Docs — Agent D (`docs/UX_AND_LAYOUT.md`, `PROJECT_ROADMAP.md`, `docs/ARCHITECTURE.md`,
`tests/README.md`, `assets/README.md` is Agent A's)

- `docs/UX_AND_LAYOUT.md`: new **10.12 Broadcast Welcome default screens and motion
  (September 8, 2026)** after 10.11: what changed for the operator (new default pre-game and
  halftime screens, the two new presets, Classic kept), the announcement ticker (where the
  lines live — in the layout, not game state; edit in the editor; Motion off shows them as one
  static line), the Motion switch (editor toolbar button; `config.json` `presentation.motion`;
  every animation on the wall pauses; use it for the HDMI test and the practice window), the
  new element properties in plain words (fill effect, border style, rotation, vertical text,
  bleed, animation presets and their minimum durations), the bundled Barlow Condensed and the
  crest, the opponent-slot rule (operator drops in their own art; nothing is invented), the
  safe-area caveat for Fifty Yard Line and for a marquee, and what is still open (owner
  sign-off on the default pair; stadium-resolution legibility). Amend 10.6 with the `bleed`
  exception and 10.8 (what v2 does not support: remove "animations" from the list, say what is
  bounded).
- `PROJECT_ROADMAP.md`: new item **12. Pre-game and halftime defaults — Broadcast Welcome,
  September 8, 2026** in "Owner-requested next scoreboard work", same shape as items 7–11
  (what, where, evidence, open items). Update "Next Action" and the test count line the lead
  hands over.
- `docs/ARCHITECTURE.md`: one paragraph where the layout editor's no-game-state rule is stated:
  the motion switch is a host preference in `config.json`, pushed with `window.applyMotion`, and
  the ticker's lines are layout content.
- `tests/README.md`: the new browser suite and its capture env var.
- Do not edit any source or test file.

## 6. Ownership (exact)

| Agent | Owns (may edit) | Must not edit |
|---|---|---|
| A (schema, presets, Python plumbing, packaging) | `src/scoreboard/presentation/layout.py`, `src/scoreboard/infrastructure/config.py`, `src/scoreboard/host/layout_bridge.py`, `src/scoreboard/host/bridge.py` (SpectatorBridge only), `src/scoreboard/host/app.py` (publish_motion + wiring only), `tools/build_package.py`, `pyproject.toml`, `assets/README.md`, `tests/unit/test_layout_schema.py`, new `tests/unit/test_event_screens.py`, `tests/integration/test_layout_bridge.py`, `tests/integration/test_packaging.py`, `tests/integration/test_spectator_layout_render.py` (**only** to add a `BUNDLED_IMAGES` contract test) | every `views/` file, every other test |
| B (renderer) | `src/scoreboard/views/shared/board.css`, `board.js` (not the `DEFAULT_LAYOUT`/`DEFAULT_SCREENS`/`FONT_FAMILIES` literals), `src/scoreboard/views/spectator/spectator.js`, `spectator.css`, new `tests/ui/event_screens.cjs`, new `tests/ui/test_event_screens_browser.py`, `tests/integration/test_spectator_layout_render.py` (**only** the marker list) | `layout.py`, `views/layout/*` |
| C (editor) | `src/scoreboard/views/layout/*`, `tests/integration/test_layout_editor_contract.py`, `tests/ui/layout_editor.cjs`, `tests/ui/test_layout_editor_browser.py` | `board.*`, `layout.py` |
| D (docs) | `docs/UX_AND_LAYOUT.md`, `docs/ARCHITECTURE.md`, `PROJECT_ROADMAP.md`, `tests/README.md` | everything else |
| Lead | regenerates `board.js` literals, runs the suites and browser tests, real-`pywebview` run, captures, `.scratch/event-screens/` notes | — |

Agents cannot be messaged after they finish: leave a **STATE** note at the end of your report
(what landed, what you could not finish, exact test results).

## 7. Acceptance (the lead checks all of it)

1. `default_screen("pregame")`/`("halftime")` are the Broadcast Welcome screens; both validate
   `ok` with zero warnings; all 18 screen presets validate with zero warnings; unique ids.
2. `board.js` literals equal Python (contract tests green) after regeneration.
3. Browser suite (3.5) green at 1920/1366/640, motion on and off; captures in
   `captures/event-screens/`.
4. Editor contract tests green; the editor can add/select/move/restyle/undo a ticker and set
   every new property; `layout_editor.cjs` green.
5. Full suite green (baseline 1207 / 0 / 0 / 3 skips before this work; the 3 skips are A-1).
6. Real `pywebview` run: default layout shows the welcome pre-game, halftime after
   `set_quarter HALF`, `set_motion(False)` freezes the sweep/ticker on the practice window,
   `set_motion(True)` resumes, revision unchanged throughout.
7. An operator's saved v3 layout (e.g. the Grid look) keeps its own event screens; only a
   document missing `screens` gets the new default.

## 8. Explicitly out of scope

No changes to clocks, rules, commands, history, recovery, the game board, view-model strings,
or cutscenes. Nothing fetched over the network.

## 9. The owner's handoff (verbatim geometry tables)

### 9.1 Geometry conventions

Canvas is 16:9. `x`/`width` are fractions of canvas **width**; `y`/`height` are fractions of
canvas **height**; `font_scale` is a fraction of canvas **width**. Values were authored at
1280×720. Letter-spacing is in `em`. Palette: navy `#071B3A`, panel navy `#0D2B5A`, deep panel
`#0A1B33`, near-black `#030A12`, identity blue `#17468C`, blue edge `#2869BC` / `#2C62AB`, red
`#C8242B`, red edge `#D0002C`, deep red `#A50021`, white `#FFFFFF`, mist `#DDE7F4`, muted steel
`#93A9C9`, amber `#F5AE08`. Minimum type `font_scale` 0.0188.

### 9.2 `1a` — Pre-game, "Broadcast Welcome" (default)

Background: flat `#071B3A`.

| # | Item | Kind | x | y | w | h | font_scale | Style |
|---|---|---|---|---|---|---|---|---|
| 1 | Top glow | box, gradient | 0 | 0 | 1.0 | 0.52 | — | `radial-gradient(60% 100% at 50% 0, rgba(44,98,171,.5), transparent 72%)`, z 0 |
| 2 | Light sweep | box, gradient + `sweep` 11s linear infinite | — | −0.20 | 0.34 | 1.40 | — | `linear-gradient(90deg, transparent, rgba(255,255,255,.06), transparent)`, z 0 |
| 3 | Home rule | box | 0.03 | 0.042 | 0.28 | 4px | — | `#C8242B` |
| 4 | Away rule | box | 0.69 | 0.042 | 0.28 | 4px | — | `#2C62AB` |
| 5 | "TMSA TIGERS FOOTBALL" | text | 0.33 | 0.026 | 0.34 | 0.045 | 0.0203 | `#93A9C9`, w600, ls .22, center |
| 6 | "WELCOME TO" | text | 0.10 | 0.100 | 0.80 | 0.05 | 0.0266 | `#DDE7F4`, w500, ls .42, center |
| 7 | "TIGER STADIUM" | text | 0.05 | 0.145 | 0.90 | 0.17 | 0.1220 | condensed 700, `#FFFFFF`, center |
| 8 | Gold rule | box | 0.41 | 0.325 | 0.18 | 5px | — | `#F5AE08` |
| 9 | `event_title` | widget | 0.10 | 0.365 | 0.80 | 0.05 | 0.0266 | `#F5AE08`, w600, ls .34, center |
| 10 | `event_clock` | widget | 0.10 | 0.415 | 0.80 | 0.19 | 0.1480 | Graduate, `#F5AE08`, tabular, `fit_text`, colon on `blink_soft` 1s |
| 11 | Crest | image | — | 0.63 | 0.117 | 0.208 | — | white plate, `corner_cut` 16px all, art inset ~10% |
| 12 | `home_name` | widget | — | 0.63 | — | 0.208 | 0.0810 | condensed 700, `#FFFFFF`, uppercase, `fit_text` |
| 13 | "VS" | text | — | 0.63 | — | 0.208 | 0.0410 | Graduate, `#F5AE08` |
| 14 | `away_name` | widget | — | 0.63 | — | 0.208 | 0.0810 | condensed 700, `#DDE7F4`, uppercase, `fit_text` |
| 15 | Opponent slot | image placeholder | — | 0.63 | 0.117 | 0.208 | — | 3px dashed `rgba(221,231,244,.45)`, 45° hatch `rgba(221,231,244,.14)`, monospace caption |
| 16 | Ticker band | box | 0 | 0.89 | 1.0 | 0.11 | — | `#0D2B5A`, 3px top border `#2C62AB` |
| 17 | Ticker text | ticker | 0 | 0.89 | 1.0 | 0.11 | 0.0250 | `#DDE7F4`, w500, ls .16, `marquee` 30s linear infinite |

Row 11–15 is one centered group with even gaps (≈0.034 of width): crest 0.098, home name
0.155–0.40, VS ≈0.47, away name 0.53–0.79, opponent slot 0.80. `home_score` / `away_score` are
**hidden** on this screen. Announcement lines: senior-night recognition, concessions location,
national anthem time, school motto; each under ~60 characters.

### 9.3 `1b` — Halftime, "Broadcast Welcome"

Same background, glow (`sweep` 13s here), rules, and eyebrow as `1a` (rows 1–5).

| # | Item | Kind | x | y | w | h | font_scale | Style |
|---|---|---|---|---|---|---|---|---|
| 1 | `event_phase` "HALFTIME" | widget | 0.05 | 0.095 | 0.90 | 0.13 | 0.0920 | condensed 700, `#FFFFFF`, ls .04, center |
| 2 | Amber rule | box | 0.44 | 0.225 | 0.12 | 5px | — | `#F5AE08` |
| 3 | Home panel | box | 0.04 | 0.27 | 0.27 | 0.34 | — | fill `#0D2B5A`, 3px border `#2C62AB`, `corner_cut` 18px all |
| 4 | Home banner | box | 0.04 | 0.27 | 0.27 | 0.09 | — | `#17468C`, `cut_corners: top` |
| 5 | `home_name` | widget | 0.04 | 0.27 | 0.27 | 0.09 | 0.0450 | condensed 700, `#FFFFFF`, `fit_text`, center |
| 6 | `home_score` | widget | 0.04 | 0.37 | 0.27 | 0.23 | 0.1410 | Graduate, `#FFFFFF`, `fit_text`, center |
| 7 | `event_title` | widget | 0.33 | 0.29 | 0.34 | 0.06 | 0.0234 | `#F5AE08`, w600, ls .26, center, **nowrap** |
| 8 | `event_clock` | widget | 0.33 | 0.36 | 0.34 | 0.16 | 0.0920 | Graduate, `#F5AE08`, tabular, `fit_text`, **nowrap**, colon `blink_soft` |
| 9 | Away panel / banner / name / score | as rows 3–6 | 0.69 | — | 0.27 | — | — | border `#C8242B`, banner `#A50021` |
| 10 | Warm-up chip | box + text | — | 0.655 | auto | 0.086 | 0.0219 | `#0D2B5A`, 3px `#2C62AB`, `#DDE7F4`, ls .12, nowrap |
| 11 | `warmup` line | widget | — | 0.655 | auto | 0.086 | 0.0250 | `#DDE7F4`, w500, ls .10, nowrap |
| 12 | Ticker band + text | box + ticker | 0 | 0.89 | 1.0 | 0.11 | 0.0250 | as `1a` |

Rows 10–11 are a centered pair with a 0.020 gap; **both single-line at their stated size**
(`fit_text`). The centre column is 0.34 wide and the clock must not wrap. Halftime
announcements: senior-night recognition, band, raffle.

### 9.4 `1c` / `1d` — "Kickoff Clock" (preset)

Background `#030A12`. Countdown `font_scale` **0.234** — the largest element on the board.

Shared shell:
- Four rotated bars, `rotate_degrees` ±13, `height` 1.60 at `y` −0.30 (use `bleed`), on
  `drift` (9s and 11s, alternate): left `x` −0.01 `w` 0.07 `#17468C`, left inner `x` 0.07
  `w` 0.024 `#C8242B`; mirrored on the right with the colours swapped.
- Headline: `x` 0.12 `y` 0.06 `w` 0.76 `h` 0.11, `font_scale` 0.0625, condensed 700, `#FFFFFF`,
  ls .06. Pre-game "WELCOME TO TIGER STADIUM"; halftime `event_phase` "HALFTIME" at 0.0656 plus
  an amber chip "TIGER STADIUM" (`#F5AE08` fill, `#030A12` text, 0.0234).
- Amber hairlines `rgba(245,174,8,.55)` at `y` 0.185 and 0.575, `x` 0.20 `w` 0.60, 3px.
- `event_title` at `y` 0.21, 0.0266, ls .40, `#F5AE08`.
- `event_clock` at `y` 0.25 `h` 0.31, 0.234, Graduate, `#F5AE08`, `fit_text`, colon `blink_soft`.
- Announcement line at `y` 0.605, 0.0266, `#DDE7F4`, ls .10 — ticker `mode: "rotate"`, 5s per
  line, cross-fade.
- Team bars: `y` 0.69 `h` 0.25, home `x` 0.04 `w` 0.43 (3px `#2869BC`), away `x` 0.53 `w` 0.43
  (3px `#D0002C`), fill `#0A1B33`, `corner_cut` 20px all, inner padding 0.020 of width.
  - Bar content, left to right: crest / opponent slot (0.092 square, pre-game; 0.075 halftime),
    then a two-line stack — eyebrow "HOME" / "VISITOR" at 0.0188, ls .24, `#93A9C9`, above the
    team name at 0.072 condensed 700 `#FFFFFF`. Halftime replaces the eyebrow stack with name
    at 0.053 and adds `home_score`/`away_score` at 0.081 Graduate, right-aligned in the bar.
  - **Fit constraint:** the bar's content row is 0.43 of canvas width and it is tight. Verify
    `scrollWidth <= clientWidth` at 1920, 1366 and 640. If it doesn't fit, shrink the name, not
    the eyebrow (`fit_text` on the names).
- Halftime note line at `y` 0.605: "WARM-UP ENDS AT ZERO · SENIOR NIGHT ON THE 50", 0.025, nowrap.

The HOME / VISITOR eyebrows are what satisfy the "not by colour alone" rule on this direction.

### 9.5 `1e` / `1f` — "Fifty Yard Line" (preset)

Background `#071B3A` plus a field:
- Yard lines: full-bleed `repeating-linear-gradient(90deg, rgba(255,255,255,.12) 0 3px,
  transparent 3px 160px)` on `scroll_x` (14s pre-game, 18s halftime), overhanging the canvas by
  one period on the right (`bleed`) so the loop is seamless. (stripes: on 0.0023, off 0.1227.)
- Hash rule at `y` 0.47, 4px, `repeating-linear-gradient(90deg, rgba(255,255,255,.30) 0 26px,
  transparent 26px 52px)`, same scroll (on 0.0203, off 0.0203 — period differs from the yard
  lines, so give it its own `--sx` via its own stripes fill).
- Ghost "50" numerals, Graduate, white at opacity .05, `font_scale` 0.117, at `x` 0.145 and
  0.715, `y` 0.05 (pre-game only) — text elements, so they must sit inside the safe area.
- End-zone bands, full height: pre-game `w` 0.13, halftime `w` 0.16. Home `#17468C` with a 5px
  white inner edge; away `#C8242B`. Pre-game carries the team name **vertically**
  (`orientation: vertical_flipped` on the left band, `vertical` on the right), 0.072, ls .22,
  condensed 700, white. Halftime stacks horizontal name 0.039 over `home_score`/`away_score`
  0.103 Graduate over a 0.05×4px white rule at 50 % opacity.
- Pre-game centre stack: crest plate 0.123 square at `y` 0.06 (white, `corner_cut` 18px);
  "WELCOME TO" `y` 0.31, 0.0234, ls .40, `#DDE7F4`; "TIGER STADIUM" `y` 0.35 `h` 0.12, 0.086,
  condensed 700, `text_effect: shadow`.
- Clock plate: pre-game `x` 0.20 `y` 0.53 `w` 0.60 `h` 0.26; halftime `x` 0.22 `y` 0.29
  `w` 0.56 `h` 0.30. Fill `#030A12` at opacity .82, 4px `#F5AE08`, `corner_cut` 22px. Inside:
  `event_title` 0.025 ls .34 `#F5AE08`, then `event_clock` 0.123 (pre-game) / 0.133 (halftime)
  Graduate **white** — the one direction where the numerals are white.
- Halftime adds `event_phase` "HALFTIME" at `y` 0.07 `h` 0.11, 0.081, shadow; a subline
  "TIGER STADIUM · HOMECOMING" at `y` 0.20, 0.0234, ls .34; and a warm-up row at `y` 0.625 —
  amber chip (`#F5AE08` fill, `#071B3A` text, 0.021) plus `warmup` 0.0234, both `fit_text`.
- Ticker band is **white with navy text** here (`#FFFFFF` / `#071B3A`, 0.0234, ls .16), inset
  to the field between the bands: pre-game `x` 0.13 `w` 0.74, halftime `x` 0.15 `w` 0.70,
  `h` 0.10, bottom-aligned.

**Safe-area caveat:** this direction deliberately bleeds to all four edges. Keep every glyph
inside the 4 % inset — bands and stripes may bleed, lettering may not.

### 9.6 Behaviour and acceptance (owner's words)

- Both screens must render correctly with `warmup` hidden (pre-game), with a three-digit score,
  with a long school name (`fit_text` on every name and numeral), and at 0:00.
- The **motion kill switch** must be exercised: with motion off, every screen must still be
  complete and legible — no information may live only in a moving element.
- No animation may restart or stutter on the once-per-second snapshot publish. Bind animations
  to elements that persist across renders, not to nodes recreated per tick.
- The layout editor must be able to select, move, restyle and undo every new element type, and
  its live preview (which reuses `board.css` unchanged) must match the spectator page.
- Changing built-in **defaults** touches the validation/normalization tests and any saved
  layout: migrate rather than reset an operator's saved layout.
- Capture evidence at 1920, 1366 and 640, motion on and off, plus a real `pywebview` run.
