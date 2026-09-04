"""Display enumeration helpers with no persistence or hardware control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class ScreenLike(Protocol):
    x: int
    y: int
    width: int
    height: int
    scale: float


@dataclass(frozen=True)
class DisplayTarget:
    """A current Windows display choice, identified only for this process."""

    index: int
    x: int
    y: int
    width: int
    height: int
    scale: float

    @property
    def label(self) -> str:
        return (
            f"Display {self.index + 1}: {self.width}x{self.height} "
            f"at {self.x},{self.y} ({self.scale:g}x)"
        )


def enumerate_displays(screens: Iterable[ScreenLike]) -> list[DisplayTarget]:
    """Create deterministic, operator-visible choices from pywebview screens."""
    return [
        DisplayTarget(
            index=index,
            x=screen.x,
            y=screen.y,
            width=screen.width,
            height=screen.height,
            scale=screen.scale,
        )
        for index, screen in enumerate(screens)
    ]


def selected_screen(screens: list[ScreenLike], index: int) -> ScreenLike | None:
    """Return a selected current screen, never substituting the primary display."""
    if 0 <= index < len(screens):
        return screens[index]
    return None
