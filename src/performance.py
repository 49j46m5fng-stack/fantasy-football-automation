"""Player and team performance analytics against frozen baseline projections."""

from dataclasses import dataclass
from typing import Any

from src.scoring import (
    ScoredPlayerWeek,
)


class PerformanceAnalyticsError(ValueError):
    """Raised when performance analytics cannot be calculated safely."""


BOOM = "boom"
NORMAL = "normal"
BUST = "bust"
LOW_PROJECTION = "low_projection"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PlayerPerformance:
    """Actual player performance against the frozen baseline."""

    roster_id: int
    manager_name: str
    player_id: str
    player_name: str | None
    position: str | None
    was_baseline_starter: bool
    baseline_projection: float | None
    actual_points: float | None
    difference: float | None
    ratio: float | None
    classification: str


@dataclass(frozen=True)
class TeamPerformance:
    """Baseline performance summary for one fantasy roster."""

    roster_id: int
    manager_name: str

    baseline_starter_count: int
    resolved_starter_count: int

    boom_count: int
    normal_count: int
    bust_count: int
    low_projection_count: int
    unresolved_count: int

    baseline_starter_actual_points: float | None

    players: tuple[
        PlayerPerformance,
        ...,
    ]


@dataclass(frozen=True)
class WeekPerformance:
    """Performance analytics for one league and fantasy week."""

    season: str
    week: int
    league_key: str

    teams: tuple[
        TeamPerformance,
        ...,
    ]


@dataclass(frozen=True)
class PerformanceClassification:
    """Classification result for one projection/actual pair."""

    baseline_projection: float | None
    actual_points: float | None
    difference: float | None
    ratio: float | None
    classification: str


def _optional_number(
    value: Any,
    description: str,
) -> float | None:
    """Normalize optional numeric data without manufacturing zero."""

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
    """Read and validate boom/bust configuration."""

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
    actual_points: Any,
    analytics_config: dict[str, Any],
) -> PerformanceClassification:
    """Classify one actual result against its frozen projection."""

    projection = (
        _optional_number(
            baseline_projection,
            "baseline_projection",
        )
    )

    actual = (
        _optional_number(
            actual_points,
            "actual_points",
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
                baseline_projection=(
                    projection
                ),
                actual_points=(
                    actual
                ),
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
                baseline_projection=(
                    projection
                ),
                actual_points=(
                    actual
                ),
                difference=(
                    difference
                ),
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
        classification = (
            BOOM
        )

    elif (
        ratio
        >= bust_threshold
    ):
        classification = (
            NORMAL
        )

    else:
        classification = (
            BUST
        )

    return (
        PerformanceClassification(
            baseline_projection=(
                projection
            ),
            actual_points=(
                actual
            ),
            difference=(
                difference
            ),
            ratio=(
                ratio
            ),
            classification=(
                classification
            ),
        )
    )


def _validate_baseline_identity(
    baseline_snapshot: dict[str, Any],
) -> tuple[
    str,
    int,
    str,
]:
    """Validate baseline identity and return season/week/league."""

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
    exact_scores: dict[
        str,
        ScoredPlayerWeek,
    ],
    analytics_config: dict[str, Any],
) -> WeekPerformance:
    """Analyze all frozen baseline rostered players.

    Boom/bust counts in the team summary apply only to frozen baseline
    starters.

    Bench players are also classified and retained so later lineup-
    efficiency analytics can reuse the same deterministic information.
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

    results: list[
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

            scored = (
                exact_scores.get(
                    player_id
                )
            )

            if scored is not None:
                if (
                    scored.season
                    != season
                    or scored.week
                    != week
                ):
                    raise PerformanceAnalyticsError(
                        f"Actual score for player "
                        f"{player_id} belongs to "
                        "the wrong season/week"
                    )

                actual_points: float | None = (
                    scored.points
                )

            else:
                actual_points = None

            classification = (
                classify_player_performance(
                    baseline_projection=(
                        player.get(
                            "projected_points"
                        )
                    ),
                    actual_points=(
                        actual_points
                    ),
                    analytics_config=(
                        analytics_config
                    ),
                )
            )

            player_results.append(
                PlayerPerformance(
                    roster_id=(
                        roster_id
                    ),
                    manager_name=(
                        manager_name
                    ),
                    player_id=(
                        player_id
                    ),
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
                        classification
                        .baseline_projection
                    ),
                    actual_points=(
                        classification
                        .actual_points
                    ),
                    difference=(
                        classification
                        .difference
                    ),
                    ratio=(
                        classification
                        .ratio
                    ),
                    classification=(
                        classification
                        .classification
                    ),
                )
            )

        starter_results = [
            player
            for player
            in player_results
            if player.was_baseline_starter
        ]

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

        resolved_starters = [
            player
            for player
            in starter_results
            if (
                player.actual_points
                is not None
            )
        ]

        if (
            len(
                resolved_starters
            )
            == len(
                starter_results
            )
        ):
            starter_actual_total: (
                float | None
            ) = sum(
                player.actual_points
                or 0.0
                for player
                in resolved_starters
            )

        else:
            starter_actual_total = (
                None
            )

        results.append(
            TeamPerformance(
                roster_id=(
                    roster_id
                ),
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
                        resolved_starters
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
                baseline_starter_actual_points=(
                    starter_actual_total
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
                results
            ),
        )
    )