"""Boom/bust analytics against frozen baseline PPR projections.

Boom/bust deliberately compares like with like:

    frozen baseline pts_ppr projection
    vs
    actual Sleeper pts_ppr

Exact league-scored actual points are retained separately for later
analytics but are not used in the boom/bust ratio.
"""

from dataclasses import dataclass
from typing import Any

from src.actuals import (
    PlayerActual,
)


class PerformanceAnalyticsError(ValueError):
    """Raised when performance analytics cannot be calculated safely."""


BOOM = "boom"
NORMAL = "normal"
BUST = "bust"
LOW_PROJECTION = "low_projection"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PerformanceClassification:
    """One projection-vs-actual classification."""

    baseline_projection: float | None
    actual_ppr_points: float | None
    difference: float | None
    ratio: float | None
    classification: str


@dataclass(frozen=True)
class PlayerPerformance:
    """One rostered player's baseline-relative performance."""

    roster_id: int
    manager_name: str

    player_id: str
    player_name: str | None
    position: str | None

    was_baseline_starter: bool

    baseline_projection: float | None

    actual_ppr_points: float | None
    exact_league_points: float | None

    difference: float | None
    ratio: float | None
    classification: str


@dataclass(frozen=True)
class TeamPerformance:
    """Boom/bust summary for one fantasy roster."""

    roster_id: int
    manager_name: str

    baseline_starter_count: int
    resolved_starter_count: int

    boom_count: int
    normal_count: int
    bust_count: int
    low_projection_count: int
    unresolved_count: int

    baseline_starter_actual_ppr_points: float | None
    baseline_starter_exact_points: float | None

    players: tuple[
        PlayerPerformance,
        ...,
    ]


@dataclass(frozen=True)
class WeekPerformance:
    """Boom/bust analytics for one league and week."""

    season: str
    week: int
    league_key: str

    teams: tuple[
        TeamPerformance,
        ...,
    ]


def _optional_number(
    value: Any,
    description: str,
) -> float | None:
    """Normalize an optional numeric value without inventing zero."""

    if value is None:
        return None

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
        raise PerformanceAnalyticsError(
            f"{description} must be numeric or null"
        )

    return float(
        value
    )


def _thresholds(
    analytics_config: dict[str, Any],
) -> tuple[
    float,
    float,
    float,
]:
    """Read and validate boom/bust thresholds."""

    try:
        boom_threshold = float(
            analytics_config[
                "boom_threshold"
            ]
        )

        bust_threshold = float(
            analytics_config[
                "bust_threshold"
            ]
        )

        minimum_projection = float(
            analytics_config[
                "minimum_projection_for_ratio"
            ]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise PerformanceAnalyticsError(
            "Invalid analytics threshold configuration"
        ) from exc

    if boom_threshold <= 0:
        raise PerformanceAnalyticsError(
            "boom_threshold must be positive"
        )

    if bust_threshold <= 0:
        raise PerformanceAnalyticsError(
            "bust_threshold must be positive"
        )

    if (
        boom_threshold
        <= bust_threshold
    ):
        raise PerformanceAnalyticsError(
            "boom_threshold must be greater "
            "than bust_threshold"
        )

    if minimum_projection < 0:
        raise PerformanceAnalyticsError(
            "minimum_projection_for_ratio "
            "cannot be negative"
        )

    return (
        boom_threshold,
        bust_threshold,
        minimum_projection,
    )


def classify_player_performance(
    baseline_projection: Any,
    actual_ppr_points: Any,
    analytics_config: dict[str, Any],
) -> PerformanceClassification:
    """Classify actual PPR performance against frozen PPR projection."""

    projection = (
        _optional_number(
            baseline_projection,
            "baseline_projection",
        )
    )

    actual = (
        _optional_number(
            actual_ppr_points,
            "actual_ppr_points",
        )
    )

    (
        boom_threshold,
        bust_threshold,
        minimum_projection,
    ) = _thresholds(
        analytics_config
    )

    if (
        projection is None
        or actual is None
    ):
        return (
            PerformanceClassification(
                baseline_projection=projection,
                actual_ppr_points=actual,
                difference=None,
                ratio=None,
                classification=(
                    UNRESOLVED
                ),
            )
        )

    difference = (
        actual
        - projection
    )

    if (
        projection
        < minimum_projection
    ):
        return (
            PerformanceClassification(
                baseline_projection=projection,
                actual_ppr_points=actual,
                difference=difference,
                ratio=None,
                classification=(
                    LOW_PROJECTION
                ),
            )
        )

    ratio = (
        actual
        / projection
    )

    if (
        ratio
        >= boom_threshold
    ):
        classification = BOOM

    elif (
        ratio
        >= bust_threshold
    ):
        classification = NORMAL

    else:
        classification = BUST

    return (
        PerformanceClassification(
            baseline_projection=projection,
            actual_ppr_points=actual,
            difference=difference,
            ratio=ratio,
            classification=classification,
        )
    )


def _validate_baseline_identity(
    baseline_snapshot: dict[str, Any],
) -> tuple[
    str,
    int,
    str,
]:
    """Validate baseline identity."""

    if (
        baseline_snapshot.get(
            "stage"
        )
        != "baseline"
    ):
        raise PerformanceAnalyticsError(
            "Performance analytics require "
            "a baseline snapshot"
        )

    season = baseline_snapshot.get(
        "season"
    )

    week = baseline_snapshot.get(
        "week"
    )

    league_key = (
        baseline_snapshot.get(
            "league_key"
        )
    )

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise PerformanceAnalyticsError(
            "Baseline is missing season"
        )

    if not isinstance(
        week,
        int,
    ):
        raise PerformanceAnalyticsError(
            "Baseline is missing week"
        )

    if (
        not isinstance(
            league_key,
            str,
        )
        or not league_key
    ):
        raise PerformanceAnalyticsError(
            "Baseline is missing league_key"
        )

    return (
        season,
        week,
        league_key,
    )


def analyze_baseline_performance(
    baseline_snapshot: dict[str, Any],
    actuals: dict[
        str,
        PlayerActual,
    ],
    analytics_config: dict[str, Any],
) -> WeekPerformance:
    """Analyze frozen baseline roster performance.

    All rostered players are retained in the output.

    Team boom/bust counts include only players who were frozen baseline
    starters.
    """

    (
        season,
        week,
        league_key,
    ) = _validate_baseline_identity(
        baseline_snapshot
    )

    data = baseline_snapshot.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise PerformanceAnalyticsError(
            "Baseline snapshot is missing data"
        )

    teams = data.get(
        "teams"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise PerformanceAnalyticsError(
            "Baseline snapshot is missing teams"
        )

    team_results: list[
        TeamPerformance
    ] = []

    for team in teams:
        if not isinstance(
            team,
            dict,
        ):
            raise PerformanceAnalyticsError(
                "Baseline team must be an object"
            )

        roster_id = team.get(
            "roster_id"
        )

        manager_name = team.get(
            "manager_name"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise PerformanceAnalyticsError(
                "Baseline team is missing roster_id"
            )

        if not isinstance(
            manager_name,
            str,
        ):
            raise PerformanceAnalyticsError(
                f"Roster {roster_id} is "
                "missing manager_name"
            )

        starters = team.get(
            "starters"
        )

        rostered_players = (
            team.get(
                "rostered_players"
            )
        )

        if not isinstance(
            starters,
            list,
        ):
            raise PerformanceAnalyticsError(
                f"Roster {roster_id} starters "
                "must be a list"
            )

        if not isinstance(
            rostered_players,
            list,
        ):
            raise PerformanceAnalyticsError(
                f"Roster {roster_id} "
                "rostered_players must be a list"
            )

        starter_ids: set[
            str
        ] = set()

        for starter in starters:
            if not isinstance(
                starter,
                dict,
            ):
                raise PerformanceAnalyticsError(
                    "Starter record must be an object"
                )

            raw_player_id = (
                starter.get(
                    "player_id"
                )
            )

            if raw_player_id is None:
                continue

            player_id = str(
                raw_player_id
            )

            if (
                not player_id
                or player_id == "0"
            ):
                continue

            starter_ids.add(
                player_id
            )

        seen_player_ids: set[
            str
        ] = set()

        player_results: list[
            PlayerPerformance
        ] = []

        for player in (
            rostered_players
        ):
            if not isinstance(
                player,
                dict,
            ):
                raise PerformanceAnalyticsError(
                    "Rostered player record "
                    "must be an object"
                )

            raw_player_id = (
                player.get(
                    "player_id"
                )
            )

            if raw_player_id is None:
                continue

            player_id = str(
                raw_player_id
            )

            if (
                not player_id
                or player_id == "0"
            ):
                continue

            if (
                player_id
                in seen_player_ids
            ):
                raise PerformanceAnalyticsError(
                    f"Roster {roster_id} contains "
                    f"duplicate player {player_id}"
                )

            seen_player_ids.add(
                player_id
            )

            actual = actuals.get(
                player_id
            )

            if actual is not None:
                if (
                    actual.season
                    != season
                    or actual.week
                    != week
                ):
                    raise PerformanceAnalyticsError(
                        f"Actual score for player "
                        f"{player_id} belongs to "
                        "the wrong season/week"
                    )

                actual_ppr = (
                    actual.ppr_points
                )

                exact_points: (
                    float | None
                ) = (
                    actual.exact_points
                )

            else:
                actual_ppr = None
                exact_points = None

            classified = (
                classify_player_performance(
                    baseline_projection=(
                        player.get(
                            "projected_points"
                        )
                    ),
                    actual_ppr_points=(
                        actual_ppr
                    ),
                    analytics_config=(
                        analytics_config
                    ),
                )
            )

            player_results.append(
                PlayerPerformance(
                    roster_id=roster_id,
                    manager_name=(
                        manager_name
                    ),
                    player_id=player_id,
                    player_name=(
                        player.get(
                            "player_name"
                        )
                    ),
                    position=(
                        player.get(
                            "position"
                        )
                    ),
                    was_baseline_starter=(
                        player_id
                        in starter_ids
                    ),
                    baseline_projection=(
                        classified
                        .baseline_projection
                    ),
                    actual_ppr_points=(
                        classified
                        .actual_ppr_points
                    ),
                    exact_league_points=(
                        exact_points
                    ),
                    difference=(
                        classified
                        .difference
                    ),
                    ratio=(
                        classified
                        .ratio
                    ),
                    classification=(
                        classified
                        .classification
                    ),
                )
            )

        missing_starter_ids = (
            starter_ids
            - seen_player_ids
        )

        if missing_starter_ids:
            raise PerformanceAnalyticsError(
                f"Roster {roster_id} baseline "
                "starter IDs are missing from "
                "rostered_players: "
                f"{sorted(missing_starter_ids)}"
            )

        starter_results = [
            player
            for player
            in player_results
            if player.was_baseline_starter
        ]

        resolved_classifications = [
            player
            for player
            in starter_results
            if (
                player.actual_ppr_points
                is not None
            )
        ]

        if (
            len(
                resolved_classifications
            )
            == len(
                starter_results
            )
        ):
            starter_ppr_total: (
                float | None
            ) = sum(
                player.actual_ppr_points
                or 0.0
                for player
                in starter_results
            )

        else:
            starter_ppr_total = None

        exact_resolved = [
            player
            for player
            in starter_results
            if (
                player.exact_league_points
                is not None
            )
        ]

        if (
            len(
                exact_resolved
            )
            == len(
                starter_results
            )
        ):
            starter_exact_total: (
                float | None
            ) = sum(
                player.exact_league_points
                or 0.0
                for player
                in starter_results
            )

        else:
            starter_exact_total = None

        team_results.append(
            TeamPerformance(
                roster_id=roster_id,
                manager_name=(
                    manager_name
                ),
                baseline_starter_count=(
                    len(
                        starter_results
                    )
                ),
                resolved_starter_count=(
                    len(
                        resolved_classifications
                    )
                ),
                boom_count=sum(
                    1
                    for player
                    in starter_results
                    if (
                        player.classification
                        == BOOM
                    )
                ),
                normal_count=sum(
                    1
                    for player
                    in starter_results
                    if (
                        player.classification
                        == NORMAL
                    )
                ),
                bust_count=sum(
                    1
                    for player
                    in starter_results
                    if (
                        player.classification
                        == BUST
                    )
                ),
                low_projection_count=sum(
                    1
                    for player
                    in starter_results
                    if (
                        player.classification
                        == LOW_PROJECTION
                    )
                ),
                unresolved_count=sum(
                    1
                    for player
                    in starter_results
                    if (
                        player.classification
                        == UNRESOLVED
                    )
                ),
                baseline_starter_actual_ppr_points=(
                    starter_ppr_total
                ),
                baseline_starter_exact_points=(
                    starter_exact_total
                ),
                players=tuple(
                    player_results
                ),
            )
        )

    return (
        WeekPerformance(
            season=season,
            week=week,
            league_key=league_key,
            teams=tuple(
                team_results
            ),
        )
    )