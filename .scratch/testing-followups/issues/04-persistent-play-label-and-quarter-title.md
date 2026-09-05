# Keep the Play Clock label visible and expand quarter labels

Type: task
Status: resolved
Priority: medium
Phase: 2

## Finding

Clearing the play clock removes its spectator label because the label is hidden
when the display value is blank. The operator wants `PLAY CLOCK` to remain
visible, with an em dash or two dashes in the value position after a manual or
automatic clear. The spectator board should also say `2nd Quarter`, not only
`2nd` (and use the matching expanded wording for live quarters).

## Scope

This is presentation-only. The existing `play_clock_cleared` state still
distinguishes an intentional clear from an expired visible `0.0`; the renderer
maps a cleared state to a placeholder instead of hiding the label. Quarter
storage remains the compact authoritative label unless a documented display
formatter expands it.

## Acceptance criteria

- `PLAY CLOCK` remains visible on the spectator view at all times in game mode.
- Cleared state renders a neutral `—` or `--`; a naturally expired, uncleared
  play clock continues to render `0.0`.
- Manual clear and automatic clears caused by game-clock transitions share the
  same display behavior.
- Live quarter labels render `1st Quarter` through `4th Quarter`; `PRE`,
  `HALF`, `OT`, and `FINAL` retain intentionally reviewed wording.
- Operator snapshots, state semantics, and event logging are unchanged.

## Comments

- Recorded from owner testing feedback on 2026-09-05.
- Implemented 2026-09-05: the view model presents a cleared play clock as an
  em dash while preserving its distinct expired `0.0` value; spectator-only
  live-period wording expands the compact stored quarter label. Verification
  passed on 2026-09-05: focused spectator and real-browser keyboard tests,
  followed by the isolated full suite (405 tests), passed. `compileall`,
  dependency validation, and diff checks also passed.
