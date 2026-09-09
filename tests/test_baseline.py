import pytest

from src.baseline import (
    BaselineBuildError,
    build_baseline_snapshot_data,
)
from src.projections import PlayerProjection


LEAGUE_ID = "test-league"


def sample_inputs():
    league = {
        "name": "Test League",
        "season": "2026",
        "season_type": "regular",
        "status": "in_season",
        "total_rosters": 2,
        "roster_positions": [
            "RB",
            "BN",
        ],
        "scoring_settings": {
            "rec": 1.0,
        },
        "settings": {},
    }

    users = [
        {
            "user_id": "user-1",
            "display_name": "Manager One",
        },
        {
            "user_id": "user-2",
            "display_name": "Manager Two",
        },
    ]

    rosters = [
        {
            "roster_id": 1,
            "owner_id": "user-1",
        },
        {
            "roster_id": 2,
            "owner_id": "user-2",
        },
    ]

    matchups = [
        {
            "roster_id": 1,
            "matchup_id": 1,
            "starters": [
                "starter-1",
            ],
            "players": [
                "starter-1",
                "bench-1",
            ],
        },
        {
            "roster_id": 2,
            "matchup_id": 1,
            "starters": [
                "starter-2",
            ],
            "players": [
                "starter-2",
            ],
        },
    ]

    players = {
        "starter-1": {
            "full_name": "Starter One",
            "position": "RB",
            "team": "AAA",
        },
        "bench-1": {
            "full_name": "Bench One",
            "position": "RB",
            "team": "BBB",
        },
        "starter-2": {
            "full_name": "Starter Two",
            "position": "RB",
            "team": "CCC",
        },
    }

    projections = {
        "starter-1": PlayerProjection(
            player_id="starter-1",
            season="2026",
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 10.0,
                "rush_yd": 50.0,
            },
        ),
        "bench-1": PlayerProjection(
            player_id="bench-1",
            season="2026",
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 100.0,
            },
        ),
        "starter-2": PlayerProjection(
            player_id="starter-2",
            season="2026",
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 20.0,
            },
        ),
    }

    return (
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    )


def build_sample_baseline():
    (
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    ) = sample_inputs()

    return build_baseline_snapshot_data(
        league_key="goats",
        league_id=LEAGUE_ID,
        week=1,
        league=league,
        users=users,
        rosters=rosters,
        matchup_records=matchups,
        players=players,
        projection_lookup=projections,
        overrides={},
        capture_context={
            "first_kickoff": "example",
        },
    )


def test_baseline_contains_both_teams() -> None:
    baseline = build_sample_baseline()

    assert len(baseline["teams"]) == 2


def test_only_starters_count_toward_team_projection() -> None:
    baseline = build_sample_baseline()

    team = baseline["teams"][0]

    assert team["baseline_projection"] == 10.0

    assert (
        team["rostered_players"][1]
        ["projected_points"]
        == 100.0
    )


def test_baseline_preserves_raw_projection_stats() -> None:
    baseline = build_sample_baseline()

    team = baseline["teams"][0]
    starter = team["starters"][0]

    assert (
        starter["projection_stats"]
        ["rush_yd"]
        == 50.0
    )


def test_baseline_preserves_raw_starting_lineup() -> None:
    baseline = build_sample_baseline()

    team = baseline["teams"][0]

    assert team["baseline_starters_raw"] == [
        "starter-1"
    ]


def test_baseline_connects_opponents() -> None:
    baseline = build_sample_baseline()

    team_one = baseline["teams"][0]
    team_two = baseline["teams"][1]

    assert team_one["opponent_roster_id"] == 2
    assert team_two["opponent_roster_id"] == 1


def test_missing_matchup_record_is_rejected() -> None:
    (
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    ) = sample_inputs()

    with pytest.raises(
        BaselineBuildError,
        match="No Week 1 matchup record",
    ):
        build_baseline_snapshot_data(
            league_key="goats",
            league_id=LEAGUE_ID,
            week=1,
            league=league,
            users=users,
            rosters=rosters,
            matchup_records=[
                matchups[0],
            ],
            players=players,
            projection_lookup=projections,
            overrides={},
            capture_context={},
        )