# Field Assistant Rules, Workflow, and Test Matrix

**Status:** Implemented September 5, 2026, with the amendments recorded below (see "Amendments"). Native Windows/WebView2 rendering of the helper window, the 1366×768-at-100%/125% visual check, and a live operator rehearsal remain outstanding; see `PROJECT_ROADMAP.md` "Field Assistant" and `docs/UX_AND_LAYOUT.md` §11.5.

## Amendments

- **September 5, 2026 — the helper never had a bridge, and the screen is rebuilt for a volunteer.** A second operator attempt still could not finalize anything: **Confirm Play** stayed disabled no matter what was pressed, with no message. Driving the real pywebview/WebView2 window from a harness (not a browser stub) showed why: `field_assistant.js` waited for `pywebviewready` on `document`, and pywebview dispatches that event on `window` only, so the page ran with a null bridge forever. Every preview silently returned before calling Python; the ten-per-second `applyView` pushes still rendered revision, clocks, and the draft ball, so the window looked alive. The listener is now on `window`, exactly as `shared/render.js` does, and a source-contract test forbids a `document` listener. The same run found the yard numbers drifting off their lines (a fixed string of spaces cannot track percentage-drawn lines); they are now positioned by percentage.

  *The screen itself was the larger problem.* The owner's operators are volunteers with about five minutes of training, and the first screen — a **Workflow** dropdown whose choice revealed different control groups, a direction dropdown labelled "HOME attacks toward", a separate **Preview result** press, and a banner pointing "below" at a control that sat to the right — was too hard to set up and use. The window now shows exactly one panel at a time, chosen from the authoritative snapshot: **direction** (asked once per game, in the words "Which end zone does HOME score in during the 1st quarter?", with the drawing mirroring to the chosen side before anything is saved), **start** (nobody has the ball: **HOME BALL HERE** / **AWAY BALL HERE**, which is the opening kickoff, every post-score kickoff, and any re-sync), and **play** (click where the ball ended, then press **PLAY OVER — BALL HERE**, **INCOMPLETE PASS**, or **OTHER TEAM'S BALL HERE** — a punt, interception, fumble, turnover on downs, or kickoff return are one and the same explicit change of possession to Python). **PENALTY…**, **SCORE…**, and **FIX MANUALLY…** open sub-panels. Whatever is pressed is previewed by Python at once and the result becomes the Confirm button's own label (`CONFIRM → 2nd down — HOME ball · 2nd & 3 · at HOME 32`), so the operator reads what will happen before it happens; a fourth-down failure disables Confirm and names the button that flips possession. **Preview result** is gone (auto-preview made it redundant); **Discard draft** reads **Cancel**; **Re-sync** reads **Reload from scoreboard**. After a confirmed touchdown the score panel stays open on the try for the scoring team. Section 4 below is rewritten to describe this flow; the rules in section 3, the action envelope, and the atomic-command boundary are unchanged.

  *The manual escape hatch now exists inside the helper.* Sections 2 and 7 always reserved a manual path for unusual special-teams outcomes, but it lived only in the main window's Field drawer. **FIX MANUALLY…** lets the operator state team, down, distance (or Goal), and the clicked spot; Python validates every value and derives only the line to gain, and the result is committed as one `manual` action through the same atomic command (section 3.5, section 4.6, FA-31).

  *Evidence.* A harness that launches the real application, opens the helper through the operator bridge, and presses the actual buttons with `evaluate_js` drove seven consecutive commits — direction, opening series, a normal play, a punt, a manual fix, a touchdown, a try, and a kickoff return — with the persisted state agreeing at each revision. The old script under the same harness never enabled Confirm. The 1366×768-at-125% check and a live operator rehearsal remain outstanding.

- **September 5, 2026 — the draft ball now belongs to the operator, and `PRE` is usable.** First operator use showed the assistant was unusable in practice: the ball snapped back to the 50 as soon as it was moved, and nothing could be finalized. Two defects, fixed together.

  *The draft ball was re-seeded by every refresh push.* The host publishes a complete operator snapshot to the helper ten times a second (`REFRESH_INTERVAL_SECONDS = 0.1`). The helper re-seeded its draft ball from the authoritative spot on any push where no preview had yet been accepted and no pointer was held down — so within 100 ms of a nudge, an arrow key, a yard selection, or a completed drag, the ball returned to the persisted spot, which is `HOME 50` at the start of a game. Re-syncing made it worse, because discarding the draft re-armed the overwrite. The draft ball is now re-seeded at exactly three moments: when the window opens, when **Re-sync** is pressed, and after a committed action. A refresh push may re-draw the same spot on the mirrored side after a quarter boundary; it may never move it. **Discard draft** clears the pending proposal and leaves the ball where the operator put it.

  *`PRE` was refused outright.* A game's persisted quarter is `PRE` until the operator advances it, and the calculator accepted only the four regulation quarters, so every preview at the start of a game — the moment the opening series is being staged — failed with "quarter must be a regulation quarter or OT". `PRE` is now one of the assistant's quarters and is treated as "before the 1st quarter": identical rules direction, and a drawing mirrored the same way the 1st quarter will be, so the setup staged before kickoff is the setup that survives the quarter change. `HALF`, `OT`, and `FINAL` remain manual-only. Finalizing in `PRE` does not advance the quarter; the quarter control remains the operator's.

  *Also changed with them:* every operator change now re-previews automatically (debounced, one request per drag, on release), so the Proposed panel always describes the ball actually on screen. **Confirm** remains a separate, deliberate press, and is disabled the moment a change makes the last accepted proposal stale. **Preview result** is retained for an explicit re-preview.

- **September 5, 2026 — direction-by-quarter wording corrected.** Section 3.2 originally said that the offense direction in the private absolute coordinate itself flips every quarter (`+1`/`-1` alternating with the quarter). Because that coordinate is label-based (0 is always the HOME goal line, 100 the AWAY goal line; section 3.1), a literal per-quarter flip of the direction was internally inconsistent and would have moved a 2nd-quarter HOME gain toward HOME's own goal line. The implemented rule instead fixes each team's direction in the label coordinate — HOME always `+1` toward the AWAY goal line, AWAY always `-1` — and lets only the on-screen drawing mirror at each quarter boundary. Section 3.2 and the FA-02 test-matrix row below reflect the corrected rule; this note preserves why the original wording was wrong.

**Purpose:** Reduce the operator's end-of-play workload by providing a separate, field-shaped **Field Assistant** window. It calculates and applies field status after a play while preserving the existing scoreboard-control screen, its manual field-status controls, and their current independent logic as a visible fallback.

## 1. Non-negotiable boundaries

- The current operator screen remains usable and unchanged in behavior. Its down, distance, possession, and ball-on controls remain the manual correction path.
- The Field Assistant is a separate, similarly sized window. It is an operator aid, not a spectator display and not a second authoritative process.
- Python remains the sole authoritative state owner. JavaScript only renders a draft field and requests validated commands.
- A finalized play changes all affected football fields in **one** validated, persisted, logged, revision-checked command. The spectator board must never receive a sequence such as "new ball spot, old down".
- Finalizing field status never starts, stops, resets, or edits either clock. It remains usable when a game clock is running because a running-clock play may still need a quick post-play update.
- The application remains fully offline. No networking, cloud service, physical-controller integration, LED protocol work, OBS work, or vendor-system modification is part of this feature.
- Existing manual edits are never overwritten silently. A changed revision requires the assistant to re-sync and rebuild its draft.

## 2. Confirmed product decisions

| Topic | Decision |
|---|---|
| Field labels | Use `HOME 25` / `AWAY 25`, meaning yards from that named team's goal line. |
| Direction | The teams switch ends at every quarter boundary. Each team's rules-coordinate direction is fixed; the assistant mirrors only the on-screen drawing's attacking side from the selected quarter after an operator establishes the first-quarter side (corrected September 5, 2026; see section 3.2). |
| Scrimmage | Automate ordinary scrimmage outcomes, incomplete passes, first downs, goal-to-go, turnover-on-downs proposals, and possession changes explicitly selected by the operator. |
| Penalties | Provide ±5/±10/±15 proposed-spot shortcuts, then require an explicit down result: repeat down, count down, automatic first down, no play, or decline. |
| Defined transitions | Include kickoff, touchdown, try/PAT, made field goal, and safety workflows. Unusual special-teams outcomes retain a manual escape hatch. |
| Existing controls | Keep the existing manual field-status and score controls; the assistant does not remove or change their behavior. |

## 3. Rule model

### 3.1 Canonical field coordinate

The rules engine works with a private absolute coordinate from `0` to `100`:

- `0` is the HOME goal line;
- `100` is the AWAY goal line;
- `50` is midfield.

The existing persisted `BallSpot(team, yard_line)` remains the display/state boundary:

- `HOME y` maps to absolute `y` for `0..50`;
- `AWAY y` maps to absolute `100 - y` for `0..50`;
- midfield is emitted canonically as `HOME 50`; either legacy/manual `HOME 50` or `AWAY 50` reads as the same physical spot.

The assistant draft may use the absolute coordinate, but it must not expose a new competing ball-position convention to the operator or spectator views.

### 3.2 Direction by quarter (corrected September 5, 2026 — see Amendments)

Each team's direction in the label-based absolute coordinate (section 3.1) is fixed and never alternates: HOME is always `+1` toward the AWAY goal line, and AWAY is always `-1` toward the HOME goal line. A quarter change never moves the offense's calculated direction, because `0`/`100` in that coordinate are fixed to HOME's and AWAY's goal lines respectively, not to "left" and "right" — a coordinate flip would silently reverse which goal line a gain counts toward.

What does alternate, once per quarter boundary, is presentation only. At the start of use, the operator explicitly selects which end of the **on-screen field drawing** HOME attacks toward in the first quarter (`home_goal_side`, `left` or `right`). That side mirrors at every quarter boundary (1st↔2nd, 3rd↔4th, and so on), the same way real teams change ends, so the drawing keeps showing the true attacking direction spectators would see in the stadium — without ever touching the stored ball spot, the line to gain, or either team's fixed rules-coordinate direction.

The stored ball spot never moves merely because the quarter changes; only the drawing's mirrored side changes.

`PRE` is one of the assistant's quarters and is treated as "before the 1st quarter" — the same rules direction and the same drawing side the 1st quarter will use — because a game's persisted quarter is `PRE` while the opening series is being staged. `HALF`, `OT`, and `FINAL` are manual-only; `OT` stays manual until local overtime rules are confirmed.

*Original wording, corrected above (see Amendments):* "At the start of use, the operator explicitly selects which end zone HOME attacks in the first quarter. Let that direction be `+1` toward the AWAY goal line or `-1` toward the HOME goal line. [1st/3rd: first-quarter direction; 2nd/4th: opposite, for both HOME and AWAY.] The stored ball spot never moves merely because the quarter changes; only the direction arrow and calculations change." This was internally inconsistent with the fixed-goal-line coordinate in section 3.1 and was never implemented as written.

### 3.3 Series and line to gain

For each active series, the helper tracks a line-to-gain coordinate and derives distance from it. It must not derive rules in JavaScript.

- Start of a normal series: set the line to gain ten yards in the offense's direction, capped at that direction's goal line.
- If that line to gain is the goal line—whether it is exactly ten yards away or nearer—show `Goal` rather than a numeric distance. A loss can make the physical distance larger while the display correctly remains goal-to-go.
- A normal play that reaches or passes the line to gain starts a new first down at the final spot and creates a new ten-yard line to gain, again capped at the goal line.
- A normal play that does not reach it advances the down and retains the existing line to gain.
- An incomplete pass retains the ball spot and line to gain but advances the down.
- A fourth-down failure must be presented as a clear **proposed turnover on downs**, not silently converted to possession. The operator confirms the new offense and final spot.
- A proposed ball at or beyond the goal line cannot be finalized as an ordinary scrimmage play. The operator must choose the applicable scoring/exception transition.

The helper must present the derived result before final confirmation: final ball spot, possession, down, and distance/goal-to-go.

### 3.4 Penalties

Penalty buttons adjust only the proposed enforcement spot. They do not infer a rule from the yardage.

After a yardage adjustment, the operator selects one result:

| Result | Field-status consequence |
|---|---|
| Repeat down | Keep the down and existing line to gain; use the enforced spot. |
| Count down | Advance the down and retain the existing line to gain; use the enforced spot. |
| Automatic first | Set first down and create a new line to gain from the enforced spot. |
| No play | Record that classification, retain/replay the down as explicitly shown, and use the operator-confirmed enforcement spot. |
| Decline | Discard the penalty adjustment and apply the underlying proposed play result. |

The confirmation view must state the selected consequence in plain language. Offset, multiple, dead-ball, enforcement-from-a-different-spot, and local-rule exceptions remain manual corrections unless a later approved design adds them.

### 3.5 Defined transitions

Each transition is explicit; no score or possession change is inferred solely from ball position.

| Transition | Assistant action |
|---|---|
| Touchdown | Operator selects scoring team and whether to add the displayed `+6` through the atomic command. Clear ordinary down/distance/ball status and offer the try workflow. An operator who already used the existing score control can select `score already recorded` to prevent duplication. |
| Try/PAT | Operator chooses scoring team and `+1`, `+2`, or no score. The result clears ordinary field status and offers kickoff setup. Defensive returns, blocked tries, and unusual local rules use manual correction. |
| Made field goal | Operator selects scoring team and whether to add `+3`; clear ordinary field status and offer kickoff setup. |
| Safety | Operator selects scoring team and whether to add `+2`; clear ordinary field status. The resulting free kick is explicitly set up by the operator rather than assumed. |
| Kickoff | Operator selects receiving team and final return/touchback spot, then starts that team's new first-and-ten series. An onside kick, kick-return touchdown, or other exception may leave through the manual path. |
| Manual set | Operator states team, down, distance or Goal, and the clicked spot; Python validates and derives only the line to gain; one atomic command; this is the in-assistant manual escape hatch that §2 and §7 reserve for unusual special-teams outcomes. |

Every scoring confirmation must display the exact point delta before it is applied. The existing quick score buttons remain available and unchanged.

## 4. Operator workflow

### 4.1 Start or re-sync a series

The window shows one panel at a time, chosen from the authoritative snapshot (see the September 5, 2026 amendment).

1. Open **Field Assistant** from the operator application. The quarter may still be `PRE`; the assistant works there, and finalizing does not advance the quarter.
2. **Direction panel** (shown only until a first-quarter direction has been saved for this game): answer *Which end zone does HOME score in during the 1st quarter?* with **◀ LEFT end zone** or **RIGHT end zone ▶**. The drawing mirrors to match at once; the choice is saved by the first confirmed series and never asked again.
3. **Start panel** (shown whenever no team has the ball): click the field where the ball is, then press **HOME BALL HERE** or **AWAY BALL HERE**. This is the opening kickoff return, every post-score kickoff return, and any re-sync after a manual correction — a kickoff is simply "the receiving team's ball here".
4. The Confirm button reads the result — **CONFIRM → Start 1st & 10 — HOME ball · 1st & 10 · at HOME 25**, or **1st & Goal** when the line to gain is the goal line — and one press commits it.
5. The assistant shows the ball, direction arrow, and line to gain. The existing operator and spectator windows show the resulting snapshot.

### 4.2 Finalize a normal scrimmage play

1. After the whistle, move the draft ball to the final real-world spot by click, drag, yard buttons, arrow keys, or the typed yard line. It stays where it is put; nothing but **Reload from scoreboard**, a commit, or re-opening the window moves it.
2. **Play panel:** press **PLAY OVER — BALL HERE** or **INCOMPLETE PASS**. For a punt, interception, fumble recovery, turnover on downs, or kickoff return press **OTHER TEAM'S BALL HERE**, which names the new offense and starts its 1st & 10 at the ball.
3. Python re-calculates the proposed result on every change without being asked, and the Confirm button's label states it (first down, goal-to-go, next down). A fourth-down failure disables Confirm and names the **… BALL HERE** button that makes the change of possession explicit; possession is never flipped by inference.
4. Press the single large **CONFIRM → …** control.
5. One authoritative snapshot updates the original operator view and spectator board.

### 4.3 Penalty workflow

1. Start from the play's proposed final spot, or select **Incomplete** when applicable.
2. Use `−15`, `−10`, `−5`, `+5`, `+10`, or `+15` to set the enforcement spot. Directional labels must make clear whether a move benefits the offense, not merely whether it moves left/right on screen.
3. Select repeat down, count down, automatic first, no play, or decline.
4. Review the stated field result and confirm once.

### 4.4 Scoring and kickoff workflow

1. Press **SCORE…** after the official outcome is known. The panel lists **TOUCHDOWN**, **FIELD GOAL**, and **SAFETY** with one button per team, each showing its points, plus the **TRY / PAT** row (**NO GOOD**, **KICK +1**, **2-POINT +2**) for a chosen team.
2. The Confirm label states the exact point delta and that down/distance will clear; tick *Points were already added on the main scoreboard* to commit the transition without re-adding them.
3. Confirm the transition. After a touchdown the panel stays open on the try for the scoring team; after a try or field goal the start panel offers **HOME/AWAY BALL HERE** for the kickoff return.
4. If the real play does not match a supported path, press **FIX MANUALLY…** (section 4.6) or use the main window's Field drawer and then **Reload from scoreboard** here.

### 4.5 Manual fallback, revision protection, and Undo

- On open, the assistant reads one complete current snapshot and records its base revision.
- The draft ball is the operator's until they finish with it. It is re-seeded from the authoritative spot only on open, on **Re-sync**, and after a committed action. The ten-per-second refresh push updates every read-only readout and may re-draw the draft on the mirrored side at a quarter boundary, but never moves it, and never silently changes what Confirm would send.
- If the current operator screen, keyboard shortcut, or another accepted action changes that revision, the assistant displays **FIELD STATUS CHANGED ELSEWHERE — RE-SYNC REQUIRED**. It must disable Confirm Play until the operator re-syncs or discards the draft.
- Re-sync never tries to merge a stale draft. It uses the current authoritative field status as the new baseline.
- A finalized assistant operation is one reversible history item, including all changed football fields and any confirmed score delta. Undo restores the complete prior authoritative state as one action; it must not leave a new ball spot paired with old down/distance.
- An assistant failure, closed helper window, invalid draft, or stale revision changes no game state and never stops a clock.

### 4.6 Fix manually

1. When the real outcome does not match any supported transition, select **Manual set** instead of closing the assistant.
2. State the team, down, distance (or Goal), and the spot the operator clicked. These are the only facts the operator supplies.
3. Python still validates the quarter and team, rejects an impossible down/distance, and refuses a spot sitting on a goal line. It derives the line to gain itself; it is never accepted from the payload. A requested distance that would overrun the goal line is clamped to it, and the persisted distance is corrected to match so down/distance/line-to-gain always agree.
4. Confirm once. The result commits as the same single atomic command as every other transition, with its own history entry and Undo.

## 5. Interface requirements

- The Field Assistant window targets the existing operator-screen sizes, including 1366×768 at 100% and 125% scaling, without page scrolling during ordinary play finalization.
- The field visibly shows HOME/AWAY end zones, yard lines, a draggable/clickable ball, offense direction, and line to gain. It must not rely on color alone for any of those meanings.
- Current authoritative status and the derived proposed status are visually distinct.
- Clock state remains visible as read-only context, but no clock controls appear in the assistant.
- The primary action is a single Confirm button whose label is the previewed result (`CONFIRM → …`). Exactly one panel of choices is visible at a time, and every choice is a labelled button; dangerous or ambiguous result choices remain explicit rather than being inferred by drag distance.
- The spectator display remains read-only and receives only committed snapshots.

## 6. Required architecture and persistence behavior

- Implement pure football-field calculation separately from command handling and UI.
- Add an additive, versioned assistant/series state only where it is required to recover an active line to gain and first-quarter direction. It must recover safely and never prevent recovery of older saved games.
- Use one composite validated command such as `finalize_field_play` or another clearly named equivalent. It must check the expected revision, validate the full proposed transition, persist state and action history in the existing transaction, increment revision once, and publish one snapshot.
- Record source, old/new relevant values, selected outcome, penalty resolution where applicable, optional score delta, and result in durable history.
- Existing `set_down`, `set_distance`, `set_possession`, `set_ball_on`, and scoring commands retain their behavior. The new operation composes state internally; it must not call those commands one after another through the bridge.

## 7. Explicit exclusions and safe manual escape hatches

- No live ball tracking. The operator finalizes only after the play is over.
- No automated officiating judgment, foul detection, clock control, statistics, video, networking, or physical-controller work.
- No automatic possession flip from a fourth-down failure, a score, a safety, or ball position alone.
- No automatic OT-direction logic until local overtime rules are approved.
- No attempt to model offsetting/multiple penalties, blocked kicks, onside kicks, defensive try returns, or other exceptions beyond a clear manual fallback.

## 8. Test matrix

| ID | Area | Scenario | Expected result |
|---|---|---|---|
| FA-01 | Coordinate conversion | HOME 0/25/50 and AWAY 0/25/50 round-trip | Physical spot is preserved; midfield normalizes to HOME 50. |
| FA-02 | Direction | Both first-quarter on-screen-side choices across 1st–4th | HOME/AWAY rules-coordinate directions stay fixed per team (HOME `+1`, AWAY `-1`) across every quarter; only `home_goal_side` mirrors at each quarter boundary; physical ball spot remains fixed. Corrected September 5, 2026 — see Amendments; originally specified as alternating per-team directions. |
| FA-03 | Series start | First-and-10 at midfield, own 25, opponent 10, and opponent 5 | Correct line to gain and distance; either opponent 10 or 5 becomes Goal-to-Go. |
| FA-04 | Normal play | Gain short of line to gain | Ball moves, down advances once, line to gain remains, distance is correct. |
| FA-05 | First down | Gain exactly to and beyond line to gain | First down, new line to gain, correct ten/goal-to-go distance. |
| FA-06 | Loss | Backward play from a normal series | Down advances; distance increases correctly without invalid field position. |
| FA-07 | Incomplete | Incomplete at each down | Ball and line to gain remain; down advances; no clock mutation. |
| FA-08 | Fourth down | Fourth-down miss | Helper proposes, but does not silently commit, turnover on downs. |
| FA-09 | Goal line | Proposed normal play at/beyond either goal line | Ordinary confirmation is rejected; explicit transition is required. |
| FA-10 | Penalty spot | Each ±5/±10/±15 action near both goal lines | Proposed spot is clamped/validated and direction labels are correct. |
| FA-11 | Penalty outcome | Repeat, count, automatic first, no play, decline | Each produces only its documented down/line-to-gain consequence and a descriptive history entry. |
| FA-12 | Turnover | Explicit change of possession at either side of field | New offense, final spot, first-and-ten, direction, and line to gain are correct. |
| FA-13 | Touchdown | Score add and score-already-recorded paths | Correct optional +6 once; ordinary field status clears; no duplicate score. |
| FA-14 | Try/PAT | +1, +2, and no-score outcomes | Correct optional score delta and kickoff offering; no invented special-rule behavior. |
| FA-15 | Field goal/safety | Made field goal and safety for both teams | Correct optional points; field status clears; follow-up does not assume possession. |
| FA-16 | Kickoff | Touchback and return-end spots for either receiving team | Receiving team starts a new series at confirmed spot with first-and-ten/goal-to-go. |
| FA-17 | Atomicity | Finalize a play changing ball, down, distance, possession, and score | One revision, one persisted transaction, one history entry, one published complete snapshot. |
| FA-18 | Undo | Undo every composite outcome | Entire previous state returns in one logged Undo; no partial field-status pairing occurs. |
| FA-19 | Stale draft | Manual field edit or score changes revision while draft is open | Confirm is disabled; re-sync/discard is required; no stale write occurs. |
| FA-20 | Manual fallback | Existing field controls before/after helper use | Their command behavior remains unchanged and the assistant can re-sync from them. |
| FA-21 | Clock isolation | Finalize each supported outcome with game/play clocks stopped and running | Both clocks' values/running states are unchanged. |
| FA-22 | Recovery | Restart during an active series and after a composite command | Line-to-gain/direction state and committed snapshot recover safely; clocks recover stopped under existing rules. |
| FA-23 | Old data | Recover a pre-Field-Assistant saved game | Defaults are safe; no migration prevents startup; assistant asks for setup. |
| FA-24 | Persistence failure | Simulated transaction/write failure on finalize | No partial state/history is visible; existing operator remains usable and error is reported. |
| FA-25 | Spectator publication | Observe snapshots during confirm and failed/stale submit | Only one post-commit complete snapshot is rendered; no partial update follows a failure. |
| FA-26 | Window failure | Close/fail Field Assistant while clocks run | Core operator, spectator, persistence, and clocks continue; reopening gets the latest snapshot. |
| FA-27 | Layout/accessibility | 1366×768 at 100% and 125%; keyboard and pointer workflows | Ordinary finalization fits without scrolling; all meanings have text/shape cues; draft controls are keyboard reachable. |
| FA-29 | Draft ownership | Move the ball by nudge, arrow key, drag, and yard selection while refresh pushes continue; then Re-sync, then confirm a play | The spot stays exactly where the operator put it across any number of pushes; only open, Re-sync, and a committed action re-seed it; a quarter boundary re-draws the same spot on the mirrored side. |
| FA-30 | PRE quarter | Stage an opening series and a normal play with the persisted quarter still `PRE`; then repeat in `HALF`/`OT`/`FINAL` | `PRE` calculates exactly as the 1st quarter does and finalizes without advancing the quarter; `HALF`, `OT`, and `FINAL` are refused with a manual-only message. |
| FA-28 | Rehearsal | Multi-quarter sequence: gains, loss, incomplete, penalty, turnover, TD, try, kickoff | Operator-visible results, action history, recovery, and spectator values agree at every finalized play. |
| FA-31 | Manual set | Operator states team, down, distance (or Goal), and the clicked spot, at each down and both goal lines, including a distance that would overrun a goal line | Line to gain is derived, never accepted; goal-to-go and overrun-clamped down/distance/line-to-gain always agree; an unestablished direction, an impossible down/distance, a goal-line spot, or a non-regulation/`OT`/`HALF`/`FINAL` quarter is refused; commits as one atomic command. |

## 9. Definition of done for implementation

The feature is ready for rehearsal only when the pure rule matrix, composite-command/persistence tests, stale-draft tests, existing-manual-control regression tests, UI window tests, recovery tests, and a multi-quarter rehearsal all pass. Native Windows/WebView2 and live operator rehearsal remain required evidence before any game-day use.
