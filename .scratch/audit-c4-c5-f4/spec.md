# Deep-dive audit items C4, C5, F4 — implementation spec

Status: implemented pass with C4 reopened by the September 6 reconciliation.
C5 and the presets half of F4 are present; C4 preserves command-lock isolation
but still needs cross-thread/per-window delivery ordering fixed and tested.
This remains the implementation evidence trail. Where it is silent, keep today's behaviour and the house
rules in `AGENTS.md` (validated commands only, Python produces every displayed
value, presentation is never an authoritative state owner, a preference file
may never stop the scoreboard, no network).

The three findings, verbatim from `PROJECT_ROADMAP.md` ("Deep-dive audit"):

- **C4** — Every 100 ms tick blocks unboundedly on WebView2 while holding the
  command lock. `ScoreboardApplication.tick()` holds `_command_lock` across
  `_publish` → `WindowHost._push` → `window.evaluate_js`, and the installed
  pywebview backend implements `evaluate_js` as `Invoke(...)` then
  `Semaphore(0).acquire()` with no timeout (`edgechromium.py:136-165`;
  `Window.run_js` goes through the same path, so there is no non-blocking
  primitive). A stalled WebView2 UI thread hangs the refresh thread holding the
  lock every command needs. Same-pattern siblings to fix in the same pass:
  `ScoreboardBridge.command()` publishes under the lock and has no catch-all
  like `tick()`; `GameStore._refresh_backup` does a full SQLite backup copy
  on every accepted command.
- **C5** — The display-recovery path is the hardest thing on screen to hit.
  `Reopen Display` is 32 px against the project's 44 px floor; the display
  selector lives inside the **Corrections** drawer one panel from destructive
  Apply buttons. Fix direction: a dedicated Display drawer, and a health-strip
  re-flow that meets 44 px without pushing live controls off 1366×768 (U-001).
- **F4** — No team presets, colours, or logos; both names are retyped from a
  blank state every week. Scope here is the **S–M "presets" half**: a saved
  team library with one-click apply, carrying a short name and two colours.
  Visual identity on the spectator board (colour-bound widgets, logos) is the
  L half and is explicitly **out of scope**; the view model carries the
  identity so that later work has the data.

Test command (always an isolated data dir):

```
SCOREBOARD_DATA_DIR=<scratch dir> ./.venv/Scripts/python.exe -m unittest <module or discover -s tests> -v
```

The reconciled suite is green: 853 tests, 0 failures, 0 errors, 3 skipped (the 3
skips name owner question A-1 and stay skipped). Any other failure is a
regression you introduced. Never add `-t .`.

---

## 1. C4 — publish off the lock, bound the slow work (Agent A)

### 1.1 `ScoreboardApplication` (`src/scoreboard/host/app.py`)

Contract to preserve: the application stays window-free and synchronous.
`set_publisher(push)` installs `push(window_name, view)`; tests count those
calls (`test_a_tick_publishes_to_both_windows` expects exactly
`["operator", "spectator"]` per tick; `test_scoring_finalize_is_one_revision_
one_history_row_one_complete_publish` expects exactly one publish per accepted
command). A push that raises for `"spectator"` still marks the display closed
and keeps the clock (`test_a_spectator_push_failure_marks_the_display_and_
keeps_the_clock`).

Change:

1. `tick()` holds `_command_lock` only for `_watch_displays()`, `bridge.tick()`,
   and building the two snapshots. The pushes happen **after** the `with`
   block. Concretely, factor a `_snapshot(operator_view)` that, under the
   lock, returns a small immutable batch: a monotonically increasing sequence
   number (`self._publish_seq += 1`), the operator view's `revision`, the
   operator view, and `bridge.spectator_snapshot()`. `_deliver(batch)` runs
   outside the command lock.
2. `_publish(operator_view)` (called by the bridge's `on_accepted` and by
   `spectator_opened/closed`) does the same: take the command lock briefly to
   build the batch (RLock, so it is harmless when a caller already holds it),
   release, then `_deliver`.
3. Ordering guard in `_deliver`: a separate `self._publish_lock`
   (`threading.Lock`) serialises deliveries; a batch whose
   `(revision, seq)` is lower than the last delivered key is dropped
   silently (a later snapshot already went out). Same-revision ticks have
   increasing seqs, so clock refreshes are never dropped in order.
4. The per-window try/except behaviour of today's `_publish` is unchanged
   (operator push error → `unhandled_error(context="operator_push")`;
   spectator push error → `unhandled_error(context="spectator_push")` **and**
   `bridge.display_closed(...)`; field-assistant push error →
   `unhandled_error(context="field_assistant_push")`). `display_closed` then
   publishes again through `_publish` — that is fine (new seq, same revision).

### 1.2 `ScoreboardBridge` (`src/scoreboard/host/bridge.py`)

1. `command()` and `finalize_field_action()` build the accepted view under the
   lock but call `self._on_accepted(view)` **after** the `with` block. The
   returned payload is built under the lock as today.
2. Catch-all, mirroring `tick()`: wrap the body of `command()` after
   `build_command` (service submit + record + payload) so that an unexpected
   exception is reported as `self._diagnostics.unhandled_error(context=
   "command", error=exc, command=str(name))` and the method returns a
   rejection payload `{"accepted": False, "confirmation_required": False,
   "error": {"code": "INTERNAL_ERROR", "message": "That control failed
   unexpectedly and changed nothing. The game is still running; see the
   diagnostics log."}, "event": None, "confirmation": None, "view":
   self._view()}`. Add `INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"` next to
   the other codes and export it. A `CommandError` from `build_command` keeps
   today's path. Do the same for `finalize_field_action()` with
   `context="finalize_field_action"`. Persistence failures are already
   handled inside `GameStore` and must keep their existing status behaviour.

### 1.3 `WindowHost` publisher (`src/scoreboard/host/publisher.py`, new; wired in `app.py`)

The blocking call lives only at the window boundary, so that is where the
wait is bounded. New module `src/scoreboard/host/publisher.py`:

```python
class WindowPublisher:
    """Latest-wins, one-thread delivery of view models to webview windows."""
    def __init__(self, deliver: Callable[[str, dict[str, Any]], None], *,
                 on_stall: Callable[[str, float], None] | None = None,
                 on_recovered: Callable[[str, float], None] | None = None,
                 stall_after: float = PUBLISH_STALL_SECONDS,   # 2.0
                 monotonic: Callable[[], float] = time.monotonic) -> None
    def offer(self, window_name: str, view: dict[str, Any]) -> None
    def start(self) -> None
    def stop(self, timeout: float = 2.0) -> None
    @property
    def started(self) -> bool
    @property
    def in_flight(self) -> tuple[str, float] | None   # (window_name, started_at) while delivering
```

Rules:

- `offer()` never blocks and never raises. While **not started** it calls
  `deliver` inline (synchronously) — this keeps every existing host test
  deterministic. While started it stores the view in a per-window "latest"
  slot (a newer offer for the same window replaces an undelivered older one)
  and wakes the thread.
- The thread drains slots in a fixed order (`operator`, `spectator`,
  `field_assistant`, then any other name) calling `deliver(name, view)` and
  catching every exception (report through `on_stall`? no — through the
  `deliver` callable itself; see below). The thread must never die on an
  exception.
- Stall detection: `offer()` (called 10×/s by the tick) checks `in_flight`;
  if a delivery has been running longer than `stall_after` and has not been
  reported, call `on_stall(window_name, elapsed)` once. When that delivery
  finally completes, call `on_recovered(window_name, elapsed)` once.
- `stop()` sets a stop flag, wakes the thread, joins with the timeout, and
  never raises even if the thread is stuck inside a stalled `evaluate_js`
  (the thread is a daemon named `scoreboard-publish`).

Wire it in `WindowHost`:

- `self._publisher = WindowPublisher(self._deliver, on_stall=..., on_recovered=...)`
  in `__init__`. `_push(window_name, view)` becomes `self._publisher.offer(...)`.
  Rename today's `_push` body to `_deliver(window_name, view)`; keep its
  behaviour, including destroying a test/field-assistant window whose push
  fails. Because `_deliver` now runs on the publisher thread, the operator and
  spectator `evaluate_js` errors that today propagate to
  `ScoreboardApplication._publish` must be handled here instead: catch, log
  `unhandled_error(context="spectator_push"/"operator_push")`, and for the
  spectator call `self.application.spectator_closed(f"The display stopped
  responding: {exc}")`. (The application-level try/except stays for the
  window-free/inline path.)
- `on_stall` → `application.diagnostics.note("PUBLISH_STALLED", window=name,
  seconds=round(elapsed, 1))`; `on_recovered` → `note("PUBLISH_RECOVERED", ...)`.
- `_operator_loaded()` calls `self._publisher.start()` immediately before
  `self.application.start_refresh()`; `_operator_closing()` calls
  `self._publisher.stop()` after `stop_refresh()`. `StartupGuardTests` call
  `_operator_loaded()` directly — add `self.addCleanup(host._operator_closing)`
  or an equivalent so no thread outlives a test.

### 1.4 Bounded backup refresh (`src/scoreboard/infrastructure/persistence.py`)

`_refresh_backup()` today copies the whole database after every accepted
command, under the command lock. Bound it without weakening the policy
("refresh after a verified commit, never from a half-written file"):

- New `BACKUP_MIN_INTERVAL_SECONDS: Final[float] = 2.0` and an injectable
  `monotonic: Callable[[], float] | None = None` on `GameStore.__init__`/`open`
  (default `time.monotonic`).
- `_refresh_backup(*, force: bool = False)`: if `force`, or no backup has been
  taken yet this session, or `monotonic() - self._last_backup_at >= interval`
  → back up now; otherwise set `self._backup_pending = True` and return.
- `checkpoint()` (called from every tick) ends by flushing a pending backup
  when the interval has elapsed. `begin_session` and `record_shutdown` use
  `force=True`; `record_command`, `record_expiration`,
  `record_game_clock_expiration_and_play_clock_clear` use the bounded call.
- Existing tests that read the backup right after a command must keep
  passing: the first backup of a session is immediate, and tests that need
  a later one either advance the injected clock or call `checkpoint(...,
  force=True)`; if a test genuinely needs "backup after this exact command",
  pass `monotonic=` a fake that advances ≥ 2 s per reading. Do not weaken
  `test_an_interrupted_commit_leaves_a_valid_backup`.

### 1.5 Tests for C4 (Agent A owns these files)

- `tests/integration/test_publish_off_lock.py` (new):
  - a `push` that blocks on an `Event` for `"operator"`: `tick()` returns on
    the refresh thread? No — simpler and deterministic: run `application.tick()`
    on a worker thread with a blocking publisher; from the main thread, within
    a 2-second wait, `bridge.command("game_clock_start", {}, 0)` must be
    accepted while the push is still blocked (proves the lock is free), then
    release the push. Mirror the C2 test in `test_data_folder.py` for style.
  - the ordering guard: deliver batches out of order by hand and assert the
    stale one is dropped.
  - `command()` catch-all: monkeypatch `service.submit` to raise; the result
    is `accepted False`, code `INTERNAL_ERROR`, a complete `view`, a
    diagnostics `unhandled_error` entry, and the store's status untouched.
  - `on_accepted` runs outside the lock: an `on_accepted` that asserts
    `not lock._is_owned()` — `RLock` has `_is_owned()` in CPython; or record
    whether `lock.acquire(blocking=False)` from another thread succeeds
    inside the callback.
- `tests/integration/test_window_publisher.py` (new): inline delivery when not
  started; latest-wins while a delivery is blocked (offer three views, only
  the last is delivered after release); stall/recovered callbacks fire once
  each using an injected monotonic; `stop()` returns within its timeout with
  a stuck delivery; a raising `deliver` does not kill the thread.
- `tests/integration/test_persistence.py`: add a test that the backup is not
  rewritten on every command inside the interval and is flushed by a later
  checkpoint (use the injected monotonic and the backup file's mtime or
  contents).
- Update `tests/README.md` table rows for the two new files.

---

## 2. C5 — a Display drawer and a 44 px Reopen (Agent B)

Files: `src/scoreboard/views/operator/index.html`, `operator.css`,
`operator.js`, `keyboard.js` (only if a close-list change is needed),
`docs/UX_AND_LAYOUT.md`, tests listed in 2.4.

### 2.1 Health strip

- `#reopen-display` becomes a real 44 px target: `.chip-button { min-height:
  var(--touch); min-width: 168px; font-weight: 700; font-size: 15px; }`.
  The strip is allowed to grow to 44 + padding; the body grid gives the board
  the flexible row, so nothing is pushed off screen — but you must **verify**
  at the two U-001 viewports (1093×614 CSS, and 1180×720) that
  `document.documentElement.scrollHeight === clientHeight` and every button
  in `.clocks` is inside the viewport (see 2.4).
- Add a second, always-visible button in the strip immediately after
  `#reopen-display`: `<button type="button" id="open-display" class="chip-button
  secondary" data-action="open_display">Display…</button>` (44 px too, `min-width`
  120px, `border-color: var(--edge)` so Reopen stays the loud one).
- Keep `#chip-display` as the status text. Remove the stale CSS comment that
  concedes 32 px.
- If the strip cannot hold everything at 1093 px wide, let `.brand` shrink
  (`font-size: 12px`, `letter-spacing: 0.04em`) and the chips' padding drop to
  `2px 6px` before anything else; do not wrap.

### 2.2 Display drawer

New `<div class="drawer" id="display-drawer" hidden aria-label="Spectator display">`
placed right after the `#corrections` drawer. Contents, in order:

1. `<h2>SPECTATOR DISPLAY</h2>` and a hint: "Where the board is shown. Nothing
   here changes scores, clocks, or the game."
2. Row `id="display-status-row"`: label "Status", `<span class="chip"
   id="drawer-display-chip">` (mirrors `#chip-display` text and bad/good
   flags), `<span class="folder-path" id="display-detail">` (the health
   `detail` text), and a second `Reopen Display` button `id="drawer-reopen-display"
   data-action="reopen_display"` (44 px; shown/hidden with `can_reopen`
   exactly like the strip button).
3. Row `id="display-row"` (keep this id and the ids/actions inside it — tests
   pin them): "Saved display" + `#display-summary` + `Forget saved display`
   (`data-action="forget_display"`).
4. `<p class="hint" id="display-note">` (same text as today).
5. Row `id="display-choices-row"`: "Available now" + `#display-choices`.
6. Row `.end`: Close.

Remove the display rows from `#corrections` (the data-folder rows **stay** in
Corrections — out of scope — but update the comment above them so it no
longer refers to "the row below it"). Corrections keeps score/clock/quarter/
team-name rows unchanged.

### 2.3 `operator.js`

- `handleAction('open_display')` → `openDrawer('display-drawer')` then
  `refreshDisplays()`.
- `reopen_display` (both buttons share the action): on `needs_selection`, open
  `display-drawer` (not corrections) and `refreshDisplays()`; drop the
  `scrollIntoView` on `#display-row` unless still useful.
- `renderHealth`: re-read displays when the label changes **and the display
  drawer is open** (replace the `corrections` check). Also mirror label,
  bad/good flags, `detail` (fall back to `health.display.target` when open) and
  `can_reopen` into the drawer's status row.
- `open_corrections` no longer calls `refreshDisplays()` (still refreshes the
  data folder).
- `closeDrawers()` list gains `'display-drawer'`.
- Everything else (display buttons with `data-display-key`, `forget_display`)
  unchanged.

### 2.4 Tests and verification for C5

- `tests/integration/test_display_selection.py::HostActionTests::
  test_every_display_control_is_reachable_from_the_operator_page` — extend:
  `id="display-drawer"` exists; `id="display-row"`, `id="display-choices"`,
  `data-action="forget_display"` are **inside** the display drawer (split the
  HTML on the drawer's opening tag and the next `<div class="drawer"`), and
  **not** inside `#corrections`; `data-action="open_display"` is in the
  `<header class="health"`; `id="reopen-display"` is in the header.
- New `tests/integration/test_display_drawer_contract.py`: `operator.css`
  gives `.chip-button` `min-height: var(--touch)` and no `32px` remains; the
  JS `closeDrawers` list names `display-drawer`; `reopen_display` handling
  opens `display-drawer` and not `corrections`; the display drawer contains
  no `data-command` (host actions only) and no `danger` button.
- `tests/integration/test_data_folder.py::OperatorControlTests::
  test_the_control_lives_inside_the_drawer` splits on `id="event-drawer"` to
  find the end of the corrections drawer — with the new drawer inserted
  between them it still works if the display drawer comes **after**
  corrections and before event-drawer; if you place it elsewhere, fix that
  split. Run the whole `tests/integration` package.
- Browser check (you must do it, not describe it): run Playwright via Node
  (`export PATH="/c/Program Files/nodejs:$PATH"`), a throwaway script in
  the scratchpad modelled on `tests/ui/keyboard.cjs` (stub `window.pywebview.api`
  with `get_snapshot`, `command`, `displays`, `reopen_display`,
  `forget_display`, `select_display`, `data_folder`, `teams` returning plain
  objects), at viewports 1093×614 and 1180×720: assert
  `#reopen-display` (make it visible by rendering a view whose
  `health.display.can_reopen` is true) and `#open-display` have
  `getBoundingClientRect().height >= 44`, the page has no vertical overflow,
  every `.clocks button` bottom ≤ viewport height, the header does not
  overflow horizontally (`header.scrollWidth <= header.clientWidth`), and
  clicking `#open-display` shows `#display-drawer` with the display buttons.
  Save a screenshot of each viewport into the scratchpad and name the paths
  in your report. Extend `tests/ui/keyboard.cjs` **only** if a small addition
  fits (it already runs the operator page at 1093×614); otherwise leave it.
- `docs/UX_AND_LAYOUT.md`: update §4 wireframe (Display… in the strip), §6.8
  (the fallback panel is now **Display… → Available now**), §8 (remove the
  concession; record the measured heights), and "Where the game is saved, and
  which display it is on" (display moved out of Corrections on September 6,
  2026; the data folder is still there and still the revisit).

---

## 3. F4 — team presets (Agent C backend, Agent D operator UI)

### 3.1 Design

Team identity is **not** game state: `GameState` keeps `home_name`/`away_name`
only; applying a preset submits the existing, validated `set_team_name`
command (pregame-only, F-010, undoable, in the action history). The library
of saved teams is a laptop preference like `layouts.json`: its own file,
its own schema version, "may never stop the scoreboard", atomic writes.

File `teams.json` in the data directory (`ScoreboardPaths.teams`,
`TEAMS_FILENAME = "teams.json"` in `infrastructure/paths.py`; add it to
`describe()`):

```json
{
  "schema_version": 1,
  "teams": [
    {"name": "Eagles", "short_name": "EAG", "primary": "#1F4E9A", "secondary": "#FFFFFF"}
  ]
}
```

Rules for one team (`validate_team(payload) -> TeamPreset | TeamIssue`):

- `name`: string, trimmed, 1–24 characters (the same rule as
  `domain.state.MAX_TEAM_NAME_LENGTH`; import the constant). Names are unique
  case-insensitively after trimming.
- `short_name`: optional string, trimmed, 1–`MAX_SHORT_NAME_LENGTH = 6`
  characters; when absent/blank, derive: the name with spaces removed,
  upper-cased, first 4 characters.
- `primary`, `secondary`: optional `#RRGGBB` (case-insensitive, stored
  upper-case); defaults `DEFAULT_PRIMARY = "#FFFFFF"`, `DEFAULT_SECONDARY =
  "#111111"`. Anything else → issue `INVALID_COLOR`.
- Unknown keys are ignored on read and dropped on write.
- `MAX_STORED_TEAMS = 64`; a save beyond that → issue `TOO_MANY_TEAMS`.
- Issue codes: `INVALID_NAME`, `INVALID_SHORT_NAME`, `INVALID_COLOR`,
  `TOO_MANY_TEAMS`, `NOT_FOUND`, `NOT_AN_OBJECT`, `SCHEMA_VERSION`,
  `TEAM_DROPPED` (a bad stored entry, siblings still load), `DUPLICATE`
  (a later duplicate stored entry, dropped).

### 3.2 `src/scoreboard/infrastructure/teams.py` (Agent C, new)

```python
TEAM_LIBRARY_SCHEMA_VERSION: Final[int] = 1
MAX_STORED_TEAMS, MAX_SHORT_NAME_LENGTH, DEFAULT_PRIMARY, DEFAULT_SECONDARY

@dataclass(frozen=True, slots=True)
class TeamIssue: code: str; message: str

@dataclass(frozen=True, slots=True)
class TeamPreset:
    name: str; short_name: str; primary: str; secondary: str
    def to_dict(self) -> dict[str, str]

@dataclass(frozen=True, slots=True)
class TeamLibrary:
    teams: tuple[TeamPreset, ...]
    issues: tuple[TeamIssue, ...] = ()
    fell_back: bool = False
    def find(self, name: Any) -> TeamPreset | None      # case-insensitive, trimmed
    def sorted(self) -> list[TeamPreset]                # by name, case-insensitive
    def to_dict(self) -> dict[str, Any]                 # the file document

def validate_team(payload: Any) -> TeamPreset | TeamIssue
def derive_short_name(name: str) -> str
def read_library(paths) -> TeamLibrary           # never raises; empty library on any failure, with issues
def write_library(paths, library) -> bool         # atomic temp + os.replace; never writes over a newer schema_version on disk (copy layouts.py's `_is_newer_on_disk` idea)
def save_team(paths, payload) -> tuple[TeamLibrary, TeamIssue | None]   # replace-by-name or append
def delete_team(paths, name) -> tuple[TeamLibrary, TeamIssue | None]
```

Mirror `infrastructure/layouts.py`'s docstring tone and error handling.
Never touch `config.json`, `layouts.json`, or `scoreboard.db`.

### 3.3 `src/scoreboard/host/teams.py` (Agent C, new)

```python
class TeamPresets:
    """The saved-team library as the bridge needs it: in-memory, locked, no game path."""
    def __init__(self, paths: ScoreboardPaths, *, diagnostics: Diagnostics | None = None) -> None
    @property
    def library(self) -> TeamLibrary
    def identity(self, name: Any) -> dict[str, str] | None     # {"name","short_name","primary","secondary"} or None
    def identities(self, home_name: str, away_name: str) -> dict[str, dict | None]   # {"home": ..., "away": ...}
    def state(self) -> dict[str, Any]     # {"teams": [preset dicts, sorted], "issues": [{"code","message"}], "fell_back": bool}
    def save(self, payload: Any) -> dict[str, Any]    # {"ok": bool, "message": str, "teams": [...]}
    def delete(self, name: Any) -> dict[str, Any]     # same shape
```

- Reads the library once in `__init__` (record `note("TEAM_LIBRARY_FELL_BACK",
  ...)` when `fell_back` or issues); `save`/`delete` write through
  `infrastructure.teams` then replace the in-memory library. A `threading.Lock`
  guards the in-memory library; `identity()` is a dict lookup and must stay
  cheap because the bridge will call it inside `_view()` ten times a second.
- Diagnostics notes: `TEAM_PRESET_SAVED` (`name`), `TEAM_PRESET_DELETED`
  (`name`), `TEAM_PRESET_REFUSED` (`code`, `message`).
- Messages: saved → `"Saved team NAME."`; replaced → `"Updated team NAME."`;
  deleted → `"Deleted team NAME."`; refused → the issue message.

### 3.4 Bridge and view-model contract (wired by the orchestrator after A and C finish; **Agent D builds against this shape**)

`ScoreboardBridge` gains a `teams: TeamPresets | None = None` keyword and three
JS-API methods, all host actions (no revision, no command, no history row):

```
api.teams()                -> {"teams": [...], "issues": [...], "current": {"home": identity|null, "away": identity|null}}
api.save_team(payload)     -> {"ok": bool, "message": str, "teams": [...], "current": {...}}
api.delete_team(name)      -> same shape
```

`operator_view_model` (and the spectator snapshot) gains, per side,
`teams.home.identity` / `teams.away.identity`: the matching preset dict
`{"name","short_name","primary","secondary"}` or `null` when the current name
matches no saved team. The identity is looked up by the **current team name**;
nothing else changes in the view model.

### 3.5 Operator UI (Agent D — starts only after Agent B has finished, because both edit the operator files)

Files: `src/scoreboard/views/operator/index.html`, `operator.css`,
`operator.js`; tests in 3.6; `docs/UX_AND_LAYOUT.md` (new §5b "Teams drawer").

- Tool bar: a new first button `<button type="button" id="open-teams"
  data-action="open_teams">Teams &#9656;</button>`.
- Drawer `<div class="drawer" id="teams-drawer" hidden aria-label="Teams">`
  placed after `#display-drawer` (or after `#corrections` if the display drawer
  is not there yet — read the file). Contents:
  1. `<h2>TEAMS</h2>`; hint: "Pick a saved team for each side. Team names can
     change only before kickoff, and each change asks you to confirm. Colours
     and short names are saved for the board; they never change scores or
     clocks."
  2. Row "Now": HOME `<span data-field="teams.home.name">` + `<span
     class="swatch" id="home-identity-swatch">` + `<span id="home-identity-short">`;
     AWAY likewise (`away-identity-swatch`, `away-identity-short`). A swatch is a
     20×20 box whose left half is `primary` and right half `secondary`; hidden
     when identity is null.
  3. `<div id="team-list" class="team-list">` rendered by JS from `api.teams()`:
     one `.team-row` per preset: swatch, `<span class="team-name-cell">NAME
     <small>(SHORT)</small></span>`, and buttons
     `Use for HOME` / `Use for AWAY` — these are ordinary command controls:
     `data-command="set_team_name" data-team="home" data-name="<name>"
     data-confirm="local" data-confirm-title="Change the HOME team name?"` —
     `argumentsFor()` gains `if (button.dataset.name !== undefined)
     args.name = button.dataset.name;` (before the `argSource` branch), so the
     existing local-confirm path (`describeChange` shows `OLD → NEW`), the
     source detection, and the revision check all apply unchanged. Then
     `Edit` (`data-action="edit_team" data-name=`, fills the form) and
     `Delete…` (`data-action="delete_team" data-name=`; opens the existing
     confirm dialog with a `perform` callback — extend `openDialog`/accept so
     a request may carry `perform: function()` instead of `command`; Cancel
     still does nothing).
     Empty library → a single `<span class="hint">No saved teams yet. Save the
     names below.</span>`.
  4. Form row `id="team-form"`: `<input type="text" id="team-name-input"
     maxlength="24" data-draft="true" aria-label="Team name">`, `<input
     type="text" id="team-short-input" maxlength="6" data-draft="true"
     aria-label="Short name (up to 6)">`, `<input type="color"
     id="team-primary-input" value="#FFFFFF" aria-label="Primary colour">`,
     `<input type="color" id="team-secondary-input" value="#111111"
     aria-label="Secondary colour">`, `<button data-action="save_team">Save
     team</button>`, plus `<button data-action="prefill_team" data-team="home">
     Use HOME name</button>` and the AWAY twin (copies the current name into
     the name field; nothing else).
  5. Row `.end`: Close.
- `operator.js`: `open_teams` → `openDrawer('teams-drawer')` + `refreshTeams()`;
  `refreshTeams()` → `api.teams()` → `renderTeams(payload)`; `save_team` reads
  the four fields at click time, calls `api.save_team({...})`, shows
  `result.message` via `showAlert`, re-renders the list; `delete_team` → confirm
  → `api.delete_team(name)`; `edit_team` fills the form; `render()` updates
  the two "Now" swatches from `model.teams.home.identity` /
  `model.teams.away.identity` and, on the live board, a thin identity stripe:
  `<span class="identity-stripe" id="home-identity-stripe" hidden>` inside
  each `.team` section right under `.team-name`, background = primary,
  `border-bottom` = secondary, text = short name — hidden when identity is
  null. `closeDrawers()` gains `'teams-drawer'`. `whenReady` also calls
  `refreshTeams()` once so the "Now" swatches are right before the drawer is
  first opened (identity also arrives in every view, so this is belt and
  braces).
- Nothing in the drawer computes or stores a team name: applying is
  `set_team_name` through `api.command`; the bridge refuses it after kickoff
  and the alert shows the refusal.
- If a bridge method is missing (`!api.teams`), the drawer shows "Saved teams
  are unavailable in this build." and the form is disabled — the operator
  page must never throw.

### 3.6 Tests for F4

Agent C:

- `tests/integration/test_team_library.py` (new): round-trip, atomic write,
  missing/invalid/newer-schema file → empty with issues and no exception,
  one bad entry dropped while siblings load, duplicate handling,
  case-insensitive replace on save, delete, the 64 cap, colour and short-name
  validation and derivation, `find()`, and the "never touches
  `config.json`/`layouts.json`/`scoreboard.db`" boundary (same style as
  `test_layout_persistence.py`).
- `tests/integration/test_team_presets.py` (new): `TeamPresets` — identity
  lookup, `identities()` for two names, save/delete messages and diagnostics
  notes, refused save returns `ok: False` and the issue message, a library
  file that fails to write returns `ok: False` and keeps the old in-memory
  library.
- Update `docs/PROJECT_STRUCTURE.md` (tree and the responsibility table) and
  `tests/README.md` for the new modules/tests.

Agent D:

- `tests/integration/test_team_presets_ui.py` (new, source-contract style like
  `test_data_folder.py::OperatorControlTests`): `data-action="open_teams"` in
  the tool bar; `id="teams-drawer"` exists and holds the form ids; the
  drawer's static HTML contains no `data-command` (the apply buttons are
  generated); `operator.js` contains `api.teams()`, `api.save_team(`,
  `api.delete_team(`, sets `data-command` to `set_team_name` for the generated
  buttons, and `argumentsFor` reads `dataset.name`; `closeDrawers` names
  `teams-drawer`; no `set_team_name` string is computed from anything but a
  preset name.
- Browser check with a stub bridge (same recipe as 2.4, at 1093×614): open the
  drawer, render two presets, click `Use for HOME`, assert the confirm dialog
  shows `HOME → Eagles`, confirm, and assert the stub received
  `command("set_team_name", {team:"home", name:"Eagles", source:..., confirmed:true}, rev)`;
  save a team through the form and assert `save_team` was called with the
  four fields; screenshot to the scratchpad and name the path.

---

## 4. Documentation (orchestrator, after verification)

`PROJECT_ROADMAP.md` (C4/C5/F4 rows, Current Status, Decision Log, Next Action
item 3), `docs/ARCHITECTURE.md` §8 (publisher, off-lock publish, bounded
backup) and §9 (`teams.json`), `docs/UX_AND_LAYOUT.md` (Agents B and D write
their sections; orchestrator reconciles), `docs/MVP_REQUIREMENTS.md` non-goals
sentence about team presets.

## 5. Ownership (disjoint; do not edit another agent's files)

| Agent | Owns | Must not touch |
|---|---|---|
| A (C4) | `src/scoreboard/host/app.py`, `src/scoreboard/host/bridge.py`, `src/scoreboard/host/publisher.py` (new), `src/scoreboard/infrastructure/persistence.py`, `tests/integration/test_publish_off_lock.py` (new), `tests/integration/test_window_publisher.py` (new), `tests/integration/test_persistence.py`, `tests/integration/test_display_selection.py` **only** to add the `_operator_closing` cleanup in `StartupGuardTests`, `tests/README.md` rows for its new tests | views, docs other than README rows, teams modules |
| B (C5) | `src/scoreboard/views/operator/{index.html,operator.css,operator.js,keyboard.js}`, `tests/integration/test_display_drawer_contract.py` (new), `tests/integration/test_display_selection.py` **only** `test_every_display_control_is_reachable_from_the_operator_page`, `tests/integration/test_data_folder.py` only if the split needs it, `tests/ui/keyboard.cjs` (optional), `docs/UX_AND_LAYOUT.md` display sections | Python under `src/`, other tests |
| C (F4 backend) | `src/scoreboard/infrastructure/teams.py` (new), `src/scoreboard/host/teams.py` (new), `src/scoreboard/infrastructure/paths.py` (add `teams`), `tests/integration/test_team_library.py` (new), `tests/integration/test_team_presets.py` (new), `docs/PROJECT_STRUCTURE.md`, `tests/README.md` rows for its tests | bridge.py, app.py, views |
| D (F4 UI; after B) | the operator view files, `tests/integration/test_team_presets_ui.py` (new), `docs/UX_AND_LAYOUT.md` new §5b | Python under `src/` |
| Orchestrator | wiring in `bridge.py`/`app.py` for `TeamPresets`, roadmap and architecture docs, full-suite and real-runtime verification | — |

Two agents editing `tests/README.md` is unavoidable: append rows only, at the
end of the table, and do not reflow the file.
