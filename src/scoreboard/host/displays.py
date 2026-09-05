"""Choosing which Windows display the spectator window belongs on.

Task 1 proved a window can be placed on a chosen screen. It selected that
screen by list position, which is the least durable identity Windows offers:
unplug the HDMI cable, change a resolution, or let the LED processor come back
in a different order, and index 1 is a different monitor -- or the operator's
own screen.

This module replaces the index with a best-effort *identity* and the matching
rules around it (UX_AND_LAYOUT.md section 7). Everything here is pure: it takes
a list of screens and a remembered preference and returns a decision. No
window is opened, no file is read, and no Windows API is called, so the whole
selection policy is testable on a machine with one display -- which is what the
development host has.

Two deliberate refusals:

* **An unmatched preference never falls back to the primary screen.** A
  spectator window that quietly covers the operator's controls twenty minutes
  before kickoff is worse than no spectator window at all, so a missing display
  is reported and the operator chooses (D-002).
* **A match never moves a window on its own.** These functions answer "which
  display would this be?"; opening or moving anything stays an explicit
  operator action (Task 10 boundary, D-006).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Final, Iterable, Protocol, Sequence


class ScreenLike(Protocol):
    x: int
    y: int
    width: int
    height: int
    scale: float


#: How a remembered display was recognised in the current screen list. The
#: operator is told which of these happened, because "the same display" and
#: "a display in the same place" are not the same claim.
MATCH_EXACT: Final[str] = "exact"
MATCH_NAME: Final[str] = "name"
MATCH_GEOMETRY: Final[str] = "geometry"
MATCH_NONE: Final[str] = "none"

#: How a display was arrived at when no remembered preference was consulted.
#: Kept beside the match tiers because the operator view shows one field.
MATCH_CHOSEN: Final[str] = "chosen"
MATCH_INDEX: Final[str] = "index"
MATCH_DEFAULT: Final[str] = "default"

#: The tiers that mean "this is the display that was saved". Opening one of
#: these refreshes the stored record; anything else must not re-point it.
RECOGNISED_MATCHES: Final[frozenset[str]] = frozenset(
    {MATCH_EXACT, MATCH_NAME, MATCH_GEOMETRY}
)


@dataclass(frozen=True, slots=True)
class DisplayTarget:
    """One display as it exists right now, with its best-effort identity.

    ``index`` is where this display sits in the current enumeration. It is
    shown to the operator and accepted from the command line, but it is never
    used to recognise a remembered display: that is what ``key`` and ``name``
    are for.
    """

    index: int
    x: int
    y: int
    width: int
    height: int
    scale: float
    #: The Windows device name (``\\\\.\\DISPLAY2``) when it could be read.
    #: ``None`` is normal, not a failure: the identity falls back to geometry.
    name: str | None = None

    @property
    def primary(self) -> bool:
        """Windows always places the primary display's bounds at the origin."""

        return self.x == 0 and self.y == 0

    @property
    def key(self) -> str:
        """A stable token for this display within one enumeration.

        Geometry, not index. Two displays cannot occupy the same rectangle of
        the virtual desktop, so this is unique, and it does not change when
        another monitor is unplugged and the list gets shorter. The operator
        view sends this back to ask for a display; the host re-resolves it
        against a fresh enumeration, so a display that vanished in between is
        reported missing rather than confused with its neighbour.
        """

        return f"{self.width}x{self.height}+{self.x}+{self.y}"

    @property
    def label(self) -> str:
        return (
            f"Display {self.index + 1}: {self.width}x{self.height} "
            f"at {self.x},{self.y} ({self.scale:g}x)"
        )

    @property
    def description(self) -> str:
        """The label plus whatever identity Windows gave us, for the operator."""

        parts = [self.label]
        if self.name:
            parts.append(self.name)
        if self.primary:
            parts.append("primary")
        return " — ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible, because this crosses the bridge to the operator."""

        return {
            "index": self.index,
            "key": self.key,
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "primary": self.primary,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
        }

    def as_preference(self) -> "DisplayPreference":
        return DisplayPreference(
            name=self.name,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            scale=self.scale,
        )


@dataclass(frozen=True, slots=True)
class DisplayPreference:
    """The remembered display, as it looked when the operator chose it.

    Deliberately not an index. Geometry plus the device name is the most
    identity Windows offers without asking for the monitor's EDID, and either
    half alone is enough to recognise the display again in the common failure
    cases: a resolution change keeps the name, and a device renumbering keeps
    the geometry.
    """

    name: str | None
    x: int
    y: int
    width: int
    height: int
    scale: float

    @property
    def label(self) -> str:
        geometry = f"{self.width}x{self.height} at {self.x},{self.y}"
        return geometry if not self.name else f"{geometry} ({self.name})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
        }


def preference_from_dict(payload: Any) -> DisplayPreference | None:
    """Read a stored preference, or ``None`` if it is not usable.

    Tolerant on purpose, exactly like ``paths.read_chosen_root``: a preference
    that is missing, truncated, hand-edited, or written by a future version
    must never stop the scoreboard from starting. Falling back to "no saved
    display" costs one operator click; refusing to start costs the game.
    """

    if not isinstance(payload, dict):
        return None
    numbers: dict[str, float] = {}
    for field in ("x", "y", "width", "height", "scale"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numbers[field] = float(value)
    if numbers["width"] <= 0 or numbers["height"] <= 0 or numbers["scale"] <= 0:
        return None
    name = payload.get("name")
    if name is not None and not isinstance(name, str):
        return None
    return DisplayPreference(
        name=name or None,
        x=int(numbers["x"]),
        y=int(numbers["y"]),
        width=int(numbers["width"]),
        height=int(numbers["height"]),
        scale=numbers["scale"],
    )


@dataclass(frozen=True, slots=True)
class DisplayMatch:
    """Which display a request resolved to, and how confident that is."""

    target: DisplayTarget | None
    how: str
    message: str

    @property
    def found(self) -> bool:
        return self.target is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "how": self.how,
            "message": self.message,
            "target": None if self.target is None else self.target.to_dict(),
        }


def enumerate_displays(
    screens: Iterable[ScreenLike],
    names: Sequence[str | None] | None = None,
) -> list[DisplayTarget]:
    """Create deterministic, operator-visible choices from pywebview screens.

    ``names`` is the parallel list of Windows device names when the host could
    read them. It is optional because pywebview does not expose them and the
    call that does is a best-effort extra: a missing name degrades the identity
    to geometry, which is still far better than an index.
    """

    targets: list[DisplayTarget] = []
    for index, screen in enumerate(screens):
        name = None
        if names is not None and index < len(names):
            name = names[index] or None
        targets.append(
            DisplayTarget(
                index=index,
                x=screen.x,
                y=screen.y,
                width=screen.width,
                height=screen.height,
                scale=screen.scale,
                name=name,
            )
        )
    return targets


def _same_geometry(target: DisplayTarget, preference: DisplayPreference) -> bool:
    return (
        target.x == preference.x
        and target.y == preference.y
        and target.width == preference.width
        and target.height == preference.height
    )


def match_preference(
    preference: DisplayPreference | None, displays: Sequence[DisplayTarget]
) -> DisplayMatch:
    """Recognise a remembered display in the current list, or say it is gone.

    Three tiers, most specific first:

    1. **exact** -- the same device name in the same place at the same scale;
    2. **name** -- the same device, moved or re-scaled. A stadium processor
       that renegotiates HDMI at a different resolution lands here;
    3. **geometry** -- a display occupying the same rectangle under a different
       name, which is what a device renumbering after a replug looks like.

    There is deliberately no fourth tier. An index fallback is exactly the
    Task 1 behaviour this replaces, and it is the one that quietly covers the
    operator's screen (D-002).
    """

    if preference is None:
        return DisplayMatch(None, MATCH_NONE, "No display has been saved yet.")
    if not displays:
        return DisplayMatch(
            None, MATCH_NONE, "Windows is not reporting any display at all."
        )

    for target in displays:
        if (
            preference.name is not None
            and target.name == preference.name
            and _same_geometry(target, preference)
            and target.scale == preference.scale
        ):
            return DisplayMatch(
                target, MATCH_EXACT, f"Saved display found: {target.description}."
            )

    if preference.name is not None:
        for target in displays:
            if target.name == preference.name:
                return DisplayMatch(
                    target,
                    MATCH_NAME,
                    (
                        f"Saved display {preference.name} is back, but its size or "
                        f"position changed: it was {preference.label} and is now "
                        f"{target.width}x{target.height} at {target.x},{target.y}. "
                        "Check the board fills the wall."
                    ),
                )

    for target in displays:
        if _same_geometry(target, preference):
            return DisplayMatch(
                target,
                MATCH_GEOMETRY,
                (
                    "A display is in the same place as the saved one but Windows "
                    f"now calls it {target.name or 'an unnamed device'}. Check the "
                    "board is on the right screen."
                ),
            )

    return DisplayMatch(
        None,
        MATCH_NONE,
        (
            f"DISPLAY NOT FOUND: the saved display ({preference.label}) is not "
            "connected. The scoreboard is still running and saving; choose a "
            "display when one is available."
        ),
    )


def default_target(displays: Sequence[DisplayTarget]) -> DisplayTarget | None:
    """The display to offer when nothing has been saved yet.

    The first non-primary display, because the spectator window is fullscreen
    and borderless and the primary screen is where the operator's controls
    are. With only one display there is no answer, and ``None`` is the honest
    one: the operator can still choose that display deliberately, which is the
    right way to end up mirroring the controls.
    """

    for target in displays:
        if not target.primary:
            return target
    return None


def find_by_key(key: Any, displays: Sequence[DisplayTarget]) -> DisplayTarget | None:
    """Resolve an operator's choice from the view, against a fresh enumeration."""

    if not isinstance(key, str):
        return None
    for target in displays:
        if target.key == key:
            return target
    return None


def selected_screen(screens: list[ScreenLike], index: int) -> ScreenLike | None:
    """Return a selected current screen, never substituting the primary display."""
    if 0 <= index < len(screens):
        return screens[index]
    return None


class DisplayWatch:
    """Notices displays appearing and disappearing, at a bounded cadence.

    Windows offers no event pywebview passes on, so the only way to know the
    LED wall was unplugged is to look. Looking on every refresh would mean four
    Windows enumerations a second forever, so this samples at most once per
    ``interval`` and reports only when the set of displays actually changed.

    Both the screen source and the clock are injected, so a test can unplug a
    monitor by returning a shorter list -- which is the only way this behaviour
    can be exercised on a development host with one screen.

    Detection exists to *report*. Nothing here moves a window: after a
    reconnection the operator decides, which is the D-006 rule and the Task 10
    boundary against hidden auto-moves during live play.
    """

    def __init__(
        self,
        read_displays: Callable[[], Sequence["DisplayTarget"]],
        *,
        monotonic: Callable[[], float],
        interval: float = 2.0,
    ) -> None:
        self._read_displays = read_displays
        self._monotonic = monotonic
        self._interval = float(interval)
        self._last_sample: float | None = None
        self._known: tuple[str, ...] | None = None

    @property
    def known(self) -> tuple[str, ...]:
        return () if self._known is None else self._known

    def poll(self, *, force: bool = False) -> list[DisplayTarget] | None:
        """Sample if it is time, and return the list only when it changed.

        The first sample establishes what is connected and reports no change:
        every display was "new" at startup, and saying so would be noise.
        """

        now = float(self._monotonic())
        if not force and self._last_sample is not None:
            if now - self._last_sample < self._interval:
                return None
        self._last_sample = now

        displays = list(self._read_displays())
        keys = tuple(display.key for display in displays)
        first_sample = self._known is None
        changed = keys != self._known
        self._known = keys
        if first_sample or not changed:
            return None
        return displays


__all__ = [
    "DisplayWatch",
    "MATCH_CHOSEN",
    "MATCH_DEFAULT",
    "MATCH_EXACT",
    "MATCH_INDEX",
    "MATCH_GEOMETRY",
    "MATCH_NAME",
    "MATCH_NONE",
    "RECOGNISED_MATCHES",
    "DisplayMatch",
    "DisplayPreference",
    "DisplayTarget",
    "ScreenLike",
    "default_target",
    "enumerate_displays",
    "find_by_key",
    "match_preference",
    "preference_from_dict",
    "selected_screen",
]
