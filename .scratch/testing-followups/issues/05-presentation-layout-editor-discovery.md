# Research a safe visual layout editor for the spectator board

Type: research
Status: done
Priority: low
Phase: 3

**Resolved September 5, 2026, ahead of formal Phase 3.** The owner asked for
this work directly after the local-time and expanded-football-fields requests
(items 1 and 2 of "Owner-requested next scoreboard work" in
`PROJECT_ROADMAP.md`); it is delivered as item 3 of that same list. This does
not advance Phase 3 as a whole, Task 12, the Phase 0 HDMI gate, or any
hardware/stadium evidence — those remain exactly where the roadmap and
`docs/PHASE_2_BACKLOG.md` record them.

## Goal

Plan an easy local editor that lets a non-developer move spectator-board
elements, change colors, and save visual layouts without being able to alter
authoritative scores, clock behavior, or game rules.

## Constraints

- Deferred until Phase 2 acceptance is complete; no editor is added to a live
  game-day surface now.
- Offline only; configurations are local, versioned, validated files with a
  built-in default and a one-click restore path.
- Editing happens in a preview/safe mode, never the active game board.
- Layouts must preserve safe margins, minimum readable type sizes, contrast,
  and required field visibility at the measured stadium resolution.
- Game state remains rendered into named slots; the editor changes only the
  presentation recipe for those slots.

## Discovery questions

Choose the first editor level: (1) approved themes/colors/type scale only, (2)
drag-and-drop named slots within constrained zones, or (3) a freeform canvas.
The recommended first version is level 2, because it is powerful enough for
school branding but still protects legibility and required scoreboard fields.

**Resolved September 5, 2026.** Level 2 (named-slot editing within
constrained zones) was the chosen level, but it was delivered as **numeric
constrained editing rather than dragging**: every widget's position, size,
font scale, color, alignment, weight, stacking order, and visibility is a
validated number field with a documented minimum and maximum, not a
mouse-drag interaction. See "Phase 2 owner request 3 — presentation layout
editor" in `PROJECT_ROADMAP.md` and `docs/UX_AND_LAYOUT.md` §10.

How the remaining discovery questions resolved:

- **Safe margins, minimum readable type, contrast, and required-field
  visibility** are enforced by strict Python-side validation, not by editor
  UI convention alone: a layout that would place a visible widget outside the
  safe area, below the minimum widget size, or below the minimum font scale
  is rejected outright rather than accepted or silently clamped.
- **Preview and rollback** both live in the editor. The preview canvas
  renders the live game snapshot through the same renderer as the real
  spectator board (`views/shared/board.js`), so what the operator sees while
  editing is the same code path a spectator sees. `Reset this widget` and
  `Reset entire layout…` restore the built-in default on request, and a
  corrupted or invalid stored layout falls back to the last valid layout and
  then to the built-in default automatically, with no operator action
  required and no launch ever blocked.
- **Named slots versus a freeform canvas:** the editor exposes exactly the
  fifteen named widgets the spectator board can render
  (`docs/UX_AND_LAYOUT.md` §10.4). An operator cannot add a slot, rename one,
  or attach arbitrary text to an authoritative field — this is level 2 as
  scoped, not level 3.
- **"Editing happens in a preview/safe mode, never the active game board"**
  is satisfied by construction: the editor is a separate window from the
  spectator display, and its preview canvas is a second instance of the same
  renderer rather than the live board itself. Saving a layout publishes it to
  the live spectator board (and any open practice/editor window) only after
  validation passes.
- **A production-editor time estimate** was not requested as part of this
  delivery; v1 is the production editor, scoped to the numeric-only,
  fifteen-widget boundary above rather than a throwaway prototype. A freeform
  canvas, drag-and-drop, or logo/media support remain future work if ever
  requested — see the v1 exclusion list in `docs/PHASE_2_BACKLOG.md`.

## Expected output

Delivered as a working v1 editor rather than a prototype:
`src/scoreboard/presentation/layout.py` (schema, defaults, and validation),
`src/scoreboard/infrastructure/layouts.py` (`layouts.json` persistence),
`src/scoreboard/host/layout_bridge.py` (the non-mutating host bridge), and
`src/scoreboard/views/layout/` (the editor UI), plus
`src/scoreboard/views/shared/board.js`/`board.css` (the widgetized renderer
shared by the editor preview and the real spectator board). Automated test
counts: 103 focused tests pass (schema 42, persistence 18, bridge 18, renderer contract 8, editor contract 14, spectator browser 2, editor browser 1).

## Comments

- Recorded from owner testing feedback on 2026-09-05.
- Delivered September 5, 2026 as "Phase 2 owner request 3" — see
  `PROJECT_ROADMAP.md` for full evidence and `docs/UX_AND_LAYOUT.md` §10 for
  the operator-facing description.
