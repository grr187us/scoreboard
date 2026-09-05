# Make running clocks instantly distinguishable by color

Type: task
Status: resolved
Priority: medium
Phase: 2

## Finding

When a clock is running, the operator should be able to recognize it at a
glance without reading the status word: game-clock presentation green and
play-clock presentation red. Textual `RUNNING`/`STOPPED` status remains, since
color is supplemental and must not be the sole indicator.

## Scope

Apply the state-driven colors to the operator clock cards and, after a contrast
check, the spectator clock values. Stopped, cleared, and expired values retain
their existing neutral styling. No clock behavior, command, or state ownership
changes.

## Acceptance criteria

- A running game clock has a clear green treatment; a running play clock has a
  clear red treatment.
- The treatment updates from the authoritative snapshot, including Start, Stop,
  expiry, recovery, and play-clock clear paths.
- `RUNNING`/`STOPPED` remains visible and contrast remains legible on the LED
  presentation.
- Automated DOM/render coverage proves the correct class/state mapping.

## Comments

- Recorded from owner testing feedback on 2026-09-05.
- Implemented 2026-09-05: the operator and spectator values receive classes
  directly from the authoritative running flags; text status remains visible.
- Verified 2026-09-05: focused spectator and real-browser keyboard tests,
  followed by the isolated full suite (405 tests), passed. `compileall`,
  dependency validation, and diff checks also passed.
