# Add deliberate quarter-transition safeguards

Type: task
Status: complete
Priority: high
Phase: 2
Blocked by: 01

## Finding

The visible Quarter forward/back controls can make a major game-clock change.
They currently confirm only when either clock is running. The operator requests
a second confirmation for quarter changes in general, with a distinct protocol
when a pregame countdown has not reached zero.

## Safety boundary

Small reversible scoring increments such as `+6` stay one action. Quarter
changes, resets, direct time corrections, New Game, and End Game are major
time/lifecycle actions and must remain deliberate, reviewable, and logged.

## Confirmed decision

Every forward, back, and direct quarter action confirms even when clocks are
stopped. The owner-approved PRE-to-1st accepting action is exactly
`Start 1st quarter — discard remaining pregame time`. The final behavior is:

- normal stopped quarter move: one confirmation that names the source/target
  quarter and any game-clock value that will load;
- either clock running: the same confirmation also says both clocks will stop;
- PRE with time remaining: a stronger explicit override described in issue 01;
- a countdown naturally at zero: normal first-quarter confirmation, with no
  pregame-abandonment warning.

## Delivered behavior

- Mouse, keyboard, and direct selection share confirmation/revision behavior.
- Cancel changes nothing; accepting stops any running clocks and records the command.
- Prompts name source/target, running clocks to stop, and loaded clock value.
- PRE at zero gets the normal confirmation, without abandonment wording.

## Verification

Command/service tests for every transition class, UI tests for cancel/confirm
and keyboard parity, durable-history assertions, and an operator rehearsal.

## Comments

- Recorded from owner testing feedback on 2026-09-05.
