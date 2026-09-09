import pytest

from src.actuals import (
    ActualScoringError,
    build_exact_score_lookup,
)
from src.performance import (
    BOOM,
    BUST,
    LOW_PROJECTION,
    NORMAL,
    UNRESOLVED,
    PerformanceAnalyticsError,
    analyze_baseline_performance,
    classify_player_performance,
)
from src.player_stats import (
    PlayerWeekStat,
)
from src.scoring import (
    ScoredPlayerWeek,
)


ANALYTICS = {
    "boom_threshold": 1.5,
    "bust_threshold": 0.8,
    "minimum_projection_for_ratio": 1.0,
}


def test_boom_threshold_is_inclusive() -> None:
    result = (
        classify_player_performance(
            10.0,
            15.0,
            ANALYTICS,
        )
    )

    assert (
        result.classification
        == BOOM
    )

    assert (
        result.ratio
        == pytest.approx(
            1.5
        )
    )


def test_normal_threshold_is_inclusive() -> None:
    result = (
        classify_player_performance(
            10.0,
            8.0,
            ANALYTICS,
        )
    )

    assert (
        result.classification
        == NORMAL
    )


def test_bust_below_threshold() -> None:
    result = (
        classify_player_performance(
            10.0,
            7.9,
            ANALYTICS,
        )
    )

    assert (
        result.classification
        == BUST
    )


def test_low_projection_does_not_use_ratio() -> None:
    result = (
        classify_player_performance(
            0.5,
            10.0,
            ANALYTICS,
        )
    )

    assert (
        result.classification
        == LOW_PROJECTION
    )

    assert result.ratio is None

    assert (
        result.difference
        == pytest.approx(
            9.5
        )
    )


def test_missing_actual_is_unresolved() -> None:
    result = (
        classify_player_performance(
            10.0,
            None,
            ANALYTICS,
        )
    )

    assert (
        result.classification
        == UNRESOLVED
    )

    assert result.ratio is None
    assert result.difference is None


def test_duplicate_actual_records_rejected() -> None:
    records = [
        PlayerWeekStat(
            player_id="a",
            season="2026",
            week=1,
            stats={
                "rec": 1,
            },
        ),
        PlayerWeekStat(
            player_id="a",
            season="2026",
            week=1,
            stats={
                "rec": 2,
            },
        ),
    ]

    with pytest.raises(
        ActualScoringError,
        match="Duplicate",
    ):
        build_exact_score_lookup(
            records,
            {
                "rec": 1.0,
            },
        )


def _baseline() -> dict:
    return {
        "season": "2026",
        "week": 1,
        "league_key": "goats",
        "stage": "baseline",
        "data": {
            "teams": [
                {
                    "roster_id": 1,
                    "manager_name": (
                        "Manager One"
                    ),
                    "starters": [
                        {
                            "player_id": "a",
                        },
                        {
                            "player_id": "b",
                        },
                        {
                            "player_id": None,
                        },
                    ],
                    "rostered_players": [
                        {
                            "player_id": "a",
                            "player_name": (
                                "Player A"
                            ),
                            "position": "RB",
                            "projected_points": 10.0,
                        },
                        {
                            "player_id": "b",
                            "player_name": (
                                "Player B"
                            ),
                            "position": "WR",
                            "projected_points": 10.0,
                        },
                        {
                            "player_id": "c",
                            "player_name": (
                                "Player C"
                            ),
                            "position": "RB",
                            "projected_points": 5.0,
                        },
                    ],
                }
            ]
        },
    }


def _score(
    player_id: str,
    points: float,
) -> ScoredPlayerWeek:
    return ScoredPlayerWeek(
        player_id=player_id,
        season="2026",
        week=1,
        points=points,
        contributions=(),
    )


def test_analyze_baseline_counts_starter_results() -> None:
    result = (
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            exact_scores={
                "a": _score(
                    "a",
                    16.0,
                ),
                "b": _score(
                    "b",
                    5.0,
                ),
                "c": _score(
                    "c",
                    20.0,
                ),
            },
            analytics_config=(
                ANALYTICS
            ),
        )
    )

    team = result.teams[0]

    assert (
        team.baseline_starter_count
        == 2
    )

    assert (
        team.boom_count
        == 1
    )

    assert (
        team.bust_count
        == 1
    )

    assert (
        team.baseline_starter_actual_points
        == pytest.approx(
            21.0
        )
    )


def test_bench_player_is_classified_but_not_counted_as_starter() -> None:
    result = (
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            exact_scores={
                "a": _score(
                    "a",
                    10.0,
                ),
                "b": _score(
                    "b",
                    10.0,
                ),
                "c": _score(
                    "c",
                    20.0,
                ),
            },
            analytics_config=(
                ANALYTICS
            ),
        )
    )

    team = result.teams[0]

    bench = [
        player
        for player
        in team.players
        if player.player_id == "c"
    ][0]

    assert (
        bench.was_baseline_starter
        is False
    )

    assert (
        bench.classification
        == BOOM
    )

    assert team.boom_count == 0


def test_missing_actual_prevents_starter_total() -> None:
    result = (
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            exact_scores={
                "a": _score(
                    "a",
                    10.0,
                )
            },
            analytics_config=(
                ANALYTICS
            ),
        )
    )

    team = result.teams[0]

    assert (
        team.resolved_starter_count
        == 1
    )

    assert (
        team.unresolved_count
        == 1
    )

    assert (
        team.baseline_starter_actual_points
        is None
    )


def test_wrong_actual_week_is_rejected() -> None:
    wrong = ScoredPlayerWeek(
        player_id="a",
        season="2026",
        week=2,
        points=10.0,
        contributions=(),
    )

    with pytest.raises(
        PerformanceAnalyticsError,
        match="wrong season/week",
    ):
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            exact_scores={
                "a": wrong,
            },
            analytics_config=(
                ANALYTICS
            ),
        )


def test_non_baseline_snapshot_rejected() -> None:
    baseline = _baseline()

    baseline[
        "stage"
    ] = "final"

    with pytest.raises(
        PerformanceAnalyticsError,
        match="baseline snapshot",
    ):
        analyze_baseline_performance(
            baseline_snapshot=baseline,
            exact_scores={},
            analytics_config=(
                ANALYTICS
            ),
        )


def test_invalid_projection_rejected() -> None:
    with pytest.raises(
        PerformanceAnalyticsError,
        match="must be numeric",
    ):
        classify_player_performance(
            "10",
            12.0,
            ANALYTICS,
        )