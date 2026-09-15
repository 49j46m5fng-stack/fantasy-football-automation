import pytest

from src.season_analytics import (
    LUCK_LUCKY,
    LUCK_NEUTRAL,
    LUCK_UNLUCKY,
    LuckConfig,
    SeasonAnalyticsError,
    build_luck_tracker,
    build_relegation_watch,
    build_team_simulation_states,
    build_weekly_league_results,
    completed_final_weeks,
    load_luck_config,
)
from src.season_report import (
    generate_season_report_markdown,
)
from src.standings import (
    ScheduledMatchup,
    TeamWeekScore,
    aggregate_season_standings,
    calculate_weekly_results,
)
from src.storage import write_snapshot


def _config() -> LuckConfig:
    return LuckConfig(
        unlucky_threshold=0.5,
        lucky_threshold=0.5,
    )


def _weekly(
    league_key: str,
    week: int,
    scores: list[tuple[int, str, float]],
    matchups: list[tuple[int, int]],
):
    return calculate_weekly_results(
        season="2026",
        week=week,
        league_key=league_key,
        scores=[
            TeamWeekScore(
                roster_id,
                manager_name,
                points,
            )
            for roster_id, manager_name, points in scores
        ],
        matchups=[
            ScheduledMatchup(
                a,
                b,
            )
            for a, b in matchups
        ],
    )


def _two_league_week():
    """GOATs roster 1 scores high but loses to the top scorer."""

    goats = _weekly(
        "goats",
        1,
        [
            (1, "SkolSquad", 145.0),
            (2, "TopScore", 150.0),
            (3, "LowA", 70.0),
            (4, "LowB", 80.0),
        ],
        [
            (1, 2),
            (3, 4),
        ],
    )

    doats = _weekly(
        "doats",
        1,
        [
            (1, "DoatA", 90.0),
            (2, "DoatB", 85.0),
            (3, "DoatC", 60.0),
            (4, "DoatD", 55.0),
        ],
        [
            (1, 2),
            (3, 4),
        ],
    )

    return {
        "goats": [goats],
        "doats": [doats],
    }


# ---------------------------------------------------------------------
# Luck tracker
# ---------------------------------------------------------------------


def test_high_score_that_loses_is_unlucky() -> None:
    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=_two_league_week(),
        config=_config(),
    )

    team = next(
        item
        for item in tracker.weeks[0].teams
        if item.team_key == "goats:1"
    )

    assert team.result == "loss"
    assert team.classification == LUCK_UNLUCKY
    assert team.luck_wins < 0


def test_cross_league_rank_spans_both_leagues() -> None:
    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=_two_league_week(),
        config=_config(),
    )

    team = next(
        item
        for item in tracker.weeks[0].teams
        if item.team_key == "goats:1"
    )

    assert team.cross_league_team_count == 8
    assert team.cross_league_score_rank == 2
    assert team.league_team_count == 4
    assert team.league_score_rank == 2


def test_unlucky_note_states_the_cross_league_placing() -> None:
    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=_two_league_week(),
        config=_config(),
    )

    team = next(
        item
        for item in tracker.weeks[0].teams
        if item.team_key == "goats:1"
    )

    assert "Lost despite scoring 2 of 8" in team.note


def test_low_score_that_wins_is_lucky() -> None:
    """DoatC wins with the 6th-best of 8 scores by drawing the worst team."""

    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=_two_league_week(),
        config=_config(),
    )

    team = next(
        item
        for item in tracker.weeks[0].teams
        if item.team_key == "doats:3"
    )

    assert team.result == "win"
    assert team.classification == LUCK_LUCKY
    assert team.luck_wins > 0
    assert "Won while scoring" in team.note


def test_top_scorer_winning_is_not_lucky() -> None:
    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=_two_league_week(),
        config=_config(),
    )

    team = next(
        item
        for item in tracker.weeks[0].teams
        if item.team_key == "goats:2"
    )

    assert team.result == "win"
    assert team.classification == LUCK_NEUTRAL


def test_tied_scores_share_cross_league_rank() -> None:
    weekly = {
        "goats": [
            _weekly(
                "goats",
                1,
                [
                    (1, "A", 100.0),
                    (2, "B", 100.0),
                    (3, "C", 50.0),
                    (4, "D", 40.0),
                ],
                [
                    (1, 2),
                    (3, 4),
                ],
            )
        ],
    }

    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=weekly,
        config=_config(),
    )

    ranks = {
        team.team_key: (
            team.cross_league_score_rank
        )
        for team in tracker.weeks[0].teams
    }

    assert ranks["goats:1"] == 1
    assert ranks["goats:2"] == 1
    assert ranks["goats:3"] == 3


def test_season_luck_totals_accumulate() -> None:
    weekly = _two_league_week()

    weekly["goats"].append(
        _weekly(
            "goats",
            2,
            [
                (1, "SkolSquad", 140.0),
                (2, "TopScore", 145.0),
                (3, "LowA", 70.0),
                (4, "LowB", 80.0),
            ],
            [
                (1, 2),
                (3, 4),
            ],
        )
    )

    weekly["doats"].append(
        _weekly(
            "doats",
            2,
            [
                (1, "DoatA", 90.0),
                (2, "DoatB", 85.0),
                (3, "DoatC", 60.0),
                (4, "DoatD", 55.0),
            ],
            [
                (1, 2),
                (3, 4),
            ],
        )
    )

    tracker = build_luck_tracker(
        season="2026",
        weekly_by_league=weekly,
        config=_config(),
    )

    team = next(
        item
        for item in tracker.teams
        if item.league_key == "goats"
        and item.roster_id == 1
    )

    assert team.games == 2
    assert team.unlucky_weeks == 2
    assert team.actual_win_equivalent == 0.0
    assert team.luck_wins < -1.0


def test_luck_thresholds_come_from_config() -> None:
    config = load_luck_config(
        {
            "analytics": {
                "luck": {
                    "unlucky_threshold": 0.25,
                    "lucky_threshold": 0.75,
                }
            }
        }
    )

    assert config.unlucky_threshold == 0.25
    assert config.lucky_threshold == 0.75


def test_luck_config_defaults_when_absent() -> None:
    config = load_luck_config(
        {}
    )

    assert config.unlucky_threshold == 0.5
    assert config.lucky_threshold == 0.5


def test_negative_luck_threshold_is_rejected() -> None:
    with pytest.raises(
        SeasonAnalyticsError
    ):
        load_luck_config(
            {
                "analytics": {
                    "luck": {
                        "unlucky_threshold": -1.0,
                    }
                }
            }
        )


# ---------------------------------------------------------------------
# Snapshot integration
# ---------------------------------------------------------------------


def _write_final(
    data_root,
    league_key: str,
    week: int,
    teams: list[tuple[int, str, float | None]],
    matchups: list[tuple[int, int]],
) -> None:
    points = {
        roster_id: value
        for roster_id, _, value in teams
    }

    write_snapshot(
        data_root=data_root,
        season="2026",
        week=week,
        league_key=league_key,
        league_id=f"id-{league_key}",
        stage="final",
        data={
            "final_format_version": 1,
            "teams": [
                {
                    "roster_id": roster_id,
                    "manager_name": manager_name,
                    "effective_final_points": value,
                }
                for roster_id, manager_name, value in teams
            ],
            "matchups": [
                {
                    "matchup_id": index + 1,
                    "roster_a_id": a,
                    "roster_b_id": b,
                    "roster_a_points": points[a],
                    "roster_b_points": points[b],
                    "score_complete": True,
                }
                for index, (a, b) in enumerate(
                    matchups
                )
            ],
        },
    )


def test_completed_weeks_stop_at_first_gap(
    tmp_path,
) -> None:
    data_root = tmp_path / "data"

    for week in (1, 3):
        for league_key in (
            "goats",
            "doats",
        ):
            _write_final(
                data_root,
                league_key,
                week,
                [
                    (1, "A", 100.0),
                    (2, "B", 90.0),
                ],
                [
                    (1, 2),
                ],
            )

    assert completed_final_weeks(
        data_root=data_root,
        season="2026",
        league_keys=(
            "goats",
            "doats",
        ),
        max_week=5,
    ) == (
        1,
    )


def test_missing_final_score_is_rejected(
    tmp_path,
) -> None:
    data_root = tmp_path / "data"

    _write_final(
        data_root,
        "goats",
        1,
        [
            (1, "A", 100.0),
            (2, "B", None),
        ],
        [
            (1, 2),
        ],
    )

    from src.season_analytics import (
        read_final_snapshot,
    )

    snapshot = read_final_snapshot(
        data_root=data_root,
        season="2026",
        league_key="goats",
        week=1,
    )

    with pytest.raises(
        SeasonAnalyticsError
    ):
        build_weekly_league_results(
            snapshot
        )


# ---------------------------------------------------------------------
# Relegation watch and simulation inputs
# ---------------------------------------------------------------------


def _standings():
    return aggregate_season_standings(
        [
            _weekly(
                "goats",
                1,
                [
                    (1, "A", 150.0),
                    (2, "B", 120.0),
                    (3, "C", 90.0),
                    (4, "D", 60.0),
                ],
                [
                    (1, 4),
                    (2, 3),
                ],
            )
        ]
    )


def test_relegation_zone_is_flagged() -> None:
    watch = build_relegation_watch(
        league_key="goats",
        standings=_standings(),
        league_config={
            "relegation_spots": 2,
        },
        simulation=None,
    )

    zone = [
        team
        for team in watch
        if team.in_relegation_zone
    ]

    assert len(zone) == 2
    assert {
        team.analytical_rank
        for team in zone
    } == {
        3,
        4,
    }
    assert all(
        team.warning is not None
        for team in zone
    )


def test_probabilities_are_none_without_simulation() -> None:
    watch = build_relegation_watch(
        league_key="goats",
        standings=_standings(),
        league_config={
            "relegation_spots": 2,
        },
        simulation=None,
    )

    assert all(
        team.relegation_probability is None
        for team in watch
    )


def test_simulation_states_use_completed_scores() -> None:
    standings = _standings()

    states = build_team_simulation_states(
        standings=standings,
        weekly_results=[
            _weekly(
                "goats",
                1,
                [
                    (1, "A", 150.0),
                    (2, "B", 120.0),
                    (3, "C", 90.0),
                    (4, "D", 60.0),
                ],
                [
                    (1, 4),
                    (2, 3),
                ],
            )
        ],
    )

    lookup = {
        state.roster_id: state
        for state in states
    }

    assert lookup[1].mean_points == pytest.approx(
        150.0
    )
    assert lookup[1].stddev_points == pytest.approx(
        0.0
    )
    assert lookup[1].wins == 1


# ---------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------


def test_report_renders_without_optional_analytics() -> None:
    from src.season_analytics import (
        LeagueSeasonAnalytics,
        SeasonAnalytics,
    )

    standings = _standings()

    league = LeagueSeasonAnalytics(
        league_key="goats",
        league_name="GOATs",
        through_week=1,
        weekly_results=(),
        standings=standings,
        power_rankings=None,
        simulation=None,
        watch=build_relegation_watch(
            league_key="goats",
            standings=standings,
            league_config={
                "relegation_spots": 2,
            },
            simulation=None,
        ),
        warnings=(
            "Power rankings unavailable.",
        ),
    )

    analytics = SeasonAnalytics(
        season="2026",
        through_week=1,
        leagues=(
            league,
        ),
        luck=build_luck_tracker(
            season="2026",
            weekly_by_league=_two_league_week(),
            config=_config(),
        ),
        warnings=(),
    )

    markdown = (
        generate_season_report_markdown(
            analytics
        )
    )

    assert "Relegation Warnings" in markdown
    assert "Luck Tracker" in markdown
    assert (
        "Power rankings are not available"
        in markdown
    )
    assert (
        "Season simulations are not available"
        in markdown
    )
    assert "100.0%" in markdown
