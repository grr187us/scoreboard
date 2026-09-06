# Current Project Audit — September 6, 2026

**Status:** Completed repository-to-document reconciliation. This is a point-in-time audit; `PROJECT_ROADMAP.md` remains the command center.

## Scope and verified baseline

This audit compared the implementation, tests, tracked documentation, active `.scratch/` specifications, packaging record, and working tree. It deliberately did not rewrite `High School LED Scoreboard — Project Knowledge Base.md`, which remains historical reference material.

The full discovered suite was rerun from a clean temporary Python 3.11.9 environment with the repository's pinned dependencies, Node.js on `PATH`, and an isolated `SCOREBOARD_DATA_DIR`:

```text
Ran 853 tests in 48.448s
OK (skipped=3)
```

The three skips explicitly name open football-rules question A-1. `compileall` passed, `uv pip check` found all 17 installed packages compatible, the repository checker found 0 broken relative links across 24 Markdown files, and `git diff --check` passed with line-ending notices only.

The checked-out branch is `feature/field-status` at `e1e3b04`. The C4/C5/F4 work and the partial F3/implemented I4 work are uncommitted working-tree changes; the audit preserved them.

## Material deviations found

| Area | Documented before this audit | What the working tree actually does | Disposition |
|---|---|---|---|
| C4 publication ordering | Claimed a `(revision, sequence)` guard made cross-thread delivery fully stale-proof and that a stalled UI affected only that window | The command lock is correctly released before any webview call, so commands, clocks, persistence, and checkpoints continue. However, `_publish_lock` protects only the ordering check, not the per-window offers. Two delivery threads can interleave an older spectator offer after a newer one. One `WindowPublisher` worker also serializes all window deliveries, so one blocked window delays later deliveries to other windows | C4 is reopened as **partially implemented**. The safety win is retained, but cross-window ordering/isolation needs an implementation correction and a concurrency regression test before C4 is complete |
| F3 crowd status | Roadmap said entirely absent; test documentation implied F3 existed | Reconciled as layout-only groundwork on September 6, 2026, then **completed the same day**: authoritative `game_status`/`status_clock` state, a `StatusCountdown` engine, four commands, bridge values, spectator widgets, and an always-visible operator crowd row now exist, with unit, contract, and real-bridge browser evidence | Recorded as **implemented**. See the F3 row in `PROJECT_ROADMAP.md` for the evidence and the three deliberate limits |
| I4 undo history | Roadmap, architecture, README, and backlog still described one-level Undo | The service keeps an in-memory LIFO stack of up to 20 reversible entries, the bridge publishes the stack, and the operator exposes its history. Barriers clear the stack; recovery intentionally restores none of it | Marked implemented and current documents updated. Historical Task 5 text is retained as the original baseline, with a later-expansion note |
| F4 team presets | Roadmap had the right functional boundary but stale focused-test counts | `teams.json`, host actions, operator library, identity lookup, and operator-side colour/short-name cues are present. Spectator visual identity is still deliberately absent | Presets remain implemented; counts and the partial-boundary wording are corrected |
| Test baseline | Current documents variously said 750 or 837 tests | Current working tree discovers 853 tests and passes all of them except the three deliberate A-1 skips | Current-status documents now use 853. Older counts remain only where they describe historical runs |
| Local development environment | Documents described the repository `.venv` as rebuilt and usable | Its `pyvenv.cfg` points to an unavailable user-profile Python path and the launcher cannot start. A clean temporary environment could be built from the declared dependencies and passed the suite | The repository `.venv` is local/generated and may be removed and recreated; documentation no longer presents it as current reproducibility evidence |
| Packaged application | Roadmap wording implied the available package carried the latest behavior | `dist/` is absent, and the September 5 package record predates the current C4/C5/F3/F4/I4 working tree | Packaging evidence remains historical. A fresh build is required before target-laptop checks |
| Field Assistant evidence | Some summaries still said native WebView2 had not been exercised | The real pywebview/WebView2 development-host harness is recorded and passed; target-laptop 1366×768/125% and live-volunteer rehearsal remain open | Current status now distinguishes development-host evidence from release evidence |
| Display recovery navigation | The physical checklist still directed operators through Corrections | C5 moved this workflow to the dedicated `Display…` drawer | Checklist and packaging instructions updated |

## Files that may safely be removed locally

No tracked source, test, specification, or evidence file is unambiguously safe to remove. In particular, keep `brand-baseline/` as design provenance, and keep both active untracked `.scratch/` efforts plus the untracked F4/C4 implementation and tests.

The following ignored/generated local artifacts may be removed without losing source history. Nothing was deleted during this audit.

| Path | Why removable | How restored / caveat |
|---|---|---|
| `.venv/` | Generated environment; currently broken because its interpreter path is stale | Recreate from Python 3.11 with `py -3.11 -m venv .venv`, then `python -m pip install -e ".[build]"` |
| `node_modules/` | Generated JavaScript development dependencies | Restore with `npm ci` from the committed lockfile |
| `src/scoreboard.egg-info/` | Editable-install metadata | Recreated by the editable install |
| `**/__pycache__/` | Python bytecode caches | Recreated automatically |
| `Run Scoreboard.lnk` | Ignored machine-local convenience shortcut | Remove only if the owner does not use it |
| `.vscode/` | Ignored editor-local settings | Remove only if the owner does not use them |

## Current release blockers

1. Repair C4's cross-thread/per-window publication ordering and prove it with a forced-interleaving test.
2. Perform the Phase 0 stadium HDMI gate and record evidence.
3. Work the two-display checklist on real hardware.
4. Answer A-1 with the owner/officials.
5. Rebuild the package from the reconciled working tree, then run the target-laptop/offline checks.
6. Complete Task 12 sustained rehearsal and recovery acceptance.

F3 completion, spectator team visual identity, and the other roadmap features remain planned work, not release evidence already earned.
