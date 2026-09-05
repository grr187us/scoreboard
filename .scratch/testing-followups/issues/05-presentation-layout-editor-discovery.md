# Research a safe visual layout editor for the spectator board

Type: research
Status: needs-info
Priority: low
Phase: 3

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

## Expected output

A small prototype plus a written layout schema, validation rules, preview and
rollback workflow, and an estimate for a production editor.

## Comments

- Recorded from owner testing feedback on 2026-09-05.
