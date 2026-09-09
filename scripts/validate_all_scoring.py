"""Validate exact fantasy scoring across all roster positions.

This diagnostic compares the exact scoring engine with Sleeper pts_ppr
for QB/RB/FB/WR/TE/K/DEF player-week records.

It also prints all non-zero raw stats for mismatches so unusual scoring
events can be investigated.

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


CONFIG_PATH = Path("config.json")

HISTORICAL_SEASON = "2025"

AUDIT_WEEKS = (
    1,
    2,
    3,
    4,
)

TARGET_POSITIONS = {
    "QB",
    "RB",
    "FB",
    "WR",
    "TE",
    "K",
    "DEF",
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
            "config.json must contain an object"
        )

    return config


def load_scoring_settings(
    config: dict[str, Any],
    sleeper: SleeperClient,
) -> dict[str, Any]:
    """Load scoring settings and verify both leagues still match."""

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
            "No leagues configured"
        )

    reference: dict[str, Any] | None = None
    reference_key: str | None = None

    for (
        league_key,
        league_config,
    ) in leagues.items():
        if not isinstance(
            league_config,
            dict,
        ):
            raise RuntimeError(
                f"Invalid league config: {league_key}"
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
                f"{league_key} has no valid league_id"
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
                f"{league_key} has no scoring_settings"
            )

        if reference is None:
            reference = dict(
                scoring
            )
            reference_key = league_key
            continue

        if scoring != reference:
            raise RuntimeError(
                "League scoring settings differ: "
                f"{reference_key} vs {league_key}"
            )

    if reference is None:
        raise RuntimeError(
            "No scoring settings found"
        )

    return reference


def classify_position(
    player_id: str,
    stats: dict[str, Any],
    players: dict[
        str,
        dict[str, Any],
    ],
) -> str | None:
    """Resolve fantasy position, including team defenses."""

    metadata = players.get(
        player_id
    )

    if isinstance(
        metadata,
        dict,
    ):
        position = metadata.get(
            "position"
        )

        if (
            isinstance(
                position,
                str,
            )
            and position
        ):
            return position

    # Defensive team IDs such as SEA or PHI can be resolved from
    # their team-level stat shape even if metadata is unavailable.
    if (
        player_id.isalpha()
        and len(player_id) <= 4
        and (
            "pts_allow" in stats
            or "yds_allow" in stats
            or "pts_allow_0" in stats
        )
    ):
        return "DEF"

    return None


def player_name(
    player_id: str,
    position: str,
    players: dict[
        str,
        dict[str, Any],
    ],
) -> str:
    """Return readable player/team name."""

    if position == "DEF":
        return f"{player_id} D/ST"

    metadata = players.get(
        player_id
    )

    if not isinstance(
        metadata,
        dict,
    ):
        return player_id

    name = metadata.get(
        "full_name"
    )

    if (
        isinstance(
            name,
            str,
        )
        and name
    ):
        return name

    return player_id


def nonzero_raw_stats(
    stats: dict[str, Any],
) -> list[
    tuple[
        str,
        Any,
    ]
]:
    """Return non-zero raw stats for mismatch inspection."""

    result: list[
        tuple[
            str,
            Any,
        ]
    ] = []

    for key, value in sorted(
        stats.items()
    ):
        if value is None:
            continue

        if (
            isinstance(
                value,
                (int, float),
            )
            and not isinstance(
                value,
                bool,
            )
        ):
            if abs(
                float(
                    value
                )
            ) <= 1e-12:
                continue

        result.append(
            (
                key,
                value,
            )
        )

    return result


def main() -> int:
    """Run complete historical scoring validation."""

    config = load_config()

    sleeper = SleeperClient()

    scoring_settings = (
        load_scoring_settings(
            config,
            sleeper,
        )
    )

    print("=" * 78)
    print(
        "ALL-POSITION EXACT SCORING VALIDATION"
    )
    print("=" * 78)

    print()
    print(
        "GOATs and DOATs scoring "
        "settings are identical."
    )

    print()
    print(
        "Refreshing player metadata..."
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

    comparable: Counter[
        str
    ] = Counter()

    exact: Counter[
        str
    ] = Counter()

    mismatches: Counter[
        str
    ] = Counter()

    missing_ppr: Counter[
        str
    ] = Counter()

    unresolved_position = 0

    mismatch_examples: list[
        dict[str, Any]
    ] = []

    for week in AUDIT_WEEKS:
        print()
        print(
            f"Fetching {HISTORICAL_SEASON} "
            f"Week {week}..."
        )

        records = (
            provider.get_week_stats(
                season=(
                    HISTORICAL_SEASON
                ),
                week=week,
            )
        )

        week_counts: Counter[
            str
        ] = Counter()

        for record in records:
            position = (
                classify_position(
                    player_id=(
                        record.player_id
                    ),
                    stats=record.stats,
                    players=players,
                )
            )

            if position is None:
                unresolved_position += 1
                continue

            if (
                position
                not in TARGET_POSITIONS
            ):
                continue

            scored = (
                score_player_week(
                    record,
                    scoring_settings,
                )
            )

            if scored is None:
                raise RuntimeError(
                    "Existing stat record "
                    "unexpectedly scored as null"
                )

            ppr = (
                actual_ppr_points(
                    record
                )
            )

            if ppr is None:
                missing_ppr[
                    position
                ] += 1

                continue

            difference = (
                scored.points
                - ppr
            )

            comparable[
                position
            ] += 1

            week_counts[
                position
            ] += 1

            if abs(
                difference
            ) <= 0.01:
                exact[
                    position
                ] += 1

                continue

            mismatches[
                position
            ] += 1

            if len(
                mismatch_examples
            ) < 40:
                mismatch_examples.append(
                    {
                        "week": week,
                        "player_id": (
                            record.player_id
                        ),
                        "player_name": (
                            player_name(
                                record.player_id,
                                position,
                                players,
                            )
                        ),
                        "position": (
                            position
                        ),
                        "exact": (
                            scored.points
                        ),
                        "ppr": (
                            ppr
                        ),
                        "difference": (
                            difference
                        ),
                        "raw_stats": (
                            nonzero_raw_stats(
                                record.stats
                            )
                        ),
                        "contributions": [
                            (
                                contribution
                            )
                            for contribution
                            in scored.contributions
                        ],
                    }
                )

        print(
            "  comparable: "
            + ", ".join(
                (
                    f"{position}="
                    f"{week_counts[position]}"
                )
                for position
                in sorted(
                    week_counts
                )
            )
        )

    print()
    print("=" * 78)
    print("RESULTS BY POSITION")
    print("=" * 78)

    total_comparable = 0
    total_exact = 0
    total_mismatch = 0

    for position in sorted(
        TARGET_POSITIONS
    ):
        position_total = (
            comparable[
                position
            ]
        )

        position_exact = (
            exact[
                position
            ]
        )

        position_mismatch = (
            mismatches[
                position
            ]
        )

        total_comparable += (
            position_total
        )

        total_exact += (
            position_exact
        )

        total_mismatch += (
            position_mismatch
        )

        rate = (
            position_exact
            / position_total
            * 100.0
            if position_total
            else 0.0
        )

        print(
            f"{position:<4} "
            f"comparable={position_total:>4}  "
            f"exact={position_exact:>4}  "
            f"mismatch={position_mismatch:>4}  "
            f"rate={rate:>6.2f}%  "
            f"missing_ppr="
            f"{missing_ppr[position]:>4}"
        )

    print()
    print(
        f"Total comparable: "
        f"{total_comparable}"
    )

    print(
        f"Total exact:      "
        f"{total_exact}"
    )

    print(
        f"Total mismatches: "
        f"{total_mismatch}"
    )

    if total_comparable:
        print(
            f"Overall rate:     "
            f"{(
                total_exact
                / total_comparable
                * 100.0
            ):.2f}%"
        )

    print(
        f"Unresolved positions: "
        f"{unresolved_position}"
    )

    if mismatch_examples:
        print()
        print("=" * 78)
        print("MISMATCH FORENSICS")
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
                f"{example['ppr']:.2f}"
            )

            print(
                f"  difference: "
                f"{example['difference']:+.2f}"
            )

            print()
            print(
                "  Exact-scoring contributions:"
            )

            if not example[
                "contributions"
            ]:
                print(
                    "    <none>"
                )

            else:
                for contribution in (
                    example[
                        "contributions"
                    ]
                ):
                    print(
                        f"    "
                        f"{contribution.scoring_key:<24} "
                        f"{contribution.stat_value:>8g} "
                        f"x "
                        f"{contribution.multiplier:>6g} "
                        f"= "
                        f"{contribution.points:>8g} "
                        f"[{contribution.source}]"
                    )

            print()
            print(
                "  All non-zero raw stats:"
            )

            for (
                key,
                value,
            ) in example[
                "raw_stats"
            ]:
                print(
                    f"    {key:<30} "
                    f"{value}"
                )

    print()
    print("=" * 78)
    print("VALIDATION GATE")
    print("=" * 78)

    print(
        "Offensive matches validate ordinary "
        "QB/RB/WR/TE/FB scoring."
    )

    print(
        "K and DEF results determine whether "
        "the exact scorer is ready for full "
        "lineup-efficiency calculations."
    )

    print(
        "Any mismatches must be understood "
        "before the scorer is integrated "
        "into final analytics."
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