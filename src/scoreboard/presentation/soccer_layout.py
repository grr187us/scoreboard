"""The soccer spectator presentation-layout schema (mirrors
``scoreboard.presentation.layout``, spec section 2.2/5.1).

Football's ``presentation/layout.py`` is frozen (hard rule 1): this module
never edits it, only imports its pure, registry-agnostic helpers (safe-area,
background, fill/border, animation, orientation, text-style, element, and
overlap validation; the small numeric/colour primitives; the Grid preset's
own box/text/palette builders) so a soccer widget is validated exactly as
strictly as a football one, without duplicating that logic. Everything that
*is* football-specific -- the widget id set, its dotted view-model paths, its
default geometry, and the one property (``period``'s Standard/Short format
choice) that football's ``_validate_widget`` cannot honour for a foreign
registry (its format-restriction branch is hard-wired to football's own
``WIDGET_REGISTRIES["game"]`` object by identity) -- is a fresh, soccer-owned
table and a small soccer-owned widget validator below.

The soccer game screen's document shape is identical to football's schema v3
(``schema_version``, ``widgets``, ``elements``, ``screens.pregame``/
``halftime``); the two event screens are **football's own, unchanged**
(spec section 5.1): a soccer layout's ``screens.pregame``/``halftime`` are
validated by calling ``layout._validate_screen(raw, "pregame")`` directly --
no override needed, since those screen ids are already registered in
football's ``SCREEN_KINDS``/``WIDGET_REGISTRIES`` -- so a soccer pre-game or
halftime board renders with exactly the same widgets, presets, and Python-
supplied wording football's own event screens do.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Final, Mapping

from scoreboard.presentation import layout as football_layout
from scoreboard.presentation.layout import (
    LayoutIssue,
    LayoutValidation,
    WidgetRegistry,
)

# --- Widget registry (spec 5.1) ---------------------------------------------

SOCCER_WIDGET_IDS: Final[tuple[str, ...]] = (
    "home_name", "home_score", "away_name", "away_score",
    "game_clock_label", "game_clock_value",
    "period",
    "status_message", "status_clock",
    "home_shots", "away_shots", "home_saves", "away_saves",
    "home_corners", "away_corners", "home_fouls", "away_fouls",
    "home_yellow", "away_yellow", "home_red", "away_red",
    "shootout_home", "shootout_away",
)

SOCCER_WIDGET_LABELS: Final[dict[str, str]] = {
    "home_name": "Home team name", "home_score": "Home score",
    "away_name": "Away team name", "away_score": "Away score",
    "game_clock_label": "Game clock label", "game_clock_value": "Game clock",
    "period": "Period",
    "status_message": "Crowd message", "status_clock": "Status countdown",
    "home_shots": "Home shots", "away_shots": "Away shots",
    "home_saves": "Home saves", "away_saves": "Away saves",
    "home_corners": "Home corners", "away_corners": "Away corners",
    "home_fouls": "Home fouls", "away_fouls": "Away fouls",
    "home_yellow": "Home yellow cards", "away_yellow": "Away yellow cards",
    "home_red": "Home red cards", "away_red": "Away red cards",
    "shootout_home": "Shootout - home", "shootout_away": "Shootout - away",
}

#: Dotted path into the soccer spectator view model (spec section 3.3).
#: ``None`` means a static label, exactly as football's own ``WIDGET_FIELDS``.
_FIELDS: Final[dict[str, str | None]] = {
    "home_name": "teams.home.name", "home_score": "teams.home.score",
    "away_name": "teams.away.name", "away_score": "teams.away.score",
    "game_clock_label": None, "game_clock_value": "clocks.game.display",
    "period": "period_display",
    "status_message": "status.display", "status_clock": "status.clock_display",
    "home_shots": "soccer.home.shots_display", "away_shots": "soccer.away.shots_display",
    "home_saves": "soccer.home.saves_display", "away_saves": "soccer.away.saves_display",
    "home_corners": "soccer.home.corners_display", "away_corners": "soccer.away.corners_display",
    "home_fouls": "soccer.home.fouls_display", "away_fouls": "soccer.away.fouls_display",
    "home_yellow": "soccer.home.cards.yellow_display", "away_yellow": "soccer.away.cards.yellow_display",
    "home_red": "soccer.home.cards.red_display", "away_red": "soccer.away.cards.red_display",
    "shootout_home": "soccer.shootout.home_display", "shootout_away": "soccer.shootout.away_display",
}
SOCCER_WIDGET_FIELDS: Final[dict[str, str | None]] = _FIELDS

#: Application-controlled label text (spec section 5.1); never operator-edited.
_TEXTS: Final[dict[str, str]] = {"game_clock_label": "GAME CLOCK"}
SOCCER_WIDGET_TEXTS: Final[dict[str, str]] = _TEXTS

#: ``period``'s Standard/Short format choice (spec section 5.1): "Standard"
#: reads football's own ``period_display`` field ("1st Half"); "Short" reads
#: a second field the bridge must also publish, ``period_display_short``
#: ("1ST") -- see this module's docstring and the report for the exact
#: contract agent B's view model must honour.
SOCCER_WIDGET_FORMAT_FIELDS: Final[dict[str, dict[str, str]]] = {
    "period": {"short": "period_display_short"},
}
SOCCER_WIDGET_FORMAT_LABELS: Final[dict[str, str]] = {
    "default": "Standard", "short": "Short (1ST)",
}

#: Widgets whose value can legitimately be absent (spec section 5.1): the
#: renderer hides them, rather than an empty box, exactly like football's
#: ``OPTIONAL_WIDGET_IDS``.
_OPTIONAL_WIDGET_IDS: Final[frozenset[str]] = frozenset({
    "status_message", "status_clock",
    "home_yellow", "away_yellow", "home_red", "away_red",
    "shootout_home", "shootout_away",
})
SOCCER_OPTIONAL_WIDGET_IDS: Final[frozenset[str]] = _OPTIONAL_WIDGET_IDS

#: The game-board widgets the wall must not draw once the game is FINAL or
#: while it is in SHOOTOUT (spec section 5.1): only the game clock -- period
#: keeps showing "FINAL"/"SHOOTOUT" so the wall still reads correctly. The
#: soccer spectator view model must list exactly these ids under
#: ``board.hidden_widgets`` whenever ``lifecycle == "FINAL"`` or
#: ``period == "SHOOTOUT"`` -- see the report for the exact bridge contract.
SOCCER_FINAL_HIDDEN_WIDGET_IDS: Final[tuple[str, ...]] = ("game_clock_label", "game_clock_value")

#: No free element in the built-in Soccer Grid preset frames the game clock
#: on its own (the gold frame decorates ``period`` instead, spec section
#: 5.2), but the prefix is still published, mirroring football's
#: ``FINAL_HIDDEN_ELEMENT_PREFIXES``, so a future preset or a hand-built
#: layout can name a clock-framing element and have it hide automatically.
SOCCER_FINAL_HIDDEN_ELEMENT_PREFIXES: Final[tuple[str, ...]] = ("game_clock_",)


def hidden_element_prefixes() -> tuple[str, ...]:
    """The element-id prefixes hidden alongside :data:`SOCCER_FINAL_HIDDEN_WIDGET_IDS`."""

    return SOCCER_FINAL_HIDDEN_ELEMENT_PREFIXES


_WIDGET_GROUPS: Final[dict[str, str]] = {
    "home_name": "Teams", "home_score": "Teams", "away_name": "Teams", "away_score": "Teams",
    "game_clock_label": "Clocks", "game_clock_value": "Clocks", "period": "Clocks",
    "home_shots": "Match", "away_shots": "Match", "home_saves": "Match", "away_saves": "Match",
    "home_corners": "Match", "away_corners": "Match", "home_fouls": "Match", "away_fouls": "Match",
    "home_yellow": "Cards", "away_yellow": "Cards", "home_red": "Cards", "away_red": "Cards",
    "shootout_home": "Shootout", "shootout_away": "Shootout",
    "status_message": "Status", "status_clock": "Status",
}
SOCCER_WIDGET_GROUPS: Final[dict[str, str]] = _WIDGET_GROUPS
SOCCER_WIDGET_GROUP_ORDER: Final[tuple[str, ...]] = (
    "Teams", "Clocks", "Match", "Cards", "Shootout", "Status",
)

SOCCER_REGISTRY: Final[WidgetRegistry] = WidgetRegistry(
    SOCCER_WIDGET_IDS, SOCCER_WIDGET_LABELS, SOCCER_WIDGET_FIELDS, SOCCER_WIDGET_TEXTS,
    SOCCER_OPTIONAL_WIDGET_IDS, SOCCER_WIDGET_GROUPS, SOCCER_WIDGET_GROUP_ORDER,
)

# --- Palette and fonts: the owner's Scoreboard Grid palette, unchanged ------
# (spec section 5.2: "same palette and fonts" as football's Grid preset).

_BG: Final[str] = "#030A12"
_PANEL: Final[str] = "#071321"
_WHITE: Final[str] = "#F2F2F2"
_AMBER: Final[str] = "#F5AE08"
_GOLD: Final[str] = "#E9A51A"
_HOME_BANNER: Final[str] = "#08439A"
_HOME_EDGE: Final[str] = "#2869BC"
_AWAY_BANNER: Final[str] = "#A50021"
_AWAY_EDGE: Final[str] = "#D0002C"
_SILVER: Final[str] = "#C5C9CD"
_YELLOW_CARD: Final[str] = "#FFD500"
_RED_CARD: Final[str] = "#FF4B4B"
_CUT: Final[float] = 0.012
_RULE_H: Final[float] = 0.003
_LABEL_FONT: Final[str] = "bahnschrift_condensed"
_DIGIT_FONT: Final[str] = "varsity"

#: Fit-to-box widgets (spec section 5.2): names, scores, the game clock, and
#: the period readout shrink rather than spill; nothing else does.
_FIT_TEXT_WIDGET_IDS: Final[frozenset[str]] = frozenset({
    "home_name", "away_name", "home_score", "away_score", "game_clock_value", "period",
})

# (visible, x, y, width, height, font_scale, color, font_weight, font_family)
_GEOMETRY: Final[dict[str, tuple[bool, float, float, float, float, float, str, int, str]]] = {
    "home_name": (True, 0.040, 0.090, 0.28, 0.11, 0.070, _WHITE, 700, _LABEL_FONT),
    "away_name": (True, 0.680, 0.090, 0.28, 0.11, 0.070, _WHITE, 700, _LABEL_FONT),
    "home_score": (True, 0.040, 0.225, 0.28, 0.36, 0.300, _WHITE, 700, _DIGIT_FONT),
    "away_score": (True, 0.680, 0.225, 0.28, 0.36, 0.300, _WHITE, 700, _DIGIT_FONT),
    "game_clock_label": (False, 0.360, 0.040, 0.28, 0.04, 0.020, _SILVER, 700, _LABEL_FONT),
    "game_clock_value": (True, 0.350, 0.090, 0.30, 0.32, 0.220, _AMBER, 700, _DIGIT_FONT),
    "period": (True, 0.350, 0.450, 0.30, 0.14, 0.090, _WHITE, 700, _DIGIT_FONT),
    "status_message": (True, 0.040, 0.045, 0.15, 0.035, 0.016, _AMBER, 800, _LABEL_FONT),
    "status_clock": (True, 0.195, 0.045, 0.08, 0.035, 0.016, _AMBER, 800, _LABEL_FONT),
    "home_shots": (False, 0.045, 0.625, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "away_shots": (False, 0.825, 0.625, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "home_saves": (False, 0.185, 0.625, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "away_saves": (False, 0.685, 0.625, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "home_corners": (False, 0.045, 0.720, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "away_corners": (False, 0.825, 0.720, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "home_fouls": (False, 0.185, 0.720, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "away_fouls": (False, 0.685, 0.720, 0.13, 0.09, 0.046, _WHITE, 700, _LABEL_FONT),
    "home_yellow": (False, 0.045, 0.815, 0.13, 0.075, 0.040, _YELLOW_CARD, 700, _LABEL_FONT),
    "away_yellow": (False, 0.825, 0.815, 0.13, 0.075, 0.040, _YELLOW_CARD, 700, _LABEL_FONT),
    "home_red": (False, 0.185, 0.815, 0.13, 0.075, 0.040, _RED_CARD, 700, _LABEL_FONT),
    "away_red": (False, 0.685, 0.815, 0.13, 0.075, 0.040, _RED_CARD, 700, _LABEL_FONT),
    "shootout_home": (False, 0.350, 0.620, 0.30, 0.10, 0.045, _WHITE, 700, _LABEL_FONT),
    "shootout_away": (False, 0.350, 0.730, 0.30, 0.10, 0.045, _WHITE, 700, _LABEL_FONT),
}


def _build_default_soccer_widget(widget_id: str) -> dict[str, Any]:
    visible, x, y, width, height, font_scale, color, font_weight, font_family = _GEOMETRY[widget_id]
    widget: dict[str, Any] = {
        "id": widget_id, "visible": visible,
        "x": x, "y": y, "width": width, "height": height, "font_scale": font_scale,
        "color": color, "text_align": "center", "vertical_align": "middle",
        "font_weight": font_weight, "z_index": 2,
    }
    widget.update(football_layout._STYLE_DEFAULTS)
    widget["font_family"] = font_family
    if widget_id in ("home_name", "away_name"):
        widget["text_transform"] = "uppercase"
    if widget_id in ("game_clock_label", "status_message", "status_clock"):
        widget["letter_spacing"] = 0.10
    widget["display_format"] = "default"
    widget["fit_text"] = widget_id in _FIT_TEXT_WIDGET_IDS
    return widget


#: The built-in default (also the Soccer Grid preset's) geometry for every
#: widget -- deep-copied on every read, exactly like football's
#: ``_DEFAULT_WIDGETS``.
_DEFAULT_SOCCER_WIDGETS: Final[dict[str, dict[str, Any]]] = {
    widget_id: _build_default_soccer_widget(widget_id) for widget_id in SOCCER_WIDGET_IDS
}


def default_soccer_widget(widget_id: str) -> dict[str, Any]:
    """A fresh copy of ``widget_id``'s built-in default widget."""

    return dict(_DEFAULT_SOCCER_WIDGETS[widget_id])


def _default_soccer_widgets() -> dict[str, dict[str, Any]]:
    return {widget_id: default_soccer_widget(widget_id) for widget_id in SOCCER_WIDGET_IDS}


# --- Widget validation (mirrors layout._validate_widget) --------------------
# football_layout._validate_widget cannot be reused as-is: its display_format
# allow-list is hard-wired to football's own game registry by identity
# (``registry is WIDGET_REGISTRIES["game"]``), so period's Standard/Short
# choice would always be rejected. Every other check below calls football's
# own pure, registry-agnostic helpers, so this stays a thin, mirrored
# function rather than a second full copy of the validator's logic.


def _validate_soccer_widget(
    widget_id: str, raw: Any, safe_area: Mapping[str, float], defaults: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[LayoutIssue], list[LayoutIssue]]:
    label = SOCCER_WIDGET_LABELS[widget_id]
    default = defaults[widget_id]
    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    if not isinstance(raw, dict):
        errors.append(LayoutIssue("WIDGET_ID", f"{label}: the widget entry must be an object.", widget_id))
        return None, errors, warnings

    id_value = raw.get("id", widget_id)
    if id_value != widget_id:
        errors.append(LayoutIssue("WIDGET_ID", f"{label}: id must be {widget_id!r}; got {id_value!r}.", widget_id))

    for key in raw:
        if key not in football_layout._KNOWN_WIDGET_PROPERTIES:
            warnings.append(
                LayoutIssue("UNKNOWN_PROPERTY", f"{label}: unknown property {key!r} was ignored.",
                            widget_id, severity="warning")
            )

    normalized: dict[str, Any] = {"id": widget_id}

    formats = SOCCER_WIDGET_FORMAT_FIELDS.get(widget_id, {})
    display_format = raw.get("display_format", "default")
    if not isinstance(display_format, str) or display_format not in ("default", *formats):
        errors.append(LayoutIssue("DISPLAY_FORMAT", f"{label}: unsupported display format.", widget_id))
        display_format = "default"
    normalized["display_format"] = display_format

    fit_text = raw.get("fit_text", default.get("fit_text", False))
    if not isinstance(fit_text, bool):
        errors.append(LayoutIssue("FIT_TEXT", f"{label}: shrink to fit must be true or false.", widget_id))
        fit_text = default.get("fit_text", False)
    normalized["fit_text"] = fit_text

    visible = raw.get("visible", default["visible"])
    if not isinstance(visible, bool):
        errors.append(LayoutIssue("VISIBLE", f"{label}: visible must be true or false; got {visible!r}.", widget_id))
        normalized["visible"] = default["visible"]
    else:
        normalized["visible"] = visible

    for coordinate in ("x", "y"):
        value = raw.get(coordinate, default[coordinate])
        ok, number = football_layout._is_finite_number(value)
        if not ok or not 0.0 <= number <= 1.0:
            errors.append(
                LayoutIssue("COORDINATE", f"{label}: {coordinate} must be between 0 and 1; got {value!r}.", widget_id)
            )
            normalized[coordinate] = default[coordinate]
        else:
            normalized[coordinate] = football_layout._round_coordinate(number)

    for dimension, minimum in (("width", football_layout.MIN_WIDGET_WIDTH), ("height", football_layout.MIN_WIDGET_HEIGHT)):
        value = raw.get(dimension, default[dimension])
        ok, number = football_layout._is_finite_number(value)
        if not ok or not 0.0 <= number <= 1.0:
            errors.append(
                LayoutIssue("DIMENSION", f"{label}: {dimension} must be between 0 and 1; got {value!r}.", widget_id)
            )
            normalized[dimension] = default[dimension]
        elif number < minimum:
            errors.append(
                LayoutIssue("MIN_DIMENSION", f"{label}: {dimension} must be at least {minimum}; got {number!r}.", widget_id)
            )
            normalized[dimension] = default[dimension]
        else:
            normalized[dimension] = football_layout._round_coordinate(number)

    value = raw.get("font_scale", default["font_scale"])
    ok, number = football_layout._is_finite_number(value)
    if not ok or not football_layout.MIN_FONT_SCALE <= number <= football_layout.MAX_FONT_SCALE:
        errors.append(
            LayoutIssue(
                "FONT_SCALE",
                f"{label}: font_scale must be between {football_layout.MIN_FONT_SCALE} and "
                f"{football_layout.MAX_FONT_SCALE}; got {value!r}.", widget_id,
            )
        )
        normalized["font_scale"] = default["font_scale"]
    else:
        normalized["font_scale"] = football_layout._round_coordinate(number)

    value = raw.get("color", default["color"])
    color = football_layout._normalize_color(value)
    if color is None:
        errors.append(LayoutIssue("COLOR", f"{label}: color must be a hex color like #RRGGBB; got {value!r}.", widget_id))
        normalized["color"] = default["color"]
    else:
        normalized["color"] = color

    value = raw.get("text_align", default["text_align"])
    if value not in football_layout.TEXT_ALIGNMENTS:
        errors.append(
            LayoutIssue("TEXT_ALIGN", f"{label}: text_align must be one of "
                        f"{list(football_layout.TEXT_ALIGNMENTS)}; got {value!r}.", widget_id)
        )
        normalized["text_align"] = default["text_align"]
    else:
        normalized["text_align"] = value

    value = raw.get("vertical_align", default["vertical_align"])
    if value not in football_layout.VERTICAL_ALIGNMENTS:
        errors.append(
            LayoutIssue("VERTICAL_ALIGN", f"{label}: vertical_align must be one of "
                        f"{list(football_layout.VERTICAL_ALIGNMENTS)}; got {value!r}.", widget_id)
        )
        normalized["vertical_align"] = default["vertical_align"]
    else:
        normalized["vertical_align"] = value

    value = raw.get("font_weight", default["font_weight"])
    if isinstance(value, bool) or value not in football_layout.FONT_WEIGHTS:
        errors.append(
            LayoutIssue("FONT_WEIGHT", f"{label}: font_weight must be one of "
                        f"{list(football_layout.FONT_WEIGHTS)}; got {value!r}.", widget_id)
        )
        normalized["font_weight"] = default["font_weight"]
    else:
        normalized["font_weight"] = value

    value = raw.get("z_index", default["z_index"])
    if (isinstance(value, bool) or not isinstance(value, int)
            or not football_layout.MIN_Z_INDEX <= value <= football_layout.MAX_Z_INDEX):
        errors.append(
            LayoutIssue("Z_INDEX", f"{label}: z_index must be between {football_layout.MIN_Z_INDEX} and "
                        f"{football_layout.MAX_Z_INDEX}; got {value!r}.", widget_id)
        )
        normalized["z_index"] = default["z_index"]
    else:
        normalized["z_index"] = value

    normalized.update(football_layout._validate_fill_and_border(raw, label, widget_id, default, errors))
    normalized.update(football_layout._validate_text_extra_style(raw, label, widget_id, default, errors))
    normalized["animation"] = football_layout._validate_animation(raw, label, widget_id, errors)
    normalized["orientation"] = football_layout._validate_orientation(raw, label, widget_id, default, errors)

    tolerance = 1e-6
    left, top = safe_area["left"], safe_area["top"]
    right, bottom = safe_area["right"], safe_area["bottom"]
    x, y = normalized["x"], normalized["y"]
    width, height = normalized["width"], normalized["height"]
    if x < left - tolerance:
        errors.append(LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the left safe-area edge.", widget_id))
    if y < top - tolerance:
        errors.append(LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the top safe-area edge.", widget_id))
    if x + width > 1.0 - right + tolerance:
        errors.append(LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the right safe-area edge.", widget_id))
    if y + height > 1.0 - bottom + tolerance:
        errors.append(LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: it extends past the bottom safe-area edge.", widget_id))

    return normalized, errors, warnings


def _validate_soccer_game_screen(raw: Any) -> tuple[dict[str, Any] | None, list[LayoutIssue], list[LayoutIssue]]:
    """Validate the top-level soccer game screen -- mirrors
    ``layout._validate_screen(raw, "game")`` for the soccer registry, using
    :func:`_validate_soccer_widget` in place of football's widget validator.
    """

    defaults = _default_soccer_widgets()
    if not isinstance(raw, dict):
        return None, [LayoutIssue("SCREEN", "The screen must be an object.", screen="game")], []

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    safe_area, safe_area_issues = football_layout._validate_safe_area(raw.get("safe_area"))
    errors.extend(i for i in safe_area_issues if i.severity != "warning")
    warnings.extend(i for i in safe_area_issues if i.severity == "warning")

    background, background_issues = football_layout._validate_background(raw.get("background"))
    errors.extend(i for i in background_issues if i.severity != "warning")
    warnings.extend(i for i in background_issues if i.severity == "warning")

    raw_widgets = raw.get("widgets", {})
    if not isinstance(raw_widgets, dict):
        errors.append(LayoutIssue("WIDGETS", "widgets must be an object."))
        raw_widgets = {}

    for key in raw_widgets:
        if key not in SOCCER_WIDGET_IDS:
            warnings.append(LayoutIssue("UNKNOWN_WIDGET", f"Unknown widget {key!r} was ignored.", severity="warning"))

    normalized_widgets: dict[str, dict[str, Any]] = {}
    for widget_id in SOCCER_WIDGET_IDS:
        if widget_id not in raw_widgets:
            warnings.append(
                LayoutIssue("MISSING_WIDGET", f"{SOCCER_WIDGET_LABELS[widget_id]} was missing and was "
                            "filled with its default.", widget_id, severity="warning")
            )
            normalized_widgets[widget_id] = dict(defaults[widget_id])
            continue
        normalized, widget_errors, widget_warnings = _validate_soccer_widget(
            widget_id, raw_widgets[widget_id], safe_area, defaults
        )
        errors.extend(widget_errors)
        warnings.extend(widget_warnings)
        normalized_widgets[widget_id] = normalized if normalized is not None else dict(defaults[widget_id])

    overlap_errors, overlap_warnings = football_layout._check_overlaps(normalized_widgets, SOCCER_REGISTRY)
    errors.extend(overlap_errors)
    warnings.extend(overlap_warnings)

    raw_elements = raw.get("elements", [])
    if not isinstance(raw_elements, list):
        errors.append(LayoutIssue("ELEMENTS", "elements must be a list."))
        raw_elements = []
    elif len(raw_elements) > football_layout.MAX_ELEMENTS:
        errors.append(
            LayoutIssue("MAX_ELEMENTS", f"A layout may have at most {football_layout.MAX_ELEMENTS} "
                        f"elements; got {len(raw_elements)}.")
        )
        raw_elements = raw_elements[: football_layout.MAX_ELEMENTS]

    normalized_elements: list[dict[str, Any]] = []
    seen_element_ids: set[str] = set()
    total_image_bytes = 0
    for index, raw_element in enumerate(raw_elements):
        normalized_element, element_errors, element_warnings, element_id, image_bytes = football_layout._validate_element(
            index, raw_element, safe_area, SOCCER_WIDGET_IDS
        )
        if element_id is not None and element_id not in SOCCER_WIDGET_IDS:
            if element_id in seen_element_ids:
                element_errors.append(
                    LayoutIssue("ELEMENT_ID", f"Element #{index + 1}: id {element_id!r} is used by "
                                "more than one element.", element_id)
                )
            else:
                seen_element_ids.add(element_id)
        errors.extend(element_errors)
        warnings.extend(element_warnings)
        normalized_elements.append(normalized_element)
        if image_bytes is not None:
            total_image_bytes += image_bytes

    if total_image_bytes > football_layout.MAX_TOTAL_IMAGE_BYTES:
        errors.append(
            LayoutIssue("IMAGES_TOO_LARGE", f"All images together must be at most "
                        f"{football_layout.MAX_TOTAL_IMAGE_BYTES} bytes; got {total_image_bytes}.")
        )

    tagged_errors = [replace(issue, screen="game") for issue in errors]
    tagged_warnings = [replace(issue, screen="game") for issue in warnings]

    if errors:
        return None, tagged_errors, tagged_warnings

    screen_doc = {
        "safe_area": safe_area, "background": background,
        "widgets": {widget_id: normalized_widgets[widget_id] for widget_id in SOCCER_WIDGET_IDS},
        "elements": normalized_elements,
    }
    return screen_doc, tagged_errors, tagged_warnings


def default_soccer_screen() -> dict[str, Any]:
    """The built-in default (unstyled geometry) game screen document."""

    return {
        "safe_area": dict(football_layout._DEFAULT_SAFE_AREA),
        "background": dict(football_layout._DEFAULT_BACKGROUND),
        "widgets": _default_soccer_widgets(),
        "elements": [],
    }


def validate_soccer_layout(payload: Any) -> LayoutValidation:
    """Strictly validate ``payload`` as a soccer layout document (mirrors
    ``layout.validate_layout``). The top level is the soccer game screen;
    ``screens.pregame``/``halftime`` are football's own event screens,
    unchanged (spec section 5.1) -- validated by calling
    ``layout._validate_screen`` directly, since those screen ids are already
    registered there.
    """

    if not isinstance(payload, dict):
        return LayoutValidation(None, (LayoutIssue("NOT_AN_OBJECT", "A layout must be an object."),))

    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []

    version = payload.get("schema_version")
    is_upgrade = False
    if (isinstance(version, bool) or not isinstance(version, int)
            or version not in football_layout._ACCEPTED_SCHEMA_VERSIONS):
        errors.append(LayoutIssue("SCHEMA_VERSION", f"schema_version must be 1, 2, or 3; got {version!r}."))
    elif version in (1, 2):
        is_upgrade = True
        warnings.append(
            LayoutIssue("SCHEMA_UPGRADED", "This layout was saved by an earlier version and was "
                        "upgraded; save it to keep the upgrade.", severity="warning")
        )

    name_value = payload.get("name", football_layout.DEFAULT_LAYOUT_NAME)
    name_issue = football_layout.validate_layout_name(name_value)
    if name_issue is not None:
        errors.append(name_issue)
        normalized_name = football_layout.DEFAULT_LAYOUT_NAME
    else:
        normalized_name = name_value.strip()

    game_screen, game_errors, game_warnings = _validate_soccer_game_screen(payload)
    errors.extend(game_errors)
    warnings.extend(game_warnings)

    raw_screens = payload.get("screens")
    screen_docs: dict[str, dict[str, Any]] = {}
    if raw_screens is None:
        if not is_upgrade:
            warnings.append(
                LayoutIssue("MISSING_SCREENS", "The pre-game and halftime screens were missing and "
                            "were filled with their defaults.", severity="warning")
            )
        for screen_id in football_layout.EVENT_SCREEN_IDS:
            screen_docs[screen_id] = football_layout.default_screen(screen_id)
    elif not isinstance(raw_screens, dict):
        errors.append(LayoutIssue("SCREENS", "screens must be an object."))
        for screen_id in football_layout.EVENT_SCREEN_IDS:
            screen_docs[screen_id] = football_layout.default_screen(screen_id)
    else:
        for key in raw_screens:
            if key not in football_layout.EVENT_SCREEN_IDS:
                warnings.append(LayoutIssue("UNKNOWN_SCREEN", f"Unknown screen {key!r} was ignored.", severity="warning"))
        for screen_id in football_layout.EVENT_SCREEN_IDS:
            if screen_id not in raw_screens:
                warnings.append(
                    LayoutIssue("MISSING_SCREEN", f"The {football_layout.SCREEN_LABELS[screen_id]} screen "
                                "was missing and was filled with its default.", severity="warning")
                )
                screen_docs[screen_id] = football_layout.default_screen(screen_id)
                continue
            normalized_screen, screen_errors, screen_warnings = football_layout._validate_screen(
                raw_screens[screen_id], screen_id
            )
            errors.extend(screen_errors)
            warnings.extend(screen_warnings)
            screen_docs[screen_id] = (
                normalized_screen if normalized_screen is not None else football_layout.default_screen(screen_id)
            )

    if errors:
        return LayoutValidation(None, tuple(errors), tuple(warnings))

    assert game_screen is not None
    layout = {
        "schema_version": football_layout.LAYOUT_SCHEMA_VERSION,
        "name": normalized_name,
        "safe_area": game_screen["safe_area"],
        "background": game_screen["background"],
        "widgets": game_screen["widgets"],
        "elements": game_screen["elements"],
        "screens": {"pregame": screen_docs["pregame"], "halftime": screen_docs["halftime"]},
    }
    return LayoutValidation(layout, tuple(errors), tuple(warnings))


def load_soccer_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    """Never-raising entry point: a valid soccer layout, or the built-in default."""

    try:
        result = validate_soccer_layout(payload)
    except Exception as exc:  # noqa: BLE001 - a layout file must never crash the host
        return default_soccer_layout(), (LayoutIssue("NOT_AN_OBJECT", f"The layout could not be read: {exc}"),)
    if result.ok:
        assert result.layout is not None
        return result.layout, result.warnings
    return default_soccer_layout(), result.errors + result.warnings


def clamp_soccer_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    """Best-effort "Fit to safe area" repair, mirroring ``layout.clamp_layout``."""

    try:
        return _clamp_soccer_layout(payload)
    except Exception:  # noqa: BLE001 - a repair action must never crash the host
        return default_soccer_layout(), ()


def _clamp_soccer_game_screen(raw: Any) -> tuple[dict[str, Any], list[LayoutIssue]]:
    issues: list[LayoutIssue] = []
    safe_area = football_layout._coerce_safe_area(raw.get("safe_area") if isinstance(raw, dict) else None)
    raw_widgets = raw.get("widgets") if isinstance(raw, dict) else None
    if not isinstance(raw_widgets, dict):
        raw_widgets = {}

    defaults = _default_soccer_widgets()
    normalized_widgets: dict[str, dict[str, Any]] = {}
    for widget_id in SOCCER_WIDGET_IDS:
        default = defaults[widget_id]
        raw_widget = raw_widgets.get(widget_id)
        if not isinstance(raw_widget, dict):
            normalized_widgets[widget_id] = dict(default)
            continue

        label = SOCCER_WIDGET_LABELS[widget_id]
        widget = dict(default)
        for passthrough in football_layout._CLAMP_PASSTHROUGH_PROPERTIES:
            if passthrough in raw_widget:
                widget[passthrough] = raw_widget[passthrough]

        available_width = max(football_layout.MIN_WIDGET_WIDTH, 1.0 - safe_area["left"] - safe_area["right"])
        available_height = max(football_layout.MIN_WIDGET_HEIGHT, 1.0 - safe_area["top"] - safe_area["bottom"])
        width, width_changed = football_layout._clamp_number(
            raw_widget.get("width", default["width"]), football_layout.MIN_WIDGET_WIDTH, available_width, default["width"]
        )
        height, height_changed = football_layout._clamp_number(
            raw_widget.get("height", default["height"]), football_layout.MIN_WIDGET_HEIGHT, available_height, default["height"]
        )
        if width_changed and "width" in raw_widget:
            issues.append(LayoutIssue("DIMENSION", f"{label}: width was adjusted to fit.", widget_id, "warning", "game"))
        if height_changed and "height" in raw_widget:
            issues.append(LayoutIssue("DIMENSION", f"{label}: height was adjusted to fit.", widget_id, "warning", "game"))
        widget["width"], widget["height"] = width, height

        max_x = max(safe_area["left"], 1.0 - safe_area["right"] - width)
        max_y = max(safe_area["top"], 1.0 - safe_area["bottom"] - height)
        x, x_changed = football_layout._clamp_number(raw_widget.get("x", default["x"]), safe_area["left"], max_x, default["x"])
        y, y_changed = football_layout._clamp_number(raw_widget.get("y", default["y"]), safe_area["top"], max_y, default["y"])
        if x_changed and "x" in raw_widget:
            issues.append(LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: x was moved inside the safe area.", widget_id, "warning", "game"))
        if y_changed and "y" in raw_widget:
            issues.append(LayoutIssue("OUTSIDE_SAFE_AREA", f"{label}: y was moved inside the safe area.", widget_id, "warning", "game"))
        widget["x"], widget["y"] = x, y

        font_scale, font_scale_changed = football_layout._clamp_number(
            raw_widget.get("font_scale", default["font_scale"]), football_layout.MIN_FONT_SCALE,
            football_layout.MAX_FONT_SCALE, default["font_scale"]
        )
        if font_scale_changed and "font_scale" in raw_widget:
            issues.append(LayoutIssue("FONT_SCALE", f"{label}: font_scale was adjusted to fit.", widget_id, "warning", "game"))
        widget["font_scale"] = font_scale
        widget["id"] = widget_id
        normalized_widgets[widget_id] = widget

    raw_elements = raw.get("elements") if isinstance(raw, dict) else None
    elements: list[dict[str, Any]] = []
    if isinstance(raw_elements, list):
        for raw_element in raw_elements[: football_layout.MAX_ELEMENTS]:
            clamped_element = football_layout._clamp_element(raw_element, safe_area)
            if clamped_element is None:
                continue
            label = football_layout.element_label(clamped_element)
            element_id = clamped_element["id"]
            for prop, code, what in (
                ("width", "DIMENSION", "width was adjusted to fit"),
                ("height", "DIMENSION", "height was adjusted to fit"),
                ("x", "OUTSIDE_SAFE_AREA", "x was moved inside its boundary"),
                ("y", "OUTSIDE_SAFE_AREA", "y was moved inside its boundary"),
            ):
                if prop in raw_element and raw_element[prop] != clamped_element[prop]:
                    issues.append(LayoutIssue(code, f"{label}: {what}.", element_id, "warning", "game"))
            elements.append(clamped_element)

    screen_doc = {
        "safe_area": safe_area,
        "background": football_layout._coerce_background(raw.get("background") if isinstance(raw, dict) else None),
        "widgets": normalized_widgets,
        "elements": elements,
    }
    return screen_doc, issues


def _clamp_soccer_layout(payload: Any) -> tuple[dict[str, Any], tuple[LayoutIssue, ...]]:
    if not isinstance(payload, dict):
        return default_soccer_layout(), ()

    issues: list[LayoutIssue] = []
    game_screen, game_issues = _clamp_soccer_game_screen(payload)
    issues.extend(game_issues)

    raw_screens = payload.get("screens")
    if not isinstance(raw_screens, dict):
        raw_screens = {}

    screen_docs: dict[str, dict[str, Any]] = {}
    for screen_id in football_layout.EVENT_SCREEN_IDS:
        registry = football_layout.WIDGET_REGISTRIES[football_layout.SCREEN_KINDS[screen_id]]
        defaults = {
            widget_id: football_layout.default_screen_widget(screen_id, widget_id) for widget_id in registry.ids
        }
        screen_doc, screen_issues = football_layout._clamp_screen(raw_screens.get(screen_id), registry, defaults, screen_id)
        screen_docs[screen_id] = screen_doc
        issues.extend(screen_issues)

    name_value = payload.get("name", football_layout.DEFAULT_LAYOUT_NAME)
    name = (
        football_layout.DEFAULT_LAYOUT_NAME
        if football_layout.validate_layout_name(name_value) is not None
        else name_value.strip()
    )

    layout = {
        "schema_version": football_layout.LAYOUT_SCHEMA_VERSION,
        "name": name,
        "safe_area": game_screen["safe_area"],
        "background": game_screen["background"],
        "widgets": game_screen["widgets"],
        "elements": game_screen["elements"],
        "screens": {"pregame": screen_docs["pregame"], "halftime": screen_docs["halftime"]},
    }
    return layout, tuple(issues)


def reset_soccer_widget(layout: Mapping[str, Any], widget_id: str, screen: str = "game") -> dict[str, Any]:
    """Restore exactly one widget, on one screen, to its default (mirrors
    ``layout.reset_widget``). Never raises.
    """

    normalized, _warnings = load_soccer_layout(layout)
    if screen == "game":
        if widget_id not in SOCCER_WIDGET_IDS:
            return normalized
        widgets = dict(normalized["widgets"])
        widgets[widget_id] = default_soccer_widget(widget_id)
        return {**normalized, "widgets": widgets}

    if screen not in football_layout.EVENT_SCREEN_IDS:
        return normalized
    registry = football_layout.WIDGET_REGISTRIES[football_layout.SCREEN_KINDS[screen]]
    if widget_id not in registry.ids:
        return normalized
    default = football_layout.default_screen_widget(screen, widget_id)
    screens = dict(normalized["screens"])
    screen_doc = dict(screens[screen])
    widgets = dict(screen_doc["widgets"])
    widgets[widget_id] = default
    screens[screen] = {**screen_doc, "widgets": widgets}
    return {**normalized, "screens": screens}


def soccer_widget_descriptors(kind: str = "soccer") -> list[dict[str, Any]]:
    """Static metadata for every widget of ``kind`` (``"soccer"`` or
    ``"event"``), mirroring ``layout.widget_descriptors``. ``"event"``
    delegates straight to football's own descriptors -- the pre-game/
    halftime registry is football's, unchanged.
    """

    if kind == "event":
        return football_layout.widget_descriptors("event")
    return [
        {
            "id": widget_id,
            "label": SOCCER_WIDGET_LABELS[widget_id],
            "field": SOCCER_WIDGET_FIELDS[widget_id],
            "static_text": SOCCER_WIDGET_TEXTS.get(widget_id),
            "optional": widget_id in SOCCER_OPTIONAL_WIDGET_IDS,
            "group": SOCCER_WIDGET_GROUPS[widget_id],
            "default": default_soccer_widget(widget_id),
            "formats": [
                {"id": format_id, "label": SOCCER_WIDGET_FORMAT_LABELS[format_id]}
                for format_id in ("default", *SOCCER_WIDGET_FORMAT_FIELDS.get(widget_id, {}))
            ],
        }
        for widget_id in SOCCER_WIDGET_IDS
    ]


def soccer_screen_descriptors() -> list[dict[str, Any]]:
    """Every screen's metadata, in ``("game", "pregame", "halftime")`` order:
    a ``"soccer"``-kind game screen, then football's own pre-game/halftime
    descriptors, unchanged (spec section 5.1).
    """

    game_descriptor = {
        "id": "game", "label": "Game", "kind": "soccer",
        "widgets": soccer_widget_descriptors("soccer"),
        "widget_groups": list(SOCCER_WIDGET_GROUP_ORDER),
    }
    football_descriptors = {entry["id"]: entry for entry in football_layout.screen_descriptors()}
    return [game_descriptor, football_descriptors["pregame"], football_descriptors["halftime"]]


# --- Presets (spec section 5.2/5.3): Soccer Grid (default), Broadcast bar, --
# Classic. Event-screen presets are football's own, unchanged (reused as-is).


def default_soccer_layout(name: str = football_layout.DEFAULT_LAYOUT_NAME) -> dict[str, Any]:
    """The built-in default: "Soccer Grid" (spec section 5.2) -- the owner's
    Scoreboard Grid palette applied to the soccer widget set, with the same
    Grid-style pre-game/halftime event screens football's own Grid preset
    uses.
    """

    return _normalized_soccer_preset(_raw_soccer_grid_layout(name))


def _grid_header_elements() -> list[dict[str, Any]]:
    """Corner stripes and the silver heading (spec section 5.2), matching
    football's Grid header trim exactly but titled for soccer.
    """

    return [
        football_layout._grid_box("home_rule", 0.025, 0.034, 0.31, _RULE_H, _HOME_EDGE),
        football_layout._grid_box("home_tab", 0.185, 0.02, 0.15, 0.017, _HOME_EDGE, corner_cut=0.006, cut_corners="right"),
        football_layout._grid_box("away_rule", 0.665, 0.034, 0.31, _RULE_H, _AWAY_EDGE),
        football_layout._grid_box("away_tab", 0.665, 0.02, 0.15, 0.017, _AWAY_EDGE, corner_cut=0.006, cut_corners="left"),
        football_layout._grid_text("title", "HIGH SCHOOL SOCCER", 0.30, 0.04, 0.40, 0.045, 0.019,
                                    _SILVER, letter_spacing=0.16, font_family=_LABEL_FONT),
    ]


def _raw_soccer_grid_layout(name: str) -> dict[str, Any]:
    layout: dict[str, Any] = {
        "schema_version": football_layout.LAYOUT_SCHEMA_VERSION,
        "name": name,
        "safe_area": dict(football_layout._DEFAULT_SAFE_AREA),
        "background": {"color": _BG},
        "widgets": _default_soccer_widgets(),
        "elements": [],
    }

    elements = _grid_header_elements()
    for side, edge, banner, x in (("home", _HOME_EDGE, _HOME_BANNER, 0.025), ("away", _AWAY_EDGE, _AWAY_BANNER, 0.665)):
        elements += [
            football_layout._grid_box(f"{side}_panel", x, 0.085, 0.31, 0.635, _PANEL,
                                       border_color=edge, border_width=0.0015, corner_cut=_CUT),
            football_layout._grid_box(f"{side}_banner", x, 0.085, 0.31, 0.12, banner, z_index=1,
                                       border_color=_SILVER, border_width=0.0015, corner_cut=_CUT, cut_corners="top"),
        ]
    # The gold-framed period cell (spec section 5.2: "instead of the
    # play-clock panel"), a small margin around the period widget's box.
    elements.append(
        football_layout._grid_box("period_panel", 0.335, 0.435, 0.33, 0.17, None,
                                   border_color=_GOLD, border_width=0.002, corner_cut=0.016, z_index=0)
    )
    layout["elements"] = elements
    layout["screens"] = {
        screen_id: football_layout._grid_event_screen(screen_id) for screen_id in football_layout.EVENT_SCREEN_IDS
    }
    return layout


def _broadcast_soccer_layout() -> dict[str, Any]:
    """Soccer widgets in football's Broadcast bar geometry (spec 5.2)."""

    layout: dict[str, Any] = {
        "schema_version": football_layout.LAYOUT_SCHEMA_VERSION,
        "name": "Broadcast bar",
        "safe_area": dict(football_layout._DEFAULT_SAFE_AREA),
        "background": {"color": "#000000"},
        "widgets": _default_soccer_widgets(),
        "elements": [],
    }
    overrides: dict[str, dict[str, Any]] = {
        "home_name": {"x": 0.05, "y": 0.80, "width": 0.20, "height": 0.14, "font_scale": 0.032,
                      "text_align": "right", "font_family": "arial", "text_transform": "none",
                      "color": "#FFFFFF"},
        "home_score": {"x": 0.26, "y": 0.80, "width": 0.12, "height": 0.14, "font_scale": 0.07,
                       "font_family": "arial", "color": "#FFFFFF"},
        "game_clock_value": {"x": 0.39, "y": 0.80, "width": 0.22, "height": 0.14, "font_scale": 0.08,
                              "font_family": "arial", "color": "#FFFFFF"},
        "away_score": {"x": 0.62, "y": 0.80, "width": 0.12, "height": 0.14, "font_scale": 0.07,
                       "font_family": "arial", "color": "#FFFFFF"},
        "away_name": {"x": 0.75, "y": 0.80, "width": 0.20, "height": 0.14, "font_scale": 0.032,
                      "text_align": "left", "font_family": "arial", "text_transform": "none",
                      "color": "#FFFFFF"},
        "period": {"x": 0.04, "y": 0.705, "width": 0.30, "height": 0.065, "font_scale": 0.028,
                   "text_align": "left", "font_family": "arial", "color": "#FFFFFF"},
        "status_message": {"x": 0.38, "y": 0.705, "width": 0.28, "height": 0.065, "font_scale": 0.022},
        "status_clock": {"x": 0.68, "y": 0.705, "width": 0.16, "height": 0.065, "font_scale": 0.022},
    }
    for widget_id, changes in overrides.items():
        layout["widgets"][widget_id].update(changes)
    layout["elements"] = [
        {"id": "broadcast_bar", "type": "box", "x": 0.0, "y": 0.78, "width": 1.0, "height": 0.18,
         "background": "#101820", "corner_radius": 0.012, "z_index": 0},
    ]
    layout["screens"] = {
        "pregame": football_layout._broadcast_bar_screen("pregame"),
        "halftime": football_layout._broadcast_bar_screen("halftime"),
    }
    return layout


def _classic_soccer_layout() -> dict[str, Any]:
    """Plain, unstyled geometry -- the base widget default with a black
    background, no free elements, and football's own default (Broadcast
    Welcome) event screens (spec section 5.2).
    """

    layout: dict[str, Any] = {
        "schema_version": football_layout.LAYOUT_SCHEMA_VERSION,
        "name": "Classic",
        "safe_area": dict(football_layout._DEFAULT_SAFE_AREA),
        "background": {"color": "#000000"},
        "widgets": _default_soccer_widgets(),
        "elements": [],
    }
    plain: dict[str, Any] = {"font_family": "arial", "text_transform": "none", "color": "#FFFFFF"}
    for widget_id in ("home_name", "away_name", "home_score", "away_score", "game_clock_value", "period"):
        layout["widgets"][widget_id].update(plain)
    layout["widgets"]["status_message"]["color"] = "#FFC845"
    layout["widgets"]["status_clock"]["color"] = "#FFC845"
    layout["screens"] = {
        "pregame": football_layout.default_screen("pregame"),
        "halftime": football_layout.default_screen("halftime"),
    }
    return layout


def _normalized_soccer_preset(layout: dict[str, Any]) -> dict[str, Any]:
    result = validate_soccer_layout(layout)
    if not result.ok or result.layout is None:
        return layout
    return result.layout


def soccer_preset_descriptors() -> list[dict[str, Any]]:
    """The built-in soccer game presets (spec section 5.2): Soccer Grid
    (the default), Broadcast bar, and Classic.
    """

    return [
        {
            "id": "grid", "name": "Soccer Grid",
            "description": "The default: square blue and red HOME/AWAY panels with block-digit "
            "scores, an amber game clock, and a gold-framed period readout.",
            "layout": _normalized_soccer_preset(_raw_soccer_grid_layout("Soccer Grid")),
        },
        {
            "id": "broadcast", "name": "Broadcast bar",
            "description": "A dark bar across the bottom holds the score and clock; the top of "
            "the board stays free for future media.",
            "layout": _normalized_soccer_preset(_broadcast_soccer_layout()),
        },
        {
            "id": "classic", "name": "Classic",
            "description": "A plain, unstyled arrangement: centred names and scores, the game "
            "clock and period below.",
            "layout": _normalized_soccer_preset(_classic_soccer_layout()),
        },
    ]


def soccer_screen_preset_descriptors() -> dict[str, list[dict[str, Any]]]:
    """The pre-game/halftime screen presets -- football's own, unchanged
    (spec section 5.1): the same gallery (Classic, Matchup, Score first,
    Broadcast bar, Scoreboard Grid, Tigers navy...) applies to a soccer
    layout's event screens exactly as it does to football's.
    """

    return football_layout.screen_preset_descriptors()


def soccer_limits() -> dict[str, Any]:
    """Every schema constant the soccer editor's inputs need (mirrors
    ``layout.limits``): football's shared numeric/style limits, plus the
    soccer-specific screens/widget-groups tables.
    """

    limits = dict(football_layout.limits())
    limits["widget_groups"] = list(SOCCER_WIDGET_GROUP_ORDER)
    limits["screens"] = [
        {"id": "game", "label": "Game", "kind": "soccer"},
        {"id": "pregame", "label": football_layout.SCREEN_LABELS["pregame"], "kind": "event"},
        {"id": "halftime", "label": football_layout.SCREEN_LABELS["halftime"], "kind": "event"},
    ]
    return limits


def supported_widget_ids(view_model: Mapping[str, Any], kind: str = "soccer") -> tuple[str, ...]:
    """Ids of ``kind`` (``"soccer"`` or ``"event"``) whose field resolves to
    real data, plus every static-label id (mirrors ``layout.supported_widget_ids``).
    """

    if kind == "event":
        return football_layout.supported_widget_ids(view_model, "event")
    if not isinstance(view_model, dict):
        view_model = {}
    supported = []
    for widget_id in SOCCER_WIDGET_IDS:
        field = SOCCER_WIDGET_FIELDS[widget_id]
        if field is None:
            supported.append(widget_id)
            continue
        value = football_layout._resolve_path(view_model, field)
        if value is None or value == "":
            continue
        supported.append(widget_id)
    return tuple(supported)


#: Generic aliases matching football's own names (``default_layout``,
#: ``validate_layout``, ...): this is what lets ``soccer_layout`` itself be
#: passed as the ``schema=``/``layout_module=`` object to
#: ``infrastructure.layouts`` and ``host.layout_bridge.PresentationLayouts``
#: (spec section 2.3/3, "Presentation" interface contract) without those
#: shared modules needing to know soccer's function names at all.
WIDGET_IDS = SOCCER_WIDGET_IDS
default_layout = default_soccer_layout
validate_layout = validate_soccer_layout
validate_layout_name = football_layout.validate_layout_name
clamp_layout = clamp_soccer_layout
reset_widget = reset_soccer_widget
widget_descriptors = soccer_widget_descriptors
screen_descriptors = soccer_screen_descriptors
preset_descriptors = soccer_preset_descriptors
screen_preset_descriptors = soccer_screen_preset_descriptors
limits = soccer_limits


__all__ = [
    "WIDGET_IDS",
    "SOCCER_WIDGET_IDS",
    "SOCCER_WIDGET_LABELS",
    "SOCCER_WIDGET_FIELDS",
    "SOCCER_WIDGET_TEXTS",
    "SOCCER_WIDGET_FORMAT_FIELDS",
    "SOCCER_WIDGET_FORMAT_LABELS",
    "SOCCER_OPTIONAL_WIDGET_IDS",
    "SOCCER_WIDGET_GROUPS",
    "SOCCER_WIDGET_GROUP_ORDER",
    "SOCCER_REGISTRY",
    "SOCCER_FINAL_HIDDEN_WIDGET_IDS",
    "SOCCER_FINAL_HIDDEN_ELEMENT_PREFIXES",
    "hidden_element_prefixes",
    "default_soccer_widget",
    "default_soccer_screen",
    "default_soccer_layout",
    "validate_soccer_layout",
    "load_soccer_layout",
    "clamp_soccer_layout",
    "reset_soccer_widget",
    "soccer_widget_descriptors",
    "soccer_screen_descriptors",
    "soccer_preset_descriptors",
    "soccer_screen_preset_descriptors",
    "soccer_limits",
    "supported_widget_ids",
    "default_layout",
    "validate_layout",
    "validate_layout_name",
    "clamp_layout",
    "reset_widget",
    "widget_descriptors",
    "screen_descriptors",
    "preset_descriptors",
    "screen_preset_descriptors",
    "limits",
]
