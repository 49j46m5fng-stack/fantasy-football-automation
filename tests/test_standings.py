import pytest

from src.standings import (
    ScheduledMatchup,
    StandingsAnalyticsError,
    TeamWeekScore,
    aggregate_season_standings,
    calculate_weekly_results,
)


def _week_one():
    return calculate_weekly_results(
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


def test_weekly_actual_records() -> None:
    result = _week_one()

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert teams[1].win == 1
    assert teams[2].loss == 1
    assert teams[3].win == 1
    assert teams[4].loss == 1


def test_weekly_all_play_records() -> None:
    result = _week_one()

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1].all_play_wins
        == 3
    )

    assert (
        teams[2].all_play_wins
        == 2
    )

    assert (
        teams[3].all_play_wins
        == 1
    )

    assert (
        teams[4].all_play_wins
        == 0
    )


def test_expected_wins() -> None:
    result = _week_one()

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1].expected_wins
        == pytest.approx(
            1.0
        )
    )

    assert (
        teams[2].expected_wins
        == pytest.approx(
            2.0 / 3.0
        )
    )

    assert (
        teams[3].expected_wins
        == pytest.approx(
            1.0 / 3.0
        )
    )

    assert (
        teams[4].expected_wins
        == pytest.approx(
            0.0
        )
    )


def test_luck_wins_detect_schedule_effect() -> None:
    result = _week_one()

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1].luck_wins
        == pytest.approx(
            0.0
        )
    )

    assert (
        teams[2].luck_wins
        == pytest.approx(
            -2.0 / 3.0
        )
    )

    assert (
        teams[3].luck_wins
        == pytest.approx(
            2.0 / 3.0
        )
    )

    assert (
        teams[4].luck_wins
        == pytest.approx(
            0.0
        )
    )


def test_all_play_ties_count_half_expected_win() -> None:
    result = (
        calculate_weekly_results(
            season="2026",
            week=1,
            league_key="doats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    100.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    100.0,
                ),
                TeamWeekScore(
                    3,
                    "C",
                    90.0,
                ),
                TeamWeekScore(
                    4,
                    "D",
                    80.0,
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

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1].all_play_wins
        == 2
    )

    assert (
        teams[1].all_play_ties
        == 1
    )

    assert (
        teams[1].expected_wins
        == pytest.approx(
            2.5 / 3.0
        )
    )

    assert (
        teams[1].actual_win_equivalent
        == pytest.approx(
            0.5
        )
    )


def test_unknown_matchup_roster_rejected() -> None:
    with pytest.raises(
        StandingsAnalyticsError,
        match="unknown roster",
    ):
        calculate_weekly_results(
            season="2026",
            week=1,
            league_key="goats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    100.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    90.0,
                ),
            ],
            matchups=[
                ScheduledMatchup(
                    1,
                    999,
                )
            ],
        )


def test_roster_cannot_appear_twice() -> None:
    with pytest.raises(
        StandingsAnalyticsError,
        match="multiple weekly matchups",
    ):
        calculate_weekly_results(
            season="2026",
            week=1,
            league_key="goats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    100.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    90.0,
                ),
                TeamWeekScore(
                    3,
                    "C",
                    80.0,
                ),
                TeamWeekScore(
                    4,
                    "D",
                    70.0,
                ),
            ],
            matchups=[
                ScheduledMatchup(
                    1,
                    2,
                ),
                ScheduledMatchup(
                    1,
                    3,
                ),
            ],
        )


def test_season_aggregation() -> None:
    week_one = _week_one()

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

    standings = (
        aggregate_season_standings(
            [
                week_one,
                week_two,
            ]
        )
    )

    teams = {
        team.roster_id: team
        for team
        in standings.teams
    }

    assert (
        standings.through_week
        == 2
    )

    assert (
        teams[1].games
        == 2
    )

    assert (
        teams[1].wins
        == 1
    )

    assert (
        teams[1].losses
        == 1
    )

    assert (
        teams[1].points_for
        == pytest.approx(
            200.0
        )
    )


def test_analytical_rank_uses_record_then_points() -> None:
    standings = (
        aggregate_season_standings(
            [
                _week_one()
            ]
        )
    )

    ranks = {
        team.roster_id: (
            team.analytical_rank
        )
        for team
        in standings.teams
    }

    # Rosters 1 and 3 both won.
    # Roster 1 scored more points.
    assert ranks[1] == 1
    assert ranks[3] == 2


def test_duplicate_completed_week_rejected() -> None:
    week = _week_one()

    with pytest.raises(
        StandingsAnalyticsError,
        match="Duplicate completed week",
    ):
        aggregate_season_standings(
            [
                week,
                week,
            ]
        )


def test_roster_set_change_rejected() -> None:
    week_one = _week_one()

    week_two = (
        calculate_weekly_results(
            season="2026",
            week=2,
            league_key="goats",
            scores=[
                TeamWeekScore(
                    1,
                    "A",
                    100.0,
                ),
                TeamWeekScore(
                    2,
                    "B",
                    90.0,
                ),
            ],
            matchups=[
                ScheduledMatchup(
                    1,
                    2,
                )
            ],
        )
    )

    with pytest.raises(
        StandingsAnalyticsError,
        match="roster set changed",
    ):
        aggregate_season_standings(
            [
                week_one,
                week_two,
            ]
        )