"""Cutscenes: the event registry, pack-manifest validation, and the program.

A cutscene is a host concern, exactly like the presentation layout (see
``presentation/layout.py``'s docstring for why that split exists): this
module never touches disk, a clock, or a window. It defines what a cutscene
*is* -- which events exist, what a pack manifest may say, and what a
complete "program" document looks like -- so that :mod:`scoreboard.
infrastructure.cutscene_packs` (I/O) and :mod:`scoreboard.host.cutscenes`
(playback state, timers) can both be built on top of something that never
raises and never needs a temporary directory to test.

**Why a program rather than letting the page read a pack directly**: the
spectator page must not need to know how a cutscene is configured -- one
JSON document, built once per trigger by :func:`build_program`, tells it
everything: how long to play, where the stage sits, what the temporary
"morph" layout looks like, and what text and colours to show. Python owns
every value; JavaScript only copies it onto the screen (the house rule this
spec inherits from the layout-editor and presentation-screens specs).

**Why manifests are validated the same way a layout is** (strict, with a
plain-language fallback): a pack folder is something an operator or a
volunteer drops files into by hand, so a manifest with a typo must not be
able to crash a trigger -- :func:`validate_manifest` always returns a usable,
normalized manifest, and a hard problem (an unknown event, a media file that
is not actually in the folder) is reported as an error that causes the
*whole pack* to be skipped rather than an exception thrown mid-broadcast.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Collection, Final, Mapping

# --- Constants (spec section 2.1; exact names and values -- other agents
# hard-code them) -------------------------------------------------------------

CUTSCENE_EVENTS: Final[tuple[str, ...]] = ("first_down", "touchdown")
EVENT_LABELS = {"first_down": "First down", "touchdown": "Touchdown"}
EVENT_HEADLINES = {"first_down": "FIRST DOWN", "touchdown": "TOUCHDOWN"}
#: Which side a cutscene is "for" when the operator does not say: a first
#: down belongs to the side with possession; a touchdown defaults to home.
EVENT_DEFAULT_TEAM = {"first_down": "possession", "touchdown": "home"}
DEFAULT_DURATION_SECONDS = {"first_down": 7.0, "touchdown": 10.0}
MIN_DURATION_SECONDS: Final[float] = 2.0
MAX_DURATION_SECONDS: Final[float] = 30.0
INTRO_IDS: Final[tuple[str, ...]] = ("claw_scratch", "none")
INTRO_DURATION_MS = {"claw_scratch": 1400, "none": 0}
#: Milliseconds the outro (fade + restore) takes; the program carries it so
#: the page and the host agree on when the board is back.
OUTRO_DURATION_MS: Final[int] = 600
BUILTIN_SCENE_IDS = {"first_down": "first_down", "touchdown": "touchdown"}
SCENE_TYPES: Final[tuple[str, ...]] = ("builtin", "video", "image")
MEDIA_EXTENSIONS = {
    "video": (".webm", ".mp4"),
    "image": (".png", ".gif", ".jpg", ".jpeg", ".webp", ".apng"),
}
FIT_MODES: Final[tuple[str, ...]] = ("cover", "contain")
#: The stage: the part of the 16:9 canvas above the Broadcast bar's status
#: row (`quarter` etc. start at y 0.705 in the preset).
STAGE = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.70}
#: From brand-baseline/palette.json.
THEME = {
    "navy": "#071B3A", "navy_elevated": "#0D2B5A", "blue": "#17468C",
    "red": "#C8242B", "blue_light": "#2C62AB", "white": "#FFFFFF",
    "mist": "#DDE7F4", "ink": "#030711", "gold": "#FFB703",
}
MANIFEST_SCHEMA_VERSION: Final[int] = 1
TEAM_SIDES: Final[tuple[str, ...]] = ("home", "away")

BUILTIN_PACK_PREFIX: Final[str] = "builtin:"


# --- Small numeric helper (mirrors presentation/layout.py's) ----------------


def _is_finite_number(value: Any) -> tuple[bool, float]:
    """``bool`` is never accepted where a number is expected."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, 0.0
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return False, 0.0
    return True, number


# --- Issues and results ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CutsceneIssue:
    """One problem found while validating a pack manifest, or a repair made
    to it. ``severity`` is ``"error"`` (the pack is unusable as a whole) or
    ``"warning"`` (a value was adjusted but the pack is still usable).
    """

    code: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


@dataclass(frozen=True, slots=True)
class ManifestValidation:
    """The result of validating one pack manifest.

    ``manifest`` is always a complete, normalized manifest -- every optional
    field filled with its default -- even when ``ok`` is ``False``, the same
    "never hand back nothing usable" trade :mod:`presentation.layout` makes
    for a widget. A caller that skips unusable packs (see
    :mod:`scoreboard.infrastructure.cutscene_packs`) is expected to check
    ``ok`` before trusting ``manifest``.
    """

    ok: bool
    manifest: dict[str, Any]
    issues: tuple[CutsceneIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "manifest": self.manifest,
            "issues": [issue.to_dict() for issue in self.issues],
        }


# --- Manifest validation (spec section 2.2) ---------------------------------


def _validate_scene(raw_scene: Any, files: Collection[str]) -> tuple[dict[str, Any] | None, list[CutsceneIssue]]:
    """Validate the ``scene`` block of a manifest. ``None`` means unusable."""

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

    # scene_type is "video" or "image" from here on.
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


def validate_manifest(payload: Any, *, files: Collection[str]) -> ManifestValidation:
    """Validate one pack manifest (spec section 2.2).

    ``files`` is the set of filenames present in the pack folder -- this
    function never touches disk itself, so a caller (the scanner, or a unit
    test) decides what "the folder" contains.
    """

    if not isinstance(payload, dict):
        return ManifestValidation(
            False, _fallback_manifest(CUTSCENE_EVENTS[0]),
            (CutsceneIssue("MANIFEST_SCHEMA", "A pack manifest must be an object."),),
        )

    issues: list[CutsceneIssue] = []

    schema_version = payload.get("schema_version")
    if schema_version != MANIFEST_SCHEMA_VERSION:
        issues.append(
            CutsceneIssue(
                "MANIFEST_SCHEMA",
                f"schema_version must be {MANIFEST_SCHEMA_VERSION}; got {schema_version!r}.",
            )
        )

    raw_name = payload.get("name")
    name: str | None = None
    if not isinstance(raw_name, str) or not raw_name.strip() or len(raw_name.strip()) > 64:
        issues.append(CutsceneIssue("MANIFEST_NAME", f"name must be 1-64 characters; got {raw_name!r}."))
    else:
        name = raw_name.strip()

    raw_event = payload.get("event")
    event = raw_event if raw_event in CUTSCENE_EVENTS else None
    if event is None:
        issues.append(
            CutsceneIssue("MANIFEST_EVENT", f"event must be one of {list(CUTSCENE_EVENTS)}; got {raw_event!r}.")
        )
    # Every field below that depends on "which event" falls back to a
    # deterministic default event rather than raising when the event itself
    # was rejected -- the whole manifest is unusable either way (ok is
    # False), but a normalized document must still exist.
    event_for_defaults = event if event is not None else CUTSCENE_EVENTS[0]

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

    raw_intro = payload.get("intro")
    if raw_intro is None:
        intro = "claw_scratch"
    elif raw_intro in INTRO_IDS:
        intro = raw_intro
    else:
        issues.append(
            CutsceneIssue("MANIFEST_INTRO", f"intro must be one of {list(INTRO_IDS)}; got {raw_intro!r}.")
        )
        intro = "claw_scratch"

    scene, scene_issues = _validate_scene(payload.get("scene"), files)
    issues.extend(scene_issues)
    if scene is None:
        scene = {"type": "builtin", "id": BUILTIN_SCENE_IDS[event_for_defaults]}

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "name": name if name is not None else "Untitled",
        "event": event if event is not None else event_for_defaults,
        "duration_seconds": duration_seconds,
        "intro": intro,
        "scene": scene,
    }
    ok = not any(issue.severity == "error" for issue in issues)
    return ManifestValidation(ok, manifest, tuple(issues))


def _fallback_manifest(event: str) -> dict[str, Any]:
    """The normalized manifest used when the payload was not even an object."""

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "name": "Untitled",
        "event": event,
        "duration_seconds": DEFAULT_DURATION_SECONDS[event],
        "intro": "claw_scratch",
        "scene": {"type": "builtin", "id": BUILTIN_SCENE_IDS[event]},
    }


# --- Built-in packs (spec section 2.3) --------------------------------------


def builtin_pack_id(event: str) -> str:
    return f"{BUILTIN_PACK_PREFIX}{event}"


def builtin_pack(event: str) -> dict[str, Any]:
    """The code-authored pack for ``event`` -- ships with no files at all."""

    return {
        "id": builtin_pack_id(event),
        "name": f"Built-in {EVENT_LABELS[event].lower()}",
        "event": event,
        "builtin": True,
        "duration_seconds": DEFAULT_DURATION_SECONDS[event],
        "intro": "claw_scratch",
        "scene": {"type": "builtin", "id": BUILTIN_SCENE_IDS[event]},
        "folder": None,
        "media_url": None,
    }


def normalize_pack(
    pack_id: str, manifest: Mapping[str, Any], *, folder: str, media_url: str | None
) -> dict[str, Any]:
    """A scanned pack's dict shape (spec section 2.3): the manifest's fields,
    plus the folder identity infrastructure resolved. ``manifest`` is assumed
    already normalized by :func:`validate_manifest`.
    """

    return {
        "id": pack_id,
        "name": manifest.get("name"),
        "event": manifest.get("event"),
        "builtin": False,
        "duration_seconds": manifest.get("duration_seconds"),
        "intro": manifest.get("intro"),
        "scene": manifest.get("scene"),
        "folder": folder,
        "media_url": media_url,
    }


# --- The program (spec section 2.4) -----------------------------------------


def _resolve_team(event: str, team: str | None, spectator_view: Mapping[str, Any]) -> str:
    if team in TEAM_SIDES:
        return team  # type: ignore[return-value]

    default = EVENT_DEFAULT_TEAM.get(event, "home")
    if default != "possession":
        return default

    football = spectator_view.get("football") if isinstance(spectator_view, Mapping) else None
    possession = football.get("possession") if isinstance(football, Mapping) else None
    return possession if possession in TEAM_SIDES else "home"


def _resolve_team_text(spectator_view: Mapping[str, Any], team: str) -> tuple[str, Any]:
    teams = spectator_view.get("teams") if isinstance(spectator_view, Mapping) else None
    block = teams.get(team) if isinstance(teams, Mapping) else None
    name = block.get("name") if isinstance(block, Mapping) else None
    score = block.get("score") if isinstance(block, Mapping) else None
    if not isinstance(name, str):
        name = ""
    if score is None:
        score = 0
    return name, score


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

    # An unrecognized/absent scene type on an already-resolved pack should not
    # be reachable (every pack in the library came through validate_manifest
    # or builtin_pack), but a program must never fail to build over it.
    return {"type": "builtin", "id": BUILTIN_SCENE_IDS.get(event, CUTSCENE_EVENTS[0])}


def build_program(
    *,
    play_id: int,
    event: str,
    pack: Mapping[str, Any],
    team: str | None,
    spectator_view: Mapping[str, Any],
    layout: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the one JSON document that tells the spectator page everything
    it needs to play one cutscene (spec section 2.4).
    """

    resolved_team = _resolve_team(event, team, spectator_view)
    team_name, score = _resolve_team_text(spectator_view, resolved_team)

    duration_seconds = pack.get("duration_seconds", DEFAULT_DURATION_SECONDS.get(event, MIN_DURATION_SECONDS))
    intro_id = pack.get("intro", "claw_scratch")

    program_layout: dict[str, Any] = copy.deepcopy(dict(layout)) if isinstance(layout, Mapping) else {}
    program_layout["name"] = "Cutscene"

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "play_id": play_id,
        "event": event,
        "label": EVENT_LABELS.get(event, event),
        "team": resolved_team,
        "pack_id": pack.get("id", builtin_pack_id(event)),
        "duration_ms": round(duration_seconds * 1000),
        "intro": {"id": intro_id, "duration_ms": INTRO_DURATION_MS.get(intro_id, 0)},
        "outro_ms": OUTRO_DURATION_MS,
        "stage": dict(STAGE),
        "layout": program_layout,
        "scene": _resolve_scene(event, pack),
        "theme": dict(THEME),
        "texts": {
            "headline": EVENT_HEADLINES.get(event, event.upper()),
            "subline": team_name.upper(),
            "team_name": team_name,
            "score": str(score),
        },
    }


# --- Descriptors for the window (spec section 2.5) --------------------------


def event_descriptors() -> list[dict[str, Any]]:
    """One descriptor per event, in :data:`CUTSCENE_EVENTS` order."""

    return [
        {
            "id": event,
            "label": EVENT_LABELS[event],
            "headline": EVENT_HEADLINES[event],
            "default_team": EVENT_DEFAULT_TEAM[event],
            "default_duration_seconds": DEFAULT_DURATION_SECONDS[event],
            "builtin_pack_id": builtin_pack_id(event),
        }
        for event in CUTSCENE_EVENTS
    ]


__all__ = [
    "BUILTIN_PACK_PREFIX",
    "BUILTIN_SCENE_IDS",
    "CUTSCENE_EVENTS",
    "DEFAULT_DURATION_SECONDS",
    "EVENT_DEFAULT_TEAM",
    "EVENT_HEADLINES",
    "EVENT_LABELS",
    "FIT_MODES",
    "INTRO_DURATION_MS",
    "INTRO_IDS",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_DURATION_SECONDS",
    "MEDIA_EXTENSIONS",
    "MIN_DURATION_SECONDS",
    "OUTRO_DURATION_MS",
    "SCENE_TYPES",
    "STAGE",
    "TEAM_SIDES",
    "THEME",
    "CutsceneIssue",
    "ManifestValidation",
    "build_program",
    "builtin_pack",
    "builtin_pack_id",
    "event_descriptors",
    "normalize_pack",
    "validate_manifest",
]
