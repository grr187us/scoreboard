"""I/O for soccer cutscene packs: scanning the packs folder and the
selection file.

Mirrors :mod:`scoreboard.infrastructure.cutscene_packs` (football; frozen)
for spec section 7. The only difference from football's module is which
presentation module supplies the event vocabulary and which paths are
read/written -- ``paths`` here is expected to already be the sport-rooted
:class:`~scoreboard.infrastructure.paths.ScoreboardPaths` (``root.for_sport
("soccer")``), so ``paths.cutscenes``/``paths.cutscene_selection`` resolve to
``<root>/soccer/cutscenes/`` and ``<root>/soccer/cutscenes.json`` for free
(``ScoreboardPaths.for_sport``, spec section 2/9). This module itself never
computes a sport-specific path; it only reads the two properties every
``ScoreboardPaths`` already exposes.

Same "never touch config.json/layouts.json/teams.json/scoreboard.db"
boundary, the same "every read returns something usable, never an
exception" contract, and the same atomic temp-file + ``os.replace`` write.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Final

from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.presentation import soccer_cutscenes as cutscenes_module
from scoreboard.presentation.soccer_cutscenes import (
    SOCCER_BUILTIN_PACK_PREFIX,
    SOCCER_CUTSCENE_EVENTS,
    builtin_pack,
    validate_manifest,
)

PACK_README_FILENAME: Final[str] = "README.txt"
SELECTION_SCHEMA_VERSION: Final[int] = 1

_MANIFEST_FILENAME: Final[str] = "manifest.json"

_README_TEXT: Final[str] = """Soccer cutscene packs
======================

One folder per cutscene. The folder name is the pack id; restart is not
needed -- press Rescan in the soccer Cutscenes window after adding or
editing a folder here.

Each pack folder must contain a manifest.json shaped like this:

{
  "schema_version": 1,
  "name": "Goal -- net ripple",
  "event": "goal",
  "duration_seconds": 7,
  "intro": "none",
  "scene": {"type": "video", "src": "goal.webm", "fit": "cover", "loop": false}
}

Rules:

- schema_version must be 1.
- name is text, 1-64 characters.
- event is "goal" (the only soccer cutscene event so far).
- duration_seconds is optional (2-30 seconds; out-of-range values are
  clamped rather than rejected); if left out, 7 s is used.
- intro is optional: "claw_scratch" or "none". Left out, a goal defaults to
  "none" -- the scene is on the wall the instant the board finishes
  morphing, with no separate strike first.
- scene is required:
    - a built-in animation: {"type": "builtin", "id": "goal"}
    - a video: {"type": "video", "src": "<filename>.webm or .mp4",
      "fit": "cover" or "contain", "loop": true or false}
    - an image: {"type": "image", "src": "<filename>.png/.gif/.jpg/.jpeg/
      .webp/.apng", "fit": "cover" or "contain"}
  "src" must be a plain filename -- no folders, no ".." -- and that file
  must sit right beside this manifest.json.

A folder name may not start with "builtin:" (reserved for the app's own
built-in packs) and may not contain a slash or backslash.
"""


def _is_reserved_pack_folder_name(name: str) -> bool:
    """Identical rule to football's (see
    :func:`scoreboard.infrastructure.cutscene_packs._is_reserved_pack_folder_name`),
    copied rather than imported because the football name is private.
    """

    return name.startswith(SOCCER_BUILTIN_PACK_PREFIX) or "/" in name or "\\" in name


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Every usable pack found under the ``cutscenes`` folder, plus issues."""

    packs: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class CutsceneLibrary:
    """Every known pack (built-ins first, then scanned) and the selection."""

    packs: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...]
    selection: dict[str, str]

    def resolve(self, event: str) -> tuple[dict[str, Any], bool]:
        pack_id = self.selection.get(event)
        if pack_id is None:
            return builtin_pack(event), False
        for pack in self.packs:
            if pack["id"] == pack_id and pack["event"] == event:
                return pack, False
        return builtin_pack(event), True


def ensure_packs_directory(paths: ScoreboardPaths) -> None:
    """Create the ``cutscenes`` folder and, only if absent, write the README.

    Never raises.
    """

    try:
        paths.cutscenes.mkdir(parents=True, exist_ok=True)
        readme = paths.cutscenes / PACK_README_FILENAME
        if not readme.exists():
            readme.write_text(_README_TEXT, encoding="utf-8")
    except OSError:
        pass


def scan_packs(paths: ScoreboardPaths) -> ScanResult:
    """Scan every immediate subfolder of ``cutscenes`` for a manifest."""

    directory = paths.cutscenes
    if not directory.is_dir():
        return ScanResult((), ())

    try:
        entries = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return ScanResult((), ())

    packs: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for entry in entries:
        if not entry.is_dir():
            continue
        manifest_path = entry / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            continue

        folder_name = entry.name
        if _is_reserved_pack_folder_name(folder_name):
            issues.append(
                {
                    "pack_id": folder_name,
                    "code": "PACK_ID",
                    "message": f"The pack folder {folder_name!r} is reserved and was skipped.",
                    "severity": "error",
                }
            )
            continue

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            issues.append(
                {
                    "pack_id": folder_name,
                    "code": "MANIFEST_JSON",
                    "message": f"{folder_name}/manifest.json could not be read as JSON.",
                    "severity": "error",
                }
            )
            continue

        try:
            files = {item.name for item in entry.iterdir() if item.is_file()}
        except OSError:
            files = set()

        result = validate_manifest(payload, files=files)
        for issue in result.issues:
            issues.append({"pack_id": folder_name, **issue.to_dict()})
        if not result.ok:
            continue

        manifest = result.manifest
        scene = manifest["scene"]
        media_url = None
        if scene["type"] in ("video", "image"):
            media_url = (entry / scene["src"]).as_uri()
        pack = cutscenes_module.normalize_pack(
            folder_name, manifest, folder=str(entry), media_url=media_url
        )
        packs.append(pack)

    packs.sort(key=lambda pack: (pack["event"], str(pack["name"]).lower(), pack["id"]))
    return ScanResult(tuple(packs), tuple(issues))


#: Whether GOAL plays automatically after an accepted ``add_goal`` command
#: (spec section 7: "automatic after an accepted add_goal (switch, default
#: on)"). Football has no such switch (its cutscenes are always
#: operator-triggered), so this is stored in soccer's own selection file --
#: never in ``config.json`` -- under a new, purely additive top-level key the
#: selection-file reader/writer below preserve even when the caller only
#: touches the other one.
DEFAULT_AUTO_TRIGGER: Final[dict[str, bool]] = {"goal": True}


def _read_raw_document(paths: ScoreboardPaths) -> dict[str, Any]:
    """The selection file's raw, still-untrusted payload, or ``{}``."""

    try:
        raw_text = paths.cutscene_selection.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        payload = json.loads(raw_text)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_auto_trigger(paths: ScoreboardPaths) -> dict[str, bool]:
    """Event -> whether it plays automatically. Never raises; a missing,
    unreadable, or malformed file yields :data:`DEFAULT_AUTO_TRIGGER` (every
    event defaults on), and an individual bad entry falls back to its own
    default rather than dropping the whole mapping.
    """

    payload = _read_raw_document(paths)
    version = payload.get("schema_version")
    if isinstance(version, bool) or version != SELECTION_SCHEMA_VERSION:
        return dict(DEFAULT_AUTO_TRIGGER)

    raw = payload.get("auto_trigger")
    result = dict(DEFAULT_AUTO_TRIGGER)
    if isinstance(raw, dict):
        for event in SOCCER_CUTSCENE_EVENTS:
            value = raw.get(event)
            if isinstance(value, bool):
                result[event] = value
    return result


def write_auto_trigger(paths: ScoreboardPaths, auto_trigger: dict[str, bool]) -> bool:
    """Persist ``auto_trigger`` atomically, alongside whatever pack
    selection is already on disk. Returns whether the write succeeded.
    """

    if _is_newer_on_disk(paths):
        return False
    selection = read_selection(paths)
    document = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "selected": dict(selection),
        "auto_trigger": {
            event: bool(auto_trigger.get(event, DEFAULT_AUTO_TRIGGER[event]))
            for event in SOCCER_CUTSCENE_EVENTS
        },
    }
    return _write_document(paths, document)


def _write_document(paths: ScoreboardPaths, document: dict[str, Any]) -> bool:
    temporary = paths.cutscene_selection.with_suffix(".json.tmp")
    try:
        paths.cutscene_selection.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, paths.cutscene_selection)
        return True
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink()
        except OSError:
            pass
        return False


def _is_newer_on_disk(paths: ScoreboardPaths) -> bool:
    try:
        payload = json.loads(paths.cutscene_selection.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return False
    return version > SELECTION_SCHEMA_VERSION


def read_selection(paths: ScoreboardPaths) -> dict[str, str]:
    """Event -> pack id. Never raises."""

    payload = _read_raw_document(paths)
    if not payload:
        return {}

    version = payload.get("schema_version")
    if isinstance(version, bool) or version != SELECTION_SCHEMA_VERSION:
        return {}

    selected = payload.get("selected")
    if not isinstance(selected, dict):
        return {}

    result: dict[str, str] = {}
    for event, pack_id in selected.items():
        if event in SOCCER_CUTSCENE_EVENTS and isinstance(pack_id, str):
            result[event] = pack_id
    return result


def write_selection(paths: ScoreboardPaths, selection: dict[str, str]) -> bool:
    """Store ``selection`` atomically, preserving whatever ``auto_trigger``
    is already on disk. Returns whether the write succeeded.
    """

    if _is_newer_on_disk(paths):
        return False
    document = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "selected": dict(selection),
        "auto_trigger": read_auto_trigger(paths),
    }
    return _write_document(paths, document)


def library(paths: ScoreboardPaths) -> CutsceneLibrary:
    """Every known pack (built-ins first, one per event, then scanned) and
    the current selection.
    """

    scan = scan_packs(paths)
    selection = read_selection(paths)
    packs = tuple(builtin_pack(event) for event in SOCCER_CUTSCENE_EVENTS) + scan.packs
    return CutsceneLibrary(packs=packs, issues=scan.issues, selection=selection)


__all__ = [
    "DEFAULT_AUTO_TRIGGER",
    "PACK_README_FILENAME",
    "SELECTION_SCHEMA_VERSION",
    "CutsceneLibrary",
    "ScanResult",
    "ensure_packs_directory",
    "library",
    "read_auto_trigger",
    "read_selection",
    "scan_packs",
    "write_auto_trigger",
    "write_selection",
]
