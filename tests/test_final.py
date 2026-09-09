import pytest

from src.final import (
    FinalBuildError,
    build_final_snapshot_data,
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
                "a",
                "b",
            ],
            "players": [
                "a",
                "b",
                "e",
            ],
            "points": 121.5,
            "custom_points": None,
        },
        {
            "roster_id": 2,
            "matchup_id": 1,
            "starters": [
                "c",
                "d",
            ],
            "players": [
                "c",
                "d",
            ],
            "points": 115.25,
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

    return (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
    )


def build_sample():
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
    ) = sample_inputs()

    return build_final_snapshot_data(
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
        capture_context={
            "mode": "test",
        },
    )


def test_final_contains_both_teams() -> None:
    final = build_sample()

    assert len(
        final["teams"]
    ) == 2


def test_final_preserves_starters() -> None:
    final = build_sample()

    team = final["teams"][0]

    assert (
        team[
            "final_starters_raw"
        ]
        == [
            "a",
            "b",
        ]
    )

    assert (
        team["starters"][0][
            "player_name"
        ]
        == "Player A"
    )


def test_final_preserves_team_scores() -> None:
    final = build_sample()

    team = final["teams"][0]

    assert (
        team[
            "final_points"
        ]
        == 121.5
    )

    assert (
        team[
            "effective_final_points"
        ]
        == 121.5
    )


def test_custom_points_override_effective_score() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
    ) = sample_inputs()

    matchups[0][
        "custom_points"
    ] = 130.0

    final = (
        build_final_snapshot_data(
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
            capture_context={},
        )
    )

    team = final["teams"][0]

    assert (
        team["final_points"]
        == 121.5
    )

    assert (
        team[
            "effective_final_points"
        ]
        == 130.0
    )


def test_matchup_winner_and_margin() -> None:
    final = build_sample()

    matchup = final[
        "matchups"
    ][0]

    assert (
        matchup[
            "winner_roster_id"
        ]
        == 1
    )

    assert (
        matchup[
            "loser_roster_id"
        ]
        == 2
    )

    assert (
        matchup["margin"]
        == pytest.approx(
            6.25
        )
    )

    assert (
        matchup["tied"]
        is False
    )


def test_missing_score_remains_missing() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
    ) = sample_inputs()

    matchups[0][
        "points"
    ] = None

    final = (
        build_final_snapshot_data(
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
            capture_context={},
        )
    )

    assert (
        final["teams"][0][
            "effective_final_points"
        ]
        is None
    )

    assert (
        final["matchups"][0][
            "score_complete"
        ]
        is False
    )

    assert (
        final["matchups"][0][
            "margin"
        ]
        is None
    )


def test_empty_final_slot_is_preserved() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
    ) = sample_inputs()

    matchups[0][
        "starters"
    ][1] = "0"

    final = (
        build_final_snapshot_data(
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
            capture_context={},
        )
    )

    team = final["teams"][0]

    assert (
        team["starters"][1][
            "player_id"
        ]
        is None
    )

    assert len(
        team["warnings"]
    ) == 1


def test_roster_set_must_match_baseline() -> None:
    (
        baseline,
        league,
        users,
        rosters,
        matchups,
        players,
    ) = sample_inputs()

    baseline["data"][
        "teams"
    ].pop()

    with pytest.raises(
        FinalBuildError,
        match=(
            "Current roster set does not "
            "match the frozen baseline"
        ),
    ):
        build_final_snapshot_data(
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
            capture_context={},
        )