"""Fail when a Markdown file links to a repository file that does not exist.

Development-only. The roadmap has recorded a "relative Markdown file-link
check" as release evidence since Task 8; this is that check as a script so CI
can run it. Only relative file links are inspected: URLs with a scheme,
``mailto:`` links, and bare ``#anchor`` links are ignored, and a trailing
``#anchor`` or ``:line`` suffix is stripped before the path is resolved
against the linking file's own directory.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.venv', 'venv', 'node_modules', '.git', 'build', 'dist', '.scratch'}
LINK = re.compile(r'(?<!\\)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
SCHEME = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*:')


def markdown_files(root: Path):
    for path in sorted(root.rglob('*.md')):
        if SKIP_DIRS.isdisjoint(path.relative_to(root).parts):
            yield path


def broken_links(path: Path):
    text = path.read_text(encoding='utf-8', errors='replace')
    for match in LINK.finditer(text):
        target = match.group(1).strip('<>')
        if not target or target.startswith('#') or SCHEME.match(target):
            continue
        clean = target.split('#', 1)[0]
        clean = re.sub(r':\d+(?::\d+)?$', '', clean)
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        if not resolved.exists():
            line = text.count('\n', 0, match.start()) + 1
            yield line, target


def main(argv=None) -> int:
    root = Path(argv[0]).resolve() if argv else ROOT
    failures = 0
    checked = 0
    for path in markdown_files(root):
        checked += 1
        for line, target in broken_links(path):
            failures += 1
            print(f'{path.relative_to(root).as_posix()}:{line}: broken link -> {target}')
    print(f'{checked} Markdown files checked, {failures} broken relative link(s).')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
