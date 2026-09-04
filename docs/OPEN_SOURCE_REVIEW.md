# Open-Source Scoreboard Review

**Research snapshot:** September 4, 2026
**Purpose:** Determine whether to adopt a code base or borrow proven ideas for the Phase 2 MVP.

## 1. Method and evidence limits

Each candidate was inspected from a shallow clone of its public GitHub repository at the commit listed below. Evidence came from the root license, README, source tree, timing/control code, packaging files, and test files. A shallow clone establishes the current snapshot and latest commit date but is not a full maintenance-history audit. Releases were not installed or run, and OBS-dependent projects were not compiled during Phase 1.

`Repository fact` below means visible in that snapshot. `Interpretation` is this project's engineering judgment.

No candidate code has been copied. Where a repository has no license—or conflicting license files—copyright law does not permit us to assume reuse rights.

## 2. Summary

| Candidate | Snapshot/latest commit | License evidence | Recommendation |
|---|---|---|---|
| [AmericanFootballScoreboard](https://github.com/chris109b/AmericanFootballScoreboard) | `e4a533d`, 2017-09-13 | Root `LICENSE`: GPL-3.0 | **Borrow specific ideas** |
| [Football-Scoreboard](https://github.com/KevinZheng2025/Football-Scoreboard) | `112d08b`, 2021-12-18 | No license file or declaration found | **Use only as a reference** |
| [fly-scoreboard](https://github.com/mmlTools/fly-scoreboard) | `93dc083`, 2026-08-25 | Conflict: README says MIT; root `LICENSE` is GPL-2.0 text | **Use only as a reference** until clarified |
| [alpower/scoreboard](https://github.com/alpower/scoreboard) | `89d1c93`, 2025-01-19 | No license file or declaration found | **Use only as a reference** |
| [streamn-scoreboard](https://github.com/StreamnDad/streamn-scoreboard) | `4e6791d`, 2026-04-17 | Root `LICENSE` and README: GPL-2.0 | **Borrow specific ideas** |
| [scorebug](https://github.com/david-mcgaughy/scorebug) | `923d81b`, 2025-12-06 | Root `LICENSE`: GPL-3.0 | **Use only as a reference** |

None is recommended for adoption. The best reusable concept is the separation between a testable state core and presentation/integration consumers. The MVP still needs project-specific football scoring controls, an independent 25/40 play clock, safe correction, restart-stopped recovery, and direct fullscreen stadium output without OBS.

### Capability checklist

This table condenses repository facts first; maintainability/adoption language is the reviewer's interpretation.

| Candidate | Language/framework | Windows and offline | Football/clock | Controls and rendering | Packaging/tests | Maintainability/adoption risk |
|---|---|---|---|---|---|---|
| AmericanFootballScoreboard | Python, Tornado, HTML/CSS/JS | Windows setup documented; can run locally after dependencies, though remote/network discovery is prominent | American-football fields; one wall-time delta game clock; no 25/40 clock found | Remote browser control, browser display, OBS/log plugins | Python/package setup; no automated suite found | Clear early separation, but 2017-era dependencies/code and no recovery proof |
| Football-Scoreboard | Python/Tkinter | Runs locally after Python/assets; Windows instructions | American-football UI; callback-count game clock; no play clock found | Native control plus fixed 1280×43 display, captured/color-keyed in OBS | No packaged executable/tests found | Single coupled file, fixed layout, drift risk, no license |
| fly-scoreboard | C++/Qt OBS plugin, HTML/CSS/JS templates | Windows release; local/offline after OBS/plugin install | Generic fields/timers; current “football” template is association football; no American-football model/play clock | OBS dock/hotkeys, WebSocket, local-file browser sources | Release/build scripts; no automated tests found | Active and modular, but OBS/C++ complexity and conflicting license evidence |
| alpower/scoreboard | Single-file HTML/CSS/JS | Local-file/offline OBS use with bundled assets | Association football/futsal; callback-count timer; no American-football controls | Controls and overlay share one browser source; `localStorage` | No build/package/tests | Very small but tightly coupled, drift-prone, and unlicensed |
| streamn-scoreboard | C/C++/Qt OBS plugin | Windows x64 release; local/offline after OBS/plugin install | Multi-sport generic football preset; elapsed-tenths game clock; no football scoring increments/play clock found | OBS dock/hotkeys and text-file outputs | Release builds; seven core test files and claimed 100% core coverage | Strong core boundary, but OBS/GPL/C++ adoption adds major MVP cost |
| scorebug | HTML/CSS/JS, OBS WebSocket, PowerShell | Windows-oriented; remote CDN/OCR/ticker paths prevent a fully self-contained offline claim | Basketball, callback-count game clock | Browser dashboard/overlay through OBS; optional OCR polling | Manual file setup; no tests/package found | Useful failover UX, but coupled external services, hard-coded example credential, and wrong sport |

## 3. Candidate findings

### 3.1 chris109b/AmericanFootballScoreboard

**Repository facts**

- Python package with HTML/CSS/JavaScript pages and a Tornado server; dependencies include Tornado, Zeroconf, netifaces, and CairoSVG.
- README describes remote web control, browser displays from 640×360 through 3840×2160, master/slave networking, logfile and OBS text-file plugins.
- Football state includes teams, scores, timeouts, offense, down, yards-to-go, ball position, and game phase.
- Windows instructions require installing Python and packages; no current installer/release packaging was found in the snapshot.
- Clock uses a Tornado `PeriodicCallback` and subtracts the difference between integer `time.time()` samples. This is better than assuming every callback equals one second, but it uses adjustable wall time, one-second precision, and mutable minute/second fields rather than a monotonic deadline.
- No independent 25/40 play clock was found.
- Root license is GPL-3.0.
- Latest snapshot commit is from September 2017.
- `plugins/testplugin.py` is an extension example; no automated test suite was found.

**Interpretation**

The project demonstrates a sound high-level split: authoritative Python state, web control/display, serialized snapshots, and output plugins. It is too old and network-oriented to adopt, and its clock/recovery/package model does not meet the MVP. GPL-3.0 reuse would also impose obligations that require an explicit project licensing decision.

**Recommendation: Borrow specific ideas.** Borrow the state-to-view/plugin boundary and full-snapshot update concept. Do not copy code during Phase 2.

### 3.2 KevinZheng2025/Football-Scoreboard

**Repository facts**

- A single approximately 38 KB Python/Tkinter `.pyw` program plus images and saved-game examples.
- README targets Windows/Mac users who install Python, run the file, capture a fixed scoreboard window in OBS, and color-key its background.
- The spectator window is fixed at 1280×43 and is explicitly non-resizable.
- Includes team names/colors/logos, timeouts, possession, football score increments, a game clock, saved team templates, and a touchdown animation.
- Clock loops with `time.sleep(0.1)`, increments a counter, and subtracts one second every ten iterations while calling Tk updates. It is vulnerable to scheduler/rendering drift and blocks normal event-loop design.
- Saved templates use Python pickle and cover identity settings rather than complete crash-safe game state.
- No root license or license declaration was found; no automated tests or packaging configuration were found.
- Latest snapshot commit is December 2021.

**Interpretation**

It is visually relevant and proves that separate Tkinter control/display windows can feed OBS, but fixed geometry, callback-count timing, single-file coupling, no safe license, and no tests make it unsuitable for reuse or live-stadium authority.

**Recommendation: Use only as a reference.** Observe its compact operator feature inventory; do not copy code or assets.

### 3.3 mmlTools/fly-scoreboard

**Repository facts**

- Active C++/Qt OBS Studio plugin with a dock UI, customizable HTML/CSS/JavaScript overlays, hotkeys, event logs, template selection, and a local WebSocket command/state service.
- Windows release layout installs a DLL and data into OBS; building requires CMake, Visual Studio, Qt/OBS dependencies. OBS is mandatory.
- State includes teams, arbitrary paired/single fields, and multiple count-up/countdown timers. The current overlay has modular pages labelled football with fouls, cards, and corners; this is not an American-football game model.
- Timer state stores `remaining_ms` and `last_tick_ms`; render code derives a live value from `Date.now()`, and native code reconciles elapsed time on stop. This avoids one-tick-per-callback drift, although wall-clock rather than monotonic time is visible in the inspected rendering path.
- State is serialized to `plugin.json` with WebSocket updates and file polling fallback; events are recorded separately.
- No automated test files or CTest configuration were found in the snapshot.
- Latest snapshot commit is August 2026.
- **License evidence conflicts:** README says “MIT License,” while the root `LICENSE` contains GNU GPL version 2 text. This must be clarified before any code reuse.

**Interpretation**

This is strong evidence for flexible web templates, full-state broadcast, fallback state files, and dock/hotkey workflows. It is OBS-centered, not American-football-specific, and has an unacceptable licensing ambiguity for adoption. Its C++/Qt plugin build is unnecessary for the MVP.

**Recommendation: Use only as a reference.** Borrow concepts only: complete state broadcasts, template/runtime separation, and event categories. Do not copy code until license provenance is resolved and compatibility is deliberately chosen.

### 3.4 alpower/scoreboard

**Repository facts**

- Two self-contained HTML files (association football and futsal), local font files, and logos; no build system or server.
- README instructs users to load a local file as an interactive OBS Browser Source and position its controls offscreen.
- Team settings/scores/period persist in browser `localStorage`.
- Association-football clock uses a one-second `setInterval` and increments an integer each callback. It does not reconcile actual elapsed time after a delayed callback.
- Score correction uses plus/minus-one buttons and direct numeric fields. It has no American-football +2/+3/+6 workflow or independent play clock.
- No license, automated tests, or Windows packaging was found.
- Latest snapshot commit is January 2025.

**Interpretation**

This is admirably small and easy to customize, but it combines controls and display in one file, relies on OBS interaction/localStorage, and has a drift-prone clock. Lack of a license prevents code/font/logo reuse.

**Recommendation: Use only as a reference.** The resolution-flexible HTML approach is useful; implement it independently.

### 3.5 StreamnDad/streamn-scoreboard

**Repository facts**

- C/C++/Qt OBS plugin supporting seven sport presets, including a generic football preset, with a native dock, 45 hotkeys, game/event timestamps, and 27 text outputs for OBS sources.
- Windows x64 release packages exist; OBS 30+ is required. Building on Windows requires Visual Studio, Qt, and OBS development dependencies.
- Architecture separates a pure C `scoreboard-core` static library from the OBS-dependent module.
- The game clock stores tenths. A 100 ms Qt timer uses `QElapsedTimer` elapsed time plus a remainder and passes actual elapsed tenths into the core, avoiding simple callback-count drift.
- The repository includes seven core test source files. README/CI claims 100% line coverage on the core; this Phase 1 review confirmed the files/configuration but did not independently compile or reproduce the coverage result.
- State/profile persistence, score adjustment, period advance/rewind, hotkeys, and event logging are covered. Football score events are intentionally not logged by default, and no football-specific +2/+3/+6 controls or 25/40 play clock were found.
- Root license and README identify GPL-2.0, required because it links with OBS/libobs.
- Latest snapshot commit is April 2026.

**Interpretation**

This is the strongest engineering reference: testable core separation, actual-elapsed-time clock calculation, hotkey inventory, persistence, and event logs are relevant. Adoption would make OBS and a C/C++ GPL plugin the MVP core while still leaving football-specific work, which is the wrong trade.

**Recommendation: Borrow specific ideas.** Independently implement the pure-core boundary, elapsed-time testing, explicit output adapters, and high-coverage reliability focus. Do not copy GPL code without a deliberate compatible licensing decision.

### 3.6 david-mcgaughy/scorebug

**Repository facts**

- High-school basketball OBS overlay with `control.html`, `overlay.html`, JSON configuration, a PowerShell ticker scraper, and CSV data.
- Manual control communicates through OBS WebSocket custom events; the overlay can also poll third-party scoreboard OCR at 200 ms and temporarily prioritize manual updates.
- Clock uses a one-second `setInterval` and subtracts one from `totalSeconds` per callback; it is not monotonic/deadline based.
- Team configuration can be changed live, but permanent changes require downloading and manually replacing `gameconfig.json`.
- The snapshot contains an OBS WebSocket password literal and remote CDN script references; that is unsuitable as a production security/offline pattern even if the password is only a local example.
- No automated tests or standalone Windows packaging were found. OBS and browser-source setup are central.
- Root license is GPL-3.0. Latest snapshot commit is December 2025.

**Interpretation**

The dashboard/overlay separation, manual failover concept, and visual control feedback are useful workflow references. Basketball/OCR/ticker features, callback clock, external resources, manual persistence, and OBS authority do not fit the MVP.

**Recommendation: Use only as a reference.** Borrow no code; note the failover/status UX patterns.

## 4. Cross-project lessons

### Proven patterns worth using

- A distinct authoritative state core and replaceable presentation/integration consumers.
- Complete state snapshots with revisions rather than view-owned truth.
- Separate operator and spectator surfaces.
- Actual elapsed-time clock math rather than decrement-per-callback.
- Hotkeys for frequent actions and explicit correction controls.
- Local persistence plus append-only event/audit information.
- Web presentation for scalable, customizable graphics.

### Risks repeatedly observed

- OBS becoming mandatory before production/media features need it.
- Callback-count clocks (`setInterval`/`sleep`) that drift under load.
- Controls and display sharing one page/window and one failure domain.
- `localStorage` or ad hoc files treated as complete recovery design.
- No tests around the most game-critical timing logic.
- Fixed pixel geometry intended for stream overlays rather than a full display.
- Absent or ambiguous licensing.

## 5. Adoption decision

Implement the Phase 2 MVP independently under the architecture in [ARCHITECTURE.md](ARCHITECTURE.md). Borrow concepts, not code. Before any future third-party copy or dependency adoption:

1. record the exact repository commit and file;
2. verify the license from consistent repository evidence;
3. confirm compatibility with this project's as-yet-unselected license;
4. preserve required notices/source obligations;
5. add tests proving the borrowed component meets MVP behavior.

This review does not claim that no similar project exists. It records only the candidates inspected for this Phase 1 decision.
