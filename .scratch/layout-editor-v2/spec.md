# Presentation layout editor v2 — design spec

Status: completed historical implementation spec (September 5, 2026). Four
implementation agents built the v2 overhaul against disjoint ownership. The
current schema is v3; where this spec is silent, keep the
v1 behaviour and the v1 house rules.

## 0. Why

The v1 editor (commit `ca648c2`) is functionally correct and safe but looks and
feels like a 2005 admin form: a ~600 px preview in a 1220 px window, a plain
list of fifteen buttons, number boxes in 0-to-1 fractions, no undo, no
multi-select, no alignment tools, no free text, no images, no shapes, no board
background, no fonts, no presets, and no way to rename, duplicate, or delete a
stored layout from the UI even though the bridge can delete one. The owner's
verdict: "stuck 20 years in the past".

v2 turns it into a real design surface — a Figma/Canva-class canvas editor for
the spectator board — while keeping every v1 safety property intact:

- The editor still has **no path to a game command**. It changes only where
  and how things are drawn.
- Every **game value** shown on the board is still produced in Python and
  copied, never computed, by JavaScript.
- Validation is still strict in Python, `Save` is still gated on Python's
  verdict, and a malformed `layouts.json` still cannot stop the scoreboard.
- Core operation is still fully offline: no CDN, no network fetch, no fonts or
  images loaded from anywhere but the layout document itself.

## 1. Schema v2 (`src/scoreboard/presentation/layout.py`)

`LAYOUT_SCHEMA_VERSION` becomes **2**. `validate_layout` accepts a document
whose `schema_version` is 1 **or** 2 and always normalizes to 2. A version-1
document gets every new property filled from its default and one **warning**
`SCHEMA_UPGRADED` ("This layout was saved by an earlier version and was
upgraded; save it to keep the upgrade."). Any other version (0, 3, "1", 1.0,
True, missing) is still an error `SCHEMA_VERSION`.

### 1.1 Document shape

```json
{
  "schema_version": 2,
  "name": "Default",
  "safe_area": {"top": 0.04, "right": 0.04, "bottom": 0.04, "left": 0.04},
  "background": {"color": "#000000"},
  "widgets": { "<widget_id>": { ...widget... }, ... },
  "elements": [ { ...element... }, ... ]
}
```

`default_layout()` returns exactly this with `elements: []`,
`background.color == "#000000"`, and every widget carrying the v1 geometry
plus the new style defaults in 1.3. **The built-in default must render
pixel-identical to v1** (same geometry, Arial, no backgrounds, no effects).

### 1.2 `background`

`{"color": "#RRGGBB"}`. Missing → default with warning `MISSING_BACKGROUND`
(same treatment as a missing safe area). Wrong shape or invalid colour →
error `BACKGROUND`. Normalized colour is uppercase 6-digit hex.

### 1.3 Widget properties (v1 set plus these; all optional, all defaulted)

| property | type / range | default | notes |
|---|---|---|---|
| `font_family` | key of `FONT_FAMILIES` | `"arial"` | see 1.5 |
| `letter_spacing` | number, `-0.05..0.30` (em) | `0.0` | |
| `text_transform` | `"none"` \| `"uppercase"` | `"none"` | |
| `text_effect` | `"none"` \| `"shadow"` \| `"outline"` | `"none"` | |
| `background` | `null` \| `"#RRGGBB"` | `null` | box fill behind the text |
| `background_opacity` | number `0.0..1.0` | `1.0` | |
| `border_color` | `null` \| `"#RRGGBB"` | `null` | |
| `border_width` | number `0.0..0.02` (fraction of canvas **width**) | `0.0` | |
| `corner_radius` | number `0.0..0.10` (fraction of canvas width) | `0.0` | |
| `padding` | number `0.0..0.05` (fraction of canvas width) | `0.0` | inner inset |

Invalid values are **errors** with codes `FONT_FAMILY`, `LETTER_SPACING`,
`TEXT_TRANSFORM`, `TEXT_EFFECT`, `BACKGROUND`, `BACKGROUND_OPACITY`,
`BORDER_COLOR`, `BORDER_WIDTH`, `CORNER_RADIUS`, `PADDING`, each naming the
widget by its `WIDGET_LABELS` text like every v1 message. `_KNOWN_WIDGET_PROPERTIES`
grows accordingly so none of them trips `UNKNOWN_PROPERTY`.

`WIDGET_GROUPS: dict[str, str]` assigns each widget to `"Teams"`, `"Clocks"`,
or `"Field"`; `widget_descriptors()` gains `"group"`. Groups: Teams =
home_name, home_score, possession, away_name, away_score; Clocks =
game_clock_label, game_clock_value, play_clock_label, play_clock_value,
quarter; Field = down, distance, ball_on, home_timeouts, away_timeouts.

### 1.4 Elements

`elements` is a **list** (order is not stacking order — `z_index` is). Missing
→ `[]` with **no** warning (an old file simply has none). Not a list → error
`ELEMENTS`. More than `MAX_ELEMENTS = 24` → error `MAX_ELEMENTS`.

Every element:

| property | type / range | notes |
|---|---|---|
| `id` | `^[a-z][a-z0-9_]{0,39}$`, unique among elements, not a `WIDGET_IDS` value | error `ELEMENT_ID` |
| `type` | `"text"` \| `"image"` \| `"box"` | error `ELEMENT_TYPE` |
| `visible` | bool, default `true` | |
| `x`,`y`,`width`,`height` | as widgets (`MIN_WIDGET_WIDTH/HEIGHT` apply) | |
| `z_index` | as widgets | |
| `opacity` | `0.05..1.0`, default `1.0` | error `OPACITY` |
| `background`, `background_opacity`, `border_color`, `border_width`, `corner_radius` | as in 1.3 | |

`type == "text"` additionally: `text` (string; after `strip()` 1..120 chars,
no control characters other than `\n`, at most 3 `\n`; error `TEXT`), and the
full text style set: `color`, `font_scale`, `font_family`, `font_weight`,
`letter_spacing`, `text_transform`, `text_effect`, `text_align`,
`vertical_align`, `padding` — same ranges and defaults as widgets, except
`color` defaults to `"#FFFFFF"`, `font_scale` to `0.03`, `font_weight` to `700`.

`type == "image"` additionally: `src` — a data URI matching
`^data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$`, whose decoded bytes
(`base64.b64decode(..., validate=True)`) are at most `MAX_IMAGE_BYTES =
2_000_000` and start with the matching magic (`\x89PNG`, `\xFF\xD8\xFF`,
`GIF8`, `RIFF....WEBP`); errors `IMAGE_SRC`, `IMAGE_TOO_LARGE`. The decoded
sizes of every image in the layout must total at most `MAX_TOTAL_IMAGE_BYTES =
6_000_000` (error `IMAGES_TOO_LARGE`). `fit`: `"contain"` \| `"cover"` \|
`"fill"`, default `"contain"` (error `IMAGE_FIT`).

`type == "box"`: nothing extra (a box is its background/border/radius).

Unknown property on an element → warning `UNKNOWN_PROPERTY` naming the element
as `Text "…"`, `Image <id>`, or `Box <id>`. Messages name elements that way
throughout (`element_label(element) -> str` helper).

**Placement rules.** A `text` element must sit inside the safe area exactly
like a widget (`OUTSIDE_SAFE_AREA`). An `image` or `box` must sit inside the
canvas (`0..1` on both axes, error `OUTSIDE_CANVAS`) but **may** cross the safe
area — a full-bleed backdrop is the main reason they exist. **Elements never
take part in overlap checking**: a panel behind the scores is the point.
Widget-versus-widget overlap rules are unchanged.

`clamp_layout` repairs element geometry the same way it repairs widgets (text
elements into the safe area, image/box into the canvas), passes every other
element property through, drops an element with no usable `id`/`type`, and
truncates the list to `MAX_ELEMENTS`.

### 1.5 Font families

```python
FONT_FAMILIES: Final[dict[str, str]] = {
    "arial":       "Arial, Helvetica, sans-serif",
    "arial_black": "'Arial Black', Arial, sans-serif",
    "impact":      "Impact, 'Arial Black', sans-serif",
    "bahnschrift": "Bahnschrift, 'Segoe UI', Arial, sans-serif",
    "segoe":       "'Segoe UI', Segoe, Arial, sans-serif",
    "segoe_black": "'Segoe UI Black', 'Segoe UI', Arial, sans-serif",
    "consolas":    "Consolas, 'Courier New', monospace",
    "georgia":     "Georgia, 'Times New Roman', serif",
    "verdana":     "Verdana, Geneva, sans-serif",
    "trebuchet":   "'Trebuchet MS', Arial, sans-serif",
}
FONT_FAMILY_LABELS = {"arial": "Arial", "arial_black": "Arial Black", "impact": "Impact",
    "bahnschrift": "Bahnschrift", "segoe": "Segoe UI", "segoe_black": "Segoe UI Black",
    "consolas": "Consolas", "georgia": "Georgia", "verdana": "Verdana", "trebuchet": "Trebuchet MS"}
```

All are Windows system fonts; nothing is downloaded. `board.js` mirrors
`FONT_FAMILIES` as a strict-JSON literal (section 3) and the contract test
compares them.

### 1.6 `limits()` additions

`min_letter_spacing`, `max_letter_spacing`, `max_border_width`,
`max_corner_radius`, `max_padding`, `min_opacity`, `max_elements`,
`max_text_length` (120), `max_text_lines` (4), `max_image_bytes`,
`max_total_image_bytes`, `font_families` (list of `{"id","label"}` in the
order above), `text_transforms`, `text_effects`, `image_fits`,
`element_types`. `widget_groups` (ordered list `["Teams","Clocks","Field"]`).

### 1.7 Presets

`preset_descriptors() -> list[dict]` returns, in this order, dicts with
`id`, `name`, `description`, `layout` (a full valid v2 document, `name` set to
the preset name):

1. `classic` — "Classic": exactly `default_layout("Classic")`.
2. `broadcast` — "Broadcast bar": a dark rounded box element
   (`#101820`, radius 0.012) spanning the bottom of the safe area (roughly
   y 0.78–0.96); inside it, left to right: home name + score, game clock,
   away name + score; quarter, down, distance, and ball on sit in a slim row
   just above the bar; play clock label/value at the right end of that row.
   The upper ~70 % of the board is empty black — "leaves the top of the board
   free for future media".
3. `big_score` — "Big score": both scores at `font_scale` 0.20 filling the
   top half beside each name, game clock at 0.12 lower-left, play clock at
   0.10 lower-right with its label above it, quarter centred at the bottom,
   down/distance/ball on in a small bottom row.
4. `tigers` — "Tigers navy": brand baseline from `brand-baseline/palette.json`.
   Background `#071B3A`; a red (`#C8242B`) box element across the very top
   (y 0–0.025, full width) and another across the very bottom; a
   `#0D2B5A` rounded box behind each score; names in `bahnschrift`
   uppercase; possession in `#FFB703`; muted text in `#DDE7F4`.

Every preset must validate with `ok == True` and **zero warnings**. A unit
test asserts that for all of them, and that ids are unique.

## 2. Bridge and storage

### 2.1 `src/scoreboard/infrastructure/layouts.py`

Add `rename_layout(paths, old, new)` and `duplicate_layout(paths, name,
new_name)`, both returning `(LayoutLibrary, LayoutValidation)` like their
siblings. `"Default"` cannot be renamed (error `DEFAULT_PROTECTED`) but can be
duplicated. Renaming to an existing name is refused (`LAYOUT_EXISTS`);
duplicating to an existing name is refused the same way. Renaming the active
layout keeps it active under the new name; duplicating makes the copy active.
`MAX_STORED_LAYOUTS` still applies to duplicate. Everything is atomic and
writes nothing on refusal, as today.

### 2.2 `src/scoreboard/host/layout_bridge.py`

`PresentationLayouts` gains `rename(old, new)` and `duplicate(name, new_name)`
following the `select`/`delete` pattern (publish on success, diagnostics note
on refusal). `state()` gains `"presets": layout_module.preset_descriptors()`.

`LayoutEditorBridge` public surface becomes exactly:
`get_snapshot, layout_state, preview_layout, clamp_layout, reset_widget,
save_layout, select_layout, delete_layout, rename_layout, duplicate_layout,
reset_layout`. Still no `command`, still no method named after any
`CommandType` value. Update the pinned set in `test_layout_bridge.py`.

## 3. Renderer (`views/shared/board.js`, `board.css`, `views/spectator/*`)

House rules unchanged and enforced by `tests/integration/test_spectator_layout_render.py`:
board.js and spectator.js contain none of `Math.`, `toFixed`, `parseInt`,
`parseFloat`, `setInterval`, `revision++`, `api.command`; the spectator page
has no `<button`, `<input`, `<dialog`, `data-command`, `data-action`. The
editor contract test additionally forbids the substrings `handle`, `guide`,
`drag`, `resize` **anywhere in board.js or board.css, comments included,
case-insensitively** — an editing affordance must never leak onto the LED
wall. (Use "grip", "pointer", "scale" or rephrase.) Hex → rgb conversion uses
`Number('0x' + pair)`, never `parseInt`.

Strict-JSON literals mirrored from Python and checked by the contract test:
`WIDGET_IDS`, `WIDGET_FIELDS`, `WIDGET_TEXTS`, `OPTIONAL_WIDGET_IDS`,
`DEFAULT_LAYOUT` (now v2, with every widget carrying the 1.3 defaults,
`"background": {"color": "#000000"}`, `"elements": []`, `"schema_version": 2`),
plus new `FONT_FAMILIES`. Key order inside `DEFAULT_LAYOUT` does not matter
(the test compares parsed values) but keep it readable.

Behaviour:

- `build(container)` sets `container.dataset.boardRoot = "1"` and builds the
  widget nodes as today. Every placed node — widget or element — also carries
  `data-item="<id>"`. Widgets keep `data-widget`; elements get
  `data-element="<id>"` and `data-element-type`.
- `applyLayout(container, layout)` finds the board root as
  `container.querySelector('[data-board-root]') || container`, then
  **reconciles** element nodes: creates missing ones, removes ones no longer in
  `layout.elements`, updates the rest. Element nodes are **inserted before the
  first widget node**, so at equal `z_index` a widget draws above an element
  (a backdrop added at z 0 sits behind the scores without any restacking).
  Text elements use `class="widget element element-text"` with the same
  `.widget-text` child as widgets so `board.css` styles them identically;
  image elements are `class="element element-image"` containing an `<img
  alt="">` whose `src` is copied from the layout and whose `object-fit` comes
  from `fit`; boxes are `class="element element-box"`.
- Custom properties set per node: v1's `--x --y --w --h --fs --color --fw --ta
  --va` plus `--ff` (the CSS stack from `FONT_FAMILIES`), `--ls` (em number),
  `--tt` (`none`/`uppercase`), `--bg` (an `rgba(...)` string or `transparent`,
  combining `background` and `background_opacity`), `--bc` (border colour or
  `transparent`), `--bw`, `--br`, `--pad` (fractions, applied as
  `calc(var(--canvas-width) * var(--bw))` etc.), `--op` (opacity, elements).
  Text effect is a class: `effect-shadow` / `effect-outline`.
- Board background: paint it on the **container** passed to `applyLayout`
  (the `#canvas` on both pages) with `container.style.background = color`, so
  the pregame/halftime event board, which shares the canvas, gets the same
  ground. Do not paint it on the board root.
- `applyModel` is unchanged for widgets and ignores elements entirely: element
  text is copied once from the layout in `applyLayout`, never from the model.
  Update the header comment: JavaScript copies text from exactly three places
  — the view model, `WIDGET_TEXTS`, and a validated layout's `elements[].text`
  — and computes none of it.
- Tolerance: a malformed element entry (no id, unknown type, bad src) is
  skipped without throwing, exactly as a malformed widget is today.
- `board.css`: `.element-image img { width:100%; height:100%; object-fit:
  var(--fit); pointer-events:none; user-select:none; }`; `.effect-shadow
  .widget-text { text-shadow: 0 0.06em 0.18em rgba(0,0,0,.85) }`;
  `.effect-outline .widget-text { -webkit-text-stroke: 0.04em #000;
  paint-order: stroke fill }`; `.widget { font-family: var(--ff); letter-spacing:
  calc(var(--ls) * 1em); text-transform: var(--tt); background: var(--bg);
  border: calc(var(--canvas-width) * var(--bw)) solid var(--bc); border-radius:
  calc(var(--canvas-width) * var(--br)); padding: calc(var(--canvas-width) *
  var(--pad)); }` — with sensible fallbacks in every `var()` so a v1 layout
  pushed by an older host still draws.
- `spectator.css` keeps `--canvas-width`; nothing else changes on the
  spectator page except that the canvas background now follows the layout.

## 4. Editor (`views/layout/`)

### 4.1 Files

`index.html`, `layout.css`, and JavaScript split across `layout.js`
(bootstrap, bridge calls, state adoption), `editor-state.js` (draft, history,
selection, element factories), `editor-canvas.js` (gestures, handles, guides,
marquee, zoom), `editor-panels.js` (layers, inspector, library menu, presets,
issues). They share one namespace object `window.LayoutEditor`. All are plain
ES5-compatible scripts with `'use strict'`, loaded in that dependency order
after `../shared/render.js` and `../shared/board.js`. No modules, no build.

`tests/integration/test_layout_editor_contract.py` is updated to read **every**
`.js` file in the editor directory for the forbidden-token and bridge-method
checks, so splitting cannot weaken them.

### 4.2 Hard constraints (enforced by that contract test — read it first)

- No `data-command` in HTML; no `api.command`, no `.command(` in code.
- **No `CommandType` value as a substring anywhere in the HTML or in the
  comment-stripped JS.** The list includes `undo`, `set_score`, `new_game`,
  `end_game`, `set_down`, `set_distance`, `set_quarter`, `timeout_used`, and
  more (`scoreboard.domain.commands.CommandType`). Consequences: the history
  feature is `history_back` / `history_forward` in identifiers and data-actions,
  and visible labels use the capitalized words "Undo" / "Redo" only (Python's
  `in` is case-sensitive; the lowercase `undo` must not occur).
- Every `api.<name>(` call must be a real `LayoutEditorBridge` method (2.2).
- No `toFixed`, `parseInt`, `parseFloat`, `setInterval` in any editor script.
  Percent display is `String(Math.round(value * 1000) / 10)`; input is
  `Number(input.value) / 100`.
- `Math.` may only be followed by `round`. Use ternaries/helpers for min, max,
  abs, floor.
- The comment-stripped code must not contain `.display`, `_display`,
  `.seconds`, `.score`. So: never `element.style.display = …` (use the
  `hidden` attribute), never a variable ending in `.score`.
- No `window.prompt`, `window.alert`, `window.confirm`, nor the substrings
  `prompt(`, `alert(`, `confirm(` — every confirmation is inline UI.
- The HTML must contain (lowercased) "never changes", "scores", and "clocks":
  keep the one-line scope note.
- These `data-action` names must survive: `save`, `save_as_open`, `discard`,
  `reset_widget`, `reset_layout_confirm`, `clamp`, `nudge_up`, `nudge_down`,
  `nudge_left`, `nudge_right`, `raise`, `lower`. `data-handle`, `pointerdown`,
  `shiftKey`, and the four `Arrow*` key names must appear in the scripts.
- The widget list must be generated from `layout_state().widgets` — no widget
  id or label literal in the HTML. Limits come from `layout_state().limits`.
- `data-prop` attributes on controls declare the editable property set; the
  contract test's `EDITABLE_PROPERTIES` is updated to the v2 set (1.3 + element
  props `text`, `opacity`, `fit`, and the board props declared as
  `data-board-prop="background_color"` and `data-board-prop="safe_top"` etc.).

### 4.3 Layout of the window (1220×780 default, 980×620 minimum)

```
┌ toolbar ───────────────────────────────────────────────────────────────────┐
│ ◼ Layout designer   [Default ▾]  ● unsaved   ↶ ↷   + Text  + Image  + Box  │
│                                     Presets ▾   zoom [−][100%][+][Fit]  Save │
├ layers 240px ┬ canvas (flexible) ────────────────┬ inspector 312px ────────┤
│ BOARD        │                                   │ (context sections)      │
│ ▸ TEAMS      │      dark dotted work area,       │                         │
│   ○ Home…    │      16:9 canvas centred,         │                         │
│ ▸ CLOCKS     │      safe-area dashed outline,    │                         │
│ ▸ FIELD      │      selection + 8 grips, guides, │                         │
│ ▸ ELEMENTS   │      marquee, drag readout chip   │                         │
├ status bar ──┴───────────────────────────────────┴─────────────────────────┤
│ ✓ No problems · 15 fields · 2 elements     [issues ▴]   scope note          │
└────────────────────────────────────────────────────────────────────────────┘
```

- **Toolbar.** Product name "Layout designer". The layout name is a menu
  button (`data-action="library_menu"`) listing stored layouts (select on
  click) and, below a divider: Save, Save as…, Duplicate…, Rename…, Delete…,
  Reset to built-in… . Save as / Duplicate / Rename / Delete each open a small
  inline popover with a text field and Confirm/Cancel (no browser dialogs).
  Delete and Reset require the inline confirm. "Default" shows Rename and
  Delete disabled with a tooltip "The Default layout is always available".
- **Undo / Redo** icon buttons (`history_back` / `history_forward`, Ctrl+Z,
  Ctrl+Y and Ctrl+Shift+Z), disabled when the stack is empty. History holds
  the last 100 drafts. A gesture, a nudge, a restack, an add/duplicate/
  delete, a preset, a clamp, a reset, and every `change` event on a control
  push one entry; `input` events update the draft live without pushing.
- **Add** buttons: `add_text` (a text element "NEW TEXT" 0.24×0.08 at the
  canvas centre, z 10, colour white, `font_scale` 0.03, bold), `add_image`
  (opens a hidden `<input type="file" accept="image/png,image/jpeg,image/gif,
  image/webp">`; the file is read with `FileReader.readAsDataURL`, refused
  inline if larger than `limits.max_image_bytes` or not an accepted type, then
  measured with an `Image` so the element keeps its aspect ratio at 0.30
  canvas width, z 0, `fit: contain`), `add_box` (0.30×0.20 at the centre, z 0,
  fill `#1B222B`, radius 0.01). Dropping an image file onto the canvas does the
  same as `add_image` (`dragover`/`drop` on the canvas are the editor's, and
  `dragstart` is prevented so the browser never ghost-drags an `<img>`).
  New elements get ids `text_1`, `image_1`, `box_1` … skipping ids already in
  use, and become the selection.
- **Presets** menu: one entry per `state.presets` with name and description;
  choosing one replaces the draft (after an inline "Replace the current draft?"
  confirm if the draft is dirty), keeps the current stored layout name, marks
  dirty, pushes history.
- **Zoom**: `zoom_out`, `zoom_in`, `zoom_fit`, and a readout. Levels 50, 75,
  100, 150, 200 % of the fit size. The fit size is measured from the canvas
  panel (`ResizeObserver`, or `resize` on window) and written to
  `--preview-width` on `#canvas`. Above fit the panel scrolls; the canvas is
  centred in both axes when smaller.
- **Save** is the one primary (accent-filled) button. Disabled while errors
  exist. Ctrl+S saves. The dirty dot sits beside the layout name.

- **Layers rail.** Top row "Board" (selects the board: inspector shows
  background colour, safe-area insets, presets). Then collapsible groups from
  `limits.widget_groups` with widgets from `state.widgets` filtered by
  `descriptor.group`, then "Elements" listing `draft.elements` (by descending
  `z_index`, then insertion). Each row: a 16 px type icon (text/image/box/
  field), the label (elements show their text, image file name if known, or
  id), an eye toggle button (`data-toggle-visible`) that flips `visible`
  without changing selection, and for elements a trash button
  (`data-delete-element`). Hidden rows are dimmed and say "hidden" in the
  tooltip and via `aria-pressed` on the eye. The selected row is highlighted;
  Shift+click adds to the selection.
- **Canvas.** The work area background is a subtle dot grid (`radial-gradient`
  dots at 16 px) on `#0d1014`; the 16:9 canvas has a 1 px `#2a313b` border and a
  soft shadow; the safe area is a dashed `#3a4452` outline with a tiny "safe
  area" label at its top-left corner. Selection: 1.5 px accent outline; eight
  grips (single selection only) as 9 px squares with a dark fill and accent
  border; multi-selection draws an outline per item and a dashed group box.
  Guides as today. While dragging or resizing, a readout chip near the
  pointer shows `X 24.0%  Y 12.0%` or `W 38.0%  H 11.8%`. Hidden items still
  render at 28 % opacity with a dotted border (as v1) and are selectable.
  Clicking empty canvas clears the selection; dragging on empty canvas draws a
  marquee and selects every visible item it intersects. Right-click opens a
  small context menu: Bring to front, Bring forward, Send backward, Send to
  back, Duplicate (elements), Delete (elements), Hide/Show, Reset (widgets).
- **Multi-select.** Shift+click (rail or canvas) toggles membership; the last
  clicked is primary. Dragging any selected item moves the whole selection by
  one delta, clamped so no member leaves its boundary (safe area for widgets
  and text, canvas for image/box). Arrow nudges move all. Delete removes the
  selected elements (widgets in the selection are left alone). Escape clears.
- **Inspector** (right). Header shows the selection ("Home score", "Text
  “HOMECOMING”", "3 items", or "Board"). Sections, each with a small
  uppercase title:
  1. *Position & size* — X, Y, W, H as percent inputs in a 2×2 grid (`data-prop`
     x/y/width/height; values shown in percent, stored as fractions), then a
     compact arrange strip: align left / centre / right / top / middle /
     bottom (icons; `align_left` … `align_bottom`; with one item selected these
     align to the safe area, with several they align to each other),
     distribute horizontally / vertically (`distribute_h` / `distribute_v`,
     enabled with three or more), and the four nudge arrows (`nudge_*`, kept
     for the contract test, small).
  2. *Layer* — Bring to front / forward / backward / to back (`to_front`,
     `raise`, `lower`, `to_back`), the numeric `z_index` (`data-prop`), and the
     eye/visible checkbox (`data-prop="visible"`).
  3. *Text* (widgets and text elements) — for text elements a textarea
     (`data-prop="text"`, `maxlength` from limits); font family select
     (`data-prop="font_family"`, options from `limits.font_families`), weight
     select with names (Regular 400 … Black 900), size as percent of board
     width (`font_scale`), letter spacing (`letter_spacing`, step 0.01),
     transform toggle "Aa / AA" (`text_transform`), effect segmented control
     (`text_effect`), colour (swatch + hex text, `data-prop="color"`), alignment
     icon groups (`text_align`, `vertical_align`). Static labels show the v1
     note that their wording is fixed.
  4. *Fill & border* — fill on/off + colour + opacity slider (`background`,
     `background_opacity`), border colour + width (`border_color`,
     `border_width`), corner radius (`corner_radius`), padding (`padding`; text
     only), element opacity (`opacity`; elements only).
  5. *Image* (image elements) — thumbnail, "Replace image…" (`replace_image`),
     fit select (`fit`), size readout.
  6. *Actions* — Reset this widget (`reset_widget`), Duplicate (`duplicate`),
     Delete (`delete_element`), Fit to safe area (`clamp`, whole layout).
  Board selected: background colour (`data-board-prop="background_color"`),
  the four safe-area insets as percent (`data-board-prop="safe_top"` …), and
  the presets gallery as cards (name, description, an "Apply" button).
- **Status bar.** Left: `✓ No problems` or `⚠ 2 errors · 1 warning`; clicking
  toggles an issues drawer that slides up over the canvas bottom listing each
  issue as today (click selects the item). Right: the scope note "Changes how
  the board looks. It never changes scores, clocks, or any other game value."
  `Reset entire layout…` lives in the library menu, not here.

### 4.4 Visual language

Modern, dense, dark design-tool aesthetic. Tokens (in `layout.css`):

```
--bg:#0d1014; --surface:#14181e; --surface-2:#1a2028; --line:#262d37;
--line-strong:#333c48; --ink:#e9edf2; --ink-2:#a6b0bd; --ink-3:#6f7a88;
--accent:#4da3ff; --accent-ink:#0b1420; --ok:#35c48a; --warn:#ffbf47;
--danger:#ff6b6b; --radius:8px; --radius-sm:5px;
font-family: "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif; 13px base.
```

Rules: 8 px spacing scale; section titles 11 px, 600, letter-spacing .08em,
`--ink-3`; inputs 28 px tall with `--surface-2` fill, `--line` border, accent
focus ring; icon buttons 28×28 with inline SVG 16 px stroke icons (1.75 px
stroke, `currentColor`) — text, image, box, eye, eye-off, trash, undo/redo
arrows, align ×6, distribute ×2, layer up/down, zoom; segmented controls for
enumerations; the primary Save button accent-filled; hover states on every
interactive row; no emoji, no external icon fonts, no images from a CDN.
Every control has a `title` and, where it is icon-only, an `aria-label`. Focus
rings stay visible. Nothing conveys state by colour alone (hidden rows say so;
errors carry the word).

Keyboard: arrows nudge (Shift ×4), Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z history,
Ctrl+D duplicate, Delete/Backspace remove elements, Escape clears selection or
closes a menu/popover, Ctrl+S save, Ctrl+A select all visible, `+`/`-` zoom
when focus is not in a field. Arrows and Delete never fire while a text
field has focus.

### 4.5 Bridge conversation

Unchanged pattern: `layout_state()` on load and after library actions;
`get_snapshot()` for the preview values; `preview_layout(draft)` after every
committed change (drafts with images can be a few MB — that is acceptable, but
never call it per pointer-move); `save_layout(name, draft)`,
`select_layout(name)`, `delete_layout(name)`, `rename_layout(old, new)`,
`duplicate_layout(name, new)`, `reset_layout()`, `reset_widget(id, draft)`,
`clamp_layout(draft)`. `window.applyLayout` / `window.applyView` host pushes
behave as in v1 (a dirty draft is never replaced behind the operator's back).

### 4.6 Browser test

`tests/ui/layout_editor.cjs` and `test_layout_editor_browser.py` are updated
to the new UI (ids, actions, percent inputs) and extended with: add text
element, add box, history back/forward, multi-select drag, align, delete
element. They cannot run on this machine (no Node/Playwright) — keep them
faithful anyway.

## 5. Docs (after implementation)

`docs/UX_AND_LAYOUT.md` §10 (rewrite 10.1–10.8 for v2; the "no free text/
images" exclusions move to a "what v2 adds" list; the event-countdown board
remains out of scope), `docs/MVP_REQUIREMENTS.md` line ~279, `docs/PHASE_2_BACKLOG.md`
"Presentation layout editor" section, `docs/ARCHITECTURE.md` §9 layouts.json
paragraph (images stored inline as data URIs, size caps), `PROJECT_ROADMAP.md`
(a "Phase 2 owner request 3 — v2" entry, decision-log rows superseding the
"numeric fields only" decision, and the verification table row). Distinguish
verified from claimed.

## 6. Non-goals (still)

OBS/video/animation/sponsor rotation, networking, per-resolution layouts,
editing the operator window, editing the pregame/halftime countdown board,
binding a text element to a game field, SVG images (script risk), fonts that
are not already installed on Windows.

## 7. Verification plan

- Focused suites per agent, then the full discovery run compared with the
  baseline in `PROJECT_ROADMAP.md` (16 failures + 3 errors on `2af419d`).
- The orchestrator drives the editor in the preview browser against a stub
  bridge (screenshots) and in the real pywebview runtime (open the editor from
  `WindowHost`, add elements through `evaluate_js`, save, read `layouts.json`,
  confirm the spectator window received the push).

## 8. Open questions for the owner (not blocking)

- Should a text element be allowed to bind to a game field later (e.g. a
  custom label that follows the home team name)? v2 says no.
- Is 2 MB per image enough for the stadium backdrop? A 1920×1080 JPEG is
  typically 200–600 KB; PNG with alpha can exceed 2 MB.

## 9. File ownership

| Agent | Owns | Must not touch |
|---|---|---|
| A schema | `src/scoreboard/presentation/layout.py`, `tests/unit/test_layout_schema.py` | everything else |
| B renderer | `src/scoreboard/views/shared/board.js`, `board.css`, `src/scoreboard/views/spectator/*`, `tests/integration/test_spectator_layout_render.py` | editor, Python |
| C editor | `src/scoreboard/views/layout/*`, `tests/integration/test_layout_editor_contract.py`, `tests/ui/layout_editor.cjs`, `tests/ui/test_layout_editor_browser.py` | renderer, Python |
| D bridge | `src/scoreboard/infrastructure/layouts.py`, `src/scoreboard/host/layout_bridge.py`, `tests/integration/test_layout_bridge.py`, `tests/integration/test_layout_persistence.py` | schema module, views |
| E review | reads everything; edits only `docs/*.md`, `PROJECT_ROADMAP.md`, `README.md` and files the orchestrator names | — |
