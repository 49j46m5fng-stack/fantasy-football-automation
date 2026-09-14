"""Integrate remaining-player projections into Sunday/MNF snapshots."""

from datetime import datetime
from typing import Any

from src.nfl_games import TeamGameState
from src.projections import PlayerProjection
from src.remaining import (
    RemainingStarter,
    RemainingTeamProjection,
    build_remaining_team_projection,
)
from src.team_projections import ProjectionOverride


class SundayRemainingError(ValueError):
    """Raised when Sunday remaining-player data cannot be built safely."""


def serialize_datetime(
    value: datetime | None,
) -> str | None:
    """Serialize an optional timezone-aware datetime."""

    if value is None:
        return None

    return value.isoformat()


def serialize_remaining_starter(
    starter: RemainingStarter,
) -> dict[str, Any]:
    """Convert one RemainingStarter to JSON-safe data."""

    return {
        "slot": starter.slot,
        "player_id": starter.player_id,
        "player_name": starter.player_name,
        "position": starter.position,
        "nfl_team": starter.nfl_team,
        "actual_points": starter.actual_points,
        "actual_source": starter.actual_source,
        "fresh_projection": starter.fresh_projection,
        "projection_source": starter.projection_source,
        "game_state": starter.game_state,
        "game_id": starter.game_id,
        "opponent": starter.opponent,
        "kickoff": serialize_datetime(
            starter.kickoff
        ),
        "still_to_play": starter.still_to_play,
        "remaining_projection": (
            starter.remaining_projection
        ),
        "reason": starter.reason,
    }


def serialize_remaining_team_projection(
    result: RemainingTeamProjection,
) -> dict[str, Any]:
    """Convert one team remaining projection to JSON-safe data."""

    return {
        "roster_id": result.roster_id,
        "current_points": result.current_points,
        "remaining_player_count": (
            result.remaining_player_count
        ),
        "remaining_projected_points": (
            result.remaining_projected_points
        ),
        "projected_final_estimate": (
            result.projected_final_estimate
        ),
        "players": [
            serialize_remaining_starter(
                starter
            )
            for starter in result.starters
        ],
        "warnings": list(
            result.warnings
        ),
    }


def build_remaining_lookup(
    *,
    matchup_records: list[
        dict[str, Any]
    ],
    projection_lookup: dict[
        str,
        PlayerProjection,
    ],
    players: dict[
        str,
        dict[str, Any],
    ],
    overrides: dict[
        str,
        ProjectionOverride,
    ],
    team_states: dict[
        str,
        TeamGameState,
    ],
    point_field: str = "pts_ppr",
) -> dict[
    int,
    RemainingTeamProjection,
]:
    """Build remaining-player projections for all fantasy rosters."""

    results: dict[
        int,
        RemainingTeamProjection,
    ] = {}

    for matchup_record in matchup_records:
        roster_id = matchup_record.get(
            "roster_id"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise SundayRemainingError(
                "Sunday matchup record is missing "
                "a valid roster_id"
            )

        if roster_id in results:
            raise SundayRemainingError(
                f"Duplicate Sunday roster_id "
                f"{roster_id}"
            )

        raw_current_points = (
            matchup_record.get(
                "points"
            )
        )

        if (
            isinstance(
                raw_current_points,
                bool,
            )
            or not isinstance(
                raw_current_points,
                (int, float),
            )
        ):
            raise SundayRemainingError(
                f"Roster {roster_id} is missing "
                "numeric current points"
            )

        results[
            roster_id
        ] = build_remaining_team_projection(
            matchup_record,
            current_points=float(
                raw_current_points
            ),
            projection_lookup=(
                projection_lookup
            ),
            players=players,
            overrides=overrides,
            team_states=team_states,
            point_field=point_field,
        )

    return results


def serialize_remaining_lookup(
    lookup: dict[
        int,
        RemainingTeamProjection,
    ],
) -> dict[str, dict[str, Any]]:
    """Serialize a roster-keyed remaining projection lookup."""

    return {
        str(roster_id): (
            serialize_remaining_team_projection(
                result
            )
        )
        for roster_id, result
        in sorted(
            lookup.items()
        )
    }


def attach_remaining_to_snapshot(
    snapshot: dict[str, Any],
    lookup: dict[
        int,
        RemainingTeamProjection,
    ],
) -> dict[str, Any]:
    """Attach remaining-player analytics to a Sunday snapshot.

    The existing snapshot is copied rather than modified in place.
    """

    if not isinstance(
        snapshot,
        dict,
    ):
        raise SundayRemainingError(
            "Sunday snapshot must be a dictionary"
        )

    enriched = dict(
        snapshot
    )

    enriched[
        "remaining"
    ] = {
        "calculation": (
            "current_points + projections for "
            "starters whose NFL games have not started"
        ),
        "teams": (
            serialize_remaining_lookup(
                lookup
            )
        ),
    }

    return enriched