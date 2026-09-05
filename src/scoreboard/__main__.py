"""Command-line entry point: one action starts the game and both windows.

A packaged build is launched from a shortcut with no console (W-004), so every
path that used to end in ``print`` and a non-zero exit now goes through
``host.preflight.report``: in a checkout it prints, and in a packaged build it
opens a message box. A scoreboard that exits silently when double-clicked is
indistinguishable from a broken shortcut, which is the worst thing it could do
twenty minutes before kickoff.
"""

from __future__ import annotations

import argparse

from scoreboard.domain.state import APP_VERSION
from scoreboard.host import preflight
from scoreboard.host.app import RecoveryChoiceRequired, ScoreboardApplication, WindowHost
from scoreboard.infrastructure.persistence import InstanceAlreadyRunning


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open the operator and spectator scoreboard windows."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"scoreboard {APP_VERSION}",
    )
    parser.add_argument(
        "--display-index",
        type=int,
        default=None,
        help=(
            "Force a zero-based Windows display index for the spectator window. "
            "The default is to use the display saved in config.json, and to open "
            "nothing rather than cover the operator's screen when it is missing."
        ),
    )
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--resume",
        dest="startup_choice",
        action="store_const",
        const="resume",
        help="Continue the recovered game with every clock stopped.",
    )
    choice.add_argument(
        "--new-game",
        dest="startup_choice",
        action="store_const",
        const="new",
        help="Start a clean game, archiving the previous one.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report the runtime prerequisites and the data folder, then exit.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="With --check, also show the report in a dialog for a shortcut.",
    )
    parser.add_argument(
        "--choose-data-folder",
        action="store_true",
        help="Pick where the game and its logs are saved, then exit.",
    )
    parser.add_argument(
        "--auto-close-after-seconds",
        type=float,
        help="Test only: close the operator after this positive duration.",
    )
    parser.set_defaults(startup_choice=None)
    return parser.parse_args(argv)


def run_check(show: bool = False) -> int:
    """Answer 'is this laptop ready?' without touching the database.

    This never opens a dialog on its own. A readiness check is run from a
    terminal by a technician and from the build script by a machine, and a
    modal dialog would hang both; a packaged build has no console, so the
    report is also written to a file that survives the process. ``--show`` adds
    the dialog for the one case that wants it: a double-clickable shortcut.
    """

    from scoreboard.infrastructure.paths import resolve_paths

    lines = [f"scoreboard {APP_VERSION}"]
    problems = 0
    for prerequisite in preflight.check_prerequisites():
        lines.append(prerequisite.message())
        problems += 0 if prerequisite.satisfied else 1

    written_to: str | None = None
    try:
        paths = resolve_paths().ensure()
        lines.append(f"Data folder: {paths.root}")
        destination = paths.log_directory / "readiness.txt"
        destination.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        written_to = str(destination)
    except Exception as exc:  # noqa: BLE001 - reported, not raised, in a check
        lines.append(f"Data folder could not be resolved: {exc}")
        problems += 1

    report = "\n\n".join(lines)
    if written_to is not None:
        report += f"\n\nSaved to: {written_to}"
    if preflight.has_console():
        print(report)
    if show:
        preflight.report("Scoreboard readiness", report)
    return 0 if problems == 0 else 1


def run_choose_data_folder() -> int:
    """Open the folder picker with no game running, then exit.

    This is the setup path: a technician runs it once before a season, from a
    terminal or from a second shortcut, and never has to touch an environment
    variable. It starts no service, takes no instance lock, and opens no
    database, so it is safe to run at any time.
    """

    from scoreboard.host.folders import choose_data_folder

    choice = choose_data_folder()
    # report() prints when there is a console and opens a dialog when there is
    # not, which is exactly right here: the operator asked for a dialog anyway.
    preflight.report("Scoreboard data folder", choice.message)
    return 0 if choice.outcome in ("chosen", "cancelled") else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.choose_data_folder:
        return run_choose_data_folder()
    if args.check:
        return run_check(show=args.show)

    # WebView2 is the one prerequisite the package cannot carry. Saying so is
    # far better than opening no window and leaving no explanation (W-002).
    webview2 = preflight.check_webview2()
    if not webview2.satisfied:
        preflight.report("Scoreboard cannot start", webview2.message())
        return 4

    try:
        application = ScoreboardApplication()
    except InstanceAlreadyRunning as exc:
        # Refusing the second instance protects the database (R-004).
        preflight.report("Scoreboard is already running", str(exc))
        return 2

    host = WindowHost(
        application,
        initial_display_index=args.display_index,
        auto_close_after_seconds=args.auto_close_after_seconds,
    )
    try:
        host.run(startup_choice=args.startup_choice, interactive=True)
    except RecoveryChoiceRequired as exc:
        # Defensive fallback for a non-interactive host adapter.
        report = exc.report
        lines = [report.message]
        if report.checkpoint_at:
            lines.append(f"Last saved: {report.checkpoint_at_local or report.checkpoint_at}")
        lines.append(
            "Start again with --resume to continue that game, "
            "or --new-game to replace it."
        )
        preflight.report("Scoreboard needs a recovery choice", "\n\n".join(lines))
        application.shutdown(reason="recovery choice required")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
