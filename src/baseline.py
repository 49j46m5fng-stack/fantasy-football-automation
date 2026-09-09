"""Build structured weekly baseline snapshot data."""

from typing import Any

from src.normalize import normalize_rosters, pair_matchups
from src.players import get_player_name
from src.projections import PlayerProjection
from src.team_projections import (
    ProjectionOverride,
    calculate_team_projection,
    resolve_player_projection,
)


class BaselineBuildError(ValueError):
    """Raised when baseline data cannot be assembled safely."""


def _projection_metadata(
    player_id: str,
    projection_lookup: dict[str, PlayerProjection],
) -> dict[str, Any]:
    """Return the original projection-feed details for one player."""

    projection = projection_lookup.get(player_id)

    if projection is None:
        return {
            "category": None,
            "company": None,
            "stats": None,
        }

    return {
        "category": projection.category,
        "company": projection.company,
        "stats": dict(projection.stats),
    }


def _build_rostered_player_record(
    player_id: str,
    projection_lookup: dict[str, PlayerProjection],
    players: dict[str, dict[str, Any]],
    overrides: dict[str, ProjectionOverride],
    point_field: str,
) -> dict[str, Any]:
    """Build baseline projection data for any rostered player."""

    metadata = players.get(player_id) or {}

    resolved = resolve_player_projection(
        slot=0,
        player_id=player_id,
        projection_lookup=projection_lookup,
        players=players,
        overrides=overrides,
        point_field=point_field,
    )

    projection_metadata = _projection_metadata(
        player_id,
        projection_lookup,
    )

    return {
        "player_id": player_id,
        "player_name": get_player_name(
            player_id,
            players,
        ),
        "position": metadata.get("position"),
        "team": metadata.get("team"),
        "injury_status": metadata.get("injury_status"),
        "projected_points": resolved.points,
        "projection_source": resolved.source,
        "projection_reason": resolved.reason,
        "projection_category": projection_metadata["category"],
        "projection_company": projection_metadata["company"],
        "projection_stats": projection_metadata["stats"],
    }


def build_baseline_snapshot_data(
    league_key: str,
    league_id: str,
    week: int,
    league: dict[str, Any],
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    matchup_records: list[dict[str, Any]],
    players: dict[str, dict[str, Any]],
    projection_lookup: dict[str, PlayerProjection],
    overrides: dict[str, ProjectionOverride],
    capture_context: dict[str, Any],
    point_field: str = "pts_ppr",
) -> dict[str, Any]:
    """Assemble one league's complete baseline snapshot contents."""

    if week < 1:
        raise BaselineBuildError(
            "week must be at least 1"
        )

    # Normalize managers and fantasy rosters first.
    normalized_rosters = normalize_rosters(
        league_key=league_key,
        league_id=league_id,
        users=users,
        rosters=rosters,
    )

    roster_lookup = {
        roster.roster_id: roster
        for roster in normalized_rosters
    }

    # Build a roster -> raw matchup record lookup before attempting
    # to pair opponents. This lets us produce a clear baseline-level
    # error when a roster is missing its weekly matchup record.
    raw_matchup_lookup: dict[int, dict[str, Any]] = {}

    for record in matchup_records:
        roster_id = record.get("roster_id")

        if not isinstance(roster_id, int):
            raise BaselineBuildError(
                "Matchup record is missing "
                "a valid integer roster_id"
            )

        if roster_id in raw_matchup_lookup:
            raise BaselineBuildError(
                f"Duplicate matchup record for "
                f"roster {roster_id}"
            )

        raw_matchup_lookup[roster_id] = record

    # Every fantasy roster must have exactly one weekly matchup record.
    for roster_id in sorted(roster_lookup):
        if roster_id not in raw_matchup_lookup:
            raise BaselineBuildError(
                f"No Week {week} matchup record "
                f"found for roster {roster_id}"
            )

    # Now that completeness has been validated, safely pair opponents.
    normalized_matchups = pair_matchups(
        league_key=league_key,
        league_id=league_id,
        week=week,
        matchup_records=matchup_records,
    )

    opponent_lookup: dict[int, int] = {}
    matchup_id_lookup: dict[int, int] = {}

    for matchup in normalized_matchups:
        opponent_lookup[
            matchup.roster_a_id
        ] = matchup.roster_b_id

        opponent_lookup[
            matchup.roster_b_id
        ] = matchup.roster_a_id

        matchup_id_lookup[
            matchup.roster_a_id
        ] = matchup.matchup_id

        matchup_id_lookup[
            matchup.roster_b_id
        ] = matchup.matchup_id

    teams: list[dict[str, Any]] = []
    league_warnings: list[str] = []

    for roster_id in sorted(roster_lookup):
        roster = roster_lookup[roster_id]

        matchup_record = raw_matchup_lookup[roster_id]

        opponent_roster_id = opponent_lookup.get(
            roster_id
        )

        if opponent_roster_id is None:
            raise BaselineBuildError(
                f"No opponent found for "
                f"roster {roster_id}"
            )

        matchup_id = matchup_id_lookup.get(
            roster_id
        )

        if matchup_id is None:
            raise BaselineBuildError(
                f"No matchup ID found for "
                f"roster {roster_id}"
            )

        raw_starters = (
            matchup_record.get("starters")
            or []
        )

        if not isinstance(raw_starters, list):
            raise BaselineBuildError(
                f"Roster {roster_id} starters "
                "must be a list"
            )

        raw_rostered_players = (
            matchup_record.get("players")
            or []
        )

        if not isinstance(
            raw_rostered_players,
            list,
        ):
            raise BaselineBuildError(
                f"Roster {roster_id} players "
                "must be a list"
            )

        # Team projection counts starters only.
        team_projection = calculate_team_projection(
            matchup_record=matchup_record,
            projection_lookup=projection_lookup,
            players=players,
            overrides=overrides,
            point_field=point_field,
        )

        starter_records: list[
            dict[str, Any]
        ] = []

        for starter in team_projection.starters:
            # Empty Sleeper lineup slots remain visible in the
            # baseline instead of being disguised as player IDs.
            if starter.player_id is None:
                starter_records.append(
                    {
                        "slot": starter.slot,
                        "player_id": None,
                        "player_name": starter.player_name,
                        "position": None,
                        "team": None,
                        "injury_status": None,
                        "projected_points": starter.points,
                        "projection_source": starter.source,
                        "projection_reason": starter.reason,
                        "projection_category": None,
                        "projection_company": None,
                        "projection_stats": None,
                    }
                )

                continue

            player_record = _build_rostered_player_record(
                player_id=starter.player_id,
                projection_lookup=projection_lookup,
                players=players,
                overrides=overrides,
                point_field=point_field,
            )

            starter_records.append(
                {
                    "slot": starter.slot,
                    **player_record,
                }
            )

        # Preserve projections for every rostered player, including
        # bench players, so later lineup-change analysis can compare
        # against the projection information that existed at baseline.
        rostered_player_records: list[
            dict[str, Any]
        ] = []

        seen_player_ids: set[str] = set()

        for raw_player_id in raw_rostered_players:
            if (
                not raw_player_id
                or str(raw_player_id) == "0"
            ):
                continue

            player_id = str(raw_player_id)

            if player_id in seen_player_ids:
                continue

            seen_player_ids.add(player_id)

            rostered_player_records.append(
                _build_rostered_player_record(
                    player_id=player_id,
                    projection_lookup=projection_lookup,
                    players=players,
                    overrides=overrides,
                    point_field=point_field,
                )
            )

        team_warnings = list(
            team_projection.warnings
        )

        league_warnings.extend(
            team_warnings
        )

        teams.append(
            {
                "roster_id": roster.roster_id,
                "owner_id": roster.owner_id,
                "manager_name": roster.manager_name,
                "matchup_id": matchup_id,
                "opponent_roster_id": opponent_roster_id,
                "baseline_starters_raw": list(
                    raw_starters
                ),
                "rostered_player_ids": [
                    str(player_id)
                    for player_id in raw_rostered_players
                    if player_id
                    and str(player_id) != "0"
                ],
                "baseline_projection": (
                    team_projection.projected_points
                ),
                "known_projected_points": (
                    team_projection.known_projected_points
                ),
                "projection_complete": (
                    team_projection.complete
                ),
                "warnings": team_warnings,
                "starters": starter_records,
                "rostered_players": (
                    rostered_player_records
                ),
            }
        )

    matchups = [
        {
            "matchup_id": matchup.matchup_id,
            "roster_a_id": matchup.roster_a_id,
            "roster_b_id": matchup.roster_b_id,
        }
        for matchup in normalized_matchups
    ]

    return {
        "baseline_format_version": 1,
        "capture_context": dict(
            capture_context
        ),
        "projection_method": {
            "provider": (
                "Sleeper unofficial projection feed"
            ),
            "category": "proj",
            "point_field": point_field,
            "exact_league_scoring": False,
        },
        "league": {
            "name": league.get("name"),
            "season": league.get("season"),
            "season_type": league.get(
                "season_type"
            ),
            "status": league.get("status"),
            "total_rosters": league.get(
                "total_rosters"
            ),
            "roster_positions": league.get(
                "roster_positions"
            ),
            "scoring_settings": league.get(
                "scoring_settings"
            ),
            "settings": league.get(
                "settings"
            ),
        },
        "matchups": matchups,
        "teams": teams,
        "warnings": league_warnings,
        "source_data": {
            "league": league,
            "users": users,
            "rosters": rosters,
            "matchups": matchup_records,
        },
    }