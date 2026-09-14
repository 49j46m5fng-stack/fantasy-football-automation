"""Tests for Sunday remaining-player snapshot integration."""

from datetime import (
    datetime,
    timezone,
)

import pytest

from src.nfl_games import (
    TeamGameState,
)
from src.projections import (
    PlayerProjection,
)
from src.sunday_remaining import (
    SundayRemainingError,
    attach_remaining_to_snapshot,
    build_remaining_lookup,
    serialize_remaining_lookup,
)


KICKOFF = datetime(
    2026,
    9,
    15,
    0,
    15,
    tzinfo=timezone.utc,
)


def projection(
    player_id: str,
    points: float,
) -> PlayerProjection:
    return PlayerProjection(
        player_id=player_id,
        season="2026",
        week=1,
        stats={
            "pts_ppr": points,
        },
    )


def state(
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


def test_build_remaining_lookup() -> None:
    matchup_records = [
        {
            "roster_id": 1,
            "points": 80.0,
            "starters": [
                "sunday-player",
                "monday-player",
            ],
            "players_points": {
                "sunday-player": 18.0,
                "monday-player": 0.0,
            },
        }
    ]

    result = build_remaining_lookup(
        matchup_records=matchup_records,
        projection_lookup={
            "sunday-player": projection(
                "sunday-player",
                15.0,
            ),
            "monday-player": projection(
                "monday-player",
                20.0,
            ),
        },
        players={
            "sunday-player": {
                "full_name": "Sunday Player",
                "position": "RB",
                "team": "DAL",
            },
            "monday-player": {
                "full_name": "Monday Player",
                "position": "QB",
                "team": "KC",
            },
        },
        overrides={},
        team_states={
            "DAL": state(
                "DAL",
                "final",
            ),
            "KC": state(
                "KC",
                "scheduled",
            ),
        },
    )

    assert set(
        result
    ) == {
        1
    }

    team = result[1]

    assert team.current_points == 80.0

    assert (
        team.remaining_projected_points
        == 20.0
    )

    assert (
        team.projected_final_estimate
        == 100.0
    )

    assert (
        team.remaining_player_count
        == 1
    )


def test_serialize_remaining_lookup() -> None:
    lookup = build_remaining_lookup(
        matchup_records=[
            {
                "roster_id": 2,
                "points": 75.5,
                "starters": [
                    "player-1",
                ],
                "players_points": {
                    "player-1": 0.0,
                },
            }
        ],
        projection_lookup={
            "player-1": projection(
                "player-1",
                12.5,
            )
        },
        players={
            "player-1": {
                "full_name": "Monday Receiver",
                "position": "WR",
                "team": "DEN",
            }
        },
        overrides={},
        team_states={
            "DEN": state(
                "DEN",
                "scheduled",
            )
        },
    )

    serialized = (
        serialize_remaining_lookup(
            lookup
        )
    )

    assert set(
        serialized
    ) == {
        "2"
    }

    team = serialized["2"]

    assert (
        team[
            "current_points"
        ]
        == 75.5
    )

    assert (
        team[
            "remaining_projected_points"
        ]
        == 12.5
    )

    assert (
        team[
            "projected_final_estimate"
        ]
        == 88.0
    )

    player = (
        team[
            "players"
        ][0]
    )

    assert (
        player[
            "player_name"
        ]
        == "Monday Receiver"
    )

    assert (
        player[
            "still_to_play"
        ]
        is True
    )

    assert (
        player[
            "kickoff"
        ]
        == KICKOFF.isoformat()
    )


def test_attach_remaining_to_snapshot() -> None:
    snapshot = {
        "schema_version": 1,
        "league_key": "goats",
    }

    lookup = build_remaining_lookup(
        matchup_records=[
            {
                "roster_id": 1,
                "points": 90.0,
                "starters": [
                    "player-1",
                ],
                "players_points": {
                    "player-1": 0.0,
                },
            }
        ],
        projection_lookup={
            "player-1": projection(
                "player-1",
                10.0,
            )
        },
        players={
            "player-1": {
                "full_name": "Monday Player",
                "position": "TE",
                "team": "KC",
            }
        },
        overrides={},
        team_states={
            "KC": state(
                "KC",
                "scheduled",
            )
        },
    )

    enriched = (
        attach_remaining_to_snapshot(
            snapshot,
            lookup,
        )
    )

    assert (
        "remaining"
        not in snapshot
    )

    assert (
        enriched[
            "remaining"
        ][
            "teams"
        ][
            "1"
        ][
            "projected_final_estimate"
        ]
        == 100.0
    )


def test_duplicate_roster_rejected() -> None:
    matchup = {
        "roster_id": 1,
        "points": 10.0,
        "starters": [],
        "players_points": {},
    }

    with pytest.raises(
        SundayRemainingError,
        match="Duplicate",
    ):
        build_remaining_lookup(
            matchup_records=[
                matchup,
                dict(
                    matchup
                ),
            ],
            projection_lookup={},
            players={},
            overrides={},
            team_states={},
        )


def test_missing_current_points_rejected() -> None:
    with pytest.raises(
        SundayRemainingError,
        match="numeric current points",
    ):
        build_remaining_lookup(
            matchup_records=[
                {
                    "roster_id": 1,
                    "starters": [],
                }
            ],
            projection_lookup={},
            players={},
            overrides={},
            team_states={},
        )