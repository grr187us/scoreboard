"""Command-line entry point for the Phase 2 Task 1 runtime proof."""

from __future__ import annotations

import argparse

from scoreboard.host.app import WindowHost


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open the operator and selected-display spectator proof windows."
    )
    parser.add_argument(
        "--display-index",
        type=int,
        default=1,
        help="Zero-based Windows display index for the spectator window (default: 1).",
    )
    parser.add_argument(
        "--auto-close-after-seconds",
        type=float,
        help="Proof-test only: close the operator after this positive duration.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    WindowHost(
        initial_display_index=args.display_index,
        auto_close_after_seconds=args.auto_close_after_seconds,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
