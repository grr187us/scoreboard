"""Test-only stdin/stdout transport to the real soccer bridge, isolated data.

Copies ``tests/ui/bridge_server.py``'s stdin JSON protocol (one JSON request
per line, one JSON response per line) but serves the soccer operator page
against the real ``SoccerBridge`` (``scoreboard.host.soccer_bridge``, agent
B's module) instead of football's ``ScoreboardBridge``.

Ops:
  - ``snapshot``: return ``bridge.get_snapshot()``.
  - ``command``: ``bridge.command(*args)``.
  - ``reset``: start a new game and set the period to ``1st`` (soccer's
    equivalent of football's PRE -> 1st quarter reset), then return the
    snapshot.
  - ``pregame``: start a new game and stop there (period stays ``PRE``).
  - ``seed``: put the game into a given period / score / shootout state
    through ordinary, validated commands rather than by touching internal
    state directly -- so a seeded fixture can never diverge from what a real
    operator session could reach. Payload (``request['seed']``):
      {"period": "2nd", "home_score": 2, "away_score": 1,
       "shootout_first_kicker": "home", "shootout_kicks": [["home", true], ...]}
    All keys optional; period advances via period_forward/set_period.
  - ``history``: read the action-history rows (soccer's own store).
"""
import json
from pathlib import Path
import sys
import tempfile

from scoreboard.host.soccer_app import SoccerApplication
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.infrastructure.persistence import read_action_history

# The period ladder a `reset`/`seed` op walks through with `set_period`
# (spec 3.1's PERIOD_LABELS, mirrored here only for a deterministic test
# fixture -- not imported from scoreboard.domain.soccer.state so this file
# does not fail to import while that module is still landing).
_PERIOD_ORDER = ("PRE", "1st", "HALF", "2nd", "OT1", "OT2", "SHOOTOUT", "FINAL")


def _set_period(bridge, label):
    revision = bridge.get_snapshot()["revision"]
    result = bridge.command("set_period", {"label": label, "confirmed": True}, revision)
    if not result.get("accepted") and result.get("confirmation_required"):
        revision = result["view"]["revision"]
        result = bridge.command(
            "set_period", {"label": label, "confirmed": True}, revision
        )
    return result


def _seed(bridge, spec):
    bridge.command("new_game", {"confirmed": True})
    # Team names are pregame-only (spec 3.2), so rename before advancing the
    # period.
    for team, key in (("home", "home_name"), ("away", "away_name")):
        if key in spec:
            revision = bridge.get_snapshot()["revision"]
            bridge.command("set_team_name", {"team": team, "name": spec[key]}, revision)
    period = spec.get("period")
    if period:
        _set_period(bridge, period)
    for team, key in (("home", "home_score"), ("away", "away_score")):
        if key in spec:
            revision = bridge.get_snapshot()["revision"]
            bridge.command("set_score", {"team": team, "value": spec[key]}, revision)
    first_kicker = spec.get("shootout_first_kicker")
    if first_kicker:
        revision = bridge.get_snapshot()["revision"]
        bridge.command("set_shootout_first_kicker", {"team": first_kicker}, revision)
    for team, made in spec.get("shootout_kicks", []):
        revision = bridge.get_snapshot()["revision"]
        bridge.command("shootout_kick", {"team": team, "made": made}, revision)
    return bridge.get_snapshot()


def main():
    with tempfile.TemporaryDirectory(prefix="scoreboard-soccer-ui-") as directory:
        app = SoccerApplication(
            resolve_paths(Path(directory)), diagnostics=NullDiagnostics(),
            monotonic_clock=lambda: 1000.0,
        )
        bridge = app.start_new()
        try:
            for line in sys.stdin:
                request = json.loads(line)
                operation = request["op"]
                if operation == "reset":
                    bridge.command("new_game", {"confirmed": True})
                    _set_period(bridge, "1st")
                    result = bridge.get_snapshot()
                elif operation == "pregame":
                    bridge.command("new_game", {"confirmed": True})
                    result = bridge.get_snapshot()
                elif operation == "seed":
                    result = _seed(bridge, request.get("seed", {}))
                elif operation == "command":
                    result = bridge.command(*request["args"])
                elif operation == "history":
                    result = read_action_history(app.paths.database)
                else:
                    result = bridge.get_snapshot()
                print(json.dumps(result), flush=True)
        finally:
            app.shutdown()


if __name__ == "__main__":
    main()
