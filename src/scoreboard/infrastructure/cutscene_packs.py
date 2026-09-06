"""I/O for cutscene packs: scanning the packs folder and the selection file.

Mirrors :mod:`scoreboard.infrastructure.layouts`'s style and its "never touch
``config.json``/``layouts.json``/``teams.json``/``scoreboard.db``" boundary:
a cutscene pack is a laptop preference, exactly like a saved layout or a
saved team, with its own files and its own schema versions, independent of
every other preference and of the game database.

Every read here returns something usable, never an exception: a missing
``cutscenes`` folder is the ordinary state before an operator has ever
dropped a pack in, not damage; a folder that fails to parse is one skipped
pack (with an issue recorded) rather than a reason to give up on every other
pack; a missing or unreadable selection file is simply "nothing selected"
for every event, which :class:`CutsceneLibrary.resolve` already treats as
"use the built-in".

Writes use the same atomic temp-file + ``os.replace`` pattern as
``layouts.py``/``teams.py``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Final

from scoreboard.infrastructure.paths import ScoreboardPaths
from scoreboard.presentation import cutscenes as cutscenes_module
from scoreboard.presentation.cutscenes import (
    BUILTIN_PACK_PREFIX,
    CUTSCENE_EVENTS,
    builtin_pack,
    validate_manifest,
)

PACK_README_FILENAME: Final[str] = "README.txt"
SELECTION_SCHEMA_VERSION: Final[int] = 1

_MANIFEST_FILENAME: Final[str] = "manifest.json"

_README_TEXT: Final[str] = """Cutscene packs
==============

One folder per cutscene. The folder name is the pack id; restart is not
needed -- press Rescan in the Cutscenes window after adding or editing a
folder here.

Each pack folder must contain a manifest.json shaped like this:

{
  "schema_version": 1,
  "name": "Touchdown -- roar",
  "event": "touchdown",
  "duration_seconds": 10,
  "intro": "claw_scratch",
  "scene": {"type": "video", "src": "touchdown.webm", "fit": "cover", "loop": false}
}

Rules:

- schema_version must be 1.
- name is text, 1-64 characters.
- event is "first_down", "touchdown", "turnover", "penalty" or
  "make_some_noise".
- duration_seconds is optional (2-30 seconds; out-of-range values are
  clamped rather than rejected); if left out, a sensible default is used
  (7 s first_down, 10 s touchdown, 7 s turnover, 7 s penalty,
  5 s make_some_noise).
- intro is optional: "claw_scratch" (the Tigers claw strike) or "none".
  Left out, it defaults per event: "claw_scratch" for first_down,
  touchdown and turnover, "none" for penalty (a flag on the play is
  nobody's moment) and make_some_noise (a 5 s crowd prompt has no time
  for a strike).
- scene is required:
    - a built-in animation: {"type": "builtin", "id": "first_down"},
      {"type": "builtin", "id": "touchdown"},
      {"type": "builtin", "id": "turnover"},
      {"type": "builtin", "id": "penalty"} or
      {"type": "builtin", "id": "make_some_noise"}
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
    """Whether a folder name cannot be used as a scanned pack id.

    Pulled out as its own pure check so it can be tested directly: a name
    starting with :data:`~scoreboard.presentation.cutscenes.BUILTIN_PACK_PREFIX`
    cannot even be created on Windows (``:`` is not a legal filename
    character there), so the on-disk scan can never actually exercise that
    half of the rule on this platform -- the check still guards against a
    folder copied in from elsewhere, or a future platform.
    """

    return name.startswith(BUILTIN_PACK_PREFIX) or "/" in name or "\\" in name


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
        """The selected pack for ``event``, or the built-in with
        ``fell_back=True`` when the selection names a pack that is not
        present, or is for a different event.
        """

        pack_id = self.selection.get(event)
        if pack_id is None:
            return builtin_pack(event), False
        for pack in self.packs:
            if pack["id"] == pack_id and pack["event"] == event:
                return pack, False
        return builtin_pack(event), True


def ensure_packs_directory(paths: ScoreboardPaths) -> None:
    """Create the ``cutscenes`` folder and, only if absent, write the README.

    Never raises: a laptop that cannot create this folder still starts the
    application, it simply has nowhere for scan_packs to find anything.
    """

    try:
        paths.cutscenes.mkdir(parents=True, exist_ok=True)
        readme = paths.cutscenes / PACK_README_FILENAME
        if not readme.exists():
            readme.write_text(_README_TEXT, encoding="utf-8")
    except OSError:
        pass


def scan_packs(paths: ScoreboardPaths) -> ScanResult:
    """Scan every immediate subfolder of ``cutscenes`` for a manifest.

    A missing ``cutscenes`` directory is not an error: it yields an empty
    result, the ordinary state before an operator drops anything in.
    """

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
    """Event -> pack id. Never raises; every failure yields ``{}`` (whole
    file) or drops just the offending event (a non-string value).
    """

    try:
        raw_text = paths.cutscene_selection.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        payload = json.loads(raw_text)
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}

    version = payload.get("schema_version")
    if isinstance(version, bool) or version != SELECTION_SCHEMA_VERSION:
        return {}

    selected = payload.get("selected")
    if not isinstance(selected, dict):
        return {}

    result: dict[str, str] = {}
    for event, pack_id in selected.items():
        if event in CUTSCENE_EVENTS and isinstance(pack_id, str):
            result[event] = pack_id
    return result


def write_selection(paths: ScoreboardPaths, selection: dict[str, str]) -> bool:
    """Store ``selection`` atomically. Returns whether the write succeeded.

    Never raises, and leaves a newer file already on disk untouched, the
    same trade every sibling preference file in this codebase makes.
    """

    if _is_newer_on_disk(paths):
        return False
    document = {"schema_version": SELECTION_SCHEMA_VERSION, "selected": dict(selection)}
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


def library(paths: ScoreboardPaths) -> CutsceneLibrary:
    """Every known pack (built-ins first, one per event, then scanned) and
    the current selection.
    """

    scan = scan_packs(paths)
    selection = read_selection(paths)
    packs = tuple(builtin_pack(event) for event in CUTSCENE_EVENTS) + scan.packs
    return CutsceneLibrary(packs=packs, issues=scan.issues, selection=selection)


__all__ = [
    "PACK_README_FILENAME",
    "SELECTION_SCHEMA_VERSION",
    "CutsceneLibrary",
    "ScanResult",
    "ensure_packs_directory",
    "library",
    "read_selection",
    "scan_packs",
    "write_selection",
]
