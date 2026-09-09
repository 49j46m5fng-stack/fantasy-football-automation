"""Deterministic fantasy-football power rankings.

Power rankings combine five independently calculated components:

- season scoring strength
- season all-play strength
- recent schedule-neutral form
- current projection strength
- season lineup efficiency

Each raw component is converted to a within-league percentile from
0 to 100 before the configured weights are applied.

These are analytical power rankings. They are not official Sleeper
standings or playoff seeds.
"""

from dataclasses import dataclass
import math
from typing import Any

from src.standings import (
    SeasonStandings,
    WeeklyLeagueResults,
)


class PowerRankingError(ValueError):
    """Raised when power rankings cannot be calculated safely."""


@dataclass(frozen=True)
class PowerRankingConfig:
    """Validated power-ranking configuration."""

    scoring_strength_weight: float
    all_play_weight: float
    recent_form_weight: float
    projection_strength_weight: float
    lineup_efficiency_weight: float

    recent_form_weeks: int


@dataclass(frozen=True)
class TeamPowerMetrics:
    """Raw power-ranking inputs for one fantasy team."""

    roster_id: int
    manager_name: str

    points_per_game: float
    all_play_percentage: float
    recent_expected_wins: float
    projected_starter_points: float
    lineup_efficiency_pct: float


@dataclass(frozen=True)
class PowerRankingTeam:
    """Completed deterministic power-ranking result."""

    current_rank: int
    previous_rank: int | None
    rank_change: int | None

    roster_id: int
    manager_name: str

    composite_score: float

    points_per_game: float
    scoring_strength_score: float

    all_play_percentage: float
    all_play_score: float

    recent_expected_wins: float
    recent_form_score: float

    projected_starter_points: float
    projection_strength_score: float

    lineup_efficiency_pct: float
    lineup_efficiency_score: float


@dataclass(frozen=True)
class PowerRankings:
    """Power rankings for one league through one completed week."""

    season: str
    league_key: str
    through_week: int

    recent_form_weeks_used: int

    teams: tuple[
        PowerRankingTeam,
        ...,
    ]


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
        raise PowerRankingError(
            f"{description} must be numeric"
        )

    normalized = float(
        value
    )

    if not math.isfinite(
        normalized
    ):
        raise PowerRankingError(
            f"{description} must be finite"
        )

    return normalized


def load_power_ranking_config(
    project_config: dict[str, Any],
) -> PowerRankingConfig:
    """Read and validate power-ranking settings from config.json."""

    try:
        analytics = (
            project_config[
                "analytics"
            ]
        )

        settings = (
            analytics[
                "power_rankings"
            ]
        )

    except (
        KeyError,
        TypeError,
    ) as exc:
        raise PowerRankingError(
            "Missing analytics.power_rankings configuration"
        ) from exc

    if not isinstance(
        settings,
        dict,
    ):
        raise PowerRankingError(
            "analytics.power_rankings must be an object"
        )

    weight_names = (
        "scoring_strength_weight",
        "all_play_weight",
        "recent_form_weight",
        "projection_strength_weight",
        "lineup_efficiency_weight",
    )

    weights: dict[
        str,
        float,
    ] = {}

    for name in weight_names:
        if name not in settings:
            raise PowerRankingError(
                f"Missing power-ranking setting {name}"
            )

        weight = _finite_number(
            settings[
                name
            ],
            name,
        )

        if weight < 0:
            raise PowerRankingError(
                f"{name} cannot be negative"
            )

        weights[
            name
        ] = weight

    total_weight = sum(
        weights.values()
    )

    if not math.isclose(
        total_weight,
        1.0,
        abs_tol=1e-9,
        rel_tol=0.0,
    ):
        raise PowerRankingError(
            "Power-ranking weights must sum to 1.0"
        )

    recent_form_weeks = (
        settings.get(
            "recent_form_weeks"
        )
    )

    if (
        isinstance(
            recent_form_weeks,
            bool,
        )
        or not isinstance(
            recent_form_weeks,
            int,
        )
        or recent_form_weeks < 1
    ):
        raise PowerRankingError(
            "recent_form_weeks must be "
            "a positive integer"
        )

    return PowerRankingConfig(
        scoring_strength_weight=(
            weights[
                "scoring_strength_weight"
            ]
        ),
        all_play_weight=(
            weights[
                "all_play_weight"
            ]
        ),
        recent_form_weight=(
            weights[
                "recent_form_weight"
            ]
        ),
        projection_strength_weight=(
            weights[
                "projection_strength_weight"
            ]
        ),
        lineup_efficiency_weight=(
            weights[
                "lineup_efficiency_weight"
            ]
        ),
        recent_form_weeks=(
            recent_form_weeks
        ),
    )


def _percentile_scores(
    values: dict[
        int,
        float,
    ],
) -> dict[
    int,
    float,
]:
    """Convert raw values into tie-aware 0-100 league percentiles."""

    if len(
        values
    ) < 2:
        raise PowerRankingError(
            "Power rankings require at least two teams"
        )

    ordered = sorted(
        values.items(),
        key=lambda item: (
            item[1],
            item[0],
        ),
    )

    team_count = len(
        ordered
    )

    result: dict[
        int,
        float,
    ] = {}

    index = 0

    while (
        index
        < team_count
    ):
        value = ordered[
            index
        ][1]

        end = (
            index
            + 1
        )

        while (
            end
            < team_count
            and math.isclose(
                ordered[
                    end
                ][1],
                value,
                abs_tol=1e-9,
                rel_tol=0.0,
            )
        ):
            end += 1

        first_rank = (
            index
            + 1
        )

        last_rank = end

        average_rank = (
            first_rank
            + last_rank
        ) / 2.0

        percentile = (
            (
                average_rank
                - 1.0
            )
            / (
                team_count
                - 1
            )
            * 100.0
        )

        for tied_index in range(
            index,
            end,
        ):
            roster_id = (
                ordered[
                    tied_index
                ][0]
            )

            result[
                roster_id
            ] = round(
                percentile,
                8,
            )

        index = end

    return result


def calculate_recent_form(
    weekly_results: list[
        WeeklyLeagueResults
    ],
    recent_form_weeks: int,
) -> tuple[
    dict[
        int,
        float,
    ],
    int,
]:
    """Calculate average weekly expected wins over recent completed weeks."""

    if (
        not isinstance(
            recent_form_weeks,
            int,
        )
        or isinstance(
            recent_form_weeks,
            bool,
        )
        or recent_form_weeks < 1
    ):
        raise PowerRankingError(
            "recent_form_weeks must be "
            "a positive integer"
        )

    if not weekly_results:
        raise PowerRankingError(
            "At least one weekly result is required"
        )

    ordered = sorted(
        weekly_results,
        key=lambda result: (
            result.week
        ),
    )

    reference = (
        ordered[0]
    )

    seen_weeks: set[
        int
    ] = set()

    reference_rosters = {
        team.roster_id
        for team
        in reference.teams
    }

    for weekly in ordered:
        if (
            weekly.season
            != reference.season
        ):
            raise PowerRankingError(
                "Recent-form weeks span multiple seasons"
            )

        if (
            weekly.league_key
            != reference.league_key
        ):
            raise PowerRankingError(
                "Recent-form weeks span multiple leagues"
            )

        if weekly.week in seen_weeks:
            raise PowerRankingError(
                f"Duplicate recent-form week {weekly.week}"
            )

        seen_weeks.add(
            weekly.week
        )

        roster_ids = {
            team.roster_id
            for team
            in weekly.teams
        }

        if (
            roster_ids
            != reference_rosters
        ):
            raise PowerRankingError(
                "Roster set changed across "
                "recent-form weeks"
            )

    selected = ordered[
        -recent_form_weeks:
    ]

    totals = {
        roster_id: 0.0
        for roster_id
        in reference_rosters
    }

    for weekly in selected:
        for team in weekly.teams:
            totals[
                team.roster_id
            ] += (
                team.expected_wins
            )

    weeks_used = len(
        selected
    )

    averages = {
        roster_id: round(
            total
            / float(
                weeks_used
            ),
            8,
        )
        for (
            roster_id,
            total,
        )
        in totals.items()
    }

    return (
        averages,
        weeks_used,
    )


def build_team_power_metrics(
    standings: SeasonStandings,
    weekly_results: list[
        WeeklyLeagueResults
    ],
    projected_starter_points: dict[
        int,
        float,
    ],
    lineup_efficiency_pct: dict[
        int,
        float,
    ],
    ranking_config: PowerRankingConfig,
) -> tuple[
    tuple[
        TeamPowerMetrics,
        ...,
    ],
    int,
]:
    """Build raw power-ranking metrics from deterministic analytics."""

    if not standings.teams:
        raise PowerRankingError(
            "Season standings contain no teams"
        )

    recent_form, weeks_used = (
        calculate_recent_form(
            weekly_results,
            ranking_config.recent_form_weeks,
        )
    )

    standings_rosters = {
        team.roster_id
        for team
        in standings.teams
    }

    if (
        set(
            recent_form
        )
        != standings_rosters
    ):
        raise PowerRankingError(
            "Recent-form roster set does not "
            "match season standings"
        )

    if (
        set(
            projected_starter_points
        )
        != standings_rosters
    ):
        raise PowerRankingError(
            "Projection-strength roster set does "
            "not match season standings"
        )

    if (
        set(
            lineup_efficiency_pct
        )
        != standings_rosters
    ):
        raise PowerRankingError(
            "Lineup-efficiency roster set does "
            "not match season standings"
        )

    latest_week = max(
        weekly.week
        for weekly
        in weekly_results
    )

    if (
        latest_week
        != standings.through_week
    ):
        raise PowerRankingError(
            "Latest weekly result does not match "
            "standings through_week"
        )

    results: list[
        TeamPowerMetrics
    ] = []

    for team in standings.teams:
        if team.games < 1:
            raise PowerRankingError(
                f"Roster {team.roster_id} "
                "has no completed games"
            )

        points_per_game = (
            team.points_for
            / float(
                team.games
            )
        )

        projection = _finite_number(
            projected_starter_points[
                team.roster_id
            ],
            (
                f"Roster {team.roster_id} "
                "projected starter points"
            ),
        )

        efficiency = _finite_number(
            lineup_efficiency_pct[
                team.roster_id
            ],
            (
                f"Roster {team.roster_id} "
                "lineup efficiency"
            ),
        )

        results.append(
            TeamPowerMetrics(
                roster_id=(
                    team.roster_id
                ),
                manager_name=(
                    team.manager_name
                ),
                points_per_game=round(
                    points_per_game,
                    8,
                ),
                all_play_percentage=(
                    team.all_play_percentage
                ),
                recent_expected_wins=(
                    recent_form[
                        team.roster_id
                    ]
                ),
                projected_starter_points=(
                    projection
                ),
                lineup_efficiency_pct=(
                    efficiency
                ),
            )
        )

    return (
        tuple(
            results
        ),
        weeks_used,
    )


def calculate_power_rankings(
    season: str,
    league_key: str,
    through_week: int,
    metrics: tuple[
        TeamPowerMetrics,
        ...,
    ],
    ranking_config: PowerRankingConfig,
    recent_form_weeks_used: int,
    previous_ranks: dict[
        int,
        int,
    ] | None = None,
) -> PowerRankings:
    """Calculate deterministic composite power rankings."""

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise PowerRankingError(
            "season must be a non-empty string"
        )

    if (
        not isinstance(
            league_key,
            str,
        )
        or not league_key
    ):
        raise PowerRankingError(
            "league_key must be a non-empty string"
        )

    if (
        not isinstance(
            through_week,
            int,
        )
        or through_week < 1
    ):
        raise PowerRankingError(
            "through_week must be a positive integer"
        )

    if len(
        metrics
    ) < 2:
        raise PowerRankingError(
            "At least two teams are required"
        )

    roster_ids: set[
        int
    ] = set()

    normalized_metrics: list[
        TeamPowerMetrics
    ] = []

    for team in metrics:
        if (
            team.roster_id
            in roster_ids
        ):
            raise PowerRankingError(
                f"Duplicate roster {team.roster_id}"
            )

        roster_ids.add(
            team.roster_id
        )

        if (
            not isinstance(
                team.manager_name,
                str,
            )
            or not team.manager_name
        ):
            raise PowerRankingError(
                f"Roster {team.roster_id} "
                "must have a manager name"
            )

        normalized_metrics.append(
            TeamPowerMetrics(
                roster_id=(
                    team.roster_id
                ),
                manager_name=(
                    team.manager_name
                ),
                points_per_game=(
                    _finite_number(
                        team.points_per_game,
                        "points_per_game",
                    )
                ),
                all_play_percentage=(
                    _finite_number(
                        team.all_play_percentage,
                        "all_play_percentage",
                    )
                ),
                recent_expected_wins=(
                    _finite_number(
                        team.recent_expected_wins,
                        "recent_expected_wins",
                    )
                ),
                projected_starter_points=(
                    _finite_number(
                        team.projected_starter_points,
                        "projected_starter_points",
                    )
                ),
                lineup_efficiency_pct=(
                    _finite_number(
                        team.lineup_efficiency_pct,
                        "lineup_efficiency_pct",
                    )
                ),
            )
        )

    if previous_ranks is not None:
        unknown_previous = (
            set(
                previous_ranks
            )
            - roster_ids
        )

        if unknown_previous:
            raise PowerRankingError(
                "Previous rankings contain "
                "unknown roster IDs"
            )

        previous_values = list(
            previous_ranks.values()
        )

        if any(
            (
                isinstance(
                    rank,
                    bool,
                )
                or not isinstance(
                    rank,
                    int,
                )
                or rank < 1
            )
            for rank
            in previous_values
        ):
            raise PowerRankingError(
                "Previous ranks must be "
                "positive integers"
            )

        if (
            len(
                previous_values
            )
            != len(
                set(
                    previous_values
                )
            )
        ):
            raise PowerRankingError(
                "Previous ranks must be unique"
            )

    scoring_scores = (
        _percentile_scores(
            {
                team.roster_id: (
                    team.points_per_game
                )
                for team
                in normalized_metrics
            }
        )
    )

    all_play_scores = (
        _percentile_scores(
            {
                team.roster_id: (
                    team.all_play_percentage
                )
                for team
                in normalized_metrics
            }
        )
    )

    recent_form_scores = (
        _percentile_scores(
            {
                team.roster_id: (
                    team.recent_expected_wins
                )
                for team
                in normalized_metrics
            }
        )
    )

    projection_scores = (
        _percentile_scores(
            {
                team.roster_id: (
                    team.projected_starter_points
                )
                for team
                in normalized_metrics
            }
        )
    )

    efficiency_scores = (
        _percentile_scores(
            {
                team.roster_id: (
                    team.lineup_efficiency_pct
                )
                for team
                in normalized_metrics
            }
        )
    )

    unranked: list[
        dict[str, Any]
    ] = []

    for team in (
        normalized_metrics
    ):
        roster_id = (
            team.roster_id
        )

        composite = (
            scoring_scores[
                roster_id
            ]
            * ranking_config
            .scoring_strength_weight
            + all_play_scores[
                roster_id
            ]
            * ranking_config
            .all_play_weight
            + recent_form_scores[
                roster_id
            ]
            * ranking_config
            .recent_form_weight
            + projection_scores[
                roster_id
            ]
            * ranking_config
            .projection_strength_weight
            + efficiency_scores[
                roster_id
            ]
            * ranking_config
            .lineup_efficiency_weight
        )

        unranked.append(
            {
                "team": team,
                "composite": round(
                    composite,
                    8,
                ),
            }
        )

    ordered = sorted(
        unranked,
        key=lambda item: (
            -item[
                "composite"
            ],
            -item[
                "team"
            ].points_per_game,
            -item[
                "team"
            ].all_play_percentage,
            item[
                "team"
            ].roster_id,
        ),
    )

    ranked: list[
        PowerRankingTeam
    ] = []

    for current_rank, item in (
        enumerate(
            ordered,
            start=1,
        )
    ):
        team = item[
            "team"
        ]

        previous_rank = (
            previous_ranks.get(
                team.roster_id
            )
            if previous_ranks
            is not None
            else None
        )

        rank_change = (
            (
                previous_rank
                - current_rank
            )
            if previous_rank
            is not None
            else None
        )

        ranked.append(
            PowerRankingTeam(
                current_rank=(
                    current_rank
                ),
                previous_rank=(
                    previous_rank
                ),
                rank_change=(
                    rank_change
                ),
                roster_id=(
                    team.roster_id
                ),
                manager_name=(
                    team.manager_name
                ),
                composite_score=(
                    item[
                        "composite"
                    ]
                ),
                points_per_game=(
                    team.points_per_game
                ),
                scoring_strength_score=(
                    scoring_scores[
                        team.roster_id
                    ]
                ),
                all_play_percentage=(
                    team.all_play_percentage
                ),
                all_play_score=(
                    all_play_scores[
                        team.roster_id
                    ]
                ),
                recent_expected_wins=(
                    team.recent_expected_wins
                ),
                recent_form_score=(
                    recent_form_scores[
                        team.roster_id
                    ]
                ),
                projected_starter_points=(
                    team.projected_starter_points
                ),
                projection_strength_score=(
                    projection_scores[
                        team.roster_id
                    ]
                ),
                lineup_efficiency_pct=(
                    team.lineup_efficiency_pct
                ),
                lineup_efficiency_score=(
                    efficiency_scores[
                        team.roster_id
                    ]
                ),
            )
        )

    return PowerRankings(
        season=season,
        league_key=league_key,
        through_week=through_week,
        recent_form_weeks_used=(
            recent_form_weeks_used
        ),
        teams=tuple(
            ranked
        ),
    )


def build_power_rankings(
    standings: SeasonStandings,
    weekly_results: list[
        WeeklyLeagueResults
    ],
    projected_starter_points: dict[
        int,
        float,
    ],
    lineup_efficiency_pct: dict[
        int,
        float,
    ],
    project_config: dict[str, Any],
    previous_ranks: dict[
        int,
        int,
    ] | None = None,
) -> PowerRankings:
    """Build power rankings from deterministic upstream analytics."""

    ranking_config = (
        load_power_ranking_config(
            project_config
        )
    )

    (
        metrics,
        weeks_used,
    ) = (
        build_team_power_metrics(
            standings=standings,
            weekly_results=(
                weekly_results
            ),
            projected_starter_points=(
                projected_starter_points
            ),
            lineup_efficiency_pct=(
                lineup_efficiency_pct
            ),
            ranking_config=(
                ranking_config
            ),
        )
    )

    return calculate_power_rankings(
        season=(
            standings.season
        ),
        league_key=(
            standings.league_key
            
        ),
        through_week=(
            standings.through_week
        ),
        metrics=metrics,
        ranking_config=(
            ranking_config
        ),
        recent_form_weeks_used=(
            weeks_used
        ),
        previous_ranks=(
            previous_ranks
        ),
    )