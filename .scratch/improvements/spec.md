# Improvements round 1 (September 8, 2026, branch `improvements`)

Two owner-reported bugs. Read this whole file before editing anything.

## Bug 1: a cutscene repaints the board in the wrong colours

**Symptom.** The operator's active layout (for example the "Scoreboard Grid"
or "Tigers Stadium" preset) paints the scores gold (`#FFB703`). When any
cutscene fires, the board morphs down into the Broadcast bar and the scores
turn white, in a different font. It looks broken. The owner accepts the
morph (scores shrink to the bottom); they want the *look* of every widget to
be the operator's look throughout.

**Root cause (confirmed).** `src/scoreboard/host/app.py:219` builds
`CutsceneDirector` with no `read_layout`, so `CutsceneDirector._resolve_layout`
(`host/cutscenes.py:130`) always falls back to the stock Broadcast preset,
and `build_program` (`presentation/cutscenes.py:451`) deep-copies that preset
verbatim as `program["layout"]`. The spectator draws both boards from that
override (`views/spectator/spectator.js`, `setOverrideLayout`), so every
widget takes the Broadcast preset's white `#FFFFFF` / arial styling.

**Fix (Python only; one fix covers all five events because every event goes
through `build_program`).**

1. `presentation/cutscenes.py`: `build_program` gains a keyword-only
   parameter `board_layout: Mapping[str, Any] | None = None` (the operator's
   active layout, the *style source*). `layout` stays the *geometry source*
   (the Broadcast bar). The program layout is built like this:
   - Start from `copy.deepcopy(layout)`, `name = "Cutscene"` (unchanged).
   - For the top-level `widgets` and for every screen under `screens.*`
     (`pregame`, `halftime`, and any other key present), for each widget id
     that exists in *both* the geometry layout and the matching place in
     `board_layout` (top-level widgets ↔ top-level widgets, `screens.X` ↔
     `screens.X`), copy these keys from the board widget when present:
     `STYLE_KEYS = ("color", "font_family", "font_weight", "letter_spacing",
     "text_transform", "text_effect")`.
     Export `CUTSCENE_STYLE_KEYS` (that tuple) in `__all__` so tests and the
     reviewer can pin it.
   - Do **not** copy geometry, `visible`, `z_index`, `text_align`,
     `vertical_align`, `padding`, `display_format`, backgrounds, borders,
     corners, or free `elements`; do not copy the page `background`.
   - Every widget that received a style copy gets `fit_text: True` on the
     program layout (the operator's font can be wider than the Broadcast
     bar's slot; fitting is the safety net). Widgets untouched keep whatever
     `fit_text` they had.
   - `board_layout=None` or not a Mapping → behave exactly as today.
   - Never mutate either input (the existing deep-copy test stays green).
2. `host/cutscenes.py`: `CutsceneDirector.__init__` gains
   `read_board_layout: Callable[[], dict[str, Any]] | None = None`. In
   `trigger`, read it **outside** `self._lock`, right beside the existing
   `layout = self._resolve_layout()` call (the lock-ordering rule in the
   file's comments applies: never call out to another lock holder while
   holding the director lock). A raising reader is contained like the
   spectator-view reader: note it through diagnostics the same way and pass
   `None`. Pass the result as `board_layout=` to `build_program`.
3. `host/app.py:219`: pass `read_board_layout=self.layouts.current_layout`
   (`self.layouts` is created a few lines above; `current_layout` is
   `host/layout_bridge.py:118` and returns a valid normalized document).
4. Tests, mirroring the existing style:
   - `tests/unit/test_cutscene_schema.py`: a board layout with gold scores and
     `varsity`/`bahnschrift` fonts merged over the Broadcast preset yields a
     program layout whose `home_score`/`away_score`/clock widgets carry the
     board's colour/font and `fit_text: True`, while their `x/y/width/height/
     font_scale` still equal the Broadcast preset's; screens are merged the
     same way; an id present only in the board layout is ignored; an id
     present only in the geometry layout is untouched; `board_layout=None`
     equals the old output; neither input mutated.
   - `tests/integration/test_cutscene_director.py`: a director built with
     `read_board_layout` publishes the merged colours for **every one of the
     five events** (`CUTSCENE_EVENTS`); a raising `read_board_layout` still
     triggers and notes a diagnostic.
   - `tests/integration/test_cutscenes_window.py` or
     `test_host_application.py` (whichever already constructs the real
     `Application`): the app's director publishes the active layout's colour
     after the operator selects a preset with gold scores.
   - Update the `tests/README.md` rows for the touched test files (one
     sentence each, same voice).

## Bug 2: the game clock renders too big until the clock first starts

**Symptom.** Before the game clock starts, `12:00` is drawn larger than its
box and overlaps the score. The instant the clock starts the size snaps to
correct.

**Root cause (strong hypothesis, verify before fixing).** `fitWidgetText` in
`src/scoreboard/views/shared/board.js:1588` measures the text once and caches
by a key that includes the text and the CSS `font-family` *string*, not the
font's *load state*. The Scoreboard Grid preset draws digits in `varsity`,
which is the bundled Graduate web font (`board.css` `@font-face`, loaded lazily
on first use). The first fit runs before Graduate has loaded, so the measured
ink is the fallback face's (narrower), the factor comes out too large, and
the cached key is only invalidated when the clock text changes — i.e. when
the clock starts. Scores show the same issue less visibly because `0` is
narrow.

**Fix (JS only, `views/shared/board.js`).** Re-fit every fitted widget when
fonts finish loading: on `document.fonts.ready` and on every
`document.fonts` `loadingdone` event, clear every element's `_fitKey` under
both boards and re-run `fitWidgetText` for each `[data-widget]` with
`data-fit-text="1"` (there is already a pattern for re-applying `_lastModel`
on the board root; reuse it). Guard for browsers without `document.fonts`.
Keep the measurement cache otherwise; keep the existing behaviour that the
fit never abbreviates text.

**Verification.** A browser test in `tests/ui/grid.cjs` +
`tests/ui/test_grid_browser.py` (the Scoreboard Grid preset already has a
harness there): load the spectator page with the Grid preset and a pregame /
`12:00` model, wait for `document.fonts.ready`, and assert the game clock
text's ink rect fits inside its widget box and does not intersect the score
widgets' boxes — and that the same holds *before* any model change. Also
prove the assertion would have failed before the fix (run it once against
the pre-fix file and record the numbers in your report).

## Ground rules for every agent

- Own only the files listed in your task. Do not touch `dist/`, `captures/`,
  or `build/`.
- Python: `./.venv/Scripts/python.exe` (bare `python` is the Store alias).
  Tests: from the repo root,
  `./.venv/Scripts/python.exe -m unittest tests.unit.test_cutscene_schema tests.integration.test_cutscene_director -v`
  (add the files you touched). The full run is
  `./.venv/Scripts/python.exe -m unittest discover -s tests` (green:
  1124 tests, 3 expected skips). Set `SCOREBOARD_DATA_DIR` to a scratch
  folder when running anything that touches the data directory.
- Node is at `C:\Program Files\nodejs` and is **not on PATH**; prepend it
  (`$env:Path = "C:\Program Files\nodejs;" + $env:Path` in PowerShell, or
  `export PATH="/c/Program Files/nodejs:$PATH"` in Git Bash) before any
  browser test. Browser tests run through unittest as well
  (`tests.ui.test_grid_browser`).
- Follow the file-header docstring voice already in each file. Comments say
  *why*, not *what*.
- Do not commit. Report exactly which files you changed and the test output.
