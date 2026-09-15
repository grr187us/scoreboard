"""The sport picker: the first window an interactive launch opens.

Mirrors :mod:`scoreboard.host.startup` in shape -- a small, temporary bridge
with no live-game command surface -- but one step earlier: it decides *which*
application (football or soccer) gets built at all, before that sport's own
startup/recovery screen (``views/startup`` or ``views/soccer_startup``) ever
runs (spec section 2.5). ``SportPickerBridge`` is deliberately as narrow as
:class:`~scoreboard.host.startup.StartupBridge`: ``choose_sport`` and
``last_sport``, nothing else.

Threading (read this before changing ``_choose_sport`` or ``run``):
pywebview runs exactly one event loop per process, started once by
``webview.start()``. :meth:`SportPickerHost.run` creates the picker window and
is the one call in this whole feature that starts that loop. The picker's
``choose_sport`` callback -- :meth:`SportPickerHost._choose_sport` -- runs on
webview's own UI thread *while that loop is already spinning* (a pywebview
``js_api`` method always does). That is exactly why
:meth:`~scoreboard.host.app.WindowHost.run` was split into
:meth:`~scoreboard.host.app.WindowHost.begin` (window creation only, no
``webview.start()``) and ``run`` (``begin()`` + ``webview.start()`` +
shutdown, spec section 2.3f): calling ``begin()`` from inside
``_choose_sport`` opens the chosen sport's operator (or startup) window on the
*same already-running* loop instead of trying to start a second one, which
pywebview does not support. When every window this process opened is later
closed, the single ``webview.start()`` call made here (not
``WindowHost.run()``) returns, and :meth:`SportPickerHost.run` shuts down
whichever application was built -- ``WindowHost.run()`` itself is never
called in this path, so it keeps calling ``webview.start()`` exactly once,
unmodified, for every existing football call site.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Final

import webview

from scoreboard.host import preflight
from scoreboard.host.app import ScoreboardApplication, WindowHost, view_url
from scoreboard.infrastructure import config
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.infrastructure.persistence import InstanceAlreadyRunning

#: The ``config.json`` section remembering the last sport chosen (spec 2.5).
SPORT_SECTION: Final[str] = "sport"
SPORTS: Final[tuple[str, str]] = ("football", "soccer")


def read_last_sport(paths: ScoreboardPaths) -> str | None:
    """The last sport chosen, or ``None``. Never guesses; a bad file reads as
    "nothing remembered", the same contract every preference in
    ``infrastructure.config`` makes.
    """

    section = config.read_section(paths, SPORT_SECTION)
    if not isinstance(section, dict):
        return None
    value = section.get("last")
    return value if value in SPORTS else None


def write_last_sport(paths: ScoreboardPaths, sport: str) -> bool:
    """Remember ``sport`` as the picker's next pre-focused button."""

    return config.write_section(paths, SPORT_SECTION, {"last": sport})


class SportPickerBridge:
    """The picker window's tiny JSON API. No live-game command surface."""

    def __init__(
        self,
        choose: Callable[[str], None],
        last_sport: Callable[[], str | None],
    ) -> None:
        self._choose = choose
        self._last_sport = last_sport

    def choose_sport(self, sport: Any) -> None:
        """The operator pressed FOOTBALL or SOCCER. Never auto-called."""

        if sport not in SPORTS:
            raise ValueError("Choose Football or Soccer.")
        self._choose(sport)

    def last_sport(self) -> str | None:
        """Which button to pre-focus. The page never chooses on its own."""

        return self._last_sport()


class SportPickerHost:
    """Opens "Choose sport", then hands off to that sport's :class:`WindowHost`.

    See the module docstring for why this class -- not
    :meth:`~scoreboard.host.app.WindowHost.run` -- is the one thing in the
    soccer-mode feature that calls ``webview.start()``.
    """

    def __init__(
        self,
        root_paths: ScoreboardPaths,
        *,
        display_index: int | None = None,
        auto_close_after_seconds: float | None = None,
    ) -> None:
        if auto_close_after_seconds is not None and auto_close_after_seconds <= 0:
            raise ValueError("--auto-close-after-seconds must be greater than zero")
        self._root_paths = root_paths.ensure()
        self._display_index = display_index
        self._auto_close_after_seconds = auto_close_after_seconds
        self._picker_window: Any = None
        self.host: WindowHost | None = None

    def run(self) -> None:
        self._picker_window = webview.create_window(
            "Choose sport",
            url=view_url("sport_picker"),
            js_api=SportPickerBridge(self._choose_sport, self._last_sport),
            width=520,
            height=360,
            min_size=(520, 360),
            resizable=False,
        )
        try:
            if self._auto_close_after_seconds is None:
                webview.start()
            else:
                webview.start(self._close_after_delay, (self._auto_close_after_seconds,))
        finally:
            if self.host is not None:
                self.host.application.shutdown()

    def _last_sport(self) -> str | None:
        return read_last_sport(self._root_paths)

    def _choose_sport(self, sport: str) -> None:
        """Build the chosen application and open its window on this same loop.

        ``InstanceAlreadyRunning`` from either constructor is reported exactly
        as ``__main__`` reports it today, and the picker stays open so the
        operator can choose the other sport or quit (spec 2.5).
        """

        if self.host is not None:
            return  # A choice was already made; a double click does nothing.
        write_last_sport(self._root_paths, sport)
        application: Any
        try:
            if sport == "football":
                application = ScoreboardApplication(self._root_paths)
            else:
                # Lazy: agent A/B's soccer host module, imported only when
                # Soccer is actually chosen, so a football-only launch never
                # needs it to exist.
                from scoreboard.host.soccer_app import SoccerApplication

                application = SoccerApplication(self._root_paths)
        except InstanceAlreadyRunning as exc:
            preflight.report("Scoreboard is already running", str(exc))
            return

        host = WindowHost(
            application,
            initial_display_index=self._display_index,
            auto_close_after_seconds=self._auto_close_after_seconds,
        )
        self.host = host
        host.begin(None, interactive=True)
        window, self._picker_window = self._picker_window, None
        if window is not None:
            window.destroy()

    def _close_after_delay(self, seconds: float) -> None:
        threading.Event().wait(seconds)
        if self.host is not None:
            window = self.host.operator_window or self.host.startup_window
            if window is not None:
                window.destroy()
                return
        if self._picker_window is not None:
            self._picker_window.destroy()


__all__ = [
    "SPORTS",
    "SPORT_SECTION",
    "SportPickerBridge",
    "SportPickerHost",
    "read_last_sport",
    "write_last_sport",
]
