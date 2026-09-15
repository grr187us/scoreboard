"""Soccer's cutscene registry, pack-manifest validation, and the program.

Mirrors :mod:`scoreboard.presentation.cutscenes` (football; frozen, spec
section 12 of ``seams_audit.md``) for spec section 7 ("GOAL cutscene") of
``.scratch/soccer-mode/spec.md``. There is exactly one soccer event so far,
``goal``. The one genuine departure from football's design (owner choice F,
spec section 7 and ``design_draft.md`` section 6): football's cutscenes are
unconditionally the home team's (the wall is the Tigers' wall); soccer's GOAL
must celebrate whichever side actually scored, so :func:`build_program` takes
a required keyword-only ``team`` argument and reads the scoring team's name
from the live spectator view rather than from a fixed school identity.

Stateless helpers that do not encode any football-specific vocabulary are
reused directly by import from the football module (:data:`SCENE_TYPES`,
:data:`MEDIA_EXTENSIONS`, :data:`FIT_MODES`, :data:`MANIFEST_SCHEMA_VERSION`,
:data:`BUILTIN_PACK_PREFIX`, :data:`INTRO_IDS`, :data:`INTRO_DURATION_MS`,
:data:`STAGE`, :data:`THEME`, :class:`CutsceneIssue`, :class:`ManifestValidation`,
:func:`normalize_pack`) -- the football module itself is never edited (hard
rule 1). Football's private ``_validate_scene`` is *not* reused: it checks a
builtin scene id against football's own ``BUILTIN_SCENE_IDS`` by closure, so
this module keeps its own copy scoped to soccer's scene ids.
"""

from __future__ import annotations

import copy
from pathlib import PurePosixPath
from typing import Any, Collection, Final, Mapping

from scoreboard.presentation.cutscenes import (
    BUILTIN_PACK_PREFIX,
    CutsceneIssue,
    FIT_MODES,
    INTRO_DURATION_MS,
    INTRO_IDS,
    ManifestValidation,
    MANIFEST_SCHEMA_VERSION,
    MEDIA_EXTENSIONS,
    SCENE_TYPES,
    STAGE,
    THEME,
    _is_finite_number,
    normalize_pack,
)

# --- Constants (spec section 7; exact names and values) ---------------------

SOCCER_CUTSCENE_EVENTS: Final[tuple[str, ...]] = ("goal",)
EVENT_LABELS: Final[dict[str, str]] = {"goal": "Goal"}
EVENT_HEADLINES: Final[dict[str, str]] = {"goal": "GOAL"}
#: Unlike football's fixed ``EVENT_TEAM`` (always ``"home"``, or ``None`` for
#: the team-neutral penalty), a GOAL is whichever side actually scored --
#: there is no default team here at all; the trigger always supplies one.
DEFAULT_DURATION_SECONDS: Final[dict[str, float]] = {"goal": 7.0}
MIN_DURATION_SECONDS: Final[float] = 2.0
MAX_DURATION_SECONDS: Final[float] = 30.0
#: A GOAL has no intro -- the scene is on the wall the instant the board
#: finishes morphing to the Broadcast bar underneath it.
EVENT_DEFAULT_INTRO: Final[dict[str, str]] = {"goal": "none"}
#: Milliseconds the outro (fade + restore) takes -- the same 600 ms football
#: uses, defined independently so this module carries no import-time
#: coupling to a football constant that could someday change.
SOCCER_OUTRO_DURATION_MS: Final[int] = 600
BUILTIN_SCENE_IDS: Final[dict[str, str]] = {"goal": "goal"}
SOCCER_MANIFEST_SCHEMA_VERSION: Final[int] = MANIFEST_SCHEMA_VERSION
SOCCER_BUILTIN_PACK_PREFIX: Final[str] = BUILTIN_PACK_PREFIX

#: The saved team-identity fallback colours (spec section 7): navy for the
#: home side, red for the away side, used only when the live spectator view
#: carries no saved primary colour for that team.
FALLBACK_HOME_PRIMARY: Final[str] = "#08439A"
FALLBACK_AWAY_PRIMARY: Final[str] = "#A50021"

#: The widget properties a cutscene program borrows from the operator's
#: active layout, same list football's ``CUTSCENE_STYLE_KEYS`` uses.
CUTSCENE_STYLE_KEYS: Final[tuple[str, ...]] = (
    "color", "font_family", "font_weight", "letter_spacing", "text_transform", "text_effect",
)


# --- Manifest validation (mirrors football's validate_manifest) -------------


def _validate_scene(raw_scene: Any, files: Collection[str]) -> tuple[dict[str, Any] | None, list[CutsceneIssue]]:
    """Validate the ``scene`` block of a manifest. ``None`` means unusable.

    Identical in every rule to football's private ``_validate_scene``
    (:mod:`scoreboard.presentation.cutscenes`), copied rather than imported
    because that function checks a builtin id against football's own
    ``BUILTIN_SCENE_IDS`` by closure over its own module globals -- importing
    it here would validate a soccer manifest's ``scene.id`` against
    football's five ids instead of soccer's one.
    """

    issues: list[CutsceneIssue] = []
    if not isinstance(raw_scene, dict):
        issues.append(CutsceneIssue("MANIFEST_SCENE", "scene must be an object."))
        return None, issues

    scene_type = raw_scene.get("type")
    if scene_type not in SCENE_TYPES:
        issues.append(
            CutsceneIssue(
                "MANIFEST_SCENE", f"scene.type must be one of {list(SCENE_TYPES)}; got {scene_type!r}."
            )
        )
        return None, issues

    if scene_type == "builtin":
        scene_id = raw_scene.get("id")
        if scene_id not in BUILTIN_SCENE_IDS.values():
            issues.append(
                CutsceneIssue(
                    "MANIFEST_SCENE",
                    f"scene.id must be one of {list(BUILTIN_SCENE_IDS.values())}; got {scene_id!r}.",
                )
            )
            return None, issues
        return {"type": "builtin", "id": scene_id}, issues

    src = raw_scene.get("src")
    if (
        not isinstance(src, str)
        or not src
        or "/" in src
        or "\\" in src
        or ".." in src
    ):
        issues.append(
            CutsceneIssue("MANIFEST_MEDIA", f"scene.src must be a plain filename; got {src!r}.")
        )
        return None, issues

    extension = PurePosixPath(src).suffix.lower()
    if extension not in MEDIA_EXTENSIONS[scene_type]:
        issues.append(
            CutsceneIssue(
                "MANIFEST_MEDIA",
                f"scene.src {src!r} must end in one of {MEDIA_EXTENSIONS[scene_type]}.",
            )
        )
        return None, issues

    if src not in files:
        issues.append(
            CutsceneIssue("MANIFEST_MEDIA", f"scene.src names a file not in the pack folder: {src!r}.")
        )
        return None, issues

    fit = raw_scene.get("fit", "cover")
    if fit not in FIT_MODES:
        issues.append(
            CutsceneIssue("MANIFEST_SCENE", f"scene.fit must be one of {list(FIT_MODES)}; got {fit!r}.")
        )
        fit = "cover"

    loop = raw_scene.get("loop", False)
    if not isinstance(loop, bool):
        issues.append(CutsceneIssue("MANIFEST_SCENE", f"scene.loop must be true or false; got {loop!r}."))
        loop = False

    scene: dict[str, Any] = {"type": scene_type, "src": src, "fit": fit}
    if scene_type == "video":
        scene["loop"] = loop
    return scene, issues


def validate_manifest(payload: Any, *, files: Any = frozenset()) -> ManifestValidation:
    """Validate one soccer pack manifest. Mirrors football's
    :func:`scoreboard.presentation.cutscenes.validate_manifest` exactly,
    scoped to :data:`SOCCER_CUTSCENE_EVENTS`.
    """

    if not isinstance(payload, dict):
        return ManifestValidation(
            False, _fallback_manifest(SOCCER_CUTSCENE_EVENTS[0]),
            (CutsceneIssue("MANIFEST_SCHEMA", "A pack manifest must be an object."),),
        )

    issues: list[CutsceneIssue] = []

    schema_version = payload.get("schema_version")
    if schema_version != SOCCER_MANIFEST_SCHEMA_VERSION:
        issues.append(
            CutsceneIssue(
                "MANIFEST_SCHEMA",
                f"schema_version must be {SOCCER_MANIFEST_SCHEMA_VERSION}; got {schema_version!r}.",
            )
        )

    raw_name = payload.get("name")
    name: str | None = None
    if not isinstance(raw_name, str) or not raw_name.strip() or len(raw_name.strip()) > 64:
        issues.append(CutsceneIssue("MANIFEST_NAME", f"name must be 1-64 characters; got {raw_name!r}."))
    else:
        name = raw_name.strip()

    raw_event = payload.get("event")
    event = raw_event if raw_event in SOCCER_CUTSCENE_EVENTS else None
    if event is None:
        issues.append(
            CutsceneIssue(
                "MANIFEST_EVENT",
                f"event must be one of {list(SOCCER_CUTSCENE_EVENTS)}; got {raw_event!r}.",
            )
        )
    event_for_defaults = event if event is not None else SOCCER_CUTSCENE_EVENTS[0]

    raw_duration = payload.get("duration_seconds")
    if raw_duration is None:
        duration_seconds = DEFAULT_DURATION_SECONDS[event_for_defaults]
    else:
        ok, number = _is_finite_number(raw_duration)
        if not ok:
            issues.append(
                CutsceneIssue("MANIFEST_DURATION", f"duration_seconds must be a number; got {raw_duration!r}.")
            )
            duration_seconds = DEFAULT_DURATION_SECONDS[event_for_defaults]
        elif number < MIN_DURATION_SECONDS or number > MAX_DURATION_SECONDS:
            clamped = min(max(number, MIN_DURATION_SECONDS), MAX_DURATION_SECONDS)
            issues.append(
                CutsceneIssue(
                    "DURATION_CLAMPED",
                    f"duration_seconds {number!r} was clamped to {clamped}.",
                    severity="warning",
                )
            )
            duration_seconds = clamped
        else:
            duration_seconds = number

    default_intro = EVENT_DEFAULT_INTRO[event_for_defaults]
    raw_intro = payload.get("intro")
    if raw_intro is None:
        intro = default_intro
    elif raw_intro in INTRO_IDS:
        intro = raw_intro
    else:
        issues.append(
            CutsceneIssue("MANIFEST_INTRO", f"intro must be one of {list(INTRO_IDS)}; got {raw_intro!r}.")
        )
        intro = default_intro

    scene, scene_issues = _validate_scene(payload.get("scene"), files)
    issues.extend(scene_issues)
    if scene is None:
        scene = {"type": "builtin", "id": BUILTIN_SCENE_IDS[event_for_defaults]}

    manifest = {
        "schema_version": SOCCER_MANIFEST_SCHEMA_VERSION,
        "name": name if name is not None else "Untitled",
        "event": event if event is not None else event_for_defaults,
        "duration_seconds": duration_seconds,
        "intro": intro,
        "scene": scene,
    }
    ok = not any(issue.severity == "error" for issue in issues)
    return ManifestValidation(ok, manifest, tuple(issues))


def _fallback_manifest(event: str) -> dict[str, Any]:
    return {
        "schema_version": SOCCER_MANIFEST_SCHEMA_VERSION,
        "name": "Untitled",
        "event": event,
        "duration_seconds": DEFAULT_DURATION_SECONDS[event],
        "intro": EVENT_DEFAULT_INTRO[event],
        "scene": {"type": "builtin", "id": BUILTIN_SCENE_IDS[event]},
    }


# --- Built-in packs -----------------------------------------------------


def builtin_pack_id(event: str) -> str:
    return f"{SOCCER_BUILTIN_PACK_PREFIX}{event}"


def builtin_pack(event: str) -> dict[str, Any]:
    """The code-authored pack for ``event`` -- ships with no files at all."""

    return {
        "id": builtin_pack_id(event),
        "name": f"Built-in {EVENT_LABELS[event].lower()}",
        "event": event,
        "builtin": True,
        "duration_seconds": DEFAULT_DURATION_SECONDS[event],
        "intro": EVENT_DEFAULT_INTRO[event],
        "scene": {"type": "builtin", "id": BUILTIN_SCENE_IDS[event]},
        "folder": None,
        "media_url": None,
    }


# --- The program (spec section 7) -------------------------------------


def _resolve_team_name(spectator_view: Mapping[str, Any], team: str) -> str:
    """The scoring team's name, straight from the live spectator view.

    Unlike football's fixed school identity, this is deliberately
    configurable text -- a visitor's goal must read as *their* name, not a
    silently-relabeled ``HOME``/``AWAY``. A missing or malformed view yields
    ``""`` rather than raising; the scene still plays, just without a name.
    """

    if not isinstance(spectator_view, Mapping):
        return ""
    teams = spectator_view.get("teams")
    if not isinstance(teams, Mapping):
        return ""
    side = teams.get(team)
    if not isinstance(side, Mapping):
        return ""
    name = side.get("name")
    return name if isinstance(name, str) else ""


def _resolve_team_primary(spectator_view: Mapping[str, Any], team: str, fallback: str) -> str:
    """The saved primary colour for ``team``, or ``fallback``.

    The live spectator view is expected to carry a saved team identity under
    ``teams.<side>.primary`` when one has been chosen (mirroring the shape
    of :mod:`scoreboard.infrastructure.teams`'s ``TeamPreset.primary``); a
    missing, malformed, or non-hex value falls back to the fixed navy/red
    pair rather than ever raising or leaving the theme incomplete.
    """

    if isinstance(spectator_view, Mapping):
        teams = spectator_view.get("teams")
        if isinstance(teams, Mapping):
            side = teams.get(team)
            if isinstance(side, Mapping):
                primary = side.get("primary")
                if isinstance(primary, str) and primary:
                    return primary
    return fallback


def _resolve_scene(event: str, pack: Mapping[str, Any]) -> dict[str, Any]:
    scene_spec = pack.get("scene")
    scene_spec = scene_spec if isinstance(scene_spec, Mapping) else {}
    scene_type = scene_spec.get("type")

    if scene_type == "builtin":
        return {"type": "builtin", "id": scene_spec.get("id", BUILTIN_SCENE_IDS.get(event))}

    if scene_type in ("video", "image"):
        scene: dict[str, Any] = {
            "type": scene_type,
            "src": pack.get("media_url"),
            "fit": scene_spec.get("fit", "cover"),
        }
        if scene_type == "video":
            scene["loop"] = bool(scene_spec.get("loop", False))
        scene["fallback"] = {"type": "builtin", "id": BUILTIN_SCENE_IDS.get(event)}
        return scene

    return {"type": "builtin", "id": BUILTIN_SCENE_IDS.get(event, SOCCER_CUTSCENE_EVENTS[0])}


def _apply_board_style(widgets: Any, board_widgets: Any) -> None:
    """Identical in behaviour to football's private helper of the same name
    (:mod:`scoreboard.presentation.cutscenes`); copied rather than imported
    since the football name is private (a leading underscore) and this
    module must not depend on football's internals staying stable.
    """

    if not isinstance(widgets, dict) or not isinstance(board_widgets, Mapping):
        return
    for widget_id, widget in widgets.items():
        if not isinstance(widget, dict):
            continue
        board_widget = board_widgets.get(widget_id)
        if not isinstance(board_widget, Mapping):
            continue
        copied = False
        for key in CUTSCENE_STYLE_KEYS:
            if key in board_widget:
                widget[key] = board_widget[key]
                copied = True
        if copied:
            widget["fit_text"] = True


def build_program(
    play_id: int,
    event: str,
    pack: Mapping[str, Any],
    spectator_view: Mapping[str, Any],
    layout: Mapping[str, Any],
    board_layout: Mapping[str, Any] | None = None,
    *,
    team: str,
) -> dict[str, Any]:
    """Build the one JSON document the spectator page needs to play a GOAL
    cutscene (spec section 7). Same shape as football's
    :func:`scoreboard.presentation.cutscenes.build_program` output --
    ``views/spectator/cutscene.js``'s player (and its soccer twin,
    ``views/soccer_spectator/cutscene.js``) reads the same keys either way.

    ``team`` is required and keyword-only: ``"home"`` or ``"away"``, the side
    that scored. Unlike football, there is no default -- a GOAL is never
    "nobody's" -- an unrecognised value falls back to ``"home"`` rather than
    raising, matching this codebase's "a trigger must never crash" rule.
    """

    resolved_team = team if team in ("home", "away") else "home"
    team_name = _resolve_team_name(spectator_view, resolved_team)

    duration_seconds = pack.get("duration_seconds", DEFAULT_DURATION_SECONDS.get(event, MIN_DURATION_SECONDS))
    intro_id = pack.get("intro", EVENT_DEFAULT_INTRO.get(event, "none"))

    program_layout: dict[str, Any] = copy.deepcopy(dict(layout)) if isinstance(layout, Mapping) else {}
    program_layout["name"] = "Cutscene"

    if isinstance(board_layout, Mapping):
        _apply_board_style(program_layout.get("widgets"), board_layout.get("widgets"))
        board_screens = board_layout.get("screens")
        program_screens = program_layout.get("screens")
        if isinstance(program_screens, dict) and isinstance(board_screens, Mapping):
            for screen_id, screen in program_screens.items():
                board_screen = board_screens.get(screen_id)
                if not isinstance(screen, dict) or not isinstance(board_screen, Mapping):
                    continue
                _apply_board_style(screen.get("widgets"), board_screen.get("widgets"))

    theme = dict(THEME)
    theme["home_primary"] = _resolve_team_primary(spectator_view, "home", FALLBACK_HOME_PRIMARY)
    theme["away_primary"] = _resolve_team_primary(spectator_view, "away", FALLBACK_AWAY_PRIMARY)

    return {
        "schema_version": SOCCER_MANIFEST_SCHEMA_VERSION,
        "play_id": play_id,
        "event": event,
        "label": EVENT_LABELS.get(event, event),
        "team": resolved_team,
        "pack_id": pack.get("id", builtin_pack_id(event)),
        "duration_ms": round(duration_seconds * 1000),
        "intro": {"id": intro_id, "duration_ms": INTRO_DURATION_MS.get(intro_id, 0)},
        "outro_ms": SOCCER_OUTRO_DURATION_MS,
        "stage": dict(STAGE),
        "layout": program_layout,
        "scene": _resolve_scene(event, pack),
        "theme": theme,
        "texts": {
            "headline": EVENT_HEADLINES.get(event, event.upper()),
            "subline": team_name.upper() if team_name else "",
            "team_name": team_name,
        },
    }


# --- Descriptors for the window ------------------------------------------


def event_descriptors() -> list[dict[str, Any]]:
    """One descriptor per event, in :data:`SOCCER_CUTSCENE_EVENTS` order."""

    return [
        {
            "id": event,
            "label": EVENT_LABELS[event],
            "headline": EVENT_HEADLINES[event],
            "default_duration_seconds": DEFAULT_DURATION_SECONDS[event],
            "builtin_pack_id": builtin_pack_id(event),
        }
        for event in SOCCER_CUTSCENE_EVENTS
    ]


__all__ = [
    "BUILTIN_SCENE_IDS",
    "CUTSCENE_STYLE_KEYS",
    "DEFAULT_DURATION_SECONDS",
    "EVENT_DEFAULT_INTRO",
    "EVENT_HEADLINES",
    "EVENT_LABELS",
    "FALLBACK_AWAY_PRIMARY",
    "FALLBACK_HOME_PRIMARY",
    "MAX_DURATION_SECONDS",
    "MIN_DURATION_SECONDS",
    "SOCCER_BUILTIN_PACK_PREFIX",
    "SOCCER_CUTSCENE_EVENTS",
    "SOCCER_MANIFEST_SCHEMA_VERSION",
    "SOCCER_OUTRO_DURATION_MS",
    "ManifestValidation",
    "build_program",
    "builtin_pack",
    "builtin_pack_id",
    "event_descriptors",
    "normalize_pack",
    "validate_manifest",
    # Reused (imported, not redefined) from football so soccer callers can
    # depend on this module alone.
    "BUILTIN_PACK_PREFIX",
    "FIT_MODES",
    "INTRO_DURATION_MS",
    "INTRO_IDS",
    "MANIFEST_SCHEMA_VERSION",
    "MEDIA_EXTENSIONS",
    "SCENE_TYPES",
    "STAGE",
    "THEME",
    "CutsceneIssue",
]
