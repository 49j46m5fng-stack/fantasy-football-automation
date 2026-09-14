"""Tests for remaining Monday/MNF fantasy projections."""

from datetime import (
    datetime,
    timezone,
)

from src.nfl_games import (
    TeamGameState,
)
from src.projections import (
    PlayerProjection,
)
from src.remaining import (
    build_remaining_team_projection,
)


KICKOFF = datetime(
    2026,
    9,
    15,
    0,
    15,
    tzinfo=timezone.utc,
)


def team_state(
    team: str,
    status: str,
) -> TeamGameState:
    return TeamGameState(
        team=team,
        game_id=f"{team}-game",
        kickoff=KICKOFF,
        opponent="OPP",
        status=status,
    )


def projection(
    player_id: str,
    points: float | None,
) -> PlayerProjection:
    stats = {}

    if points is not None:
        stats["pts_ppr"] = points

    return PlayerProjection(
        player_id=player_id,
        season="2026",
        week=1,
        stats=stats,
    )


def test_scheduled_player_counts_as_remaining() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {
            "player-1": 0.0,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=80.0,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    15.5,
                ),
            },
            players={
                "player-1": {
                    "full_name": "Monday Player",
                    "position": "WR",
                    "team": "KC",
                }
            },
            overrides={},
            team_states={
                "KC": team_state(
                    "KC",
                    "scheduled",
                )
            },
        )
    )

    assert (
        result.remaining_projected_points
        == 15.5
    )

    assert (
        result.projected_final_estimate
        == 95.5
    )

    assert (
        result.remaining_player_count
        == 1
    )

    starter = result.starters[0]

    assert starter.still_to_play is True
    assert starter.game_state == "scheduled"

    assert (
        starter.remaining_projection
        == 15.5
    )


def test_final_player_has_zero_remaining() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {
            "player-1": 22.4,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=90.0,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    17.0,
                ),
            },
            players={
                "player-1": {
                    "full_name": "Finished Player",
                    "position": "RB",
                    "team": "DAL",
                }
            },
            overrides={},
            team_states={
                "DAL": team_state(
                    "DAL",
                    "final",
                )
            },
        )
    )

    starter = result.starters[0]

    assert starter.actual_points == 22.4

    assert (
        starter.actual_source
        == "sleeper_matchup_players_points"
    )

    assert starter.still_to_play is False

    assert (
        starter.remaining_projection
        == 0.0
    )

    assert (
        result.remaining_projected_points
        == 0.0
    )

    assert (
        result.projected_final_estimate
        == 90.0
    )


def test_in_progress_player_is_unresolved() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {
            "player-1": 7.2,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=87.2,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    20.0,
                ),
            },
            players={
                "player-1": {
                    "full_name": "Live Player",
                    "position": "QB",
                    "team": "KC",
                }
            },
            overrides={},
            team_states={
                "KC": team_state(
                    "KC",
                    "in_progress",
                )
            },
        )
    )

    starter = result.starters[0]

    assert starter.actual_points == 7.2

    assert (
        starter.remaining_projection
        is None
    )

    assert (
        result.remaining_projected_points
        is None
    )

    assert (
        result.projected_final_estimate
        is None
    )

    assert result.warnings


def test_unknown_game_state_is_unresolved() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {},
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=50.0,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    11.0,
                ),
            },
            players={
                "player-1": {
                    "full_name": "Mystery Player",
                    "position": "WR",
                    "team": "KC",
                }
            },
            overrides={},
            team_states={},
        )
    )

    assert (
        result.remaining_projected_points
        is None
    )

    assert (
        result.projected_final_estimate
        is None
    )


def test_missing_projection_defaults_to_zero() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {
            "player-1": 0.0,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=70.0,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    None,
                ),
            },
            players={
                "player-1": {
                    "full_name": "No Projection",
                    "position": "TE",
                    "team": "KC",
                }
            },
            overrides={},
            team_states={
                "KC": team_state(
                    "KC",
                    "scheduled",
                )
            },
        )
    )

    starter = result.starters[0]

    assert starter.fresh_projection == 0.0

    assert (
        starter.remaining_projection
        == 0.0
    )

    assert (
        result.projected_final_estimate
        == 70.0
    )


def test_missing_projection_record_defaults_to_zero() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {
            "player-1": 0.0,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=70.0,
            projection_lookup={},
            players={
                "player-1": {
                    "full_name": "Missing Record",
                    "position": "TE",
                    "team": "KC",
                }
            },
            overrides={},
            team_states={
                "KC": team_state(
                    "KC",
                    "scheduled",
                )
            },
        )
    )

    starter = result.starters[0]

    assert starter.fresh_projection == 0.0

    assert (
        starter.projection_source
        == "missing_projection_zero"
    )

    assert (
        result.projected_final_estimate
        == 70.0
    )


def test_scheduled_missing_actual_is_zero() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
        ],
        "players_points": {},
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=60.0,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    9.8,
                ),
            },
            players={
                "player-1": {
                    "full_name": "Tonight Player",
                    "position": "WR",
                    "team": "DEN",
                }
            },
            overrides={},
            team_states={
                "DEN": team_state(
                    "DEN",
                    "scheduled",
                )
            },
        )
    )

    starter = result.starters[0]

    assert starter.actual_points == 0.0

    assert (
        starter.actual_source
        == "not_started_zero"
    )


def test_multiple_remaining_players_are_summed() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "player-1",
            "player-2",
            "player-3",
        ],
        "players_points": {
            "player-1": 14.0,
            "player-2": 0.0,
            "player-3": 0.0,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=88.0,
            projection_lookup={
                "player-1": projection(
                    "player-1",
                    15.0,
                ),
                "player-2": projection(
                    "player-2",
                    20.5,
                ),
                "player-3": projection(
                    "player-3",
                    8.25,
                ),
            },
            players={
                "player-1": {
                    "full_name": "Sunday Player",
                    "position": "RB",
                    "team": "DAL",
                },
                "player-2": {
                    "full_name": "Monday QB",
                    "position": "QB",
                    "team": "KC",
                },
                "player-3": {
                    "full_name": "Monday WR",
                    "position": "WR",
                    "team": "DEN",
                },
            },
            overrides={},
            team_states={
                "DAL": team_state(
                    "DAL",
                    "final",
                ),
                "KC": team_state(
                    "KC",
                    "scheduled",
                ),
                "DEN": team_state(
                    "DEN",
                    "scheduled",
                ),
            },
        )
    )

    assert (
        result.remaining_player_count
        == 2
    )

    assert (
        result.remaining_projected_points
        == 28.75
    )

    assert (
        result.projected_final_estimate
        == 116.75
    )


def test_empty_slot_contributes_zero() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "0",
        ],
        "players_points": {},
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=50.0,
            projection_lookup={},
            players={},
            overrides={},
            team_states={},
        )
    )

    starter = result.starters[0]

    assert starter.player_id is None
    assert starter.game_state == "empty_slot"

    assert (
        starter.remaining_projection
        == 0.0
    )

    assert (
        result.projected_final_estimate
        == 50.0
    )


def test_defense_uses_player_id_as_team() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "KC",
        ],
        "players_points": {
            "KC": 0.0,
        },
    }

    result = (
        build_remaining_team_projection(
            matchup,
            current_points=50.0,
            projection_lookup={
                "KC": projection(
                    "KC",
                    6.0,
                ),
            },
            players={
                "KC": {
                    "full_name": "Kansas City Chiefs",
                    "position": "DEF",
                }
            },
            overrides={},
            team_states={
                "KC": team_state(
                    "KC",
                    "scheduled",
                )
            },
        )
    )

    starter = result.starters[0]

    assert starter.nfl_team == "KC"
    assert starter.still_to_play is True

    assert (
        starter.remaining_projection
        == 6.0
    )