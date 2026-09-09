"""Build exact player-week actual scoring from normalized Sleeper stats."""

from typing import Any

from src.player_stats import (
    PlayerWeekStat,
)
from src.scoring import (
    FantasyScoringError,
    ScoredPlayerWeek,
    score_player_week,
)


class ActualScoringError(ValueError):
    """Raised when exact player actuals cannot be constructed safely."""


def build_exact_score_lookup(
    records: list[PlayerWeekStat],
    scoring_settings: dict[str, Any],
) -> dict[str, ScoredPlayerWeek]:
    """Build player_id -> exact league-scored player-week result.

    Duplicate player records are rejected.

    Missing players are not manufactured. If a player does not have a
    normalized stat record, that player simply will not appear in the
    returned lookup.
    """

    lookup: dict[
        str,
        ScoredPlayerWeek,
    ] = {}

    for record in records:
        if (
            record.player_id
            in lookup
        ):
            raise ActualScoringError(
                "Duplicate actual-stat record "
                f"for player {record.player_id}"
            )

        try:
            scored = (
                score_player_week(
                    record,
                    scoring_settings,
                )
            )

        except FantasyScoringError as exc:
            raise ActualScoringError(
                "Could not score actual stats "
                f"for player {record.player_id}: "
                f"{exc}"
            ) from exc

        if scored is None:
            raise ActualScoringError(
                "Existing player-stat record "
                f"unexpectedly scored as null: "
                f"{record.player_id}"
            )

        lookup[
            record.player_id
        ] = scored

    return lookup