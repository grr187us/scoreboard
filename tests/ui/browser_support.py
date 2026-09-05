"""Development-only browser runner; no browser tooling ships with the app."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run_browser(script, payload):
    env = os.environ.copy()
    # Prefer normal developer configuration; the desktop bundle is a fallback.
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
    if not env.get('NODE_PATH') and bundled.is_dir():
        env['NODE_PATH'] = str(bundled)
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('UI tests require Node and Playwright (development only). See tests/README.md.')
    result = subprocess.run([node, str(ROOT / 'tests/ui' / script)],
                            input=json.dumps(payload), text=True, encoding='utf-8',
                            capture_output=True, cwd=ROOT, env=env, timeout=90)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)
