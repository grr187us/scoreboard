"""The presentation-layout library: several complete layouts, one active.

**Why a separate file rather than a ``config.json`` section:** the library can
hold several complete layouts and carries its own schema version, independent
of the display preference ``config.json`` holds. A damaged layout library must
not be able to cost the operator their saved display, and vice versa -- two
independent preference concerns should not share one failure mode. This
follows exactly the same "a preference file may never stop the scoreboard"
contract as :mod:`scoreboard.infrastructure.config`, and uses the same atomic
temp-file + ``os.replace`` write.

Every read returns a usable library, never an exception: a missing file, an
unreadable one, invalid JSON, the wrong shape, an unsupported or newer schema
version, or an ``active`` pointer to nothing all fall back to the single
built-in default layout, exactly the way a malformed ``config.json`` falls
back to no preference at all. An individual stored layout that fails
:func:`~scoreboard.presentation.layout.validate_layout` is simply dropped
(with an issue) while its siblings still load -- that is the one place this
module recovers *partially* rather than falling all the way back, because one
bad layout should not cost every other saved one.

A newer ``schema_version`` on disk is left untouched by every write in this
module (same reasoning as ``config.py``): a build that does not understand a
future file must not destroy what a later build will still be able to read.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Final

from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.presentation.layout import (
    DEFAULT_LAYOUT_NAME,
    LayoutIssue,
    LayoutValidation,
    default_layout,
    validate_layout,
    validate_layout_name,
)

LAYOUT_LIBRARY_SCHEMA_VERSION: Final[int] = 1
MAX_LAYOUT_NAME_LENGTH: Final[int] = 40
MAX_STORED_LAYOUTS: Final[int] = 20


@dataclass(frozen=True, slots=True)
class LayoutLibrary:
    """Every stored layout, and which one is active."""

    active: str
    layouts: dict[str, dict[str, Any]]
    issues: tuple[LayoutIssue, ...] = ()
    fell_back: bool = False

    def active_layout(self) -> dict[str, Any]:
        """The active layout document. Always returns something usable."""

        layout = self.layouts.get(self.active)
        if layout is not None:
            return layout
        if self.layouts:
            return next(iter(self.layouts.values()))
        return default_layout()

    def names(self) -> list[str]:
        """Stored layout names, sorted, with ``"Default"`` always first."""

        others = sorted(name for name in self.layouts if name != DEFAULT_LAYOUT_NAME)
        if DEFAULT_LAYOUT_NAME in self.layouts:
            return [DEFAULT_LAYOUT_NAME, *others]
        return others

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LAYOUT_LIBRARY_SCHEMA_VERSION,
            "active": self.active,
            "layouts": self.layouts,
        }


def default_library() -> LayoutLibrary:
    """The library containing only the built-in default layout."""

    return LayoutLibrary(active=DEFAULT_LAYOUT_NAME, layouts={DEFAULT_LAYOUT_NAME: default_layout()})


def _fall_back(issues: tuple[LayoutIssue, ...]) -> LayoutLibrary:
    fresh = default_library()
    return LayoutLibrary(active=fresh.active, layouts=fresh.layouts, issues=issues, fell_back=True)


def _is_newer_on_disk(paths: ScoreboardPaths) -> bool:
    """Whether the stored file already declares a schema newer than ours."""

    try:
        payload = json.loads(paths.layouts.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return False
    return version > LAYOUT_LIBRARY_SCHEMA_VERSION


def read_library(paths: ScoreboardPaths) -> LayoutLibrary:
    """Return the stored layout library, or the built-in default.

    Every failure short-circuits to the same answer: the caller's response is
    identical either way, so there is no reason to distinguish "no file" from
    "unreadable file" from "a future build wrote this" beyond the recorded
    issue text.
    """

    try:
        raw_text = paths.layouts.read_text(encoding="utf-8")
    except OSError:
        return _fall_back(())
    try:
        payload = json.loads(raw_text)
    except ValueError:
        return _fall_back(
            (LayoutIssue("NOT_AN_OBJECT", "The layout library file is not valid JSON."),)
        )
    if not isinstance(payload, dict):
        return _fall_back((LayoutIssue("NOT_AN_OBJECT", "The layout library must be an object."),))

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return _fall_back(
            (LayoutIssue("SCHEMA_VERSION", "The layout library's schema_version is missing or invalid."),)
        )
    if version != LAYOUT_LIBRARY_SCHEMA_VERSION:
        # Covers both an older/unsupported version and a newer one. Either
        # way this build must not guess at what the sections mean, and a
        # newer file is left completely alone -- see the module docstring.
        return _fall_back(
            (LayoutIssue("SCHEMA_VERSION", f"Unsupported layout library schema_version {version!r}."),)
        )

    raw_layouts = payload.get("layouts")
    if not isinstance(raw_layouts, dict):
        return _fall_back((LayoutIssue("WIDGETS", "The layout library's layouts must be an object."),))

    issues: list[LayoutIssue] = []
    layouts: dict[str, dict[str, Any]] = {}
    for name, raw_layout in raw_layouts.items():
        name_issue = validate_layout_name(name)
        if name_issue is not None:
            issues.append(
                LayoutIssue(
                    "LAYOUT_NAME", f"A stored layout name was invalid and was dropped: {name!r}.",
                    severity="warning",
                )
            )
            continue
        result = validate_layout(raw_layout)
        if not result.ok:
            issues.append(
                LayoutIssue(
                    "WIDGETS", f"The stored layout {name!r} was invalid and was dropped.",
                    severity="warning",
                )
            )
            continue
        issues.extend(result.warnings)
        clean_name = name.strip()
        assert result.layout is not None
        layouts[clean_name] = {**result.layout, "name": clean_name}

    if not layouts:
        # Every stored layout was invalid (or there were none) -- there is
        # nothing left to serve, so fall back completely.
        return _fall_back(tuple(issues) or (LayoutIssue("WIDGETS", "No stored layout was usable."),))

    active = payload.get("active")
    if not isinstance(active, str) or active not in layouts:
        # An unresolvable active pointer is one of the "ANY problem" cases
        # this module answers uniformly: fall back completely rather than
        # guessing which layout the operator meant.
        return _fall_back(
            tuple(issues)
            + (LayoutIssue("LAYOUT_NAME", f"The active layout {active!r} was not found."),)
        )

    if DEFAULT_LAYOUT_NAME not in layouts:
        # "Default" always exists in a library this module hands out, even
        # if a hand-edited file omitted it.
        layouts[DEFAULT_LAYOUT_NAME] = default_layout()

    return LayoutLibrary(active=active, layouts=layouts, issues=tuple(issues), fell_back=False)


def write_library(paths: ScoreboardPaths, library: LayoutLibrary) -> bool:
    """Store ``library`` atomically. Returns whether the write succeeded.

    Never raises: a failure -- including a newer file already on disk -- is
    reported to the caller rather than propagated, the same trade
    :func:`scoreboard.infrastructure.config.write_config` makes.
    """

    if _is_newer_on_disk(paths):
        return False
    document = library.to_dict()
    temporary = paths.layouts.with_suffix(".json.tmp")
    try:
        paths.layouts.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, paths.layouts)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink()
        except OSError:
            pass
        return False


def save_layout(paths: ScoreboardPaths, name: Any, payload: Any) -> tuple[LayoutLibrary, LayoutValidation]:
    """Validate and store ``payload`` under ``name``, making it active.

    On any failure -- an invalid name, an invalid layout, too many stored
    layouts, or a disk write failure -- this returns the **currently stored**
    library completely unchanged, and writes nothing. This is the "preserve
    the last valid layout" guarantee: a rejected save can never cost an
    operator the layout that was already saved.
    """

    current = read_library(paths)
    name_issue = validate_layout_name(name)
    if name_issue is not None:
        return current, LayoutValidation(None, (name_issue,))
    clean_name = name.strip()

    result = validate_layout(payload)
    if not result.ok:
        return current, result

    layouts = dict(current.layouts)
    if clean_name not in layouts and len(layouts) >= MAX_STORED_LAYOUTS:
        issue = LayoutIssue(
            "MAX_STORED_LAYOUTS", f"No more than {MAX_STORED_LAYOUTS} layouts may be stored."
        )
        return current, LayoutValidation(None, (issue,))

    assert result.layout is not None
    layouts[clean_name] = {**result.layout, "name": clean_name}
    library = LayoutLibrary(active=clean_name, layouts=layouts)
    if not write_library(paths, library):
        issue = LayoutIssue("WRITE_FAILED", "The layout could not be saved to disk.")
        return current, LayoutValidation(None, (issue,))
    return library, result


def select_layout(paths: ScoreboardPaths, name: Any) -> tuple[LayoutLibrary, LayoutValidation]:
    """Make the stored layout named ``name`` active."""

    current = read_library(paths)
    name_issue = validate_layout_name(name)
    if name_issue is not None:
        return current, LayoutValidation(None, (name_issue,))
    clean_name = name.strip()
    if clean_name not in current.layouts:
        issue = LayoutIssue("LAYOUT_NOT_FOUND", f"No stored layout is named {clean_name!r}.")
        return current, LayoutValidation(None, (issue,))

    library = LayoutLibrary(active=clean_name, layouts=current.layouts)
    if not write_library(paths, library):
        issue = LayoutIssue("WRITE_FAILED", "The selection could not be saved to disk.")
        return current, LayoutValidation(None, (issue,))
    return library, LayoutValidation(library.active_layout(), ())


def delete_layout(paths: ScoreboardPaths, name: Any) -> tuple[LayoutLibrary, LayoutValidation]:
    """Remove the stored layout named ``name``. ``"Default"`` cannot be removed."""

    current = read_library(paths)
    name_issue = validate_layout_name(name)
    if name_issue is not None:
        return current, LayoutValidation(None, (name_issue,))
    clean_name = name.strip()
    if clean_name == DEFAULT_LAYOUT_NAME:
        issue = LayoutIssue("DEFAULT_PROTECTED", "The Default layout cannot be deleted.")
        return current, LayoutValidation(None, (issue,))
    if clean_name not in current.layouts:
        issue = LayoutIssue("LAYOUT_NOT_FOUND", f"No stored layout is named {clean_name!r}.")
        return current, LayoutValidation(None, (issue,))

    layouts = dict(current.layouts)
    del layouts[clean_name]
    active = DEFAULT_LAYOUT_NAME if current.active == clean_name else current.active
    library = LayoutLibrary(active=active, layouts=layouts)
    if not write_library(paths, library):
        issue = LayoutIssue("WRITE_FAILED", "The deletion could not be saved to disk.")
        return current, LayoutValidation(None, (issue,))
    return library, LayoutValidation(library.active_layout(), ())


def reset_library(paths: ScoreboardPaths) -> LayoutLibrary:
    """Restore the built-in single-layout library, discarding every save."""

    library = default_library()
    write_library(paths, library)
    return library


__all__ = [
    "LAYOUT_LIBRARY_SCHEMA_VERSION",
    "MAX_LAYOUT_NAME_LENGTH",
    "MAX_STORED_LAYOUTS",
    "LayoutLibrary",
    "default_library",
    "delete_layout",
    "read_library",
    "reset_library",
    "save_layout",
    "select_layout",
    "write_library",
]
