# Pre-game and halftime screens in the layout designer — spec (schema v3)

Status: completed historical implementation spec (September 6, 2026). Five
agents built the schema-v3 screens against disjoint ownership. Where this spec
is silent, keep the v2
behaviour and the v2 house rules (`.scratch/layout-editor-v2/spec.md`).

## 0. Goal

Today the spectator page draws the pre-game and halftime "event board"
(countdown title, countdown, phase, warmup line, score line) from fixed HTML
in `views/spectator/index.html`; only the in-game board is a layout. The
owner wants the pre-game and halftime screens customizable "just like the
scoreboard", plus a few presets for each.

Design: one stored layout document now describes **three screens**. The
in-game screen keeps its v2 shape at the top level of the document (so every
existing test, file, and push keeps working). Two new screens live under
`screens.pregame` and `screens.halftime`, each a complete mini-document with
its own safe area, background, widgets (a *different* widget set: the event
widgets) and free elements. The renderer builds either "kind" of board; the
spectator page picks the screen from `lifecycle`; the editor gains a
Game / Pre-game / Halftime switcher and per-screen presets.

Unchanged safety properties: the editor still has no path to a game command;
every game value is produced in Python and copied by JavaScript; validation
is strict in Python; a malformed `layouts.json` cannot stop the scoreboard;
no network, no CDN, no fonts or images from outside the document.

## 1. Schema v3 (`src/scoreboard/presentation/layout.py`) — Agent A

`LAYOUT_SCHEMA_VERSION = 3`; `_ACCEPTED_SCHEMA_VERSIONS = (1, 2, 3)`. A v1 or
v2 document is accepted, upgraded, and gets the one warning `SCHEMA_UPGRADED`
(same text as today). The `SCHEMA_VERSION` error text becomes
`"schema_version must be 1, 2, or 3; got …"`. Anything else is still refused.

### 1.1 Document shape

```json
{
  "schema_version": 3,
  "name": "Default",
  "safe_area": {...}, "background": {...}, "widgets": {...game widgets...}, "elements": [...],
  "screens": {
    "pregame":  {"safe_area": {...}, "background": {...}, "widgets": {...event widgets...}, "elements": [...]},
    "halftime": {"safe_area": {...}, "background": {...}, "widgets": {...event widgets...}, "elements": [...]}
  }
}
```

Constants:

```python
SCREEN_IDS: Final[tuple[str, ...]] = ("game", "pregame", "halftime")
EVENT_SCREEN_IDS: Final[tuple[str, ...]] = ("pregame", "halftime")
SCREEN_LABELS = {"game": "Game", "pregame": "Pre-game", "halftime": "Halftime"}
SCREEN_KINDS = {"game": "game", "pregame": "event", "halftime": "event"}
WIDGET_KINDS: Final[tuple[str, ...]] = ("game", "event")
```

A **kind** names a widget registry. The existing `WIDGET_IDS`,
`WIDGET_LABELS`, `WIDGET_FIELDS`, `WIDGET_TEXTS`, `OPTIONAL_WIDGET_IDS`,
`WIDGET_GROUPS`, `WIDGET_GROUP_ORDER` are the `"game"` registry and keep
their names and values exactly. The `"event"` registry is new:

```python
EVENT_WIDGET_IDS = ("home_name", "home_score", "away_name", "away_score",
                    "event_phase", "event_title", "event_clock", "warmup")
EVENT_WIDGET_LABELS = {
    "home_name": "Home team name", "home_score": "Home score",
    "away_name": "Away team name", "away_score": "Away score",
    "event_phase": "Phase label", "event_title": "Countdown title",
    "event_clock": "Countdown", "warmup": "Warmup line",
}
EVENT_WIDGET_FIELDS = {
    "home_name": "teams.home.name", "home_score": "teams.home.score",
    "away_name": "teams.away.name", "away_score": "teams.away.score",
    "event_phase": "clocks.event.phase", "event_title": "clocks.event.title",
    "event_clock": "clocks.event.display", "warmup": "clocks.event.warmup_display",
}
EVENT_WIDGET_TEXTS: dict[str, str] = {}          # no static labels on event screens
EVENT_OPTIONAL_WIDGET_IDS = frozenset({"warmup"})  # hidden when the value is empty/None
EVENT_WIDGET_GROUPS = {"home_name": "Teams", "home_score": "Teams", "away_name": "Teams",
    "away_score": "Teams", "event_phase": "Countdown", "event_title": "Countdown",
    "event_clock": "Countdown", "warmup": "Countdown"}
EVENT_WIDGET_GROUP_ORDER = ("Teams", "Countdown")
```

(`clocks.event.warmup_display` is a new view-model string Agent D adds:
`"Warmup follows: 3:00"` while the halftime countdown is above the warmup
threshold, else `None`. It replaces the two-part "Warmup follows: <span>"
line the old HTML drew.)

Implement the registries as one small frozen dataclass `WidgetRegistry(ids,
labels, fields, texts, optional, groups, group_order)` and
`WIDGET_REGISTRIES: dict[str, WidgetRegistry] = {"game": ..., "event": ...}`,
with `registry_for(kind)`. The module-level game constants stay as the
public names (the registry just references them).

### 1.2 Event widget defaults

Two default screens, `default_screen(screen_id)`. Both use the default safe
area (0.04 all round) and background `#000000`, `elements: []`, and every
widget carries `_STYLE_DEFAULTS`, `z_index 0`, `color "#FFFFFF"`,
`vertical_align "middle"`. Geometry (fractions; `fs` = font_scale):

| widget | pregame visible | halftime visible | x | y | w | h | fs | weight | text_align |
|---|---|---|---|---|---|---|---|---|---|
| event_phase | false | true | 0.30 | 0.05 | 0.40 | 0.09 | 0.045 | 700 | center |
| event_title | true | true | 0.10 | 0.15 | 0.80 | 0.10 | 0.050 | 400 | center |
| event_clock | true | true | 0.10 | 0.26 | 0.80 | 0.32 | 0.140 | 700 | center |
| warmup | false | true | 0.25 | 0.59 | 0.50 | 0.07 | 0.035 | 400 | center |
| home_name | true | true | 0.04 | 0.72 | 0.30 | 0.12 | 0.040 | 700 | right |
| home_score | true | true | 0.35 | 0.70 | 0.12 | 0.16 | 0.070 | 700 | center |
| away_score | true | true | 0.53 | 0.70 | 0.12 | 0.16 | 0.070 | 700 | center |
| away_name | true | true | 0.66 | 0.72 | 0.30 | 0.12 | 0.040 | 700 | left |

The geometry is identical for both screens; only `visible` differs. These
reproduce today's centred event board closely enough (title, big countdown,
score line; phase and warmup only at halftime). Both must validate `ok` with
zero warnings. `default_layout()` now includes `"screens": {"pregame":
default_screen("pregame"), "halftime": default_screen("halftime")}`.
`default_widget(widget_id)` is unchanged (game); add
`default_screen_widget(screen_id, widget_id)`.

### 1.3 Validation

Refactor the widget/element/overlap logic so it validates **one screen**
given a registry and a screen id: `_validate_screen(raw, screen_id) ->
(normalized_screen | None, errors, warnings)`. The top level of the document
is validated as the `"game"` screen with the *existing* messages and codes
(no prefix — the existing tests keep passing). Each event screen's messages
are prefixed with its label: `"Pre-game: Countdown must sit inside the safe
area."`, `"Halftime: …"`.

`LayoutIssue` gains a field `screen: str | None = None` (after `severity`;
positional construction of existing call sites stays valid) and `to_dict()`
includes `"screen"`. Every issue raised inside a screen carries that screen's
id (`"game"` too); document-wide issues (`SCHEMA_VERSION`, `LAYOUT_NAME`,
`SCREENS`…) carry `None`.

`screens` handling: missing → filled from defaults with **one** warning
`MISSING_SCREENS` ("The pre-game and halftime screens were missing and were
filled with their defaults.") — but **not** when the document is a v1/v2
upgrade (then `SCHEMA_UPGRADED` already says it). Not a dict → error
`SCREENS`. Unknown key inside → warning `UNKNOWN_SCREEN`. A single screen
missing → warning `MISSING_SCREEN` (filled from its default); not a dict →
error `SCREEN`. Inside a screen the rules are exactly the game rules against
the event registry: unknown widget ids warn, missing ones fill with that
screen's default, elements may not reuse that screen's widget ids, element
ids are unique per screen (the same id may appear on different screens),
`MAX_ELEMENTS` and `MAX_TOTAL_IMAGE_BYTES` apply **per screen**.

Normalized output always carries all three screens in canonical key order:
`schema_version, name, safe_area, background, widgets, elements, screens`
with `screens` ordered `pregame, halftime`.

`clamp_layout` / `_clamp_layout` repair every screen the same way they repair
the top level (per-screen safe area). `reset_widget(layout, widget_id,
screen="game")` resets one widget on one screen to that screen's default;
an unknown screen or widget id returns the normalized layout unchanged.

`widget_descriptors(kind="game")` returns the registry's descriptors (same
dict shape as today, `default` from the game defaults for `"game"` and from
the **pregame** defaults for `"event"`). New `screen_descriptors()` returns,
in `SCREEN_IDS` order:

```python
{"id": "pregame", "label": "Pre-game", "kind": "event",
 "widgets": [...widget_descriptors("event") with "default" taken from THIS screen's defaults...],
 "widget_groups": ["Teams", "Countdown"]}
```

`supported_widget_ids(view_model, kind="game")` gains the kind argument.

`limits()` gains `"screens": [{"id","label","kind"}, ...]` and
`"event_widget_groups": ["Teams", "Countdown"]`; `"widget_groups"` stays the
game list.

### 1.4 Presets

`preset_descriptors()` keeps its shape (`id, name, description, layout`) and
the same four ids, but each `layout` is a full v3 document whose screens
match the preset's style:

- `classic` → default screens.
- `broadcast` → the broadcast screen presets (below).
- `big_score` → `pregame_matchup` + `halftime_score_first`.
- `tigers` → the tigers screen presets.

New `screen_preset_descriptors() -> dict[str, list[dict]]` keyed by event
screen id; each entry is `{"id", "name", "description", "screen"}` where
`screen` is a complete, normalized screen mini-document (validate it inside a
full document and pull it back out, mirroring `_normalized_preset`). Ids are
globally unique across game presets and screen presets.

Pre-game presets, in this order:

1. `pregame_classic` — "Classic": exactly `default_screen("pregame")`.
2. `pregame_matchup` — "Matchup": both team names big (`font_scale` 0.075,
   uppercase, weight 900) filling the upper half left and right (home
   right-aligned, away left-aligned), a text element `"VS"` (`font_scale`
   0.05, colour `#FFB703`, weight 900) centred between them, the countdown
   title small above the countdown, the countdown (`font_scale` 0.12) in the
   lower half, scores in a small bottom row (`font_scale` 0.05). Phase and
   warmup hidden.
3. `pregame_broadcast` — "Broadcast bar": a dark rounded box element
   (`#101820`, radius 0.012) spanning the bottom of the safe area (y about
   0.78–0.96); inside it, left to right: home name + score, the countdown,
   away score + name; the countdown title in a slim row just above the bar.
   Upper ~70 % empty black — leaves the top free for future media.
4. `pregame_tigers` — "Tigers navy": background `#071B3A`; red (`#C8242B`)
   box elements across the very top (y 0–0.025, full width) and the very
   bottom; a `#0D2B5A` rounded box behind the countdown; names in
   `bahnschrift` uppercase; title in `#DDE7F4`; countdown white; scores in
   `#FFB703`.

Halftime presets, in this order:

1. `halftime_classic` — "Classic": exactly `default_screen("halftime")`.
2. `halftime_score_first` — "Score first": scores at `font_scale` 0.16 beside
   each name in the top half, the phase label (`event_phase`) centred below
   them, the countdown (`font_scale` 0.10) and the warmup line at the
   bottom; title hidden.
3. `halftime_broadcast` — "Broadcast bar": as the pre-game one, with the
   phase label at the left end of the slim row and the warmup line at its
   right end.
4. `halftime_tigers` — "Tigers navy": as the pre-game one with phase in
   `#FFB703` and the warmup line in `#DDE7F4`.

Every preset (full and screen) must validate `ok == True` with **zero
warnings** — no overlaps between visible widgets, everything inside the safe
area. Unit tests assert that, the ordering, and id uniqueness.

### 1.5 Tests (`tests/unit/test_layout_schema.py`)

Update every `schema_version == 2` expectation to 3; add tests for: v2
upgrade fills screens with only `SCHEMA_UPGRADED`; v3 without screens →
`MISSING_SCREENS`; a bad screen → error with the `"Halftime: "` prefix and
`issue.screen == "halftime"`; per-screen element id uniqueness; per-screen
`MAX_ELEMENTS`; `clamp_layout` repairs a pregame widget; `reset_widget(...,
screen="halftime")`; `screen_descriptors()` shape; presets and screen
presets valid with zero warnings; `limits()["screens"]`.

## 2. Renderer (`views/shared/board.js`, `board.css`, `views/spectator/*`) — Agent B

House rules unchanged (`tests/integration/test_spectator_layout_render.py`):
no `Math.`, `toFixed`, `parseInt`, `parseFloat`, `setInterval`, `revision++`,
`api.command` in board.js/spectator.js; no `<button`, `<input`, `<dialog`,
`data-command`, `data-action` on the spectator page; none of the substrings
`handle`, `guide`, `drag`, `resize` anywhere in board.js/board.css (comments
included, case-insensitive).

New strict-JSON literals mirrored from Python and compared by the contract
test: `EVENT_WIDGET_IDS`, `EVENT_WIDGET_FIELDS`, `EVENT_WIDGET_TEXTS` (`{}`),
`EVENT_OPTIONAL_WIDGET_IDS` (`["warmup"]`), and `DEFAULT_SCREENS` (exactly
`default_layout()["screens"]`: both screens, every widget with every v2 style
default, key order irrelevant — the test compares parsed values).
`DEFAULT_LAYOUT` gains `"schema_version": 3` and a `"screens"` key equal to
`DEFAULT_SCREENS`. Simplest: define `DEFAULT_SCREENS` first as its own pure
JSON literal and assign `DEFAULT_LAYOUT.screens = DEFAULT_SCREENS` *outside*
the `DEFAULT_LAYOUT` literal (the test lifts each literal's text and
`json.loads` it; compare `DEFAULT_LAYOUT` against `default_layout()` with the
screens merged in — Agent B updates the test accordingly). If the numbers in
section 1.2 and Agent A's output disagree, the orchestrator regenerates the
JS literal from Python at integration; do not agonize over it.

Behaviour:

- `build(container, kind)` — `kind` is `"game"` (default when omitted) or
  `"event"`; builds that registry's widgets; sets `container.dataset.boardRoot
  = "1"` and `container.dataset.boardKind = kind`.
- `applyLayout(container, doc)` — `doc` is a **screen document** (the top
  level of a layout for the game board, or `layout.screens.pregame` /
  `.halftime` for an event board). The board root is found as today; the
  widget id list and per-widget fallbacks come from the root's `boardKind`
  (`DEFAULT_LAYOUT` for game, `DEFAULT_SCREENS.pregame` for event). Background
  is still painted on the `container` passed in. The safe-area guide lookup
  becomes `container.querySelector('#safe-area, [data-safe-area]')`.
- `applyModel(container, model)` — same kind lookup for the field map.
- `screenForLifecycle(lifecycle)` → `"pregame"` for `"PRE_GAME"`,
  `"halftime"` for `"HALFTIME"`, else `"game"`.
- `screenDocument(layout, screenId)` → the layout itself for `"game"` (or an
  unknown id); `layout.screens[screenId]` when that is a plain object; else
  `DEFAULT_SCREENS[screenId]`.
- Export all of the above on `ScoreboardBoard`.

Spectator page:

- `index.html`: `#game-board` and `#event-board` are both empty sections;
  the hand-written `<p>` event markup and the `#safe-area` div go away (the
  guide drew nothing). Keep the comment explaining that the score stays on
  the wall through pregame and halftime (now as widgets on the event screen).
- `spectator.js`: build both boards (`B.build(gameBoard, 'game')`,
  `B.build(eventBoard, 'event')`), keep `currentLayout` (starts as
  `B.DEFAULT_LAYOUT`), apply the game doc to `gameBoard` and the current
  event screen doc to `eventBoard` (`eventBoard.dataset.screen` remembers
  which). `applyView` computes the screen id from `model.lifecycle`,
  re-applies the event screen doc only when it changed, runs `applyModel` on
  both boards, toggles which board is shown, and sets the running flags on
  the game board's clock widgets as today. `R.bindFields` is no longer needed.
  `window.applyLayout(layout)` stores the full document and re-applies both.
- `spectator.css`: drop the old `.phase/.event-title/.event-clock/.warmup/
  .event-*` rules; `#event-board { position:absolute; inset:0 }` like
  `#game-board`. `#canvas` keeps its black background and `--canvas-width`.
- Tests: extend `test_spectator_layout_render.py` with the new literal
  comparisons (`EVENT_*` ↔ `layout.EVENT_*`, `DEFAULT_SCREENS` ↔
  `default_layout()["screens"]`), and fix anything in `tests/integration/
  test_spectator.py`, `tests/ui/spectator.cjs`, `tests/ui/test_spectator_
  browser.py` that referenced the old event markup (grep for `event-board`,
  `event-clock`, `clocks.event`, `warmup`). Keep the `.cjs` faithful even
  though it cannot run here (no Node/Playwright).

## 3. Editor (`views/layout/*`) — Agent C

Read `tests/integration/test_layout_editor_contract.py` first; every v2 hard
constraint still applies (no `CommandType` value as a substring — including
`event_countdown`, `new_game`, `end_game` — in the HTML or the
comment-stripped JS; no `.display`/`_display`/`.seconds`/`.score`; no
`prompt(`/`alert(`/`confirm(`; `Math.` only before `round`; no
`toFixed`/`parseInt`/`parseFloat`/`setInterval`; no widget id, label, or
screen label literal in the HTML — everything comes from `layout_state()`).

- **Screen switcher.** In the toolbar, right after the layout-name menu and
  the dirty dot: a segmented control `#screen-switch` (`role="tablist"`)
  generated from `state.screens` — one button per screen, `data-screen="<id>"`,
  text from `descriptor.label`, `aria-selected`. Ctrl+1/2/3 also switch.
- **State.** `app.screen` (starts `"game"`), `app.screenDescriptor()`
  (from `state.screens`), `app.screenDoc()` → `app.draft` for `"game"`, else
  `app.draft.screens[app.screen]`, and `app.widgetIds()`. `app.draft` stays
  the **full** document (history snapshots it whole; `preview_layout`,
  `save_layout`, `clamp_layout` receive it whole). Every place that today
  edits or reads `app.draft.widgets / .elements / .safe_area / .background`
  for editing goes through `app.screenDoc()` instead — in `layout.js`,
  `editor-state.js`, `editor-canvas.js`, `editor-panels.js`. The state
  helpers that take a `draft` (`getWidget`, `getElement`, `nextElementId`,
  `makeTextElement`, `safeBounds`, `clampGroupDelta`, `elementsForLayers`, …)
  keep their signatures and are simply passed the screen doc.
- **Switching** clears the selection, sets `boardSelected`, rebuilds the
  board root with `Board.build(boardRoot, descriptor.kind)`, re-renders
  everything. The preview is `Board.applyLayout(canvas, app.screenDoc())`
  then `Board.applyModel(boardRoot, app.snapshot)`.
- **Layers rail.** Groups come from `descriptor.widget_groups`, widgets from
  `descriptor.widgets`. Elements from the screen doc.
- **Inspector Board section.** Background and safe-area insets of the
  current screen (`data-board-prop` names unchanged). Presets gallery for the
  current screen (below).
- **Presets.** On the Game screen: `state.presets` — applying copies only
  `safe_area`, `background`, `widgets`, `elements` from `preset.layout` into
  the draft (name and `screens` are kept). On Pre-game/Halftime:
  `state.screen_presets[app.screen]` — applying replaces
  `draft.screens[app.screen]` with a clone of `preset.screen`. Same dirty-
  draft inline confirm, history push, and rerender as today.
- **Reset widget** calls `api.reset_widget(id, app.draft, app.screen)`.
- **Issues.** Each issue now has `screen`. The issues drawer lists them all;
  the status-bar count covers all screens; clicking an issue from another
  screen switches to that screen before selecting the item. The "N fields ·
  M elements" readout is for the current screen.
- **Element ids** are per screen (`nextElementId(app.screenDoc(), app.widgetIds(), prefix)`).
- **Host pushes** (`window.applyLayout`, `window.applyView`) unchanged in
  spirit: a dirty draft is never replaced; a clean one adopts the full doc
  and re-renders the current screen.
- **Contract test** (`test_layout_editor_contract.py`): add checks that
  `data-screen` and `screen_presets` appear in the scripts, that
  `reset_widget(` is called with three arguments, that no `event_countdown`
  substring exists; keep every existing check. Update `tests/ui/
  layout_editor.cjs` and `test_layout_editor_browser.py` faithfully (switch
  to Pre-game, apply a screen preset, add a text element there, switch back,
  save) even though they cannot run here.
- The scope note must still contain (lowercased) "never changes", "scores",
  and "clocks".

## 4. Storage, bridge, host, view model — Agent D

- `src/scoreboard/infrastructure/layouts.py`: no behavioural change beyond
  what v3 normalization implies; confirm `read_library` still drops an
  invalid layout and keeps siblings. `LAYOUT_LIBRARY_SCHEMA_VERSION` stays 1.
- `src/scoreboard/host/layout_bridge.py`: `state()` gains
  `"screens": layout_module.screen_descriptors()` and
  `"screen_presets": layout_module.screen_preset_descriptors()`.
  `PresentationLayouts.reset_widget(widget_id, payload, screen="game")` and
  `LayoutEditorBridge.reset_widget(widget_id, payload, screen="game")` pass
  the screen through to `layout_module.reset_widget(normalized, widget_id,
  screen)`. The public surface of `LayoutEditorBridge` is otherwise
  **unchanged** (the pinned set in `test_layout_bridge.py` stays).
- `src/scoreboard/host/bridge.py`: `spectator_view_model` adds
  `clocks.event.warmup_display`: `"Warmup follows: 3:00"` exactly when
  `warmup_follows` is `"3:00"`, else `None` (keep `warmup_follows` as is).
  Add a test in `tests/integration/test_bridge.py` for both cases (PRE_GAME →
  None; HALFTIME above the threshold → the string).
- Tests you own: `test_layout_bridge.py`, `test_layout_persistence.py`
  (`schema_version` expectations → 3; a stored v2 file upgrades on read;
  `state()["screens"]` and `["screen_presets"]` shapes; `reset_widget` with a
  screen), `test_bridge.py` (only the new warmup test), `test_host_application.py`
  if anything there pins the state shape.
- `src/scoreboard/host/app.py` should need no change (`publish_layout` and
  `get_layout` already push the whole document); verify by reading, and fix
  only if a real problem appears.

## 5. Docs — Agent E

Edit only `docs/UX_AND_LAYOUT.md` (§6.1a: the presentation is now a layout;
§10: add "10.9 Pre-game and halftime screens" covering the switcher, the
event widget inventory, per-screen presets, and remove "editing the
pregame/halftime countdown board" from 10.8), `docs/ARCHITECTURE.md` §9
(schema v3, `screens`), `docs/PHASE_2_BACKLOG.md` ("Presentation layout
editor" section), `docs/MVP_REQUIREMENTS.md` (the line near 279 that scopes
the layout editor), `PROJECT_ROADMAP.md` (a "Phase 2 owner request 4 —
pre-game and halftime screens" entry after the v2 entry, a decision-log row,
and a verification-table row marked **claimed, orchestrator verification
pending** — do not claim any test result you did not run), and `README.md`
if it describes the editor. Distinguish claimed from verified everywhere.
Validate relative Markdown links you touch.

## 6. Verification plan (orchestrator)

Focused suites per agent, then the full discovery run compared with the
baseline in `PROJECT_ROADMAP.md` (15 failures + 3 errors on `308ddd6`). Then
the preview-browser stub run and the real pywebview run from the v2 recipe:
open the editor, switch to Pre-game, apply a preset, add text, save, read
`layouts.json`, confirm the spectator/test window shows the pregame screen
during PRE_GAME and the halftime screen during HALFTIME.

Test command (Git Bash): `SCOREBOARD_DATA_DIR=/tmp/sb-<agent> ./.venv/Scripts/python.exe -m unittest tests.unit.test_layout_schema -v`
(PowerShell: `$env:SCOREBOARD_DATA_DIR='C:\Temp\sb-<agent>'; .\.venv\Scripts\python.exe -m unittest ...`).
There is no `python` on PATH; always use `./.venv/Scripts/python.exe`.

## 7. Non-goals

Editing the operator window; binding a text element to a game field; SVG
images; per-resolution layouts; OBS/video; a fourth screen (end of game,
timeouts) — the schema leaves room (`SCREEN_IDS`) but nothing is added now.

## 8. File ownership

| Agent | Owns | Must not touch |
|---|---|---|
| A schema | `src/scoreboard/presentation/layout.py`, `tests/unit/test_layout_schema.py` | everything else |
| B renderer | `src/scoreboard/views/shared/board.js`, `board.css`, `src/scoreboard/views/spectator/*`, `tests/integration/test_spectator_layout_render.py`, `tests/integration/test_spectator.py`, `tests/ui/spectator.cjs`, `tests/ui/test_spectator_browser.py` | editor, Python source |
| C editor | `src/scoreboard/views/layout/*`, `tests/integration/test_layout_editor_contract.py`, `tests/ui/layout_editor.cjs`, `tests/ui/test_layout_editor_browser.py` | renderer, Python source |
| D bridge | `src/scoreboard/infrastructure/layouts.py`, `src/scoreboard/host/layout_bridge.py`, `src/scoreboard/host/bridge.py` (warmup_display only), `src/scoreboard/host/app.py` (only if needed), `tests/integration/test_layout_bridge.py`, `test_layout_persistence.py`, `test_bridge.py` (new warmup test only), `test_host_application.py` | schema module, views |
| E docs | `docs/*.md`, `PROJECT_ROADMAP.md`, `README.md` | code and tests |

Agents A–D run in parallel against this spec, so each hard-codes the names
and defaults above rather than reading another agent's output. The
orchestrator integrates, regenerates the JS default literals from Python if
the contract test disagrees, and runs the full verification.
