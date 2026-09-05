"""Bounded rotating diagnostic log for startup, failures, and recovery (P-008).

This is the operator's and the maintainer's record of *what the application
did*, and it is deliberately separate from the durable action history in the
SQLite database:

* the action history answers "what happened in the game" and must survive for
  audit, so it is transactional, append-only, and never rotated away;
* this log answers "what happened to the program" and is allowed to roll over,
  because a three-week-old startup line has no game-day value (R-003).

Every timestamp comes from an injected wall clock. The domain never sees this
module, and this module never reads a monotonic clock.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Final

from scoreboard.infrastructure.paths import ScoreboardPaths

#: One megabyte per file with four older files kept: enough to cover a whole
#: game plus several restarts, small enough to read and to copy off a laptop.
DEFAULT_MAX_BYTES: Final[int] = 1_000_000
DEFAULT_BACKUP_COUNT: Final[int] = 4

_LOGGER_NAME: Final[str] = "scoreboard.diagnostics"
_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(message)s"


def utc_now() -> datetime:
    """The production wall clock: timezone-aware UTC."""

    return datetime.now(timezone.utc)


def _render(event: str, fields: dict[str, Any]) -> str:
    """One line per event: an event name plus stable ``key=value`` pairs."""

    parts = [event]
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").replace("\r", " ")
        parts.append(f"{key}={text!r}" if " " in text else f"{key}={text}")
    return " ".join(parts)


class Diagnostics:
    """A small named-event API over one bounded rotating file handler.

    Callers use the named methods rather than formatting their own strings, so
    the required P-008 events stay greppable and consistently shaped.
    """

    def __init__(
        self,
        paths: ScoreboardPaths,
        *,
        wall_clock: Callable[[], datetime] | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        logger_name: str | None = None,
    ) -> None:
        self._paths = paths.ensure()
        self._wall_clock = utc_now if wall_clock is None else wall_clock
        # A per-instance logger name keeps parallel tests from sharing handlers
        # and keeps this log out of the application's root logger.
        self._logger = logging.getLogger(logger_name or f"{_LOGGER_NAME}.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._handler = RotatingFileHandler(
            self._paths.log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=False,
        )
        self._handler.setFormatter(logging.Formatter(_FORMAT))
        self._logger.handlers.clear()
        self._logger.addHandler(self._handler)

    # --- Lifecycle ----------------------------------------------------------

    @property
    def log_file(self):
        return self._paths.log_file

    def close(self) -> None:
        """Flush and release the file handle.

        Windows keeps an open log file locked, so a clean shutdown and every
        test that removes a temporary directory must call this.
        """

        self._handler.flush()
        self._logger.removeHandler(self._handler)
        self._handler.close()

    def flush(self) -> None:
        self._handler.flush()

    def __enter__(self) -> "Diagnostics":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # --- Required P-008 events ---------------------------------------------

    def startup(self, *, app_version: str, **fields: Any) -> None:
        self._logger.info(
            _render("STARTUP", {"app_version": app_version, **self._locations(), **fields})
        )

    def shutdown(self, *, reason: str = "clean", **fields: Any) -> None:
        self._logger.info(_render("SHUTDOWN", {"reason": reason, **fields}))

    def recovery(self, *, source: str, message: str, **fields: Any) -> None:
        self._logger.info(
            _render("RECOVERY", {"source": source, "message": message, **fields})
        )

    def display_opened(self, *, target: str, **fields: Any) -> None:
        self._logger.info(_render("DISPLAY_OPENED", {"target": target, **fields}))

    def display_closed(self, *, reason: str, **fields: Any) -> None:
        self._logger.info(_render("DISPLAY_CLOSED", {"reason": reason, **fields}))

    def data_folder_choice(self, *, outcome: str, root: str, **fields: Any) -> None:
        """An operator opened the data-folder picker (P-008).

        Where a game is saved is exactly the kind of thing nobody remembers
        changing three weeks later, so the change and its outcome are recorded
        even when the operator cancelled.
        """

        self._logger.info(
            _render("DATA_FOLDER_CHOICE", {"outcome": outcome, "root": root, **fields})
        )

    def clock_expired(self, *, clock: str, **fields: Any) -> None:
        """A clock counted itself down to 0:00 (F-037, F-046).

        The durable record lives in the action history; this line is the
        program-level trace beside the start that preceded it.
        """

        self._logger.info(_render("CLOCK_EXPIRED", {"clock": clock, **fields}))

    def command_rejected(self, *, command: str, code: str, message: str, **fields: Any) -> None:
        self._logger.warning(
            _render(
                "COMMAND_REJECTED",
                {"command": command, "code": code, "message": message, **fields},
            )
        )

    def persistence_failure(self, *, operation: str, error: str, **fields: Any) -> None:
        self._logger.error(
            _render("PERSISTENCE_FAILURE", {"operation": operation, "error": error, **fields})
        )

    def persistence_recovered(self, *, operation: str, **fields: Any) -> None:
        """A previously failing write succeeded again; the warning can clear."""

        self._logger.info(_render("PERSISTENCE_RECOVERED", {"operation": operation, **fields}))

    def unhandled_error(self, *, context: str, error: BaseException | str, **fields: Any) -> None:
        self._logger.error(
            _render("UNHANDLED_ERROR", {"context": context, "error": error, **fields}),
            exc_info=isinstance(error, BaseException),
        )

    def instance_refused(self, *, reason: str, **fields: Any) -> None:
        """A second authoritative instance was refused this data directory (R-004)."""

        self._logger.warning(_render("INSTANCE_REFUSED", {"reason": reason, **fields}))

    def note(self, event: str, **fields: Any) -> None:
        """An event that is real but has no dedicated required shape."""

        self._logger.info(_render(event, fields))

    # --- Internals ----------------------------------------------------------

    def _locations(self) -> dict[str, Any]:
        return {"data_root": self._paths.root}


class NullDiagnostics(Diagnostics):
    """A diagnostics object that opens no file.

    Used by tests and by pure call sites that accept an optional logger, so
    callers never need ``if diagnostics is not None`` around every event.
    """

    def __init__(self) -> None:  # noqa: D107 - deliberately does not call super
        self._logger = logging.getLogger(f"{_LOGGER_NAME}.null")
        self._logger.addHandler(logging.NullHandler())
        self._logger.propagate = False

    @property
    def log_file(self) -> None:
        return None

    def close(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def _locations(self) -> dict[str, Any]:
        return {}


__all__ = [
    "DEFAULT_BACKUP_COUNT",
    "DEFAULT_MAX_BYTES",
    "Diagnostics",
    "NullDiagnostics",
    "utc_now",
]
