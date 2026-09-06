"""The saved-team library: names, short names, and two colours per team.

**Why a separate file rather than a ``config.json`` section or game state:**
team identity is not game state -- ``GameState`` keeps only ``home_name``/
``away_name`` (see ``domain/state.py``), and applying a saved team still goes
through the existing, validated ``set_team_name`` command like any manual
retype. This file is the *library* a shortcut is drawn from: a laptop
preference, exactly like ``layouts.json``, with its own schema version,
independent of both ``config.json`` and the game database. A damaged team
library must not be able to cost the operator their saved display or game,
and vice versa -- this follows exactly the same "a preference file may never
stop the scoreboard" contract as :mod:`scoreboard.infrastructure.config` and
:mod:`scoreboard.infrastructure.layouts`, and uses the same atomic temp-file
+ ``os.replace`` write.

Every read returns a usable library, never an exception: a missing file, an
unreadable one, invalid JSON, the wrong shape, or an unsupported/newer schema
version all fall back to the built-in empty library -- there being no saved
teams yet is the ordinary first run, not damage. An individual stored team
that fails :func:`validate_team` is simply dropped (with a ``TEAM_DROPPED``
issue) while its siblings still load, the same partial-recovery trade
``layouts.py`` makes for one bad stored layout: one bad entry should not cost
every other saved team. A later duplicate name (case-insensitive, after
trimming) is dropped the same way, with a ``DUPLICATE`` issue.

A newer ``schema_version`` on disk is left untouched by every write in this
module (same reasoning as ``config.py``/``layouts.py``): a build that does not
understand a future file must not destroy what a later build will still be
able to read.

This module never touches ``config.json``, ``layouts.json``, or
``scoreboard.db``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Final

from scoreboard.domain.state import MAX_TEAM_NAME_LENGTH
from scoreboard.infrastructure.paths import ScoreboardPaths

TEAM_LIBRARY_SCHEMA_VERSION: Final[int] = 1
MAX_STORED_TEAMS: Final[int] = 64
MAX_SHORT_NAME_LENGTH: Final[int] = 6
DEFAULT_PRIMARY: Final[str] = "#FFFFFF"
DEFAULT_SECONDARY: Final[str] = "#111111"

#: Exactly ``#RRGGBB`` -- unlike the presentation layout's colour parsing,
#: shorthand ``#RGB`` is not accepted here (spec F4 section 3.1).
_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True, slots=True)
class TeamIssue:
    """One problem found while reading, saving, or deleting a team."""

    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class TeamPreset:
    """One saved team: a name, a short name, and two colours."""

    name: str
    short_name: str
    primary: str
    secondary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "short_name": self.short_name,
            "primary": self.primary,
            "secondary": self.secondary,
        }


@dataclass(frozen=True, slots=True)
class TeamLibrary:
    """Every stored team."""

    teams: tuple[TeamPreset, ...]
    issues: tuple[TeamIssue, ...] = ()
    fell_back: bool = False

    def find(self, name: Any) -> TeamPreset | None:
        """The stored team matching ``name``, case-insensitively after trimming."""

        if not isinstance(name, str):
            return None
        trimmed = name.strip()
        if not trimmed:
            return None
        lowered = trimmed.lower()
        for team in self.teams:
            if team.name.lower() == lowered:
                return team
        return None

    def sorted(self) -> list[TeamPreset]:
        """Stored teams ordered by name, case-insensitively."""

        return sorted(self.teams, key=lambda team: team.name.lower())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TEAM_LIBRARY_SCHEMA_VERSION,
            "teams": [team.to_dict() for team in self.teams],
        }


def default_library() -> TeamLibrary:
    """The library containing no saved teams -- the ordinary first run."""

    return TeamLibrary(teams=())


def _fall_back(issues: tuple[TeamIssue, ...]) -> TeamLibrary:
    return TeamLibrary(teams=(), issues=issues, fell_back=True)


def derive_short_name(name: str) -> str:
    """The default short name: spaces removed, upper-cased, first 4 characters."""

    condensed = "".join(name.split()).upper()
    return condensed[:4]


def _resolve_color(value: Any, default: str) -> tuple[str, TeamIssue | None]:
    """A stored/validated colour, or the default when ``value`` is absent."""

    if value is None or (isinstance(value, str) and not value.strip()):
        return default, None
    if not isinstance(value, str) or not _COLOR_PATTERN.match(value.strip()):
        return default, TeamIssue(
            "INVALID_COLOR", f"A colour must be a hex value like #RRGGBB; got {value!r}."
        )
    return value.strip().upper(), None


def validate_team(payload: Any) -> TeamPreset | TeamIssue:
    """Validate one team payload, returning a usable preset or the first issue.

    ``name`` is trimmed and must be 1-``MAX_TEAM_NAME_LENGTH`` characters (the
    same rule ``domain.state`` enforces for ``set_team_name``). ``short_name``,
    ``primary``, and ``secondary`` are optional; when absent or blank a
    default is derived/used instead of refusing the whole team. Unknown keys
    are ignored.
    """

    if not isinstance(payload, dict):
        return TeamIssue("NOT_AN_OBJECT", "A team must be an object.")

    raw_name = payload.get("name")
    if not isinstance(raw_name, str):
        return TeamIssue("INVALID_NAME", "A team name must be text.")
    name = raw_name.strip()
    if not name:
        return TeamIssue("INVALID_NAME", "A team name must not be empty.")
    if len(name) > MAX_TEAM_NAME_LENGTH:
        return TeamIssue(
            "INVALID_NAME", f"A team name must be at most {MAX_TEAM_NAME_LENGTH} characters."
        )

    raw_short = payload.get("short_name")
    if raw_short is None or (isinstance(raw_short, str) and not raw_short.strip()):
        short_name = derive_short_name(name)
    elif isinstance(raw_short, str):
        short_name = raw_short.strip()
        if len(short_name) > MAX_SHORT_NAME_LENGTH:
            return TeamIssue(
                "INVALID_SHORT_NAME",
                f"A short name must be at most {MAX_SHORT_NAME_LENGTH} characters.",
            )
    else:
        return TeamIssue("INVALID_SHORT_NAME", "A short name must be text.")

    primary, primary_issue = _resolve_color(payload.get("primary"), DEFAULT_PRIMARY)
    if primary_issue is not None:
        return primary_issue
    secondary, secondary_issue = _resolve_color(payload.get("secondary"), DEFAULT_SECONDARY)
    if secondary_issue is not None:
        return secondary_issue

    return TeamPreset(name=name, short_name=short_name, primary=primary, secondary=secondary)


def _is_newer_on_disk(paths: ScoreboardPaths) -> bool:
    """Whether the stored file already declares a schema newer than ours."""

    try:
        payload = json.loads(paths.teams.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return False
    return version > TEAM_LIBRARY_SCHEMA_VERSION


def read_library(paths: ScoreboardPaths) -> TeamLibrary:
    """Return the stored team library, or the built-in empty one.

    Every failure -- absent file, unreadable file, invalid JSON, the wrong
    shape, an unreadable or newer schema version -- is the same answer,
    because the caller's response to all of them is identical: carry on with
    no saved teams. Never raises.
    """

    try:
        raw_text = paths.teams.read_text(encoding="utf-8")
    except OSError:
        return _fall_back(())
    try:
        payload = json.loads(raw_text)
    except ValueError:
        return _fall_back((TeamIssue("NOT_AN_OBJECT", "The team library file is not valid JSON."),))
    if not isinstance(payload, dict):
        return _fall_back((TeamIssue("NOT_AN_OBJECT", "The team library must be an object."),))

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return _fall_back(
            (TeamIssue("SCHEMA_VERSION", "The team library's schema_version is missing or invalid."),)
        )
    if version != TEAM_LIBRARY_SCHEMA_VERSION:
        # Covers both an older/unsupported version and a newer one. Either
        # way this build must not guess at what the entries mean, and a newer
        # file is left completely alone -- see the module docstring.
        return _fall_back(
            (TeamIssue("SCHEMA_VERSION", f"Unsupported team library schema_version {version!r}."),)
        )

    raw_teams = payload.get("teams")
    if not isinstance(raw_teams, list):
        return _fall_back((TeamIssue("NOT_AN_OBJECT", "The team library's teams must be a list."),))

    issues: list[TeamIssue] = []
    teams: list[TeamPreset] = []
    seen: set[str] = set()
    for index, raw_team in enumerate(raw_teams):
        result = validate_team(raw_team)
        if isinstance(result, TeamIssue):
            if isinstance(raw_team, dict) and isinstance(raw_team.get("name"), str):
                label = raw_team["name"]
            else:
                label = f"entry #{index + 1}"
            issues.append(
                TeamIssue(
                    "TEAM_DROPPED",
                    f"The stored team {label!r} was invalid and was dropped: {result.message}",
                )
            )
            continue
        key = result.name.lower()
        if key in seen:
            issues.append(
                TeamIssue("DUPLICATE", f"A duplicate stored team named {result.name!r} was dropped.")
            )
            continue
        seen.add(key)
        teams.append(result)

    if raw_teams and not teams:
        # Every stored entry was invalid -- nothing left to serve.
        return _fall_back(tuple(issues) or (TeamIssue("NOT_AN_OBJECT", "No stored team was usable."),))

    return TeamLibrary(teams=tuple(teams), issues=tuple(issues), fell_back=False)


def write_library(paths: ScoreboardPaths, library: TeamLibrary) -> bool:
    """Store ``library`` atomically. Returns whether the write succeeded.

    Never raises: a failure -- including a newer file already on disk -- is
    reported to the caller rather than propagated, the same trade
    :func:`scoreboard.infrastructure.layouts.write_library` makes.
    """

    if _is_newer_on_disk(paths):
        return False
    document = library.to_dict()
    temporary = paths.teams.with_suffix(".json.tmp")
    try:
        paths.teams.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, paths.teams)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink()
        except OSError:
            pass
        return False


def save_team(paths: ScoreboardPaths, payload: Any) -> tuple[TeamLibrary, TeamIssue | None]:
    """Validate and store one team, replacing any existing team of the same name.

    On any failure -- an invalid team, too many stored teams, or a disk write
    failure -- this returns the **currently stored** library completely
    unchanged, and writes nothing. This is the "preserve the last valid
    library" guarantee: a rejected save can never cost an operator a team that
    was already saved.
    """

    current = read_library(paths)
    result = validate_team(payload)
    if isinstance(result, TeamIssue):
        return current, result

    teams = list(current.teams)
    lowered = result.name.lower()
    existing_index = next(
        (index for index, team in enumerate(teams) if team.name.lower() == lowered), None
    )
    if existing_index is None and len(teams) >= MAX_STORED_TEAMS:
        issue = TeamIssue("TOO_MANY_TEAMS", f"No more than {MAX_STORED_TEAMS} teams may be stored.")
        return current, issue

    if existing_index is None:
        teams.append(result)
    else:
        teams[existing_index] = result

    library = TeamLibrary(teams=tuple(teams))
    if not write_library(paths, library):
        issue = TeamIssue("WRITE_FAILED", "The team could not be saved to disk.")
        return current, issue
    return library, None


def delete_team(paths: ScoreboardPaths, name: Any) -> tuple[TeamLibrary, TeamIssue | None]:
    """Remove the stored team named ``name``."""

    current = read_library(paths)
    if not isinstance(name, str) or not name.strip():
        return current, TeamIssue("NOT_FOUND", "No team name was given.")
    trimmed = name.strip()
    lowered = trimmed.lower()
    teams = [team for team in current.teams if team.name.lower() != lowered]
    if len(teams) == len(current.teams):
        return current, TeamIssue("NOT_FOUND", f"No stored team is named {trimmed!r}.")

    library = TeamLibrary(teams=tuple(teams))
    if not write_library(paths, library):
        issue = TeamIssue("WRITE_FAILED", "The deletion could not be saved to disk.")
        return current, issue
    return library, None


__all__ = [
    "DEFAULT_PRIMARY",
    "DEFAULT_SECONDARY",
    "MAX_SHORT_NAME_LENGTH",
    "MAX_STORED_TEAMS",
    "TEAM_LIBRARY_SCHEMA_VERSION",
    "TeamIssue",
    "TeamLibrary",
    "TeamPreset",
    "default_library",
    "delete_team",
    "derive_short_name",
    "read_library",
    "save_team",
    "validate_team",
    "write_library",
]
