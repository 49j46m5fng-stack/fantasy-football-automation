"""Validate the exact fantasy scoring engine against Sleeper pts_ppr.

This script is diagnostic only.

It compares our exact scoring engine with Sleeper's historical pts_ppr
values for ordinary offensive fantasy players across several completed
2025 NFL weeks.

The comparison is not intended to prove that pts_ppr is league scoring.
Differences can be legitimate when league scoring differs from Sleeper's
generic PPR convention.

Nothing is written to disk.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.player_stats import (
    SleeperPlayerStatsProvider,
    actual_ppr_points,
)
from src.players import (
    get_player_map,
)
from src.scoring import (
    score_player_week,
)
from src.sleeper import (
    SleeperClient,
)


CONFIG_PATH = Path(
    "config.json"
)

HISTORICAL_SEASON = "2025"

AUDIT_WEEKS = (
    1,
    2,
    3,
    4,
)

OFFENSIVE_POSITIONS = {
    "QB",
    "RB",
    "FB",
    "WR",
    "TE",
}


def load_config() -> dict[str, Any]:
    """Load project configuration."""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(
            file
        )

    if not isinstance(
        config,
        dict,
    ):
        raise RuntimeError(
            "config.json must contain "
            "a JSON object"
        )

    return config


def load_scoring_settings(
    config: dict[str, Any],
    sleeper: SleeperClient,
) -> dict[str, Any]:
    """Load scoring settings and verify both leagues are identical."""

    leagues = config.get(
        "leagues"
    )

    if (
        not isinstance(
            leagues,
            dict,
        )
        or not leagues
    ):
        raise RuntimeError(
            "No leagues are configured"
        )

    reference: dict[
        str,
        Any,
    ] | None = None

    reference_name: str | None = None

    for (
        league_key,
        league_config,
    ) in leagues.items():
        if not isinstance(
            league_config,
            dict,
        ):
            raise RuntimeError(
                f"Invalid league config: "
                f"{league_key}"
            )

        league_id = (
            league_config.get(
                "league_id"
            )
        )

        if not isinstance(
            league_id,
            str,
        ):
            raise RuntimeError(
                f"{league_key} has "
                "no valid league_id"
            )

        league = sleeper.get_league(
            league_id
        )

        scoring = league.get(
            "scoring_settings"
        )

        if not isinstance(
            scoring,
            dict,
        ):
            raise RuntimeError(
                f"{league_key} has no "
                "scoring_settings"
            )

        if reference is None:
            reference = dict(
                scoring
            )

            reference_name = (
                league_key
            )

            continue

        if scoring != reference:
            raise RuntimeError(
                "Configured leagues no "
                "longer have identical "
                "scoring settings: "
                f"{reference_name} vs "
                f"{league_key}"
            )

    if reference is None:
        raise RuntimeError(
            "No scoring settings found"
        )

    return reference


def player_position(
    player_id: str,
    players: dict[
        str,
        dict[str, Any],
    ],
) -> str | None:
    """Return normalized Sleeper position metadata."""

    metadata = players.get(
        player_id
    )

    if not isinstance(
        metadata,
        dict,
    ):
        return None

    position = metadata.get(
        "position"
    )

    if not isinstance(
        position,
        str,
    ):
        return None

    return position


def player_name(
    player_id: str,
    players: dict[
        str,
        dict[str, Any],
    ],
) -> str:
    """Return a readable player name."""

    metadata = players.get(
        player_id
    )

    if not isinstance(
        metadata,
        dict,
    ):
        return player_id

    for field in (
        "full_name",
        "display_name",
        "first_name",
    ):
        value = metadata.get(
            field
        )

        if (
            isinstance(
                value,
                str,
            )
            and value
        ):
            return value

    return player_id


def main() -> int:
    """Run the historical exact-scoring validation."""

    config = load_config()

    sleeper = SleeperClient()

    print("=" * 78)
    print(
        "EXACT SCORING ENGINE VALIDATION"
    )
    print("=" * 78)

    print()
    print(
        "Loading current league "
        "scoring settings..."
    )

    scoring_settings = (
        load_scoring_settings(
            config,
            sleeper,
        )
    )

    print(
        "GOATs and DOATs scoring "
        "settings are identical."
    )

    print()
    print(
        "Refreshing Sleeper player metadata..."
    )

    players = get_player_map(
        sleeper,
        refresh=True,
    )

    print(
        f"Player metadata records: "
        f"{len(players)}"
    )

    provider = (
        SleeperPlayerStatsProvider()
    )

    comparable = 0
    exact_matches = 0
    mismatches = 0
    missing_metadata = 0
    skipped_non_offense = 0

    mismatch_by_position: Counter[
        str
    ] = Counter()

    comparison_by_position: Counter[
        str
    ] = Counter()

    mismatch_examples: list[
        dict[str, Any]
    ] = []

    largest_difference = 0.0

    for week in AUDIT_WEEKS:
        print()
        print(
            f"Fetching {HISTORICAL_SEASON} "
            f"Week {week} stats..."
        )

        records = (
            provider.get_week_stats(
                season=(
                    HISTORICAL_SEASON
                ),
                week=week,
            )
        )

        week_comparable = 0
        week_exact = 0
        week_mismatch = 0

        for record in records:
            ppr_points = (
                actual_ppr_points(
                    record
                )
            )

            if ppr_points is None:
                continue

            position = (
                player_position(
                    record.player_id,
                    players,
                )
            )

            if position is None:
                missing_metadata += 1
                continue

            if (
                position
                not in OFFENSIVE_POSITIONS
            ):
                skipped_non_offense += 1
                continue

            scored = (
                score_player_week(
                    record,
                    scoring_settings,
                )
            )

            if scored is None:
                raise RuntimeError(
                    "Existing player stat "
                    "unexpectedly scored as null"
                )

            difference = (
                scored.points
                - ppr_points
            )

            absolute_difference = abs(
                difference
            )

            comparable += 1
            week_comparable += 1

            comparison_by_position[
                position
            ] += 1

            if (
                absolute_difference
                <= 0.01
            ):
                exact_matches += 1
                week_exact += 1

            else:
                mismatches += 1
                week_mismatch += 1

                mismatch_by_position[
                    position
                ] += 1

                largest_difference = max(
                    largest_difference,
                    absolute_difference,
                )

                if len(
                    mismatch_examples
                ) < 30:
                    mismatch_examples.append(
                        {
                            "week": week,
                            "player_id": (
                                record.player_id
                            ),
                            "player_name": (
                                player_name(
                                    record.player_id,
                                    players,
                                )
                            ),
                            "position": (
                                position
                            ),
                            "exact": (
                                scored.points
                            ),
                            "pts_ppr": (
                                ppr_points
                            ),
                            "difference": (
                                difference
                            ),
                            "contributions": [
                                {
                                    "key": (
                                        contribution
                                        .scoring_key
                                    ),
                                    "stat": (
                                        contribution
                                        .stat_value
                                    ),
                                    "multiplier": (
                                        contribution
                                        .multiplier
                                    ),
                                    "points": (
                                        contribution
                                        .points
                                    ),
                                    "source": (
                                        contribution
                                        .source
                                    ),
                                }
                                for contribution
                                in scored.contributions
                            ],
                        }
                    )

        print(
            f"  comparable: "
            f"{week_comparable}"
        )

        print(
            f"  exact:      "
            f"{week_exact}"
        )

        print(
            f"  mismatches: "
            f"{week_mismatch}"
        )

    print()
    print("=" * 78)
    print(
        "OVERALL RESULTS"
    )
    print("=" * 78)

    print(
        f"Comparable offensive "
        f"player-weeks:      "
        f"{comparable}"
    )

    print(
        f"Exact within 0.01:       "
        f"{exact_matches}"
    )

    print(
        f"Mismatches:              "
        f"{mismatches}"
    )

    if comparable:
        exact_rate = (
            exact_matches
            / comparable
            * 100.0
        )

        print(
            f"Exact-match rate:        "
            f"{exact_rate:.2f}%"
        )

    print(
        f"Largest abs difference:  "
        f"{largest_difference:.2f}"
    )

    print(
        f"Missing player metadata: "
        f"{missing_metadata}"
    )

    print(
        f"Skipped K/DEF/other:     "
        f"{skipped_non_offense}"
    )

    print()
    print(
        "BY POSITION"
    )
    print("-" * 78)

    for position in sorted(
        comparison_by_position
    ):
        total = (
            comparison_by_position[
                position
            ]
        )

        mismatch_count = (
            mismatch_by_position[
                position
            ]
        )

        exact_count = (
            total
            - mismatch_count
        )

        print(
            f"{position:<4} "
            f"total={total:>4}  "
            f"exact={exact_count:>4}  "
            f"mismatch="
            f"{mismatch_count:>4}"
        )

    if mismatch_examples:
        print()
        print("=" * 78)
        print(
            "MISMATCH EXAMPLES"
        )
        print("=" * 78)

        for example in (
            mismatch_examples
        ):
            print()
            print(
                f"Week {example['week']} | "
                f"{example['player_name']} "
                f"({example['position']}, "
                f"{example['player_id']})"
            )

            print(
                f"  exact:      "
                f"{example['exact']:.2f}"
            )

            print(
                f"  pts_ppr:    "
                f"{example['pts_ppr']:.2f}"
            )

            print(
                f"  difference: "
                f"{example['difference']:+.2f}"
            )

            print(
                "  scoring contributions:"
            )

            for contribution in (
                example[
                    "contributions"
                ]
            ):
                print(
                    f"    "
                    f"{contribution['key']:<24} "
                    f"{contribution['stat']:>7g} "
                    f"x "
                    f"{contribution['multiplier']:>6g} "
                    f"= "
                    f"{contribution['points']:>8g} "
                    f"[{contribution['source']}]"
                )

    print()
    print("=" * 78)
    print(
        "INTERPRETATION"
    )
    print("=" * 78)

    print(
        "Exact matches show that our "
        "raw-stat scorer reproduces "
        "Sleeper's generic PPR result "
        "for that player-week."
    )

    print()
    print(
        "Mismatches are not automatically "
        "errors. They may be caused by "
        "league scoring that intentionally "
        "differs from generic pts_ppr."
    )

    print()
    print(
        "The contribution detail above "
        "is intended to make every "
        "difference auditable."
    )

    print()
    print(
        "VALIDATION COMPLETE — "
        "nothing was written."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )