"""Temporary startup API. It exposes no live-game command surface."""

from typing import Any, Callable


class StartupBridge:
    def __init__(self, report: Callable[[], dict[str, Any]], choose: Callable[[str], None]):
        self._report = report
        self._choose = choose

    def get_recovery(self) -> dict[str, Any]:
        return self._report()

    def resume_recovered_game(self) -> None:
        self._choose("resume")

    def start_new_game(self) -> None:
        self._choose("new")
