# Handoff — Phase 2 Task 10: display selection, fullscreen, and failure recovery

**Written:** September 5, 2026
**For:** the next implementation session
**Branch:** `phase-2-audit`, at `7e04aa1`, three commits ahead of `main`

---

## Read these first, in this order

1. `AGENTS.md` — the durable rules for this repository. They are not optional and several of them are the reason the codebase looks the way it does.
2. `PROJECT_ROADMAP.md` — the living command-center document. Read it **completely**, including the Decision Log and the Test and Evidence Log. It is the authority on status; this handoff is a summary of it, not a replacement.
3. `High School LED Scoreboard — Project Knowledge Base.md` — reference material and history. Do not casually rewrite it.
4. `docs/PHASE_2_BACKLOG.md` — Task 10's own objective, boundaries, verification, and acceptance criteria. **That task definition is the contract for this session**, not this handoff.
5. `docs/MVP_REQUIREMENTS.md` sections 7 and 9 — the D-nnn spectator-display and R-nnn reliability requirements Task 10 has to satisfy.
6. `docs/ARCHITECTURE.md` and `docs/PROJECT_STRUCTURE.md` — the layer boundaries. `docs/UX_AND_LAYOUT.md` for the operator surface.

---

## Where the project actually stands

Phase 2 backlog Tasks **1–9 and 11** are implemented and verified locally. **Task 10 is the only remaining implementation task.** Task 12 (sustained rehearsal) closes Phase 2 after it.

A working scoreboard runs today: authoritative state, both clocks, event countdowns, the command service, SQLite persistence with recovery, the operator window, the fullscreen spectator window, keyboard controls, an offline Windows package, and an operator-chosen data folder.

**316 Python tests pass.** Two `tests/ui/` browser tests error unless Node.js and Playwright are installed — that is deliberate (they fail loudly rather than skipping), so `273 passed, 2 errors` on a machine without that tooling is the expected shape, not a regression.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### What happened in the three commits before this handoff

- `54395c4` — a full audit of Tasks 1–9 against the requirements. Two cross-task defects fixed: clock expiration was never written to the durable history, and the application version was a hard compatibility gate that would have made every saved game unrecoverable at the first version bump. Added a whole-game fake-time rehearsal and a real-time clock measurement.
- `5e94eb5` — Task 11 packaging, built **out of order** (see the warning below). Found and fixed a packaging defect: only `*.html` was declared as package data, so an installed copy shipped pages without their stylesheets or scripts.
- `7e04aa1` — the operator-chosen data folder, with a native folder picker.

---

## Read this before you touch the display code

**Task 11 was built before Task 10.** The backlog lists Tasks 1–10 as Task 11's dependencies; that ordering was inverted deliberately, because Task 10 needs a two-display machine the development host does not have and Task 11 needed none.

The consequence you inherit: **the package currently in `dist/` carries Task 1-era display behaviour** — a fixed `--display-index`, no persisted display identity, no disconnect handling. When you finish Task 10 you **must rebuild the package**:

```powershell
.\.venv\Scripts\python.exe tools\build_package.py
```

and record the rebuild in the roadmap. No release may use the pre-Task-10 package. This is stated in `docs/PACKAGING.md` and `docs/PHASE_2_BACKLOG.md` as well; do not let it get lost.

---

## What Task 10 has to do

From `docs/PHASE_2_BACKLOG.md` — read the full entry, this is the shape of it:

> Turn the Task 1 proof into production-quality selection, persisted identity, close/reopen, and disconnect/reconnect behavior.

Acceptance criteria, in the backlog's words:

- A saved display is selected predictably when present.
- A missing display never hides or blocks the operator; status and explicit recovery are provided.
- Display close or disconnect does not stop clocks or corrupt state.
- A reopened view shows the current revision immediately.
- The stadium result and geometry are documented, and no unsupported auto-recovery claim is made.

Boundaries, also from the backlog: Windows display and window management only. **No** LED or RJ45 protocol work, no processor configuration, no automatic HDMI source switching, no OBS projector, and **no hidden auto-moves during live play**.

---

## What already exists that you will be building on

| File | What it currently does |
|---|---|
| `src/scoreboard/host/displays.py` | Enumerates `webview.screens` and picks one by index. Small and pure; no persistence, no identity, no reconnect logic. Tested by `tests/test_displays.py`. |
| `src/scoreboard/host/app.py` | `WindowHost.open_spectator(display_index)`, `reopen_spectator()`, `toggle_spectator_fullscreen()`, and the `_spectator_closed` handler. `ScoreboardApplication.spectator_opened/closed` push health to the operator. |
| `src/scoreboard/host/bridge.py` | `DisplayLink` / `DisplayStatus` — the tiny surface the health strip reads. `reopen_display()` is already the model for a host action that changes no game state. |
| `src/scoreboard/views/operator/index.html` | The health strip chip `#chip-display` and the `Reopen Display` button. |
| `src/scoreboard/infrastructure/paths.py` | `CONFIG_FILENAME` (`config.json`) is defined and **currently unused**. That is very likely where a persisted display preference belongs. |

The data-folder pointer added in `7e04aa1` is a working, tested precedent for "remember an operator's choice on disk, validate it at startup, fall back quietly when it has gone stale." Read `read_chosen_root` / `validate_root` in `paths.py` and `tests/integration/test_data_folder.py::StalePointerTests` before designing display persistence — the same failure modes apply when a saved monitor is unplugged, and the same rule should hold: **a stale preference must never stop the scoreboard from starting.**

---

## Constraints that will bite you if you ignore them

These are established decisions, all recorded in the roadmap's Decision Log. Do not reverse them casually.

1. **The service is the only writer of the authoritative revision.** Display work must not advance one. Follow `reopen_display()` and the new `choose_data_folder()`: host actions return the current view model, change no game state, and are tested to leave a running clock running.
2. **Nothing outside `domain/` re-implements clock arithmetic**, and **every displayed clock string is produced in Python** by `domain/formatting.py`. There is a test asserting the operator script contains no `Math.floor` and no `toFixed`.
3. **No domain object crosses the bridge.** Every returned value is `str`, `int`, `float`, `bool`, `None`, `list`, or `dict`, and survives `json.dumps(..., allow_nan=False)`. There is a test that walks every payload.
4. **A spectator failure must never reach the state engine** (R-002). Look at `_publish` in `host/app.py`: a push failure is caught, logged, and marks the display closed; the clocks keep running.
5. **No hidden auto-moves during live play.** If a display comes back, the operator decides whether to use it. This is an explicit Task 10 boundary and it matters more than convenience.
6. **U-001**: every live control must fit at 1366×768 at 100% and 125% Windows scaling with no scrolling. This was measured by hand and the measurement is recorded in the roadmap. If you add an always-visible control, that evidence is invalidated and must be re-taken. The drawer overlay is the safe place to add things — that is why the data-folder control went there.
7. **Runtime state stays out of the repository** (P-009). Check `git status --ignored` before you commit.
8. **Do not mark anything complete because files exist.** Record the verification you actually performed. This is an `AGENTS.md` rule and the roadmap follows it strictly, including saying plainly what is *not* claimed.

---

## The hardware problem you have to plan around

**This development host exposes exactly one display** (`5120x1440`). Every second-display acceptance criterion in Task 10 is therefore unverifiable here.

Plan for that from the start rather than discovering it at the end:

- Build the logic so it is testable **without a window**, the way `ScoreboardApplication` is already separated from `WindowHost`. Fake screen lists, fake display identities, and injected failures should carry most of the coverage.
- Write the manual two-display checklist as you go, in the same style as the checklist at the end of `docs/PACKAGING.md`, so the owner can execute it on a real two-monitor setup.
- State clearly in the roadmap what was proven against fakes and what still needs hardware. Do not let a passing suite imply a display was ever placed on a second monitor.

There is also a **Phase 0 gate still open**: the personal-laptop HDMI test at the stadium, planned for **September 8, 2026**. Task 10's stadium-specific acceptance depends on its result — the resolution, scaling, and reconnect behaviour of the LED processor are unknown until then. Design for a display whose geometry you do not yet know, and do not bake in an assumption that the test may contradict.

---

## One open question that outranks this task

**Audit question A-1**, in the roadmap and in `docs/MVP_REQUIREMENTS.md` sections 3 and 13:

> A game-clock Start always clears the play clock (F-048). That assumes the game clock starts at the snap. Under NFHS-style rules the game clock also starts on the **ready-for-play** — after an out-of-bounds play or a penalty — with the play clock already running toward the snap. In those situations the current rule blanks the stadium's only play-clock display and the operator must reload a preset.

This is a football-rules question for the owner and the officials, not a code decision, and it is the one open item that can visibly mislead the field. If it is still unanswered, **ask; do not implement a change to F-048 on your own judgement**, and do not let it block Task 10 — the two are independent.

Four other audit questions (A-2 through A-5) are recorded in the roadmap. None of them blocks Task 10.

---

## Definition of done for this session

- Task 10's acceptance criteria met, or the specific ones that need hardware explicitly listed as outstanding with a manual checklist written for them.
- Automated coverage for everything provable without a second display: selection, persisted identity, a missing or stale saved display, close and reopen while clocks run, and a reopened view showing the current revision.
- `PROJECT_ROADMAP.md` updated: a Task 10 evidence section, any new Decision Log rows, new Test and Evidence Log rows, the Current Status table, and the Next Action.
- `docs/PHASE_2_BACKLOG.md` status line updated.
- `docs/UX_AND_LAYOUT.md` updated if the operator surface changed.
- The package rebuilt and the rebuild recorded, since the current one predates this task.
- The full suite run and its real result reported, including the two browser errors if Node is absent.
- `compileall`, `pip check`, relative Markdown links, and `git status --ignored` all checked before committing — see the "Documentation and completion" section of `AGENTS.md`.

## What is explicitly not in this session

Task 12 rehearsal, OBS, media, networking, the physical USB controller, down and distance, timeouts, possession, statistics, and any direct LED or RJ45 protocol work. If Task 10 surfaces a request that belongs to a later phase, record it in the roadmap and keep going — that is the backlog guardrail at the end of `docs/PHASE_2_BACKLOG.md`.
