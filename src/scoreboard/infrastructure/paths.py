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
LOCK_FILENAME: Final[str] = "scoreboard.lock"
LOG_DIRECTORY_NAME: Final[str] = "logs"
LOG_FILENAME: Final[str] = "application.log"

#: Escape hatch for an operator or a support session that must relocate runtime
#: data. It is read only when no explicit override is supplied.
DATA_DIRECTORY_ENVIRONMENT_VARIABLE: Final[str] = "SCOREBOARD_DATA_DIR"

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
        }


def resolve_paths(override: Path | str | None = None) -> ScoreboardPaths:
    """Return the runtime locations, preferring an explicit override.

    Resolution order: an explicit ``override`` (used by every test), then
    :data:`DATA_DIRECTORY_ENVIRONMENT_VARIABLE`, then the platform-reported
    per-user application-data root. A relative path is refused rather than
    silently resolved against the current working directory, which could place
    live state inside the repository.
    """

    if override is not None:
        candidate = Path(override)
    else:
        env_value = os.environ.get(DATA_DIRECTORY_ENVIRONMENT_VARIABLE)
        candidate = (
            Path(env_value)
            if env_value
            else user_data_root() / APPLICATION_DIRECTORY_NAME
        )
    if not candidate.is_absolute():
        raise PathResolutionError(
            "runtime data must use an absolute per-user path, never a "
            f"repository-relative one; got {candidate!s}"
        )
    return ScoreboardPaths(candidate)


__all__ = [
    "APPLICATION_DIRECTORY_NAME",
    "BACKUP_FILENAME",
    "CONFIG_FILENAME",
    "DATABASE_FILENAME",
    "DATA_DIRECTORY_ENVIRONMENT_VARIABLE",
    "LOCK_FILENAME",
    "LOG_DIRECTORY_NAME",
    "LOG_FILENAME",
    "PathResolutionError",
    "ScoreboardPaths",
    "resolve_paths",
    "user_data_root",
]
