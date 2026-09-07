# Windows packaging and offline launch

**Status:** Rebuilt and verified on the development host September 7, 2026,
including Tigers Stadium and the current cutscenes. `dist/Scoreboard` contains
version 0.1.0, 823 files, 31.0 MB. Asset and frozen `--check` verification
passed with isolated data. Clean-machine, network-disabled, stadium, and
target-laptop acceptance remain open.
An eight-second frozen-process smoke check against an isolated saved Tigers
Stadium layout exited 0 and logged clean startup/shutdown. This does not
establish physical display placement or readability.
**Last updated:** September 7, 2026

This document covers how the offline package is built, what it contains, what the operator's laptop must already have, and which acceptance checks still need a person.

The September 7 build used the available Blender CPython 3.11.11 runtime
with `src` and the pinned dependencies in `.venv/Lib/site-packages` on
`PYTHONPATH`; the repository `.venv` launcher currently points at a missing
python.org installation. Restore the documented Python 3.11 environment
before following the usual build command below. The full discovered suite
passed 1115 tests with 3 expected A-1 skips on the build runtime.

## What the package is

A PyInstaller **one-folder** build (W-003): `dist/Scoreboard/`, containing `Scoreboard.exe` and an `_internal/` folder with the Python runtime, the dependencies, and the bundled pages.

One folder rather than one file is deliberate. A one-folder build starts without unpacking to a temporary directory, keeps the pages visible as ordinary files that can be inspected on the operator's laptop when something looks wrong, and makes it obvious what shipped. One-file packaging stays deferred until recovery, startup time, and asset handling are proven in the field.

The build is windowed: there is no console. Every fatal message an operator needs — a missing WebView2 runtime, a second instance, a recovery choice the window flow could not make — reaches them through a message box instead of a `print` nobody would see. That is what `scoreboard.host.preflight.report` is for.

## Versions this was built and tested with

| Component | Version |
|---|---|
| Windows | 11 Home, 10.0.26200.9278 |
| Python | 3.11.11 (64-bit) |
| PyInstaller | 6.22.2 |
| pywebview | 6.2.1 |
| Microsoft Edge WebView2 Runtime | 152.0.4191.62 |
| Application | 0.1.0 |

The application version has one definition, `APP_VERSION` in `src/scoreboard/domain/state.py`. The packaging metadata, the executable's Windows version resource, the diagnostics log, the durable action history, and every stored snapshot all follow it, so a build cannot be stamped with a version the running code does not report (W-006).

## Building

From the repository root, in the virtual environment from [the Task 1 runtime proof](PHASE_2_TASK_1_RUNTIME_PROOF.md):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe tools\build_package.py
```

`build` is an optional dependency group holding PyInstaller alone. Nothing in it ships inside the package, and the application never imports any of it.

The script cleans stale output, runs PyInstaller against [`tools/scoreboard.spec`](../tools/scoreboard.spec), and then verifies the result rather than trusting the exit code:

- every page, stylesheet, and script a window loads is present and non-empty;
- no bundled page references a remote resource, because the stadium laptop has no internet during a game;
- the frozen executable runs `--check` end to end, exits cleanly, and reports the expected version.

To re-verify an existing build without rebuilding it, add `--verify-only`.

## Installing on an operator laptop

1. Copy the whole `Scoreboard` folder anywhere the operator can write to — the desktop is fine. Keep the folder together; `Scoreboard.exe` will not run on its own.
2. Right-click `Scoreboard.exe` → **Send to** → **Desktop (create shortcut)**, and rename the shortcut `Scoreboard`. That shortcut is the one action that starts the game and both windows (W-004).
3. Double-click the shortcut once before game day and let it open, then close it. The first launch is the slowest.

**SmartScreen.** The executable is not code-signed, so Windows may show *"Windows protected your PC"* the first time. Choose **More info** → **Run anyway**. If the folder arrived in a `.zip`, right-click the zip → **Properties** → tick **Unblock** before extracting, which avoids the prompt for every file inside. Code signing is out of scope for the MVP; if the school's machine policy blocks unsigned executables outright, that is a deployment constraint to raise before the first live use, not something the package can work around.

## What the laptop must already have

Exactly one thing: the **Microsoft Edge WebView2 Runtime**. Both windows are drawn with it, and it is the one component the package cannot carry.

It is present by default on current Windows 11 installations. The application checks for it at startup and, if it is absent, says so in a dialog naming the remedy rather than opening no window:

> Install the Microsoft Edge WebView2 Runtime (Evergreen Standalone Installer) from Microsoft, then start the scoreboard again. It is a one-time install on this laptop and needs an internet connection only while it downloads; the scoreboard itself never needs one.

To check a laptop without starting a game:

```powershell
.\Scoreboard.exe --check
```

That reports the application version, the WebView2 runtime version, and the data folder, writes the same report to `%LOCALAPPDATA%\Scoreboard\logs\readiness.txt`, and exits. It never opens a dialog, so it is safe in a script; add `--show` if you want a double-clickable shortcut that displays the result.

Python, Node.js, and OBS are **not** required on the operator machine (W-002).

## Where the game lives

Runtime data is outside the application folder, under `%LOCALAPPDATA%\Scoreboard`:

| Path | Contents |
|---|---|
| `scoreboard.db` | The current game, its state, and its append-only action history |
| `scoreboard.backup.db` | The automatically refreshed last-known-good copy |
| `scoreboard.lock` | The single-instance lock, released by Windows when the process exits |
| `logs\application.log` | The bounded rotating diagnostic log |
| `logs\readiness.txt` | The most recent `--check` report |

This is why an update is safe mid-season: replacing the whole `Scoreboard` folder does not touch a game (W-005). Verified on September 5, 2026 by seeding a game, deleting the application folder entirely, rebuilding it, and launching the new build, which recovered the same game — Tigers 7, Eagles 3, second quarter — with its history continuing in one log.

## Choosing where the game is saved

The default above is correct but buried several folders deep. An operator who wants the game and its logs somewhere they can find after a game — a folder on the desktop, a shared drive, a USB stick — can choose one:

- **In the application:** open **Corrections**, and use **Choose folder…** in the *Saved to* row at the bottom. **Use standard folder** puts it back. Display selection is no longer in Corrections; it lives in the separate **Display…** drawer.
- **Before a season, without starting a game:** run `Scoreboard.exe --choose-data-folder`, or make a second shortcut with that argument. It opens the same picker, starts no game, takes no instance lock, and opens no database.

The choice takes effect **the next time the scoreboard starts**. The running game keeps saving where it already was, because its database connection, its instance lock, and its log handler are all open on that folder; moving them under a live game is a much larger operation than this feature is, and one no operator should trigger by accident mid-quarter. Every dialog says this.

The choice is remembered in `%LOCALAPPDATA%\Scoreboard\data-location.json`, which deliberately stays in the *standard* location even when the game data does not — a pointer stored inside the folder it points at could never be found again.

If the chosen folder is gone at the next launch — the USB stick is not plugged in, the share is not mapped — the scoreboard reports the standard folder and starts normally rather than refusing to run. Losing a preference is recoverable; not starting before kickoff is not.

Resolution order, highest first:

| Source | When it applies |
|---|---|
| `SCOREBOARD_DATA_DIR` | Tests and rehearsals. It outranks a chosen folder on purpose, so a rehearsal can never write into the real game folder by accident. Do not set it on the production laptop. |
| The chosen folder | Whenever one is saved and still reachable |
| The standard per-user location | Otherwise |

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Normal run and clean shutdown |
| 1 | `--check` found a problem, or `--choose-data-folder` could not save the choice |
| 2 | Another copy is already running; the first one keeps the game |
| 3 | A recovery choice was needed and the window flow could not make it |
| 4 | The WebView2 runtime is missing |

## Release checks that still need a person

A build script cannot establish any of these. None may be treated as passed on the strength of a green build.

- [ ] **Clean machine.** Copy the folder to a Windows account with no Python, no Node.js, and no OBS, and launch it from the shortcut. Record the Windows build.
- [ ] **Offline.** Disable every network adapter and complete a full game workflow (R-001).
- [ ] **No terminal.** Confirm nothing resembling a console window appears at any point.
- [ ] **Missing WebView2.** On a machine without the runtime, confirm the dialog appears and names the remedy. This has been proven only by test double so far; the real absence has not been observed.
- [ ] **SmartScreen.** Record exactly what the school's laptop shows on first launch and whether policy permits running it.
- [ ] **Second display.** Spectator placement, fullscreen, close and reopen, disconnect and reconnect, resolution and scaling changes. Built in Task 10 and covered by automated tests against a fake screen list; none of it has run on real two-display hardware. Work [the two-display checklist](DISPLAY_CHECKLIST.md), which is written for exactly this.
- [ ] **Update during a season.** Replace the folder with a newer build between two games and confirm the previous game still recovers, this time on the target laptop.
- [ ] **Startup time.** Time the shortcut to a usable operator window on the target laptop, cold and warm.

## Development-host evidence, September 5, 2026

What has been verified here, and only here:

- The package builds reproducibly: 152 files, 27.3 MB, application version 0.1.0.
- `Scoreboard.exe` carries the version in its Windows file-version resource; Properties shows FileVersion and ProductVersion 0.1.0.
- A packaged launch with an isolated data folder opened the operator and fullscreen spectator windows, logged `STARTUP app_version=0.1.0`, `RECOVERY`, `DISPLAY_OPENED`, and `SHUTDOWN reason=clean`, exited 0, and left no orphan process.
- The application folder was deleted, rebuilt, and relaunched; the seeded game recovered intact with a continuous history.
- A non-editable wheel now contains all eleven view files. The previous metadata declared only `*.html`, which would have shipped the pages without their stylesheets or scripts.

This host has one display, so nothing about second-display placement is claimed.

## Rebuild after Task 10, September 5, 2026

The build recorded above carried the Task 1-era display behaviour — a fixed `--display-index`, no saved display, no disconnect handling — because Task 11 was built before Task 10. **It has been rebuilt.** 152 files, 27.4 MB, version 0.1.0, and the build script's own verification passed: every page, stylesheet, and script present and non-empty, no bundled page referencing a remote resource, and the frozen executable running `--check` end to end.

The rebuilt package was then confirmed to carry the new behaviour rather than the old, against an isolated data folder on this one-display host:

- With no display saved, it **opened no spectator window** and logged `DISPLAY_CLOSED reason='No second display is connected, so the spectator board was not opened over your controls…'`. The old build would have used a fixed index. Exit 0, no orphan process.
- With a display saved in `config.json`, it logged `DISPLAY_OPENED` and `DISPLAY_SELECTED … how=exact` and opened the fullscreen board on it. Exit 0.
- With a deliberately corrupt `config.json`, it started normally and simply behaved as though nothing was saved — the tolerance rule, observed in the frozen build rather than only in a test.

`--display-index` now defaults to "use the saved display" instead of `1`. A technician can still force an index from a terminal, and doing so does not overwrite the saved display.

Second-display placement is still not claimed. Work [the two-display checklist](DISPLAY_CHECKLIST.md).
