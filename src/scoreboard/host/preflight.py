"""Runtime prerequisites, and how to tell an operator about a fatal problem.

A packaged build has no console (W-002, W-004): ``print`` reaches nobody, so a
missing prerequisite would otherwise look like an application that does nothing
when double-clicked. This module answers two questions:

* is the Microsoft Edge WebView2 Runtime installed, which is the one thing the
  package cannot carry and the operator's machine must already have;
* how does a message reach a person when there is no terminal to print to.

Nothing here touches game state, and a check that cannot run is never allowed
to stop the application: an unreadable registry means "unknown", not "missing".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final

#: The Edge Update client identifier for the WebView2 Evergreen Runtime. The
#: runtime registers itself here whether it was installed per-machine or
#: per-user, so both hives are worth reading.
WEBVIEW2_CLIENT_ID: Final[str] = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

WEBVIEW2_REMEDY: Final[str] = (
    "Install the Microsoft Edge WebView2 Runtime (Evergreen Standalone "
    "Installer) from Microsoft, then start the scoreboard again. It is a "
    "one-time install on this laptop and needs an internet connection only "
    "while it downloads; the scoreboard itself never needs one."
)


@dataclass(frozen=True, slots=True)
class Prerequisite:
    """One checked requirement, and what to do when it is not satisfied."""

    name: str
    satisfied: bool
    detail: str
    remedy: str = ""

    def message(self) -> str:
        if self.satisfied:
            return f"{self.name}: {self.detail}"
        return f"{self.name} is missing.\n\n{self.detail}\n\n{self.remedy}".strip()


def webview2_version() -> str | None:
    """The installed WebView2 Runtime version, or ``None`` if none was found.

    Returns ``None`` both when the runtime is genuinely absent and when the
    registry cannot be read at all -- on a non-Windows host, for instance.
    Callers must treat ``None`` as "could not confirm", never as proof.
    """

    try:
        import winreg  # noqa: PLC0415 - Windows only, and only when checked
    except ImportError:
        return None

    subkey = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}"
    candidates = (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT_ID}"),
        (winreg.HKEY_LOCAL_MACHINE, subkey),
        (winreg.HKEY_CURRENT_USER, subkey),
    )
    for hive, path in candidates:
        try:
            with winreg.OpenKey(hive, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if isinstance(version, str) and version.strip() and version != "0.0.0.0":
            return version
    return None


def check_webview2() -> Prerequisite:
    version = webview2_version()
    if version is None:
        return Prerequisite(
            name="Microsoft Edge WebView2 Runtime",
            satisfied=False,
            detail=(
                "The scoreboard draws both windows with WebView2 and could not "
                "find it on this computer."
            ),
            remedy=WEBVIEW2_REMEDY,
        )
    return Prerequisite(
        name="Microsoft Edge WebView2 Runtime",
        satisfied=True,
        detail=f"version {version}",
    )


def check_prerequisites() -> list[Prerequisite]:
    """Every prerequisite the operator's machine must supply, in report order."""

    return [check_webview2()]


def frozen() -> bool:
    """Whether this is a packaged build rather than a source checkout."""

    return bool(getattr(sys, "frozen", False))


def has_console() -> bool:
    """Whether anything printed to standard output can actually be read.

    A windowed PyInstaller build has no console; ``sys.stdout`` may be ``None``
    outright, or a stream nobody will ever see.
    """

    stream = getattr(sys, "stdout", None)
    return stream is not None and hasattr(stream, "write") and not frozen()


def report(title: str, message: str) -> None:
    """Put one message in front of the operator, console or not.

    In a checkout this prints. In a packaged build it opens a message box,
    because a silent exit is indistinguishable from a broken shortcut. If even
    that fails, the message still goes to standard error rather than vanishing.
    """

    if has_console():
        print(message)
        return
    try:
        import ctypes  # noqa: PLC0415 - only needed on the no-console path

        # MB_OK | MB_ICONERROR | MB_SETFOREGROUND
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10 | 0x10000)
    except Exception:  # noqa: BLE001 - a failed dialog must not mask the cause
        print(message, file=sys.stderr)


__all__ = [
    "WEBVIEW2_CLIENT_ID",
    "WEBVIEW2_REMEDY",
    "Prerequisite",
    "check_prerequisites",
    "check_webview2",
    "frozen",
    "has_console",
    "report",
    "webview2_version",
]
