# Broadcast Welcome default screens — build notes (September 8–9, 2026)

Status: implemented on branch `improvements`, uncommitted; owner sign-off on the default pair
and the stadium-resolution legibility check remain open (spec section 7).

## How it was built
Four file-owned agents against `spec.md` (A schema/presets/plumbing, B renderer, C editor,
D docs); the lead regenerated `board.js`'s `DEFAULT_LAYOUT`/`DEFAULT_SCREENS`/`FONT_FAMILIES`
literals from Python (`scratchpad/regen_literals.py` pattern: rewrite the `var NAME = {...};`
blocks with `json.dumps(indent=2)`), integrated, and verified. Agent A was killed by a usage
limit after landing everything but two test expectations (fixed by the lead).

## Lead fixes after integration
- `tests/unit/test_event_screens.py`: a non-bleed box at x < 0 is a `COORDINATE` error (the
  existing rule), and the ticker label truncates at 24 characters.
- Halftime welcome `event_phase` gained `fit_text: True` so the renderer's ink-centring
  applies (its Barlow glyphs sat 7 px below the box at 1280x720 otherwise).
- `tests/ui/spectator.cjs` now measures glyph ink (as `grid.cjs` does) and awaits
  `document.fonts.ready` after each `applyView`: the event board's bundled faces are only
  requested when that board first shows, so measuring before the load raced (1 fail in 2 runs).
- `tests/integration/test_bridge.py`: `get_motion` joined the spectator bridge's read-only
  allow-list.

## Evidence
- Full suite: 1277 tests, 0 failures, 0 errors, 3 skips (A-1) — `discover -s tests`.
- `tests/ui/test_event_screens_browser.py`: 126 cases; captures `captures/event-screens/`
  (`<screen>-<on|off>-<1920|1366|640>.png`, 36 files).
- `tests/ui/test_layout_editor_browser.py`: 35 checks.
- Real pywebview: `realrun_event_screens.py` 40/40 (run with `PYTHONIOENCODING=utf-8`).
- Migration: a saved Grid layout without the new keys validates with zero warnings and keeps
  its screens; a v2 document without `screens` gets the welcome default; the owner's live
  library (`Default`, `Greg Updated`) reads with no issues.

## Known follow-ups
- `centreInk` in `board.js` shifts every fitted widget toward its optical centre (Grid and
  Stadium scores move a pixel or two); the existing browser suites pass, worth a glance on the wall.
- The 24-character stress names shrink to a sliver on Kickoff Clock halftime bars and Fifty
  Yard Line end zones (by design of `fit_text`); real school names are far shorter.
- Rotate-mode tickers use a self-rescheduling `setTimeout` (not `setInterval`, a forbidden
  token in the spectator house rules).
