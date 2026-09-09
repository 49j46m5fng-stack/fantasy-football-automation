"""Exact fantasy-point scoring from Sleeper raw statistics.

The scorer applies a league's stored Sleeper scoring_settings directly
to raw weekly player statistics.

Important semantics:

- A missing player-stat RECORD remains missing elsewhere in the system.
- Within an existing stat record, Sleeper's stat mappings are sparse.
  An absent individual counting stat therefore contributes zero.
- Points-allowed and yards-allowed buckets can be reconstructed from
  their aggregate values when available.
- The 0-19 yard field-goal bucket can be reconstructed from total made
  field goals minus the observed longer-distance buckets.
- No projection data is used here.
"""

from dataclasses import dataclass
from typing import Any

from src.player_stats import (
    PlayerWeekStat,
)


class FantasyScoringError(ValueError):
    """Raised when exact fantasy scoring cannot be calculated safely."""


@dataclass(frozen=True)
class ScoringContribution:
    """One scoring-rule contribution to a player's fantasy total."""

    scoring_key: str
    stat_value: float
    multiplier: float
    points: float
    source: str


@dataclass(frozen=True)
class ScoredPlayerWeek:
    """Exact league-scored result for one player-week record."""

    player_id: str
    season: str
    week: int
    points: float
    contributions: tuple[
        ScoringContribution,
        ...,
    ]


PTS_ALLOW_BUCKETS = (
    "pts_allow_0",
    "pts_allow_1_6",
    "pts_allow_7_13",
    "pts_allow_14_20",
    "pts_allow_21_27",
    "pts_allow_28_34",
    "pts_allow_35p",
)

YDS_ALLOW_BUCKETS = (
    "yds_allow_0_100",
    "yds_allow_100_199",
    "yds_allow_200_299",
    "yds_allow_300_349",
    "yds_allow_350_399",
    "yds_allow_400_449",
    "yds_allow_450_499",
    "yds_allow_500_549",
    "yds_allow_550p",
)

FGM_DISTANCE_BUCKETS = (
    "fgm_0_19",
    "fgm_20_29",
    "fgm_30_39",
    "fgm_40_49",
    "fgm_50_59",
    "fgm_60p",
)


def normalize_scoring_settings(
    settings: Any,
) -> dict[str, float]:
    """Normalize Sleeper scoring settings into numeric multipliers."""

    if not isinstance(
        settings,
        dict,
    ):
        raise FantasyScoringError(
            "scoring_settings must be an object"
        )

    normalized: dict[
        str,
        float,
    ] = {}

    for raw_key, raw_value in (
        settings.items()
    ):
        key = str(
            raw_key
        )

        if (
            isinstance(
                raw_value,
                bool,
            )
            or not isinstance(
                raw_value,
                (int, float),
            )
        ):
            raise FantasyScoringError(
                f"Scoring setting {key!r} "
                "must be numeric"
            )

        normalized[
            key
        ] = float(
            raw_value
        )

    return normalized


def _numeric_stat(
    stats: dict[str, Any],
    key: str,
) -> float | None:
    """Return one numeric raw stat or None when the sparse key is absent."""

    if key not in stats:
        return None

    value = stats[
        key
    ]

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
        raise FantasyScoringError(
            f"Raw statistic {key!r} "
            "must be numeric or null"
        )

    return float(
        value
    )


def _points_allowed_bucket(
    points_allowed: float,
) -> str:
    """Return the Sleeper scoring bucket for defensive points allowed."""

    if points_allowed < 0:
        raise FantasyScoringError(
            "pts_allow cannot be negative"
        )

    if points_allowed == 0:
        return "pts_allow_0"

    if points_allowed <= 6:
        return "pts_allow_1_6"

    if points_allowed <= 13:
        return "pts_allow_7_13"

    if points_allowed <= 20:
        return "pts_allow_14_20"

    if points_allowed <= 27:
        return "pts_allow_21_27"

    if points_allowed <= 34:
        return "pts_allow_28_34"

    return "pts_allow_35p"


def _yards_allowed_bucket(
    yards_allowed: float,
) -> str:
    """Return the Sleeper scoring bucket for defensive yards allowed."""

    if yards_allowed < 0:
        raise FantasyScoringError(
            "yds_allow cannot be negative"
        )

    if yards_allowed <= 100:
        return "yds_allow_0_100"

    if yards_allowed <= 199:
        return "yds_allow_100_199"

    if yards_allowed <= 299:
        return "yds_allow_200_299"

    if yards_allowed <= 349:
        return "yds_allow_300_349"

    if yards_allowed <= 399:
        return "yds_allow_350_399"

    if yards_allowed <= 449:
        return "yds_allow_400_449"

    if yards_allowed <= 499:
        return "yds_allow_450_499"

    if yards_allowed <= 549:
        return "yds_allow_500_549"

    return "yds_allow_550p"


def _derive_points_allowed_stats(
    stats: dict[str, Any],
) -> tuple[
    dict[str, float],
    set[str],
]:
    """Create a deterministic points-allowed bucket when possible."""

    derived: dict[
        str,
        float,
    ] = {}

    derived_keys: set[
        str
    ] = set()

    points_allowed = (
        _numeric_stat(
            stats,
            "pts_allow",
        )
    )

    if points_allowed is None:
        # Shutouts in Sleeper's sparse feed can omit pts_allow=0 while
        # supplying pts_allow_0 directly. In that case, preserve the raw
        # bucket rather than manufacturing an aggregate value.
        return (
            derived,
            derived_keys,
        )

    for key in (
        PTS_ALLOW_BUCKETS
    ):
        derived[
            key
        ] = 0.0

        derived_keys.add(
            key
        )

    bucket = (
        _points_allowed_bucket(
            points_allowed
        )
    )

    derived[
        bucket
    ] = 1.0

    return (
        derived,
        derived_keys,
    )


def _derive_yards_allowed_stats(
    stats: dict[str, Any],
) -> tuple[
    dict[str, float],
    set[str],
]:
    """Create a deterministic yards-allowed bucket when possible."""

    derived: dict[
        str,
        float,
    ] = {}

    derived_keys: set[
        str
    ] = set()

    yards_allowed = (
        _numeric_stat(
            stats,
            "yds_allow",
        )
    )

    if yards_allowed is None:
        return (
            derived,
            derived_keys,
        )

    for key in (
        YDS_ALLOW_BUCKETS
    ):
        derived[
            key
        ] = 0.0

        derived_keys.add(
            key
        )

    bucket = (
        _yards_allowed_bucket(
            yards_allowed
        )
    )

    derived[
        bucket
    ] = 1.0

    return (
        derived,
        derived_keys,
    )


def _derive_short_field_goals(
    stats: dict[str, Any],
) -> tuple[
    dict[str, float],
    set[str],
]:
    """Recover made 0-19 yard field goals from total made field goals."""

    total_made = (
        _numeric_stat(
            stats,
            "fgm",
        )
    )

    if total_made is None:
        return (
            {},
            set(),
        )

    observed_longer = 0.0

    for key in (
        FGM_DISTANCE_BUCKETS[1:]
    ):
        value = (
            _numeric_stat(
                stats,
                key,
            )
        )

        if value is not None:
            observed_longer += (
                value
            )

    direct_short = (
        _numeric_stat(
            stats,
            "fgm_0_19",
        )
    )

    if direct_short is not None:
        bucket_total = (
            direct_short
            + observed_longer
        )

        if abs(
            bucket_total
            - total_made
        ) > 1e-9:
            raise FantasyScoringError(
                "Field-goal distance buckets "
                "do not equal total made field goals"
            )

        return (
            {},
            set(),
        )

    short_made = (
        total_made
        - observed_longer
    )

    if short_made < -1e-9:
        raise FantasyScoringError(
            "Observed field-goal distance "
            "buckets exceed total made field goals"
        )

    if abs(
        short_made
    ) < 1e-9:
        short_made = 0.0

    return (
        {
            "fgm_0_19": (
                short_made
            )
        },
        {
            "fgm_0_19"
        },
    )


def _effective_stats(
    stats: dict[str, Any],
) -> tuple[
    dict[str, Any],
    set[str],
]:
    """Return raw stats plus safe deterministic bucket derivations."""

    effective = dict(
        stats
    )

    derived_keys: set[
        str
    ] = set()

    (
        points_allowed,
        points_keys,
    ) = (
        _derive_points_allowed_stats(
            stats
        )
    )

    effective.update(
        points_allowed
    )

    derived_keys.update(
        points_keys
    )

    (
        yards_allowed,
        yards_keys,
    ) = (
        _derive_yards_allowed_stats(
            stats
        )
    )

    effective.update(
        yards_allowed
    )

    derived_keys.update(
        yards_keys
    )

    (
        field_goals,
        field_goal_keys,
    ) = (
        _derive_short_field_goals(
            stats
        )
    )

    effective.update(
        field_goals
    )

    derived_keys.update(
        field_goal_keys
    )

    return (
        effective,
        derived_keys,
    )


def score_raw_stats(
    stats: dict[str, Any],
    scoring_settings: dict[str, Any],
) -> tuple[
    float,
    tuple[
        ScoringContribution,
        ...,
    ],
]:
    """Calculate exact league fantasy points from one raw stat mapping."""

    if not isinstance(
        stats,
        dict,
    ):
        raise FantasyScoringError(
            "stats must be an object"
        )

    settings = (
        normalize_scoring_settings(
            scoring_settings
        )
    )

    (
        effective_stats,
        derived_keys,
    ) = (
        _effective_stats(
            stats
        )
    )

    contributions: list[
        ScoringContribution
    ] = []

    total = 0.0

    for key in sorted(
        settings
    ):
        multiplier = (
            settings[
                key
            ]
        )

        if abs(
            multiplier
        ) <= 1e-12:
            continue

        stat_value = (
            _numeric_stat(
                effective_stats,
                key,
            )
        )

        # Sleeper's stat records are sparse. A missing counting stat
        # inside an otherwise existing player-week record means that
        # scoring event contributed zero.
        if stat_value is None:
            continue

        points = (
            stat_value
            * multiplier
        )

        if abs(
            points
        ) <= 1e-12:
            continue

        contribution = (
            ScoringContribution(
                scoring_key=key,
                stat_value=(
                    stat_value
                ),
                multiplier=(
                    multiplier
                ),
                points=round(
                    points,
                    8,
                ),
                source=(
                    "derived"
                    if key
                    in derived_keys
                    else "raw"
                ),
            )
        )

        contributions.append(
            contribution
        )

        total += points

    return (
        round(
            total,
            8,
        ),
        tuple(
            contributions
        ),
    )


def score_player_week(
    record: PlayerWeekStat | None,
    scoring_settings: dict[str, Any],
) -> ScoredPlayerWeek | None:
    """Score one normalized player-week record.

    A missing record remains None. It is never silently converted to zero.
    """

    if record is None:
        return None

    (
        points,
        contributions,
    ) = score_raw_stats(
        stats=record.stats,
        scoring_settings=(
            scoring_settings
        ),
    )

    return ScoredPlayerWeek(
        player_id=(
            record.player_id
        ),
        season=(
            record.season
        ),
        week=(
            record.week
        ),
        points=points,
        contributions=(
            contributions
        ),
    )