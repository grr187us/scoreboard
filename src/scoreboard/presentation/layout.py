"""The spectator presentation-layout schema: where and how, never what.

This module is pure -- no file I/O, no clock, no game state, no exceptions
that a caller must catch to stay safe. That last property matters more than it
would in an ordinary module: a layout is edited live, by an operator, in a
window that must never be able to affect the game, so every function here is
built to be called with genuinely arbitrary input and still return something
usable.

**Coordinate model** (spec section 4.1): ``x``/``y``/``width``/``height`` are
fractions of the logical 16:9 canvas -- ``x``/``width`` of its width, ``y``/
``height`` of its height -- so the same layout document means the same thing
at 1280x720 or on a 20-foot LED wall. ``font_scale`` is *also* a fraction of
the canvas **width** rather than height or some absolute pixel size, which
matches the CSS the spectator board already used before this schema existed
(``calc(var(--canvas-width) * .12)``): today's type sizes carry over exactly
rather than shifting the moment they become editable.

**Why validation is strict** (spec section 4.6): a layout is not authoritative
game state, but it is still something an operator will look at during a live
broadcast, so a value that is out of range, the wrong type, outside the safe
area, or a serious overlap is treated as an *error* -- the whole document is
rejected rather than partially trusted. Only things that cannot possibly hurt
the picture -- an unrecognized widget id, an unrecognized property inside a
known widget, a merely decorative overlap, or an id that is simply absent --
are *warnings*: the value is dropped or filled from the default and the rest
of the document is still used. This is what lets a layout file written by a
future version, or hand-edited into something almost-but-not-quite right, keep
working instead of losing an operator's whole layout over one bad field.

**Why ``z_index`` exists at all**: overlap is *tolerated* (a label sitting
close beside its value, for instance), so which widget draws on top of the
other cannot be left to DOM order -- that would make stacking depend on
:data:`WIDGET_IDS`' declaration order, which is an implementation detail, not
something an operator chose. An explicit, saved ``z_index`` makes stacking
order a property of the layout itself.

**Schema v2** (spec section 1) adds three things without touching any of the
above: a ``background`` for the whole board, ten optional style properties on
every widget (font, letter spacing, transform, effect, fill, border, corner
radius, padding), and a list of freestanding ``elements`` (text, image, box)
an operator can add, move, and style but never bind to a game value. A
version-1 document upgrades silently into this shape -- every new property
takes its default -- with one warning so the operator knows to re-save.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, replace
from typing import Any, Collection, Final, Mapping

# --- Schema constants (spec section 4, extended by v2 spec section 1,
# extended again by v3 spec section 1 [pre-game/halftime screens]) ---------

LAYOUT_SCHEMA_VERSION: Final[int] = 3
#: schema_version values a document may declare; anything else is refused.
_ACCEPTED_SCHEMA_VERSIONS: Final[tuple[int, ...]] = (1, 2, 3)
DEFAULT_LAYOUT_NAME: Final[str] = "Default"

WIDGET_IDS: Final[tuple[str, ...]] = (
    "home_name", "home_score", "possession", "away_name", "away_score",
    "game_clock_label", "game_clock_value",
    "quarter", "down", "distance",
    "play_clock_label", "play_clock_value", "ball_on",
    "home_timeouts", "away_timeouts",
    # F3 (crowd-facing game-state messages): a crowd message ("FLAG",
    # "TIMEOUT", "INJURY", "DELAY", or nothing) and its countdown, added at
    # the end so every stored v3 layout that predates them is simply
    # "missing two widgets" -- MISSING_WIDGET already treats that as a
    # warning to fill from the default, never an error (see validate_layout).
    "status_message", "status_clock",
)

# --- Screens (spec v3 section 1.1) ------------------------------------------
#: A "screen" is one of the three boards a layout document can describe. A
#: "kind" (below) names which *widget registry* a screen draws from.
SCREEN_IDS: Final[tuple[str, ...]] = ("game", "pregame", "halftime")
EVENT_SCREEN_IDS: Final[tuple[str, ...]] = ("pregame", "halftime")
SCREEN_LABELS: Final[dict[str, str]] = {
    "game": "Game", "pregame": "Pre-game", "halftime": "Halftime",
}
SCREEN_KINDS: Final[dict[str, str]] = {
    "game": "game", "pregame": "event", "halftime": "event",
}
WIDGET_KINDS: Final[tuple[str, ...]] = ("game", "event")

TEXT_ALIGNMENTS: Final[tuple[str, ...]] = ("left", "center", "right")
VERTICAL_ALIGNMENTS: Final[tuple[str, ...]] = ("top", "middle", "bottom")
FONT_WEIGHTS: Final[tuple[int, ...]] = (400, 500, 600, 700, 800, 900)

MIN_WIDGET_WIDTH: Final[float] = 0.02
MIN_WIDGET_HEIGHT: Final[float] = 0.02
#: Fraction of the logical canvas WIDTH -- see the module docstring.
MIN_FONT_SCALE: Final[float] = 0.010
MAX_FONT_SCALE: Final[float] = 0.300
MIN_Z_INDEX: Final[int] = 0
MAX_Z_INDEX: Final[int] = 100
MIN_SAFE_INSET: Final[float] = 0.0
MAX_SAFE_INSET: Final[float] = 0.20
#: ``1 - left - right`` and ``1 - top - bottom`` must each be at least this.
MIN_SAFE_SPAN: Final[float] = 0.50
DEFAULT_SAFE_INSET: Final[float] = 0.04
#: intersection / min(area) at or above this ratio is a serious (error-level)
#: overlap; anything below it is tolerated as a warning.
SERIOUS_OVERLAP_RATIO: Final[float] = 0.25
#: Coordinates are rounded to this many decimals whenever they are normalized.
COORDINATE_PRECISION: Final[int] = 4
#: A value this close to a bound counts as touching it, not crossing it
#: (float arithmetic on ``1 - left - right`` lands a hair off the exact edge).
_BOUNDARY_TOLERANCE: Final[float] = 1e-6

#: v2 widget/text style ranges (spec section 1.3 / 1.6).
MIN_LETTER_SPACING: Final[float] = -0.05
MAX_LETTER_SPACING: Final[float] = 0.30
MAX_BORDER_WIDTH: Final[float] = 0.02
MAX_CORNER_RADIUS: Final[float] = 0.10
MAX_PADDING: Final[float] = 0.05
MIN_OPACITY: Final[float] = 0.05

#: v2 element limits (spec section 1.4 / 1.6).
MAX_ELEMENTS: Final[int] = 24
MAX_TEXT_LENGTH: Final[int] = 120
MAX_TEXT_LINES: Final[int] = 4
MAX_IMAGE_BYTES: Final[int] = 2_000_000
MAX_TOTAL_IMAGE_BYTES: Final[int] = 6_000_000

TEXT_TRANSFORMS: Final[tuple[str, ...]] = ("none", "uppercase")
TEXT_EFFECTS: Final[tuple[str, ...]] = ("none", "shadow", "outline")
IMAGE_FITS: Final[tuple[str, ...]] = ("contain", "cover", "fill")
ELEMENT_TYPES: Final[tuple[str, ...]] = ("text", "image", "box")

#: Windows system fonts only -- nothing is ever downloaded (spec section 1.5).
FONT_FAMILIES: Final[dict[str, str]] = {
    "arial": "Arial, Helvetica, sans-serif",
    "arial_black": "'Arial Black', Arial, sans-serif",
    "impact": "Impact, 'Arial Black', sans-serif",
    "bahnschrift": "Bahnschrift, 'Segoe UI', Arial, sans-serif",
    "segoe": "'Segoe UI', Segoe, Arial, sans-serif",
    "segoe_black": "'Segoe UI Black', 'Segoe UI', Arial, sans-serif",
    "consolas": "Consolas, 'Courier New', monospace",
    "georgia": "Georgia, 'Times New Roman', serif",
    "verdana": "Verdana, Geneva, sans-serif",
    "trebuchet": "'Trebuchet MS', Arial, sans-serif",
}
FONT_FAMILY_LABELS: Final[dict[str, str]] = {
    "arial": "Arial", "arial_black": "Arial Black", "impact": "Impact",
    "bahnschrift": "Bahnschrift", "segoe": "Segoe UI", "segoe_black": "Segoe UI Black",
    "consolas": "Consolas", "georgia": "Georgia", "verdana": "Verdana",
    "trebuchet": "Trebuchet MS",
}

#: Not part of the public schema constants above, but the same "1-40, no
#: control characters" limit :data:`scoreboard.infrastructure.layouts.
#: MAX_LAYOUT_NAME_LENGTH` enforces for a *stored* layout's name. It lives
#: here too because :func:`validate_layout_name` -- used for a layout
#: document's own ``name`` field -- must stay in this dependency-free module
#: rather than importing the infrastructure layer that depends on it.
_MAX_LAYOUT_NAME_LENGTH: Final[int] = 40

#: The v1 widget properties plus the ten v2 style properties (spec 1.3).
_KNOWN_WIDGET_PROPERTIES: Final[frozenset[str]] = frozenset({
    "id", "visible", "x", "y", "width", "height", "font_scale", "color",
    "text_align", "vertical_align", "font_weight", "z_index",
    "font_family", "letter_spacing", "text_transform", "text_effect",
    "background", "background_opacity", "border_color", "border_width",
    "corner_radius", "padding",
})

_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_ELEMENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_IMAGE_SRC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)$"
)

# --- Widget metadata (spec section 4.3, groups added by v2 spec 1.3) -------

WIDGET_LABELS: Final[dict[str, str]] = {
    "home_name": "Home team name",
    "home_score": "Home score",
    "possession": "Possession",
    "away_name": "Away team name",
    "away_score": "Away score",
    "game_clock_label": "Game clock label",
    "game_clock_value": "Game clock",
    "quarter": "Quarter",
    "down": "Down",
    "distance": "Distance to go",
    "play_clock_label": "Play clock label",
    "play_clock_value": "Play clock",
    "ball_on": "Ball on",
    "home_timeouts": "Home timeouts",
    "away_timeouts": "Away timeouts",
    "status_message": "Crowd message",
    "status_clock": "Status countdown",
}

#: Dotted path into the spectator view model. ``None`` means a static label.
WIDGET_FIELDS: Final[dict[str, str | None]] = {
    "home_name": "teams.home.name",
    "home_score": "teams.home.score",
    "possession": "football.possession_display",
    "away_name": "teams.away.name",
    "away_score": "teams.away.score",
    "game_clock_label": None,
    "game_clock_value": "clocks.game.display",
    "quarter": "quarter_display",
    "down": "football.down_display",
    "distance": "football.distance_display",
    "play_clock_label": None,
    "play_clock_value": "clocks.play.display",
    "ball_on": "football.ball_on_display",
    "home_timeouts": "football.home_timeouts_display",
    "away_timeouts": "football.away_timeouts_display",
    # F3: another worker adds this "status" block to the spectator view model
    # in parallel -- this module only ever names the dotted path, never
    # builds the block itself, so the two stay decoupled and buildable in
    # either order.
    "status_message": "status.display",
    "status_clock": "status.clock_display",
}

#: Application-controlled label text. Operators may style/move/hide it, never
#: edit it -- there is no free-text editor on a widget (spec section 1).
WIDGET_TEXTS: Final[dict[str, str]] = {
    "game_clock_label": "GAME CLOCK",
    "play_clock_label": "PLAY CLOCK",
}

#: Widgets whose value can legitimately be absent from a snapshot. When the
#: field is missing or its rendered text is empty, the renderer hides the
#: widget rather than drawing an empty box (graceful, non-fatal).
OPTIONAL_WIDGET_IDS: Final[frozenset[str]] = frozenset({
    "possession", "down", "distance", "ball_on",
    "home_timeouts", "away_timeouts",
    # F3: both are optional so the renderer hides them the instant their text
    # is empty -- which is the *only* thing keeping a crowd message off the
    # wall before an operator ever raises one, since "status.display"/
    # "status.clock_display" resolve to "" rather than being absent outright
    # once the other half of F3 adds the "status" block (format_game_status/
    # format_status_clock never raise; they return "" for "nothing to say").
    "status_message", "status_clock",
})

#: Which rail group each widget belongs to in the editor (spec section 1.3).
WIDGET_GROUPS: Final[dict[str, str]] = {
    "home_name": "Teams", "home_score": "Teams", "possession": "Teams",
    "away_name": "Teams", "away_score": "Teams",
    "game_clock_label": "Clocks", "game_clock_value": "Clocks",
    "play_clock_label": "Clocks", "play_clock_value": "Clocks", "quarter": "Clocks",
    "down": "Field", "distance": "Field", "ball_on": "Field",
    "home_timeouts": "Field", "away_timeouts": "Field",
    "status_message": "Status", "status_clock": "Status",
}
WIDGET_GROUP_ORDER: Final[tuple[str, ...]] = ("Teams", "Clocks", "Field", "Status")

# --- Event widget metadata (spec v3 section 1.1): the pre-game/halftime -----
# registry. Same shape as the game metadata above, one "event" widget set
# shared by both event screens (only geometry/visibility differ per screen).

EVENT_WIDGET_IDS: Final[tuple[str, ...]] = (
    "home_name", "home_score", "away_name", "away_score",
    "event_phase", "event_title", "event_clock", "warmup",
)
EVENT_WIDGET_LABELS: Final[dict[str, str]] = {
    "home_name": "Home team name", "home_score": "Home score",
    "away_name": "Away team name", "away_score": "Away score",
    "event_phase": "Phase label", "event_title": "Countdown title",
    "event_clock": "Countdown", "warmup": "Warmup line",
}
EVENT_WIDGET_FIELDS: Final[dict[str, str | None]] = {
    "home_name": "teams.home.name", "home_score": "teams.home.score",
    "away_name": "teams.away.name", "away_score": "teams.away.score",
    "event_phase": "clocks.event.phase", "event_title": "clocks.event.title",
    "event_clock": "clocks.event.display", "warmup": "clocks.event.warmup_display",
}
#: No static labels on event screens -- every event widget draws a real value.
EVENT_WIDGET_TEXTS: Final[dict[str, str]] = {}
#: Hidden when the value is empty/None (spec v3 section 1.1).
EVENT_OPTIONAL_WIDGET_IDS: Final[frozenset[str]] = frozenset({"warmup"})
EVENT_WIDGET_GROUPS: Final[dict[str, str]] = {
    "home_name": "Teams", "home_score": "Teams", "away_name": "Teams",
    "away_score": "Teams", "event_phase": "Countdown", "event_title": "Countdown",
    "event_clock": "Countdown", "warmup": "Countdown",
}
EVENT_WIDGET_GROUP_ORDER: Final[tuple[str, ...]] = ("Teams", "Countdown")


@dataclass(frozen=True, slots=True)
class WidgetRegistry:
    """One widget set -- "game" or "event" -- and everything a validator or
    the editor needs to know about it (spec v3 section 1.1). The existing
    module-level ``WIDGET_*`` names stay the public surface for the game
    registry; this dataclass just lets validation and descriptor code be
    written once and parameterized by kind instead of duplicated per kind.
    """

    ids: tuple[str, ...]
    labels: dict[str, str]
    fields: dict[str, str | None]
    texts: dict[str, str]
    optional: frozenset[str]
    groups: dict[str, str]
    group_order: tuple[str, ...]


WIDGET_REGISTRIES: Final[dict[str, WidgetRegistry]] = {
    "game": WidgetRegistry(
        WIDGET_IDS, WIDGET_LABELS, WIDGET_FIELDS, WIDGET_TEXTS,
        OPTIONAL_WIDGET_IDS, WIDGET_GROUPS, WIDGET_GROUP_ORDER,
    ),
    "event": WidgetRegistry(
        EVENT_WIDGET_IDS, EVENT_WIDGET_LABELS, EVENT_WIDGET_FIELDS, EVENT_WIDGET_TEXTS,
        EVENT_OPTIONAL_WIDGET_IDS, EVENT_WIDGET_GROUPS, EVENT_WIDGET_GROUP_ORDER,
    ),
}


def registry_for(kind: str) -> WidgetRegistry:
    """The :class:`WidgetRegistry` for ``kind`` (``"game"`` or ``"event"``)."""

    return WIDGET_REGISTRIES[kind]


# --- Element metadata (spec section 1.4) ------------------------------------

#: Properties every element may declare, regardless of type.
_BASE_ELEMENT_PROPERTIES: Final[frozenset[str]] = frozenset({
    "id", "type", "visible", "x", "y", "width", "height", "z_index", "opacity",
    "background", "background_opacity", "border_color", "border_width", "corner_radius",
})
#: A text element additionally carries the full text style set.
_TEXT_ELEMENT_PROPERTIES: Final[frozenset[str]] = _BASE_ELEMENT_PROPERTIES | frozenset({
    "text", "color", "font_scale", "font_family", "font_weight", "letter_spacing",
    "text_transform", "text_effect", "text_align", "vertical_align", "padding",
})
#: An image element additionally carries its source and fit mode.
_IMAGE_ELEMENT_PROPERTIES: Final[frozenset[str]] = _BASE_ELEMENT_PROPERTIES | frozenset({
    "src", "fit",
})
#: A box element is nothing but its background/border/radius.
_BOX_ELEMENT_PROPERTIES: Final[frozenset[str]] = _BASE_ELEMENT_PROPERTIES

#: Fallback geometry used only when an element's own x/y/width/height cannot
#: be read at all -- a modest, centred box that is always safe-area legal.
_DEFAULT_ELEMENT_GEOMETRY: Final[dict[str, float]] = {
    "x": 0.35, "y": 0.35, "width": 0.30, "height": 0.30,
}

# --- Shared v2 style defaults (spec section 1.3) ----------------------------

#: The ten new widget-style properties and their defaults. Also used, in
#: whole or in part, for element styling: a text element's font/letter-
#: spacing/transform/effect/padding set and every element's fill/border set
#: share these exact defaults (spec section 1.4 says "as in 1.3").
_STYLE_DEFAULTS: Final[dict[str, Any]] = {
    "font_family": "arial",
    "letter_spacing": 0.0,
    "text_transform": "none",
    "text_effect": "none",
    "background": None,
    "background_opacity": 1.0,
    "border_color": None,
    "border_width": 0.0,
    "corner_radius": 0.0,
    "padding": 0.0,
}

# --- Default layout geometry (spec section 4.4, styled by v2 section 1.3) --

#: These preserve the current spectator arrangement exactly as specified.
#: ``game_clock_label``, ``home_timeouts``, and ``away_timeouts`` default to
#: **hidden**, because the current spectator board draws none of them --
#: making them positionable without turning them on preserves today's
#: appearance by default. Overlap detection only ever looks at *visible*
#: widgets (see :func:`validate_layout`), which is why these three may sit in
#: otherwise-used space without ever producing a warning.
_DEFAULT_WIDGETS: Final[dict[str, dict[str, Any]]] = {
    "home_name": {
        "id": "home_name", "visible": True,
        "x": 0.040, "y": 0.040, "width": 0.380, "height": 0.118,
        "font_scale": 0.028, "color": "#FFFFFF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 700, "z_index": 0,
    },
    "home_score": {
        "id": "home_score", "visible": True,
        "x": 0.040, "y": 0.164, "width": 0.380, "height": 0.242,
        "font_scale": 0.112, "color": "#FFFFFF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 700, "z_index": 0,
    },
    "possession": {
        "id": "possession", "visible": True,
        "x": 0.430, "y": 0.071, "width": 0.140, "height": 0.056,
        "font_scale": 0.026, "color": "#57E6A4",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 700, "z_index": 0,
    },
    "away_name": {
        "id": "away_name", "visible": True,
        "x": 0.580, "y": 0.040, "width": 0.380, "height": 0.118,
        "font_scale": 0.028, "color": "#FFFFFF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 700, "z_index": 0,
    },
    "away_score": {
        "id": "away_score", "visible": True,
        "x": 0.580, "y": 0.164, "width": 0.380, "height": 0.242,
        "font_scale": 0.112, "color": "#FFFFFF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 700, "z_index": 0,
    },
    "game_clock_label": {
        "id": "game_clock_label", "visible": False,
        "x": 0.400, "y": 0.412, "width": 0.200, "height": 0.052,
        "font_scale": 0.024, "color": "#CFCFCF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "game_clock_value": {
        "id": "game_clock_value", "visible": True,
        "x": 0.040, "y": 0.470, "width": 0.920, "height": 0.200,
        "font_scale": 0.093, "color": "#FFFFFF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "quarter": {
        "id": "quarter", "visible": True,
        "x": 0.040, "y": 0.699, "width": 0.440, "height": 0.126,
        "font_scale": 0.058, "color": "#FFFFFF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "down": {
        "id": "down", "visible": True,
        "x": 0.110, "y": 0.875, "width": 0.150, "height": 0.059,
        "font_scale": 0.027, "color": "#CFCFCF",
        "text_align": "right", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "distance": {
        "id": "distance", "visible": True,
        # Set off from `down` by a real gap: the two are separate widgets, and
        # a right-aligned "3rd" butted against a left-aligned "& 7" reads as
        # "3rd& 7". The gap is the word space the single combined line used to
        # provide for free.
        "x": 0.272, "y": 0.875, "width": 0.150, "height": 0.059,
        "font_scale": 0.027, "color": "#CFCFCF",
        "text_align": "left", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "play_clock_label": {
        "id": "play_clock_label", "visible": True,
        "x": 0.500, "y": 0.733, "width": 0.210, "height": 0.059,
        "font_scale": 0.027, "color": "#FFFFFF",
        "text_align": "right", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "play_clock_value": {
        "id": "play_clock_value", "visible": True,
        "x": 0.718, "y": 0.678, "width": 0.242, "height": 0.168,
        "font_scale": 0.078, "color": "#FFFFFF",
        "text_align": "left", "vertical_align": "middle",
        "font_weight": 700, "z_index": 0,
    },
    "ball_on": {
        "id": "ball_on", "visible": True,
        "x": 0.480, "y": 0.854, "width": 0.480, "height": 0.101,
        "font_scale": 0.024, "color": "#CFCFCF",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "home_timeouts": {
        "id": "home_timeouts", "visible": False,
        "x": 0.040, "y": 0.412, "width": 0.200, "height": 0.052,
        "font_scale": 0.024, "color": "#CFCFCF",
        "text_align": "left", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    "away_timeouts": {
        "id": "away_timeouts", "visible": False,
        "x": 0.760, "y": 0.412, "width": 0.200, "height": 0.052,
        "font_scale": 0.024, "color": "#CFCFCF",
        "text_align": "right", "vertical_align": "middle",
        "font_weight": 400, "z_index": 0,
    },
    # F3 (crowd-facing game-state messages): the two free gaps of the band
    # between the score block (ends y=0.406) and the game clock (starts
    # y=0.470) -- one on either side of the three visible:False defaults that
    # already live in that band (home_timeouts x 0.040-0.240, game_clock_label
    # x 0.400-0.600, away_timeouts x 0.760-0.960). status_message sits in the
    # left gap (x 0.240-0.400), status_clock in the right gap (x 0.600-0.760),
    # both y 0.408-0.464 -- verified disjoint (zero intersection area, not
    # merely under the serious-overlap ratio) from every other default
    # widget's rectangle, visible or not, so an operator who later turns the
    # timeouts or the clock label on never gets a surprise overlap error.
    "status_message": {
        "id": "status_message", "visible": True,
        "x": 0.240, "y": 0.408, "width": 0.160, "height": 0.056,
        "font_scale": 0.026, "color": "#FFC845",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 800, "z_index": 0,
    },
    "status_clock": {
        "id": "status_clock", "visible": True,
        "x": 0.600, "y": 0.408, "width": 0.160, "height": 0.056,
        "font_scale": 0.026, "color": "#FFC845",
        "text_align": "center", "vertical_align": "middle",
        "font_weight": 800, "z_index": 0,
    },
}

#: Every widget also carries the v2 style defaults (spec section 1.3), so the
#: built-in default renders pixel-identical to v1 (Arial, no backgrounds, no
#: effects) while still being a complete v2 document.
for _widget in _DEFAULT_WIDGETS.values():
    _widget.update(_STYLE_DEFAULTS)
del _widget

# --- Default event-screen widgets (spec v3 section 1.2) ---------------------
#: Shared geometry for both event screens -- only ``visible`` differs between
#: the pre-game and halftime screen (spec table, section 1.2). Reproduces
#: today's centred event board: title, big countdown, score line; the phase
#: label and warmup line only ever show at halftime.
_EVENT_WIDGET_GEOMETRY: Final[dict[str, dict[str, Any]]] = {
    "event_phase": {"x": 0.30, "y": 0.05, "width": 0.40, "height": 0.09,
                     "font_scale": 0.045, "font_weight": 700, "text_align": "center",
                     "pregame_visible": False, "halftime_visible": True},
    "event_title": {"x": 0.10, "y": 0.15, "width": 0.80, "height": 0.10,
                     "font_scale": 0.050, "font_weight": 400, "text_align": "center",
                     "pregame_visible": True, "halftime_visible": True},
    "event_clock": {"x": 0.10, "y": 0.26, "width": 0.80, "height": 0.32,
                     "font_scale": 0.140, "font_weight": 700, "text_align": "center",
                     "pregame_visible": True, "halftime_visible": True},
    "warmup": {"x": 0.25, "y": 0.59, "width": 0.50, "height": 0.07,
               "font_scale": 0.035, "font_weight": 400, "text_align": "center",
               "pregame_visible": False, "halftime_visible": True},
    "home_name": {"x": 0.04, "y": 0.72, "width": 0.30, "height": 0.12,
                  "font_scale": 0.024, "font_weight": 700, "text_align": "right",
                  "pregame_visible": True, "halftime_visible": True},
    "home_score": {"x": 0.35, "y": 0.70, "width": 0.12, "height": 0.16,
                   "font_scale": 0.070, "font_weight": 700, "text_align": "center",
                   "pregame_visible": True, "halftime_visible": True},
    "away_score": {"x": 0.53, "y": 0.70, "width": 0.12, "height": 0.16,
                   "font_scale": 0.070, "font_weight": 700, "text_align": "center",
                   "pregame_visible": True, "halftime_visible": True},
    "away_name": {"x": 0.66, "y": 0.72, "width": 0.30, "height": 0.12,
                  "font_scale": 0.024, "font_weight": 700, "text_align": "left",
                  "pregame_visible": True, "halftime_visible": True},
}


def _build_default_event_widget(widget_id: str, screen_id: str) -> dict[str, Any]:
    geometry = _EVENT_WIDGET_GEOMETRY[widget_id]
    visible = geometry["pregame_visible"] if screen_id == "pregame" else geometry["halftime_visible"]
    widget: dict[str, Any] = {
        "id": widget_id, "visible": visible,
        "x": geometry["x"], "y": geometry["y"],
        "width": geometry["width"], "height": geometry["height"],
        "font_scale": geometry["font_scale"], "color": "#FFFFFF",
        "text_align": geometry["text_align"], "vertical_align": "middle",
        "font_weight": geometry["font_weight"], "z_index": 0,
    }
    widget.update(_STYLE_DEFAULTS)
    return widget


#: Every event widget's default, per event screen (spec v3 section 1.2).
_DEFAULT_EVENT_WIDGETS: Final[dict[str, dict[str, dict[str, Any]]]] = {
    screen_id: {
        widget_id: _build_default_event_widget(widget_id, screen_id)
        for widget_id in EVENT_WIDGET_IDS
    }
    for screen_id in EVENT_SCREEN_IDS
}

_DEFAULT_SAFE_AREA: Final[dict[str, float]] = {
    "top": DEFAULT_SAFE_INSET, "right": DEFAULT_SAFE_INSET,
    "bottom": DEFAULT_SAFE_INSET, "left": DEFAULT_SAFE_INSET,
}

_DEFAULT_BACKGROUND: Final[dict[str, str]] = {"color": "#000000"}


# --- Issues and results ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    """One problem found in a layout document, or one repair made to it.

    ``message`` always names the affected widget or element in words an
    operator can act on -- its :data:`WIDGET_LABELS` text for a widget, or
    :func:`element_label`'s text for an element -- never a raw internal id.
    ``widget_id`` carries that id when there is one (a widget id, or an
    element's own id) so a UI can select the affected item; it is ``None``
    for document-wide issues.

    ``screen`` (spec v3 section 1.3) names which screen (``"game"``,
    ``"pregame"``, or ``"halftime"``) the issue was raised inside; it is
    ``None`` for a document-wide issue (``SCHEMA_VERSION``, ``LAYOUT_NAME``,
    ``SCREENS``, ``UNKNOWN_SCREEN``...) that is not about any one screen.
    """

    code: str
    message: str
    widget_id: str | None = None
    severity: str = "error"
    screen: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "widget_id": self.widget_id,
            "severity": self.severity,
            "screen": self.screen,
        }


@dataclass(frozen=True, slots=True)
class LayoutValidation:
    """The result of validating one layout document."""

    layout: dict[str, Any] | None
    errors: tuple[LayoutIssue, ...]
    warnings: tuple[LayoutIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "layout": self.layout,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }


# --- Small numeric/color helpers --------------------------------------------


def _is_finite_number(value: Any) -> tuple[bool, float]:
    """``bool`` is never accepted where a number is expected."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, 0.0
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return False, 0.0
    return True, number


def _normalize_color(value: Any) -> str | None:
    """Uppercase 6-digit hex, or ``None`` if ``value`` is not a valid color.

    Named colours, ``rgb()``, and alpha are all rejected -- only the exact
    ``#RGB``/``#RRGGBB`` shapes survive.
    """

    if not isinstance(value, str) or not _COLOR_PATTERN.match(value):
        return None
    digits = value[1:]
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    return f"#{digits.upper()}"


def _round_coordinate(value: float) -> float:
    return round(value, COORDINATE_PRECISION)


def _clamp_number(
    value: Any, minimum: float, maximum: float, fallback: float
) -> tuple[float, bool]:
    """Clamp ``value`` into ``[minimum, maximum]``; report whether it moved."""

    ok, number = _is_finite_number(value)
    if not ok:
        return _round_coordinate(fallback), True
    # A bound computed as ``1 - left - right`` can land a hair below the value
    # of a widget that exactly touches it (0.9199999999999999 against 0.92).
    # Snapping to the bound is right; *reporting* that as an adjustment is
    # not -- validate_layout uses the same tolerance and calls it inside.
    if number < minimum:
        return _round_coordinate(minimum), minimum - number > _BOUNDARY_TOLERANCE
    if number > maximum:
        return _round_coordinate(maximum), number - maximum > _BOUNDARY_TOLERANCE
    return _round_coordinate(number), False


def _rect_overlap_ratio(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Intersection area over the smaller widget's area, or ``0`` if disjoint."""

    ax0, ay0 = a["x"], a["y"]
    ax1, ay1 = ax0 + a["width"], ay0 + a["height"]
    bx0, by0 = b["x"], b["y"]
    bx1, by1 = bx0 + b["width"], by0 + b["height"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    intersection = ix * iy
    if intersection <= 0.0:
        return 0.0
    smaller_area = min(a["width"] * a["height"], b["width"] * b["height"])
    if smaller_area <= 0.0:
        return 0.0
    return intersection / smaller_area


# --- Name validation ---------------------------------------------------------


def validate_layout_name(name: Any) -> LayoutIssue | None:
    """Whether ``name`` can be a layout name: 1-40 trimmed characters, no
    control characters. Returns ``None`` when it is fine to use.
    """

    if not isinstance(name, str):
        return LayoutIssue("LAYOUT_NAME", f"A layout name must be text; got {name!r}.")
    trimmed = name.strip()
    if not trimmed:
        return LayoutIssue("LAYOUT_NAME", "A layout name must not be empty.")
    if len(trimmed) > _MAX_LAYOUT_NAME_LENGTH:
        return LayoutIssue(
            "LAYOUT_NAME",
            f"A layout name must be at most {_MAX_LAYOUT_NAME_LENGTH} characters.",
        )
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in trimmed):
        return LayoutIssue("LAYOUT_NAME", "A layout name may not contain control characters.")
    return None


# --- Safe area ---------------------------------------------------------------


def _validate_safe_area(raw: Any) -> tuple[dict[str, float], list[LayoutIssue]]:
    """Read the safe area, saying out loud whenever a default was supplied.

    A layout with no safe area at all, or with only some of its four edges, is
    usable -- the missing edges take the documented default -- but it is never
    accepted *silently*. Filling an edge the operator did not write changes
    where every widget is allowed to sit, so it is reported as a warning for
    the same reason a missing widget is (``MISSING_WIDGET``).
    """

    errors: list[LayoutIssue] = []
    if raw is None:
        errors.append(
            LayoutIssue(
                "SAFE_AREA",
                f"This layout has no safe area, so the standard "
                f"{DEFAULT_SAFE_INSET:.0%} margin was used on all four sides.",
                severity="warning",
            )
        )
        return dict(_DEFAULT_SAFE_AREA), errors
    if not isinstance(raw, dict):
        errors.append(LayoutIssue("SAFE_AREA", "The safe area must be an object."))
        return dict(_DEFAULT_SAFE_AREA), errors

    absent = [side for side in ("top", "right", "bottom", "left") if side not in raw]
    if absent:
        errors.append(
            LayoutIssue(
                "SAFE_AREA",
                f"The safe area did not set its {', '.join(absent)} "
                f"{'inset' if len(absent) == 1 else 'insets'}, so the standard "
                f"{DEFAULT_SAFE_INSET:.0%} margin was used there.",
                severity="warning",
            )
        )

    result: dict[str, float] = {}
    for side in ("top", "right", "bottom", "left"):
        value = raw.get(side, DEFAULT_SAFE_INSET)
        ok, number = _is_finite_number(value)
        if not ok:
            errors.append(
                LayoutIssue("SAFE_AREA", f"The safe area's {side} inset must be a number; got {value!r}.")
            )
            result[side] = DEFAULT_SAFE_INSET
            continue
        if not MIN_SAFE_INSET <= number <= MAX_SAFE_INSET:
            errors.append(
                LayoutIssue(
                    "SAFE_AREA",
                    f"The safe area's {side} inset must be between {MIN_SAFE_INSET} "
                    f"and {MAX_SAFE_INSET}; got {number!r}.",
                )
            )
            result[side] = DEFAULT_SAFE_INSET
        else:
            result[side] = _round_coordinate(number)

    if 1.0 - result["left"] - result["right"] < MIN_SAFE_SPAN - 1e-9:
        errors.append(
            LayoutIssue(
                "SAFE_AREA_SPAN",
                f"The safe area's left and right insets leave less than "
                f"{MIN_SAFE_SPAN} of horizontal space.",
            )
        )
    if 1.0 - result["top"] - result["bottom"] < MIN_SAFE_SPAN - 1e-9:
        errors.append(
            LayoutIssue(
                "SAFE_AREA_SPAN",
                f"The safe area's top and bottom insets leave less than "
                f"{MIN_SAFE_SPAN} of vertical space.",
            )
        )
    return result, errors


# --- Background (spec section 1.2) ------------------------------------------


def _validate_background(raw: Any) -> tuple[dict[str, str], list[LayoutIssue]]:
    """Read the whole-board background, same "default with a warning versus
    an outright error" treatment as the safe area (spec section 1.2).
    """

    if raw is None:
        return dict(_DEFAULT_BACKGROUND), [
            LayoutIssue(
                "MISSING_BACKGROUND",
                f"This layout has no background, so {_DEFAULT_BACKGROUND['color']} was used.",
                severity="warning",
            )
        ]
    if not isinstance(raw, dict):
        return dict(_DEFAULT_BACKGROUND), [
            LayoutIssue("BACKGROUND", "The background must be an object.")
        ]
    color = _normalize_color(raw.get("color"))
    if color is None:
        return dict(_DEFAULT_BACKGROUND), [
            LayoutIssue(
                "BACKGROUND",
                f"The background colour must be a hex color like #RRGGBB; got {raw.get('color')!r}.",
            )
        ]
    return {"color": color}, []


# --- Shared v2 style validation (spec section 1.3) --------------------------


def _validate_fill_and_border(
    raw: Mapping[str, Any],
    label: str,
    subject_id: str | None,
    defaults: Mapping[str, Any],
    errors: list[LayoutIssue],
) -> dict[str, Any]:
    """``background``, ``background_opacity``, ``border_color``,
    ``border_width``, and ``corner_radius`` -- shared by every widget and
    every element (spec sections 1.3 and 1.4).
    """

    result: dict[str, Any] = {}

    value = raw.get("background", defaults["background"])
    if value is None:
        result["background"] = None
    else:
        color = _normalize_color(value)
        if color is None:
            errors.append(
                LayoutIssue(
                    "BACKGROUND",
                    f"{label}: background must be null or a hex color like #RRGGBB; got {value!r}.",
                    subject_id,
                )
            )
            result["background"] = defaults["background"]
        else:
            result["background"] = color

    value = raw.get("background_opacity", defaults["background_opacity"])
    ok, number = _is_finite_number(value)
    if not ok or not 0.0 <= number <= 1.0:
        errors.append(
            LayoutIssue(
                "BACKGROUND_OPACITY",
                f"{label}: background_opacity must be between 0.0 and 1.0; got {value!r}.",
                subject_id,
            )
        )
        result["background_opacity"] = defaults["background_opacity"]
    else:
        result["background_opacity"] = _round_coordinate(number)

    value = raw.get("border_color", defaults["border_color"])
    if value is None:
        result["border_color"] = None
    else:
        color = _normalize_color(value)
        if color is None:
            errors.append(
                LayoutIssue(
                    "BORDER_COLOR",
                    f"{label}: border_color must be null or a hex color like #RRGGBB; got {value!r}.",
                    subject_id,
                )
            )
            result["border_color"] = defaults["border_color"]
        else:
            result["border_color"] = color

    value = raw.get("border_width", defaults["border_width"])
    ok, number = _is_finite_number(value)
    if not ok or not 0.0 <= number <= MAX_BORDER_WIDTH:
        errors.append(
            LayoutIssue(
                "BORDER_WIDTH",
                f"{label}: border_width must be between 0.0 and {MAX_BORDER_WIDTH}; got {value!r}.",
                subject_id,
            )
        )
        result["border_width"] = defaults["border_width"]
    else:
        result["border_width"] = _round_coordinate(number)

    value = raw.get("corner_radius", defaults["corner_radius"])
    ok, number = _is_finite_number(value)
    if not ok or not 0.0 <= number <= MAX_CORNER_RADIUS:
        errors.append(
            LayoutIssue(
                "CORNER_RADIUS",
                f"{label}: corner_radius must be between 0.0 and {MAX_CORNER_RADIUS}; got {value!r}.",
                subject_id,
            )
        )
        result["corner_radius"] = defaults["corner_radius"]
    else:
        result["corner_radius"] = _round_coordinate(number)

    return result


def _validate_text_extra_style(
    raw: Mapping[str, Any],
    label: str,
    subject_id: str | None,
    defaults: Mapping[str, Any],
    errors: list[LayoutIssue],
) -> dict[str, Any]:
    """``font_family``, ``letter_spacing``, ``text_transform``,
    ``text_effect``, and ``padding`` -- every widget, and a text element
    (spec sections 1.3 and 1.4).
    """

    result: dict[str, Any] = {}

    value = raw.get("font_family", defaults["font_family"])
    if value not in FONT_FAMILIES:
        errors.append(
            LayoutIssue(
                "FONT_FAMILY",
                f"{label}: font_family must be one of {list(FONT_FAMILIES)}; got {value!r}.",
                subject_id,
            )
        )
        result["font_family"] = defaults["font_family"]
    else:
        result["font_family"] = value

    value = raw.get("letter_spacing", defaults["letter_spacing"])
    ok, number = _is_finite_number(value)
    if not ok or not MIN_LETTER_SPACING <= number <= MAX_LETTER_SPACING:
        errors.append(
            LayoutIssue(
                "LETTER_SPACING",
                f"{label}: letter_spacing must be between {MIN_LETTER_SPACING} and "
                f"{MAX_LETTER_SPACING}; got {value!r}.",
                subject_id,
            )
        )
        result["letter_spacing"] = defaults["letter_spacing"]
    else:
        result["letter_spacing"] = _round_coordinate(number)

    value = raw.get("text_transform", defaults["text_transform"])
    if value not in TEXT_TRANSFORMS:
        errors.append(
            LayoutIssue(
                "TEXT_TRANSFORM",
                f"{label}: text_transform must be one of {list(TEXT_TRANSFORMS)}; got {value!r}.",
                subject_id,
            )
        )
        result["text_transform"] = defaults["text_transform"]
    else:
        result["text_transform"] = value

    value = raw.get("text_effect", defaults["text_effect"])
    if value not in TEXT_EFFECTS:
        errors.append(
            LayoutIssue(
                "TEXT_EFFECT",
                f"{label}: text_effect must be one of {list(TEXT_EFFECTS)}; got {value!r}.",
                subject_id,
            )
        )
        result["text_effect"] = defaults["text_effect"]
    else:
        result["text_effect"] = value

    value = raw.get("padding", defaults["padding"])
    ok, number = _is_finite_number(value)
    if not ok or not 0.0 <= number <= MAX_PADDING:
        errors.append(
            LayoutIssue(
                "PADDING",
                f"{label}: padding must be between 0.0 and {MAX_PADDING}; got {value!r}.",
                subject_id,
            )
        )
        result["padding"] = defaults["padding"]
    else:
        result["padding"] = _round_coordinate(number)

    return result


# --- Widget validation --------------------------------------------------------


def _validate_widget(
    widget_id: str, raw: Any, safe_area: Mapping[str, float],
    registry: WidgetRegistry, defaults: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[LayoutIssue], list[LayoutIssue]]:
    label = registry.labels[widget_id]
    default = defaults[widget_id]
    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    if not isinstance(raw, dict):
        errors.append(
            LayoutIssue("WIDGET_ID", f"{label}: the widget entry must be an object.", widget_id)
        )
        return None, errors, warnings

    id_value = raw.get("id", widget_id)
    if id_value != widget_id:
        errors.append(
            LayoutIssue(
                "WIDGET_ID", f"{label}: id must be {widget_id!r}; got {id_value!r}.", widget_id
            )
        )

    for key in raw:
        if key not in _KNOWN_WIDGET_PROPERTIES:
            warnings.append(
                LayoutIssue(
                    "UNKNOWN_PROPERTY",
                    f"{label}: unknown property {key!r} was ignored.",
                    widget_id,
                    severity="warning",
                )
            )

    normalized: dict[str, Any] = {"id": widget_id}

    visible = raw.get("visible", default["visible"])
    if not isinstance(visible, bool):
        errors.append(
            LayoutIssue("VISIBLE", f"{label}: visible must be true or false; got {visible!r}.", widget_id)
        )
        normalized["visible"] = default["visible"]
    else:
        normalized["visible"] = visible

    for coordinate in ("x", "y"):
        value = raw.get(coordinate, default[coordinate])
        ok, number = _is_finite_number(value)
        if not ok or not 0.0 <= number <= 1.0:
            errors.append(
                LayoutIssue(
                    "COORDINATE",
                    f"{label}: {coordinate} must be between 0 and 1; got {value!r}.",
                    widget_id,
                )
            )
            normalized[coordinate] = default[coordinate]
        else:
            normalized[coordinate] = _round_coordinate(number)

    for dimension, minimum in (("width", MIN_WIDGET_WIDTH), ("height", MIN_WIDGET_HEIGHT)):
        value = raw.get(dimension, default[dimension])
        ok, number = _is_finite_number(value)
        if not ok or not 0.0 <= number <= 1.0:
            errors.append(
                LayoutIssue(
                    "DIMENSION",
                    f"{label}: {dimension} must be between 0 and 1; got {value!r}.",
                    widget_id,
                )
            )
            normalized[dimension] = default[dimension]
        elif number < minimum:
            errors.append(
                LayoutIssue(
                    "MIN_DIMENSION",
                    f"{label}: {dimension} must be at least {minimum}; got {number!r}.",
                    widget_id,
                )
            )
            normalized[dimension] = default[dimension]
        else:
            normalized[dimension] = _round_coordinate(number)

    value = raw.get("font_scale", default["font_scale"])
    ok, number = _is_finite_number(value)
    if not ok or not MIN_FONT_SCALE <= number <= MAX_FONT_SCALE:
        errors.append(
            LayoutIssue(
                "FONT_SCALE",
                f"{label}: font_scale must be between {MIN_FONT_SCALE} and "
                f"{MAX_FONT_SCALE}; got {value!r}.",
                widget_id,
            )
        )
        normalized["font_scale"] = default["font_scale"]
    else:
        normalized["font_scale"] = _round_coordinate(number)

    value = raw.get("color", default["color"])
    color = _normalize_color(value)
    if color is None:
        errors.append(
            LayoutIssue(
                "COLOR", f"{label}: color must be a hex color like #RRGGBB; got {value!r}.", widget_id
            )
        )
        normalized["color"] = default["color"]
    else:
        normalized["color"] = color

    value = raw.get("text_align", default["text_align"])
    if value not in TEXT_ALIGNMENTS:
        errors.append(
            LayoutIssue(
                "TEXT_ALIGN",
                f"{label}: text_align must be one of {list(TEXT_ALIGNMENTS)}; got {value!r}.",
                widget_id,
            )
        )
        normalized["text_align"] = default["text_align"]
    else:
        normalized["text_align"] = value

    value = raw.get("vertical_align", default["vertical_align"])
    if value not in VERTICAL_ALIGNMENTS:
        errors.append(
            LayoutIssue(
                "VERTICAL_ALIGN",
                f"{label}: vertical_align must be one of {list(VERTICAL_ALIGNMENTS)}; got {value!r}.",
                widget_id,
            )
        )
        normalized["vertical_align"] = default["vertical_align"]
    else:
        normalized["vertical_align"] = value

    value = raw.get("font_weight", default["font_weight"])
    if isinstance(value, bool) or value not in FONT_WEIGHTS:
        errors.append(
            LayoutIssue(
                "FONT_WEIGHT",
                f"{label}: font_weight must be one of {list(FONT_WEIGHTS)}; got {value!r}.",
                widget_id,
            )
        )
        normalized["font_weight"] = default["font_weight"]
    else:
        normalized["font_weight"] = value

    value = raw.get("z_index", default["z_index"])
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_Z_INDEX <= value <= MAX_Z_INDEX:
        errors.append(
            LayoutIssue(
                "Z_INDEX",
                f"{label}: z_index must be between {MIN_Z_INDEX} and {MAX_Z_INDEX}; got {value!r}.",
                widget_id,
            )
        )
        normalized["z_index"] = default["z_index"]
    else:
        normalized["z_index"] = value

    # v2 style properties (spec section 1.3): same shared helpers an element
    # uses, so a widget and a text element are validated identically.
    normalized.update(_validate_fill_and_border(raw, label, widget_id, default, errors))
    normalized.update(_validate_text_extra_style(raw, label, widget_id, default, errors))

    tolerance = 1e-6
    left, top = safe_area["left"], safe_area["top"]
    right, bottom = safe_area["right"], safe_area["bottom"]
    x, y = normalized["x"], normalized["y"]
    width, height = normalized["width"], normalized["height"]
    if x < left - tolerance:
        errors.append(
            LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the left safe-area edge.", widget_id)
        )
    if y < top - tolerance:
        errors.append(
            LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the top safe-area edge.", widget_id)
        )
    if x + width > 1.0 - right + tolerance:
        errors.append(
            LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the right safe-area edge.", widget_id)
        )
    if y + height > 1.0 - bottom + tolerance:
        errors.append(
            LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the bottom safe-area edge.", widget_id)
        )

    return normalized, errors, warnings


def _check_overlaps(
    widgets: Mapping[str, dict[str, Any]], registry: WidgetRegistry,
) -> tuple[list[LayoutIssue], list[LayoutIssue]]:
    """Overlap is checked among **visible** widgets only (spec section 4.4):
    a hidden widget cannot visually collide with anything. Elements never
    take part in this check at all (spec section 1.4): a full-bleed backdrop
    behind everything else is the main reason they exist.
    """

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []
    ids = list(registry.ids)
    for i, first_id in enumerate(ids):
        first = widgets[first_id]
        if not first.get("visible"):
            continue
        for second_id in ids[i + 1 :]:
            second = widgets[second_id]
            if not second.get("visible"):
                continue
            ratio = _rect_overlap_ratio(first, second)
            if ratio <= 0.0:
                continue
            message = f"{registry.labels[first_id]} and {registry.labels[second_id]} overlap."
            if ratio >= SERIOUS_OVERLAP_RATIO:
                errors.append(LayoutIssue("OVERLAP", message, first_id))
            else:
                warnings.append(LayoutIssue("OVERLAP", message, first_id, severity="warning"))
    return errors, warnings


# --- Elements (spec section 1.4) --------------------------------------------


def element_label(element: Mapping[str, Any]) -> str:
    """Name ``element`` the way an operator would read it in an issue or a
    layers-rail row: ``Text "…"``, ``Image <id>``, or ``Box <id>``.

    Accepts a raw (possibly not-yet-valid) element mapping, so it can be used
    while still assembling validation messages.
    """

    element_type = element.get("type")
    element_id = element.get("id")
    element_id = element_id if isinstance(element_id, str) and element_id else "?"
    if element_type == "text":
        text = element.get("text")
        text = text if isinstance(text, str) else ""
        # A label is read in a one-line issue or rail row; and this may be
        # raw, not-yet-validated text, so it must never carry an unbounded
        # string into every message built from it.
        limit = 40
        if len(text) > limit:
            text = text[: limit - 1] + "…"
        return f'Text "{text}"'
    if element_type == "image":
        return f"Image {element_id}"
    if element_type == "box":
        return f"Box {element_id}"
    return f"Element {element_id}"


def _validate_element_text(value: Any, label: str) -> tuple[str, list[LayoutIssue]]:
    errors: list[LayoutIssue] = []
    if not isinstance(value, str):
        errors.append(LayoutIssue("TEXT", f"{label}: text must be a string; got {value!r}."))
        return "", errors

    stripped = value.strip()
    if not 1 <= len(stripped) <= MAX_TEXT_LENGTH:
        errors.append(
            LayoutIssue(
                "TEXT",
                f"{label}: text must be 1-{MAX_TEXT_LENGTH} characters after trimming; "
                f"got {len(stripped)}.",
            )
        )
        return stripped, errors

    if stripped.count("\n") > MAX_TEXT_LINES - 1:
        errors.append(
            LayoutIssue("TEXT", f"{label}: text may have at most {MAX_TEXT_LINES} lines.")
        )
        return stripped, errors

    for character in stripped:
        if character != "\n" and (ord(character) < 0x20 or ord(character) == 0x7F):
            errors.append(
                LayoutIssue("TEXT", f"{label}: text may not contain control characters.")
            )
            return stripped, errors

    return stripped, errors


def _validate_image_src(value: Any, label: str) -> tuple[str, int | None, list[LayoutIssue]]:
    errors: list[LayoutIssue] = []
    if not isinstance(value, str):
        errors.append(LayoutIssue("IMAGE_SRC", f"{label}: src must be a data URI; got {value!r}."))
        return "", None, errors

    match = _IMAGE_SRC_PATTERN.match(value)
    if not match:
        errors.append(
            LayoutIssue(
                "IMAGE_SRC",
                f"{label}: src must be a data:image/(png|jpeg|gif|webp);base64,... URI.",
            )
        )
        return "", None, errors

    media_type, encoded = match.group(1), match.group(2)
    # Base64 carries 3 bytes per 4 characters, so the encoded length alone
    # says when an image cannot possibly fit; refuse it before decoding it.
    if len(encoded) > (MAX_IMAGE_BYTES * 4) // 3 + 4:
        errors.append(
            LayoutIssue(
                "IMAGE_TOO_LARGE",
                f"{label}: the image is over the {MAX_IMAGE_BYTES}-byte limit.",
            )
        )
        return "", None, errors
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception:
        errors.append(LayoutIssue("IMAGE_SRC", f"{label}: src's image data could not be decoded."))
        return "", None, errors

    magic_ok = (
        (media_type == "png" and decoded[:4] == b"\x89PNG")
        or (media_type == "jpeg" and decoded[:3] == b"\xff\xd8\xff")
        or (media_type == "gif" and decoded[:4] == b"GIF8")
        or (media_type == "webp" and decoded[:4] == b"RIFF" and decoded[8:12] == b"WEBP")
    )
    if not magic_ok:
        errors.append(
            LayoutIssue("IMAGE_SRC", f"{label}: src's data does not match its declared image type.")
        )
        return "", len(decoded), errors

    if len(decoded) > MAX_IMAGE_BYTES:
        errors.append(
            LayoutIssue(
                "IMAGE_TOO_LARGE",
                f"{label}: the image is {len(decoded)} bytes, over the {MAX_IMAGE_BYTES}-byte limit.",
            )
        )
        return value, len(decoded), errors

    return value, len(decoded), errors


def _validate_element(
    index: int, raw: Any, safe_area: Mapping[str, float], widget_ids: Collection[str]
) -> tuple[dict[str, Any], list[LayoutIssue], list[LayoutIssue], str | None, int | None]:
    """Validate one raw element entry.

    Always returns a usable normalized dict -- unlike :func:`_validate_widget`
    it never returns ``None`` -- because the caller only ever uses the
    normalized elements when the *whole* document has no errors at all, at
    which point every individual element must already have validated clean.
    The fourth return value is the element's own id (``None`` if it could not
    be read), used by the caller to catch duplicates and widget-id collisions.
    """

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []
    placeholder = f"Element #{index + 1}"

    if not isinstance(raw, dict):
        errors.append(LayoutIssue("ELEMENT_TYPE", f"{placeholder}: the element entry must be an object."))
        return {"id": f"_invalid_{index}", "type": "box"}, errors, warnings, None, None

    element_type = raw.get("type")
    if element_type not in ELEMENT_TYPES:
        errors.append(
            LayoutIssue(
                "ELEMENT_TYPE",
                f"{placeholder}: type must be one of {list(ELEMENT_TYPES)}; got {element_type!r}.",
            )
        )
        normalized_type = "box"
    else:
        normalized_type = element_type

    id_value = raw.get("id")
    element_id_for_issues = id_value if isinstance(id_value, str) else None
    if not isinstance(id_value, str) or not _ELEMENT_ID_PATTERN.match(id_value):
        errors.append(
            LayoutIssue(
                "ELEMENT_ID",
                f"{placeholder}: id must match ^[a-z][a-z0-9_]{{0,39}}$; got {id_value!r}.",
                element_id_for_issues,
            )
        )
    elif id_value in widget_ids:
        errors.append(
            LayoutIssue(
                "ELEMENT_ID",
                f"{placeholder}: id {id_value!r} is already used by a widget.",
                element_id_for_issues,
            )
        )

    label = element_label({"type": normalized_type, "id": id_value, "text": raw.get("text")})

    known_properties = {
        "text": _TEXT_ELEMENT_PROPERTIES,
        "image": _IMAGE_ELEMENT_PROPERTIES,
        "box": _BOX_ELEMENT_PROPERTIES,
    }[normalized_type]
    for key in raw:
        if key not in known_properties:
            warnings.append(
                LayoutIssue(
                    "UNKNOWN_PROPERTY",
                    f"{label}: unknown property {key!r} was ignored.",
                    element_id_for_issues,
                    severity="warning",
                )
            )

    normalized: dict[str, Any] = {
        "id": id_value if isinstance(id_value, str) else f"_invalid_{index}",
        "type": normalized_type,
    }

    visible = raw.get("visible", True)
    if not isinstance(visible, bool):
        errors.append(
            LayoutIssue("VISIBLE", f"{label}: visible must be true or false; got {visible!r}.", element_id_for_issues)
        )
        normalized["visible"] = True
    else:
        normalized["visible"] = visible

    for coordinate in ("x", "y"):
        value = raw.get(coordinate, _DEFAULT_ELEMENT_GEOMETRY[coordinate])
        ok, number = _is_finite_number(value)
        if not ok or not 0.0 <= number <= 1.0:
            errors.append(
                LayoutIssue(
                    "COORDINATE",
                    f"{label}: {coordinate} must be between 0 and 1; got {value!r}.",
                    element_id_for_issues,
                )
            )
            normalized[coordinate] = _DEFAULT_ELEMENT_GEOMETRY[coordinate]
        else:
            normalized[coordinate] = _round_coordinate(number)

    for dimension, minimum in (("width", MIN_WIDGET_WIDTH), ("height", MIN_WIDGET_HEIGHT)):
        value = raw.get(dimension, _DEFAULT_ELEMENT_GEOMETRY[dimension])
        ok, number = _is_finite_number(value)
        if not ok or not 0.0 <= number <= 1.0:
            errors.append(
                LayoutIssue(
                    "DIMENSION",
                    f"{label}: {dimension} must be between 0 and 1; got {value!r}.",
                    element_id_for_issues,
                )
            )
            normalized[dimension] = _DEFAULT_ELEMENT_GEOMETRY[dimension]
        elif number < minimum:
            errors.append(
                LayoutIssue(
                    "MIN_DIMENSION",
                    f"{label}: {dimension} must be at least {minimum}; got {number!r}.",
                    element_id_for_issues,
                )
            )
            normalized[dimension] = _DEFAULT_ELEMENT_GEOMETRY[dimension]
        else:
            normalized[dimension] = _round_coordinate(number)

    value = raw.get("z_index", 0)
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_Z_INDEX <= value <= MAX_Z_INDEX:
        errors.append(
            LayoutIssue(
                "Z_INDEX",
                f"{label}: z_index must be between {MIN_Z_INDEX} and {MAX_Z_INDEX}; got {value!r}.",
                element_id_for_issues,
            )
        )
        normalized["z_index"] = 0
    else:
        normalized["z_index"] = value

    value = raw.get("opacity", 1.0)
    ok, number = _is_finite_number(value)
    if not ok or not MIN_OPACITY <= number <= 1.0:
        errors.append(
            LayoutIssue(
                "OPACITY",
                f"{label}: opacity must be between {MIN_OPACITY} and 1.0; got {value!r}.",
                element_id_for_issues,
            )
        )
        normalized["opacity"] = 1.0
    else:
        normalized["opacity"] = _round_coordinate(number)

    normalized.update(
        _validate_fill_and_border(raw, label, element_id_for_issues, _STYLE_DEFAULTS, errors)
    )

    image_bytes: int | None = None
    if normalized_type == "text":
        normalized.update(
            _validate_text_extra_style(raw, label, element_id_for_issues, _STYLE_DEFAULTS, errors)
        )

        value = raw.get("color", "#FFFFFF")
        color = _normalize_color(value)
        if color is None:
            errors.append(
                LayoutIssue(
                    "COLOR", f"{label}: color must be a hex color like #RRGGBB; got {value!r}.", element_id_for_issues
                )
            )
            normalized["color"] = "#FFFFFF"
        else:
            normalized["color"] = color

        value = raw.get("font_scale", 0.03)
        ok, number = _is_finite_number(value)
        if not ok or not MIN_FONT_SCALE <= number <= MAX_FONT_SCALE:
            errors.append(
                LayoutIssue(
                    "FONT_SCALE",
                    f"{label}: font_scale must be between {MIN_FONT_SCALE} and {MAX_FONT_SCALE}; got {value!r}.",
                    element_id_for_issues,
                )
            )
            normalized["font_scale"] = 0.03
        else:
            normalized["font_scale"] = _round_coordinate(number)

        value = raw.get("font_weight", 700)
        if isinstance(value, bool) or value not in FONT_WEIGHTS:
            errors.append(
                LayoutIssue(
                    "FONT_WEIGHT",
                    f"{label}: font_weight must be one of {list(FONT_WEIGHTS)}; got {value!r}.",
                    element_id_for_issues,
                )
            )
            normalized["font_weight"] = 700
        else:
            normalized["font_weight"] = value

        value = raw.get("text_align", "center")
        if value not in TEXT_ALIGNMENTS:
            errors.append(
                LayoutIssue(
                    "TEXT_ALIGN",
                    f"{label}: text_align must be one of {list(TEXT_ALIGNMENTS)}; got {value!r}.",
                    element_id_for_issues,
                )
            )
            normalized["text_align"] = "center"
        else:
            normalized["text_align"] = value

        value = raw.get("vertical_align", "middle")
        if value not in VERTICAL_ALIGNMENTS:
            errors.append(
                LayoutIssue(
                    "VERTICAL_ALIGN",
                    f"{label}: vertical_align must be one of {list(VERTICAL_ALIGNMENTS)}; got {value!r}.",
                    element_id_for_issues,
                )
            )
            normalized["vertical_align"] = "middle"
        else:
            normalized["vertical_align"] = value

        text_value, text_errors = _validate_element_text(raw.get("text"), label)
        errors.extend(text_errors)
        normalized["text"] = text_value

    elif normalized_type == "image":
        src_value, decoded_bytes, src_errors = _validate_image_src(raw.get("src"), label)
        errors.extend(src_errors)
        normalized["src"] = src_value
        image_bytes = decoded_bytes

        fit = raw.get("fit", "contain")
        if fit not in IMAGE_FITS:
            errors.append(
                LayoutIssue(
                    "IMAGE_FIT",
                    f"{label}: fit must be one of {list(IMAGE_FITS)}; got {fit!r}.",
                    element_id_for_issues,
                )
            )
            normalized["fit"] = "contain"
        else:
            normalized["fit"] = fit

    # box: nothing beyond the base properties already handled above.

    x, y = normalized["x"], normalized["y"]
    width, height = normalized["width"], normalized["height"]
    tolerance = 1e-6
    if normalized_type == "text":
        left, top = safe_area["left"], safe_area["top"]
        right, bottom = safe_area["right"], safe_area["bottom"]
        if (
            x < left - tolerance
            or y < top - tolerance
            or x + width > 1.0 - right + tolerance
            or y + height > 1.0 - bottom + tolerance
        ):
            errors.append(
                LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the safe area.", element_id_for_issues)
            )
    else:
        if x < -tolerance or y < -tolerance or x + width > 1.0 + tolerance or y + height > 1.0 + tolerance:
            errors.append(
                LayoutIssue("OUTSIDE_CANVAS", f"{label}: it extends past the edge of the canvas.", element_id_for_issues)
            )

    return normalized, errors, warnings, element_id_for_issues, image_bytes


def _clamp_element(raw: Any, safe_area: Mapping[str, float]) -> dict[str, Any] | None:
    """Best-effort geometry repair for one element (spec section 1.4): every
    non-geometry property passes through untouched; an element with no usable
    ``id``/``type`` is dropped rather than guessed at.
    """

    if not isinstance(raw, dict):
        return None
    element_id = raw.get("id")
    element_type = raw.get("type")
    if not isinstance(element_id, str) or not _ELEMENT_ID_PATTERN.match(element_id):
        return None
    if element_type not in ELEMENT_TYPES:
        return None

    clamped = dict(raw)
    clamped["id"] = element_id
    clamped["type"] = element_type

    is_text = element_type == "text"
    min_x = safe_area["left"] if is_text else 0.0
    min_y = safe_area["top"] if is_text else 0.0
    max_width = max(MIN_WIDGET_WIDTH, (1.0 - safe_area["left"] - safe_area["right"]) if is_text else 1.0)
    max_height = max(MIN_WIDGET_HEIGHT, (1.0 - safe_area["top"] - safe_area["bottom"]) if is_text else 1.0)

    width, _ = _clamp_number(
        raw.get("width", _DEFAULT_ELEMENT_GEOMETRY["width"]), MIN_WIDGET_WIDTH, max_width,
        _DEFAULT_ELEMENT_GEOMETRY["width"],
    )
    height, _ = _clamp_number(
        raw.get("height", _DEFAULT_ELEMENT_GEOMETRY["height"]), MIN_WIDGET_HEIGHT, max_height,
        _DEFAULT_ELEMENT_GEOMETRY["height"],
    )
    max_edge_x = (1.0 - safe_area["right"]) if is_text else 1.0
    max_edge_y = (1.0 - safe_area["bottom"]) if is_text else 1.0
    max_x = max(min_x, max_edge_x - width)
    max_y = max(min_y, max_edge_y - height)
    x, _ = _clamp_number(raw.get("x", _DEFAULT_ELEMENT_GEOMETRY["x"]), min_x, max_x, _DEFAULT_ELEMENT_GEOMETRY["x"])
    y, _ = _clamp_number(raw.get("y", _DEFAULT_ELEMENT_GEOMETRY["y"]), min_y, max_y, _DEFAULT_ELEMENT_GEOMETRY["y"])

    clamped["x"], clamped["y"], clamped["width"], clamped["height"] = x, y, width, height
    return clamped


# --- Screen validation (spec v3 section 1.3) --------------------------------


def _validate_screen(
    raw: Any, screen_id: str
) -> tuple[dict[str, Any] | None, list[LayoutIssue], list[LayoutIssue]]:
    """Validate one screen's mini-document: safe area, background, widgets
    (against the registry for this screen's kind), overlaps, and elements.

    The game screen is validated by calling this with the whole top-level
    document and ``screen_id="game"`` -- its codes and messages are
    byte-identical to schema v1/v2 (no prefix), which is how existing tests
    keep passing untouched. An event screen's issues get their label as a
    message prefix (``"Pre-game: "`` / ``"Halftime: "``) and every issue
    raised in here -- game included -- carries ``screen_id``.
    """

    kind = SCREEN_KINDS[screen_id]
    registry = WIDGET_REGISTRIES[kind]
    defaults = default_screen(screen_id)["widgets"]
    prefix = "" if screen_id == "game" else f"{SCREEN_LABELS[screen_id]}: "

    def tag(issue: LayoutIssue) -> LayoutIssue:
        message = f"{prefix}{issue.message}" if prefix else issue.message
        return replace(issue, message=message, screen=screen_id)

    if not isinstance(raw, dict):
        return None, [tag(LayoutIssue("SCREEN", "The screen must be an object."))], []

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    safe_area, safe_area_issues = _validate_safe_area(raw.get("safe_area"))
    # A supplied default is a warning; a value that cannot be read is an error.
    errors.extend(i for i in safe_area_issues if i.severity != "warning")
    warnings.extend(i for i in safe_area_issues if i.severity == "warning")

    background, background_issues = _validate_background(raw.get("background"))
    errors.extend(i for i in background_issues if i.severity != "warning")
    warnings.extend(i for i in background_issues if i.severity == "warning")

    raw_widgets = raw.get("widgets", {})
    if not isinstance(raw_widgets, dict):
        errors.append(LayoutIssue("WIDGETS", "widgets must be an object."))
        raw_widgets = {}

    for key in raw_widgets:
        if key not in registry.ids:
            warnings.append(
                LayoutIssue("UNKNOWN_WIDGET", f"Unknown widget {key!r} was ignored.", severity="warning")
            )

    normalized_widgets: dict[str, dict[str, Any]] = {}
    for widget_id in registry.ids:
        if widget_id not in raw_widgets:
            warnings.append(
                LayoutIssue(
                    "MISSING_WIDGET",
                    f"{registry.labels[widget_id]} was missing and was filled with its default.",
                    widget_id,
                    severity="warning",
                )
            )
            normalized_widgets[widget_id] = dict(defaults[widget_id])
            continue
        normalized, widget_errors, widget_warnings = _validate_widget(
            widget_id, raw_widgets[widget_id], safe_area, registry, defaults
        )
        errors.extend(widget_errors)
        warnings.extend(widget_warnings)
        normalized_widgets[widget_id] = normalized if normalized is not None else dict(defaults[widget_id])

    overlap_errors, overlap_warnings = _check_overlaps(normalized_widgets, registry)
    errors.extend(overlap_errors)
    warnings.extend(overlap_warnings)

    raw_elements = raw.get("elements", [])
    if not isinstance(raw_elements, list):
        errors.append(LayoutIssue("ELEMENTS", "elements must be a list."))
        raw_elements = []
    elif len(raw_elements) > MAX_ELEMENTS:
        errors.append(
            LayoutIssue(
                "MAX_ELEMENTS", f"A layout may have at most {MAX_ELEMENTS} elements; got {len(raw_elements)}."
            )
        )
        # The document is already rejected; validating (and base64-decoding)
        # the surplus would only spend time and memory on it.
        raw_elements = raw_elements[:MAX_ELEMENTS]

    normalized_elements: list[dict[str, Any]] = []
    seen_element_ids: set[str] = set()
    total_image_bytes = 0
    for index, raw_element in enumerate(raw_elements):
        normalized_element, element_errors, element_warnings, element_id, image_bytes = _validate_element(
            index, raw_element, safe_area, registry.ids
        )
        if element_id is not None and element_id not in registry.ids:
            if element_id in seen_element_ids:
                element_errors.append(
                    LayoutIssue(
                        "ELEMENT_ID",
                        f"Element #{index + 1}: id {element_id!r} is used by more than one element.",
                        element_id,
                    )
                )
            else:
                seen_element_ids.add(element_id)
        errors.extend(element_errors)
        warnings.extend(element_warnings)
        normalized_elements.append(normalized_element)
        if image_bytes is not None:
            total_image_bytes += image_bytes

    if total_image_bytes > MAX_TOTAL_IMAGE_BYTES:
        errors.append(
            LayoutIssue(
                "IMAGES_TOO_LARGE",
                f"All images together must be at most {MAX_TOTAL_IMAGE_BYTES} bytes; "
                f"got {total_image_bytes}.",
            )
        )

    tagged_errors = [tag(issue) for issue in errors]
    tagged_warnings = [tag(issue) for issue in warnings]

    if errors:
        return None, tagged_errors, tagged_warnings

    screen_doc = {
        "safe_area": safe_area,
        "background": background,
        "widgets": {widget_id: normalized_widgets[widget_id] for widget_id in registry.ids},
        "elements": normalized_elements,
    }
    return screen_doc, tagged_errors, tagged_warnings


# --- Public API (spec section 4.6, extended by v2 section 1, v3 section 1) -


def default_widget(widget_id: str) -> dict[str, Any]:
    """A fresh copy of ``widget_id``'s built-in default (game) widget."""

    return dict(_DEFAULT_WIDGETS[widget_id])


def default_screen_widget(screen_id: str, widget_id: str) -> dict[str, Any]:
    """A fresh copy of ``widget_id``'s built-in default on ``screen_id``
    (spec v3 section 1.2). For ``"game"`` this is exactly
    :func:`default_widget`; for an event screen it comes from that screen's
    own default (pre-game and halftime share geometry but not visibility).
    """

    if screen_id == "game":
        return default_widget(widget_id)
    return dict(_DEFAULT_EVENT_WIDGETS[screen_id][widget_id])


def default_screen(screen_id: str) -> dict[str, Any]:
    """The built-in default mini-document for one screen (spec v3 section
    1.2): the standard safe area, black background, no free elements, and
    every widget of that screen's registry at its default geometry/style.
    """

    kind = SCREEN_KINDS[screen_id]
    registry = WIDGET_REGISTRIES[kind]
    return {
        "safe_area": dict(_DEFAULT_SAFE_AREA),
        "background": dict(_DEFAULT_BACKGROUND),
        "widgets": {widget_id: default_screen_widget(screen_id, widget_id) for widget_id in registry.ids},
        "elements": [],
    }


def default_layout(name: str = DEFAULT_LAYOUT_NAME) -> dict[str, Any]:
    """The built-in default layout, which reproduces today's spectator board
    pixel-for-pixel: same geometry, Arial, no backgrounds, no effects, no
    elements (spec section 1.1); now also carries the default pre-game and
    halftime screens (spec v3 section 1.2).
    """

    return {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "name": name,
        "safe_area": dict(_DEFAULT_SAFE_AREA),
        "background": dict(_DEFAULT_BACKGROUND),
        "widgets": {widget_id: default_widget(widget_id) for widget_id in WIDGET_IDS},
        "elements": [],
        "screens": {
            "pregame": default_screen("pregame"),
            "halftime": default_screen("halftime"),
        },
    }


def validate_layout(payload: Any) -> LayoutValidation:
    """Strictly validate ``payload`` as a layout document.

    See the module docstring for what counts as an error versus a warning.
    This function never raises: every check is a type/membership test before
    any value is used, so arbitrary JSON-decoded input is safe to pass in
    directly. A document whose ``schema_version`` is 1 or 2 is accepted and
    upgraded to 3 with a warning; any other version is refused.

    The top level of the document is the **game** screen (spec v3 section
    1.3): its codes and messages are unprefixed and identical to schema
    v1/v2, so every existing caller keeps working untouched. Two more
    screens -- ``screens.pregame`` and ``screens.halftime`` -- are validated
    the same way against the *event* widget registry, with their issues'
    messages prefixed by their label.
    """

    if not isinstance(payload, dict):
        return LayoutValidation(
            None, (LayoutIssue("NOT_AN_OBJECT", "A layout must be an object."),)
        )

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    version = payload.get("schema_version")
    is_upgrade = False
    if isinstance(version, bool) or not isinstance(version, int) or version not in _ACCEPTED_SCHEMA_VERSIONS:
        errors.append(
            LayoutIssue(
                "SCHEMA_VERSION",
                f"schema_version must be 1, 2, or 3; got {version!r}.",
            )
        )
    elif version in (1, 2):
        is_upgrade = True
        warnings.append(
            LayoutIssue(
                "SCHEMA_UPGRADED",
                "This layout was saved by an earlier version and was upgraded; "
                "save it to keep the upgrade.",
                severity="warning",
            )
        )

    name_value = payload.get("name", DEFAULT_LAYOUT_NAME)
    name_issue = validate_layout_name(name_value)
    if name_issue is not None:
        errors.append(name_issue)
        normalized_name = DEFAULT_LAYOUT_NAME
    else:
        normalized_name = name_value.strip()

    game_screen, game_errors, game_warnings = _validate_screen(payload, "game")
    errors.extend(game_errors)
    warnings.extend(game_warnings)

    raw_screens = payload.get("screens")
    screen_docs: dict[str, dict[str, Any]] = {}
    if raw_screens is None:
        # Missing entirely: fill both from defaults with one warning -- but
        # not when the document is a v1/v2 upgrade, since SCHEMA_UPGRADED
        # already told the operator everything new was filled in (spec v3
        # section 1.3).
        if not is_upgrade:
            warnings.append(
                LayoutIssue(
                    "MISSING_SCREENS",
                    "The pre-game and halftime screens were missing and were "
                    "filled with their defaults.",
                    severity="warning",
                )
            )
        for screen_id in EVENT_SCREEN_IDS:
            screen_docs[screen_id] = default_screen(screen_id)
    elif not isinstance(raw_screens, dict):
        errors.append(LayoutIssue("SCREENS", "screens must be an object."))
        for screen_id in EVENT_SCREEN_IDS:
            screen_docs[screen_id] = default_screen(screen_id)
    else:
        for key in raw_screens:
            if key not in EVENT_SCREEN_IDS:
                warnings.append(
                    LayoutIssue("UNKNOWN_SCREEN", f"Unknown screen {key!r} was ignored.", severity="warning")
                )
        for screen_id in EVENT_SCREEN_IDS:
            if screen_id not in raw_screens:
                warnings.append(
                    LayoutIssue(
                        "MISSING_SCREEN",
                        f"The {SCREEN_LABELS[screen_id]} screen was missing and was "
                        f"filled with its default.",
                        severity="warning",
                    )
                )
                screen_docs[screen_id] = default_screen(screen_id)
                continue
            normalized_screen, screen_errors, screen_warnings = _validate_screen(
                raw_screens[screen_id], screen_id
            )
            errors.extend(screen_errors)
            warnings.extend(screen_warnings)
            screen_docs[screen_id] = (
                normalized_screen if normalized_screen is not None else default_screen(screen_id)
            )

    if errors:
        return LayoutValidation(None, tuple(errors), tuple(warnings))

    assert game_screen is not None
    layout = {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "name": normalized_name,
        "safe_area": game_screen["safe_area"],
        "background": game_screen["background"],
        "widgets": game_screen["widgets"],
        "elements": game_screen["elements"],
        "screens": {
            "pregame": screen_docs["pregame"],
            "halftime": screen_docs["halftime"],
        },
    }
    return LayoutValidation(layout, tuple(errors), tuple(warnings))


def load_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    """Never-raising entry point: a valid layout, or the built-in default.

    A malformed layout file must never stop the scoreboard from launching
    (spec section 0), so this is the function every reader should call.
    """

    try:
        result = validate_layout(payload)
    except Exception as exc:  # noqa: BLE001 - a layout file must never crash the host
        return default_layout(), (
            LayoutIssue("NOT_AN_OBJECT", f"The layout could not be read: {exc}"),
        )
    if result.ok:
        assert result.layout is not None
        return result.layout, result.warnings
    return default_layout(), result.errors + result.warnings


def _coerce_safe_area(raw: Any) -> dict[str, float]:
    """A best-effort safe area for :func:`clamp_layout`: always usable,
    never an error -- clamping is a repair action, not a second validator.
    """

    result: dict[str, float] = {}
    for side in ("top", "right", "bottom", "left"):
        value = raw.get(side) if isinstance(raw, dict) else None
        ok, number = _is_finite_number(value) if value is not None else (False, 0.0)
        if not ok:
            number = DEFAULT_SAFE_INSET
        result[side] = _round_coordinate(min(max(number, MIN_SAFE_INSET), MAX_SAFE_INSET))

    for first, second in (("left", "right"), ("top", "bottom")):
        if 1.0 - result[first] - result[second] < MIN_SAFE_SPAN:
            total = result[first] + result[second]
            available = 1.0 - MIN_SAFE_SPAN
            if total > 0.0:
                factor = available / total
                result[first] = _round_coordinate(result[first] * factor)
                result[second] = _round_coordinate(result[second] * factor)
            else:
                result[first] = result[second] = 0.0
    return result


def _coerce_background(raw: Any) -> dict[str, str]:
    """A best-effort background for :func:`clamp_layout`, same spirit as
    :func:`_coerce_safe_area`.
    """

    if isinstance(raw, dict):
        color = _normalize_color(raw.get("color"))
        if color is not None:
            return {"color": color}
    return dict(_DEFAULT_BACKGROUND)


def clamp_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    """Best-effort repair for the editor's "Fit to safe area" action.

    Only position, size, and font scale are adjusted -- never colour,
    alignment, weight, stacking order, visibility, or overlap (spec section
    4.6) -- and, for elements, only position and size (spec section 1.4).
    This never raises: garbage input becomes the built-in default with no
    adjustments to report, exactly like :func:`load_layout`.
    """

    try:
        return _clamp_layout(payload)
    except Exception:  # noqa: BLE001 - a repair action must never crash the host
        return default_layout(), ()


_CLAMP_PASSTHROUGH_PROPERTIES: Final[tuple[str, ...]] = (
    "visible", "color", "text_align", "vertical_align", "font_weight", "z_index",
    "font_family", "letter_spacing", "text_transform", "text_effect",
    "background", "background_opacity", "border_color", "border_width",
    "corner_radius", "padding",
)


def _clamp_screen(
    raw: Any, registry: WidgetRegistry, defaults: Mapping[str, dict[str, Any]], screen_id: str,
) -> tuple[dict[str, Any], list[LayoutIssue]]:
    """Best-effort geometry repair for one screen (spec v3 section 1.3): the
    same repair :func:`_clamp_layout` always did for the top level, just
    parameterized by registry/defaults so it can run again for each event
    screen.
    """

    issues: list[LayoutIssue] = []
    safe_area = _coerce_safe_area(raw.get("safe_area") if isinstance(raw, dict) else None)
    raw_widgets = raw.get("widgets") if isinstance(raw, dict) else None
    if not isinstance(raw_widgets, dict):
        raw_widgets = {}

    normalized_widgets: dict[str, dict[str, Any]] = {}
    for widget_id in registry.ids:
        default = defaults[widget_id]
        raw_widget = raw_widgets.get(widget_id)
        if not isinstance(raw_widget, dict):
            normalized_widgets[widget_id] = dict(default)
            continue

        label = registry.labels[widget_id]
        widget = dict(default)
        for passthrough in _CLAMP_PASSTHROUGH_PROPERTIES:
            if passthrough in raw_widget:
                widget[passthrough] = raw_widget[passthrough]

        available_width = max(MIN_WIDGET_WIDTH, 1.0 - safe_area["left"] - safe_area["right"])
        available_height = max(MIN_WIDGET_HEIGHT, 1.0 - safe_area["top"] - safe_area["bottom"])
        width, width_changed = _clamp_number(
            raw_widget.get("width", default["width"]), MIN_WIDGET_WIDTH, available_width, default["width"]
        )
        height, height_changed = _clamp_number(
            raw_widget.get("height", default["height"]), MIN_WIDGET_HEIGHT, available_height, default["height"]
        )
        if width_changed and "width" in raw_widget:
            issues.append(
                LayoutIssue("DIMENSION", f"{label}: width was adjusted to fit.", widget_id, "warning", screen_id)
            )
        if height_changed and "height" in raw_widget:
            issues.append(
                LayoutIssue("DIMENSION", f"{label}: height was adjusted to fit.", widget_id, "warning", screen_id)
            )
        widget["width"], widget["height"] = width, height

        max_x = max(safe_area["left"], 1.0 - safe_area["right"] - width)
        max_y = max(safe_area["top"], 1.0 - safe_area["bottom"] - height)
        x, x_changed = _clamp_number(raw_widget.get("x", default["x"]), safe_area["left"], max_x, default["x"])
        y, y_changed = _clamp_number(raw_widget.get("y", default["y"]), safe_area["top"], max_y, default["y"])
        if x_changed and "x" in raw_widget:
            issues.append(
                LayoutIssue(
                    "OUTSIDE_SAFE_AREA", f"{label}: x was moved inside the safe area.", widget_id, "warning", screen_id
                )
            )
        if y_changed and "y" in raw_widget:
            issues.append(
                LayoutIssue(
                    "OUTSIDE_SAFE_AREA", f"{label}: y was moved inside the safe area.", widget_id, "warning", screen_id
                )
            )
        widget["x"], widget["y"] = x, y

        font_scale, font_scale_changed = _clamp_number(
            raw_widget.get("font_scale", default["font_scale"]), MIN_FONT_SCALE, MAX_FONT_SCALE, default["font_scale"]
        )
        if font_scale_changed and "font_scale" in raw_widget:
            issues.append(
                LayoutIssue("FONT_SCALE", f"{label}: font_scale was adjusted to fit.", widget_id, "warning", screen_id)
            )
        widget["font_scale"] = font_scale
        widget["id"] = widget_id
        normalized_widgets[widget_id] = widget

    raw_elements = raw.get("elements") if isinstance(raw, dict) else None
    elements: list[dict[str, Any]] = []
    if isinstance(raw_elements, list):
        for raw_element in raw_elements[:MAX_ELEMENTS]:
            clamped_element = _clamp_element(raw_element, safe_area)
            if clamped_element is None:
                continue
            # Say what moved, exactly as the widget path above does.
            label = element_label(clamped_element)
            element_id = clamped_element["id"]
            for prop, code, what in (
                ("width", "DIMENSION", "width was adjusted to fit"),
                ("height", "DIMENSION", "height was adjusted to fit"),
                ("x", "OUTSIDE_SAFE_AREA", "x was moved inside its boundary"),
                ("y", "OUTSIDE_SAFE_AREA", "y was moved inside its boundary"),
            ):
                if prop in raw_element and raw_element[prop] != clamped_element[prop]:
                    issues.append(LayoutIssue(code, f"{label}: {what}.", element_id, "warning", screen_id))
            elements.append(clamped_element)

    screen_doc = {
        "safe_area": safe_area,
        "background": _coerce_background(raw.get("background") if isinstance(raw, dict) else None),
        "widgets": normalized_widgets,
        "elements": elements,
    }
    return screen_doc, issues


def _clamp_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    if not isinstance(payload, dict):
        return default_layout(), ()

    issues: list[LayoutIssue] = []

    game_defaults = {widget_id: default_widget(widget_id) for widget_id in WIDGET_IDS}
    game_screen, game_issues = _clamp_screen(payload, WIDGET_REGISTRIES["game"], game_defaults, "game")
    issues.extend(game_issues)

    raw_screens = payload.get("screens")
    if not isinstance(raw_screens, dict):
        raw_screens = {}

    screen_docs: dict[str, dict[str, Any]] = {}
    for screen_id in EVENT_SCREEN_IDS:
        registry = WIDGET_REGISTRIES[SCREEN_KINDS[screen_id]]
        defaults = {widget_id: default_screen_widget(screen_id, widget_id) for widget_id in registry.ids}
        screen_doc, screen_issues = _clamp_screen(raw_screens.get(screen_id), registry, defaults, screen_id)
        screen_docs[screen_id] = screen_doc
        issues.extend(screen_issues)

    name_value = payload.get("name", DEFAULT_LAYOUT_NAME)
    name = DEFAULT_LAYOUT_NAME if validate_layout_name(name_value) is not None else name_value.strip()

    layout = {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "name": name,
        "safe_area": game_screen["safe_area"],
        "background": game_screen["background"],
        "widgets": game_screen["widgets"],
        "elements": game_screen["elements"],
        "screens": {
            "pregame": screen_docs["pregame"],
            "halftime": screen_docs["halftime"],
        },
    }
    return layout, tuple(issues)


def reset_widget(layout: Mapping[str, Any], widget_id: str, screen: str = "game") -> dict[str, Any]:
    """Restore exactly one widget, on one screen, to its default; every other
    widget -- on every screen -- is whatever ``layout`` already validates to.
    An unknown screen or widget id returns the normalized layout unchanged
    (spec v3 section 1.3). Never raises.
    """

    normalized, _warnings = load_layout(layout)
    if screen not in SCREEN_IDS:
        return normalized
    registry = WIDGET_REGISTRIES[SCREEN_KINDS[screen]]
    if widget_id not in registry.ids:
        return normalized
    default = default_screen_widget(screen, widget_id)

    if screen == "game":
        widgets = dict(normalized["widgets"])
        widgets[widget_id] = default
        return {**normalized, "widgets": widgets}

    screens = dict(normalized["screens"])
    screen_doc = dict(screens[screen])
    widgets = dict(screen_doc["widgets"])
    widgets[widget_id] = default
    screens[screen] = {**screen_doc, "widgets": widgets}
    return {**normalized, "screens": screens}


def widget_descriptors(kind: str = "game") -> list[dict[str, Any]]:
    """Static metadata for every widget of ``kind`` ("game" or "event"), in
    the registry's id order.

    This drives the editor's widget list so it never hard-codes a widget id
    (spec section 8): the UI is generated entirely from this function's
    output. ``default`` comes from the built-in game defaults for
    ``"game"``, and from the pre-game screen's defaults for ``"event"``
    (spec v3 section 1.3) -- use :func:`screen_descriptors` for a
    per-screen-accurate default.
    """

    registry = WIDGET_REGISTRIES[kind]
    default_screen_id = "game" if kind == "game" else "pregame"
    return [
        {
            "id": widget_id,
            "label": registry.labels[widget_id],
            "field": registry.fields[widget_id],
            "static_text": registry.texts.get(widget_id),
            "optional": widget_id in registry.optional,
            "group": registry.groups[widget_id],
            "default": default_screen_widget(default_screen_id, widget_id),
        }
        for widget_id in registry.ids
    ]


def screen_descriptors() -> list[dict[str, Any]]:
    """Static metadata for every screen, in :data:`SCREEN_IDS` order (spec
    v3 section 1.3): drives the editor's Game / Pre-game / Halftime switcher
    and its per-screen layers rail, without hard-coding a screen or widget
    id anywhere in the UI. Each entry's ``widgets`` carries that *screen's
    own* defaults -- unlike :func:`widget_descriptors`, halftime's entry
    does not borrow pre-game's defaults.
    """

    descriptors = []
    for screen_id in SCREEN_IDS:
        kind = SCREEN_KINDS[screen_id]
        registry = WIDGET_REGISTRIES[kind]
        widgets = [
            {
                "id": widget_id,
                "label": registry.labels[widget_id],
                "field": registry.fields[widget_id],
                "static_text": registry.texts.get(widget_id),
                "optional": widget_id in registry.optional,
                "group": registry.groups[widget_id],
                "default": default_screen_widget(screen_id, widget_id),
            }
            for widget_id in registry.ids
        ]
        descriptors.append(
            {
                "id": screen_id,
                "label": SCREEN_LABELS[screen_id],
                "kind": kind,
                "widgets": widgets,
                "widget_groups": list(registry.group_order),
            }
        )
    return descriptors


# --- Event screen presets (spec v3 section 1.4) -----------------------------


def _pregame_matchup_screen() -> dict[str, Any]:
    """"Matchup": big team names face off, a "VS" mark between them, a slim
    countdown title, a big countdown in the lower half, and a small score
    row at the very bottom. Phase and warmup stay hidden (pre-game default).
    """

    screen = default_screen("pregame")
    overrides: dict[str, dict[str, Any]] = {
        "home_name": {"x": 0.04, "y": 0.06, "width": 0.40, "height": 0.14, "font_scale": 0.075,
                      "font_weight": 900, "text_transform": "uppercase", "text_align": "right"},
        "away_name": {"x": 0.56, "y": 0.06, "width": 0.40, "height": 0.14, "font_scale": 0.075,
                      "font_weight": 900, "text_transform": "uppercase", "text_align": "left"},
        "event_title": {"x": 0.10, "y": 0.22, "width": 0.80, "height": 0.06, "font_scale": 0.030},
        "event_clock": {"x": 0.10, "y": 0.30, "width": 0.80, "height": 0.30, "font_scale": 0.120},
        "home_score": {"x": 0.35, "y": 0.85, "width": 0.12, "height": 0.09, "font_scale": 0.050},
        "away_score": {"x": 0.53, "y": 0.85, "width": 0.12, "height": 0.09, "font_scale": 0.050},
    }
    for widget_id, changes in overrides.items():
        screen["widgets"][widget_id].update(changes)
    screen["elements"] = [
        {
            "id": "vs_label", "type": "text", "text": "VS",
            "x": 0.44, "y": 0.08, "width": 0.12, "height": 0.12,
            "font_scale": 0.05, "color": "#FFB703", "font_weight": 900,
            "text_align": "center", "vertical_align": "middle",
        },
    ]
    return screen


def _halftime_score_first_screen() -> dict[str, Any]:
    """"Score first": big scores lead beside each name, the phase label
    centred below them, then the countdown and the warmup line at the
    bottom. Title hidden.
    """

    screen = default_screen("halftime")
    overrides: dict[str, dict[str, Any]] = {
        "event_title": {"visible": False},
        # font_scale is a fraction of the canvas WIDTH, so a 0.14 score glyph
        # is about 0.25 of the canvas height: the score boxes are sized to
        # hold that, not just to avoid overlapping their neighbours.
        "home_name": {"x": 0.04, "y": 0.12, "width": 0.22, "height": 0.18, "font_scale": 0.045,
                      "text_align": "right"},
        "home_score": {"x": 0.27, "y": 0.06, "width": 0.20, "height": 0.30, "font_scale": 0.140},
        "away_score": {"x": 0.53, "y": 0.06, "width": 0.20, "height": 0.30, "font_scale": 0.140},
        "away_name": {"x": 0.74, "y": 0.12, "width": 0.22, "height": 0.18, "font_scale": 0.045,
                      "text_align": "left"},
        "event_phase": {"x": 0.30, "y": 0.40, "width": 0.40, "height": 0.08, "font_scale": 0.040},
        "event_clock": {"x": 0.20, "y": 0.50, "width": 0.60, "height": 0.22, "font_scale": 0.100},
        "warmup": {"x": 0.25, "y": 0.78, "width": 0.50, "height": 0.08, "font_scale": 0.035},
    }
    for widget_id, changes in overrides.items():
        screen["widgets"][widget_id].update(changes)
    screen["elements"] = []
    return screen


def _broadcast_bar_screen(screen_id: str) -> dict[str, Any]:
    """"Broadcast bar": a dark rounded bar across the bottom holds name +
    score, the countdown, and score + name; a slim row just above the bar
    carries the countdown title (halftime also fits the phase label at its
    left end and the warmup line at its right end). The upper ~70% stays
    empty black, free for future media.
    """

    screen = default_screen(screen_id)
    overrides: dict[str, dict[str, Any]] = {
        "home_name": {"x": 0.04, "y": 0.80, "width": 0.18, "height": 0.12, "font_scale": 0.035,
                      "text_align": "right"},
        "home_score": {"x": 0.23, "y": 0.80, "width": 0.10, "height": 0.12, "font_scale": 0.060},
        "event_clock": {"x": 0.35, "y": 0.79, "width": 0.30, "height": 0.14, "font_scale": 0.090},
        "away_score": {"x": 0.67, "y": 0.80, "width": 0.10, "height": 0.12, "font_scale": 0.060},
        "away_name": {"x": 0.78, "y": 0.80, "width": 0.18, "height": 0.12, "font_scale": 0.035,
                      "text_align": "left"},
        "event_title": {"x": 0.04, "y": 0.71, "width": 0.92, "height": 0.06, "font_scale": 0.030},
    }
    for widget_id, changes in overrides.items():
        screen["widgets"][widget_id].update(changes)
    if screen_id == "halftime":
        screen["widgets"]["event_phase"].update(
            {"x": 0.04, "y": 0.71, "width": 0.19, "height": 0.06, "font_scale": 0.028, "text_align": "left"}
        )
        # "Warmup follows: 3:00" is about eleven ems wide; at this size it
        # needs roughly 0.25 of the canvas width or it wraps onto two lines.
        screen["widgets"]["warmup"].update(
            {"x": 0.66, "y": 0.71, "width": 0.30, "height": 0.06, "font_scale": 0.022, "text_align": "right"}
        )
        # Shrink the title to make room for the phase label and warmup line
        # sharing the same slim row.
        screen["widgets"]["event_title"].update(
            {"x": 0.24, "y": 0.71, "width": 0.40, "height": 0.06, "font_scale": 0.024}
        )
    screen["elements"] = [
        {
            "id": "broadcast_bar", "type": "box",
            "x": 0.0, "y": 0.78, "width": 1.0, "height": 0.18,
            "background": "#101820", "corner_radius": 0.012,
        },
    ]
    return screen


def _tigers_event_screen(screen_id: str) -> dict[str, Any]:
    """"Tigers navy": the same brand baseline as the game preset (spec
    section 1.7) applied to an event screen -- navy background, red
    top/bottom bars, a navy panel behind the countdown, bahnschrift
    uppercase team names, and the tinted secondary text.
    """

    screen = default_screen(screen_id)
    screen["widgets"]["home_name"].update({"font_family": "bahnschrift", "text_transform": "uppercase"})
    screen["widgets"]["away_name"].update({"font_family": "bahnschrift", "text_transform": "uppercase"})
    screen["widgets"]["event_title"].update({"color": "#DDE7F4"})
    screen["widgets"]["home_score"].update({"color": "#FFB703"})
    screen["widgets"]["away_score"].update({"color": "#FFB703"})
    if screen_id == "halftime":
        screen["widgets"]["event_phase"].update({"color": "#FFB703"})
        screen["widgets"]["warmup"].update({"color": "#DDE7F4"})
    screen["background"] = {"color": "#071B3A"}
    clock = screen["widgets"]["event_clock"]
    screen["elements"] = [
        {
            "id": "top_bar", "type": "box",
            "x": 0.0, "y": 0.0, "width": 1.0, "height": 0.025,
            "background": "#C8242B", "z_index": 5,
        },
        {
            "id": "bottom_bar", "type": "box",
            "x": 0.0, "y": 0.975, "width": 1.0, "height": 0.025,
            "background": "#C8242B", "z_index": 5,
        },
        {
            "id": "countdown_panel", "type": "box",
            "x": clock["x"], "y": clock["y"], "width": clock["width"], "height": clock["height"],
            "background": "#0D2B5A", "corner_radius": 0.02,
        },
    ]
    return screen


def _normalized_screen_preset(screen_id: str, screen: dict[str, Any]) -> dict[str, Any]:
    """A screen preset exactly as :func:`validate_layout` would hand it back
    -- validate it wrapped in a full document, then pull the screen back out
    (spec v3 section 1.4), mirroring :func:`_normalized_preset`.
    """

    document = default_layout()
    document["screens"][screen_id] = screen
    result = validate_layout(document)
    if not result.ok or result.layout is None:
        # Unreachable for a preset the unit test has checked.
        return screen
    return result.layout["screens"][screen_id]


def _stadium_box(id: str, x: float, y: float, width: float, height: float,
                 color: str) -> dict[str, Any]:
    return {"id": id, "type": "box", "x": x, "y": y, "width": width,
            "height": height, "background": color, "z_index": 0}


def _stadium_text(id: str, text: str, x: float, y: float, width: float,
                  height: float, size: float, color: str = "#A9BCD6") -> dict[str, Any]:
    return {"id": id, "type": "text", "text": text, "x": x, "y": y,
            "width": width, "height": height, "font_scale": size,
            "font_family": "bahnschrift", "font_weight": 700,
            "text_align": "left", "vertical_align": "middle", "color": color}


def _stadium_elements() -> list[dict[str, Any]]:
    # Ordinary editable elements only: no asset, special renderer, or schema
    # extension. Three subdued slash glyphs make the header's claw motif.
    return [
        _stadium_box("top_red", 0, 0, 0.5, 0.02, "#C8242B"),
        _stadium_box("top_blue", 0.5, 0, 0.5, 0.02, "#1764AF"),
        _stadium_text("stadium_brand", "TIGERS  /  FOOTBALL", 0.05, 0.04, 0.60, 0.055, 0.024, "#FFFFFF"),
        _stadium_text("claw_mark", "///", 0.85, 0.04, 0.10, 0.065, 0.032, "#29456C"),
        _stadium_box("header_rule", 0.05, 0.105, 0.90, 0.02, "#29456C"),
    ]


def _stadium_style(screen: dict[str, Any]) -> None:
    screen["background"] = {"color": "#071B3A"}
    for widget in screen["widgets"].values():
        widget.update(font_family="bahnschrift", font_weight=700,
                      color="#FFFFFF", text_align="center", z_index=2)


def _stadium_event_screen(screen_id: str) -> dict[str, Any]:
    screen = default_screen(screen_id)
    _stadium_style(screen)
    geometry = {
        "event_phase": (0.30, 0.13, 0.40, 0.065, 0.024),
        "event_title": (0.10, 0.205, 0.80, 0.07, 0.031),
        "event_clock": (0.15, 0.28, 0.70, 0.29, 0.145),
        "warmup": (0.20, 0.585, 0.60, 0.06, 0.022),
        "home_name": (0.065, 0.70, 0.235, 0.21, 0.029),
        "home_score": (0.305, 0.705, 0.165, 0.21, 0.088),
        "away_score": (0.53, 0.705, 0.165, 0.21, 0.088),
        "away_name": (0.70, 0.70, 0.235, 0.21, 0.029),
    }
    for id, (x, y, width, height, size) in geometry.items():
        screen["widgets"][id].update(x=x, y=y, width=width, height=height, font_scale=size)
    for id in ("home_name", "away_name", "event_title", "event_phase"):
        screen["widgets"][id]["text_transform"] = "uppercase"
    screen["widgets"]["event_phase"]["color"] = "#FFB703"
    screen["widgets"]["warmup"]["color"] = "#A9BCD6"
    screen["elements"] = _stadium_elements() + [
        _stadium_box("home_panel", 0.04, 0.675, 0.445, 0.275, "#861E30"),
        _stadium_box("away_panel", 0.515, 0.675, 0.445, 0.275, "#124C85"),
        _stadium_box("home_accent", 0.04, 0.675, 0.445, 0.02, "#E13A46"),
        _stadium_box("away_accent", 0.515, 0.675, 0.445, 0.02, "#3285D1"),
    ]
    return screen


def _stadium_preset_layout() -> dict[str, Any]:
    """Tigers Stadium: a static, editable three-screen presentation package.

    The centre clock leads, team panels frame it, and field/status values
    have dedicated space even when every optional field is populated.
    Colours are fixed design choices, not bindings to saved team identity.
    """
    layout = default_layout("Tigers Stadium")
    _stadium_style(layout)
    geometry = {
        "home_name": (0.055, 0.17, 0.235, 0.16, 0.026),
        "home_score": (0.05, 0.33, 0.245, 0.30, 0.140),
        "away_name": (0.71, 0.17, 0.235, 0.16, 0.026),
        "away_score": (0.705, 0.33, 0.245, 0.30, 0.140),
        "possession": (0.34, 0.13, 0.32, 0.055, 0.022),
        "game_clock_label": (0.32, 0.205, 0.36, 0.045, 0.018),
        "game_clock_value": (0.305, 0.26, 0.39, 0.25, 0.135),
        "quarter": (0.32, 0.52, 0.36, 0.065, 0.029),
        "play_clock_label": (0.35, 0.635, 0.17, 0.045, 0.019),
        "play_clock_value": (0.53, 0.59, 0.13, 0.13, 0.060),
        "status_message": (0.31, 0.725, 0.25, 0.055, 0.025),
        "status_clock": (0.575, 0.725, 0.12, 0.055, 0.025),
        "down": (0.055, 0.855, 0.13, 0.095, 0.042),
        "distance": (0.225, 0.855, 0.17, 0.095, 0.042),
        "ball_on": (0.445, 0.85, 0.49, 0.10, 0.022),
    }
    for id, (x, y, width, height, size) in geometry.items():
        layout["widgets"][id].update(x=x, y=y, width=width, height=height, font_scale=size)
    for id in ("home_name", "away_name", "quarter"):
        layout["widgets"][id]["text_transform"] = "uppercase"
    layout["widgets"]["game_clock_label"]["visible"] = True
    for id in ("possession", "status_message", "status_clock"):
        layout["widgets"][id]["color"] = "#FFB703"
    for id in ("game_clock_label", "play_clock_label"):
        layout["widgets"][id]["color"] = "#A9BCD6"
    layout["elements"] = _stadium_elements() + [
        _stadium_box("home_panel", 0.04, 0.145, 0.265, 0.535, "#861E30"),
        _stadium_box("away_panel", 0.695, 0.145, 0.265, 0.535, "#124C85"),
        _stadium_box("home_accent", 0.04, 0.145, 0.265, 0.02, "#E13A46"),
        _stadium_box("away_accent", 0.695, 0.145, 0.265, 0.02, "#3285D1"),
        _stadium_box("field_strip", 0.04, 0.80, 0.92, 0.16, "#102D53"),
        _stadium_text("down_label", "DOWN", 0.055, 0.815, 0.13, 0.03, 0.015),
        _stadium_text("distance_label", "TO GO", 0.225, 0.815, 0.17, 0.03, 0.015),
        _stadium_text("field_label", "FIELD POSITION", 0.445, 0.815, 0.49, 0.03, 0.015),
    ]
    layout["screens"] = {id: _stadium_event_screen(id) for id in EVENT_SCREEN_IDS}
    return layout


def _raw_pregame_screen_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "pregame_classic",
            "name": "Classic",
            "description": "The built-in default pre-game arrangement.",
            "screen": default_screen("pregame"),
        },
        {
            "id": "pregame_matchup",
            "name": "Matchup",
            "description": "Big team names face off with a VS mark; the countdown "
            "fills the lower half.",
            "screen": _pregame_matchup_screen(),
        },
        {
            "id": "pregame_broadcast",
            "name": "Broadcast bar",
            "description": "A dark bar across the bottom holds the score and "
            "countdown; the top of the board stays free for future media.",
            "screen": _broadcast_bar_screen("pregame"),
        },
        {
            "id": "pregame_tigers",
            "name": "Tigers navy",
            "description": "Navy background with red accents and bahnschrift team "
            "names, from the Tigers brand baseline.",
            "screen": _tigers_event_screen("pregame"),
        },
        {
            "id": "pregame_stadium", "name": "Tigers Stadium",
            "description": "A dominant kickoff countdown with red and blue matchup panels.",
            "screen": _stadium_event_screen("pregame"),
        },
    ]


def _raw_halftime_screen_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "halftime_classic",
            "name": "Classic",
            "description": "The built-in default halftime arrangement.",
            "screen": default_screen("halftime"),
        },
        {
            "id": "halftime_score_first",
            "name": "Score first",
            "description": "Big scores lead, with the phase, countdown, and warmup "
            "line below.",
            "screen": _halftime_score_first_screen(),
        },
        {
            "id": "halftime_broadcast",
            "name": "Broadcast bar",
            "description": "A dark bar across the bottom holds the score and "
            "countdown, with the phase and warmup line in the slim row above.",
            "screen": _broadcast_bar_screen("halftime"),
        },
        {
            "id": "halftime_tigers",
            "name": "Tigers navy",
            "description": "Navy background with red accents and bahnschrift team "
            "names, from the Tigers brand baseline.",
            "screen": _tigers_event_screen("halftime"),
        },
        {
            "id": "halftime_stadium", "name": "Tigers Stadium",
            "description": "A dominant return countdown, warmup line, and red and blue score panels.",
            "screen": _stadium_event_screen("halftime"),
        },
    ]


def screen_preset_descriptors() -> dict[str, list[dict[str, Any]]]:
    """The built-in per-screen presets (spec v3 section 1.4), keyed by event
    screen id, each a complete normalized
    screen mini-document. Every preset here (and every game preset from
    :func:`preset_descriptors`) validates ``ok`` with zero warnings, and
    every id -- across both functions -- is globally unique.
    """

    return {
        "pregame": [
            {**entry, "screen": _normalized_screen_preset("pregame", entry["screen"])}
            for entry in _raw_pregame_screen_presets()
        ],
        "halftime": [
            {**entry, "screen": _normalized_screen_preset("halftime", entry["screen"])}
            for entry in _raw_halftime_screen_presets()
        ],
    }


def _classic_preset_layout() -> dict[str, Any]:
    return default_layout("Classic")


def _broadcast_preset_layout() -> dict[str, Any]:
    layout = default_layout("Broadcast bar")
    overrides: dict[str, dict[str, Any]] = {
        "possession": {"visible": False},
        # The bar: name | score | clock | score | name on one line.
        "home_name": {"x": 0.05, "y": 0.80, "width": 0.20, "height": 0.14, "font_scale": 0.032,
                      "text_align": "right"},
        "home_score": {"x": 0.26, "y": 0.80, "width": 0.12, "height": 0.14, "font_scale": 0.07},
        "game_clock_value": {"x": 0.39, "y": 0.80, "width": 0.22, "height": 0.14, "font_scale": 0.08},
        "away_score": {"x": 0.62, "y": 0.80, "width": 0.12, "height": 0.14, "font_scale": 0.07},
        "away_name": {"x": 0.75, "y": 0.80, "width": 0.20, "height": 0.14, "font_scale": 0.032,
                      "text_align": "left"},
        # The slim status row just above the bar. Widths leave room for the
        # longest strings each field produces ("4th Quarter", "PLAY CLOCK").
        "quarter": {"x": 0.04, "y": 0.705, "width": 0.20, "height": 0.065, "font_scale": 0.028,
                    "text_align": "left"},
        "down": {"x": 0.25, "y": 0.705, "width": 0.09, "height": 0.065, "font_scale": 0.025},
        "distance": {"x": 0.35, "y": 0.705, "width": 0.09, "height": 0.065, "font_scale": 0.025},
        "ball_on": {"x": 0.45, "y": 0.705, "width": 0.22, "height": 0.065, "font_scale": 0.022},
        "play_clock_label": {"x": 0.68, "y": 0.705, "width": 0.15, "height": 0.065, "font_scale": 0.02},
        "play_clock_value": {"x": 0.84, "y": 0.705, "width": 0.12, "height": 0.065, "font_scale": 0.034},
    }
    for widget_id, changes in overrides.items():
        layout["widgets"][widget_id].update(changes)
    layout["background"] = {"color": "#000000"}
    layout["elements"] = [
        {
            "id": "broadcast_bar",
            "type": "box",
            "x": 0.0, "y": 0.78, "width": 1.0, "height": 0.18,
            "background": "#101820", "corner_radius": 0.012, "z_index": 0,
        },
    ]
    layout["screens"] = {
        "pregame": _broadcast_bar_screen("pregame"),
        "halftime": _broadcast_bar_screen("halftime"),
    }
    return layout


def _big_score_preset_layout() -> dict[str, Any]:
    layout = default_layout("Big score")
    overrides: dict[str, dict[str, Any]] = {
        "possession": {"visible": False},
        "home_name": {"x": 0.06, "y": 0.05, "width": 0.40, "height": 0.10, "font_scale": 0.045},
        "home_score": {"x": 0.06, "y": 0.16, "width": 0.40, "height": 0.32, "font_scale": 0.20},
        "away_name": {"x": 0.54, "y": 0.05, "width": 0.40, "height": 0.10, "font_scale": 0.045},
        "away_score": {"x": 0.54, "y": 0.16, "width": 0.40, "height": 0.32, "font_scale": 0.20},
        "game_clock_value": {"x": 0.06, "y": 0.55, "width": 0.30, "height": 0.18, "font_scale": 0.12},
        "play_clock_label": {"x": 0.70, "y": 0.55, "width": 0.20, "height": 0.05, "font_scale": 0.03},
        "play_clock_value": {"x": 0.70, "y": 0.61, "width": 0.20, "height": 0.13, "font_scale": 0.10},
        "quarter": {"x": 0.30, "y": 0.78, "width": 0.40, "height": 0.08, "font_scale": 0.045},
        "down": {"x": 0.10, "y": 0.87, "width": 0.15, "height": 0.06, "font_scale": 0.025, "text_align": "right"},
        "distance": {"x": 0.27, "y": 0.87, "width": 0.15, "height": 0.06, "font_scale": 0.025, "text_align": "left"},
        "ball_on": {"x": 0.45, "y": 0.87, "width": 0.40, "height": 0.06, "font_scale": 0.022},
        # F3: the built-in default's status_message/status_clock rectangles
        # (x 0.240-0.400 / 0.600-0.760, y 0.408-0.464) sit squarely under this
        # preset's enlarged home_score/away_score panels (y 0.16-0.48), which
        # would be a serious (error-level) overlap -- so, exactly like every
        # other repositioned widget above, only these two are moved, into the
        # gap between the enlarged game_clock_value (ends x=0.36) and
        # play_clock_label (starts x=0.70), both at y 0.55-0.606 with margins
        # on every side, disjoint from every other widget in this preset.
        "status_message": {"x": 0.370, "y": 0.550, "width": 0.150, "height": 0.056},
        "status_clock": {"x": 0.540, "y": 0.550, "width": 0.150, "height": 0.056},
    }
    for widget_id, changes in overrides.items():
        layout["widgets"][widget_id].update(changes)
    layout["background"] = {"color": "#000000"}
    layout["elements"] = []
    layout["screens"] = {
        "pregame": _pregame_matchup_screen(),
        "halftime": _halftime_score_first_screen(),
    }
    return layout


def _tigers_preset_layout() -> dict[str, Any]:
    """Brand baseline colours from ``brand-baseline/palette.json`` (spec
    section 1.7): navy board, red top/bottom bars, navy-elevated score
    panels, bahnschrift uppercase team names, amber possession indicator,
    and mist-coloured secondary text. Geometry is untouched from the v1
    default, which already validates clean, so only style changes here.
    """

    layout = default_layout("Tigers navy")
    overrides: dict[str, dict[str, Any]] = {
        "home_name": {"font_family": "bahnschrift", "text_transform": "uppercase"},
        "away_name": {"font_family": "bahnschrift", "text_transform": "uppercase"},
        "possession": {"color": "#FFB703"},
        "quarter": {"color": "#DDE7F4"},
        "down": {"color": "#DDE7F4"},
        "distance": {"color": "#DDE7F4"},
        "ball_on": {"color": "#DDE7F4"},
        "play_clock_label": {"color": "#DDE7F4"},
    }
    for widget_id, changes in overrides.items():
        layout["widgets"][widget_id].update(changes)
    layout["background"] = {"color": "#071B3A"}
    layout["elements"] = [
        {
            "id": "top_bar", "type": "box",
            "x": 0.0, "y": 0.0, "width": 1.0, "height": 0.025,
            "background": "#C8242B", "z_index": 5,
        },
        {
            "id": "bottom_bar", "type": "box",
            "x": 0.0, "y": 0.975, "width": 1.0, "height": 0.025,
            "background": "#C8242B", "z_index": 5,
        },
        {
            "id": "home_score_panel", "type": "box",
            "x": 0.040, "y": 0.164, "width": 0.380, "height": 0.242,
            "background": "#0D2B5A", "corner_radius": 0.02, "z_index": 0,
        },
        {
            "id": "away_score_panel", "type": "box",
            "x": 0.580, "y": 0.164, "width": 0.380, "height": 0.242,
            "background": "#0D2B5A", "corner_radius": 0.02, "z_index": 0,
        },
    ]
    layout["screens"] = {
        "pregame": _tigers_event_screen("pregame"),
        "halftime": _tigers_event_screen("halftime"),
    }
    return layout


def _normalized_preset(layout: dict[str, Any]) -> dict[str, Any]:
    """The preset exactly as :func:`validate_layout` would hand it back.

    The preset builders write only the properties that differ from a default,
    so an element may omit ``visible`` or ``opacity``. The editor reads those
    keys directly, and a missing ``visible`` would show an element as hidden
    in its inspector while the renderer drew it. Normalizing here means every
    consumer sees the same complete document a saved layout would be.
    """

    result = validate_layout(layout)
    if not result.ok or result.layout is None:
        # Unreachable for a preset the unit test has checked, but a preset
        # must never come back as None: fall back to the raw document.
        return layout
    return result.layout


def preset_descriptors() -> list[dict[str, Any]]:
    """The built-in presets (spec section 1.7): a full valid v2 document per
    entry, each already the standard shape :func:`validate_layout` returns
    (``ok is True`` with zero warnings, asserted by a unit test).
    """

    return [
        {**entry, "layout": _normalized_preset(entry["layout"])}
        for entry in _raw_preset_descriptors()
    ]


def _raw_preset_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "id": "classic",
            "name": "Classic",
            "description": "The built-in default arrangement.",
            "layout": _classic_preset_layout(),
        },
        {
            "id": "broadcast",
            "name": "Broadcast bar",
            "description": "A dark bar across the bottom holds the score and clock; "
            "the top of the board stays free for future media.",
            "layout": _broadcast_preset_layout(),
        },
        {
            "id": "big_score",
            "name": "Big score",
            "description": "Oversized scores fill the top half, with the clocks and "
            "field state below.",
            "layout": _big_score_preset_layout(),
        },
        {
            "id": "tigers",
            "name": "Tigers navy",
            "description": "Navy background with red accents and bahnschrift team names, "
            "from the Tigers brand baseline.",
            "layout": _tigers_preset_layout(),
        },
        {
            "id": "stadium", "name": "Tigers Stadium",
            "description": "Large white scores, a dominant centre clock, red and blue team panels, "
            "and a dedicated field strip. Matching Pre-game and Halftime presets are available.",
            "layout": _stadium_preset_layout(),
        },
    ]


def limits() -> dict[str, Any]:
    """Every schema constant above, JSON-compatible, for the editor's inputs."""

    return {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "min_widget_width": MIN_WIDGET_WIDTH,
        "min_widget_height": MIN_WIDGET_HEIGHT,
        "min_font_scale": MIN_FONT_SCALE,
        "max_font_scale": MAX_FONT_SCALE,
        "min_z_index": MIN_Z_INDEX,
        "max_z_index": MAX_Z_INDEX,
        "min_safe_inset": MIN_SAFE_INSET,
        "max_safe_inset": MAX_SAFE_INSET,
        "min_safe_span": MIN_SAFE_SPAN,
        "default_safe_inset": DEFAULT_SAFE_INSET,
        "serious_overlap_ratio": SERIOUS_OVERLAP_RATIO,
        "coordinate_precision": COORDINATE_PRECISION,
        "font_weights": list(FONT_WEIGHTS),
        "text_alignments": list(TEXT_ALIGNMENTS),
        "vertical_alignments": list(VERTICAL_ALIGNMENTS),
        "min_letter_spacing": MIN_LETTER_SPACING,
        "max_letter_spacing": MAX_LETTER_SPACING,
        "max_border_width": MAX_BORDER_WIDTH,
        "max_corner_radius": MAX_CORNER_RADIUS,
        "max_padding": MAX_PADDING,
        "min_opacity": MIN_OPACITY,
        "max_elements": MAX_ELEMENTS,
        "max_text_length": MAX_TEXT_LENGTH,
        "max_text_lines": MAX_TEXT_LINES,
        "max_image_bytes": MAX_IMAGE_BYTES,
        "max_total_image_bytes": MAX_TOTAL_IMAGE_BYTES,
        "font_families": [{"id": key, "label": FONT_FAMILY_LABELS[key]} for key in FONT_FAMILIES],
        "text_transforms": list(TEXT_TRANSFORMS),
        "text_effects": list(TEXT_EFFECTS),
        "image_fits": list(IMAGE_FITS),
        "element_types": list(ELEMENT_TYPES),
        "widget_groups": list(WIDGET_GROUP_ORDER),
        "screens": [
            {"id": screen_id, "label": SCREEN_LABELS[screen_id], "kind": SCREEN_KINDS[screen_id]}
            for screen_id in SCREEN_IDS
        ],
        "event_widget_groups": list(EVENT_WIDGET_GROUP_ORDER),
    }


def _resolve_path(view_model: Mapping[str, Any], path: str) -> Any:
    node: Any = view_model
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def supported_widget_ids(view_model: Mapping[str, Any], kind: str = "game") -> tuple[str, ...]:
    """Ids of ``kind`` ("game" or "event") whose field resolves to real
    data, plus every static-label id.

    Tolerates a completely empty view model: every static-label widget is
    still "supported" (it draws application-owned text regardless of game
    state), and every data-driven widget is simply absent.
    """

    if not isinstance(view_model, dict):
        view_model = {}
    registry = WIDGET_REGISTRIES[kind]
    supported = []
    for widget_id in registry.ids:
        field = registry.fields[widget_id]
        if field is None:
            supported.append(widget_id)
            continue
        value = _resolve_path(view_model, field)
        if value is None or value == "":
            continue
        supported.append(widget_id)
    return tuple(supported)


__all__ = [
    "COORDINATE_PRECISION",
    "DEFAULT_LAYOUT_NAME",
    "DEFAULT_SAFE_INSET",
    "ELEMENT_TYPES",
    "EVENT_OPTIONAL_WIDGET_IDS",
    "EVENT_SCREEN_IDS",
    "EVENT_WIDGET_FIELDS",
    "EVENT_WIDGET_GROUPS",
    "EVENT_WIDGET_GROUP_ORDER",
    "EVENT_WIDGET_IDS",
    "EVENT_WIDGET_LABELS",
    "EVENT_WIDGET_TEXTS",
    "FONT_FAMILIES",
    "FONT_FAMILY_LABELS",
    "FONT_WEIGHTS",
    "IMAGE_FITS",
    "LAYOUT_SCHEMA_VERSION",
    "MAX_BORDER_WIDTH",
    "MAX_CORNER_RADIUS",
    "MAX_ELEMENTS",
    "MAX_FONT_SCALE",
    "MAX_IMAGE_BYTES",
    "MAX_LETTER_SPACING",
    "MAX_PADDING",
    "MAX_SAFE_INSET",
    "MAX_TEXT_LENGTH",
    "MAX_TEXT_LINES",
    "MAX_TOTAL_IMAGE_BYTES",
    "MAX_Z_INDEX",
    "MIN_FONT_SCALE",
    "MIN_LETTER_SPACING",
    "MIN_OPACITY",
    "MIN_SAFE_INSET",
    "MIN_SAFE_SPAN",
    "MIN_WIDGET_HEIGHT",
    "MIN_WIDGET_WIDTH",
    "MIN_Z_INDEX",
    "OPTIONAL_WIDGET_IDS",
    "SCREEN_IDS",
    "SCREEN_KINDS",
    "SCREEN_LABELS",
    "SERIOUS_OVERLAP_RATIO",
    "TEXT_ALIGNMENTS",
    "TEXT_EFFECTS",
    "TEXT_TRANSFORMS",
    "VERTICAL_ALIGNMENTS",
    "WIDGET_FIELDS",
    "WIDGET_GROUPS",
    "WIDGET_GROUP_ORDER",
    "WIDGET_IDS",
    "WIDGET_KINDS",
    "WIDGET_LABELS",
    "WIDGET_REGISTRIES",
    "WIDGET_TEXTS",
    "LayoutIssue",
    "LayoutValidation",
    "WidgetRegistry",
    "clamp_layout",
    "default_layout",
    "default_screen",
    "default_screen_widget",
    "default_widget",
    "element_label",
    "limits",
    "load_layout",
    "preset_descriptors",
    "registry_for",
    "reset_widget",
    "screen_descriptors",
    "screen_preset_descriptors",
    "supported_widget_ids",
    "validate_layout",
    "validate_layout_name",
    "widget_descriptors",
]
