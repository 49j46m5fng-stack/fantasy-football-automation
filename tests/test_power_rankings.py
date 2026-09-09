import pytest

from src.power_rankings import (
    PowerRankingConfig,
    PowerRankingError,
    TeamPowerMetrics,
    build_power_rankings,
    calculate_power_rankings,
    calculate_recent_form,
    load_power_ranking_config,
)
from src.standings import (
    ScheduledMatchup,
    TeamWeekScore,
    aggregate_season_standings,
    calculate_weekly_results,
)


def _project_config() -> dict:
    return {
        "analytics": {
            "power_rankings": {
                "scoring_strength_weight": 0.30,
                "all_play_weight": 0.25,
                "recent_form_weight": 0.20,
                "projection_strength_weight": 0.15,
                "lineup_efficiency_weight": 0.10,
                "recent_form_weeks": 3,
            }
        }
    }


def _ranking_config() -> PowerRankingConfig:
    return (
        load_power_ranking_config(
            _project_config()
        )
    )


def _ordered_metrics():
    return (
        TeamPowerMetrics(
            roster_id=1,
            manager_name="A",
            points_per_game=130.0,
            all_play_percentage=0.90,
            recent_expected_wins=0.90,
            projected_starter_points=125.0,
            lineup_efficiency_pct=96.0,
        ),
        TeamPowerMetrics(
            roster_id=2,
            manager_name="B",
            points_per_game=120.0,
            all_play_percentage=0.70,
            recent_expected_wins=0.70,
            projected_starter_points=118.0,
            lineup_efficiency_pct=92.0,
        ),
        TeamPowerMetrics(
            roster_id=3,
            manager_name="C",
            points_per_game=110.0,
            all_play_percentage=0.40,
            recent_expected_wins=0.40,
            projected_starter_points=110.0,
            lineup_efficiency_pct=88.0,
        ),
        TeamPowerMetrics(
            roster_id=4,
            manager_name="D",
            points_per_game=100.0,
            all_play_percentage=0.10,
            recent_expected_wins=0.10,
            projected_starter_points=100.0,
            lineup_efficiency_pct=80.0,
        ),
    )


def _weeks():
    week_one = (
        calculate_weekly_results(
            season="2026",
            week=1,
            league_key="goats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    120.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    110.0,
                ),
                TeamWeekScore(
                    3,
                    "C",
                    100.0,
                ),
                TeamWeekScore(
                    4,
                    "D",
                    90.0,
                ),
            ],
            matchups=[
                ScheduledMatchup(
                    1,
                    2,
                ),
                ScheduledMatchup(
                    3,
                    4,
                ),
            ],
        )
    )

    week_two = (
        calculate_weekly_results(
            season="2026",
            week=2,
            league_key="goats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    80.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    130.0,
                ),
                TeamWeekScore(
                    3,
                    "C",
                    120.0,
                ),
                TeamWeekScore(
                    4,
                    "D",
                    110.0,
                ),
            ],
            matchups=[
                ScheduledMatchup(
                    1,
                    4,
                ),
                ScheduledMatchup(
                    2,
                    3,
                ),
            ],
        )
    )

    week_three = (
        calculate_weekly_results(
            season="2026",
            week=3,
            league_key="goats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    125.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    100.0,
                ),
                TeamWeekScore(
                    3,
                    "C",
                    115.0,
                ),
                TeamWeekScore(
                    4,
                    "D",
                    90.0,
                ),
            ],
            matchups=[
                ScheduledMatchup(
                    1,
                    3,
                ),
                ScheduledMatchup(
                    2,
                    4,
                ),
            ],
        )
    )

    return [
        week_one,
        week_two,
        week_three,
    ]


def test_config_loads() -> None:
    config = _ranking_config()

    assert (
        config.scoring_strength_weight
        == pytest.approx(
            0.30
        )
    )

    assert (
        config.recent_form_weeks
        == 3
    )


def test_weights_must_sum_to_one() -> None:
    config = _project_config()

    config[
        "analytics"
    ][
        "power_rankings"
    ][
        "scoring_strength_weight"
    ] = 0.50

    with pytest.raises(
        PowerRankingError,
        match="sum to 1.0",
    ):
        load_power_ranking_config(
            config
        )


def test_stronger_team_ranks_first() -> None:
    result = (
        calculate_power_rankings(
            season="2026",
            league_key="goats",
            through_week=3,
            metrics=(
                _ordered_metrics()
            ),
            ranking_config=(
                _ranking_config()
            ),
            recent_form_weeks_used=3,
        )
    )

    assert [
        team.roster_id
        for team
        in result.teams
    ] == [
        1,
        2,
        3,
        4,
    ]


def test_best_team_scores_100_in_each_component() -> None:
    result = (
        calculate_power_rankings(
            season="2026",
            league_key="goats",
            through_week=3,
            metrics=(
                _ordered_metrics()
            ),
            ranking_config=(
                _ranking_config()
            ),
            recent_form_weeks_used=3,
        )
    )

    best = (
        result.teams[0]
    )

    assert (
        best.scoring_strength_score
        == pytest.approx(
            100.0
        )
    )

    assert (
        best.all_play_score
        == pytest.approx(
            100.0
        )
    )

    assert (
        best.recent_form_score
        == pytest.approx(
            100.0
        )
    )

    assert (
        best.projection_strength_score
        == pytest.approx(
            100.0
        )
    )

    assert (
        best.lineup_efficiency_score
        == pytest.approx(
            100.0
        )
    )


def test_equal_metrics_receive_equal_percentiles() -> None:
    metrics = (
        TeamPowerMetrics(
            1,
            "A",
            100.0,
            0.5,
            0.5,
            100.0,
            90.0,
        ),
        TeamPowerMetrics(
            2,
            "B",
            100.0,
            0.5,
            0.5,
            100.0,
            90.0,
        ),
        TeamPowerMetrics(
            3,
            "C",
            100.0,
            0.5,
            0.5,
            100.0,
            90.0,
        ),
        TeamPowerMetrics(
            4,
            "D",
            100.0,
            0.5,
            0.5,
            100.0,
            90.0,
        ),
    )

    result = (
        calculate_power_rankings(
            season="2026",
            league_key="goats",
            through_week=1,
            metrics=metrics,
            ranking_config=(
                _ranking_config()
            ),
            recent_form_weeks_used=1,
        )
    )

    for team in result.teams:
        assert (
            team.composite_score
            == pytest.approx(
                50.0
            )
        )


def test_rank_change_positive_means_moved_up() -> None:
    result = (
        calculate_power_rankings(
            season="2026",
            league_key="goats",
            through_week=3,
            metrics=(
                _ordered_metrics()
            ),
            ranking_config=(
                _ranking_config()
            ),
            recent_form_weeks_used=3,
            previous_ranks={
                1: 3,
                2: 1,
                3: 2,
                4: 4,
            },
        )
    )

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1].rank_change
        == 2
    )

    assert (
        teams[2].rank_change
        == -1
    )


def test_recent_form_uses_latest_requested_weeks() -> None:
    recent, weeks_used = (
        calculate_recent_form(
            _weeks(),
            recent_form_weeks=2,
        )
    )

    assert (
        weeks_used
        == 2
    )

    # Team 1:
    # Week 2 was lowest score -> 0 expected wins
    # Week 3 was highest score -> 1 expected win
    assert (
        recent[1]
        == pytest.approx(
            0.5
        )
    )


def test_recent_form_uses_available_weeks_early_season() -> None:
    recent, weeks_used = (
        calculate_recent_form(
            _weeks()[:2],
            recent_form_weeks=3,
        )
    )

    assert (
        weeks_used
        == 2
    )

    assert set(
        recent
    ) == {
        1,
        2,
        3,
        4,
    }


def test_build_power_rankings_from_standings() -> None:
    weeks = _weeks()

    standings = (
        aggregate_season_standings(
            weeks
        )
    )

    result = (
        build_power_rankings(
            standings=standings,
            weekly_results=weeks,
            projected_starter_points={
                1: 125.0,
                2: 118.0,
                3: 121.0,
                4: 100.0,
            },
            lineup_efficiency_pct={
                1: 95.0,
                2: 90.0,
                3: 92.0,
                4: 85.0,
            },
            project_config=(
                _project_config()
            ),
        )
    )

    assert (
        result.through_week
        == 3
    )

    assert (
        result.recent_form_weeks_used
        == 3
    )

    assert len(
        result.teams
    ) == 4


def test_missing_projection_roster_rejected() -> None:
    weeks = _weeks()

    standings = (
        aggregate_season_standings(
            weeks
        )
    )

    with pytest.raises(
        PowerRankingError,
        match="Projection-strength roster set",
    ):
        build_power_rankings(
            standings=standings,
            weekly_results=weeks,
            projected_starter_points={
                1: 125.0,
                2: 118.0,
                3: 121.0,
            },
            lineup_efficiency_pct={
                1: 95.0,
                2: 90.0,
                3: 92.0,
                4: 85.0,
            },
            project_config=(
                _project_config()
            ),
        )


def test_unknown_previous_rank_roster_rejected() -> None:
    with pytest.raises(
        PowerRankingError,
        match="unknown roster IDs",
    ):
        calculate_power_rankings(
            season="2026",
            league_key="goats",
            through_week=3,
            metrics=(
                _ordered_metrics()
            ),
            ranking_config=(
                _ranking_config()
            ),
            recent_form_weeks_used=3,
            previous_ranks={
                999: 1,
            },
        )