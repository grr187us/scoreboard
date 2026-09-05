"""Presentation-only concerns: how the spectator board looks, not what it says.

Nothing in this package is authoritative game state. It owns the layout schema
that positions and styles the spectator board's widgets (:mod:`layout`); it has
no I/O of its own (see :mod:`scoreboard.infrastructure.layouts` for that) and no
path back into :mod:`scoreboard.domain.commands`.
"""

from __future__ import annotations
