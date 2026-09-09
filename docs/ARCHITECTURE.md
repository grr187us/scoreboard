# Architecture Evaluation and Decision

**Decision status:** Accepted for Phase 2, subject to an early Windows host proof and the Phase 0 HDMI gate
**Decision date:** September 4, 2026

## 1. Decision summary

Build the MVP as a **single local Python application process** with:

- a pure authoritative state/command core;
- monotonic, deadline-based game, play, and crowd-status clocks owned by that core (the game clock is also the kickoff and halftime countdown while the quarter is `PRE` or `HALF`; the separate event-countdown engine was removed September 9, 2026);
- local JSON configuration plus an embedded SQLite recovery database and automatic backup;
- a durable append-only action history stored with recoverable state;
- two primary HTML/CSS/JavaScript views hosted in managed `pywebview` windows: operator and spectator;
- two independently lifecycled helper windows the operator opens on demand — the Field Assistant (`views/field_assistant/`) and the presentation-layout editor (`views/layout/`) — neither of which is a production-display target, a display-health state owner, or an authoritative state owner;
- an optional, fixed-size 640×360 bordered spectator test window for local
  layout checks and operator practice; it is neither a production-display
  target nor a display-health state owner;
- a narrow JavaScript-to-Python command bridge and Python-to-view snapshot notifications;
- a PyInstaller one-folder Windows package after development behavior is proven.

This is a hybrid of option 1 (Python engine plus web presentation) and a small native window host. It deliberately omits a local HTTP/WebSocket server from the MVP. OBS and other integrations can later consume a read-only local transport adapter without taking ownership of state. The embedded SQLite store and automatic backup are confirmed implementation decisions, not a pending architecture choice.

## 2. Decision drivers

In order of importance:

1. Correct clocks and deterministic state changes.
2. Fast, understandable recovery during a game.
3. One-action, offline Windows operation.
4. Reliable separation and targeting of operator/spectator windows.
5. A presentation layer that can grow into polished graphics.
6. Testability without running a browser or OBS for core logic.
7. Extension points for OBS and hardware inputs without rewriting the game engine.

## 3. Options evaluated

Ratings are relative to this MVP: `Strong`, `Mixed`, or `Weak`. They are architecture judgments, not claims that the underlying tools are universally good or bad.

| Criterion | Python + web renderer | JS-only local app | Python-native rendering | Adapt existing project | OBS-centered | Recommended hybrid |
|---|---|---|---|---|---|---|
| Reliability | Strong core; browser/process details to manage | Mixed; one runtime, but browser state/timer lifecycle is fragile | Strong if one toolkit | Varies; no candidate matches requirements | Mixed; more configuration and failure surface | **Strong**; one authority/process, managed views |
| Simplicity | Mixed if server + browser are separate | Strong initially | Strong initially | Appears quick, but adaptation cost is high | Weak for basic scoreboard | **Strong**; Python + one host dependency |
| Windows support | Strong, but browser launch needs care | Strong in Edge/Chrome | Strong toolkit-dependent | Mixed | Strong when OBS/plugin versions align | **Strong**; WebView2 host with early proof |
| Offline operation | Strong when assets are local | Strong | Strong | Mostly possible | Strong after installation | **Strong** |
| Clock correctness | Strong with monotonic Python model | Mixed; possible, easy to implement poorly | Strong | Varies; several candidates tick callbacks | Mixed; plugin-dependent | **Strong**; pure injected-clock core |
| Fullscreen/output targeting | Mixed in external browser | Weak/mixed without a host | Strong | Varies | Strong through OBS canvas | **Strong** if pywebview screen proof passes |
| Packaging/startup | Mixed with server/browser orchestration | Mixed; Electron would add weight | Strong with mature toolkit | Varies | Weak for MVP: requires OBS + plugin setup | **Strong/mixed**; PyInstaller + WebView2 proof needed |
| Maintainability | Strong with boundaries | Mixed as rules grow | Mixed; presentation coupled to toolkit | Weak/mixed given candidate mismatch | Mixed; OBS APIs constrain core | **Strong**; pure core, replaceable views/host |
| Ease with Codex | Strong | Strong | Mixed | Mixed because legacy/foreign code | Mixed due C/C++/OBS APIs | **Strong**; Python tests + ordinary web assets |
| Automated testing | Strong | Strong for logic if carefully separated | Strong | Varies; most candidates sparse | Mixed; OBS-dependent behavior is costly | **Strong**; core tests do not launch UI |
| Recovery after failure | Strong if designed | Mixed; localStorage is insufficient alone | Strong | Varies | Mixed; state may live in plugin/config | **Strong**; SQLite transactions, backup, and stopped recovery |
| Future OBS integration | Strong via browser/local API | Strong | Mixed | Candidate-specific | Strong | **Strong** through optional read-only adapter |
| Future controller input | Strong command API | Mixed | Strong | Candidate-specific | Mixed; tends to couple to OBS actions | **Strong** through optional input adapter |
| Future multi-operator | Strong with later local transport | Strong with later transport | Mixed | Candidate-specific | Mixed | **Strong later**; explicitly deferred now |
| Media/animation | Strong web platform | Strong | Mixed | Varies | Very strong | **Strong later**; web view/optional OBS |

## 4. Why this is the smallest architecture that satisfies the MVP

A web renderer alone does not reliably choose and own a second Windows display. A separate web server plus a manually launched browser adds ports, processes, and operator steps before networking is needed. A full native renderer couples game logic to a presentation toolkit and makes future graphics harder.

The selected design adds only one MVP runtime dependency beyond Python: `pywebview`, using the Windows WebView2 runtime. It keeps one process, one authority, managed windows, and ordinary HTML/CSS/JavaScript. The core does not import the UI host, so the window technology can be replaced if the first Phase 2 proof exposes unacceptable behavior.

PyInstaller is a build-time dependency, introduced after the development launcher is stable. One-folder packaging is preferred first because its contents and missing assets are easier to diagnose than a self-extracting one-file executable.

## 5. Rejected or deferred alternatives

### 5.1 Python engine + external browser/server

**Deferred, not rejected.** A local `aiohttp` HTTP/WebSocket adapter is a good future boundary for OBS or multiple operators. It is unnecessary for one local operator in the MVP and complicates startup, ports, browser profiles, fullscreen, and shutdown.

### 5.2 HTML/CSS/JavaScript-only local application

**Rejected for the authoritative core.** JavaScript can implement a correct monotonic/deadline clock, but local file/browser lifecycle, persistence, multi-window coordination, and future hardware input are less predictable. Candidate projects using callback decrement and `localStorage` demonstrate how quickly a simple overlay becomes a fragile game controller.

### 5.3 Python-native rendering

**Rejected for presentation, retained for hosting.** Tkinter/Qt drawing could make a reliable basic board, but polished scalable graphics, theming, and future OBS/browser consumption would cost more. Native window management remains useful through the small webview host.

### 5.4 Adapt an existing scoreboard

**Rejected after repository review.** No evaluated candidate provides the required football scoring increments, independent 25/40 play clock, safe correction/recovery, spectator-scale fullscreen output, and non-OBS Windows operation with a suitable maintained/tested core. Specific patterns may be borrowed; code will not be copied without license review.

### 5.5 OBS-centered implementation

**Deferred to Phase 3.** OBS is excellent for scenes, media, and compositing, but it is unnecessary for scores and clocks and would make a large application/plugin part of the core failure surface. The MVP must survive with OBS absent.

### 5.6 Existing-project hybrid

**Rejected as a code base; accepted as a learning strategy.** The project will borrow patterns such as local snapshots, presentation consumers, hotkeys, event logs, and separation of core logic from integrations while implementing a smaller domain-specific core.

## 6. Authoritative state and command flow

```text
Operator HTML/JS
      │ validated command request
      ▼
Python command service ──► pure state/rules ──► new immutable snapshot + revision
      │                           │
      │                           ├──► SQLite state + action-history transaction
      │                           └──► verified database backup
      │
      ├──► operator snapshot notification
      └──► spectator snapshot notification
```

The Python command service is the only writer. JavaScript stores only ephemeral view state such as an open drawer or focus. Every command contains a command name, arguments, input source, and optional state revision; the service validates and serializes commands, produces one new state revision, persists it, logs it, and publishes a complete snapshot.

Publishing complete small snapshots is simpler and safer than applying a chain of UI-side deltas. A newly opened spectator view can render the latest snapshot immediately.

### Lifecycle and spectator visibility (Task 8)

Accepted quarter changes, including quarter Undo, set lifecycle from the manual
label: PRE/PRE_GAME, HALF/HALFTIME, FINAL/FINAL, otherwise IN_PROGRESS.
A Game Clock Start while PRE runs only the kickoff countdown and remains PRE_GAME;
an accepted quarter transition enters IN_PROGRESS.
New Game restores PRE_GAME; End Game sets FINAL. Expiry never advances it.
Entering PRE or HALF selects the corresponding event preset only when the event
kind differs; an already selected countdown retains its current value. This
uses EventCountdown.select and does not reset the game/play clocks.

Every quarter command is a two-step, expected-revision-protected operation.
Its Python-generated confirmation describes source/target, clocks that will
stop, and any clock load. PRE to a live quarter discards the pregame value and
loads stopped 12:00; PRE to 1st with time remaining carries the exact stronger
accept label `Start 1st quarter — discard remaining pregame time`. A normal
live-quarter transition loads 12:00 only from zero. Clock-loading transitions
are non-undoable because quarter-only Undo cannot restore their prior value.

The state and persisted snapshot carry an additive boolean `play_clock_cleared`.
Preset/correction makes it false; manual clear and a stopped-to-running game
Start make it true; reset follows whether an engine preset exists. Expiration,
Stop, other commands, checkpoints and recovery preserve it. Legacy snapshots
without the field retain the previous stopped-zero-is-blank interpretation;
the old format cannot distinguish an expired zero from a cleared zero.

### Expanded football state (September 5, 2026)

`GameState` additively carries `down`, `distance`, `possession`,
`home_timeouts`/`away_timeouts`, and `ball_on`. Each is independently settable
through its own validated command and its own reversible Undo entry; none is
derived from or coupled to a scoring, clock, or quarter command, on the same
"no invented rule automation" principle as the rest of this document.

Field position (`ball_on`) is one compound value, `BallSpot(team, yard_line)`,
on the same immutable-frozen-dataclass pattern as `ClockValue` rather than two
separate state fields. `yard_line` (0-50) is always counted from `team`'s own
goal line. Keeping it one field lets the existing generic Undo mechanism
(`application.service._handle_undo`, generic over `entry.field`)
reverse it as a unit with no special case, the same way it already reverses
`game_clock`/`play_clock` corrections without knowing anything about clocks.

Since September 6, 2026 (audit I4), the application keeps a bounded in-memory
LIFO stack of at most 20 reversible entries. Each Undo is still one validated,
logged command; non-reversible barriers clear the stack, and startup recovery
deliberately restores none of it.

A compound field reaching a generic `getattr(state, field)` path (Undo, and
the durable action-history JSON encoder) is converted to its plain field
dictionary rather than left as a domain object: `application/service.py`
converts it before building the `EventIntent` Undo returns, and
`infrastructure/persistence.py`'s history encoder converts any dataclass
generically (`dataclasses.asdict`) as a second, structural safety net. This
was found as a real defect during Task implementation -- the generic path
briefly reached the JSON boundary with a raw `BallSpot` -- and both fixes are
required together: the service-layer one keeps the immediate command result
correct, and the persistence-layer one protects any future compound field
whose own command handler forgets to convert it before logging.

Like `play_clock_cleared`, every new field is additive: `snapshot_to_state()`
defaults a snapshot with no `"football"` key to the same values
`default_state()` carries, so a game saved before this change stays
recoverable without a schema-version bump (P-004, P-006).

### Field Assistant (September 5, 2026)

The Field Assistant composes the existing layers rather than adding a new
authority. Pure rules (`domain/field_assistant.py`, no I/O, no clocks)
calculate a proposed result from a draft action. The composite
`finalize_field_action` command (`domain/commands.py`,
`CommandType.FINALIZE_FIELD_ACTION`) validates that result against the
current authoritative state inside `application/service.py`'s existing
one-expected-revision-check, one-transaction, one-revision-increment,
one-complete-snapshot discipline — the same discipline every other command
already follows, not a second command path. `host/bridge.py`'s
`FieldAssistantBridge` is the only surface JavaScript can call
(`get_snapshot`, `preview_field_action`, `finalize_field_action`), and the
helper window (`views/field_assistant/`) renders a draft and requests a
finalize, on the same "Python calculates, JavaScript only renders and
requests" rule as every other view. `preview_field_action` runs the same pure
rules read-only and advances no revision — the same pattern
`LayoutEditorBridge`'s preview/validate methods already use for presentation
layouts.

Two fields are additive on `GameState`, recovering safely from an older saved
game the same way `play_clock_cleared` and the football fields above do:
`assistant_first_quarter_home_direction` (`+1`/`-1`/`None`) and
`assistant_line_to_gain` (`0`-`100`/`None`). `ball_on` may now also become
`None` as the result of an assistant-driven scoring transition clearing field
status; a manual `set_ball_on` command is unchanged. The persisted snapshot
(`application/snapshots.py`) carries an additive `assistant` block holding
these two fields; a snapshot without it recovers to safe "setup required"
defaults, on the same additive-snapshot pattern as the football fields above.

The rules engine's coordinate is label-based, not a rotating one: `0` is
always the HOME goal line and `100` is always the AWAY goal line
(`docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md` section 3.1), so each team's
direction in that coordinate is fixed — HOME always `+1`, AWAY always `-1` —
rather than alternating by quarter. What alternates is presentation only: the
operator's one-time first-quarter choice records which side of the on-screen
field drawing HOME attacks toward, and the drawing mirrors at each quarter
boundary (`home_goal_side` in the bridge view model); stored ball spots and
line-to-gain never move at a quarter change. This corrects an inconsistency
in the original design, which proposed flipping the label-based direction
itself every quarter — a literal flip would have moved a 2nd-quarter HOME
gain toward HOME's own goal line. See the Decision Log in
`PROJECT_ROADMAP.md` and the Amendments note in
`docs/FIELD_ASSISTANT_RULES_AND_WORKFLOW.md`.

## 7. Clock model

Use an injected `MonotonicClock` interface backed in production by `time.monotonic_ns()`. Wall-clock time is used only for human-readable log timestamps, never to calculate remaining game time.

For each countdown clock store:

- `running`;
- `base_remaining_ns` captured when last stopped/corrected;
- `started_at_monotonic_ns` when running;
- configured preset/default;
- an expiration-generation identifier so expiration logs once.

While running:

```text
remaining_ns = max(0, base_remaining_ns - (now_monotonic_ns - started_at_monotonic_ns))
```

Stopping materializes the current remaining value into `base_remaining_ns` and clears the anchor. Starting sets a new anchor without rounding away the remainder. UI refresh timers merely request/render the derived value; delayed callbacks cannot create cumulative drift. Expiration is detected when the derived value reaches zero, then materialized and logged once.

Game-clock and play-clock Edit Current Time commands first materialize and stop their target clock, validate the requested time, then apply it with an explicit `start_after_apply` choice that defaults false. This preserves a single logged, testable correction path rather than letting a view edit timer state directly.

Presentation formatting is a pure derived function; it never changes stored time. Whole seconds round upward so the board never understates time remaining; neither clock displays tenths of a second (September 7, 2026: tenths read as basketball, not football). This keeps `1:00` visible through 59.0–59.99 seconds and `5` visible through 4.0–4.99 seconds, only stepping down once the clock truly reaches the next whole second.

Game and play clocks are separate instances under one coordinator. In PRE, that same authoritative Game Clock engine is configured to 30:00 and rendered as `KICKOFF IN`; it has no play-clock coupling and expiry remains PRE. An accepted departure from PRE replaces it with the applicable stopped live-quarter value. Halftime remains the separate 15:00 `UNTIL SECOND HALF` interval engine, changing presentation phase from `HALFTIME` to `WARMUP` at 3:00. All engines use the injected monotonic model; JavaScript only renders Python's formatted snapshot.

The deliberate game/play-clock couplings apply only in live quarters. A live Game Clock stopped-to-running transition clears the play clock; its real running-to-stopped Stop/expiry transition clears it too. PRE Start, Stop, and expiry never invoke those couplings. No expiry emits an alarm or automatic quarter transition.

## 8. View bridge and process model

The existing `command(name, args, expected_revision)` argument envelope accepts
`source` metadata restricted to `operator-mouse` or `operator-keyboard` (mouse is
the compatibility default). It is removed before validating command arguments.
The keyboard adapter reads the rendered snapshot for Space and uses the same
submission/confirmation function as mouse controls. Confirmation retains the
revision shown when it was opened; a later state change makes it stale instead
of silently confirming against new values. No new command/API method is added.

Startup recovery uses a separate `StartupBridge` with report/resume/new methods. Only after an explicit choice does the host create the operator with `ScoreboardBridge`; the startup window is retired. Non-interactive launches retain `RecoveryChoiceRequired`.

- One Python process creates both webview windows and starts the application event loop.
- The operator JavaScript invokes a deliberately small Python API such as `command(name, args, expected_revision)` and `get_snapshot()`.
- The bridge calls a host-only accepted-command callback after persistence; the host immediately notifies both windows. Ticks retain timed refresh/checkpoint work. No new JavaScript API method is needed. Python notifies both windows after an accepted command or clock-display boundary. The JavaScript renderer replaces displayed values from the snapshot.
- **Publishing never holds the command lock (audit C4, September 6, 2026).** The installed WebView2 backend implements `evaluate_js` as a synchronous `Invoke` followed by an untimed semaphore wait, and `Window.run_js` uses the same path, so there is no non-blocking way to reach a window. `ScoreboardApplication.tick()` and `_publish()` therefore build an immutable batch — sequence, revision, operator view, and spectator snapshot — under `_command_lock` and deliver only after release. The bridge's `command()` and `finalize_field_action()` likewise invoke the accepted-command callback after release, and unexpected exceptions become logged `INTERNAL_ERROR` rejections rather than escaping into the window. `host/publisher.py` moves the blocking call to one daemon worker, retains only the latest pending view per window, and emits one `PUBLISH_STALLED`/`PUBLISH_RECOVERED` pair around a slow call. Thus a blocked webview cannot stop commands, clock derivation, persistence, or checkpoints.
- **Known C4 deviation, reopened by the September 6 reconciliation.** The current `_publish_lock` covers only the `(revision, sequence)` check/update; it is released before the batch's per-window offers. Two caller threads can therefore pass the check in order but interleave an older spectator offer after a newer one. The existing ordering test invokes batches serially and does not force this schedule. In addition, one `WindowPublisher` worker drains all window names, so a blocked delivery delays later deliveries to otherwise healthy windows. These are presentation-delivery defects, not authoritative-state failures, but the stronger stale-proof/per-window-isolation contract is not yet met. C4 remains open until the implementation and a forced-interleaving test close both gaps. `publish_layout()` also remains a direct layout-bridge webview call outside the command lock.
- The spectator bridge exposes no mutating API. **Added September 8, 2026
  (owner request 5, decision 6).** `SpectatorBridge` is read-only about the
  game; its one action closes its own window. `close_display()` -- optional
  keyword `close` at construction, feature-detected by the spectator page as
  `typeof api.close_display === 'function'` so an older host answers plainly
  instead of throwing -- reaches nothing but the window it belongs to: no
  score, no clock, no quarter, not even another window (D-005). `DisplayLink`
  (`host/bridge.py`) gained the matching `close()` hook, overridden by
  `WindowHost` the same way `reopen()` already is; on its own it closes
  nothing. `ScoreboardBridge.close_display()` is the operator-side host
  action in the `reopen_display()` family -- under `_lock`, contained like
  every other diagnostics-reporting host action, advancing no revision and
  writing no history row -- and returns the same `displays()` payload
  `reopen_display()` does so the Display drawer can re-render from it.
  `WindowHost.close_spectator()` (`host/app.py`) is what both bridges'
  `close` callables ultimately reach: it destroys the spectator window
  outside the lock (as `open_spectator` already does), publishes the pinned
  `CLOSED_BY_OPERATOR_DETAIL` sentence through `spectator_closed()`, and
  leaves the saved display and `can_reopen` untouched so one click reopens
  it. The later `closed` event pywebview fires for the now-destroyed window
  is a no-op, because `_spectator_closed` already guards on window identity.
  The practice test window gets its own small `close_test_window()`, which
  touches no display health at all -- it was never part of that contract.
- **Added September 8, 2026 (owner request 5, decision 1).** The operator
  view model gains a `setup` block (`operator_view_model()`,
  `_setup_view()` in `host/bridge.py`): `teams_pending`/`home_pending`/
  `away_pending` booleans and a `detail` sentence, present only while the
  game is pregame and a team name is still its shipped placeholder. Python
  owns the sentence -- `scoreboard.domain.state.setup_prompt_detail()` is the
  one function that produces it, so the Teams-drawer prompt and the kickoff
  confirmation that repeats it can never disagree about the wording -- and
  the operator page only copies `detail` into the drawer and the `NOT
  CHOSEN` panel line. The spectator view model deliberately has no `setup`
  key at all: the wall never shows an instruction meant for the booth. An
  older operator build with no `setup` key is tolerated the same way a
  missing `undo_history` already is.
- The presentation-layout editor bridge follows the same rule. `host/layout_bridge.py`'s `LayoutEditorBridge` can read a live snapshot and validate/preview/save/select/delete/reset a layout, but it has deliberately no `command()` method and no way to change a score, clock, quarter, or any other game value. Its window follows the same ownership pattern as the Field Assistant helper: `WindowHost.open_layout_editor` opens it independently of the operator and spectator windows, and its closed-callback clears only its own slot, so closing or losing the editor affects no other window and advances no state revision. The editor's Motion switch (added September 8, 2026) is held to the same rule from the other side: it is a *host preference* in `config.json`, not a layout property, so `LayoutEditorBridge.set_motion`/`PresentationLayouts.set_motion` advance no revision and write no history row, and `WindowHost.publish_motion` pushes the on/off state to the spectator, practice, and layout windows with `window.applyMotion` the same way `publish_layout` pushes a layout. A layout's `ticker` element, by contrast, is ordinary layout content, not a preference or game state: its announcement lines live in the layout document and are edited exactly like a text element's wording.
- The Field Assistant bridge is narrow in a different direction: `host/bridge.py`'s `FieldAssistantBridge` exposes `get_snapshot`, `preview_field_action` (read-only, advances no revision), and `finalize_field_action` (the one composite command), all JSON-compatible. It has no other mutating method, and the helper window it serves is opened, closed, and reopened independently of the operator and spectator windows (`host/app.py`); a helper push failure destroys only the helper. `ScoreboardBridge` also defines those two methods so `FieldAssistantBridge` can delegate to it, so the isolation claim is about the *consumer*, not reachability: the Field Assistant page is the only caller, and the operator page never invokes them.
- All bridge payloads are JSON-compatible, versioned dictionaries; domain objects do not leak into JavaScript.
- If a view notification fails, log it, keep the core running, mark display health, and allow recreation from the latest snapshot.
- The optional test spectator window consumes the same read-only spectator
  snapshot through its own bridge and receives the same updates, but it has a
  separate lifecycle. Opening, closing, or failing that practice aid neither
  reads nor writes the saved-display preference and never changes the
  production spectator health strip.
- **Two new host→spectator globals for cutscenes (added September 6, 2026).**
  `window.applyCutscene(program)` and `window.endCutscene(play_id)` are
  pushed to the spectator and test windows the same way `window.applyLayout`
  is: `WindowHost.publish_cutscene`/`end_cutscene` call `evaluate_js` outside
  both the command lock and `_command_lock`'s batch delivery, wrapped in
  try/except so a cutscene push can never stop the game — a failed push is
  logged and the window survives, the same contract `publish_layout` already
  keeps. `SpectatorBridge` gained a third, read-only method, `get_cutscene()`,
  so a spectator window opened mid-cutscene (a reopened display, a freshly
  opened practice window) asks the host directly for the program in
  progress rather than missing it until the next trigger. Like the layout
  push, neither global is part of the 10 Hz view model; the operator and
  Cutscenes windows get their countdown from the ordinary view instead
  (`view["cutscenes"]`, below), never from these two globals.

This is an in-process transport, not a claim that multi-operator networking exists. A future transport implements the same command/snapshot contracts.

## 9. Configuration, state, and logs

Use the Windows per-user application data location, resolved through the platform API rather than a repository-relative path. SQLite is the confirmed embedded durable store for recoverable state and action history; no database server is permitted. Proposed logical layout:

```text
Scoreboard/
  config.json
  data-location.json               # stored in the platform-default root only
  scoreboard.db
  scoreboard.backup.db
  cutscenes.json                   # which pack is selected per cutscene event (added September 6, 2026)
  cutscenes/                       # cutscene pack folders, one manifest.json each (added September 6, 2026)
  logs/
    application.log
```

- `config.json`: schema version, defaults, display identity/geometry, operator preferences, shortcut map. In use since Task 10 for the display section, and since September 9, 2026 for the `rules` section (`domain/rules.py`'s `GameRules`: quarter/overtime/pregame/halftime lengths, warmup threshold, crowd timeout length, timeouts per half — a laptop preference the Setup drawer edits through the `rules()`/`save_rules()` host actions, never game state); read tolerantly, so a damaged or newer-version file reads as "no preferences" and never stops a launch.
- `data-location.json`: the chosen data-folder pointer, kept only under the platform-default Scoreboard root so the next launch can locate `config.json`, databases, layouts, teams, and logs in the chosen folder. `infrastructure/paths.py`, not `config.py`, owns this bootstrap layer; a bad pointer falls back safely.
- `scoreboard.db`: schema version, app version, state revision, lifecycle, teams/scores/quarter, materialized clock values, last command metadata, and append-only action history.
- `scoreboard.backup.db`: automatically refreshed last-known-good database backup. Since September 6, 2026 (audit C4) the refresh is bounded: the first commit of a session, `record_shutdown`, and `close()` refresh it immediately, and any other verified commit refreshes it at once only when `BACKUP_MIN_INTERVAL_SECONDS` (2 s) have passed since the last refresh — otherwise the refresh is marked pending and the next clock checkpoint flushes it once the interval has elapsed. A full SQLite copy no longer runs inside every accepted command under the command lock.
- `teams.json` (audit F4, September 6, 2026): the saved-team library — up to 64 entries of team name, a short name of up to six characters, and two `#RRGGBB` colours — in its own file with its own schema version, for the same reason `layouts.json` is separate from `config.json`: a damaged team library must not be able to cost the operator their saved display or layouts. Read and written by `infrastructure/teams.py` under the same never-stop-the-scoreboard contract (a missing, unreadable, newer-schema, or malformed file reads as an empty library; a bad entry is dropped with an issue while its siblings load; writes are atomic and never overwrite a newer schema). `host/teams.py`'s `TeamPresets` holds it in memory for the bridge. Team identity is deliberately **not** game state: `GameState` still carries only the two names, applying a saved team is the ordinary `set_team_name` command (pregame-only, confirmed, undoable, in the action history), and the bridge merely attaches each side's matching identity — or `null` — to every operator and spectator view by looking up the current name. `teams()`, `save_team()`, and `delete_team()` are host actions like the display and layout ones: no revision, no command, no history row.
- action history: append-only rows retaining accepted and rejected operator requests with timestamps, sequence, source, command, result, and relevant old/new values.
- diagnostic log: bounded rotating log for startup/errors; exact retention is a Phase 2 implementation detail.

For every accepted state-changing command, validate in memory, update recoverable state and append its history row in one SQLite transaction, then commit. While a clock runs, checkpoint materialized values at each displayed-second boundary without adding synthetic tick events to the action history. Refresh the last-known-good backup after verified commits on a bounded, testable policy. On startup validate the primary database, fall back to the backup, and surface the source. Running clocks always recover stopped at the last persisted derived values, with a visible checkpoint timestamp so the operator can reconcile the game.

**Stored and logged timestamps stay unambiguous UTC ISO 8601 strings** (P-010,
September 5, 2026); nothing about the database schema, the action history, or
`infrastructure/diagnostics.py`'s log lines changed. `infrastructure/local_time.py`
is a pure, separate display-only conversion (`format_local_timestamp()`) used
only where an operator *reads* a timestamp -- the recovery screen's "Last
saved" line and its non-interactive CLI equivalent -- converting to Eastern
local time (`America/New_York`) with correct daylight-saving handling. Windows
does not ship the IANA time zone database that `zoneinfo` needs to resolve
that name, so `tzdata` is a pinned runtime dependency rather than something
the operating system is assumed to provide (R-001, W-006).

### Presentation layout (`layouts.json`), added September 5, 2026; schema v2 the same day; schema v3 added September 6, 2026

Spectator-board placement, size, color, visibility, and (as of schema v2) free text/image/box elements and a board background are a host/presentation concern, exactly like the display preference and the data-folder choice above: `PresentationLayouts` (`host/layout_bridge.py`) reads, validates, stores, and publishes layouts, and advances no state revision, submits no `Command`, and writes nothing to `scoreboard.db` or its backup.

**Historical schema-v2 addition.** Schema v2 made `background` and `elements` additive to the v1 document and accepted versions 1 or 2, normalizing them to 2. A v1 document gained defaults with exactly one `SCHEMA_UPGRADED` warning. A document may hold up to `MAX_ELEMENTS = 24` free-standing `text`, `image`, or `box` items, each with geometry, stacking order, and supported style properties. Elements never participate in widget-overlap validation; only text is held to the safe area, while images and boxes may fill the canvas. Image data is restricted to validated inline PNG/JPEG/GIF/WebP, capped at 2 MB per image and 6 MB decoded per screen. Those v2 contracts remain active under current schema v3.

**Schema v3 (September 6, 2026).** `LAYOUT_SCHEMA_VERSION` is now **3**; `validate_layout` accepts `schema_version` 1, 2, or 3 and always normalizes to 3. A v1 or v2 document is upgraded in place with the same one warning (`SCHEMA_UPGRADED`), so a layout saved by any earlier version keeps opening; any other version is still a hard `SCHEMA_VERSION` error.

A v3 document adds one top-level key, `screens`, alongside the v1/v2 top-level shape. The **top level of the document remains the game screen** — its own `safe_area`, `background`, `widgets`, and `elements` — so existing readers keep working. The current registry contains seventeen game widgets: the original fifteen plus `status_message` and `status_clock`, which carry F3's crowd-facing status message and its countdown. Both are *optional* widgets: their bound values are empty strings whenever no status is raised, so the renderer hides them rather than drawing empty boxes, and the board looks exactly as it did before F3 until an operator raises a message. `screens.pregame` and `screens.halftime` are each a complete mini-document with the same four keys — their own `safe_area`, `background`, `widgets`, and `elements` — but drawn from a different registry of eight **event widgets** (home/away team name and score, phase label, countdown title, countdown, and a warmup line). `screens` missing from a v3 document (but not from a v1/v2 upgrade, where `SCHEMA_UPGRADED` already covers it) is filled from defaults with one warning (`MISSING_SCREENS`); a single missing screen fills from its own default with `MISSING_SCREEN`; an unrecognized key under `screens` warns (`UNKNOWN_SCREEN`); anything not shaped as expected is a hard error (`SCREENS` / `SCREEN`).

Validation, element-id uniqueness, `MAX_ELEMENTS`, and `MAX_TOTAL_IMAGE_BYTES` are enforced **independently per screen** — a screen's elements may not reuse that screen's own widget ids, and the same element id may appear on more than one screen without conflict, but each screen has its own 24-element and 6 MB-image ceiling. Every validation issue carries the id of the screen it belongs to (`"game"`, `"pregame"`, or `"halftime"`); a game-screen issue keeps its existing unprefixed message text so no current test or stored expectation changes, while a pregame or halftime issue is prefixed with its screen's label (for example "Halftime: Countdown must sit inside the safe area."). `clamp_layout` repairs every screen the same way it already repairs the top level.

One stored layout — one entry in `layouts.json` — always carries all three screens; there is no way to save or reference a screen independently of the layout document it belongs to. See `docs/UX_AND_LAYOUT.md` §10.9 for the operator-facing switcher, event widget inventory, and per-screen presets this schema change enables.

The layout library lives in its own file, `layouts.json`, in the same per-user Scoreboard data folder as `config.json` and `scoreboard.db` — **never as a section inside either of them**. A library can hold several named layouts and carries its own schema version; keeping it a separate file means a damaged layout library cannot cost the operator a saved game, and a damaged game cannot cost the operator a saved layout. It follows the same "a preference file may never stop the scoreboard" contract as `config.py`: an atomic temp-file-plus-`os.replace` write, and a read failure of any kind — a missing file, invalid JSON, a wrong or newer schema version, or an individually unrecoverable stored layout — falls back first to the last valid stored layout and then to the built-in default, never raising and never stopping launch.

The active layout is deliberately not part of the 10 Hz view model. It changes rarely, so the host pushes it to the spectator, practice, and editor windows only when it actually changes (`window.applyLayout(...)`), the same push-on-change pattern already used for the display and data-folder preferences, rather than carrying it on every refresh tick.

#### Optional widget formats and text fitting (September 7, 2026)

Schema v3 widgets add `display_format` (default `default`) and `fit_text`
(default `false`). Missing properties normalize silently, preserving older
layouts. An unsupported format for that widget or a non-boolean fit flag
rejects the draft. The game registry allow-lists ordinal quarter/down,
value-only distance/ball position, and dots-only timeouts. The editor's
Format choices come from widget descriptors; there is no arbitrary field
binding or game-text editor. Event widgets support only the default format.

The Python view model supplies the alternative strings from the same
authoritative state; JavaScript selects an allowed binding, never strips
suffixes, computes ordinals, or counts timeouts. The timeout formatter uses
`MAX_TIMEOUTS`, emitting filled/hollow circles with no visible numeric count.
Standard readouts and the operator's combined field status remain intact.

The shared renderer retains its latest read-only model so a layout-only
format change rebinds immediately, including with stopped clocks. Opt-in
text fitting measures rendered text against available box space and shrinks
it on one line without changing the string or the saved font size. Width
comes from the laid-out text (so tabular digits and letter spacing count);
height comes from the glyph ink via a 2D canvas `measureText`, because a
display face such as Impact has a CSS line box nearly half again as tall as
its digits and fitting to the line box would leave a score small in its
panel. A fitted line therefore may overhang its box invisibly while the
glyphs stay inside. A measurement cache avoids recomputing unchanged text
each clock tick; content, box, font, or layout changes invalidate it.
Scoreboard Grid enables fitting for team names, scores, clocks, and the stat
readouts. This is presentation geometry only and has no path to game
commands, persistence, or clock timing. `FONT_FAMILIES` gained
`bahnschrift_condensed` (the Bahnschrift variable font's condensed named
instance, present on Windows 10 and later) for the preset's labels.

Every widget and element also carries `corner_cut` (0 to
`MAX_CORNER_RADIUS`, default 0) and `cut_corners` (one of
`CUT_CORNER_SIDES`: all/top/bottom/left/right, default all). The renderer
sets `--cut` and a `data-cut-corners` attribute only when the cut is
positive; `board.css` then clips the box to a chamfered polygon, turns the
CSS border transparent so geometry is unchanged, and paints the border
colour in a `::before` clipped with an even-odd ring between the outer
polygon and a parallel inner one. The cut is capped at half the box so
opposite cuts meet in a point. Missing properties normalise to the
defaults, so older layouts are untouched.

Box elements may be hairlines: `_element_minimum_size` returns
`MIN_BOX_THICKNESS` (0.002) for a box and the widget minimum for text and
image elements, in both validation and clamp repair; the editor's resize
minimum mirrors it through `limits.min_box_thickness`. `MAX_ELEMENTS` is 40
per screen. `FONT_FAMILIES` also gained `varsity`, whose stack is
`'Jersey M54', Graduate, Impact, ...`: Graduate is the one bundled font
(`views/shared/fonts/Graduate-Regular.ttf`, SIL OFL, declared by an
`@font-face` in `board.css`, carried by the package-data patterns and the
build script's required-file list); Jersey M54 is used only when the
operator has installed it.

A widget's text is written through `setWidgetText`, which wraps each colon
in a `.clock-colon` span (the node's `textContent` is unchanged, so the
fit and hide logic is unaffected); a per-font rule lifts Impact's colon,
which the face draws low for lowercase text, to the centre of lining
digits. The spectator's running-clock recolouring rules in `board.css` are
commented out at the owner's request (September 7, 2026); the
`running-game`/`running-play` classes are still applied.

### Cutscene packs (`cutscenes/`, `cutscenes.json`), added September 6, 2026

Cutscenes are a host concern, exactly like the presentation layout and the
saved teams above: `host/cutscenes.py`'s `CutsceneDirector` owns playback
state and advances no state revision, submits no `Command`, and writes
nothing to `scoreboard.db` or its backup. `presentation/cutscenes.py` is the
pure schema module (event registry, pack-manifest validation, and the
program builder — see below); `infrastructure/cutscene_packs.py` is its I/O
half, mirroring `layouts.py`'s and `teams.py`'s "never touch `config.json`
/ `layouts.json` / `teams.json` / `scoreboard.db`" boundary and their
atomic-write, never-raise, never-stop-the-scoreboard contract.

A **pack** is a folder under `cutscenes/` holding a `manifest.json` and,
optionally, one media file (`.webm`/`.mp4` video or `.png`/`.gif`/`.jpg`/
`.jpeg`/`.webp`/`.apng` image); the folder name is the pack's id. Five
code-authored **built-in** packs (`builtin:first_down`, `builtin:touchdown`,
`builtin:turnover`, `builtin:penalty`, `builtin:make_some_noise` — one per
entry in `CUTSCENE_EVENTS`)
ship with no files at all, so the feature works before an operator ever
drops anything in. `ensure_packs_directory` creates the folder and writes a
`README.txt` into it the first time, explaining the manifest shape in plain
words; `scan_packs` reads every immediate subfolder's `manifest.json`,
validates it through `presentation.cutscenes.validate_manifest` (strict,
with a plain-language fallback exactly like a layout: an unusable pack is
skipped with a reported issue rather than crashing a trigger), and returns
every usable pack plus every issue found. Which pack is selected per event
is stored separately, in **`cutscenes.json`** at the data root — not inside
the `cutscenes/` folder itself, so an operator who empties that folder to
start over cannot also lose the selection file — with its own schema
version, read tolerantly (a missing file, bad JSON, wrong schema version, or
a non-string value yields "nothing selected" for that event, never an
exception) and written atomically (temp file plus `os.replace`).
`CutsceneLibrary.resolve(event)` returns the selected pack, or the built-in
with a recorded fallback when the selection names a pack that is missing or
belongs to a different event.

There are five events (`CUTSCENE_EVENTS`: `first_down`, `touchdown`,
`turnover`, `penalty`, `make_some_noise` — the last two added September 6,
2026, cutscenes v3) and **no home/away choice anywhere in the feature**
(September 6, 2026, cutscenes v2). Which side a cutscene is for is a
property of the event, not an argument: `EVENT_TEAM` maps every event to
`"home"` except `penalty`, which maps to `None`, and `build_program()`,
`CutsceneDirector.trigger()`, `CutscenesBridge.trigger()`, and
`ScoreboardBridge.trigger_cutscene()` all take an event and nothing else.
The sibling tables `EVENT_DEFAULT_INTRO` and `DEFAULT_DURATION_SECONDS`
give the claw strike and 5/10/7 s to first down, touchdown, and turnover,
and no intro at all to the 7 s penalty and the 5 s make-some-noise crowd
prompt (at 5 s a 1.6 s claw would eat a third of the scene). `EVENT_SUBLINE`
is the per-event subline template — `{team}`, `{team}`, `{team} BALL`,
`PENALTY`, `{team} FANS` — formatted with the fixed school identity.

Triggering a cutscene builds one JSON **program** — `build_program()` in
`presentation/cutscenes.py` — carrying everything the spectator page needs:
the duration, the stage rectangle, a deep copy of the resolved Broadcast bar
layout (renamed `"Cutscene"`) that becomes a temporary override, the intro
and scene descriptors, theme colours, and the three text values
(`headline`, `subline`, `team_name`) — no score, which the Broadcast bar
under the stage is already showing. For every branded event, `team_name` is
the fixed school identity `Tigers` rather than the configurable home-team
name, and `subline` is `EVENT_SUBLINE[event]` formatted with `TIGERS`
(`TIGERS`, `TIGERS BALL`, `TIGERS FANS`), so the scoreboard's initial
`HOME` label cannot leak into a cutscene; the penalty remains team-neutral
with subline `PENALTY` and an empty `team_name`. `CutsceneDirector.trigger()` reads the
live spectator snapshot
*before* taking its own lock, deliberately avoiding a lock-ordering
collision with the 10 Hz tick, which already holds that lock when it calls
`status()` to fill every operator view (see the comment in `trigger()`).
Publishing the program to the spectator/test windows happens outside the
lock through a `CutsceneLink` seam (mirroring `LayoutLink`), wrapped in
try/except so a publish failure can never stop the timer that ends the
cutscene — the wall may simply not show it, exactly like a layout push
failure. The end of a cutscene is scheduled on an injectable timer
(`threading.Timer` in production) rather than the 10 Hz tick, so the
countdown shown to the operator and the Cutscenes window (`view["cutscenes"]`)
is computed once in Python and only copied by JavaScript, the same rule
every other clock in this document follows.

`CutscenesBridge` is the new **Cutscenes** window's deliberately small JSON
API (`get_snapshot`, `state`, `trigger`, `cancel`, `rescan`, `select_pack`,
`open_folder`) — no `command` method, following the same isolation contract
as `FieldAssistantBridge` and `LayoutEditorBridge` above. `WindowHost.open_cutscenes`
follows the identical open/replace/close pattern as `open_field_assistant`.

## 10. Windows startup and display selection

Development startup will be one documented PowerShell command after environment setup. Production startup will be a shortcut to a PyInstaller one-folder executable; it starts both windows and no terminal is required.

The original Task 1 proof enumerated `pywebview.screens`, showed name/geometry choices, and opened a placeholder spectator window on an explicitly chosen screen in borderless fullscreen. It deliberately stored no display preference. That behavior is retained here as historical evidence only; the production host now uses the Task 10 display policy below.

**Task 10, September 5, 2026.** The identity is now saved, in the `display` section of `config.json` — the first use of the file section 9 reserved for it. It holds the Windows device name plus geometry, never a list position. `host/displays.py` stays pure: it takes a screen list and a stored preference and returns a decision, so the whole policy is testable on a one-display machine. `host/app.py` owns the Windows calls — `pywebview.screens` for geometry and `WinForms.Screen.AllScreens` for device names, both injectable — and a bounded periodic check that reports a display appearing or disappearing without ever moving a window. Resolution order is an explicit operator choice, then `--display-index`, then the saved display, then the first non-primary display; there is no fallback past that, so an unrecognised preference reports `DISPLAY NOT FOUND` rather than covering the controls (D-002, D-006). Selecting, reopening, losing, and forgetting a display are host actions: they advance no revision and write nothing to the game database, the same contract as `reopen_display()` and the data-folder picker.

The original Task 1 proof had to prove on Windows:

1. two windows open in one process;
2. the spectator window can target a selected second display and toggle fullscreen;
3. close/reopen does not stop the host;
4. WebView2 availability and packaged behavior are understandable;
5. application shutdown leaves no orphan process.

That proof passed on the development host. If WebView2 later fails materially on the target laptop, the fallback remains a small PySide6/Qt WebEngine host using the same HTML views and pure core. The domain architecture remains unchanged.

### Task 1 host evidence — September 4, 2026

The historical host proof used `pywebview==6.2.1` and no local HTTP server. Its pages were in-memory HTML loaded from bundled placeholder files; it intentionally did not include scoreboard state or persistence. The production implementation now uses the same managed-webview boundary for the authoritative scoreboard, SQLite recovery, operator view, spectator view, and startup recovery choice. The tested host used CPython 3.11.11 and Windows WebView2 Runtime `152.0.4191.62`.

Focused display-selection tests passed (four tests): display labels are deterministic, a valid selected screen object is preserved, a missing selection never falls back to the primary display, and a late close event from a replaced spectator cannot clear the newly reopened window. The actual host launched an operator plus explicitly selected fullscreen spectator window with `--display-index 0 --auto-close-after-seconds 30`, then exited with no `scoreboard-proof` or Python process remaining. The host also returned `DISPLAY NOT FOUND: Display 100` for an unavailable index. This runtime launch was performed with the normal sandbox network restriction active; it did not fetch packages or contact a service.

`pywebview.screens` reported only one available display on this host (`5120x1440 at 0,0`). Therefore, second-display placement, manual spectator close/reopen, fullscreen exit/re-entry, and offline manual operation remain reproducible acceptance checks on a normal two-display Windows setup; they are not claimed as completed local evidence. The Phase 0 stadium HDMI gate remains separate and open.

A follow-up executable smoke check on September 4, 2026 ran the proof with display indexes `0` and `99`, each with a five-second automatic close. Both exited with code 0, and post-run process checks found no remaining `scoreboard-proof`, `python`, or `pythonw` process. `pip check` and Python compilation also passed. The host's Wi-Fi adapter was connected with Internet connectivity during this check, so the required network-disabled repeat and the visible manual checklist items remain unverified; no result is inferred from the successful smoke exit.

## 11. Failure handling

| Failure | Required behavior |
|---|---|
| Spectator window closes/crashes | Core and operator continue; health strip reports `DISPLAY CLOSED`; one-click recreate from latest snapshot (a 44 px `Reopen Display` in the strip and again in the Display drawer, since September 6, 2026) |
| A window's WebView2 stops servicing scripts (GPU hiccup, native dialog, laptop under load) | Only the publisher thread waits; the refresh loop keeps checkpointing, commands keep completing, and the newest view is delivered when the window recovers. `PUBLISH_STALLED` / `PUBLISH_RECOVERED` are logged once each. Nothing in the game engine or persistence can block on a window |
| HDMI/display disappears | Core continues; the periodic display check reports `DISPLAY NOT FOUND` and names what is still true (running, saving); explicit reselection/reopen after Windows re-enumerates it, never an automatic move |
| The display list cannot be read at all | The check is switched off for the session and logged; the game, the operator, and the manual display panel all continue |
| Operator view closes | Ask for confirmation during normal close; if it is lost unexpectedly, clocks/core continue only if a visible recovery path remains, otherwise fail closed and persist stopped state |
| Persistence write fails | Keep in-memory operation, show persistent warning, write diagnostic log if possible, retry on next command; never claim `SAVED` |
| Primary database corrupt | Validate and load database backup; show recovery banner and log the fallback |
| Both databases invalid | Do not guess; offer new game and show paths for recovery; preserve invalid databases |
| Second instance starts | Refuse authority on the same data directory and explain how to focus/close the existing instance |
| Unhandled fatal exception | Best-effort diagnostic logging and safe materialized database checkpoint; recovery starts stopped |

## 12. Future integration boundaries

### OBS

Add an optional local output adapter that publishes read-only snapshots or a browser-source page. OBS can render state or switch scenes, but cannot become the canonical clock. If OBS is unavailable, the core spectator view still works.

### Physical controller

After safe identification and permission, add an input adapter that translates supported device events into the same validated commands used by mouse/keyboard. Disconnecting it has no effect on authoritative state or standard controls.

### Multiple operators

Initial operation is expected to involve two people, but Phase 2 has one laptop operator. The second person's peripheral is a future optional input adapter and cannot be authoritative or required for keyboard/mouse operation. If real workflow later demands two independently interacting clients, add authenticated local-network command clients through a transport adapter. State revisions and command serialization remain in the same authority. This is intentionally outside MVP.

### Media and animation

Spectator HTML can add transitions without changing state; long-running
media/OBS actions react to logged domain events and must be cancelable and
never delay score/clock commands. **Cutscenes (added September 6, 2026)
are the first realization of this boundary**, and its shape is the pattern
any future media feature should follow:

- **Manual trigger only.** Nothing here reacts to a score, a down, or any
  other domain event automatically — v1 is deliberately a button/hotkey the
  operator presses, not an OBS-style automatic cue. A future automatic
  trigger would still have to satisfy the "never delay score/clock
  commands" rule above.
- **A pack, not a hard-coded animation.** The unit of media is a folder
  (`cutscenes/<folder>/manifest.json` plus an optional video or image) that
  an operator can drop in and select without a restart; the app ships
  entirely code-authored built-in scenes so it works with zero media files.
  This is the extension point for "swap the animation for a video file"
  without touching Python.
- **One program, built once, interpreted, not computed, by JavaScript.**
  `presentation/cutscenes.py`'s `build_program()` is the single place that
  decides duration, stage geometry, the temporary layout, colours, and text;
  `cutscene.js` only runs a timeline against that document and manipulates
  the DOM. This is the same "Python owns every value, JavaScript copies"
  rule the presentation layout and the event-widget screens already follow.
- **Cancelable and self-healing.** `CutsceneDirector.cancel()` ends a
  cutscene immediately on request; a media file that fails to load falls
  back to the built-in scene for the rest of the cutscene rather than
  leaving the stage blank; and the spectator page runs its own safety-net
  timer that restores the board even if the host process never sends the
  end signal. The clock and score under the stage never stop updating.
- **Cutscenes are decoration, not a state owner.** No `Command`, no
  revision, no history row, nothing in `scoreboard.db` — see the "Cutscene
  packs" subsection of §9 for the full read/write contract this rests on.

## 13. Testing strategy

- **Pure unit tests:** state validation, command transitions, undo, scoring bounds, quarter workflow, snapshot schema.
- **Deterministic clock tests:** injected fake monotonic time, callback stalls, sub-second pause/resume, expiration, simultaneous clocks.
- **Persistence tests:** SQLite transaction interruption, backup fallback, schema rejection/migration, restart-stopped behavior, and write failure.
- **Bridge/contract tests:** JSON schema/version, stale revision handling, command rejection, complete snapshot rendering.
- **UI tests/manual checks:** focus suppression, held keys, dangerous confirmations, viewport matrix, display close/reopen.
- **Windows package tests:** clean account, no Python/Node/OBS, offline launch, correct data location, no orphan process.
- **Operational tests:** forced crash, HDMI disconnect, four-quarter rehearsal, two-hour soak, vendor fallback procedure.

## 14. Dependencies and constraints

- Start with Python standard library for domain, persistence, and logging.
- Add `pywebview` only in the host layer and pin the validated version.
- Add `pytest` and minimal test tooling as development dependencies.
- Add PyInstaller as a pinned build dependency after the host proof.
- Bundle every presentation asset; do not load fonts/scripts from a CDN.
- Do not introduce Node.js merely to build static HTML/CSS/JS unless a specific Phase 2 need justifies it.
- Do not add a database server, container, cloud account, or background Windows service.

## 15. HDMI-dependent decisions

The Phase 0 test does **not** need to validate the pure game architecture. It must determine:

- whether HDMI remains the system boundary at all;
- the physical resolution/aspect ratio and Windows display identity behavior;
- safe margins, scaling, seams, and readability targets;
- refresh/reconnect behavior and whether pywebview fullscreen survives processor input changes.

If a normal desktop cannot drive the wall, pause spectator/display implementation and investigate the processor boundary. Do not reverse-engineer the RJ45-style links by default.

## 16. ADR: Python authority with managed web views

### Context

The project needs correct football clocks, a simple local operator screen, a scalable fullscreen display, reliable recovery, and future production extensibility. OBS is useful later but too large a core dependency. Existing projects offer patterns but not a suitable foundation.

### Decision

Use a pure Python authoritative core and managed HTML/CSS/JavaScript operator/spectator views in one local process. Use monotonic deadline-based clocks, an embedded SQLite recovery database with a durable action history and automatic backup, and an optional-adapter boundary for future integrations.

### Consequences

**Positive:** one authority and launch action; core tests are UI-independent; web presentation remains flexible; display windows are managed; SQLite provides transactional offline recovery and action history; OBS/controller failure cannot corrupt core state.

**Negative:** pywebview/WebView2 and PyInstaller behavior must be proven on Windows; SQLite schema/backup recovery requires testing; in-process bridge code is custom; a later network/OBS consumer requires an adapter rather than being built in now.

### Revisit triggers

- The Windows multi-window/fullscreen/package proof fails materially.
- The stadium HDMI gate disproves normal display output.
- Real multi-operator requirements arrive earlier than expected.
- A maintained, correctly licensed project appears that meets the requirements with demonstrably less risk.
