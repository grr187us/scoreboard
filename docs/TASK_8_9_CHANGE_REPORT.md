# Tasks 8 and 9 change report

Historical report. Implemented in the requested order: recovery prerequisite (`c3fd05a`),
Task 8 spectator foundation (`6691c13`), then Task 9 keyboard/input safety.
Task 9 uses the commit title `Add keyboard controls with shared confirmation and input safety`.
The report describes the original Task 8/9 implementation session; later Task 10, packaging, audit, and presentation commits supersede its repository-status statements.

Validation: 261 unittest tests passed, including 36 spectator viewport cases and
keyboard browser tests against the real bridge and temporary SQLite store.
compileall, pip check, JavaScript syntax, UTF-8, diff whitespace and relative
Markdown file-link checks passed. Browser test tooling is development only.

Pending release evidence: stadium HDMI gate, physical WebView2 scaling,
two-display/fullscreen/reopen behavior, end-to-end visible latency, real OS
repeat/numpad behavior, novice and recovery rehearsal, real power-loss/full-disk tests.

The former model did not distinguish stopped expiry from clear. An additive
persisted visibility flag fixes new snapshots; legacy snapshots lacking it
retain the old stopped-zero-is-blank behavior.

## Complete changed-file inventory

55 files relative to the starting commit `5d76568`, including this report.
All are included in the three requested local commits; no uncommitted files remain after completion.

- [PROJECT_ROADMAP.md](../PROJECT_ROADMAP.md)
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/MVP_REQUIREMENTS.md](MVP_REQUIREMENTS.md)
- [docs/PHASE_2_BACKLOG.md](PHASE_2_BACKLOG.md)
- [docs/PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- [docs/TASK_8_9_CHANGE_REPORT.md](TASK_8_9_CHANGE_REPORT.md)
- [docs/UX_AND_LAYOUT.md](UX_AND_LAYOUT.md)
- [docs/evidence/task8/1280x720-3.png](evidence/task8/1280x720-3.png)
- [docs/evidence/task8/1280x720-4.png](evidence/task8/1280x720-4.png)
- [docs/evidence/task8/1280x720-5.png](evidence/task8/1280x720-5.png)
- [docs/evidence/task8/1280x720-7.png](evidence/task8/1280x720-7.png)
- [docs/evidence/task8/1366x768-3.png](evidence/task8/1366x768-3.png)
- [docs/evidence/task8/1366x768-4.png](evidence/task8/1366x768-4.png)
- [docs/evidence/task8/1366x768-5.png](evidence/task8/1366x768-5.png)
- [docs/evidence/task8/1366x768-7.png](evidence/task8/1366x768-7.png)
- [docs/evidence/task8/1920x1080-3.png](evidence/task8/1920x1080-3.png)
- [docs/evidence/task8/1920x1080-4.png](evidence/task8/1920x1080-4.png)
- [docs/evidence/task8/1920x1080-5.png](evidence/task8/1920x1080-5.png)
- [docs/evidence/task8/1920x1080-7.png](evidence/task8/1920x1080-7.png)
- [docs/evidence/task8/390x844-3.png](evidence/task8/390x844-3.png)
- [docs/evidence/task8/390x844-4.png](evidence/task8/390x844-4.png)
- [docs/evidence/task8/390x844-5.png](evidence/task8/390x844-5.png)
- [docs/evidence/task8/390x844-7.png](evidence/task8/390x844-7.png)
- [docs/evidence/task8/README.md](evidence/task8/README.md)
- [docs/evidence/task8/measurements.json](evidence/task8/measurements.json)
- [src/scoreboard/__main__.py](../src/scoreboard/__main__.py)
- [src/scoreboard/application/service.py](../src/scoreboard/application/service.py)
- [src/scoreboard/application/snapshots.py](../src/scoreboard/application/snapshots.py)
- [src/scoreboard/domain/state.py](../src/scoreboard/domain/state.py)
- [src/scoreboard/host/app.py](../src/scoreboard/host/app.py)
- [src/scoreboard/host/bridge.py](../src/scoreboard/host/bridge.py)
- [src/scoreboard/host/startup.py](../src/scoreboard/host/startup.py)
- [src/scoreboard/views/operator/index.html](../src/scoreboard/views/operator/index.html)
- [src/scoreboard/views/operator/keyboard.js](../src/scoreboard/views/operator/keyboard.js)
- [src/scoreboard/views/operator/operator.css](../src/scoreboard/views/operator/operator.css)
- [src/scoreboard/views/operator/operator.js](../src/scoreboard/views/operator/operator.js)
- [src/scoreboard/views/spectator/index.html](../src/scoreboard/views/spectator/index.html)
- [src/scoreboard/views/spectator/spectator.css](../src/scoreboard/views/spectator/spectator.css)
- [src/scoreboard/views/spectator/spectator.js](../src/scoreboard/views/spectator/spectator.js)
- [src/scoreboard/views/startup/index.html](../src/scoreboard/views/startup/index.html)
- [src/scoreboard/views/startup/startup.js](../src/scoreboard/views/startup/startup.js)
- [tests/README.md](../tests/README.md)
- [tests/integration/test_bridge.py](../tests/integration/test_bridge.py)
- [tests/integration/test_host_application.py](../tests/integration/test_host_application.py)
- [tests/integration/test_keyboard_source.py](../tests/integration/test_keyboard_source.py)
- [tests/integration/test_spectator.py](../tests/integration/test_spectator.py)
- [tests/integration/test_startup.py](../tests/integration/test_startup.py)
- [tests/ui/__init__.py](../tests/ui/__init__.py)
- [tests/ui/bridge_server.py](../tests/ui/bridge_server.py)
- [tests/ui/browser_support.py](../tests/ui/browser_support.py)
- [tests/ui/keyboard.cjs](../tests/ui/keyboard.cjs)
- [tests/ui/spectator.cjs](../tests/ui/spectator.cjs)
- [tests/ui/test_keyboard_browser.py](../tests/ui/test_keyboard_browser.py)
- [tests/ui/test_spectator_browser.py](../tests/ui/test_spectator_browser.py)
- [tests/unit/test_commands.py](../tests/unit/test_commands.py)
