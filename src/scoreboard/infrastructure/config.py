"""Operator preferences that are not game state.

``config.json`` has been in the architecture since Phase 1 (ARCHITECTURE.md
section 9) and has had a filename reserved for it since Task 6. Task 10 is the
first thing that needs it: the display an operator chose has to survive a
restart, and it is emphatically not game state -- it advances no revision, it
belongs to the laptop rather than to the game, and copying a game database to
another machine should not drag a monitor identity along with it.

The whole contract is in one sentence: **a preference file may never stop the
scoreboard from starting.** A file that is missing, empty, truncated by a power
loss, hand-edited into invalid JSON, or written by a future version reads as
"no preference set". That is the same trade
:func:`scoreboard.infrastructure.paths.read_chosen_root` makes for the data
folder, for the same reason -- on a game night, a stale setting must cost one
operator click, never the game.

Reading creates nothing. Writing is atomic through a temporary file in the same
directory, so an interrupted write leaves the previous preference intact rather
than a half-written file that reads as corrupt.
"""

from __future__ import annotations

import json
import os
from typing import Any, Final

from scoreboard.domain.rules import GameRules, RulesError, default_rules
from scoreboard.infrastructure.paths import ScoreboardPaths

#: Bumped only when an older build could misread a newer file. Unknown sections
#: are preserved on write, so adding one does not need a bump.
CONFIG_SCHEMA_VERSION: Final[int] = 1

#: The section holding the spectator display identity (Task 10).
DISPLAY_SECTION: Final[str] = "display"

#: The section holding presentation preferences (event-screens spec section
#: 2.9): ``{"motion": bool}`` -- the global animation kill switch for the
#: spectator boards. A host preference like the display, never game state.
PRESENTATION_SECTION: Final[str] = "presentation"

#: The section holding the game's timing rules (September 9, 2026): quarter,
#: overtime, pregame, and halftime lengths, the warmup threshold, the crowd
#: timeout length, and timeouts per half. See ``domain.rules``. A laptop
#: preference like the display -- a league's rules outlive any one game and
#: should not travel with a game database.
RULES_SECTION: Final[str] = "rules"


def read_config(paths: ScoreboardPaths) -> dict[str, Any]:
    """Return the stored preferences, or ``{}`` if there are none to be had.

    Every failure -- absent file, unreadable file, invalid JSON, a JSON value
    that is not an object, an unreadable schema version -- is the same answer,
    because the caller's response to all of them is identical: carry on with
    defaults.
    """

    try:
        payload = json.loads(paths.config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return {}
    if version > CONFIG_SCHEMA_VERSION:
        # Written by a newer build. Its sections may mean something different,
        # so read none of them rather than guess -- and leave the file alone,
        # so returning to the newer build does not lose the operator's setting.
        return {}
    return payload


def write_config(paths: ScoreboardPaths, payload: dict[str, Any]) -> bool:
    """Store preferences atomically. Returns whether the write succeeded.

    A failure is reported rather than raised. This is called from a button an
    operator may press during a game: losing a preference is a small
    inconvenience, and an exception escaping into the host is not.
    """

    document = {**payload, "schema_version": CONFIG_SCHEMA_VERSION}
    temporary = paths.config.with_suffix(".json.tmp")
    try:
        paths.config.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, paths.config)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink()
        except OSError:
            pass
        return False


def read_section(paths: ScoreboardPaths, section: str) -> Any:
    """One named section of the preferences, or ``None``."""

    return read_config(paths).get(section)


def write_section(paths: ScoreboardPaths, section: str, value: Any) -> bool:
    """Replace one section, leaving every other section untouched.

    Read-modify-write rather than overwrite, so a build that does not know
    about a section cannot delete it, and two features never fight over the
    file.
    """

    document = read_config(paths)
    if value is None:
        document.pop(section, None)
    else:
        document[section] = value
    return write_config(paths, document)


def read_motion(paths: ScoreboardPaths) -> bool:
    """Whether board animations are on. Absent or unreadable means **on**:
    motion is the designed look, and a damaged preference file must never
    quietly freeze the wall (same contract as every other preference).
    """

    section = read_section(paths, PRESENTATION_SECTION)
    if not isinstance(section, dict):
        return True
    motion = section.get("motion")
    return motion if isinstance(motion, bool) else True


def write_motion(paths: ScoreboardPaths, enabled: bool) -> bool:
    """Store the motion switch, keeping any other presentation key intact."""

    section = read_section(paths, PRESENTATION_SECTION)
    document = dict(section) if isinstance(section, dict) else {}
    document["motion"] = bool(enabled)
    return write_section(paths, PRESENTATION_SECTION, document)


def read_rules(paths: ScoreboardPaths) -> GameRules:
    """The stored timing rules, or the shipped defaults.

    Same contract as every other preference: a section that is missing,
    malformed, or carries a value the current build refuses reads as "no
    preference set" -- the whole section falls back, never half of it, so
    the operator sees one coherent set of defaults rather than a mix.
    """

    section = read_section(paths, RULES_SECTION)
    if not isinstance(section, dict):
        return default_rules()
    try:
        return GameRules.from_payload(section)
    except RulesError:
        return default_rules()


def write_rules(paths: ScoreboardPaths, rules: GameRules) -> bool:
    """Store the timing rules, keeping every other section intact."""

    return write_section(paths, RULES_SECTION, rules.to_dict())


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "DISPLAY_SECTION",
    "PRESENTATION_SECTION",
    "RULES_SECTION",
    "read_config",
    "read_motion",
    "read_rules",
    "read_section",
    "write_config",
    "write_motion",
    "write_rules",
    "write_section",
]
