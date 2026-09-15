"""SHA-256 fingerprints of every file football depends on, for a frozen-code guard.

Football is frozen for the soccer-mode work (see
``.scratch/soccer-mode/CONTEXT_FOR_AGENTS.md``): nothing under ``src/``,
``tests/``, ``tools/``, or ``docs/`` may change while a research/design agent
is working. This script is the tripwire.

Covers, relative to the repository root:

* every file under ``src/scoreboard/`` except ``__pycache__``;
* ``tools/build_package.py`` and ``tools/scoreboard.spec``;
* ``pyproject.toml``;
* every file under ``tests/``.

Usage::

    ./.venv/Scripts/python.exe frozen_hashes.py --write hashes_all.json
    ./.venv/Scripts/python.exe frozen_hashes.py --check hashes_all.json

``--write`` computes and stores ``{relative_path: sha256}`` (POSIX-style
relative paths, sorted, pretty-printed). ``--check`` recomputes the same map
and reports:

* ``CHANGED <path>`` -- a file the map recorded has a different hash now;
* ``REMOVED <path>`` -- a file the map recorded no longer exists;
* ``ADDED <path>`` -- a file exists now that the map never recorded
  (informational only -- a new file cannot itself prove football regressed).

Exit code is 1 if any file changed or was removed, 0 otherwise (added files
never fail the check on their own).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Directories (relative to the repo root) whose files are covered wholesale.
_TREE_ROOTS: tuple[str, ...] = ("src/scoreboard", "tests")

#: Individual files covered in addition to the trees above.
_EXTRA_FILES: tuple[str, ...] = (
    "tools/build_package.py",
    "tools/scoreboard.spec",
    "pyproject.toml",
)

_EXCLUDED_DIR_NAMES = {"__pycache__"}


def _iter_tree_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_hashes(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """Return ``{posix relative path: sha256 hex digest}`` for every covered file."""

    hashes: dict[str, str] = {}
    for tree in _TREE_ROOTS:
        root = repo_root / tree
        if not root.is_dir():
            continue
        for path in _iter_tree_files(root):
            relative = path.relative_to(repo_root).as_posix()
            hashes[relative] = _sha256(path)
    for extra in _EXTRA_FILES:
        path = repo_root / extra
        if path.is_file():
            hashes[extra] = _sha256(path)
    return hashes


def write_hashes(out_path: Path, repo_root: Path = REPO_ROOT) -> dict[str, str]:
    hashes = compute_hashes(repo_root)
    out_path.write_text(
        json.dumps(hashes, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return hashes


def check_hashes(in_path: Path, repo_root: Path = REPO_ROOT) -> int:
    """Print CHANGED/ADDED/REMOVED lines; return 1 if anything changed/removed."""

    recorded: dict[str, str] = json.loads(in_path.read_text(encoding="utf-8"))
    current = compute_hashes(repo_root)

    changed = sorted(
        path for path in recorded
        if path in current and current[path] != recorded[path]
    )
    removed = sorted(path for path in recorded if path not in current)
    added = sorted(path for path in current if path not in recorded)

    for path in changed:
        print(f"CHANGED {path}")
    for path in removed:
        print(f"REMOVED {path}")
    for path in added:
        print(f"ADDED {path}")

    if not (changed or removed or added):
        print(f"No changes: {len(current)} files match {in_path}")

    return 1 if (changed or removed) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", type=Path, metavar="JSON", help="Write the current hash map here.")
    group.add_argument("--check", type=Path, metavar="JSON", help="Check the tree against this hash map.")
    args = parser.parse_args(argv)

    if args.write is not None:
        hashes = write_hashes(args.write)
        print(f"Wrote {len(hashes)} file hashes to {args.write}")
        return 0

    return check_hashes(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
