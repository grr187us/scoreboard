"""Pure football-field calculations used by the Field Assistant.

This module intentionally knows nothing about clocks, revisions, persistence,
or windows.  It turns an already-read authoritative field context into one
complete proposed field result; the application layer decides whether and how
to commit that result atomically.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Final, Mapping

from .state import BallSpot


HOME: Final[str] = "home"
AWAY: Final[str] = "away"
TEAM_SIDES: Final[frozenset[str]] = frozenset((HOME, AWAY))
REGULATION_QUARTERS: Final[frozenset[str]] = frozenset(("1st", "2nd", "3rd", "4th"))
#: Quarters in which the assistant will calculate at all.  ``PRE`` is included
#: so the opening series or kickoff can be staged before the operator advances
#: the quarter -- at the start of a game the persisted quarter is still ``PRE``,
#: and refusing it there left the assistant unusable exactly when the operator
#: is setting the game up.  ``PRE`` is treated as "before the 1st quarter"
#: everywhere below: identical rules direction, identical drawing side.
ASSISTANT_QUARTERS: Final[frozenset[str]] = REGULATION_QUARTERS | frozenset(("PRE",))
#: Quarters whose drawing shows HOME attacking its first-quarter side.
FIRST_HALF_DRAWING_QUARTERS: Final[frozenset[str]] = frozenset(("PRE", "1st", "3rd"))
PENALTY_RESOLUTIONS: Final[frozenset[str]] = frozenset(
    ("repeat_down", "count_down", "automatic_first", "no_play", "decline")
)


class FieldAssistantValidationError(ValueError):
    """Raised when a proposed assistant calculation is not a supported path."""


def _require_team(value: str, field_name: str = "team") -> str:
    if value not in TEAM_SIDES:
        raise FieldAssistantValidationError(f"{field_name} must be 'home' or 'away'")
    return value


def _require_absolute(value: int, field_name: str = "absolute spot") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise FieldAssistantValidationError(f"{field_name} must be a whole yard from 0 through 100")
    return value


def _require_direction(value: int) -> int:
    if isinstance(value, bool) or value not in (-1, 1):
        raise FieldAssistantValidationError("first_quarter_home_direction must be -1 or +1")
    return value


def _require_assistant_quarter(quarter: str) -> str:
    if quarter not in ASSISTANT_QUARTERS:
        raise FieldAssistantValidationError(
            "Field Assistant is manual-only outside PRE and the four regulation "
            "quarters (HALF, OT, and FINAL are manual)"
        )
    return quarter


def _opponent(team: str) -> str:
    return AWAY if _require_team(team) == HOME else HOME


def absolute_from_ball_spot(ball_on: BallSpot) -> int:
    """Convert the persisted, team-relative spot to the private 0..100 scale."""

    if not isinstance(ball_on, BallSpot):
        raise FieldAssistantValidationError("ball_on must be a BallSpot")
    return ball_on.yard_line if ball_on.team == HOME else 100 - ball_on.yard_line


def ball_spot_from_absolute(absolute_spot: int) -> BallSpot:
    """Convert a 0..100 coordinate to the canonical persisted representation."""

    spot = _require_absolute(absolute_spot)
    # Midfield is deliberately always HOME 50, including input from legacy AWAY 50.
    return BallSpot(HOME, spot) if spot <= 50 else BallSpot(AWAY, 100 - spot)


def direction_for(first_quarter_home_direction: int, quarter: str, offense: str) -> int:
    """Return the offense's fixed rules direction on the label coordinate.

    The absolute coordinate is LABEL based: 0 is always the HOME goal line
    and 100 is always the AWAY goal line, no matter which physical/on-screen
    side either team is currently attacking. In that coordinate the actual
    football rule is that HOME always advances toward 100 and AWAY always
    advances toward 0 -- in every quarter. Teams switching ends at a quarter
    boundary only changes which side of the field drawing each goal line is
    presented on; it never changes this rules math. ``first_quarter_home_
    direction`` is accepted (and still validated) only because it is needed
    for presentation elsewhere (see ``home_goal_side``); it has no bearing on
    the value returned here. ``quarter`` is still required to be one of the
    assistant's quarters -- ``PRE`` or a regulation quarter -- so this stays
    manual-only in HALF, OT, and FINAL.
    """

    _require_direction(first_quarter_home_direction)
    _require_assistant_quarter(quarter)
    team = _require_team(offense, "offense")
    return 1 if team == HOME else -1


def home_goal_side(first_quarter_home_direction: int | None, quarter: str) -> str | None:
    """Return which on-screen side the HOME goal line is drawn on (presentation only).

    ``first_quarter_home_direction == +1`` means HOME attacks toward the
    RIGHT side of the field drawing in the 1st quarter, so the HOME goal line
    is drawn on the LEFT in the 1st and 3rd quarters and on the RIGHT in the
    2nd and 4th (teams switch ends at the start of each quarter). ``-1`` is
    the mirror image. This purely decides which side of the screen each goal
    line is drawn on; it never changes the rules direction from
    ``direction_for``. Returns ``None`` when ``first_quarter_home_direction``
    is ``None`` or ``quarter`` is not one of the assistant's quarters (HALF,
    OT, FINAL, and so on are manual-only here too). ``PRE`` draws the field
    the way the 1st quarter will, so the setup an operator stages before
    kickoff is the setup they keep once the quarter advances.
    """

    if first_quarter_home_direction is None or quarter not in ASSISTANT_QUARTERS:
        return None
    direction = _require_direction(first_quarter_home_direction)
    first_half = quarter in FIRST_HALF_DRAWING_QUARTERS
    if direction == 1:
        return "left" if first_half else "right"
    return "right" if first_half else "left"


@dataclass(frozen=True, slots=True)
class SeriesState:
    """Small assistant-only state needed to continue an active possession."""

    first_quarter_home_direction: int | None
    line_to_gain: int | None

    def __post_init__(self) -> None:
        if self.first_quarter_home_direction is not None:
            object.__setattr__(
                self, "first_quarter_home_direction", _require_direction(self.first_quarter_home_direction)
            )
        if self.line_to_gain is not None:
            object.__setattr__(self, "line_to_gain", _require_absolute(self.line_to_gain, "line_to_gain"))
        if self.line_to_gain is not None and self.first_quarter_home_direction is None:
            raise FieldAssistantValidationError("line_to_gain requires a first-quarter direction")


@dataclass(frozen=True, slots=True)
class FieldAssistantContext:
    """Authoritative football values read before calculating a draft.

    ``series`` is absent only while starting/re-syncing an ordinary series.
    It deliberately contains no clock or revision field.
    """

    quarter: str
    possession: str | None
    ball_on: BallSpot
    down: int | None
    distance: int | None
    series: SeriesState | None

    def __post_init__(self) -> None:
        if self.quarter not in ASSISTANT_QUARTERS | {"OT"}:
            raise FieldAssistantValidationError("quarter must be PRE, a regulation quarter, or OT")
        if self.possession is not None:
            _require_team(self.possession, "possession")
        if not isinstance(self.ball_on, BallSpot):
            raise FieldAssistantValidationError("ball_on must be a BallSpot")
        if self.down is not None and (isinstance(self.down, bool) or self.down not in (1, 2, 3, 4)):
            raise FieldAssistantValidationError("down must be 1 through 4 or null")
        if self.distance is not None and (
            isinstance(self.distance, bool) or not isinstance(self.distance, int) or self.distance < 0
        ):
            raise FieldAssistantValidationError("distance must be a non-negative whole number or null")
        if self.series is not None and not isinstance(self.series, SeriesState):
            raise FieldAssistantValidationError("series must be a SeriesState or null")


@dataclass(frozen=True, slots=True)
class FieldResult:
    """One complete proposed atomic field/score result.

    ``ball_on=None`` means the transition clears ordinary field status.  The
    state-command adapter owns the legacy state's inert display value in that
    case; it must not treat ``None`` as a goal-line spot.
    """

    ball_on: BallSpot | None
    possession: str | None
    down: int | None
    distance: int | None
    series: SeriesState | None
    score_delta_home: int = 0
    score_delta_away: int = 0
    classification: str = ""
    summary: str = ""
    follow_up: str = ""
    requires_explicit_turnover: bool = False

    def __post_init__(self) -> None:
        if self.ball_on is not None and not isinstance(self.ball_on, BallSpot):
            raise FieldAssistantValidationError("result ball_on must be a BallSpot or null")
        if self.possession is not None:
            _require_team(self.possession, "result possession")
        if self.down is not None and (isinstance(self.down, bool) or self.down not in (1, 2, 3, 4)):
            raise FieldAssistantValidationError("result down must be 1 through 4 or null")
        if self.distance is not None and (
            isinstance(self.distance, bool) or not isinstance(self.distance, int) or self.distance < 0
        ):
            raise FieldAssistantValidationError("result distance must be a non-negative whole number or null")
        if self.series is not None and not isinstance(self.series, SeriesState):
            raise FieldAssistantValidationError("result series must be a SeriesState or null")
        for name, value in (("score_delta_home", self.score_delta_home), ("score_delta_away", self.score_delta_away)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FieldAssistantValidationError(f"{name} must be a non-negative whole number")
        if not isinstance(self.requires_explicit_turnover, bool):
            raise FieldAssistantValidationError("requires_explicit_turnover must be boolean")


@dataclass(frozen=True, slots=True)
class FieldAction:
    """JSON-friendly request envelope used by bridge and command adapters.

    Supported ``kind``/payload pairs are ``start_series`` (``offense``,
    ``ball_absolute``), ``normal_play`` (``final_absolute``),
    ``incomplete_pass`` (none), ``penalty`` (``enforced_absolute``,
    ``resolution``; a decline also needs ``underlying_action``), ``turnover``
    (``new_offense``, ``final_absolute``), ``touchdown`` (``scoring_team``,
    optional ``add_score``), ``try`` (``scoring_team``, ``points``),
    ``field_goal``/``safety`` (``scoring_team``, optional ``add_score``),
    ``kickoff`` (``receiving_team``, ``final_absolute``), and ``manual``
    (``possession``, ``down``, ``distance``, ``ball_absolute``) -- the
    in-assistant manual escape hatch for stating field status directly.  An
    ``underlying_action`` is another mapping with ``kind`` and ``payload``.
    """

    kind: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind:
            raise FieldAssistantValidationError("field action kind must be a non-empty string")
        if not isinstance(self.payload, Mapping):
            raise FieldAssistantValidationError("field action payload must be a mapping")


def _require_active_series(context: FieldAssistantContext) -> tuple[str, int, int, SeriesState]:
    _require_assistant_quarter(context.quarter)
    if (context.possession is None or context.down is None or context.distance is None
            or context.series is None or context.series.line_to_gain is None
            or context.series.first_quarter_home_direction is None):
        raise FieldAssistantValidationError("an active series requires possession, down, distance, and series state")
    return context.possession, context.down, absolute_from_ball_spot(context.ball_on), context.series


def _line_to_gain(spot: int, direction: int) -> int:
    return min(100, spot + 10) if direction == 1 else max(0, spot - 10)


def _distance(spot: int, line_to_gain: int, direction: int) -> int:
    # The state/display convention reserves zero for goal-to-go.  It remains
    # zero after a loss even if the physical yards back to that goal line grow.
    if line_to_gain == (100 if direction == 1 else 0):
        return 0
    return max(0, (line_to_gain - spot) * direction)


def _result_for_series(
    *, spot: int, offense: str, down: int, series: SeriesState, quarter: str,
    classification: str, summary: str, follow_up: str = "",
) -> FieldResult:
    # _require_active_series and all constructors of a live result ensure both
    # optional setup values are present before this helper is reached.
    assert series.first_quarter_home_direction is not None
    assert series.line_to_gain is not None
    direction = direction_for(series.first_quarter_home_direction, quarter, offense)
    return FieldResult(
        ball_on=ball_spot_from_absolute(spot), possession=offense, down=down,
        distance=_distance(spot, series.line_to_gain, direction), series=series,
        classification=classification, summary=summary, follow_up=follow_up,
    )


def start_series(context: FieldAssistantContext, offense: str, ball_absolute: int) -> FieldResult:
    """Start a first-and-ten (or goal-to-go) series at the confirmed final spot."""

    _require_assistant_quarter(context.quarter)
    team = _require_team(offense, "offense")
    spot = _require_absolute(ball_absolute)
    if spot in (0, 100):
        raise FieldAssistantValidationError("a series cannot start on a goal line; use an explicit transition")
    if context.series is None or context.series.first_quarter_home_direction is None:
        raise FieldAssistantValidationError("first-quarter direction must be established before starting a series")
    direction = direction_for(context.series.first_quarter_home_direction, context.quarter, team)
    series = SeriesState(context.series.first_quarter_home_direction, _line_to_gain(spot, direction))
    result = _result_for_series(
        spot=spot, offense=team, down=1, series=series, quarter=context.quarter,
        classification="start_series", summary="Start 1st & Goal" if _distance(spot, series.line_to_gain, direction) == 0 else "Start 1st & 10",
    )
    return result


def preview_normal_play(context: FieldAssistantContext, final_absolute: int) -> FieldResult:
    """Calculate a completed ordinary scrimmage play without committing it."""

    offense, down, _old_spot, series = _require_active_series(context)
    final_spot = _require_absolute(final_absolute, "final spot")
    if final_spot in (0, 100):
        raise FieldAssistantValidationError("an ordinary scrimmage play at a goal line requires an explicit transition")
    assert series.first_quarter_home_direction is not None
    assert series.line_to_gain is not None
    direction = direction_for(series.first_quarter_home_direction, context.quarter, offense)
    reached_line = (final_spot - series.line_to_gain) * direction >= 0
    if reached_line:
        next_series = SeriesState(series.first_quarter_home_direction, _line_to_gain(final_spot, direction))
        return _result_for_series(
            spot=final_spot, offense=offense, down=1, series=next_series, quarter=context.quarter,
            classification="first_down", summary="First down" if _distance(final_spot, next_series.line_to_gain, direction) else "First and Goal",
        )
    return _advance_down(context, final_spot, "normal_play")


def _advance_down(context: FieldAssistantContext, final_spot: int, classification: str) -> FieldResult:
    offense, down, _old_spot, series = _require_active_series(context)
    if down == 4:
        return FieldResult(
            ball_on=ball_spot_from_absolute(final_spot), possession=offense, down=4,
            distance=_distance(final_spot, series.line_to_gain, direction_for(series.first_quarter_home_direction, context.quarter, offense)),
            series=series, classification="turnover_on_downs_proposed",
            summary="Turnover on downs proposed", follow_up="Confirm the new offense and final spot explicitly.",
            requires_explicit_turnover=True,
        )
    return _result_for_series(
        spot=final_spot, offense=offense, down=down + 1, series=series, quarter=context.quarter,
        classification=classification, summary=f"{down + 1}{'th' if down + 1 == 4 else 'nd' if down + 1 == 2 else 'rd'} down",
    )


def preview_incomplete_pass(context: FieldAssistantContext) -> FieldResult:
    """Advance the down while retaining the authoritative ball and line to gain."""

    _offense, _down, spot, _series = _require_active_series(context)
    return _advance_down(context, spot, "incomplete_pass")


def penalty_enforcement_spot(context: FieldAssistantContext, offense_relative_yards: int) -> tuple[int, str]:
    """Apply one approved ±5/10/15 enforcement shortcut, clamped to the field.

    Positive yards benefit the offense; negative yards benefit the defense.
    """

    offense, _down, spot, series = _require_active_series(context)
    if offense_relative_yards not in (-15, -10, -5, 5, 10, 15):
        raise FieldAssistantValidationError("penalty yardage must be one of -15, -10, -5, 5, 10, or 15")
    assert series.first_quarter_home_direction is not None
    direction = direction_for(series.first_quarter_home_direction, context.quarter, offense)
    result = min(100, max(0, spot + direction * offense_relative_yards))
    benefit = "benefits offense" if offense_relative_yards > 0 else "benefits defense"
    return result, f"{abs(offense_relative_yards)} yards, {benefit}"


def apply_penalty(
    context: FieldAssistantContext, enforced_absolute: int, resolution: str, *, underlying_result: FieldResult | None = None
) -> FieldResult:
    """Calculate an explicitly selected penalty consequence.

    For ``decline``, ``underlying_result`` is required and returned unchanged:
    declining discards the adjustment rather than reconstructing a play.
    """

    offense, down, _spot, series = _require_active_series(context)
    enforced_spot = _require_absolute(enforced_absolute, "enforcement spot")
    if resolution not in PENALTY_RESOLUTIONS:
        raise FieldAssistantValidationError("unsupported penalty resolution")
    if resolution == "decline":
        if underlying_result is None:
            raise FieldAssistantValidationError("a declined penalty requires the underlying proposed play result")
        return underlying_result
    if enforced_spot in (0, 100):
        raise FieldAssistantValidationError("a penalty enforcement spot at a goal line requires manual handling")
    if resolution in ("repeat_down", "no_play"):
        return _result_for_series(
            spot=enforced_spot, offense=offense, down=down, series=series, quarter=context.quarter,
            classification=resolution,
            summary="Penalty: repeat down" if resolution == "repeat_down" else "Penalty: no play; down replayed",
        )
    if resolution == "count_down":
        return _advance_down(context, enforced_spot, "penalty_count_down")
    direction = direction_for(series.first_quarter_home_direction, context.quarter, offense)
    next_series = SeriesState(series.first_quarter_home_direction, _line_to_gain(enforced_spot, direction))
    return _result_for_series(
        spot=enforced_spot, offense=offense, down=1, series=next_series, quarter=context.quarter,
        classification="penalty_automatic_first", summary="Penalty: automatic first down",
    )


def preview_turnover(context: FieldAssistantContext, new_offense: str, final_absolute: int) -> FieldResult:
    """Explicitly establish a new first-down series after a turnover on downs."""

    _require_active_series(context)
    team = _require_team(new_offense, "new_offense")
    if context.possession == team:
        raise FieldAssistantValidationError("turnover new_offense must differ from the current offense")
    result = start_series(context, team, final_absolute)
    return replace(
        result,
        classification="turnover",
        summary=f"Turnover: {result.summary}",
        follow_up="New offense and final spot confirmed.",
    )


def _scoring_result(team: str, points: int, classification: str, follow_up: str) -> FieldResult:
    scorer = _require_team(team, "scoring_team")
    if isinstance(points, bool) or not isinstance(points, int) or points < 0:
        raise FieldAssistantValidationError("points must be a non-negative whole number")
    return FieldResult(
        ball_on=None, possession=None, down=None, distance=None, series=None,
        score_delta_home=points if scorer == HOME else 0,
        score_delta_away=points if scorer == AWAY else 0,
        classification=classification, summary=f"{classification.replace('_', ' ').title()}: +{points}", follow_up=follow_up,
    )


def preview_touchdown(scoring_team: str, *, add_score: bool = True) -> FieldResult:
    if not isinstance(add_score, bool):
        raise FieldAssistantValidationError("add_score must be boolean")
    return _scoring_result(scoring_team, 6 if add_score else 0, "touchdown", "Set up the try/PAT.")


def preview_try(scoring_team: str, points: int) -> FieldResult:
    if isinstance(points, bool) or points not in (0, 1, 2):
        raise FieldAssistantValidationError("try points must be 0, 1, or 2")
    return _scoring_result(scoring_team, points, "try", "Set up the kickoff.")


def preview_field_goal(scoring_team: str, *, add_score: bool = True) -> FieldResult:
    if not isinstance(add_score, bool):
        raise FieldAssistantValidationError("add_score must be boolean")
    return _scoring_result(scoring_team, 3 if add_score else 0, "field_goal", "Set up the kickoff.")


def preview_safety(scoring_team: str, *, add_score: bool = True) -> FieldResult:
    if not isinstance(add_score, bool):
        raise FieldAssistantValidationError("add_score must be boolean")
    return _scoring_result(scoring_team, 2 if add_score else 0, "safety", "Set up the free kick explicitly.")


def preview_kickoff(context: FieldAssistantContext, receiving_team: str, final_absolute: int) -> FieldResult:
    """Start the receiving team's series at its confirmed return/touchback spot."""

    result = start_series(context, _require_team(receiving_team, "receiving_team"), final_absolute)
    return replace(
        result,
        classification="kickoff",
        summary=f"Kickoff: {result.summary}",
        follow_up="Receiving team's series is ready.",
    )


def preview_manual(
    context: FieldAssistantContext, possession: str, down: int, distance: int, ball_absolute: int
) -> FieldResult:
    """Commit an operator-stated field status directly, as one atomic command.

    This is the in-assistant manual escape hatch sections 2 and 7 reserve for
    unusual special-teams outcomes the other transitions do not model: the
    operator states the football facts -- offense, down, distance, and the
    clicked spot -- and Python still validates and derives everything else.
    Only the line to gain is calculated here; it is never accepted from the
    payload.
    """

    _require_assistant_quarter(context.quarter)
    team = _require_team(possession, "possession")
    if isinstance(down, bool) or not isinstance(down, int) or down not in (1, 2, 3, 4):
        raise FieldAssistantValidationError("down must be 1 through 4")
    if isinstance(distance, bool) or not isinstance(distance, int) or not 0 <= distance <= 99:
        raise FieldAssistantValidationError("distance must be a whole number from 0 through 99")
    spot = _require_absolute(ball_absolute)
    if spot in (0, 100):
        raise FieldAssistantValidationError("a live series cannot sit on a goal line; use a transition")
    if context.series is None or context.series.first_quarter_home_direction is None:
        raise FieldAssistantValidationError("first-quarter direction must be established before starting a series")
    direction = direction_for(context.series.first_quarter_home_direction, context.quarter, team)
    goal_line = 100 if direction == 1 else 0
    if distance == 0:
        line_to_gain = goal_line
        stored_distance = 0
    else:
        raw_line = spot + direction * distance
        line_to_gain = min(100, max(0, raw_line))
        # A requested distance that would overrun the goal line is clamped to
        # it; the persisted distance then becomes the true yards remaining so
        # down/distance/line-to-gain always agree with each other.
        stored_distance = abs(goal_line - spot) if line_to_gain != raw_line else distance
    series = SeriesState(context.series.first_quarter_home_direction, line_to_gain)
    ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}[down]
    label = "Goal" if stored_distance == 0 else str(stored_distance)
    return FieldResult(
        ball_on=ball_spot_from_absolute(spot), possession=team, down=down,
        distance=stored_distance, series=series, classification="manual",
        summary=f"Set {team.upper()} {ordinal} & {label}",
    )


def _payload_value(payload: Mapping[str, Any], name: str) -> Any:
    if name not in payload:
        raise FieldAssistantValidationError(f"field action payload requires {name!r}")
    return payload[name]


def calculate_field_action(context: FieldAssistantContext, action: FieldAction) -> FieldResult:
    """Dispatch a bridge-neutral action envelope to a pure proposed result."""

    if not isinstance(context, FieldAssistantContext):
        raise FieldAssistantValidationError("context must be a FieldAssistantContext")
    if not isinstance(action, FieldAction):
        raise FieldAssistantValidationError("action must be a FieldAction")
    payload = action.payload
    if action.kind == "start_series":
        return start_series(context, _payload_value(payload, "offense"), _payload_value(payload, "ball_absolute"))
    if action.kind == "normal_play":
        return preview_normal_play(context, _payload_value(payload, "final_absolute"))
    if action.kind == "incomplete_pass":
        return preview_incomplete_pass(context)
    if action.kind == "turnover":
        return preview_turnover(context, _payload_value(payload, "new_offense"), _payload_value(payload, "final_absolute"))
    if action.kind == "touchdown":
        return preview_touchdown(_payload_value(payload, "scoring_team"), add_score=payload.get("add_score", True))
    if action.kind == "try":
        return preview_try(_payload_value(payload, "scoring_team"), _payload_value(payload, "points"))
    if action.kind == "field_goal":
        return preview_field_goal(_payload_value(payload, "scoring_team"), add_score=payload.get("add_score", True))
    if action.kind == "safety":
        return preview_safety(_payload_value(payload, "scoring_team"), add_score=payload.get("add_score", True))
    if action.kind == "kickoff":
        return preview_kickoff(context, _payload_value(payload, "receiving_team"), _payload_value(payload, "final_absolute"))
    if action.kind == "manual":
        return preview_manual(
            context, _payload_value(payload, "possession"), _payload_value(payload, "down"),
            _payload_value(payload, "distance"), _payload_value(payload, "ball_absolute"),
        )
    if action.kind == "penalty":
        resolution = _payload_value(payload, "resolution")
        underlying: FieldResult | None = None
        if resolution == "decline":
            raw = _payload_value(payload, "underlying_action")
            if not isinstance(raw, Mapping):
                raise FieldAssistantValidationError("underlying_action must be a mapping")
            underlying = calculate_field_action(
                context, FieldAction(raw.get("kind"), raw.get("payload", {}))
            )
        return apply_penalty(
            context, _payload_value(payload, "enforced_absolute"), resolution, underlying_result=underlying
        )
    raise FieldAssistantValidationError(f"unsupported field action kind: {action.kind!r}")


__all__ = [
    "ASSISTANT_QUARTERS", "AWAY", "FIRST_HALF_DRAWING_QUARTERS", "HOME", "PENALTY_RESOLUTIONS",
    "REGULATION_QUARTERS", "FieldAction", "FieldAssistantContext",
    "FieldAssistantValidationError", "FieldResult", "SeriesState", "absolute_from_ball_spot",
    "apply_penalty", "ball_spot_from_absolute", "calculate_field_action", "direction_for", "home_goal_side",
    "penalty_enforcement_spot",
    "preview_field_goal", "preview_incomplete_pass", "preview_kickoff", "preview_manual", "preview_normal_play",
    "preview_safety", "preview_touchdown", "preview_try", "preview_turnover", "start_series",
]
