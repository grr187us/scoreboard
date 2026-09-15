"""Diff two golden-run output directories, file by file.

Usage::

    ./.venv/Scripts/python.exe diff_golden.py <dir_a> <dir_b>

Exits 0 if every file that exists in either directory is byte-identical
(after JSON-normalizing whitespace is irrelevant since golden_run.py always
writes pretty, sorted-key JSON with a trailing newline), exits 1 and prints a
unified diff for every file that differs, is missing, or was added.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def diff_dirs(dir_a: Path, dir_b: Path) -> int:
    names_a = {path.name for path in dir_a.glob("*") if path.is_file()}
    names_b = {path.name for path in dir_b.glob("*") if path.is_file()}
    all_names = sorted(names_a | names_b)

    differences = 0
    for name in all_names:
        path_a = dir_a / name
        path_b = dir_b / name
        if name not in names_a:
            print(f"ONLY IN {dir_b}: {name}")
            differences += 1
            continue
        if name not in names_b:
            print(f"ONLY IN {dir_a}: {name}")
            differences += 1
            continue
        lines_a = _read_lines(path_a)
        lines_b = _read_lines(path_b)
        if lines_a == lines_b:
            continue
        differences += 1
        diff = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=str(path_a),
            tofile=str(path_b),
        )
        sys.stdout.writelines(diff)
        print()

    if differences == 0:
        print(f"No differences: {dir_a} == {dir_b} ({len(all_names)} files compared)")
    else:
        print(f"{differences} file(s) differ or are missing between {dir_a} and {dir_b}")
    return 1 if differences else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dir_a", type=Path)
    parser.add_argument("dir_b", type=Path)
    args = parser.parse_args(argv)

    dir_a = args.dir_a if args.dir_a.is_absolute() else Path(__file__).resolve().parent / args.dir_a
    dir_b = args.dir_b if args.dir_b.is_absolute() else Path(__file__).resolve().parent / args.dir_b

    for path in (dir_a, dir_b):
        if not path.is_dir():
            print(f"Not a directory: {path}", file=sys.stderr)
            return 2

    return diff_dirs(dir_a, dir_b)


if __name__ == "__main__":
    raise SystemExit(main())
