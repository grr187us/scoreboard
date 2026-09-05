# September 5 testing follow-ups

**Purpose:** Track operator findings from local spectator-preview testing without
silently changing the Phase 2 requirements. The items below are not complete
until their workflow, safety impact, implementation, and verification are each
recorded.

## Scope

- Keep the Python command service authoritative.
- Preserve monotonic clock timing, offline operation, and durable action history.
- Do not bring media, OBS, networking, physical-controller work, or direct LED
  control into Phase 2.
- Treat a change that can discard a live pregame countdown or move game time as
  a dangerous operation; ordinary scoring increments remain one action.

## Proposed delivery groups

1. **Pregame-to-game transition safety**: issues 01 and 02 are one workflow and
   should be specified and implemented together.
2. **Clock and board clarity**: issues 03 and 04 are independent presentation
   work and may share one small implementation pass after snapshot semantics are
   agreed.
3. **Layout editor discovery**: issue 05 is a Phase 3 research/prototype item,
   not an MVP addition.
