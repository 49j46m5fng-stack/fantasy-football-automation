from pathlib import Path

import pytest

from src.comparison import (
    SnapshotComparisonError,
    compare_baseline_to_sunday,
    compare_snapshot_files,
)
from src.storage import write_snapshot


def player(
    player_id: str,
    name: str,
    points: float | None,
    source: str = "sleeper_pts_ppr",
) -> dict:
    return {
        "player_id": player_id,
        "player_name": name,
        "projected_points": points,
        "projection_source": source,
    }


def baseline_snapshot() -> dict:
    return {
        "schema_version": 1,
        "season": "2026",
        "week": 1,
        "league_key": "goats",
        "league_id": "test-league",
        "stage": "baseline",
        "created_at": "example",
        "data": {
            "teams": [
                {
                    "roster_id": 1,
                    "manager_name": "Manager One",
                    "baseline_starters_raw": [
                        "a",
                        "b",
                    ],
                    "baseline_projection": 20.0,
                    "warnings": [],
                    "rostered_players": [
                        player(
                            "a",
                            "Player A",
                            10.0,
                        ),
                        player(
                            "b",
                            "Player B",
                            10.0,
                        ),
                        player(
                            "c",
                            "Player C",
                            8.0,
                        ),
                    ],
                },
                {
                    "roster_id": 2,
                    "manager_name": "Manager Two",
                    "baseline_starters_raw": [
                        "d",
                        "e",
                    ],
                    "baseline_projection": 30.0,
                    "warnings": [],
                    "rostered_players": [
                        player(
                            "d",
                            "Player D",
                            15.0,
                        ),
                        player(
                            "e",
                            "Player E",
                            15.0,
                        ),
                    ],
                },
            ]
        },
    }


def sunday_snapshot() -> dict:
    return {
        "schema_version": 1,
        "season": "2026",
        "week": 1,
        "league_key": "goats",
        "league_id": "test-league",
        "stage": "sunday",
        "created_at": "example",
        "data": {
            "teams": [
                {
                    "roster_id": 1,
                    "manager_name": "Manager One",
                    "stage_starters_raw": [
                        "a",
                        "c",
                    ],
                    "stage_projection": 22.0,
                    "warnings": [],
                    "rostered_players": [
                        player(
                            "a",
                            "Player A",
                            11.0,
                        ),
                        player(
                            "b",
                            "Player B",
                            9.0,
                        ),
                        player(
                            "c",
                            "Player C",
                            11.0,
                        ),
                    ],
                },
                {
                    "roster_id": 2,
                    "manager_name": "Manager Two",
                    "stage_starters_raw": [
                        "d",
                        "e",
                    ],
                    "stage_projection": 30.0,
                    "warnings": [],
                    "rostered_players": [
                        player(
                            "d",
                            "Player D",
                            15.0,
                        ),
                        player(
                            "e",
                            "Player E",
                            15.0,
                        ),
                    ],
                },
            ]
        },
    }


def test_detects_lineup_substitution() -> None:
    comparison = compare_baseline_to_sunday(
        baseline_snapshot(),
        sunday_snapshot(),
    )

    team = comparison.teams[0]

    assert team.added_starters == (
        "c",
    )

    assert team.removed_starters == (
        "b",
    )

    assert len(team.slot_changes) == 1

    change = team.slot_changes[0]

    assert change.slot == 2
    assert change.baseline_player_id == "b"
    assert change.sunday_player_id == "c"


def test_detects_slot_move_without_substitution() -> None:
    sunday = sunday_snapshot()

    sunday["data"]["teams"][0][
        "stage_starters_raw"
    ] = [
        "b",
        "a",
    ]

    comparison = compare_baseline_to_sunday(
        baseline_snapshot(),
        sunday,
    )

    team = comparison.teams[0]

    assert team.added_starters == ()
    assert team.removed_starters == ()

    assert len(team.slot_changes) == 2


def test_filling_empty_slot_counts_as_added_starter() -> None:
    baseline = baseline_snapshot()

    baseline["data"]["teams"][0][
        "baseline_starters_raw"
    ] = [
        "a",
        "0",
    ]

    comparison = compare_baseline_to_sunday(
        baseline,
        sunday_snapshot(),
    )

    team = comparison.teams[0]

    assert team.added_starters == (
        "c",
    )

    assert team.removed_starters == ()

    assert (
        team.slot_changes[0]
        .baseline_player_id
        is None
    )

    assert (
        team.slot_changes[0]
        .sunday_player_id
        == "c"
    )


def test_detects_player_projection_movement() -> None:
    comparison = compare_baseline_to_sunday(
        baseline_snapshot(),
        sunday_snapshot(),
    )

    team = comparison.teams[0]

    changes = {
        change.player_id: change
        for change in team.projection_changes
    }

    assert changes["a"].delta == 1.0
    assert changes["b"].delta == -1.0
    assert changes["c"].delta == 3.0


def test_missing_projection_does_not_become_zero() -> None:
    baseline = baseline_snapshot()

    baseline["data"]["teams"][0][
        "rostered_players"
    ][0][
        "projected_points"
    ] = None

    comparison = compare_baseline_to_sunday(
        baseline,
        sunday_snapshot(),
    )

    team = comparison.teams[0]

    changes = {
        change.player_id: change
        for change in team.projection_changes
    }

    change = changes["a"]

    assert change.baseline_points is None
    assert change.sunday_points == 11.0
    assert change.delta is None


def test_detects_team_projection_movement() -> None:
    comparison = compare_baseline_to_sunday(
        baseline_snapshot(),
        sunday_snapshot(),
    )

    team = comparison.teams[0]

    assert (
        team.baseline_team_projection
        == 20.0
    )

    assert (
        team.sunday_team_projection
        == 22.0
    )

    assert (
        team.team_projection_delta
        == 2.0
    )


def test_mismatched_week_is_rejected() -> None:
    sunday = sunday_snapshot()

    sunday["week"] = 2

    with pytest.raises(
        SnapshotComparisonError,
        match="identity mismatch for week",
    ):
        compare_baseline_to_sunday(
            baseline_snapshot(),
            sunday,
        )


def test_mismatched_roster_sets_are_rejected() -> None:
    sunday = sunday_snapshot()

    sunday["data"]["teams"].pop()

    with pytest.raises(
        SnapshotComparisonError,
        match="roster sets do not match",
    ):
        compare_baseline_to_sunday(
            baseline_snapshot(),
            sunday,
        )


def test_compare_snapshot_files(
    tmp_path: Path,
) -> None:
    baseline = baseline_snapshot()
    sunday = sunday_snapshot()

    baseline_path = write_snapshot(
        data_root=tmp_path,
        season="2026",
        week=1,
        league_key="goats",
        league_id="test-league",
        stage="baseline",
        data=baseline["data"],
    )

    sunday_path = write_snapshot(
        data_root=tmp_path,
        season="2026",
        week=1,
        league_key="goats",
        league_id="test-league",
        stage="sunday",
        data=sunday["data"],
    )

    comparison = compare_snapshot_files(
        baseline_path,
        sunday_path,
    )

    assert comparison.week == 1
    assert comparison.league_key == "goats"
    assert len(comparison.teams) == 2
