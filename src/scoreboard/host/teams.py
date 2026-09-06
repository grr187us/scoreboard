"""The saved-team library as the bridge needs it: in-memory, locked, no game path.

Mirrors :class:`~scoreboard.host.layout_bridge.PresentationLayouts`: applying
a saved team is not a mutation this module can make. Team identity is not
game state (``domain.state.GameState`` keeps only ``home_name``/``away_name``);
applying a saved team still goes through the existing, validated
``set_team_name`` command, submitted through the bridge exactly like a manual
retype -- pregame-only, undoable, recorded in the action history (spec F4
section 3.1). This class only reads, saves, and deletes the *library* a
shortcut is drawn from, and looks up the identity that matches the game's
*current* team name so a view model can carry it forward. It never receives,
holds, or calls :class:`~scoreboard.application.service.ScoreboardService`, so
nothing here can build or submit a
:class:`~scoreboard.domain.commands.Command`; it advances no revision and
writes no action-history row.

``identity()``/``identities()`` are cheap in-memory dict lookups against a
library read once at startup and refreshed only by ``save``/``delete`` --
:mod:`scoreboard.host.bridge` calls ``identity()`` from inside a view build
roughly ten times a second, so it must never touch disk.
"""

from __future__ import annotations

import threading
from typing import Any

from scoreboard.infrastructure import teams as teams_infra
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.infrastructure.teams import TeamLibrary


class TeamPresets:
    """The saved-team library as the bridge needs it: in-memory, locked, no game path."""

    def __init__(self, paths: ScoreboardPaths, *, diagnostics: Diagnostics | None = None) -> None:
        self._paths = paths
        self._diagnostics = NullDiagnostics() if diagnostics is None else diagnostics
        self._lock = threading.Lock()
        # Serialises the read-modify-write of the file between two saves; kept
        # separate from ``_lock`` so disk I/O never sits under the lock the
        # ten-per-second view build takes (see save()).
        self._write_lock = threading.Lock()
        self._library: TeamLibrary = teams_infra.read_library(paths)
        # A missing file is the ordinary first run and is not worth a log
        # line; a file that could not be used, or entries that were dropped,
        # are.
        if self._library.issues:
            self._diagnostics.note(
                "TEAM_LIBRARY_FELL_BACK",
                fell_back=self._library.fell_back,
                issues=len(self._library.issues),
            )

    # --- The JavaScript-facing API ------------------------------------------

    @property
    def library(self) -> TeamLibrary:
        with self._lock:
            return self._library

    def identity(self, name: Any) -> dict[str, str] | None:
        """The saved team matching ``name``, or ``None``. A cheap dict lookup."""

        with self._lock:
            library = self._library
        preset = library.find(name)
        return None if preset is None else preset.to_dict()

    def identities(self, home_name: str, away_name: str) -> dict[str, dict[str, str] | None]:
        """The identity for each side's current name, for the view model."""

        return {"home": self.identity(home_name), "away": self.identity(away_name)}

    def state(self) -> dict[str, Any]:
        """Everything the operator's Teams drawer needs to render the library."""

        with self._lock:
            library = self._library
        return {
            "teams": [team.to_dict() for team in library.sorted()],
            "issues": [issue.to_dict() for issue in library.issues],
            "fell_back": library.fell_back,
        }

    def save(self, payload: Any) -> dict[str, Any]:
        """Validate and store one team, replacing any existing team of that name.

        The file write happens under ``_write_lock`` only, never under
        ``_lock``: ``identity()`` takes ``_lock`` from inside a view build that
        runs while the command lock is held, so a slow ``teams.json`` write
        must not be able to hold the game up (the C4 rule, applied here).
        """

        candidate_name = payload.get("name") if isinstance(payload, dict) else None
        with self._write_lock:
            was_replace = self.library.find(candidate_name) is not None
            library, issue = teams_infra.save_team(self._paths, payload)
            with self._lock:
                self._library = library
        teams = [team.to_dict() for team in library.sorted()]
        if issue is not None:
            self._diagnostics.note("TEAM_PRESET_REFUSED", code=issue.code, message=issue.message)
            return {"ok": False, "message": issue.message, "teams": teams}

        saved_name = candidate_name.strip() if isinstance(candidate_name, str) else ""
        preset = library.find(saved_name)
        display_name = preset.name if preset is not None else saved_name
        message = f"Updated team {display_name}." if was_replace else f"Saved team {display_name}."
        self._diagnostics.note("TEAM_PRESET_SAVED", name=display_name)
        return {"ok": True, "message": message, "teams": teams}

    def delete(self, name: Any) -> dict[str, Any]:
        """Remove the stored team named ``name``. Same lock discipline as :meth:`save`."""

        with self._write_lock:
            library, issue = teams_infra.delete_team(self._paths, name)
            with self._lock:
                self._library = library
        teams = [team.to_dict() for team in library.sorted()]
        if issue is not None:
            self._diagnostics.note("TEAM_PRESET_REFUSED", code=issue.code, message=issue.message)
            return {"ok": False, "message": issue.message, "teams": teams}

        display_name = name.strip() if isinstance(name, str) else str(name)
        self._diagnostics.note("TEAM_PRESET_DELETED", name=display_name)
        return {"ok": True, "message": f"Deleted team {display_name}.", "teams": teams}


__all__ = ["TeamPresets"]
