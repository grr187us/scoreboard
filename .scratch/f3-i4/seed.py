"""Emit one realistic operator view model for the F3/I4 sizing check.

Development tool, not part of the suite. It uses the real bridge so the shape
is whatever the application actually produces today, then stresses the two
things this measurement is about: a long LAST label with a deep undo history
behind it, and the longest crowd message.
"""
import json
import tempfile
from pathlib import Path

from scoreboard.host.app import ScoreboardApplication
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths

with tempfile.TemporaryDirectory(prefix="scoreboard-measure-") as directory:
    app = ScoreboardApplication(
        resolve_paths(Path(directory)),
        diagnostics=NullDiagnostics(),
        monotonic_clock=lambda: 1000.0,
    )
    bridge = app.start_new()
    try:
        bridge.command("new_game", {"confirmed": True})
        # Longest names F-010 allows, so the board columns are at their widest.
        bridge.command("set_team_name", {"team": "home", "name": "A" * 24, "confirmed": True})
        bridge.command("set_team_name", {"team": "away", "name": "B" * 24, "confirmed": True})
        bridge.command("set_quarter", {"label": "1st", "confirmed": True})
        for _ in range(6):
            bridge.command("add_score", {"team": "home", "points": 6})
        bridge.command("set_down", {"value": 3})
        bridge.command("set_distance", {"value": 7})
        bridge.command("set_possession", {"team": "home"})
        view = bridge.get_snapshot()
    finally:
        app.shutdown()

# The crowd row's resting state is "no message"; its widest state is the
# longest label plus a running countdown, which is what we want to measure.
view["status"] = {
    "label": "TIMEOUT",
    "active": True,
    "display": "TIMEOUT",
    "clock_display": "1:00",
    "clock": {"seconds": 60.0, "running": True, "display": "1:00", "status": "RUNNING"},
}
print(json.dumps(view))
