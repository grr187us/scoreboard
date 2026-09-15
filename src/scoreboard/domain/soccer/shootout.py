"""Pure kicks-from-the-mark rules (spec section 3.2, domain_draft.md section 3).

No state, no rules object beyond the plain ``initial_kickers`` count. Rounds are one kick per
side, alternating from ``first_kicker``; after ``initial_kickers`` a side, the shootout is
decided as soon as mathematically settled (also earlier within the first five); beyond that,
sudden death is decided the moment one side leads after both have kicked in a round.
"""

from __future__ import annotations

from scoreboard.domain.soccer.state import ShootoutKick

_OTHER: dict[str, str] = {"home": "away", "away": "home"}


def _round_of(index: int, initial_kickers: int) -> int:
    """1-based round number for the ``index``-th kick taken by one side."""

    return index + 1


def _by_team(kicks: tuple[ShootoutKick, ...], team: str) -> list[ShootoutKick]:
    return [k for k in kicks if k.team == team]


def next_kicker(
    kicks: tuple[ShootoutKick, ...], first_kicker: str | None, initial_kickers: int
) -> str | None:
    """Which side kicks next, or ``None`` when the shootout has not started or is decided."""

    if first_kicker is None:
        return None
    if is_decided(kicks, initial_kickers):
        return None
    home_count = len(_by_team(kicks, "home"))
    away_count = len(_by_team(kicks, "away"))
    second_kicker = _OTHER[first_kicker]
    counts = {first_kicker: home_count if first_kicker == "home" else away_count,
              second_kicker: away_count if first_kicker == "home" else home_count}
    if counts[first_kicker] == counts[second_kicker]:
        return first_kicker
    return second_kicker


def _remaining_initial(kicks: tuple[ShootoutKick, ...], team: str, initial_kickers: int) -> int:
    taken = len(_by_team(kicks, team))
    return max(0, initial_kickers - taken)


def is_decided(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> bool:
    """Whether the tally is already mathematically settled."""

    home_kicks = _by_team(kicks, "home")
    away_kicks = _by_team(kicks, "away")
    home_made = sum(1 for k in home_kicks if k.made)
    away_made = sum(1 for k in away_kicks if k.made)
    home_taken = len(home_kicks)
    away_taken = len(away_kicks)

    home_remaining = _remaining_initial(kicks, "home", initial_kickers)
    away_remaining = _remaining_initial(kicks, "away", initial_kickers)

    if home_taken < initial_kickers or away_taken < initial_kickers:
        # Still inside the first `initial_kickers` round for at least one side:
        # decided early only if one side cannot be caught even with every
        # remaining kick made/missed as unfavourably as possible.
        if home_made > away_made + away_remaining:
            return True
        if away_made > home_made + home_remaining:
            return True
        return False

    # Both sides have taken their initial round. Tied -> sudden death: decided
    # the moment a complete pair (both sides kicked the same number of times
    # beyond the initial round) ends with the scores unequal.
    if home_made != away_made:
        return True
    if home_taken == away_taken:
        return False
    return False


def winner(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> str | None:
    """The decided winner, or ``None`` while undecided or tied so far."""

    if not is_decided(kicks, initial_kickers):
        return None
    home_made = sum(1 for k in _by_team(kicks, "home") if k.made)
    away_made = sum(1 for k in _by_team(kicks, "away") if k.made)
    if home_made > away_made:
        return "home"
    if away_made > home_made:
        return "away"
    return None


def current_round(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> int:
    """The round number the *next* kick belongs to (1-based).

    When one side has already taken its round-N kick and the other has not, the round in
    progress is still N (the other side has not caught up yet); only once both sides have
    kicked the same number of times does the round advance to N+1.
    """

    home_taken = len(_by_team(kicks, "home"))
    away_taken = len(_by_team(kicks, "away"))
    if home_taken != away_taken:
        return max(home_taken, away_taken)
    return home_taken + 1


def in_sudden_death(kicks: tuple[ShootoutKick, ...], initial_kickers: int) -> bool:
    """Whether the shootout has moved past the initial round for both sides."""

    return (
        len(_by_team(kicks, "home")) >= initial_kickers
        and len(_by_team(kicks, "away")) >= initial_kickers
    )


__all__ = [
    "current_round",
    "in_sudden_death",
    "is_decided",
    "next_kicker",
    "winner",
]
