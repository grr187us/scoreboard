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
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Mapping

# --- Schema constants (spec section 4) --------------------------------------

LAYOUT_SCHEMA_VERSION: Final[int] = 1
DEFAULT_LAYOUT_NAME: Final[str] = "Default"

WIDGET_IDS: Final[tuple[str, ...]] = (
    "home_name", "home_score", "possession", "away_name", "away_score",
    "game_clock_label", "game_clock_value",
    "quarter", "down", "distance",
    "play_clock_label", "play_clock_value", "ball_on",
    "home_timeouts", "away_timeouts",
)

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

#: Not part of the public schema constants above, but the same "1-40, no
#: control characters" limit :data:`scoreboard.infrastructure.layouts.
#: MAX_LAYOUT_NAME_LENGTH` enforces for a *stored* layout's name. It lives
#: here too because :func:`validate_layout_name` -- used for a layout
#: document's own ``name`` field -- must stay in this dependency-free module
#: rather than importing the infrastructure layer that depends on it.
_MAX_LAYOUT_NAME_LENGTH: Final[int] = 40

_KNOWN_WIDGET_PROPERTIES: Final[frozenset[str]] = frozenset({
    "id", "visible", "x", "y", "width", "height", "font_scale", "color",
    "text_align", "vertical_align", "font_weight", "z_index",
})

_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# --- Widget metadata (spec section 4.3) -------------------------------------

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
}

#: Application-controlled label text. Operators may style/move/hide it, never
#: edit it -- there is no free-text editor (spec section 1).
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
})

# --- Default layout geometry (spec section 4.4) -----------------------------

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
}

_DEFAULT_SAFE_AREA: Final[dict[str, float]] = {
    "top": DEFAULT_SAFE_INSET, "right": DEFAULT_SAFE_INSET,
    "bottom": DEFAULT_SAFE_INSET, "left": DEFAULT_SAFE_INSET,
}


# --- Issues and results ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    """One problem found in a layout document, or one repair made to it.

    ``message`` always names the affected widget by its human
    :data:`WIDGET_LABELS` text, never its raw id -- an operator reading the
    validation panel should never need the schema to understand what is wrong.
    """

    code: str
    message: str
    widget_id: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "widget_id": self.widget_id,
            "severity": self.severity,
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
    if number < minimum:
        return _round_coordinate(minimum), True
    if number > maximum:
        return _round_coordinate(maximum), True
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


# --- Widget validation --------------------------------------------------------


def _validate_widget(
    widget_id: str, raw: Any, safe_area: Mapping[str, float]
) -> tuple[dict[str, Any] | None, list[LayoutIssue], list[LayoutIssue]]:
    label = WIDGET_LABELS[widget_id]
    default = _DEFAULT_WIDGETS[widget_id]
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
    widgets: Mapping[str, dict[str, Any]],
) -> tuple[list[LayoutIssue], list[LayoutIssue]]:
    """Overlap is checked among **visible** widgets only (spec section 4.4):
    a hidden widget cannot visually collide with anything.
    """

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []
    ids = list(WIDGET_IDS)
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
            message = f"{WIDGET_LABELS[first_id]} and {WIDGET_LABELS[second_id]} overlap."
            if ratio >= SERIOUS_OVERLAP_RATIO:
                errors.append(LayoutIssue("OVERLAP", message, first_id))
            else:
                warnings.append(LayoutIssue("OVERLAP", message, first_id, severity="warning"))
    return errors, warnings


# --- Public API (spec section 4.6) ------------------------------------------


def default_widget(widget_id: str) -> dict[str, Any]:
    """A fresh copy of ``widget_id``'s built-in default widget."""

    return dict(_DEFAULT_WIDGETS[widget_id])


def default_layout(name: str = DEFAULT_LAYOUT_NAME) -> dict[str, Any]:
    """The built-in default layout, which reproduces today's spectator board."""

    return {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "name": name,
        "safe_area": dict(_DEFAULT_SAFE_AREA),
        "widgets": {widget_id: default_widget(widget_id) for widget_id in WIDGET_IDS},
    }


def validate_layout(payload: Any) -> LayoutValidation:
    """Strictly validate ``payload`` as a layout document.

    See the module docstring for what counts as an error versus a warning.
    This function never raises: every check is a type/membership test before
    any value is used, so arbitrary JSON-decoded input is safe to pass in
    directly.
    """

    if not isinstance(payload, dict):
        return LayoutValidation(
            None, (LayoutIssue("NOT_AN_OBJECT", "A layout must be an object."),)
        )

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != LAYOUT_SCHEMA_VERSION:
        errors.append(
            LayoutIssue(
                "SCHEMA_VERSION", f"schema_version must be {LAYOUT_SCHEMA_VERSION}; got {version!r}."
            )
        )

    name_value = payload.get("name", DEFAULT_LAYOUT_NAME)
    name_issue = validate_layout_name(name_value)
    if name_issue is not None:
        errors.append(name_issue)
        normalized_name = DEFAULT_LAYOUT_NAME
    else:
        normalized_name = name_value.strip()

    safe_area, safe_area_issues = _validate_safe_area(payload.get("safe_area"))
    # A supplied default is a warning; a value that cannot be read is an error.
    errors.extend(i for i in safe_area_issues if i.severity != "warning")
    warnings.extend(i for i in safe_area_issues if i.severity == "warning")

    raw_widgets = payload.get("widgets", {})
    if not isinstance(raw_widgets, dict):
        errors.append(LayoutIssue("WIDGETS", "widgets must be an object."))
        raw_widgets = {}

    for key in raw_widgets:
        if key not in WIDGET_IDS:
            warnings.append(
                LayoutIssue("UNKNOWN_WIDGET", f"Unknown widget {key!r} was ignored.", severity="warning")
            )

    normalized_widgets: dict[str, dict[str, Any]] = {}
    for widget_id in WIDGET_IDS:
        if widget_id not in raw_widgets:
            warnings.append(
                LayoutIssue(
                    "MISSING_WIDGET",
                    f"{WIDGET_LABELS[widget_id]} was missing and was filled with its default.",
                    widget_id,
                    severity="warning",
                )
            )
            normalized_widgets[widget_id] = default_widget(widget_id)
            continue
        normalized, widget_errors, widget_warnings = _validate_widget(
            widget_id, raw_widgets[widget_id], safe_area
        )
        errors.extend(widget_errors)
        warnings.extend(widget_warnings)
        normalized_widgets[widget_id] = normalized if normalized is not None else default_widget(widget_id)

    overlap_errors, overlap_warnings = _check_overlaps(normalized_widgets)
    errors.extend(overlap_errors)
    warnings.extend(overlap_warnings)

    if errors:
        return LayoutValidation(None, tuple(errors), tuple(warnings))

    layout = {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "name": normalized_name,
        "safe_area": safe_area,
        "widgets": {widget_id: normalized_widgets[widget_id] for widget_id in WIDGET_IDS},
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


def clamp_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    """Best-effort repair for the editor's "Fit to safe area" action.

    Only position, size, and font scale are adjusted -- never colour,
    alignment, weight, stacking order, visibility, or overlap (spec section
    4.6). This never raises: garbage input becomes the built-in default with
    no adjustments to report, exactly like :func:`load_layout`.
    """

    try:
        return _clamp_layout(payload)
    except Exception:  # noqa: BLE001 - a repair action must never crash the host
        return default_layout(), ()


def _clamp_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    if not isinstance(payload, dict):
        return default_layout(), ()

    issues: list[LayoutIssue] = []
    safe_area = _coerce_safe_area(payload.get("safe_area"))
    raw_widgets = payload.get("widgets")
    if not isinstance(raw_widgets, dict):
        raw_widgets = {}

    normalized_widgets: dict[str, dict[str, Any]] = {}
    for widget_id in WIDGET_IDS:
        default = default_widget(widget_id)
        raw = raw_widgets.get(widget_id)
        if not isinstance(raw, dict):
            normalized_widgets[widget_id] = default
            continue

        label = WIDGET_LABELS[widget_id]
        widget = dict(default)
        for passthrough in ("visible", "color", "text_align", "vertical_align", "font_weight", "z_index"):
            if passthrough in raw:
                widget[passthrough] = raw[passthrough]

        available_width = max(MIN_WIDGET_WIDTH, 1.0 - safe_area["left"] - safe_area["right"])
        available_height = max(MIN_WIDGET_HEIGHT, 1.0 - safe_area["top"] - safe_area["bottom"])
        width, width_changed = _clamp_number(
            raw.get("width", default["width"]), MIN_WIDGET_WIDTH, available_width, default["width"]
        )
        height, height_changed = _clamp_number(
            raw.get("height", default["height"]), MIN_WIDGET_HEIGHT, available_height, default["height"]
        )
        if width_changed and "width" in raw:
            issues.append(LayoutIssue("DIMENSION", f"{label}: width was adjusted to fit.", widget_id, "warning"))
        if height_changed and "height" in raw:
            issues.append(
                LayoutIssue("DIMENSION", f"{label}: height was adjusted to fit.", widget_id, "warning")
            )
        widget["width"], widget["height"] = width, height

        max_x = max(safe_area["left"], 1.0 - safe_area["right"] - width)
        max_y = max(safe_area["top"], 1.0 - safe_area["bottom"] - height)
        x, x_changed = _clamp_number(raw.get("x", default["x"]), safe_area["left"], max_x, default["x"])
        y, y_changed = _clamp_number(raw.get("y", default["y"]), safe_area["top"], max_y, default["y"])
        if x_changed and "x" in raw:
            issues.append(
                LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: x was moved inside the safe area.", widget_id, "warning")
            )
        if y_changed and "y" in raw:
            issues.append(
                LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: y was moved inside the safe area.", widget_id, "warning")
            )
        widget["x"], widget["y"] = x, y

        font_scale, font_scale_changed = _clamp_number(
            raw.get("font_scale", default["font_scale"]), MIN_FONT_SCALE, MAX_FONT_SCALE, default["font_scale"]
        )
        if font_scale_changed and "font_scale" in raw:
            issues.append(
                LayoutIssue("FONT_SCALE", f"{label}: font_scale was adjusted to fit.", widget_id, "warning")
            )
        widget["font_scale"] = font_scale
        widget["id"] = widget_id
        normalized_widgets[widget_id] = widget

    name_value = payload.get("name", DEFAULT_LAYOUT_NAME)
    name = DEFAULT_LAYOUT_NAME if validate_layout_name(name_value) is not None else name_value.strip()

    layout = {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "name": name,
        "safe_area": safe_area,
        "widgets": normalized_widgets,
    }
    return layout, tuple(issues)


def reset_widget(layout: Mapping[str, Any], widget_id: str) -> dict[str, Any]:
    """Restore exactly one widget to its default; every other widget is
    whatever ``layout`` already validates to. Never raises.
    """

    normalized, _warnings = load_layout(layout)
    if widget_id not in WIDGET_IDS:
        return normalized
    widgets = dict(normalized["widgets"])
    widgets[widget_id] = default_widget(widget_id)
    return {**normalized, "widgets": widgets}


def widget_descriptors() -> list[dict[str, Any]]:
    """Static metadata for every widget, in :data:`WIDGET_IDS` order.

    This drives the editor's widget list so it never hard-codes a widget id
    (spec section 8): the UI is generated entirely from this function's
    output.
    """

    return [
        {
            "id": widget_id,
            "label": WIDGET_LABELS[widget_id],
            "field": WIDGET_FIELDS[widget_id],
            "static_text": WIDGET_TEXTS.get(widget_id),
            "optional": widget_id in OPTIONAL_WIDGET_IDS,
            "default": default_widget(widget_id),
        }
        for widget_id in WIDGET_IDS
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
    }


def _resolve_path(view_model: Mapping[str, Any], path: str) -> Any:
    node: Any = view_model
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def supported_widget_ids(view_model: Mapping[str, Any]) -> tuple[str, ...]:
    """Ids whose field resolves to real data, plus every static-label id.

    Tolerates a completely empty view model: every static-label widget is
    still "supported" (it draws application-owned text regardless of game
    state), and every data-driven widget is simply absent.
    """

    if not isinstance(view_model, dict):
        view_model = {}
    supported = []
    for widget_id in WIDGET_IDS:
        field = WIDGET_FIELDS[widget_id]
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
    "FONT_WEIGHTS",
    "LAYOUT_SCHEMA_VERSION",
    "MAX_FONT_SCALE",
    "MAX_SAFE_INSET",
    "MAX_Z_INDEX",
    "MIN_FONT_SCALE",
    "MIN_SAFE_INSET",
    "MIN_SAFE_SPAN",
    "MIN_WIDGET_HEIGHT",
    "MIN_WIDGET_WIDTH",
    "MIN_Z_INDEX",
    "OPTIONAL_WIDGET_IDS",
    "SERIOUS_OVERLAP_RATIO",
    "TEXT_ALIGNMENTS",
    "VERTICAL_ALIGNMENTS",
    "WIDGET_FIELDS",
    "WIDGET_IDS",
    "WIDGET_LABELS",
    "WIDGET_TEXTS",
    "LayoutIssue",
    "LayoutValidation",
    "clamp_layout",
    "default_layout",
    "default_widget",
    "limits",
    "load_layout",
    "reset_widget",
    "supported_widget_ids",
    "validate_layout",
    "validate_layout_name",
    "widget_descriptors",
]
