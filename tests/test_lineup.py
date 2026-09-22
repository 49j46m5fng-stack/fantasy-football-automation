import pytest

from src.actuals import (
    PlayerActual,
)
from src.lineup import (
    LineupAnalyticsError,
    analyze_final_lineup_efficiency,
)


def _actual(
    player_id: str,
    points: float,
    week: int = 1,
) -> PlayerActual:
    return PlayerActual(
        player_id=player_id,
        season="2026",
        week=week,
        ppr_points=points,
        exact_points=points,
    )


def _actuals() -> dict[
    str,
    PlayerActual,
]:
    return {
        "q1": _actual(
            "q1",
            10.0,
        ),
        "r1": _actual(
            "r1",
            5.0,
        ),
        "w1": _actual(
            "w1",
            4.0,
        ),
        "r2": _actual(
            "r2",
            20.0,
        ),
        "w2": _actual(
            "w2",
            15.0,
        ),
    }


def _final_snapshot() -> dict:
    return {
        "season": "2026",
        "week": 1,
        "league_key": "goats",
        "stage": "final",
        "data": {
            "league": {
                "roster_positions": [
                    "QB",
                    "RB",
                    "FLEX",
                    "BN",
                    "BN",
                ],
            },
            "teams": [
                {
                    "roster_id": 1,
                    "manager_name": (
                        "Manager One"
                    ),
                    "final_points": 19.0,
                    "custom_points": None,
                    "starters": [
                        {
                            "slot": 1,
                            "player_id": "q1",
                            "player_name": (
                                "Quarterback"
                            ),
                            "position": "QB",
                        },
                        {
                            "slot": 2,
                            "player_id": "r1",
                            "player_name": (
                                "Running Back One"
                            ),
                            "position": "RB",
                        },
                        {
                            "slot": 3,
                            "player_id": "w1",
                            "player_name": (
                                "Wide Receiver One"
                            ),
                            "position": "WR",
                        },
                    ],
                    "rostered_players": [
                        {
                            "player_id": "q1",
                            "player_name": (
                                "Quarterback"
                            ),
                            "position": "QB",
                        },
                        {
                            "player_id": "r1",
                            "player_name": (
                                "Running Back One"
                            ),
                            "position": "RB",
                        },
                        {
                            "player_id": "w1",
                            "player_name": (
                                "Wide Receiver One"
                            ),
                            "position": "WR",
                        },
                        {
                            "player_id": "r2",
                            "player_name": (
                                "Running Back Two"
                            ),
                            "position": "RB",
                        },
                        {
                            "player_id": "w2",
                            "player_name": (
                                "Wide Receiver Two"
                            ),
                            "position": "WR",
                        },
                    ],
                }
            ],
        },
    }


def test_actual_lineup_points() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    team = result.teams[0]

    assert (
        team.actual_lineup_points
        == pytest.approx(
            19.0
        )
    )


def test_optimizer_uses_legal_flex() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    team = result.teams[0]

    assignments = {
        assignment.slot_type: (
            assignment.player_id
        )
        for assignment
        in team.optimal_lineup
    }

    assert (
        assignments["QB"]
        == "q1"
    )

    assert (
        assignments["RB"]
        == "r2"
    )

    assert (
        assignments["FLEX"]
        == "w2"
    )


def test_optimal_lineup_points() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    assert (
        result.teams[0]
        .optimal_lineup_points
        == pytest.approx(
            45.0
        )
    )


def test_points_left_on_bench() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    assert (
        result.teams[0]
        .points_left_on_bench
        == pytest.approx(
            26.0
        )
    )


def test_lineup_efficiency_percentage() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    assert (
        result.teams[0]
        .lineup_efficiency_pct
        == pytest.approx(
            42.2222
        )
    )


def test_total_bench_points() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    assert (
        result.teams[0]
        .bench_points
        == pytest.approx(
            35.0
        )
    )


def test_start_sit_mistakes_identified() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    team = result.teams[0]

    assert {
        player.player_id
        for player
        in team.should_start
    } == {
        "r2",
        "w2",
    }

    assert {
        player.player_id
        for player
        in team.should_bench
    } == {
        "r1",
        "w1",
    }


def test_final_team_score_reconciles() -> None:
    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            _actuals(),
        )
    )

    assert (
        result.teams[0]
        .score_reconciliation_delta
        == pytest.approx(
            0.0
        )
    )


def test_missing_bench_actual_blocks_optimization() -> None:
    actuals = _actuals()

    actuals.pop(
        "r2"
    )

    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            actuals,
        )
    )

    team = result.teams[0]

    assert (
        team.optimization_complete
        is False
    )

    assert (
        team.optimal_lineup_points
        is None
    )

    assert (
        team.bench_points
        is None
    )

    assert (
        "r2"
        in team.unresolved_player_ids
    )


def test_missing_starter_actual_keeps_score_unresolved() -> None:
    actuals = _actuals()

    actuals.pop(
        "q1"
    )

    result = (
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            actuals,
        )
    )

    team = result.teams[0]

    assert (
        team.actual_lineup_complete
        is False
    )

    assert (
        team.actual_lineup_points
        is None
    )

    assert (
        team.score_reconciliation_delta
        is None
    )


def test_empty_starter_slot_is_known_zero() -> None:
    snapshot = _final_snapshot()

    snapshot[
        "data"
    ][
        "teams"
    ][0][
        "starters"
    ][2] = {
        "slot": 3,
        "player_id": None,
        "player_name": (
            "EMPTY SLOT"
        ),
        "position": None,
    }

    result = (
        analyze_final_lineup_efficiency(
            snapshot,
            _actuals(),
        )
    )

    team = result.teams[0]

    assert (
        team.actual_lineup_complete
        is True
    )

    assert (
        team.actual_lineup_points
        == pytest.approx(
            15.0
        )
    )


def test_wrong_actual_week_rejected() -> None:
    actuals = _actuals()

    actuals[
        "q1"
    ] = _actual(
        "q1",
        10.0,
        week=2,
    )

    with pytest.raises(
        LineupAnalyticsError,
        match="wrong season/week",
    ):
        analyze_final_lineup_efficiency(
            _final_snapshot(),
            actuals,
        )


def test_non_final_snapshot_rejected() -> None:
    snapshot = _final_snapshot()

    snapshot[
        "stage"
    ] = "baseline"

    with pytest.raises(
        LineupAnalyticsError,
        match="final snapshot",
    ):
        analyze_final_lineup_efficiency(
            snapshot,
            _actuals(),
        )


def test_unsupported_starting_slot_rejected() -> None:
    snapshot = _final_snapshot()

    snapshot[
        "data"
    ][
        "league"
    ][
        "roster_positions"
    ] = [
        "SUPER_FLEX",
        "BN",
    ]

    with pytest.raises(
        LineupAnalyticsError,
        match="Unsupported",
    ):
        analyze_final_lineup_efficiency(
            snapshot,
            _actuals(),
        )

def test_players_points_fallback_resolves_missing_bulk_actual() -> None:
    snapshot = _final_snapshot()
    snapshot["data"]["teams"][0]["players_points"] = {
        "r2": 20.0,
    }

    actuals = _actuals()
    actuals.pop("r2")

    result = analyze_final_lineup_efficiency(
        snapshot,
        actuals,
    )

    team = result.teams[0]

    assert team.optimization_complete is True
    assert team.optimal_lineup_points == pytest.approx(45.0)
    assert "r2" not in team.unresolved_player_ids
