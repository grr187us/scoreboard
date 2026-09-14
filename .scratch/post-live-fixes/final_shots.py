"""Drive final_shots.cjs with real Python view models and every built-in preset.

Run from the repository root (Node must be on PATH):
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\final_shots.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.presentation.layout import preset_descriptors

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "evidence"


def main() -> int:
    fourth_state = GameState(
        lifecycle="IN_PROGRESS", quarter="4th", home_name="TIGERS", away_name="EAGLES",
        home_score=27, away_score=21, game_clock=ClockValue(0.0, False, 720.0),
        play_clock=ClockValue(25.0, False, 40.0), play_clock_cleared=False,
        down=3, distance=7, possession="home", ball_on=BallSpot("away", 35),
        home_timeouts=2, away_timeouts=1, revision=90,
    )
    fourth = spectator_view_model(fourth_state)
    final = spectator_view_model(replace(fourth_state, quarter="FINAL", lifecycle="FINAL", revision=91))
    payload = {
        "presets": [{"id": p["id"], "name": p["name"], "layout": p["layout"]} for p in preset_descriptors()],
        "fourth": fourth, "final": final, "out": str(OUT),
    }
    result = subprocess.run(
        ["node", str(Path(__file__).resolve().parent / "final_shots.cjs")],
        input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True, cwd=ROOT, timeout=180,
    )
    if result.returncode:
        print(result.stdout + result.stderr)
        return 1
    report = json.loads(result.stdout)
    failures = 0
    for entry in report:
        hidden_on_final = all(v["hidden"] and v["hasValue"] == "0" for k, v in entry["after"].items() if k != "quarter")
        # A widget the preset itself switches off (layoutVisible '0') stays off;
        # every other clock widget must be back with a value after FINAL.
        restored = all(v["hasValue"] == "1" and (v["hidden"] == (v["layoutVisible"] == "0"))
                       for k, v in entry["restored"].items() if k != "quarter")
        ok = hidden_on_final and restored and entry["after"]["quarter"] == "FINAL"
        failures += 0 if ok else 1
        print(("PASS  " if ok else "FAIL  ") + entry["preset"] + "  " + json.dumps(entry["after"]) + "  restored=" + json.dumps(entry["restored"]))
    print(f"\n{len(report) - failures}/{len(report)} presets hide both clocks and captions on FINAL and restore them after")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
