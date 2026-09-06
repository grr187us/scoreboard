"""Per-user runtime data locations resolved through the platform API.

Live state must never sit beside the installed application or inside this
repository, so replacing the application folder cannot erase a game in progress
(W-005) and no database, backup, or log can be committed by accident (P-009).

On Windows the root comes from ``SHGetKnownFolderPath(FOLDERID_LocalAppData)``
rather than a hard-coded path or a repository-relative one (P-001).
Environment variables are only a fallback for when that call is unavailable,
and the non-Windows root exists solely so these tests can run anywhere;
production is Windows.

Tests always pass an explicit temporary ``override`` and therefore never touch
the operator's real data directory.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: Directory name created inside the per-user application-data root.
APPLICATION_DIRECTORY_NAME: Final[str] = "Scoreboard"

DATABASE_FILENAME: Final[str] = "scoreboard.db"
BACKUP_FILENAME: Final[str] = "scoreboard.backup.db"
CONFIG_FILENAME: Final[str] = "config.json"
#: The presentation-layout library (spec section 5). Deliberately a separate
#: file from ``config.json`` -- see ``scoreboard.infrastructure.layouts`` for
#: why -- so it gets its own filename constant here rather than a section key.
LAYOUTS_FILENAME: Final[str] = "layouts.json"
#: The saved-team library (spec F4 section 3.1). Its own file for the same
#: reason ``layouts.json`` is separate from ``config.json`` -- see
#: ``scoreboard.infrastructure.teams`` for why.
TEAMS_FILENAME: Final[str] = "teams.json"
#: The cutscene packs folder (spec section 3): a directory, not a file, so an
#: operator can drop a pack's media in beside its manifest. Same "never touch
#: the game database" boundary as ``layouts.json``/``teams.json`` -- see
#: ``scoreboard.infrastructure.cutscene_packs`` for why.
CUTSCENES_DIRECTORY_NAME: Final[str] = "cutscenes"
#: Which pack is selected per event (spec section 3), living beside the
#: ``cutscenes`` folder rather than inside it -- an operator who empties the
#: folder to start over should not also lose their selection file by
#: accident.
CUTSCENE_SELECTION_FILENAME: Final[str] = "cutscenes.json"
LOCK_FILENAME: Final[str] = "scoreboard.lock"
LOG_DIRECTORY_NAME: Final[str] = "logs"
LOG_FILENAME: Final[str] = "application.log"

#: Escape hatch for an operator or a support session that must relocate runtime
#: data. It is read only when no explicit override is supplied.
DATA_DIRECTORY_ENVIRONMENT_VARIABLE: Final[str] = "SCOREBOARD_DATA_DIR"

#: Where an operator's chosen data folder is remembered.
#:
#: This one file deliberately stays in the *platform default* root rather than
#: in the chosen folder. A pointer stored inside the folder it points at could
#: never be found again, so the default location is always readable and holds
#: nothing but the redirection.
LOCATION_POINTER_FILENAME: Final[str] = "data-location.json"

#: ``{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}`` -- FOLDERID_LocalAppData.
_LOCAL_APP_DATA_GUID: Final[tuple[int, int, int, tuple[int, ...]]] = (
    0xF1B32785,
    0x6FBA,
    0x4FCF,
    (0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91),
)


class PathResolutionError(RuntimeError):
    """Raised when no writable per-user data location can be determined."""


def _windows_local_app_data() -> Path:
    """Ask Windows itself where this user's local application data lives."""

    import ctypes
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    data1, data2, data3, data4 = _LOCAL_APP_DATA_GUID
    folder_id = _GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4))

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    buffer = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(folder_id), 0, None, ctypes.byref(buffer)
    )
    if result != 0 or not buffer.value:
        raise PathResolutionError(
            "Windows could not report the local application-data folder "
            f"(HRESULT {result:#010x})."
        )
    try:
        return Path(buffer.value)
    finally:
        ole32.CoTaskMemFree(buffer)


def _fallback_root() -> Path:
    """Resolve a root without the platform API, for fallback and non-Windows."""

    if sys.platform == "win32":
        env_value = os.environ.get("LOCALAPPDATA")
        if env_value:
            return Path(env_value)
        return Path.home() / "AppData" / "Local"
    env_value = os.environ.get("XDG_DATA_HOME")
    if env_value:
        return Path(env_value)
    return Path.home() / ".local" / "share"


def user_data_root() -> Path:
    """The per-user application-data root that contains the Scoreboard folder."""

    if sys.platform == "win32":
        try:
            return _windows_local_app_data()
        except (OSError, AttributeError, PathResolutionError):
            # A missing or restricted shell API must not stop a game: fall back
            # to the documented environment location and keep operating.
            return _fallback_root()
    return _fallback_root()


@dataclass(frozen=True, slots=True)
class ScoreboardPaths:
    """Every runtime location the application owns, rooted outside the repo."""

    root: Path

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not root.is_absolute():
            raise PathResolutionError(
                f"runtime data root must be an absolute path; got {root!s}"
            )
        object.__setattr__(self, "root", root)

    @property
    def database(self) -> Path:
        return self.root / DATABASE_FILENAME

    @property
    def backup(self) -> Path:
        return self.root / BACKUP_FILENAME

    @property
    def config(self) -> Path:
        return self.root / CONFIG_FILENAME

    @property
    def layouts(self) -> Path:
        return self.root / LAYOUTS_FILENAME

    @property
    def teams(self) -> Path:
        return self.root / TEAMS_FILENAME

    @property
    def cutscenes(self) -> Path:
        return self.root / CUTSCENES_DIRECTORY_NAME

    @property
    def cutscene_selection(self) -> Path:
        return self.root / CUTSCENE_SELECTION_FILENAME

    @property
    def lock(self) -> Path:
        return self.root / LOCK_FILENAME

    @property
    def log_directory(self) -> Path:
        return self.root / LOG_DIRECTORY_NAME

    @property
    def log_file(self) -> Path:
        return self.log_directory / LOG_FILENAME

    def quarantine(self, source: Path, stamp: str) -> Path:
        """The preserved name for a database that failed validation (P-006)."""

        safe_stamp = "".join(
            character if character.isalnum() else "-" for character in stamp
        )
        return self.root / f"{source.stem}.invalid-{safe_stamp}{source.suffix}"

    def ensure(self) -> "ScoreboardPaths":
        """Create the data root and log directory if they do not exist."""

        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.log_directory.mkdir(parents=True, exist_ok=True)
            self.cutscenes.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PathResolutionError(
                f"could not create the runtime data directory {self.root}: {exc}"
            ) from exc
        return self

    def describe(self) -> dict[str, str]:
        """JSON-compatible locations for diagnostics and the operator view."""

        return {
            "root": str(self.root),
            "database": str(self.database),
            "backup": str(self.backup),
            "log_file": str(self.log_file),
            "teams": str(self.teams),
            "cutscenes": str(self.cutscenes),
        }


def default_root() -> Path:
    """The platform-reported location, ignoring any operator choice.

    This is where the location pointer lives, so it must be resolvable even
    when the operator has sent the game data somewhere else entirely.
    """

    return user_data_root() / APPLICATION_DIRECTORY_NAME


def location_pointer() -> Path:
    """The file remembering an operator's chosen data folder."""

    return default_root() / LOCATION_POINTER_FILENAME


def validate_root(candidate: Path | str, *, create: bool = True) -> Path:
    """Return ``candidate`` as a usable data root, or explain why it is not.

    ``create=True`` is the picker's check: the folder is made and written to
    for real, so an unusable choice is refused while the operator is standing
    at the screen rather than discovered at the next launch, possibly during a
    game.

    ``create=False`` is the startup check, and it deliberately creates nothing.
    Resolving a path must not have side effects, and a saved folder on a USB
    stick that is not plugged in today should fall back quietly rather than
    causing an empty directory to appear somewhere unexpected.
    """

    path = Path(candidate).expanduser()
    if not path.is_absolute():
        raise PathResolutionError(
            "runtime data must use an absolute path, never a relative one; "
            f"got {path!s}"
        )
    if path.exists() and not path.is_dir():
        raise PathResolutionError(f"{path} is a file, not a folder")

    if not create:
        if path.is_dir():
            if not os.access(path, os.W_OK):
                raise PathResolutionError(f"{path} cannot be written to")
            return path
        # Not there yet, but its parent is: ScoreboardPaths.ensure() will make
        # it at startup, exactly as it does for the default location.
        if path.parent.is_dir():
            return path
        raise PathResolutionError(f"{path} is not reachable: {path.parent} is missing")

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".scoreboard-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise PathResolutionError(f"{path} cannot be written to: {exc}") from exc
    return path


def read_chosen_root() -> Path | None:
    """The operator's remembered data folder, or ``None`` if none is set.

    A pointer that is missing, unreadable, malformed, or names a folder that is
    no longer reachable yields ``None``: the application falls back to the
    default location and keeps running. Refusing to start because a saved
    preference went stale would be the worst possible trade on a game night.
    """

    import json

    pointer = location_pointer()
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = payload.get("root") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return validate_root(value, create=False)
    except PathResolutionError:
        return None


def write_chosen_root(root: Path | str) -> Path:
    """Remember ``root`` as the data folder for the next launch.

    The choice deliberately takes effect at the next launch rather than
    immediately: the database connection, the instance lock, and the log
    handler are all open on the current folder, and moving them under a running
    game is a far larger and riskier operation than this feature is.
    """

    import json

    validated = validate_root(root)
    pointer = location_pointer()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(
        json.dumps({"root": str(validated)}, indent=2) + "\n", encoding="utf-8"
    )
    return validated


def clear_chosen_root() -> None:
    """Forget any chosen folder and return to the platform default."""

    try:
        location_pointer().unlink()
    except OSError:
        pass


def resolve_paths(override: Path | str | None = None) -> ScoreboardPaths:
    """Return the runtime locations, preferring an explicit override.

    Resolution order: an explicit ``override`` (used by every test), then
    :data:`DATA_DIRECTORY_ENVIRONMENT_VARIABLE`, then the folder an operator
    chose through the picker, then the platform-reported per-user
    application-data root. A relative path is refused rather than silently
    resolved against the current working directory, which could place live
    state inside the repository.

    The environment variable outranks the operator's choice on purpose: it is
    how tests and rehearsals isolate themselves, and a rehearsal must never be
    able to write into the real game folder by accident.
    """

    if override is not None:
        candidate = Path(override)
    else:
        env_value = os.environ.get(DATA_DIRECTORY_ENVIRONMENT_VARIABLE)
        if env_value:
            candidate = Path(env_value)
        else:
            chosen = read_chosen_root()
            candidate = default_root() if chosen is None else chosen
    if not candidate.is_absolute():
        raise PathResolutionError(
            "runtime data must use an absolute per-user path, never a "
            f"repository-relative one; got {candidate!s}"
        )
    return ScoreboardPaths(candidate)


def describe_resolution() -> dict[str, str | None]:
    """Where the data folder came from, in plain terms, for the operator view."""

    env_value = os.environ.get(DATA_DIRECTORY_ENVIRONMENT_VARIABLE)
    chosen = read_chosen_root()
    if env_value:
        source = "environment"
        explanation = (
            f"{DATA_DIRECTORY_ENVIRONMENT_VARIABLE} is set, so it overrides any "
            "chosen folder. This is for tests and rehearsals."
        )
    elif chosen is not None:
        source = "chosen"
        explanation = "You chose this folder. Change it with Choose folder."
    else:
        source = "default"
        explanation = "This is the standard per-user location for this laptop."
    return {
        "source": source,
        "explanation": explanation,
        "root": str(resolve_paths().root),
        "default_root": str(default_root()),
        "chosen_root": None if chosen is None else str(chosen),
        "environment_root": env_value or None,
    }


__all__ = [
    "APPLICATION_DIRECTORY_NAME",
    "BACKUP_FILENAME",
    "CONFIG_FILENAME",
    "CUTSCENES_DIRECTORY_NAME",
    "CUTSCENE_SELECTION_FILENAME",
    "DATABASE_FILENAME",
    "DATA_DIRECTORY_ENVIRONMENT_VARIABLE",
    "LAYOUTS_FILENAME",
    "LOCATION_POINTER_FILENAME",
    "LOCK_FILENAME",
    "LOG_DIRECTORY_NAME",
    "LOG_FILENAME",
    "PathResolutionError",
    "ScoreboardPaths",
    "TEAMS_FILENAME",
    "clear_chosen_root",
    "default_root",
    "describe_resolution",
    "location_pointer",
    "read_chosen_root",
    "resolve_paths",
    "user_data_root",
    "validate_root",
    "write_chosen_root",
]
