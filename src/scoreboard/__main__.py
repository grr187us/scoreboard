"""Command-line entry point: one action starts the game and both windows."""

from __future__ import annotations

import argparse

from scoreboard.host.app import RecoveryChoiceRequired, ScoreboardApplication, WindowHost
from scoreboard.infrastructure.persistence import InstanceAlreadyRunning


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open the operator and spectator scoreboard windows."
    )
    parser.add_argument(
        "--display-index",
        type=int,
        default=1,
        help="Zero-based Windows display index for the spectator window (default: 1).",
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
        "--auto-close-after-seconds",
        type=float,
        help="Test only: close the operator after this positive duration.",
    )
    parser.set_defaults(startup_choice=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        application = ScoreboardApplication()
    except InstanceAlreadyRunning as exc:
        # Refusing the second instance protects the database (R-004).
        print(str(exc))
        return 2

    host = WindowHost(
        application,
        initial_display_index=args.display_index,
        auto_close_after_seconds=args.auto_close_after_seconds,
    )
    try:
        host.run(startup_choice=args.startup_choice)
    except RecoveryChoiceRequired as exc:
        # Nothing is resumed and nothing is replaced until the operator says
        # which (P-005). The in-window recovery screen is not built yet, so the
        # choice is made here and the report is shown in full.
        report = exc.report
        print(report.message)
        if report.checkpoint_at:
            print(f"Last saved: {report.checkpoint_at}")
        print("Start again with --resume to continue that game, or --new-game to replace it.")
        application.shutdown(reason="recovery choice required")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
