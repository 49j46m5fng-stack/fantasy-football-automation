"""Normalize weekly player actuals for downstream analytics.

Two scoring representations are intentionally preserved:

- ppr_points:
    Sleeper's actual pts_ppr value. This is compared with the frozen
    baseline pts_ppr projection for boom/bust analytics.

- exact_points:
    Fantasy points calculated from raw stats using the league's exact
    scoring_settings. This is used for lineup efficiency and optimal
    lineup analytics.

Missing actual records are never silently converted to zero.
"""

from dataclasses import dataclass
from typing import Any

from src.player_stats import (
    PlayerStatsError,
    PlayerWeekStat,
    actual_ppr_points,
)
from src.scoring import (
    FantasyScoringError,
    score_player_week,
)


class ActualScoringError(ValueError):
    """Raised when normalized player actuals cannot be built safely."""


@dataclass(frozen=True)
class PlayerActual:
    """Both comparison-PPR and exact league scoring for one player-week."""

    player_id: str
    season: str
    week: int
    ppr_points: float | None
    exact_points: float


def build_player_actual_lookup(
    records: list[PlayerWeekStat],
    scoring_settings: dict[str, Any],
) -> dict[str, PlayerActual]:
    """Build player_id -> normalized actual scoring.

    Duplicate player records are rejected.

    A record may legitimately have no pts_ppr value. In that case its
    ppr_points remains None while its exact league score can still be
    calculated from the raw statistics.
    """

    lookup: dict[
        str,
        PlayerActual,
    ] = {}

    for record in records:
        player_id = record.player_id

        if player_id in lookup:
            raise ActualScoringError(
                "Duplicate actual-stat record "
                f"for player {player_id}"
            )

        try:
            ppr_points = (
                actual_ppr_points(
                    record
                )
            )

            scored = (
                score_player_week(
                    record,
                    scoring_settings,
                )
            )

        except (
            PlayerStatsError,
            FantasyScoringError,
        ) as exc:
            raise ActualScoringError(
                "Could not normalize actual "
                f"scoring for player {player_id}: "
                f"{exc}"
            ) from exc

        if scored is None:
            raise ActualScoringError(
                "Existing player-stat record "
                f"unexpectedly scored as null: "
                f"{player_id}"
            )

        lookup[
            player_id
        ] = PlayerActual(
            player_id=player_id,
            season=record.season,
            week=record.week,
            ppr_points=ppr_points,
            exact_points=(
                scored.points
            ),
        )

    return lookup