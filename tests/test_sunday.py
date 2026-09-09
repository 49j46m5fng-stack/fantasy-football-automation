import pytest

from src.projections import PlayerProjection
from src.sunday import (
    SundayBuildError,
    build_sunday_snapshot_data,
)


SEASON = "2026"
LEAGUE_ID = "test-league"


def sample_inputs():
    baseline = {
        "schema_version": 1,
        "season": SEASON,
        "week": 1,
        "league_key": "goats",
        "league_id": LEAGUE_ID,
        "stage": "baseline",
        "created_at": "example",
        "data": {
            "teams": [
                {
                    "roster_id": 1,
                },
                {
                    "roster_id": 2,
                },
            ]
        },
    }

    league = {
        "name": "Test League",
        "season": SEASON,
        "season_type": "regular",
        "status": "in_season",
        "total_rosters": 2,
        "roster_positions": [
            "RB",
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
            "display_name": (
                "Manager One"
            ),
        },
        {
            "user_id": "user-2",
            "display_name": (
                "Manager Two"
            ),
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
                "a",
                "c",
            ],
            "players": [
                "a",
                "b",
                "c",
            ],
            "points": 44.5,
            "custom_points": None,
        },
        {
            "roster_id": 2,
            "matchup_id": 1,
            "starters": [
                "d",
                "0",
            ],
            "players": [
                "d",
                "e",
            ],
            "points": 32.0,
            "custom_points": None,
        },
    ]

    players = {
        "a": {
            "full_name": "Player A",
            "position": "RB",
            "team": "AAA",
        },
        "b": {
            "full_name": "Player B",
            "position": "RB",
            "team": "BBB",
        },
        "c": {
            "full_name": "Player C",
            "position": "RB",
            "team": "CCC",
        },
        "d": {
            "full_name": "Player D",
            "position": "RB",
            "team": "DDD",
        },
        "e": {
            "full_name": "Player E",
            "position": "RB",
            "team": "EEE",
        },
    }

    projections = {
        "a": PlayerProjection(
            player_id="a",
            season=SEASON,
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 11.0,
                "rush_yd": 60.0,
            },
        ),
        "b": PlayerProjection(
            player_id="b",
            season=SEASON,
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 100.0,
            },
        ),
        "c": PlayerProjection(
            player_id="c",
            season=SEASON,
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 12.0,
            },
        ),
        "d": PlayerProjection(
            player_id="d",
            season=SEASON,
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 15.0,
            },
        ),
        "e": PlayerProjection(
            player_id="e",
            season=SEASON,
            week=1,
            category="proj",
            company="test",
            stats={
                "pts_ppr": 9.0,
            },
        ),
    }

    return (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    )


def build_sample():
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    ) = sample_inputs()

    return build_sunday_snapshot_data(
        season=SEASON,
        league_key="goats",
        league_id=LEAGUE_ID,
        week=1,
        baseline_snapshot=baseline,
        league=league,
        users=users,
        rosters=rosters,
        matchup_records=matchups,
        players=players,
        projection_lookup=projections,
        overrides={},
        capture_context={
            "mode": "test",
        },
    )


def test_sunday_contains_both_teams() -> None:
    sunday = build_sample()

    assert len(
        sunday["teams"]
    ) == 2


def test_sunday_preserves_current_starters() -> None:
    sunday = build_sample()

    team = sunday["teams"][0]

    assert team[
        "stage_starters_raw"
    ] == [
        "a",
        "c",
    ]


def test_stage_projection_counts_only_starters() -> None:
    sunday = build_sample()

    team = sunday["teams"][0]

    assert (
        team["stage_projection"]
        == 23.0
    )

    bench = {
        record["player_id"]: record
        for record in (
            team["rostered_players"]
        )
    }

    assert (
        bench["b"][
            "projected_points"
        ]
        == 100.0
    )


def test_sunday_preserves_live_team_points() -> None:
    sunday = build_sample()

    team = sunday["teams"][0]

    assert (
        team["live_points"]
        == 44.5
    )

    assert (
        team[
            "effective_live_points"
        ]
        == 44.5
    )


def test_custom_points_become_effective_score() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    ) = sample_inputs()

    matchups[0][
        "custom_points"
    ] = 50.25

    sunday = (
        build_sunday_snapshot_data(
            season=SEASON,
            league_key="goats",
            league_id=LEAGUE_ID,
            week=1,
            baseline_snapshot=(
                baseline
            ),
            league=league,
            users=users,
            rosters=rosters,
            matchup_records=(
                matchups
            ),
            players=players,
            projection_lookup=(
                projections
            ),
            overrides={},
            capture_context={},
        )
    )

    team = sunday["teams"][0]

    assert (
        team["live_points"]
        == 44.5
    )

    assert (
        team["custom_points"]
        == 50.25
    )

    assert (
        team[
            "effective_live_points"
        ]
        == 50.25
    )


def test_empty_slot_is_preserved_with_warning() -> None:
    sunday = build_sample()

    team = sunday["teams"][1]

    assert (
        team["stage_starters_raw"]
        == [
            "d",
            "0",
        ]
    )

    assert (
        team["starters"][1][
            "player_id"
        ]
        is None
    )

    assert (
        team["starters"][1][
            "projection_source"
        ]
        == "empty_slot"
    )

    assert len(
        team["warnings"]
    ) == 1


def test_missing_live_points_stays_missing() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    ) = sample_inputs()

    matchups[0][
        "points"
    ] = None

    sunday = (
        build_sunday_snapshot_data(
            season=SEASON,
            league_key="goats",
            league_id=LEAGUE_ID,
            week=1,
            baseline_snapshot=(
                baseline
            ),
            league=league,
            users=users,
            rosters=rosters,
            matchup_records=(
                matchups
            ),
            players=players,
            projection_lookup=(
                projections
            ),
            overrides={},
            capture_context={},
        )
    )

    team = sunday["teams"][0]

    assert (
        team["live_points"]
        is None
    )

    assert (
        team[
            "effective_live_points"
        ]
        is None
    )


def test_roster_set_must_match_baseline() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
        projections,
    ) = sample_inputs()

    baseline["data"][
        "teams"
    ].pop()

    with pytest.raises(
        SundayBuildError,
        match=(
            "Current roster set does not "
            "match the frozen baseline"
        ),
    ):
        build_sunday_snapshot_data(
            season=SEASON,
            league_key="goats",
            league_id=LEAGUE_ID,
            week=1,
            baseline_snapshot=(
                baseline
            ),
            league=league,
            users=users,
            rosters=rosters,
            matchup_records=(
                matchups
            ),
            players=players,
            projection_lookup=(
                projections
            ),
            overrides={},
            capture_context={},
        )