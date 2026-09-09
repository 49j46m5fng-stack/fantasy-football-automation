"""Monte Carlo season-outcome simulation.

The simulation engine is intentionally separate from the code that
derives team strength.

Each team must be supplied with:

- current wins/losses/ties
- current points for
- expected weekly fantasy points
- weekly scoring standard deviation

The engine then simulates:

- remaining regular-season games
- final regular-season rank
- playoff qualification
- a fixed seeded playoff bracket
- playoff champion
- playoff runner-up
- promotion
- relegation

Probabilities are empirical Monte Carlo probabilities. Score margins
must never be labeled as probabilities.
"""

from dataclasses import dataclass
import math
import random
from typing import Any


class SimulationError(ValueError):
    """Raised when Monte Carlo simulation inputs are invalid."""


@dataclass(frozen=True)
class SimulationConfig:
    """Validated global simulation configuration."""

    simulations: int
    random_seed: int


@dataclass(frozen=True)
class TeamSimulationState:
    """Current state and weekly scoring model for one fantasy team."""

    roster_id: int
    manager_name: str

    wins: int
    losses: int
    ties: int

    points_for: float

    mean_points: float
    stddev_points: float


@dataclass(frozen=True)
class RemainingGame:
    """One remaining regular-season fantasy matchup."""

    week: int

    roster_id_1: int
    roster_id_2: int


@dataclass(frozen=True)
class LeagueSimulationRules:
    """League-specific simulation rules."""

    playoff_teams: int

    relegation_spots: int = 0

    regular_season_champion_promoted: bool = False
    playoff_champion_promoted: bool = False

    if_same_champion_promote_playoff_runner_up: bool = False


@dataclass(frozen=True)
class TeamSimulationResult:
    """Monte Carlo outcome probabilities for one fantasy team."""

    roster_id: int
    manager_name: str

    playoff_probability: float

    regular_season_title_probability: float
    playoff_title_probability: float
    playoff_runner_up_probability: float

    promotion_probability: float
    relegation_probability: float

    expected_regular_season_rank: float
    expected_regular_season_wins: float


@dataclass(frozen=True)
class LeagueSimulationResult:
    """Monte Carlo results for one fantasy league."""

    season: str
    league_key: str
    through_week: int

    simulations: int
    random_seed: int

    teams: tuple[
        TeamSimulationResult,
        ...,
    ]


@dataclass
class _SeasonRecord:
    """Mutable internal record for one simulation run."""

    wins: int
    losses: int
    ties: int

    points_for: float


@dataclass(frozen=True)
class _BracketEntry:
    """One seeded playoff-bracket entry."""

    roster_id: int
    seed: int


def _finite_number(
    value: Any,
    description: str,
) -> float:
    """Require a finite numeric value."""

    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise SimulationError(
            f"{description} must be numeric"
        )

    normalized = float(
        value
    )

    if not math.isfinite(
        normalized
    ):
        raise SimulationError(
            f"{description} must be finite"
        )

    return normalized


def load_simulation_config(
    project_config: dict[str, Any],
) -> SimulationConfig:
    """Load Monte Carlo count and seed from project configuration."""

    try:
        settings = (
            project_config[
                "simulation"
            ]
        )

    except (
        KeyError,
        TypeError,
    ) as exc:
        raise SimulationError(
            "Missing simulation configuration"
        ) from exc

    if not isinstance(
        settings,
        dict,
    ):
        raise SimulationError(
            "simulation must be an object"
        )

    simulations = settings.get(
        "simulations"
    )

    random_seed = settings.get(
        "random_seed"
    )

    if (
        isinstance(
            simulations,
            bool,
        )
        or not isinstance(
            simulations,
            int,
        )
        or simulations < 1
    ):
        raise SimulationError(
            "simulation.simulations must be "
            "a positive integer"
        )

    if (
        isinstance(
            random_seed,
            bool,
        )
        or not isinstance(
            random_seed,
            int,
        )
    ):
        raise SimulationError(
            "simulation.random_seed must be an integer"
        )

    return SimulationConfig(
        simulations=simulations,
        random_seed=random_seed,
    )


def _validate_team(
    team: TeamSimulationState,
) -> TeamSimulationState:
    """Validate one team simulation state."""

    if not isinstance(
        team.roster_id,
        int,
    ):
        raise SimulationError(
            "roster_id must be an integer"
        )

    if (
        not isinstance(
            team.manager_name,
            str,
        )
        or not team.manager_name
    ):
        raise SimulationError(
            f"Roster {team.roster_id} "
            "must have a manager_name"
        )

    for name, value in (
        (
            "wins",
            team.wins,
        ),
        (
            "losses",
            team.losses,
        ),
        (
            "ties",
            team.ties,
        ),
    ):
        if (
            isinstance(
                value,
                bool,
            )
            or not isinstance(
                value,
                int,
            )
            or value < 0
        ):
            raise SimulationError(
                f"Roster {team.roster_id} "
                f"{name} must be a "
                "non-negative integer"
            )

    points_for = _finite_number(
        team.points_for,
        (
            f"Roster {team.roster_id} "
            "points_for"
        ),
    )

    mean_points = _finite_number(
        team.mean_points,
        (
            f"Roster {team.roster_id} "
            "mean_points"
        ),
    )

    stddev_points = _finite_number(
        team.stddev_points,
        (
            f"Roster {team.roster_id} "
            "stddev_points"
        ),
    )

    if mean_points < 0:
        raise SimulationError(
            f"Roster {team.roster_id} "
            "mean_points cannot be negative"
        )

    if stddev_points < 0:
        raise SimulationError(
            f"Roster {team.roster_id} "
            "stddev_points cannot be negative"
        )

    return TeamSimulationState(
        roster_id=team.roster_id,
        manager_name=team.manager_name,
        wins=team.wins,
        losses=team.losses,
        ties=team.ties,
        points_for=points_for,
        mean_points=mean_points,
        stddev_points=stddev_points,
    )


def _validate_inputs(
    through_week: int,
    teams: list[
        TeamSimulationState
    ],
    remaining_games: list[
        RemainingGame
    ],
    rules: LeagueSimulationRules,
) -> dict[
    int,
    TeamSimulationState,
]:
    """Validate the complete simulation input set."""

    if (
        isinstance(
            through_week,
            bool,
        )
        or not isinstance(
            through_week,
            int,
        )
        or through_week < 0
    ):
        raise SimulationError(
            "through_week must be a "
            "non-negative integer"
        )

    if len(
        teams
    ) < 2:
        raise SimulationError(
            "At least two teams are required"
        )

    lookup: dict[
        int,
        TeamSimulationState,
    ] = {}

    for raw_team in teams:
        team = _validate_team(
            raw_team
        )

        if (
            team.roster_id
            in lookup
        ):
            raise SimulationError(
                f"Duplicate roster "
                f"{team.roster_id}"
            )

        lookup[
            team.roster_id
        ] = team

    if (
        isinstance(
            rules.playoff_teams,
            bool,
        )
        or not isinstance(
            rules.playoff_teams,
            int,
        )
        or rules.playoff_teams < 2
        or rules.playoff_teams
        > len(
            lookup
        )
    ):
        raise SimulationError(
            "playoff_teams must be between "
            "2 and the league team count"
        )

    if (
        isinstance(
            rules.relegation_spots,
            bool,
        )
        or not isinstance(
            rules.relegation_spots,
            int,
        )
        or rules.relegation_spots < 0
    ):
        raise SimulationError(
            "relegation_spots must be "
            "a non-negative integer"
        )

    if (
        rules.playoff_teams
        + rules.relegation_spots
        > len(
            lookup
        )
    ):
        raise SimulationError(
            "playoff teams and relegation "
            "spots cannot overlap"
        )

    if (
        rules
        .if_same_champion_promote_playoff_runner_up
        and not (
            rules
            .regular_season_champion_promoted
            and rules
            .playoff_champion_promoted
        )
    ):
        raise SimulationError(
            "Runner-up promotion fallback requires "
            "both regular-season and playoff "
            "champions to be promotion qualifiers"
        )

    seen_by_week: dict[
        int,
        set[int],
    ] = {}

    for game in remaining_games:
        if (
            isinstance(
                game.week,
                bool,
            )
            or not isinstance(
                game.week,
                int,
            )
            or game.week <= through_week
        ):
            raise SimulationError(
                "Remaining-game week must be "
                "after through_week"
            )

        if (
            not isinstance(
                game.roster_id_1,
                int,
            )
            or not isinstance(
                game.roster_id_2,
                int,
            )
        ):
            raise SimulationError(
                "Remaining-game roster IDs "
                "must be integers"
            )

        if (
            game.roster_id_1
            == game.roster_id_2
        ):
            raise SimulationError(
                f"Roster {game.roster_id_1} "
                "cannot play itself"
            )

        for roster_id in (
            game.roster_id_1,
            game.roster_id_2,
        ):
            if roster_id not in lookup:
                raise SimulationError(
                    "Remaining schedule references "
                    f"unknown roster {roster_id}"
                )

            used = (
                seen_by_week.setdefault(
                    game.week,
                    set(),
                )
            )

            if roster_id in used:
                raise SimulationError(
                    f"Roster {roster_id} appears "
                    f"multiple times in week "
                    f"{game.week}"
                )

            used.add(
                roster_id
            )

    return lookup


def _win_equivalent(
    record: _SeasonRecord,
) -> float:
    """Return wins with ties worth half a win."""

    return (
        float(
            record.wins
        )
        + 0.5
        * float(
            record.ties
        )
    )


def _rank_regular_season(
    records: dict[
        int,
        _SeasonRecord,
    ],
) -> list[int]:
    """Rank simulated regular-season standings.

    Tie-break order:

    1. win equivalent
    2. points for
    3. roster ID
    """

    return sorted(
        records,
        key=lambda roster_id: (
            -_win_equivalent(
                records[
                    roster_id
                ]
            ),
            -records[
                roster_id
            ].points_for,
            roster_id,
        ),
    )


def _draw_score(
    rng: random.Random,
    team: TeamSimulationState,
) -> float:
    """Draw one non-negative simulated weekly fantasy score."""

    score = rng.gauss(
        team.mean_points,
        team.stddev_points,
    )

    return round(
        max(
            0.0,
            score,
        ),
        2,
    )


def _next_power_of_two(
    value: int,
) -> int:
    """Return the next power of two >= value."""

    size = 1

    while size < value:
        size *= 2

    return size


def _bracket_seed_order(
    size: int,
) -> list[int]:
    """Generate a standard fixed seeded bracket order.

    Example for eight seeds:

    1, 8, 4, 5, 2, 7, 3, 6
    """

    if size == 1:
        return [
            1
        ]

    previous = (
        _bracket_seed_order(
            size // 2
        )
    )

    result: list[int] = []

    for seed in previous:
        result.extend(
            [
                seed,
                size + 1 - seed,
            ]
        )

    return result


def _playoff_game_winner(
    left: _BracketEntry,
    right: _BracketEntry,
    team_lookup: dict[
        int,
        TeamSimulationState,
    ],
    rng: random.Random,
) -> tuple[
    _BracketEntry,
    _BracketEntry,
]:
    """Simulate one playoff matchup.

    A tied playoff score advances the higher seed.
    """

    left_score = _draw_score(
        rng,
        team_lookup[
            left.roster_id
        ],
    )

    right_score = _draw_score(
        rng,
        team_lookup[
            right.roster_id
        ],
    )

    if left_score > right_score:
        return (
            left,
            right,
        )

    if right_score > left_score:
        return (
            right,
            left,
        )

    if left.seed < right.seed:
        return (
            left,
            right,
        )

    return (
        right,
        left,
    )


def _simulate_playoff_bracket(
    seeded_roster_ids: list[int],
    team_lookup: dict[
        int,
        TeamSimulationState,
    ],
    rng: random.Random,
) -> tuple[
    int,
    int,
]:
    """Simulate a fixed seeded single-elimination playoff bracket.

    Non-power-of-two playoff sizes receive top-seed byes.

    Examples:

    6 teams:
      1 bye
      4 vs 5
      2 bye
      3 vs 6

    8 teams:
      1 vs 8
      4 vs 5
      2 vs 7
      3 vs 6
    """

    playoff_count = len(
        seeded_roster_ids
    )

    if playoff_count < 2:
        raise SimulationError(
            "At least two playoff teams "
            "are required"
        )

    bracket_size = (
        _next_power_of_two(
            playoff_count
        )
    )

    seed_order = (
        _bracket_seed_order(
            bracket_size
        )
    )

    seed_lookup = {
        seed: (
            _BracketEntry(
                roster_id=roster_id,
                seed=seed,
            )
        )
        for seed, roster_id
        in enumerate(
            seeded_roster_ids,
            start=1,
        )
    }

    round_entries: list[
        _BracketEntry | None
    ] = [
        seed_lookup.get(
            seed
        )
        for seed
        in seed_order
    ]

    runner_up: (
        _BracketEntry | None
    ) = None

    while len(
        round_entries
    ) > 1:
        next_round: list[
            _BracketEntry | None
        ] = []

        is_final = (
            len(
                round_entries
            )
            == 2
        )

        for index in range(
            0,
            len(
                round_entries
            ),
            2,
        ):
            left = (
                round_entries[
                    index
                ]
            )

            right = (
                round_entries[
                    index + 1
                ]
            )

            if (
                left is None
                and right is None
            ):
                next_round.append(
                    None
                )

                continue

            if left is None:
                next_round.append(
                    right
                )

                continue

            if right is None:
                next_round.append(
                    left
                )

                continue

            (
                winner,
                loser,
            ) = (
                _playoff_game_winner(
                    left,
                    right,
                    team_lookup,
                    rng,
                )
            )

            if is_final:
                runner_up = loser

            next_round.append(
                winner
            )

        round_entries = (
            next_round
        )

    champion = (
        round_entries[0]
    )

    if (
        champion is None
        or runner_up is None
    ):
        raise SimulationError(
            "Could not resolve playoff "
            "champion and runner-up"
        )

    return (
        champion.roster_id,
        runner_up.roster_id,
    )


def simulate_league(
    season: str,
    league_key: str,
    through_week: int,
    teams: list[
        TeamSimulationState
    ],
    remaining_games: list[
        RemainingGame
    ],
    rules: LeagueSimulationRules,
    config: SimulationConfig,
) -> LeagueSimulationResult:
    """Run seeded Monte Carlo season simulations."""

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise SimulationError(
            "season must be a non-empty string"
        )

    if (
        not isinstance(
            league_key,
            str,
        )
        or not league_key
    ):
        raise SimulationError(
            "league_key must be a non-empty string"
        )

    if (
        isinstance(
            config.simulations,
            bool,
        )
        or not isinstance(
            config.simulations,
            int,
        )
        or config.simulations < 1
    ):
        raise SimulationError(
            "simulations must be a "
            "positive integer"
        )

    if (
        isinstance(
            config.random_seed,
            bool,
        )
        or not isinstance(
            config.random_seed,
            int,
        )
    ):
        raise SimulationError(
            "random_seed must be an integer"
        )

    team_lookup = (
        _validate_inputs(
            through_week=through_week,
            teams=teams,
            remaining_games=(
                remaining_games
            ),
            rules=rules,
        )
    )

    rng = random.Random(
        config.random_seed
    )

    roster_ids = sorted(
        team_lookup
    )

    playoff_counts = {
        roster_id: 0
        for roster_id
        in roster_ids
    }

    regular_title_counts = {
        roster_id: 0
        for roster_id
        in roster_ids
    }

    playoff_title_counts = {
        roster_id: 0
        for roster_id
        in roster_ids
    }

    playoff_runner_up_counts = {
        roster_id: 0
        for roster_id
        in roster_ids
    }

    promotion_counts = {
        roster_id: 0
        for roster_id
        in roster_ids
    }

    relegation_counts = {
        roster_id: 0
        for roster_id
        in roster_ids
    }

    rank_sums = {
        roster_id: 0.0
        for roster_id
        in roster_ids
    }

    win_sums = {
        roster_id: 0.0
        for roster_id
        in roster_ids
    }

    ordered_schedule = sorted(
        remaining_games,
        key=lambda game: (
            game.week,
            game.roster_id_1,
            game.roster_id_2,
        ),
    )

    for _ in range(
        config.simulations
    ):
        records = {
            roster_id: (
                _SeasonRecord(
                    wins=(
                        team_lookup[
                            roster_id
                        ].wins
                    ),
                    losses=(
                        team_lookup[
                            roster_id
                        ].losses
                    ),
                    ties=(
                        team_lookup[
                            roster_id
                        ].ties
                    ),
                    points_for=(
                        team_lookup[
                            roster_id
                        ].points_for
                    ),
                )
            )
            for roster_id
            in roster_ids
        }

        for game in (
            ordered_schedule
        ):
            team_1 = (
                team_lookup[
                    game.roster_id_1
                ]
            )

            team_2 = (
                team_lookup[
                    game.roster_id_2
                ]
            )

            score_1 = _draw_score(
                rng,
                team_1,
            )

            score_2 = _draw_score(
                rng,
                team_2,
            )

            records[
                team_1.roster_id
            ].points_for += (
                score_1
            )

            records[
                team_2.roster_id
            ].points_for += (
                score_2
            )

            if score_1 > score_2:
                records[
                    team_1.roster_id
                ].wins += 1

                records[
                    team_2.roster_id
                ].losses += 1

            elif score_2 > score_1:
                records[
                    team_2.roster_id
                ].wins += 1

                records[
                    team_1.roster_id
                ].losses += 1

            else:
                records[
                    team_1.roster_id
                ].ties += 1

                records[
                    team_2.roster_id
                ].ties += 1

        ranked = (
            _rank_regular_season(
                records
            )
        )

        regular_champion = (
            ranked[0]
        )

        regular_title_counts[
            regular_champion
        ] += 1

        playoff_rosters = (
            ranked[
                : rules.playoff_teams
            ]
        )

        for roster_id in (
            playoff_rosters
        ):
            playoff_counts[
                roster_id
            ] += 1

        if (
            rules.relegation_spots
            > 0
        ):
            relegated = ranked[
                -rules.relegation_spots:
            ]

            for roster_id in (
                relegated
            ):
                relegation_counts[
                    roster_id
                ] += 1

        (
            playoff_champion,
            playoff_runner_up,
        ) = (
            _simulate_playoff_bracket(
                seeded_roster_ids=(
                    playoff_rosters
                ),
                team_lookup=(
                    team_lookup
                ),
                rng=rng,
            )
        )

        playoff_title_counts[
            playoff_champion
        ] += 1

        playoff_runner_up_counts[
            playoff_runner_up
        ] += 1

        promoted: set[int] = set()

        if (
            rules
            .regular_season_champion_promoted
        ):
            promoted.add(
                regular_champion
            )

        if (
            rules
            .playoff_champion_promoted
        ):
            if (
                playoff_champion
                != regular_champion
                or not rules
                .regular_season_champion_promoted
            ):
                promoted.add(
                    playoff_champion
                )

            elif (
                rules
                .if_same_champion_promote_playoff_runner_up
            ):
                promoted.add(
                    playoff_runner_up
                )

        for roster_id in (
            promoted
        ):
            promotion_counts[
                roster_id
            ] += 1

        for rank, roster_id in (
            enumerate(
                ranked,
                start=1,
            )
        ):
            rank_sums[
                roster_id
            ] += float(
                rank
            )

            win_sums[
                roster_id
            ] += (
                _win_equivalent(
                    records[
                        roster_id
                    ]
                )
            )

    denominator = float(
        config.simulations
    )

    results: list[
        TeamSimulationResult
    ] = []

    for roster_id in (
        roster_ids
    ):
        team = (
            team_lookup[
                roster_id
            ]
        )

        results.append(
            TeamSimulationResult(
                roster_id=roster_id,
                manager_name=(
                    team.manager_name
                ),
                playoff_probability=round(
                    playoff_counts[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                regular_season_title_probability=round(
                    regular_title_counts[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                playoff_title_probability=round(
                    playoff_title_counts[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                playoff_runner_up_probability=round(
                    playoff_runner_up_counts[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                promotion_probability=round(
                    promotion_counts[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                relegation_probability=round(
                    relegation_counts[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                expected_regular_season_rank=round(
                    rank_sums[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
                expected_regular_season_wins=round(
                    win_sums[
                        roster_id
                    ]
                    / denominator,
                    8,
                ),
            )
        )

    return LeagueSimulationResult(
        season=season,
        league_key=league_key,
        through_week=through_week,
        simulations=(
            config.simulations
        ),
        random_seed=(
            config.random_seed
        ),
        teams=tuple(
            results
        ),
    )