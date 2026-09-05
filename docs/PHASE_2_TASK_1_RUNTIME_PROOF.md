# Phase 2 Task 1 — Runtime and Windows Multi-Window Proof

**Status:** Implemented; one-display Windows smoke evidence is recorded in `PROJECT_ROADMAP.md`. The normal two-display manual checks remain pending.

This task proves only the managed-window host. The HTML pages intentionally contain placeholder text and display-host controls only. They do not implement scoreboard state, scoring, clocks, persistence, SQLite, styling, OBS, a server, hardware protocols, or peripheral integration.

## Verified host versions

- Windows host Python: CPython 3.11.11 (the locally available Blender-bundled interpreter was used only to create the development virtual environment).
- `pywebview==6.2.1`
- Windows WebView2 Runtime: `152.0.4191.62`
- `pip==24.0` created the verified virtual environment. It is not a project dependency.

All runtime packages resolved during verification are exact pins in `pyproject.toml`. No package is fetched at application launch. Once the environment has been installed, the proof runs without network access.

## PowerShell setup and run

Use a normal CPython 3.11 installation. The commands below use the Python launcher when it is available. This host lacked the launcher, so the verified environment was created with its available CPython 3.11.11 executable instead.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --editable .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\scoreboard.exe
```

The final command starts one Python process. By default it chooses display index `1` (Windows `Display 2`) for the fullscreen spectator window. To deliberately exercise the missing-display behavior, run:

```powershell
.\.venv\Scripts\scoreboard.exe --display-index 99
```

For a non-interactive clean-shutdown smoke test, use the proof-only option below. It opens the requested windows, then closes the operator and all owned windows after 30 seconds. The longer interval gives WebView2 enough time to initialize on the verified host:

```powershell
.\.venv\Scripts\scoreboard.exe --display-index 0 --auto-close-after-seconds 30
```

> **Renamed in Task 11.** The console entry point was `scoreboard-proof` while this
> was a placeholder proof; it is now `scoreboard`, and the packaged build is
> `Scoreboard.exe`. See [Packaging](PACKAGING.md).

## Reproducible manual verification

On a normal Windows two-display setup:

1. Run `scoreboard`. Confirm the operator placeholder and a borderless fullscreen spectator placeholder open; confirm the spectator is on the selected second display.
2. In the operator window, choose each display and use **Open or reopen spectator**. Confirm it appears on the chosen display without covering the operator unless that display was explicitly selected.
3. Use **Toggle spectator fullscreen** twice and confirm fullscreen enters and exits. Reopen the spectator to restore the intended fullscreen state.
4. Close the spectator using its normal window close gesture. Confirm the operator remains usable, shows `DISPLAY CLOSED`, and reopens it with the button.
5. Start with `--display-index 99`. Confirm the operator shows `DISPLAY NOT FOUND: Display 100` and no spectator takes over the primary display.
6. Close the operator. In Task Manager, confirm the `scoreboard` Python process exits and no child process remains.
7. Disconnect network adapters after the editable install, repeat steps 1–6, and record the outcome. This task does not test HDMI/LED hardware or alter any hardware configuration.

The stadium HDMI test remains a separate Phase 0 gate. Task 10 will add persisted display identity and disconnect/reconnect handling against the real scoreboard views.
