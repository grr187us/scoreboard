# Cutscenes — spec (v1: plumbing, first down, touchdown)

Status: active implementation spec (September 6, 2026). Five agents build
against disjoint file ownership (section 10). Where this spec is silent, keep
the house rules of `.scratch/layout-editor-v2/spec.md` and
`.scratch/presentation-screens/spec.md`: Python owns every value, JavaScript
copies; strict validation in Python with a plain-language fallback; nothing
fetched from a network; no optional window has a path to a game command; a
failure in any optional surface never reaches clocks, persistence, or the
operator's controls.

## 0. Goal

The owner wants "cutscenes": press a big button in a small persistent window
(like the Field Assistant) and the LED wall plays a ~10-second branded
animation — first a set of tiger claw scratches across whatever scoreboard is
showing, then the board **morphs into the built-in Broadcast bar layout**
(score and clock along the bottom), the empty upper ~70 % becomes a **stage**
where a FIRST DOWN or TOUCHDOWN animation plays, and when it ends the board
returns to exactly how it was. Two cutscenes now (first down, touchdown);
the design must make adding more, and swapping the animation for a video
file, easy.

Decisions the owner confirmed:

1. **Media format:** a *pack folder* per cutscene (`manifest.json` + optional
   media). Ships with built-in code-authored animations so it works with no
   files at all; drop a video/image pack in the folder to replace one.
2. **Bar source:** always the shipped **Broadcast bar** preset for the
   current screen (game / pre-game / halftime). Deterministic.
3. **Triggering:** a new persistent **Cutscenes** window with big buttons,
   plus operator-window hotkeys. Triggering while one plays **replaces** it.
   A Cancel button/hotkey ends early. Manual only — nothing auto-fires from
   game state.
4. **Surfaces:** the spectator (and the practice test window) plays it. The
   operator window and the Cutscenes window show a status badge with a
   Python-computed countdown, never the animation.
5. Sound: out of scope for v1 (video is muted). Nothing here should make
   adding audio later hard.

## 1. Architecture in one paragraph

Cutscenes are a **host concern**, exactly like the presentation layout and
the saved teams: no `Command`, no revision, no history row, nothing in
`scoreboard.db`. A pure module (`presentation/cutscenes.py`) defines the event
registry, validates pack manifests, and builds the **program** — one JSON
document that tells the spectator page everything it needs to play one
cutscene (duration, stage rectangle, the temporary layout, the intro, the
scene, theme colours, text). An I/O module (`infrastructure/cutscene_packs.py`)
scans the `cutscenes/` folder under the data root and persists which pack is
selected per event in `cutscenes.json`. A host object (`host/cutscenes.py`,
`CutsceneDirector`) owns playback state (what is playing, when it ends),
publishes the program to the boards through a `CutsceneLink` seam, schedules
the end on an injectable timer, and exposes a small `CutscenesBridge` for the
new window. `ScoreboardBridge` gains three host actions
(`open_cutscenes`, `trigger_cutscene`, `cancel_cutscene`) and every
operator view carries `cutscenes: {available, playing}` so the 10 Hz refresh
tick already delivers the countdown to every window. On the spectator page,
`cutscene.js` receives `window.applyCutscene(program)` /
`window.endCutscene(play_id)`, runs the timeline (intro → morph → scene →
outro → restore), and hosts either a built-in scene from
`cutscenes/builtin.js` or a `<video>`/`<img>` from the pack, falling back to
the built-in scene if the media fails to load.

## 2. Pure module — `src/scoreboard/presentation/cutscenes.py` (Agent A)

No I/O, no threads, no clocks. Everything JSON-compatible.

### 2.1 Constants (exact names; other agents hard-code the values)

```python
CUTSCENE_EVENTS: Final[tuple[str, ...]] = ("first_down", "touchdown")
EVENT_LABELS = {"first_down": "First down", "touchdown": "Touchdown"}
EVENT_HEADLINES = {"first_down": "FIRST DOWN", "touchdown": "TOUCHDOWN"}
#: Which side a cutscene is "for" when the operator does not say: a first
#: down belongs to the side with possession; a touchdown defaults to home.
EVENT_DEFAULT_TEAM = {"first_down": "possession", "touchdown": "home"}
DEFAULT_DURATION_SECONDS = {"first_down": 7.0, "touchdown": 10.0}
MIN_DURATION_SECONDS: Final[float] = 2.0
MAX_DURATION_SECONDS: Final[float] = 30.0
INTRO_IDS: Final[tuple[str, ...]] = ("claw_scratch", "none")
INTRO_DURATION_MS = {"claw_scratch": 1400, "none": 0}
#: Milliseconds the outro (fade + restore) takes; the program carries it so
#: the page and the host agree on when the board is back.
OUTRO_DURATION_MS: Final[int] = 600
BUILTIN_SCENE_IDS = {"first_down": "first_down", "touchdown": "touchdown"}
SCENE_TYPES: Final[tuple[str, ...]] = ("builtin", "video", "image")
MEDIA_EXTENSIONS = {
    "video": (".webm", ".mp4"),
    "image": (".png", ".gif", ".jpg", ".jpeg", ".webp", ".apng"),
}
FIT_MODES: Final[tuple[str, ...]] = ("cover", "contain")
#: The stage: the part of the 16:9 canvas above the Broadcast bar's status
#: row (`quarter` etc. start at y 0.705 in the preset).
STAGE = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.70}
#: From brand-baseline/palette.json.
THEME = {
    "navy": "#071B3A", "navy_elevated": "#0D2B5A", "blue": "#17468C",
    "red": "#C8242B", "blue_light": "#2C62AB", "white": "#FFFFFF",
    "mist": "#DDE7F4", "ink": "#030711", "gold": "#FFB703",
}
MANIFEST_SCHEMA_VERSION: Final[int] = 1
TEAM_SIDES: Final[tuple[str, ...]] = ("home", "away")
```

### 2.2 Pack manifest (what an operator drops in a folder)

`<data root>/cutscenes/<folder>/manifest.json`:

```json
{
  "schema_version": 1,
  "name": "Touchdown — roar",
  "event": "touchdown",
  "duration_seconds": 10,
  "intro": "claw_scratch",
  "scene": {"type": "video", "src": "touchdown.webm", "fit": "cover", "loop": false}
}
```

Rules (`validate_manifest(payload, *, files) -> ManifestValidation`, where
`files` is the set of filenames present in the pack folder, so the pure
module never touches disk):

- `schema_version` must equal 1 → else `MANIFEST_SCHEMA` error.
- `name`: non-empty string, ≤ 64 chars after strip → else `MANIFEST_NAME`.
- `event`: one of `CUTSCENE_EVENTS` → else `MANIFEST_EVENT`.
- `duration_seconds`: optional; finite number clamped into
  `[MIN, MAX]` with a `DURATION_CLAMPED` **warning**; missing → the event
  default; non-number → `MANIFEST_DURATION` error.
- `intro`: optional; one of `INTRO_IDS`; missing → `"claw_scratch"`;
  anything else → `MANIFEST_INTRO` error.
- `scene`: required object. `type` in `SCENE_TYPES` else `MANIFEST_SCENE`.
  - `builtin`: `id` must be a value of `BUILTIN_SCENE_IDS` → else
    `MANIFEST_SCENE`.
  - `video` / `image`: `src` must be a plain filename — no `/`, `\`, `..`,
    not empty, extension (case-insensitive) in `MEDIA_EXTENSIONS[type]`,
    and present in `files` → else `MANIFEST_MEDIA` error with a message
    naming the file. `fit` optional, in `FIT_MODES`, default `"cover"`.
    `loop` optional bool, default `false`.
- Unknown top-level keys are ignored (forward compatibility), no warning.

`ManifestValidation` is a frozen dataclass: `ok: bool`, `manifest: dict`
(normalized, complete: every optional field filled), `issues: tuple[CutsceneIssue, ...]`
where `CutsceneIssue(code: str, message: str, severity: "error"|"warning")`
with `.to_dict()`. `ok` is `False` iff any error.

### 2.3 Built-in packs

`builtin_pack(event) -> dict`:

```python
{"id": "builtin:touchdown", "name": "Built-in touchdown", "event": "touchdown",
 "builtin": True, "duration_seconds": 10.0, "intro": "claw_scratch",
 "scene": {"type": "builtin", "id": "touchdown"}, "folder": None, "media_url": None}
```

`BUILTIN_PACK_PREFIX = "builtin:"`. `builtin_pack_id(event)`.

A **pack dict** (built-in or scanned) always has exactly these keys:
`id, name, event, builtin, duration_seconds, intro, scene, folder, media_url`.
For a scanned pack `id` is the folder name, `folder` is the absolute folder
path as a string, and `media_url` is the media file's `file:///` URI (from
`Path.as_uri()`) or `None` for a builtin scene. The infrastructure module
fills `folder`/`media_url`; the pure module only defines the shape and a
`normalize_pack(pack_id, manifest, *, folder, media_url) -> dict` helper.

### 2.4 The program (`build_program(...)`)

```python
def build_program(
    *, play_id: int, event: str, pack: Mapping[str, Any], team: str | None,
    spectator_view: Mapping[str, Any], layout: Mapping[str, Any],
) -> dict[str, Any]
```

- `team`: `"home"`, `"away"`, or `None`. `None` resolves through
  `EVENT_DEFAULT_TEAM`: `"possession"` reads
  `spectator_view["football"]["possession"]` (values `"home"`/`"away"`/`None`
  — check the real key in `application/snapshots.py` and use the one that is
  there; if absent or `None`, use `"home"`).
- `layout` is the complete Broadcast bar layout document (v3, with
  `screens`) the host resolved; the program carries a deep copy with
  `name` set to `"Cutscene"` and nothing else changed.
- Text comes only from the view: `team_name = view["teams"][team]["name"]`,
  `score = view["teams"][team]["score"]`. Empty team name → `"TIGERS"` is
  **not** substituted; use the name as given (the operator names teams).

Program shape (exact keys; the JS agents hard-code these):

```json
{
  "schema_version": 1,
  "play_id": 3,
  "event": "touchdown",
  "label": "Touchdown",
  "team": "home",
  "pack_id": "builtin:touchdown",
  "duration_ms": 10000,
  "intro": {"id": "claw_scratch", "duration_ms": 1400},
  "outro_ms": 600,
  "stage": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.70},
  "layout": { ...full v3 layout document, name "Cutscene"... },
  "scene": {"type": "builtin", "id": "touchdown"},
  "theme": { ...THEME... },
  "texts": {"headline": "TOUCHDOWN", "subline": "TIGERS", "team_name": "Tigers", "score": "14"}
}
```

For a media pack: `"scene": {"type": "video", "src": "file:///C:/.../touchdown.webm",
"fit": "cover", "loop": false, "fallback": {"type": "builtin", "id": "touchdown"}}`
(`image` likewise, `loop` omitted). `subline` is `team_name.upper()`;
`score` is `str(score)`.

`duration_ms = round(duration_seconds * 1000)`. Intro and outro happen
**inside** `duration_ms`, never added to it.

### 2.5 Descriptors for the window

`event_descriptors() -> list[dict]`: one per event, in `CUTSCENE_EVENTS`
order: `{"id", "label", "headline", "default_team", "default_duration_seconds", "builtin_pack_id"}`.

### 2.6 Tests — `tests/unit/test_cutscene_schema.py`

Every rule in 2.2 (valid manifest normalizes with defaults; each error code;
clamping warns; `..` and separators refused; extension mismatch; missing
file; unknown keys ignored), `builtin_pack` shape, `build_program` (team
resolution incl. possession and `None`, texts from the view, layout deep
copied and renamed, media scene carries fallback, intro/outro inside the
duration), `event_descriptors`, and a mirror test that
`views/spectator/cutscenes/builtin.js` contains
`register('claw_scratch'`, and `register('<id>'` for every value of
`BUILTIN_SCENE_IDS` (Agent C writes those literal calls; see 6.3).

## 3. I/O module — `src/scoreboard/infrastructure/cutscene_packs.py` (Agent A)

Mirrors `infrastructure/layouts.py`'s style and its "never touch
`config.json` / `layouts.json` / `teams.json` / `scoreboard.db`" boundary.

- `paths.py` additions (Agent A owns these lines): constants
  `CUTSCENES_DIRECTORY_NAME = "cutscenes"` and
  `CUTSCENE_SELECTION_FILENAME = "cutscenes.json"`; properties
  `ScoreboardPaths.cutscenes` (dir) and `ScoreboardPaths.cutscene_selection`
  (file); `describe()` gains `"cutscenes": str(self.cutscenes)`; `ensure()`
  also creates the `cutscenes` directory; add both names to `__all__`.
- `PACK_README_FILENAME = "README.txt"`; `ensure_packs_directory(paths)`
  creates the folder and, only if absent, writes a README explaining the
  manifest format (copy the JSON from 2.2 and the rules in plain words, and
  say "one folder per cutscene; the folder name is the pack id; restart is
  not needed — press Rescan").
- `scan_packs(paths) -> ScanResult(packs: tuple[dict, ...], issues: tuple[dict, ...])`:
  each immediate subfolder that contains `manifest.json` is read
  (`utf-8`, `json.loads`); unreadable/invalid JSON → one issue
  `{"pack_id": folder, "code": "MANIFEST_JSON", "message": ...}` and the
  folder is skipped; otherwise `validate_manifest(payload, files=<names in folder>)`;
  errors → skipped with issues; warnings → included with issues. Packs are
  sorted by `(event, name.lower(), id)`. Folder names are used verbatim as
  ids except that a folder whose name starts with `builtin:` or contains a
  path separator is skipped with `PACK_ID` (cannot collide with built-ins).
  A missing `cutscenes` directory is not an error: empty result.
- `read_selection(paths) -> dict[str, str]` (event → pack id; missing file,
  bad JSON, wrong `schema_version`, or a non-string value yield `{}` for
  that key/whole file with no exception) and
  `write_selection(paths, selection) -> bool` (temp file + `os.replace`,
  `{"schema_version": 1, "selected": {...}}`, `False` on `OSError`).
  `SELECTION_SCHEMA_VERSION = 1`.
- `library(paths) -> CutsceneLibrary`: frozen dataclass with `packs`
  (built-ins first, one per event, then scanned), `issues`, `selection`,
  and `resolve(event) -> tuple[dict, bool]` returning the selected pack for
  the event, or the built-in with `fell_back=True` when the selection
  names a pack that is not present or is for another event.
- Tests — `tests/integration/test_cutscene_packs.py` (in a
  `TemporaryDataDirectoryTest`): scan of good/bad/mixed folders, README
  written once, selection round-trip and atomic replace (temp file gone),
  bad selection file → `{}`, `resolve` fallback, and the boundary test that
  scanning/writing never creates or touches `config.json`, `layouts.json`,
  `teams.json`, `scoreboard.db`.

## 4. Host — `src/scoreboard/host/cutscenes.py` (Agent A)

```python
class CutsceneLink:
    """Mirrors LayoutLink. Overridden by WindowHost at wiring time."""
    def open_window(self) -> dict[str, str]: return {"message": "The Cutscenes window is unavailable."}
    def publish(self, program: dict[str, Any]) -> None: return None
    def end(self, play_id: int) -> None: return None

class CutsceneDirector:
    def __init__(self, paths, *, diagnostics=None, monotonic=None, schedule=None,
                 read_spectator_view=None, read_layout=None, folder_opener=None) -> None
```

- `link: CutsceneLink` attribute (public, replaced by the host).
- `schedule(delay_seconds: float, callback: Callable[[], None]) -> object`
  returns something with `.cancel()`. Default wraps `threading.Timer`
  (daemon, started). Tests inject a recording scheduler.
- `monotonic` default `time.monotonic`.
- `read_spectator_view: Callable[[], dict]` — the host passes
  `bridge.spectator_snapshot`; `None` → `{}` (the program then uses
  `"home"` and empty text, never raises).
- `read_layout: Callable[[], dict] | None` — **the Broadcast bar preset**,
  resolved by the director itself when `None`:
  `next(p["layout"] for p in layout_module.preset_descriptors() if p["id"] == "broadcast")`.
  Keep the parameter so a test can hand in a tiny document.
- On construction: `ensure_packs_directory`, then `_reload()` (library).
- `state() -> dict`: `{"events": event_descriptors() each extended with
  "selected_pack_id" and "selected_pack_name" and "fell_back": bool,
  "packs": [...], "issues": [...], "folder": str, "playing": status|None}`.
- `trigger(event, team=None) -> dict`: validates `event` in
  `CUTSCENE_EVENTS` and `team` in `TEAM_SIDES`/`None` → else
  `{"ok": False, "message": "..."}` (no exception). Under the lock: cancel
  any pending timer, `play_id += 1`, resolve the pack, build the program,
  record `_current = {program, started_at}`; **outside the lock**:
  `link.publish(program)` inside try/except → on failure
  `diagnostics.unhandled_error(context="cutscene_publish", error=exc)` and
  the cutscene is still considered playing (the timer still ends it; the
  wall may simply not have shown it). Then `schedule(duration_seconds, lambda: self._expire(play_id))`.
  Diagnostics: `note("CUTSCENE_REPLACED", play_id=<old>)` when one was
  playing; `note("CUTSCENE_STARTED", play_id=..., event=..., pack=..., team=..., duration_ms=...)`.
  Returns `{"ok": True, "message": "Playing Touchdown (10 s).", "play_id": n, "status": status}`.
- `cancel() -> dict`: nothing playing → `{"ok": False, "message": "No cutscene is playing."}`;
  else clear, cancel timer, `link.end(play_id)` (try/except →
  `context="cutscene_end"`), `note("CUTSCENE_CANCELLED", play_id=...)`.
- `_expire(play_id)`: if `play_id` is still current → clear, `link.end(play_id)`,
  `note("CUTSCENE_ENDED", play_id=...)`; otherwise ignore (stale timer).
- `status() -> dict | None`: `None` when idle, else
  `{"play_id", "event", "label", "team", "pack_id", "pack_name", "duration_ms",
  "elapsed_ms", "remaining_ms", "remaining_display"}` where
  `remaining_display` is `f"{remaining_seconds:.1f}s"` clamped at `0.0s`.
  Python computes it; JavaScript copies it.
- `current_program() -> dict | None`: the program while playing (a reopened
  spectator asks for it on load).
- `rescan() -> dict`: reload library; returns `state()` plus `message`.
- `select_pack(event, pack_id) -> dict`: validates, writes selection,
  reloads; `{"ok", "message", **state()}`. A failed write keeps the
  previous in-memory selection and says so.
- `open_folder() -> dict`: `folder_opener(paths.cutscenes)` (default is
  `scoreboard.host.bridge._open_in_explorer`; import lazily inside the
  method to avoid a circular import) inside try/except → plain message.
- `shutdown()`: cancel any timer (no publish).
- A `fell_back` resolution notes `CUTSCENE_SELECTION_FELL_BACK` once per
  reload, and each skipped pack notes `CUTSCENE_PACK_REJECTED`
  (pack_id, code, message) once per reload.

```python
class CutscenesBridge:
    """The Cutscenes window's deliberately small JSON API. No `command`."""
    def __init__(self, director: CutsceneDirector, operator: "ScoreboardBridge") -> None
    def get_snapshot(self) -> dict  # operator.get_snapshot() — team names + cutscenes status
    def state(self) -> dict
    def trigger(self, event: Any, team: Any = None) -> dict
    def cancel(self) -> dict
    def rescan(self) -> dict
    def select_pack(self, event: Any, pack_id: Any) -> dict
    def open_folder(self) -> dict
```

Tests — `tests/integration/test_cutscene_director.py`: fake scheduler and
`FakeMonotonic`; a recording `CutsceneLink`; trigger publishes one program
with the right shape and schedules the right delay; status counts down and
`remaining_display` clamps; expire ends exactly once and a stale timer is
ignored; replace-on-collision cancels the old timer, notes `CUTSCENE_REPLACED`,
and never calls `end` for the old one; cancel ends and clears; publish/end
raising is contained and logged; invalid event/team rejected without a
change; `select_pack` persists and `rescan` sees a new folder; the bridge
exposes no `command` attribute and no method named like a `CommandType`
value. Diagnostics assertions can use a recording `Diagnostics` the way
`test_team_presets.py` does (read that file first).

## 5. Wiring — `host/app.py`, `host/bridge.py` (Agent B, after Agent A)

### 5.1 `ScoreboardBridge`

- New kwarg `cutscenes: CutsceneDirector | None = None`, stored as
  `self._cutscenes`; `set_cutscenes_opener(opener)` mirrors
  `set_field_assistant_opener`.
- `_view()` becomes `self._with_cutscenes(self._with_identity(...))` where
  `_with_cutscenes` sets `view["cutscenes"] = {"available": director is not None,
  "playing": None if director is None else director.status()}`.
- Host actions (all under `self._lock`, all try/except → plain message, no
  revision, no history):
  - `open_cutscenes() -> dict` (mirrors `open_field_assistant`; message
    "The Cutscenes window is unavailable." when no opener).
  - `trigger_cutscene(event, team=None) -> dict`: forwards to the director;
    `{"ok": False, "message": "Cutscenes are unavailable."}` when `None`.
    The returned dict also carries `"view": self._view()` so the operator
    page re-renders the badge at once.
  - `cancel_cutscene() -> dict`: likewise.
- `SpectatorBridge.__init__` gains `read_cutscene: Callable[[], dict | None] | None = None`
  and `get_cutscene() -> dict | None` (read-only; `None` when absent).
- `__all__` gains `CutscenesBridge` re-export only if it is imported here;
  otherwise leave it in `host.cutscenes`.

### 5.2 `ScoreboardApplication`

- `self.cutscenes = CutsceneDirector(self.paths, diagnostics=self.diagnostics,
  monotonic=self._monotonic, read_spectator_view=self._read_spectator_view)`
  created beside `self.layouts`/`self.teams` (host concern, survives the
  recovered/new choice). `_read_spectator_view` returns
  `{}` when `self.bridge is None` else `self.bridge.spectator_snapshot()`.
- `_begin` passes `cutscenes=self.cutscenes` to `ScoreboardBridge`.
- `set_cutscenes_active(predicate)` and, in `_deliver`, after the field
  assistant block, an identical block pushing `("cutscenes", batch.operator_view)`
  with `context="cutscenes_push"`.
- `shutdown()` calls `self.cutscenes.shutdown()`.

### 5.3 `WindowHost`

- `self.cutscenes_window: webview.Window | None = None`.
- Wiring in `__init__`: `application.cutscenes.link.open_window = self.open_cutscenes`,
  `.publish = self.publish_cutscene`, `.end = self.end_cutscene`;
  `application.set_cutscenes_active(lambda: self.cutscenes_window is not None)`.
- `_choose_startup`: `bridge.set_cutscenes_opener(self.open_cutscenes)`.
- `open_cutscenes() -> dict[str, str]`: mirrors `open_field_assistant`
  exactly (replace a previous window, `FieldAssistant`-style containment):
  title `"Cutscenes"`, `url=view_url("cutscenes")`,
  `js_api=CutscenesBridge(self.application.cutscenes, bridge)`,
  `width=520, height=640, min_size=(420, 520)`, `on_top=True` if pywebview
  6.2.1's `create_window` accepts it (it does: `on_top` keyword) — the
  window is meant to sit beside the operator window all game.
  `events.closed += self._cutscenes_closed`.
- `publish_cutscene(program)` / `end_cutscene(play_id)`: mirror
  `publish_layout` — read `spectator_window` and `test_window` under
  `_lock`, then for each loaded window `evaluate_js` of
  `window.applyCutscene && window.applyCutscene(<json>)` /
  `window.endCutscene && window.endCutscene(<int>)` inside try/except with
  contexts `spectator_cutscene_push` / `test_spectator_cutscene_push`
  (and `..._end`). Never under `_command_lock`; never destroys a window on
  failure (a cutscene is decoration).
- Both `SpectatorBridge(...)` constructions pass
  `read_cutscene=self.application.cutscenes.current_program`.
- `_deliver`: a `"cutscenes"` branch mirroring `"field_assistant"`
  (contain failure, forget + destroy the window).

### 5.4 Tests (Agent B)

- `tests/integration/test_cutscenes_window.py` — copy the fakes from
  `test_field_assistant_window.py`: open creates a window with the right
  url/title/js_api type; reopen replaces and destroys the previous; close
  forgets; `_deliver("cutscenes", view)` pushes `applyView`; a failing push
  destroys only the helper; `publish_cutscene` reaches spectator and test
  window but not the layout editor; `end_cutscene` likewise; an
  `evaluate_js` that raises is logged and the spectator is **not**
  destroyed; the director's link is wired to the host methods; `get_cutscene`
  on the spectator bridge returns the current program while playing.
- `tests/integration/test_cutscene_bridge.py` — through a real
  `ScoreboardBridge` with a director (fake scheduler): every operator view
  carries `cutscenes.available`/`playing`; `trigger_cutscene` advances no
  revision, writes no history row, and leaves a running clock running
  (mirror `test_team_bridge.py`'s assertions); `cancel_cutscene`; a bridge
  built without a director answers plainly; `open_cutscenes` without an
  opener answers plainly.
- Update `tests/README.md` rows for every new test file (Agents A, B, C, D
  each add their own rows; keep the table's style).

## 6. Spectator player — `views/spectator/*` (Agent C, Opus)

### 6.1 Page changes

`index.html`: add, after `#event-board`,
`<section id="cutscene-stage" hidden aria-hidden="true"></section>`, and
load `cutscenes/builtin.js` then `cutscene.js` after `spectator.js`; add
`<link rel="stylesheet" href="cutscene.css">`.

`spectator.js`: keep `currentLayout` as the operator's layout and add an
`overrideLayout` (null when idle). Factor board application into
`applyBoards()` which uses `overrideLayout || currentLayout`. `window.applyLayout`
(host push) updates `currentLayout` and re-applies **only when no override
is active** (a layout edit during a cutscene lands when the cutscene ends).
Expose:

```js
window.ScoreboardSpectator = {
  setOverrideLayout: function (layoutDoc /* or null to restore */) {...},
  currentLayout: function () { return currentLayout; },
  canvas: canvas
};
```

In `whenReady`, after the layout fetch: if `typeof api.get_cutscene === 'function'`,
resolve it and, when non-null, call `window.applyCutscene(program)` with
`{resumed: true}` semantics (the page joined mid-cutscene: skip the intro,
apply the override and the scene immediately, and run its own safety-net
timer from `duration_ms - elapsed` — the host still sends `endCutscene`).
Since the program has no `elapsed_ms`, Agent A adds `"elapsed_ms"` to the
program returned by `current_program()` only (0 in the freshly built
program).

### 6.2 `cutscene.js` — the player

Globals it defines: `window.applyCutscene(program)`, `window.endCutscene(playId)`,
and `window.ScoreboardCutscenePlayer` with `{ state(), scenes }` for tests.
It must survive a malformed program (validate `play_id`, `duration_ms`,
`stage`, `layout.widgets`, `scene.type`; on failure `console.error` and
ignore — the board is untouched).

Timeline for one program (all times relative to `applyCutscene`):

| t | What happens |
|---|---|
| 0 | `#cutscene-stage` is shown **full-canvas** (inset 0) with class `intro`; the intro scene (`program.intro.id`, e.g. `claw_scratch`) mounts on it over the current board. `program.intro.id === 'none'` skips to the next row at t=0. |
| ≈ 40 % of `intro.duration_ms` | `ScoreboardSpectator.setOverrideLayout(program.layout)` with class `morphing` on `#canvas` for `OUTRO`-like 600 ms so widgets glide to the bar (see 6.4). |
| `intro.duration_ms` | Intro unmounts; the stage resizes to `program.stage` (left/top/width/height as percentages of the canvas); the main scene mounts (built-in or media). |
| `duration_ms - outro_ms` | Class `outro` on the stage (CSS fade). |
| `duration_ms` | Scene unmounts, stage hidden, `setOverrideLayout(null)` with `morphing` again, state idle. |
| `duration_ms + 1500` | **Safety net** only if the host never sent `endCutscene` — the page ends itself with the same steps (never wait on the host to give the board back). |

`window.endCutscene(playId)`: ignored unless `playId === current.play_id`;
otherwise jump to the outro row now (outro shortened to 300 ms), then the
end row. A second `applyCutscene` while one is active **replaces**: clear
every timer, unmount the current scene, and start the new timeline but
**skip the intro's morph** (the override is already the bar; still play the
claw-scratch intro on the stage area only if the new program has one —
keep it simple: on replace, run the intro inside the stage rect, not
full-canvas).

Media scenes: `video` → `<video autoplay muted playsinline preload="auto">`
with `loop` from the program and `object-fit` from `fit`; `image` → `<img>`;
both `src` set from `program.scene.src` verbatim. On the element's `error`
event (or `video` not reaching `loadeddata` within 2000 ms) →
`console.error`, unmount, mount `program.scene.fallback` (a built-in) for
the remaining time. Never `fetch()` — a `file:///` subresource on an
`<img>`/`<video>` is what WebView2 allows; `fetch` of `file://` is not.

`applyView` keeps working during a cutscene (the bar's clock keeps ticking)
— the player never touches `applyView`.

### 6.3 `cutscenes/builtin.js` — the scene registry and three scenes

```js
window.ScoreboardCutsceneScenes = {
  register: function (id, factory) {...},   // factory(stageEl, program) -> {mount(), unmount()}
  create: function (id, stageEl, program) {...},  // null when unknown
  ids: function () {...}
};
```

Register with **literal string calls** (`register('claw_scratch', ...)`,
`register('first_down', ...)`, `register('touchdown', ...)`) — the Python
mirror test greps for them. All three are code-authored (DOM + CSS
animations + inline SVG), use only `program.theme` colours and
`program.texts`, load nothing external, and must look good at 1920×1080 and
in the 640-wide practice window (size everything in `%`/`vw`-of-canvas
units via CSS custom properties `--stage-w`/`--stage-h` the player sets in
px on the stage element).

Creative direction (Tigers: navy `#071B3A`, red `#C8242B`, blue `#17468C`,
gold `#FFB703`, white):

- **`claw_scratch`** (intro, 1400 ms): three to four diagonal claw slashes
  rip across the board in quick succession (SVG paths with
  `stroke-dasharray` draw-on, a red glow behind a bright white core, a
  short shake on the canvas via a `shake` class on `#canvas`), then the
  slashes fade as the morph completes. Works over any board.
- **`first_down`** (7 s): a wide navy stage with a yard-line/field-stripe
  background sliding sideways, a huge condensed **FIRST DOWN** slamming in
  with a gold outline, a red chevron/arrow sweeping left→right, the team
  name as a subline. Ends with a calm hold.
- **`touchdown`** (10 s): bigger and bolder — a burst of gold/red
  particles or rays from center, a **TOUCHDOWN** headline that scales in
  with a bounce, the team name and current score below it, a slow
  navy-to-blue gradient drift. Tasteful, not seizure-inducing: no
  full-field strobe, no fast navy/orange alternation (brand README rule).

The user will iterate on the look later; the plumbing and the register/mount/
unmount contract are what must be right.

### 6.4 `cutscene.css` and the morph

- `#cutscene-stage { position: absolute; overflow: hidden; z-index: 50; }`
  with `left/top/width/height` set from the program by the player (inline
  styles). `.intro` → inset 0. `.outro` → `opacity: 0` with a 600 ms
  transition.
- The morph: with `#canvas.morphing`, widgets and free elements transition
  `left, top, width, height, font-size` over 600 ms. `board.css` is not
  owned by Agent C; put the rule in `cutscene.css` as
  `#canvas.morphing .widget, #canvas.morphing .element { transition: left .6s, top .6s, width .6s, height .6s, font-size .6s, opacity .6s; }`
  — check `board.css` for the actual class/selector names board.js
  produces and use those. Remove the class 700 ms after adding it.

### 6.5 Tests (Agent C)

- `tests/ui/cutscene_player.cjs` + `tests/ui/test_cutscene_player_browser.py`
  (follow `spectator.cjs` / `test_spectator_browser.py`): load the spectator
  page from `file://`, call `applyCutscene` with a program that has
  `duration_ms: 1500`, `intro.duration_ms: 200`, `outro_ms: 100`, a builtin
  scene; assert the stage is visible, the override layout is applied (a
  node with `data-item="broadcast_bar"` exists on the game board), the
  scene mounted (`#cutscene-stage` has children); after 1.7 s the stage is
  hidden and the board carries the previous layout's name again
  (`#canvas` `data-layout`); `endCutscene` early restores within 500 ms;
  a `video` scene whose `src` is a missing file falls back to the builtin
  (a child marked `data-scene="touchdown"`); a second `applyCutscene`
  replaces (the state's `play_id` is the new one). Run it with the same
  Playwright setup and skip rules as the existing browser tests.
- `tests/integration/test_cutscene_player_contract.py`: source contract —
  the spectator page references `cutscene.js`, `cutscenes/builtin.js`, and
  `#cutscene-stage`; `cutscene.js` defines `window.applyCutscene` and
  `window.endCutscene`, contains no `fetch(`, no `api.command`, no
  `pywebview.api` write; `builtin.js` registers `claw_scratch`,
  `first_down`, `touchdown`.

## 7. Cutscenes window and operator hooks — Agent D

### 7.1 `views/cutscenes/index.html`, `cutscenes.js`, `cutscenes.css`

A small dark window (base.css tokens), built for a volunteer:

- Header: `CUTSCENES`, a status line `#status` — idle: `Ready`; playing:
  `PLAYING: TOUCHDOWN · 6.2s` (copied from `view.cutscenes.playing.label`
  and `.remaining_display`); and an **always-visible** `CANCEL` button
  (`#cancel`, disabled when idle).
- Team row: two toggle buttons `#team-home` / `#team-away` showing the
  current team names from `view.teams.home.name` / `.away.name`
  (`data-team="home"|"away"`), default home. A first down uses
  `team: null` unless the operator has explicitly pressed a team button
  since the last trigger (so the possession default from Python applies);
  a touchdown always sends the selected team.
- Big buttons (≥ 88 px tall, full width): `#trigger-first-down`
  (`data-event="first_down"`, label `FIRST DOWN`) and `#trigger-touchdown`
  (`data-event="touchdown"`, label `TOUCHDOWN`). Pressing calls
  `api.trigger(event, team)` and shows the returned message in `#notice`.
- A collapsible `Packs` section: for each event a `<select data-pack-for="<event>">`
  listing `state.packs` filtered by event (built-in first), selected =
  `selected_pack_id`; change → `api.select_pack(event, id)`. Buttons
  `#rescan` (`api.rescan()`), `#open-folder` (`api.open_folder()`), and an
  `#issues` list rendering `state.issues` messages (empty → hidden).
- Keys (this window only, same table as the operator): `D` first down,
  `T` touchdown (home), `Shift+T` touchdown (away), `Shift+C` cancel.
  Ignore when focus is in a `select`/`input`.
- Bridge attach: `window.addEventListener('pywebviewready', ...)` on
  **window** (never `document`), and also attach immediately if
  `window.pywebview && window.pywebview.api` already exists; on attach call
  `api.state()` then `api.get_snapshot()`. Define
  `window.applyView = function (model) {...}` — the host pushes the full
  operator view ten times a second; render only `model.teams` names and
  `model.cutscenes` from it. Never compute the countdown locally.
- No `api.command`, no `data-command`, no `CommandType` names anywhere in
  the three files.

### 7.2 Operator window

- `index.html` footer: `<button type="button" id="open-cutscenes" data-action="open_cutscenes">Cutscenes</button>`
  right after the Field Assistant button. A badge
  `<span id="cutscene-badge" class="cutscene-badge" hidden></span>` inside
  the top bar / beside the `LAST:` strip — pick the spot that does not
  change the fixed grid rows (read the U-001 comments in `operator.css`).
  Text: `CUTSCENE: TOUCHDOWN 6.2s`, from `view.cutscenes.playing`.
- `operator.js`: handle `open_cutscenes` like `open_field_assistant`;
  render the badge in the same place the LAST strip is rendered from the
  view; add a `host` callback to the keyboard install options that
  calls `api[name](args...)` and shows the result message.
- `keyboard.js`: new binding kind `host`. Append:

```js
{key: 'd', label: 'D', action: 'Cutscene: First down', host: 'trigger_cutscene', args: ['first_down', null]},
{key: 't', label: 'T', action: 'Cutscene: Touchdown (home)', host: 'trigger_cutscene', args: ['touchdown', 'home']},
{key: 't', shift: true, label: 'Shift+T', action: 'Cutscene: Touchdown (away)', host: 'trigger_cutscene', args: ['touchdown', 'away']},
{key: 'c', shift: true, label: 'Shift+C', action: 'Cancel cutscene', host: 'cancel_cutscene'}
```

  A `host` binding goes through the same editable/repeat/held guards and
  `options.blocked()`, then `options.host(binding.host, binding.args || [])`
  instead of `submit`. They still appear in the shortcut help table.
  **Run `tests/integration/test_keyboard_source.py` and `tests/ui/test_keyboard_browser.py`**
  and adjust only if they pin the binding count.
- `operator.css`: the badge style (gold text on navy, small, never wraps).

### 7.3 Tests (Agent D) — `tests/integration/test_cutscenes_ui_contract.py`

Source contracts in the style of `test_crowd_status_ui.py`: the footer
button and its action; the badge id; the four keyboard bindings with those
exact keys and host names; the cutscenes page has the two trigger buttons
with `data-event`, the cancel button, the team toggles, one
`data-pack-for` per event, attaches on `window` `pywebviewready`, defines
`window.applyView`, and contains none of `api.command`, `data-command`, or
any `CommandType` value (import `CommandType` and iterate its values).

## 8. Docs — Agent E (after A–D)

- `docs/UX_AND_LAYOUT.md`: new `## 12. Cutscenes window (added September 6, 2026)`
  with 12.1 what it is/is not, 12.2 opening it, 12.3 layout and keys,
  12.4 what the wall shows (the timeline table from 6.2), 12.5 packs and
  the manifest (2.2), 12.6 not yet visually verified on the LED wall.
- `docs/ARCHITECTURE.md`: §9 files gains `cutscenes/` and `cutscenes.json`;
  §12 "Media and animation" is rewritten around the program/pack model;
  §8 notes the two new host→spectator globals.
- `docs/PROJECT_STRUCTURE.md`: the new modules and view folder.
- `PROJECT_ROADMAP.md`: `### 5. Cutscenes — delivered for rehearsal, September 6, 2026`
  under "Owner-requested next scoreboard work" (what was built, what is
  provisional, verification performed as reported by the orchestrator),
  plus the `## Next Action` line.
- `AGENTS.md` suite line: update the test count from the orchestrator's
  final run.
- Run `tools/check_markdown_links.py` (0 broken links).

## 9. Verification plan (orchestrator)

1. Full suite: `SCOREBOARD_DATA_DIR=<scratch> ./.venv/Scripts/python.exe -m unittest discover -s tests -v`
   → green apart from the three A-1 skips.
2. Stub-bridge preview of the spectator page (launch.json `views-static`):
   call `applyCutscene` with a real program from Python; screenshot the
   intro, the morphed bar, each built-in scene, and the restore.
3. Real pywebview runtime harness (scratchpad `realrun_cutscenes.py`):
   new game → `open_test_window()` → `open_cutscenes()` → `evaluate_js`
   click `#trigger-touchdown` → read the practice window's stage state and
   the operator view's `cutscenes.playing` → wait → confirm restore. Then
   an image pack (a generated PNG) to prove a `file:///` subresource loads
   in WebView2; a video pack if a `.webm` can be produced locally.
4. Review the complete diff.

## 10. Non-goals (v1)

Sound; auto-fire from game state; per-team packs; a pack *editor* in the
app; cutscenes on the layout editor's preview; scheduling or queuing;
transitions other than the fixed morph; any change to the game schema,
commands, persistence of the game, or the layout schema.

## 11. File ownership (disjoint; do not edit files you do not own)

| Agent | Owns |
|---|---|
| A (Sonnet) | `src/scoreboard/presentation/cutscenes.py` (new), `src/scoreboard/infrastructure/cutscene_packs.py` (new), `src/scoreboard/infrastructure/paths.py` (additions only), `src/scoreboard/host/cutscenes.py` (new), `tests/unit/test_cutscene_schema.py`, `tests/integration/test_cutscene_packs.py`, `tests/integration/test_cutscene_director.py`, its rows in `tests/README.md` |
| B (Sonnet, after A) | `src/scoreboard/host/app.py`, `src/scoreboard/host/bridge.py`, `tests/integration/test_cutscenes_window.py`, `tests/integration/test_cutscene_bridge.py`, its rows in `tests/README.md` |
| C (Opus) | `src/scoreboard/views/spectator/index.html`, `spectator.js`, `spectator.css`, `cutscene.js` (new), `cutscene.css` (new), `cutscenes/builtin.js` (new), `tests/ui/cutscene_player.cjs`, `tests/ui/test_cutscene_player_browser.py`, `tests/integration/test_cutscene_player_contract.py`, its rows in `tests/README.md` |
| D (Sonnet) | `src/scoreboard/views/cutscenes/*` (new), `src/scoreboard/views/operator/index.html`, `operator.js`, `operator.css`, `keyboard.js`, `tests/integration/test_cutscenes_ui_contract.py`, its rows in `tests/README.md`; may adjust `tests/integration/test_keyboard_source.py` / `tests/ui/keyboard.cjs` only if they pin the binding count |
| E (Sonnet, after A–D) | `docs/UX_AND_LAYOUT.md`, `docs/ARCHITECTURE.md`, `docs/PROJECT_STRUCTURE.md`, `PROJECT_ROADMAP.md`, `AGENTS.md` |

Shared test command (from the repo root, PowerShell):

```powershell
$env:SCOREBOARD_DATA_DIR = "$env:TEMP\scoreboard-tests"; .\.venv\Scripts\python.exe -m unittest tests.unit.test_cutscene_schema -v
```

`tests/README.md` is the one shared file: each agent appends only its own
rows to the table, and nothing else.
