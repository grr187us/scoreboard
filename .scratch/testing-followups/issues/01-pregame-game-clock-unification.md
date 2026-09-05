# Use the game-clock control for the 30-minute pregame countdown

Type: task
Status: complete
Priority: high
Phase: 2

## Finding

A new game correctly shows `KICKOFF IN 30:00` in the spectator/test window, but
the operator's game-clock card still shows its separate stopped `12:00` value.
The operator wants one game-clock control whose pregame meaning is the 30-minute
countdown, so both windows show the same authoritative value and running state.

## Current behavior and conflict

The current model intentionally owns a separate `event_countdown` for pregame
and halftime. `F-025`, `F-030`, the architecture clock model, and the UX all
say that pregame is separate from the game clock. This request supersedes that
provisional workflow only after the target behavior below is confirmed.

## Confirmed decision

When moving from PRE to 1st with pregame time remaining, the accepting action
reads exactly `Start 1st quarter — discard remaining pregame time`. Game Clock
Start in PRE runs the 30:00 countdown without entering game play; after the
accepted transition it starts the stopped 12:00 first-quarter clock.

## Delivered behavior

- New Game has one stopped 30:00 PRE Game Clock rendered as `KICKOFF IN`.
- Its Start/Stop/Reset/Edit actions are monotonic, durable, and PRE-only.
- Expiry stays PRE at 0:00; accepted PRE → 1st discards PRE and loads 12:00.
- Recovery restores the stopped selected PRE value; halftime stays separate.

## Verification recorded

Focused unit/integration/browser coverage includes PRE control/recovery/expiry,
the exact accepting label, direct-selection and keyboard parity, cancellation,
stale revision, and durable action history.

## Comments

- Recorded from owner testing feedback on 2026-09-05.
