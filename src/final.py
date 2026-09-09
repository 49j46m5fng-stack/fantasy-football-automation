"""Build immutable final-stage fantasy snapshot data."""

from typing import Any

from src.normalize import (
    normalize_rosters,
    pair_matchups,
)
from src.players import (
    get_player_name,
)


class FinalBuildError(ValueError):
    """Raised when final snapshot data cannot be assembled safely."""


def _optional_points(
    value: Any,
    description: str,
) -> float | None:
    """Read optional numeric fantasy points without inventing zero."""

    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise FinalBuildError(
            f"{description} must be numeric or null"
        )

    return float(value)


def _baseline_roster_ids(
    baseline_snapshot: dict[str, Any],
    season: str,
    league_key: str,
    league_id: str,
    week: int,
) -> set[int]:
    """Validate baseline identity and return its roster IDs."""

    if baseline_snapshot.get(
        "stage"
    ) != "baseline":
        raise FinalBuildError(
            "Final construction requires "
            "a baseline snapshot"
        )

    expected = {
        "season": season,
        "league_key": league_key,
        "league_id": league_id,
        "week": week,
    }

    for field, value in expected.items():
        if (
            baseline_snapshot.get(field)
            != value
        ):
            raise FinalBuildError(
                f"Baseline identity mismatch "
                f"for {field}"
            )

    data = baseline_snapshot.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise FinalBuildError(
            "Baseline snapshot is missing data"
        )

    teams = data.get(
        "teams"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise FinalBuildError(
            "Baseline snapshot is missing teams"
        )

    roster_ids: set[int] = set()

    for team in teams:
        if not isinstance(
            team,
            dict,
        ):
            raise FinalBuildError(
                "Baseline team must be an object"
            )

        roster_id = team.get(
            "roster_id"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise FinalBuildError(
                "Baseline team is missing "
                "a valid roster_id"
            )

        if roster_id in roster_ids:
            raise FinalBuildError(
                f"Baseline contains duplicate "
                f"roster_id {roster_id}"
            )

        roster_ids.add(
            roster_id
        )

    return roster_ids


def _player_record(
    player_id: str,
    players: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build compact final-stage player metadata."""

    metadata = (
        players.get(
            player_id
        )
        or {}
    )

    return {
        "player_id": player_id,
        "player_name": get_player_name(
            player_id,
            players,
        ),
        "position": metadata.get(
            "position"
        ),
        "team": metadata.get(
            "team"
        ),
        "injury_status": metadata.get(
            "injury_status"
        ),
    }


def _matchup_result(
    roster_a_id: int,
    roster_b_id: int,
    team_lookup: dict[
        int,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    """Calculate one final matchup result."""

    team_a = team_lookup.get(
        roster_a_id
    )

    team_b = team_lookup.get(
        roster_b_id
    )

    if (
        team_a is None
        or team_b is None
    ):
        raise FinalBuildError(
            "Final matchup references "
            "an unknown roster"
        )

    points_a = team_a.get(
        "effective_final_points"
    )

    points_b = team_b.get(
        "effective_final_points"
    )

    if (
        points_a is None
        or points_b is None
    ):
        return {
            "score_complete": False,
            "winner_roster_id": None,
            "loser_roster_id": None,
            "margin": None,
            "tied": None,
        }

    difference = (
        float(points_a)
        - float(points_b)
    )

    if abs(
        difference
    ) < 1e-9:
        return {
            "score_complete": True,
            "winner_roster_id": None,
            "loser_roster_id": None,
            "margin": 0.0,
            "tied": True,
        }

    if difference > 0:
        winner = roster_a_id
        loser = roster_b_id

    else:
        winner = roster_b_id
        loser = roster_a_id

    return {
        "score_complete": True,
        "winner_roster_id": winner,
        "loser_roster_id": loser,
        "margin": abs(
            difference
        ),
        "tied": False,
    }


def build_final_snapshot_data(
    season: str,
    league_key: str,
    league_id: str,
    week: int,
    baseline_snapshot: dict[str, Any],
    league: dict[str, Any],
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    matchup_records: list[dict[str, Any]],
    players: dict[str, dict[str, Any]],
    capture_context: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one league's complete final-stage snapshot."""

    if not season:
        raise FinalBuildError(
            "season cannot be empty"
        )

    if week < 1:
        raise FinalBuildError(
            "week must be at least 1"
        )

    baseline_roster_ids = (
        _baseline_roster_ids(
            baseline_snapshot=(
                baseline_snapshot
            ),
            season=season,
            league_key=league_key,
            league_id=league_id,
            week=week,
        )
    )

    normalized_rosters = (
        normalize_rosters(
            league_key=league_key,
            league_id=league_id,
            users=users,
            rosters=rosters,
        )
    )

    roster_lookup = {
        roster.roster_id: roster
        for roster
        in normalized_rosters
    }

    current_roster_ids = set(
        roster_lookup
    )

    if (
        current_roster_ids
        != baseline_roster_ids
    ):
        raise FinalBuildError(
            "Current roster set does not "
            "match the frozen baseline"
        )

    raw_matchup_lookup: dict[
        int,
        dict[str, Any],
    ] = {}

    for record in matchup_records:
        roster_id = record.get(
            "roster_id"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise FinalBuildError(
                "Matchup record is missing "
                "a valid integer roster_id"
            )

        if (
            roster_id
            in raw_matchup_lookup
        ):
            raise FinalBuildError(
                f"Duplicate matchup record "
                f"for roster {roster_id}"
            )

        raw_matchup_lookup[
            roster_id
        ] = record

    for roster_id in sorted(
        roster_lookup
    ):
        if (
            roster_id
            not in raw_matchup_lookup
        ):
            raise FinalBuildError(
                f"No Week {week} matchup "
                f"record found for roster "
                f"{roster_id}"
            )

    normalized_matchups = (
        pair_matchups(
            league_key=league_key,
            league_id=league_id,
            week=week,
            matchup_records=(
                matchup_records
            ),
        )
    )

    opponent_lookup: dict[
        int,
        int,
    ] = {}

    matchup_id_lookup: dict[
        int,
        int,
    ] = {}

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

    teams: list[
        dict[str, Any]
    ] = []

    league_warnings: list[
        str
    ] = []

    for roster_id in sorted(
        roster_lookup
    ):
        roster = roster_lookup[
            roster_id
        ]

        matchup_record = (
            raw_matchup_lookup[
                roster_id
            ]
        )

        opponent_roster_id = (
            opponent_lookup.get(
                roster_id
            )
        )

        matchup_id = (
            matchup_id_lookup.get(
                roster_id
            )
        )

        if opponent_roster_id is None:
            raise FinalBuildError(
                f"No opponent found for "
                f"roster {roster_id}"
            )

        if matchup_id is None:
            raise FinalBuildError(
                f"No matchup ID found for "
                f"roster {roster_id}"
            )

        raw_starters = (
            matchup_record.get(
                "starters"
            )
            or []
        )

        if not isinstance(
            raw_starters,
            list,
        ):
            raise FinalBuildError(
                f"Roster {roster_id} "
                "starters must be a list"
            )

        raw_rostered_players = (
            matchup_record.get(
                "players"
            )
            or []
        )

        if not isinstance(
            raw_rostered_players,
            list,
        ):
            raise FinalBuildError(
                f"Roster {roster_id} "
                "players must be a list"
            )

        final_points = (
            _optional_points(
                matchup_record.get(
                    "points"
                ),
                (
                    f"Roster {roster_id} "
                    "points"
                ),
            )
        )

        custom_points = (
            _optional_points(
                matchup_record.get(
                    "custom_points"
                ),
                (
                    f"Roster {roster_id} "
                    "custom_points"
                ),
            )
        )

        effective_final_points = (
            custom_points
            if custom_points is not None
            else final_points
        )

        starter_records: list[
            dict[str, Any]
        ] = []

        team_warnings: list[
            str
        ] = []

        for slot, raw_player_id in (
            enumerate(
                raw_starters,
                start=1,
            )
        ):
            if (
                raw_player_id is None
                or not raw_player_id
                or str(
                    raw_player_id
                )
                == "0"
            ):
                starter_records.append(
                    {
                        "slot": slot,
                        "player_id": None,
                        "player_name": (
                            "EMPTY SLOT"
                        ),
                        "position": None,
                        "team": None,
                        "injury_status": None,
                    }
                )

                warning = (
                    f"Roster {roster_id} "
                    f"has an empty final "
                    f"starter slot at "
                    f"position {slot}."
                )

                team_warnings.append(
                    warning
                )

                league_warnings.append(
                    warning
                )

                continue

            player_id = str(
                raw_player_id
            )

            starter_records.append(
                {
                    "slot": slot,
                    **_player_record(
                        player_id,
                        players,
                    ),
                }
            )

        rostered_player_records: list[
            dict[str, Any]
        ] = []

        rostered_player_ids: list[
            str
        ] = []

        seen_player_ids: set[
            str
        ] = set()

        for raw_player_id in (
            raw_rostered_players
        ):
            if (
                raw_player_id is None
                or not raw_player_id
                or str(
                    raw_player_id
                )
                == "0"
            ):
                continue

            player_id = str(
                raw_player_id
            )

            if (
                player_id
                in seen_player_ids
            ):
                continue

            seen_player_ids.add(
                player_id
            )

            rostered_player_ids.append(
                player_id
            )

            rostered_player_records.append(
                _player_record(
                    player_id,
                    players,
                )
            )

        teams.append(
            {
                "roster_id": (
                    roster.roster_id
                ),
                "owner_id": (
                    roster.owner_id
                ),
                "manager_name": (
                    roster.manager_name
                ),
                "matchup_id": (
                    matchup_id
                ),
                "opponent_roster_id": (
                    opponent_roster_id
                ),
                "final_starters_raw": (
                    list(
                        raw_starters
                    )
                ),
                "rostered_player_ids": (
                    rostered_player_ids
                ),
                "final_points": (
                    final_points
                ),
                "custom_points": (
                    custom_points
                ),
                "effective_final_points": (
                    effective_final_points
                ),
                "warnings": (
                    team_warnings
                ),
                "starters": (
                    starter_records
                ),
                "rostered_players": (
                    rostered_player_records
                ),
            }
        )

    team_lookup = {
        team["roster_id"]: team
        for team in teams
    }

    matchups: list[
        dict[str, Any]
    ] = []

    for matchup in (
        normalized_matchups
    ):
        team_a = team_lookup[
            matchup.roster_a_id
        ]

        team_b = team_lookup[
            matchup.roster_b_id
        ]

        result = (
            _matchup_result(
                roster_a_id=(
                    matchup.roster_a_id
                ),
                roster_b_id=(
                    matchup.roster_b_id
                ),
                team_lookup=(
                    team_lookup
                ),
            )
        )

        matchups.append(
            {
                "matchup_id": (
                    matchup.matchup_id
                ),
                "roster_a_id": (
                    matchup.roster_a_id
                ),
                "roster_b_id": (
                    matchup.roster_b_id
                ),
                "roster_a_points": (
                    team_a[
                        "effective_final_points"
                    ]
                ),
                "roster_b_points": (
                    team_b[
                        "effective_final_points"
                    ]
                ),
                **result,
            }
        )

    return {
        "final_format_version": 1,
        "baseline_reference": {
            "created_at": (
                baseline_snapshot.get(
                    "created_at"
                )
            ),
            "schema_version": (
                baseline_snapshot.get(
                    "schema_version"
                )
            ),
        },
        "capture_context": dict(
            capture_context
        ),
        "league": {
            "name": league.get(
                "name"
            ),
            "season": league.get(
                "season"
            ),
            "season_type": (
                league.get(
                    "season_type"
                )
            ),
            "status": league.get(
                "status"
            ),
            "total_rosters": (
                league.get(
                    "total_rosters"
                )
            ),
            "roster_positions": (
                league.get(
                    "roster_positions"
                )
            ),
            "scoring_settings": (
                league.get(
                    "scoring_settings"
                )
            ),
            "settings": (
                league.get(
                    "settings"
                )
            ),
        },
        "matchups": (
            matchups
        ),
        "teams": (
            teams
        ),
        "warnings": (
            league_warnings
        ),
        "source_data": {
            "league": league,
            "users": users,
            "rosters": rosters,
            "matchups": (
                matchup_records
            ),
        },
    }