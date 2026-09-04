"""One-process pywebview lifecycle proof for operator and spectator windows."""

from __future__ import annotations

from pathlib import Path
from threading import Event, RLock
from typing import Any

import webview

from scoreboard.host.displays import enumerate_displays, selected_screen


def _page(name: str) -> str:
    return (Path(__file__).resolve().parent.parent / "views" / name / "index.html").read_text(
        encoding="utf-8"
    )


class WindowHost:
    """Own both proof windows without owning any scoreboard state."""

    def __init__(
        self, initial_display_index: int, auto_close_after_seconds: float | None = None
    ) -> None:
        self.initial_display_index = initial_display_index
        if auto_close_after_seconds is not None and auto_close_after_seconds <= 0:
            raise ValueError("--auto-close-after-seconds must be greater than zero")
        self.auto_close_after_seconds = auto_close_after_seconds
        self.operator_window: webview.Window | None = None
        self.spectator_window: webview.Window | None = None
        self.status = "STARTING"
        self._lock = RLock()

    def run(self) -> None:
        self.operator_window = webview.create_window(
            "Scoreboard operator proof",
            html=_page("operator"),
            js_api=HostApi(self),
            width=720,
            height=480,
        )
        self.operator_window.events.loaded += self._operator_loaded
        self.operator_window.events.closing += self._operator_closing
        if self.auto_close_after_seconds is None:
            webview.start()
        else:
            webview.start(self._close_after_delay, (self.auto_close_after_seconds,))

    def _close_after_delay(self, seconds: float) -> None:
        Event().wait(seconds)
        if self.operator_window is not None:
            self.operator_window.destroy()

    def _operator_loaded(self) -> None:
        self.open_spectator(self.initial_display_index)

    def _operator_closing(self) -> None:
        with self._lock:
            self.status = "SHUTTING DOWN"
            spectator = self.spectator_window
            self.spectator_window = None
        if spectator is not None:
            spectator.destroy()

    def displays(self) -> list[dict[str, Any]]:
        return [
            {
                "index": display.index,
                "label": display.label,
            }
            for display in enumerate_displays(list(webview.screens))
        ]

    def open_spectator(self, display_index: int) -> dict[str, str]:
        """Open a new borderless fullscreen spectator placeholder on one display."""
        screens = list(webview.screens)
        screen = selected_screen(screens, display_index)
        if screen is None:
            return self._set_status(f"DISPLAY NOT FOUND: Display {display_index + 1}")

        with self._lock:
            previous_spectator = self.spectator_window
            self.spectator_window = None
        if previous_spectator is not None:
            previous_spectator.destroy()

        spectator = webview.create_window(
            "Scoreboard spectator proof",
            html=_page("spectator"),
            screen=screen,
            fullscreen=True,
            frameless=True,
            resizable=False,
            focus=False,
        )
        if spectator is None:
            return self._set_status("DISPLAY CLOSED: spectator window could not be created")
        spectator.events.closed += self._spectator_closed
        with self._lock:
            self.spectator_window = spectator

        return self._set_status(f"DISPLAY OPEN: Display {display_index + 1} (fullscreen)")

    def toggle_spectator_fullscreen(self) -> dict[str, str]:
        with self._lock:
            spectator = self.spectator_window
        if spectator is None:
            return self._set_status("DISPLAY CLOSED: Select a display and reopen it")
        spectator.toggle_fullscreen()
        return self._set_status("DISPLAY OPEN: fullscreen toggled")

    def _spectator_closed(self, window: webview.Window) -> None:
        with self._lock:
            if self.spectator_window is not window:
                return
            self.spectator_window = None
        self._set_status("DISPLAY CLOSED: Select a display and reopen it")

    def _set_status(self, message: str) -> dict[str, str]:
        with self._lock:
            self.status = message
            operator = self.operator_window
        if operator is not None and operator.events.loaded.is_set():
            operator.evaluate_js(f"window.setHostStatus({message!r})")
        return {"message": message}


class HostApi:
    """Small, display-only JavaScript bridge for the proof page."""

    def __init__(self, host: WindowHost) -> None:
        self._host = host

    def get_displays(self) -> list[dict[str, Any]]:
        return self._host.displays()

    def get_status(self) -> dict[str, str]:
        return {"message": self._host.status}

    def open_spectator(self, display_index: int) -> dict[str, str]:
        return self._host.open_spectator(display_index)

    def toggle_spectator_fullscreen(self) -> dict[str, str]:
        return self._host.toggle_spectator_fullscreen()
