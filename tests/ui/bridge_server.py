"""Test-only stdin/stdout transport to the real bridge, isolated from live data."""
import json
from pathlib import Path
import sys
import tempfile

from scoreboard.host.app import ScoreboardApplication
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.infrastructure.persistence import read_action_history


def main():
    with tempfile.TemporaryDirectory(prefix='scoreboard-keyboard-') as directory:
        app = ScoreboardApplication(resolve_paths(Path(directory)), diagnostics=NullDiagnostics(),
                                    monotonic_clock=lambda: 1000.0)
        bridge = app.start_new()
        try:
            for line in sys.stdin:
                request = json.loads(line)
                operation = request['op']
                if operation == 'reset':
                    bridge.command('new_game', {'confirmed': True})
                    bridge.command('set_quarter', {'label': '1st'})
                    result = bridge.get_snapshot()
                elif operation == 'command':
                    result = bridge.command(*request['args'])
                elif operation == 'history':
                    result = read_action_history(app.paths.database)
                else:
                    result = bridge.get_snapshot()
                print(json.dumps(result), flush=True)
        finally:
            app.shutdown()


if __name__ == '__main__':
    main()
