"""Development-only browser runner; no browser tooling ships with the app."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def run_browser(script, payload):
    env = os.environ.copy()
    # Resolution order: the project-local `npm ci` install (ROOT/node_modules,
    # which `require('playwright')` finds by walking up from tests/ui/ with no
    # help), then an explicit NODE_PATH, then the Codex desktop bundle as a
    # last-resort fallback for a machine that has never run `npm ci`.
    local = ROOT / 'node_modules' / 'playwright'
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
    if not local.is_dir() and not env.get('NODE_PATH') and bundled.is_dir():
        env['NODE_PATH'] = str(bundled)
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('UI tests require Node and Playwright (development only): '
                           'install Node.js LTS, then run `npm ci` in the repository root. '
                           'See tests/README.md.')
    if not local.is_dir() and not env.get('NODE_PATH'):
        raise RuntimeError('Playwright is not installed: run `npm ci` in the repository root '
                           '(development only). See tests/README.md.')
    result = subprocess.run([node, str(ROOT / 'tests/ui' / script)],
                            input=json.dumps(payload), text=True, encoding='utf-8',
                            capture_output=True, cwd=ROOT, env=env, timeout=90)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)
