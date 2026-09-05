"""Human-readable local-time display for operator-facing timestamps.

Every timestamp the application stores or logs is an unambiguous UTC ISO 8601
string (see :mod:`scoreboard.infrastructure.diagnostics`), and nothing here
changes that. This module is a *display-only* conversion used where an
operator reads a timestamp -- the recovery screen's "Last saved" line, and the
equivalent non-interactive command-line message -- so they can compare it
against a clock in the stadium without doing the UTC arithmetic themselves.

The stadium is in the Eastern time zone, so the conversion target is fixed at
the IANA zone ``America/New_York``. One zone name is the whole daylight-saving
policy: it already encodes the correct Eastern Daylight/Standard Time
(EDT/EST) transition dates for every year, so no separate "is it EDT or EST
today" branch exists anywhere in this codebase. Windows does not ship the IANA
time zone database, so :mod:`zoneinfo` needs the ``tzdata`` package (pinned in
``pyproject.toml``) to resolve the zone offline; this module never fetches
anything over a network (R-001).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final
from zoneinfo import ZoneInfo

#: The stadium's local time zone for operator-facing display.
DISPLAY_ZONE_NAME: Final[str] = "America/New_York"

_MONTH_NAMES: Final[tuple[str, ...]] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Every timestamp this application writes is already UTC-aware
        # (diagnostics.utc_now()); a naive value here would only come from
        # hand-edited or foreign data. Treat it as UTC rather than guessing
        # the reader's zone, since UTC is what this application ever writes.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_local_timestamp(
    value: str | datetime | None, *, zone_name: str = DISPLAY_ZONE_NAME
) -> str | None:
    """Render a stored UTC timestamp as human-readable local time.

    ``value`` is normally the ISO 8601 string this application stores
    (``diagnostics.utc_now().isoformat()``); a timezone-aware or naive
    ``datetime`` is also accepted directly. Returns ``None`` for ``None``
    input, so a caller's existing ``timestamp or "unavailable"`` fallback
    keeps working unchanged.

    A value that cannot be parsed as a timestamp is returned unchanged rather
    than raising: this function sits on an operator-facing display path, and a
    malformed timestamp is not a reason to hide the rest of the recovery
    screen (the same "an optional display failure must not stop core
    operation" principle applied to the spectator window in R-002).
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        parsed: datetime | None = (
            value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        )
    else:
        parsed = _parse(value)
    if parsed is None:
        return value if isinstance(value, str) else str(value)

    local = parsed.astimezone(ZoneInfo(zone_name))
    hour12 = local.hour % 12 or 12
    period = "AM" if local.hour < 12 else "PM"
    month = _MONTH_NAMES[local.month - 1]
    return (
        f"{month} {local.day}, {local.year} at "
        f"{hour12}:{local.minute:02d} {period} {local.tzname()}"
    )


__all__ = ["DISPLAY_ZONE_NAME", "format_local_timestamp"]
