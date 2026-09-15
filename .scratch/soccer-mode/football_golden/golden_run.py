"""A deterministic football golden run: the regression oracle for soccer mode.

Drives a real football game through the real production stack --
``scoreboard.host.app.ScoreboardApplication`` and its
``scoreboard.host.bridge.ScoreboardBridge`` -- with no pywebview window at all.
Every command goes through ``bridge.command(name, args, expected_revision)``,
exactly the path the operator page uses; every clock advance goes through a
fake monotonic source plus ``app.tick()``, exactly the path the 10 Hz refresh
loop uses.

This script owns nothing under ``src/``, ``tests/``, ``tools/``, or ``docs/``
(football is frozen -- see ``.scratch/soccer-mode/CONTEXT_FOR_AGENTS.md``). It
only reads the installed ``scoreboard`` package and writes its own output
under ``.scratch/soccer-mode/football_golden/<outdir>/``.

Usage::

    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe golden_run.py --out current

Determinism
-----------

* The monotonic clock is a ``FakeMonotonic`` starting at 1000.0, advanced only
  by this script (never by wall time).
* The wall clock used for persistence timestamps
  (``scoreboard.infrastructure.persistence.utc_now``, the module-level name
  ``GameStore`` binds as its default ``wall_clock``) is monkeypatched to a
  ``FakeWallClock`` starting at 2026-09-14T19:30:00+00:00, advancing one
  second per reading. ``scoreboard.infrastructure.diagnostics.utc_now`` is
  patched the same way for completeness, though ``NullDiagnostics`` (used
  here) never calls it.
* ``ScoreboardApplication`` is built with ``diagnostics=NullDiagnostics()`` so
  no diagnostics log file timing can leak into the output.
* Every JSON value already comes from the bridge's JSON-only contract (no
  Python object ever crosses ``operator_view_model``/``spectator_view_model``/
  ``state_to_snapshot``), so no normalization beyond the wall clock above is
  needed -- and that wall clock is already deterministic given the patch.

Run this script twice into two output directories and diff them with
``diff_golden.py`` to prove determinism before trusting either as a baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

# --- Make the real scoreboard package importable -----------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import scoreboard.infrastructure.diagnostics as diagnostics_module  # noqa: E402
import scoreboard.infrastructure.persistence as persistence_module  # noqa: E402

from scoreboard.application.snapshots import state_to_snapshot  # noqa: E402
from scoreboard.host.app import ScoreboardApplication  # noqa: E402
from scoreboard.infrastructure.diagnostics import NullDiagnostics  # noqa: E402
from scoreboard.infrastructure.paths import resolve_paths  # noqa: E402
from scoreboard.infrastructure.persistence import read_action_history  # noqa: E402


# --- Fakes (mirrors tests/integration/support.py) ----------------------------


class FakeMonotonic:
    """A monotonic source advanced only by this script."""

    def __init__(self, value: float = 1000.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class FakeWallClock:
    """A wall clock that ticks one second per reading, for stable timestamps."""

    def __init__(self, start: datetime | None = None, step_seconds: float = 1.0) -> None:
        self.value = start or datetime(2026, 9, 14, 19, 30, 0, tzinfo=timezone.utc)
        self.step = timedelta(seconds=step_seconds)
        self.readings = 0

    def __call__(self) -> datetime:
        self.readings += 1
        current = self.value
        self.value += self.step
        return current


# --- The driver ---------------------------------------------------------------


class GoldenRun:
    """Owns one application instance and records every step's complete state."""

    def __init__(self, data_root: Path) -> None:
        self.fake_monotonic = FakeMonotonic(1000.0)
        self.fake_wall = FakeWallClock()
        # GameStore.__init__ binds ``utc_now if wall_clock is None else
        # wall_clock`` against *this module's* name at call time, so patching
        # the name here (before any GameStore.open() call) is what actually
        # makes every persisted timestamp deterministic.
        persistence_module.utc_now = self.fake_wall  # type: ignore[assignment]
        diagnostics_module.utc_now = self.fake_wall  # type: ignore[assignment]

        self.paths = resolve_paths(data_root)
        self.app = ScoreboardApplication(
            self.paths,
            monotonic_clock=self.fake_monotonic,
            diagnostics=NullDiagnostics(),
        )
        self.bridge = self.app.start_new()
        self.records: list[dict[str, Any]] = []

    # --- Time -----------------------------------------------------------

    def advance(self, seconds: float) -> None:
        self.fake_monotonic.advance(seconds)

    def tick(self) -> None:
        self.app.tick()

    # --- Commands ---------------------------------------------------------

    def command(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        expect_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Submit one bridge command, following the confirm-then-resend dance.

        Every call reads ``expected_revision`` from the live service so a
        stale-revision rejection can never sneak in from a mis-tracked value.
        """

        args = dict(args or {})
        expected_revision = self.app.service.revision
        result = self.bridge.command(name, args, expected_revision)
        if expect_confirmation:
            if not result.get("confirmation_required"):
                raise AssertionError(
                    f"{name}{args}: expected CONFIRMATION_REQUIRED, got {result}"
                )
            revision = result["view"]["revision"]
            confirmed_args = dict(args)
            confirmed_args["confirmed"] = True
            result = self.bridge.command(name, confirmed_args, revision)
        if not result.get("accepted"):
            raise AssertionError(f"{name}{args} was rejected: {result.get('error')}")
        return result

    # --- Recording ----------------------------------------------------------

    def record(self, index: int, name: str) -> None:
        operator = self.bridge.get_snapshot()
        spectator = self.bridge.spectator_snapshot()
        state_snapshot = state_to_snapshot(self.app.service.state)
        history = read_action_history(self.paths.database)
        self.records.append(
            {
                "index": index,
                "name": name,
                "operator": operator,
                "spectator": spectator,
                "state_snapshot": state_snapshot,
                "history": history,
            }
        )

    def step(
        self,
        index: int,
        name: str,
        action: Callable[["GoldenRun"], None],
    ) -> None:
        action(self)
        # A small settle so a checkpoint has a chance to see a changed
        # displayed second even on a step that issued no explicit advance.
        self.advance(0.5)
        self.tick()
        self.record(index, name)


# --- The football script -------------------------------------------------


def _cmd(name: str, args: dict[str, Any] | None = None, *, confirm: bool = False):
    def action(run: GoldenRun) -> None:
        run.command(name, args, expect_confirmation=confirm)

    return action


def _advance(seconds: float):
    def action(run: GoldenRun) -> None:
        run.advance(seconds)
        run.tick()

    return action


#: (step name, action). Executed in order; every step is recorded.
FOOTBALL_SCRIPT: list[tuple[str, Callable[[GoldenRun], None]]] = [
    ("new_game", _cmd("new_game", {}, confirm=True)),
    ("set_team_name_home_tigers", _cmd("set_team_name", {"team": "home", "name": "Tigers"})),
    ("set_team_name_away_eagles", _cmd("set_team_name", {"team": "away", "name": "Eagles"})),
    ("game_clock_start_pre", _cmd("game_clock_start")),
    ("advance_65s_pregame", _advance(65.0)),
    ("game_clock_stop_pre", _cmd("game_clock_stop")),
    ("set_quarter_1st", _cmd("set_quarter", {"label": "1st"}, confirm=True)),
    ("play_clock_preset_40", _cmd("play_clock_preset", {"seconds": 40})),
    ("play_clock_start", _cmd("play_clock_start")),
    ("advance_4s", _advance(4.0)),
    ("game_clock_start_1st", _cmd("game_clock_start")),
    ("advance_12_4s", _advance(12.4)),
    ("game_clock_stop_1st", _cmd("game_clock_stop")),
    ("add_score_home_6_touchdown", _cmd("add_score", {"team": "home", "points": 6})),
    ("add_score_home_1_try", _cmd("add_score", {"team": "home", "points": 1})),
    ("set_down_1", _cmd("set_down", {"value": 1})),
    ("set_distance_10", _cmd("set_distance", {"value": 10})),
    ("set_possession_away", _cmd("set_possession", {"team": "away"})),
    ("set_ball_on_away_25", _cmd("set_ball_on", {"team": "away", "value": 25})),
    ("set_down_nudge_plus1", _cmd("set_down", {"nudge": 1})),
    ("set_distance_nudge_minus3", _cmd("set_distance", {"nudge": -3})),
    ("set_ball_on_nudge_plus5", _cmd("set_ball_on", {"nudge": 5})),
    ("set_ball_on_nudge_minus1", _cmd("set_ball_on", {"nudge": -1})),
    ("timeout_used_home", _cmd("timeout_used", {"team": "home"})),
    ("timeout_correct_away_minus1", _cmd("timeout_correct", {"team": "away", "points": -1})),
    ("set_game_status_timeout_60", _cmd("set_game_status", {"label": "TIMEOUT", "seconds": 60})),
    ("advance_3s_timeout", _advance(3.0)),
    ("status_clock_stop", _cmd("status_clock_stop")),
    ("clear_game_status_timeout", _cmd("clear_game_status")),
    ("set_game_status_flag", _cmd("set_game_status", {"label": "FLAG"})),
    ("clear_game_status_flag", _cmd("clear_game_status")),
    ("add_score_away_3", _cmd("add_score", {"team": "away", "points": 3})),
    ("undo_away_3", _cmd("undo")),
    ("correct_score_home_1", _cmd("correct_score", {"team": "home", "points": 1})),
    ("undo_correct_score_home", _cmd("undo")),
    ("set_quarter_2nd", _cmd("set_quarter", {"label": "2nd"}, confirm=True)),
    ("set_quarter_half", _cmd("set_quarter", {"label": "HALF"}, confirm=True)),
    ("game_clock_start_half", _cmd("game_clock_start")),
    ("advance_30s_half", _advance(30.0)),
    ("game_clock_stop_half", _cmd("game_clock_stop")),
    ("set_quarter_3rd", _cmd("set_quarter", {"label": "3rd"}, confirm=True)),
    ("set_quarter_4th", _cmd("set_quarter", {"label": "4th"}, confirm=True)),
    ("game_clock_correct_45", _cmd("game_clock_correct", {"seconds": 45})),
    ("game_clock_start_4th", _cmd("game_clock_start")),
    ("advance_50s_expiry", _advance(50.0)),
    ("set_quarter_ot", _cmd("set_quarter", {"label": "OT"}, confirm=True)),
    ("set_quarter_final", _cmd("set_quarter", {"label": "FINAL"}, confirm=True)),
    ("end_game", _cmd("end_game")),
]


# --- Output -------------------------------------------------------------------


def write_output(run: GoldenRun, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.glob("*.json"):
        existing.unlink()
    summary_lines = [
        "Football golden run",
        "====================",
        "",
    ]
    for record in run.records:
        index = record["index"]
        name = record["name"]
        file_path = out_dir / f"{index:02d}-{name}.json"
        payload = {
            "index": index,
            "name": name,
            "operator": record["operator"],
            "spectator": record["spectator"],
            "state_snapshot": record["state_snapshot"],
        }
        file_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        operator = record["operator"]
        summary_lines.append(
            f"{index:02d} {name}: revision={operator['revision']} "
            f"quarter={operator['quarter']} lifecycle={operator['lifecycle']} "
            f"HOME={operator['teams']['home']['score']} "
            f"AWAY={operator['teams']['away']['score']}"
        )

    # The full action history is identical (and growing) across every step by
    # the end of the run, so it is written once rather than once per step.
    final_history = run.records[-1]["history"] if run.records else []
    (out_dir / "history.json").write_text(
        json.dumps(final_history, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    final_operator = run.records[-1]["operator"] if run.records else None
    summary_lines.extend(
        [
            "",
            f"Total steps: {len(run.records)}",
            f"Total history rows: {len(final_history)}",
        ]
    )
    if final_operator is not None:
        summary_lines.extend(
            [
                f"Final quarter: {final_operator['quarter']}",
                f"Final lifecycle: {final_operator['lifecycle']}",
                f"Final HOME score: {final_operator['teams']['home']['score']}",
                f"Final AWAY score: {final_operator['teams']['away']['score']}",
                f"Final revision: {final_operator['revision']}",
            ]
        )
    (out_dir / "SUMMARY.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="current",
        help="Output directory name under .scratch/soccer-mode/football_golden/ "
        "(or an absolute/relative path). Default: current.",
    )
    args = parser.parse_args(argv)

    out_arg = Path(args.out)
    out_dir = out_arg if out_arg.is_absolute() else Path(__file__).resolve().parent / out_arg

    # SCOREBOARD_DATA_DIR, when set, names an isolated scratch root (never the
    # owner's live "Scoreboard Logs" folder -- see CONTEXT_FOR_AGENTS.md). A
    # fresh subdirectory is still made per run so a second invocation never
    # tries to *recover* the first run's game instead of starting clean.
    env_root = os.environ.get("SCOREBOARD_DATA_DIR")
    tmp_parent = Path(env_root) if env_root else Path(tempfile.gettempdir())
    tmp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scoreboard-golden-", dir=str(tmp_parent)) as tmp:
        data_root = Path(tmp) / "Scoreboard"
        run = GoldenRun(data_root)
        try:
            for index, (name, action) in enumerate(FOOTBALL_SCRIPT, start=1):
                run.step(index, name, action)
        finally:
            run.app.shutdown()
        write_output(run, out_dir)

    print(f"Wrote {len(run.records)} steps to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
