"""Audit Sleeper raw player-stat keys needed for exact league scoring.

This script is diagnostic only.

It fetches several completed historical NFL weeks from Sleeper's public
player-stat feed and compares the raw stat schema with the active scoring
settings used by GOATs and DOATs.

Nothing is written to disk.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.player_stats import (
    SleeperPlayerStatsProvider,
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


RELEVANT_PREFIXES = (
    "pass",
    "rush",
    "rec",
    "fum",
    "fg",
    "xp",
    "sack",
    "int",
    "safe",
    "blk",
    "ff",
    "st",
    "def",
    "pts_allow",
    "yds_allow",
)


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


def load_reference_scoring(
    config: dict[str, Any],
) -> tuple[
    str,
    dict[str, float],
]:
    """Fetch scoring settings from the first configured league."""

    from src.sleeper import SleeperClient

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

    first_key = next(
        iter(
            leagues
        )
    )

    league_config = leagues[
        first_key
    ]

    if not isinstance(
        league_config,
        dict,
    ):
        raise RuntimeError(
            "Invalid league configuration"
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
            "Reference league has no league_id"
        )

    league = SleeperClient().get_league(
        league_id
    )

    raw_settings = league.get(
        "scoring_settings"
    )

    if not isinstance(
        raw_settings,
        dict,
    ):
        raise RuntimeError(
            "League has no scoring_settings"
        )

    settings: dict[
        str,
        float,
    ] = {}

    for key, value in (
        raw_settings.items()
    ):
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
            raise RuntimeError(
                f"Invalid scoring value for {key}"
            )

        if abs(
            float(
                value
            )
        ) <= 1e-12:
            continue

        settings[
            str(
                key
            )
        ] = float(
            value
        )

    return (
        first_key,
        settings,
    )


def is_relevant_stat_key(
    key: str,
) -> bool:
    """Return whether a raw stat key is relevant to league scoring."""

    lower_key = (
        key.lower()
    )

    if lower_key == "pts_ppr":
        return True

    return any(
        lower_key.startswith(
            prefix
        )
        for prefix
        in RELEVANT_PREFIXES
    )


def main() -> int:
    """Run the read-only raw-stat schema audit."""

    config = load_config()

    (
        reference_league,
        scoring_settings,
    ) = load_reference_scoring(
        config
    )

    provider = (
        SleeperPlayerStatsProvider()
    )

    key_occurrences: Counter[
        str
    ] = Counter()

    nonzero_occurrences: Counter[
        str
    ] = Counter()

    samples: dict[
        str,
        list[
            tuple[
                str,
                Any,
            ]
        ],
    ] = {}

    total_records = 0

    print("=" * 78)
    print(
        "RAW PLAYER-STAT KEY AUDIT"
    )
    print("=" * 78)

    print(
        f"Reference league: "
        f"{reference_league}"
    )

    print(
        f"Historical season: "
        f"{HISTORICAL_SEASON}"
    )

    print(
        "Weeks: "
        + ", ".join(
            str(
                week
            )
            for week
            in AUDIT_WEEKS
        )
    )

    for week in (
        AUDIT_WEEKS
    ):
        print()
        print(
            f"Fetching Week {week}..."
        )

        records = (
            provider.get_week_stats(
                season=(
                    HISTORICAL_SEASON
                ),
                week=week,
            )
        )

        print(
            f"  normalized records: "
            f"{len(records)}"
        )

        total_records += len(
            records
        )

        for record in records:
            for key, value in (
                record.stats.items()
            ):
                key = str(
                    key
                )

                key_occurrences[
                    key
                ] += 1

                if (
                    isinstance(
                        value,
                        (int, float),
                    )
                    and not isinstance(
                        value,
                        bool,
                    )
                    and abs(
                        float(
                            value
                        )
                    )
                    > 1e-12
                ):
                    nonzero_occurrences[
                        key
                    ] += 1

                    entries = (
                        samples.setdefault(
                            key,
                            [],
                        )
                    )

                    if len(
                        entries
                    ) < 3:
                        entries.append(
                            (
                                record.player_id,
                                value,
                            )
                        )

    print()
    print("=" * 78)
    print(
        "ACTIVE LEAGUE SCORING KEYS"
    )
    print("=" * 78)

    matched: list[
        str
    ] = []

    unmatched: list[
        str
    ] = []

    for key, multiplier in (
        sorted(
            scoring_settings.items()
        )
    ):
        occurrences = (
            key_occurrences[
                key
            ]
        )

        nonzero = (
            nonzero_occurrences[
                key
            ]
        )

        if occurrences:
            matched.append(
                key
            )

            status = (
                "DIRECT"
            )

        else:
            unmatched.append(
                key
            )

            status = (
                "NOT OBSERVED"
            )

        print(
            f"{key:<30} "
            f"score={multiplier:>6g}  "
            f"rows={occurrences:>5}  "
            f"nonzero={nonzero:>4}  "
            f"{status}"
        )

    print()
    print("=" * 78)
    print(
        "DIRECT COVERAGE SUMMARY"
    )
    print("=" * 78)

    print(
        f"Active scoring keys: "
        f"{len(scoring_settings)}"
    )

    print(
        f"Observed directly:   "
        f"{len(matched)}"
    )

    print(
        f"Not observed:        "
        f"{len(unmatched)}"
    )

    if unmatched:
        print()
        print(
            "Scoring keys without an "
            "identically named raw stat:"
        )

        for key in unmatched:
            print(
                f"  {key}"
            )

    print()
    print("=" * 78)
    print(
        "RELEVANT RAW STAT KEYS"
    )
    print("=" * 78)

    relevant_keys = sorted(
        key
        for key
        in key_occurrences
        if is_relevant_stat_key(
            key
        )
    )

    for key in relevant_keys:
        sample_values = (
            samples.get(
                key,
                [],
            )
        )

        sample_text = (
            ", ".join(
                f"{player_id}={value}"
                for (
                    player_id,
                    value,
                )
                in sample_values
            )
            or "-"
        )

        print(
            f"{key:<30} "
            f"rows={key_occurrences[key]:>5}  "
            f"nonzero="
            f"{nonzero_occurrences[key]:>4}  "
            f"samples: {sample_text}"
        )

    print()
    print("=" * 78)
    print(
        "SPECIAL DERIVED-SCORING INPUTS"
    )
    print("=" * 78)

    candidates = (
        "pts_allow",
        "yds_allow",
        "fgm",
        "fgmiss",
        "xpm",
        "xpmiss",
    )

    for key in candidates:
        print(
            f"{key:<20} "
            f"rows="
            f"{key_occurrences[key]:>5}  "
            f"nonzero="
            f"{nonzero_occurrences[key]:>4}"
        )

    print()
    print("=" * 78)
    print(
        "AUDIT SUMMARY"
    )
    print("=" * 78)

    print(
        f"Total normalized records inspected: "
        f"{total_records}"
    )

    print(
        f"Unique raw stat keys observed: "
        f"{len(key_occurrences)}"
    )

    print(
        f"Active scoring keys observed directly: "
        f"{len(matched)} / "
        f"{len(scoring_settings)}"
    )

    print()
    print(
        "PROBE COMPLETE — "
        "nothing was written."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )