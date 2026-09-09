import pytest

from src.simulation import (
    LeagueSimulationRules,
    RemainingGame,
    SimulationConfig,
    SimulationError,
    TeamSimulationState,
    load_simulation_config,
    simulate_league,
)


def _team(
    roster_id: int,
    wins: int,
    mean: float,
    points_for: float | None = None,
    stddev: float = 0.0,
) -> TeamSimulationState:
    if points_for is None:
        points_for = (
            wins
            * 100.0
        )

    return TeamSimulationState(
        roster_id=roster_id,
        manager_name=(
            f"Team {roster_id}"
        ),
        wins=wins,
        losses=0,
        ties=0,
        points_for=(
            points_for
        ),
        mean_points=mean,
        stddev_points=stddev,
    )


def _four_teams():
    return [
        _team(
            1,
            wins=3,
            mean=120.0,
        ),
        _team(
            2,
            wins=2,
            mean=110.0,
        ),
        _team(
            3,
            wins=1,
            mean=100.0,
        ),
        _team(
            4,
            wins=0,
            mean=90.0,
        ),
    ]


def _config(
    simulations: int = 100,
    seed: int = 2026,
) -> SimulationConfig:
    return SimulationConfig(
        simulations=simulations,
        random_seed=seed,
    )


def test_load_simulation_config() -> None:
    result = (
        load_simulation_config(
            {
                "simulation": {
                    "simulations": 10000,
                    "random_seed": 2026,
                }
            }
        )
    )

    assert (
        result.simulations
        == 10000
    )

    assert (
        result.random_seed
        == 2026
    )


def test_deterministic_playoff_qualification() -> None:
    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=14,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(),
        )
    )

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1].playoff_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        teams[2].playoff_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        teams[3].playoff_probability
        == pytest.approx(
            0.0
        )
    )


def test_deterministic_playoff_title() -> None:
    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=14,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(),
        )
    )

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1]
        .playoff_title_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        teams[2]
        .playoff_runner_up_probability
        == pytest.approx(
            1.0
        )
    )


def test_relegation_uses_regular_season_finish() -> None:
    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=14,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                    relegation_spots=1,
                )
            ),
            config=_config(),
        )
    )

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[4]
        .relegation_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        teams[1]
        .relegation_probability
        == pytest.approx(
            0.0
        )
    )


def test_same_doats_champion_promotes_runner_up() -> None:
    result = (
        simulate_league(
            season="2026",
            league_key="doats",
            through_week=14,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                    regular_season_champion_promoted=True,
                    playoff_champion_promoted=True,
                    if_same_champion_promote_playoff_runner_up=True,
                )
            ),
            config=_config(),
        )
    )

    teams = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        teams[1]
        .promotion_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        teams[2]
        .promotion_probability
        == pytest.approx(
            1.0
        )
    )


def test_different_doats_champions_both_promoted() -> None:
    teams = [
        _team(
            1,
            wins=3,
            mean=100.0,
        ),
        _team(
            2,
            wins=2,
            mean=150.0,
        ),
        _team(
            3,
            wins=1,
            mean=90.0,
        ),
        _team(
            4,
            wins=0,
            mean=80.0,
        ),
    ]

    result = (
        simulate_league(
            season="2026",
            league_key="doats",
            through_week=14,
            teams=teams,
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                    regular_season_champion_promoted=True,
                    playoff_champion_promoted=True,
                    if_same_champion_promote_playoff_runner_up=True,
                )
            ),
            config=_config(),
        )
    )

    by_id = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        by_id[1]
        .regular_season_title_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        by_id[2]
        .playoff_title_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        by_id[1]
        .promotion_probability
        == pytest.approx(
            1.0
        )
    )

    assert (
        by_id[2]
        .promotion_probability
        == pytest.approx(
            1.0
        )
    )


def test_expected_rank_and_wins() -> None:
    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=14,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(),
        )
    )

    by_id = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        by_id[1]
        .expected_regular_season_rank
        == pytest.approx(
            1.0
        )
    )

    assert (
        by_id[1]
        .expected_regular_season_wins
        == pytest.approx(
            3.0
        )
    )

    assert (
        by_id[4]
        .expected_regular_season_rank
        == pytest.approx(
            4.0
        )
    )


def test_fixed_seed_is_reproducible() -> None:
    teams = [
        _team(
            1,
            wins=0,
            mean=100.0,
            stddev=20.0,
        ),
        _team(
            2,
            wins=0,
            mean=100.0,
            stddev=20.0,
        ),
        _team(
            3,
            wins=0,
            mean=100.0,
            stddev=20.0,
        ),
        _team(
            4,
            wins=0,
            mean=100.0,
            stddev=20.0,
        ),
    ]

    schedule = [
        RemainingGame(
            week=1,
            roster_id_1=1,
            roster_id_2=2,
        ),
        RemainingGame(
            week=1,
            roster_id_1=3,
            roster_id_2=4,
        ),
    ]

    first = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=0,
            teams=teams,
            remaining_games=(
                schedule
            ),
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(
                simulations=500,
                seed=123,
            ),
        )
    )

    second = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=0,
            teams=teams,
            remaining_games=(
                schedule
            ),
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(
                simulations=500,
                seed=123,
            ),
        )
    )

    assert first == second


def test_six_team_playoff_bracket_supports_byes() -> None:
    teams = [
        _team(
            1,
            wins=6,
            mean=100.0,
        ),
        _team(
            2,
            wins=5,
            mean=99.0,
        ),
        _team(
            3,
            wins=4,
            mean=98.0,
        ),
        _team(
            4,
            wins=3,
            mean=97.0,
        ),
        _team(
            5,
            wins=2,
            mean=96.0,
        ),
        _team(
            6,
            wins=1,
            mean=200.0,
        ),
    ]

    result = (
        simulate_league(
            season="2026",
            league_key="doats",
            through_week=14,
            teams=teams,
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=6,
                )
            ),
            config=_config(),
        )
    )

    by_id = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        by_id[6]
        .playoff_title_probability
        == pytest.approx(
            1.0
        )
    )


def test_playoff_tie_advances_higher_seed() -> None:
    teams = [
        _team(
            1,
            wins=2,
            mean=100.0,
        ),
        _team(
            2,
            wins=1,
            mean=100.0,
        ),
    ]

    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=14,
            teams=teams,
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(),
        )
    )

    by_id = {
        team.roster_id: team
        for team
        in result.teams
    }

    assert (
        by_id[1]
        .playoff_title_probability
        == pytest.approx(
            1.0
        )
    )


def test_unknown_schedule_roster_rejected() -> None:
    with pytest.raises(
        SimulationError,
        match="unknown roster",
    ):
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=0,
            teams=_four_teams(),
            remaining_games=[
                RemainingGame(
                    week=1,
                    roster_id_1=1,
                    roster_id_2=999,
                )
            ],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(),
        )


def test_team_cannot_play_twice_same_week() -> None:
    with pytest.raises(
        SimulationError,
        match="multiple times",
    ):
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=0,
            teams=_four_teams(),
            remaining_games=[
                RemainingGame(
                    week=1,
                    roster_id_1=1,
                    roster_id_2=2,
                ),
                RemainingGame(
                    week=1,
                    roster_id_1=1,
                    roster_id_2=3,
                ),
            ],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(),
        )


def test_invalid_playoff_count_rejected() -> None:
    with pytest.raises(
        SimulationError,
        match="playoff_teams",
    ):
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=0,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=5,
                )
            ),
            config=_config(),
        )


def test_runner_up_fallback_requires_both_champions() -> None:
    with pytest.raises(
        SimulationError,
        match="Runner-up promotion fallback",
    ):
        simulate_league(
            season="2026",
            league_key="doats",
            through_week=0,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                    regular_season_champion_promoted=True,
                    playoff_champion_promoted=False,
                    if_same_champion_promote_playoff_runner_up=True,
                )
            ),
            config=_config(),
        )


def test_playoff_probability_mass_equals_playoff_spots() -> None:
    teams = [
        _team(
            1,
            wins=0,
            mean=100.0,
            stddev=15.0,
        ),
        _team(
            2,
            wins=0,
            mean=100.0,
            stddev=15.0,
        ),
        _team(
            3,
            wins=0,
            mean=100.0,
            stddev=15.0,
        ),
        _team(
            4,
            wins=0,
            mean=100.0,
            stddev=15.0,
        ),
    ]

    schedule = [
        RemainingGame(
            week=1,
            roster_id_1=1,
            roster_id_2=2,
        ),
        RemainingGame(
            week=1,
            roster_id_1=3,
            roster_id_2=4,
        ),
    ]

    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=0,
            teams=teams,
            remaining_games=schedule,
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                )
            ),
            config=_config(
                simulations=1000,
            ),
        )
    )

    assert sum(
        team.playoff_probability
        for team
        in result.teams
    ) == pytest.approx(
        2.0
    )


def test_relegation_probability_mass_equals_spots() -> None:
    result = (
        simulate_league(
            season="2026",
            league_key="goats",
            through_week=14,
            teams=_four_teams(),
            remaining_games=[],
            rules=(
                LeagueSimulationRules(
                    playoff_teams=2,
                    relegation_spots=1,
                )
            ),
            config=_config(),
        )
    )

    assert sum(
        team.relegation_probability
        for team
        in result.teams
    ) == pytest.approx(
        1.0
    )