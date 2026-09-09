import pytest

from src.actuals import (
    ActualScoringError,
    PlayerActual,
    build_player_actual_lookup,
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


ANALYTICS = {
    "boom_threshold": 1.5,
    "bust_threshold": 0.8,
    "minimum_projection_for_ratio": 1.0,
}


def _actual(
    player_id: str,
    ppr: float | None,
    exact: float,
    week: int = 1,
) -> PlayerActual:
    return PlayerActual(
        player_id=player_id,
        season="2026",
        week=week,
        ppr_points=ppr,
        exact_points=exact,
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


def test_actual_lookup_preserves_ppr_and_exact() -> None:
    lookup = (
        build_player_actual_lookup(
            records=[
                PlayerWeekStat(
                    player_id="a",
                    season="2026",
                    week=1,
                    stats={
                        "rec": 2,
                        "pts_ppr": 2.0,
                    },
                )
            ],
            scoring_settings={
                "rec": 1.0,
            },
        )
    )

    assert (
        lookup["a"].ppr_points
        == 2.0
    )

    assert (
        lookup["a"].exact_points
        == 2.0
    )


def test_actual_lookup_missing_ppr_stays_missing() -> None:
    lookup = (
        build_player_actual_lookup(
            records=[
                PlayerWeekStat(
                    player_id="a",
                    season="2026",
                    week=1,
                    stats={
                        "rush_yd": 0,
                    },
                )
            ],
            scoring_settings={
                "rush_yd": 0.1,
            },
        )
    )

    assert (
        lookup["a"].ppr_points
        is None
    )

    assert (
        lookup["a"].exact_points
        == 0.0
    )


def test_duplicate_actual_records_rejected() -> None:
    records = [
        PlayerWeekStat(
            player_id="a",
            season="2026",
            week=1,
            stats={},
        ),
        PlayerWeekStat(
            player_id="a",
            season="2026",
            week=1,
            stats={},
        ),
    ]

    with pytest.raises(
        ActualScoringError,
        match="Duplicate",
    ):
        build_player_actual_lookup(
            records,
            {},
        )


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


def test_low_projection_avoids_ratio() -> None:
    result = (
        classify_player_performance(
            0.5,
            8.0,
            ANALYTICS,
        )
    )

    assert (
        result.classification
        == LOW_PROJECTION
    )

    assert result.ratio is None


def test_missing_ppr_is_unresolved() -> None:
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


def test_analysis_counts_only_baseline_starters() -> None:
    result = (
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            actuals={
                "a": _actual(
                    "a",
                    16.0,
                    16.0,
                ),
                "b": _actual(
                    "b",
                    5.0,
                    5.0,
                ),
                "c": _actual(
                    "c",
                    20.0,
                    20.0,
                ),
            },
            analytics_config=(
                ANALYTICS
            ),
        )
    )

    team = result.teams[0]

    assert team.boom_count == 1
    assert team.bust_count == 1

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


def test_starter_totals_preserve_both_scoring_channels() -> None:
    result = (
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            actuals={
                "a": _actual(
                    "a",
                    15.0,
                    17.0,
                ),
                "b": _actual(
                    "b",
                    10.0,
                    12.0,
                ),
            },
            analytics_config=(
                ANALYTICS
            ),
        )
    )

    team = result.teams[0]

    assert (
        team.baseline_starter_actual_ppr_points
        == pytest.approx(
            25.0
        )
    )

    assert (
        team.baseline_starter_exact_points
        == pytest.approx(
            29.0
        )
    )


def test_wrong_actual_week_rejected() -> None:
    with pytest.raises(
        PerformanceAnalyticsError,
        match="wrong season/week",
    ):
        analyze_baseline_performance(
            baseline_snapshot=(
                _baseline()
            ),
            actuals={
                "a": _actual(
                    "a",
                    10.0,
                    10.0,
                    week=2,
                )
            },
            analytics_config=(
                ANALYTICS
            ),
        )


def test_non_baseline_snapshot_rejected() -> None:
    snapshot = _baseline()

    snapshot[
        "stage"
    ] = "final"

    with pytest.raises(
        PerformanceAnalyticsError,
        match="baseline snapshot",
    ):
        analyze_baseline_performance(
            baseline_snapshot=(
                snapshot
            ),
            actuals={},
            analytics_config=(
                ANALYTICS
            ),
        )