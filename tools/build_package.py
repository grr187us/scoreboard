"""Build and verify the offline Windows package (Task 11, W-001 to W-006).

Run from the repository root, in the virtual environment that has the pinned
build extra installed::

    .\\.venv\\Scripts\\python.exe -m pip install -e ".[build]"
    .\\.venv\\Scripts\\python.exe tools\\build_package.py

It cleans stale output, runs PyInstaller against ``tools/scoreboard.spec``, and
then checks the result rather than trusting that the build succeeded: an
executable that exists but is missing its stylesheets would produce a blank
scoreboard on the wall, and nothing in a PyInstaller exit code says otherwise.

The verification deliberately stops short of launching the windows. Opening
WebView2, placing the spectator window, and running a game are the manual
release checks in ``docs/PACKAGING.md``; they need a person and a second
display, which a build script has neither of.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tools" / "scoreboard.spec"
DIST = ROOT / "dist"
WORK = ROOT / "build"
PACKAGE = DIST / "Scoreboard"

#: Files that must exist in the built package. Each one is something a window
#: loads; a missing stylesheet or script is invisible until game day.
REQUIRED_FILES: tuple[str, ...] = (
    "Scoreboard.exe",
    "_internal/scoreboard/views/operator/index.html",
    "_internal/scoreboard/views/operator/operator.css",
    "_internal/scoreboard/views/operator/operator.js",
    "_internal/scoreboard/views/operator/keyboard.js",
    "_internal/scoreboard/views/field_assistant/index.html",
    "_internal/scoreboard/views/field_assistant/field_assistant.css",
    "_internal/scoreboard/views/field_assistant/field_assistant.js",
    "_internal/scoreboard/views/layout/index.html",
    "_internal/scoreboard/views/layout/layout.css",
    "_internal/scoreboard/views/layout/layout.js",
    "_internal/scoreboard/views/layout/editor-state.js",
    "_internal/scoreboard/views/layout/editor-canvas.js",
    "_internal/scoreboard/views/layout/editor-panels.js",
    "_internal/scoreboard/views/spectator/index.html",
    "_internal/scoreboard/views/spectator/spectator.css",
    "_internal/scoreboard/views/spectator/spectator.js",
    "_internal/scoreboard/views/startup/index.html",
    "_internal/scoreboard/views/startup/startup.js",
    "_internal/scoreboard/views/shared/base.css",
    "_internal/scoreboard/views/shared/board.css",
    "_internal/scoreboard/views/shared/board.js",
    "_internal/scoreboard/views/shared/render.js",
)


def application_version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from scoreboard.domain.state import APP_VERSION

    return APP_VERSION


def clean() -> None:
    for directory in (WORK, PACKAGE):
        if directory.exists():
            shutil.rmtree(directory)


def build() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(WORK),
            str(SPEC),
        ],
        cwd=ROOT,
        check=True,
    )


def verify(version: str) -> list[str]:
    """Check the built folder against what the application actually loads."""

    problems: list[str] = []
    if not PACKAGE.is_dir():
        return [f"the package folder was not created: {PACKAGE}"]

    for relative in REQUIRED_FILES:
        path = PACKAGE / relative
        if not path.is_file():
            problems.append(f"missing from the package: {relative}")
        elif path.stat().st_size == 0:
            problems.append(f"empty in the package: {relative}")

    # The package must be self-contained: no page may reach for a network
    # resource, because the stadium laptop has no internet during a game
    # (R-001, W-002).
    views = PACKAGE / "_internal" / "scoreboard" / "views"
    if views.is_dir():
        for page in views.rglob("*"):
            if page.suffix not in (".html", ".css", ".js"):
                continue
            text = page.read_text(encoding="utf-8", errors="replace")
            for marker in ("http://", "https://", "//cdn"):
                if marker in text:
                    problems.append(f"{page.name} references a remote resource: {marker}")

    # The readiness check exercises the frozen executable end to end without
    # opening a window: it imports the application, resolves the data folder,
    # and reads the WebView2 registry entry. A windowed build has no stdout, so
    # the report is read from the file the check writes rather than from the
    # pipe, which would always be empty. Remove any earlier report first, so a
    # stale file from a previous build cannot make this one look verified.
    stale = readiness_path()
    if stale is not None and stale.is_file():
        stale.unlink()

    try:
        result = subprocess.run(
            [str(PACKAGE / "Scoreboard.exe"), "--check"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        problems.append(
            "Scoreboard.exe --check did not exit within 120 seconds. A packaged "
            "build must never block on a dialog in an automated check."
        )
        return problems

    readiness = readiness_report()
    if result.returncode != 0:
        problems.append(
            f"Scoreboard.exe --check exited {result.returncode}. "
            f"Report: {readiness or '(none written)'}"
        )
    elif readiness is None:
        problems.append(
            "Scoreboard.exe --check exited 0 but wrote no readiness report, so "
            "the frozen build's data folder could not be confirmed."
        )
    elif version not in readiness:
        problems.append(
            f"the packaged build reported a different version than {version}: {readiness}"
        )
    return problems


def readiness_path() -> Path | None:
    """Where the frozen ``--check`` writes its report, or ``None`` if unknown."""

    sys.path.insert(0, str(ROOT / "src"))
    from scoreboard.infrastructure.paths import resolve_paths

    try:
        return resolve_paths().log_directory / "readiness.txt"
    except Exception:  # noqa: BLE001 - the caller reports this as a problem
        return None


def readiness_report() -> str | None:
    """The report the frozen ``--check`` wrote, read back from the data folder."""

    path = readiness_path()
    if path is None or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Check an existing dist/Scoreboard folder without rebuilding.",
    )
    arguments = parser.parse_args()

    version = application_version()
    if not arguments.verify_only:
        print(f"Building Scoreboard {version} ...")
        clean()
        build()

    problems = verify(version)
    if problems:
        print(f"\nPackage verification FAILED ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    total = sum(path.stat().st_size for path in PACKAGE.rglob("*") if path.is_file())
    files = sum(1 for path in PACKAGE.rglob("*") if path.is_file())
    print(
        f"\nPackage verified: {PACKAGE}\n"
        f"  version {version}, {files} files, {total / 1_000_000:.1f} MB\n"
        f"  manual release checks remain: see docs/PACKAGING.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
