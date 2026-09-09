"""Audit Sleeper player scoring against historical league matchup totals.

This script is deliberately diagnostic only.

It does not write snapshots, analytics, reports, or cache files.

It answers two questions before player-level actual scoring enters
business logic:

1. Does Sleeper's bulk weekly stats feed provide usable pts_ppr values?
2. Does the league matchup payload expose any additional per-player
   scoring fields that could represent exact league-scored points?

It also compares the sum of starter pts_ppr values with the historical
league team score. A mismatch is evidence that generic PPR points must
not be treated as exact league scoring.
"""

import json
from pathlib import Path
from typing import Any

from src.player_stats import (
    SleeperPlayerStatsProvider,
    actual_ppr_points,
    build_week_stat_lookup,
)
from src.sleeper import (
    SleeperClient,
)


CONFIG_PATH = Path(
    "config.json"
)


def load_config() -> dict[str, Any]:
    """Load the project configuration."""

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
            "config.json must "
            "contain an object"
        )

    return config


def _historical_season(
    current_season: str,
) -> str:
    """Return the immediately preceding numeric season."""

    try:
        year = int(
            current_season
        )

    except ValueError as exc:
        raise RuntimeError(
            "Configured season must "
            "be numeric"
        ) from exc

    return str(
        year - 1
    )


def _valid_player_ids(
    values: Any,
) -> list[str]:
    """Return populated Sleeper player IDs."""

    if not isinstance(
        values,
        list,
    ):
        return []

    return [
        str(
            player_id
        )
        for player_id
        in values
        if (
            player_id is not None
            and str(
                player_id
            )
            not in {
                "",
                "0",
            }
        )
    ]


def _effective_team_points(
    matchup: dict[str, Any],
) -> float | None:
    """Return commissioner-adjusted team points when available."""

    custom_points = (
        matchup.get(
            "custom_points"
        )
    )

    raw_points = (
        matchup.get(
            "points"
        )
    )

    value = (
        custom_points
        if custom_points is not None
        else raw_points
    )

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
        return None

    return float(
        value
    )


def main() -> int:
    """Run the non-writing scoring audit."""

    config = load_config()

    current_season = str(
        config["season"]
    )

    historical_season = (
        _historical_season(
            current_season
        )
    )

    week = 1

    print("=" * 78)
    print("PLAYER ACTUAL-SCORING AUDIT")
    print("=" * 78)

    print(
        f"Historical season: "
        f"{historical_season}"
    )

    print(
        f"Audit week:        "
        f"{week}"
    )

    print()
    print(
        "Fetching historical "
        "weekly player stats..."
    )

    records = (
        SleeperPlayerStatsProvider()
        .get_week_stats(
            season=(
                historical_season
            ),
            week=week,
        )
    )

    stat_lookup = (
        build_week_stat_lookup(
            records
        )
    )

    ppr_records = [
        record
        for record
        in records
        if (
            actual_ppr_points(
                record
            )
            is not None
        )
    ]

    categories = sorted(
        {
            str(
                record.category
            )
            for record
            in records
            if record.category
            is not None
        }
    )

    companies = sorted(
        {
            str(
                record.company
            )
            for record
            in records
            if record.company
            is not None
        }
    )

    print()
    print("STATS FEED")
    print("-" * 78)

    print(
        f"Normalized records: "
        f"{len(records)}"
    )

    print(
        f"Records with pts_ppr: "
        f"{len(ppr_records)}"
    )

    print(
        f"Categories: "
        f"{categories or ['<not supplied>']}"
    )

    print(
        f"Companies: "
        f"{companies or ['<not supplied>']}"
    )

    print()
    print(
        "Sample scored records:"
    )

    scored_sample = sorted(
        ppr_records,
        key=lambda record: (
            actual_ppr_points(
                record
            )
            or 0.0
        ),
        reverse=True,
    )[:10]

    for record in scored_sample:
        print(
            f"  {record.player_id}: "
            f"{actual_ppr_points(record):.2f}"
        )

    sleeper = SleeperClient()

    leagues = config.get(
        "leagues",
        {},
    )

    if not isinstance(
        leagues,
        dict,
    ):
        raise RuntimeError(
            "Configured leagues "
            "must be an object"
        )

    for (
        league_key,
        league_config,
    ) in leagues.items():
        print()
        print("=" * 78)

        if not isinstance(
            league_config,
            dict,
        ):
            print(
                f"{league_key}: "
                "invalid configuration"
            )

            continue

        league_name = (
            league_config.get(
                "name",
                league_key,
            )
        )

        current_league_id = (
            league_config.get(
                "league_id"
            )
        )

        print(
            f"{league_name.upper()} "
            "HISTORICAL LEAGUE AUDIT"
        )

        print("=" * 78)

        if not isinstance(
            current_league_id,
            str,
        ):
            print(
                "No valid current "
                "league_id."
            )

            continue

        current_league = (
            sleeper.get_league(
                current_league_id
            )
        )

        previous_league_id = (
            current_league.get(
                "previous_league_id"
            )
        )

        if (
            previous_league_id
            is None
            or str(
                previous_league_id
            )
            in {
                "",
                "0",
            }
        ):
            print(
                "No previous_league_id "
                "is available."
            )

            continue

        previous_league_id = str(
            previous_league_id
        )

        previous_league = (
            sleeper.get_league(
                previous_league_id
            )
        )

        print(
            f"Previous league ID: "
            f"{previous_league_id}"
        )

        print(
            f"Previous season:    "
            f"{previous_league.get('season')}"
        )

        print(
            f"Previous league:    "
            f"{previous_league.get('name')}"
        )

        if str(
            previous_league.get(
                "season"
            )
        ) != historical_season:
            print(
                "WARNING: previous "
                "league season does not "
                "match the audit season."
            )

            continue

        matchup_records = (
            sleeper.get_matchups(
                previous_league_id,
                week=week,
            )
        )

        if not matchup_records:
            print(
                "No historical matchup "
                "records returned."
            )

            continue

        first_record = (
            matchup_records[0]
        )

        print()
        print(
            "Historical matchup keys:"
        )

        print(
            "  "
            + ", ".join(
                sorted(
                    first_record.keys()
                )
            )
        )

        interesting_keys = [
            key
            for key
            in sorted(
                first_record.keys()
            )
            if (
                "point" in key.lower()
                or "score" in key.lower()
                or "player" in key.lower()
                or "starter" in key.lower()
            )
        ]

        print()
        print(
            "Potential scoring-related keys:"
        )

        for key in (
            interesting_keys
        ):
            value = (
                first_record.get(
                    key
                )
            )

            print(
                f"  {key}: "
                f"{type(value).__name__}"
            )

        print()
        print(
            "Starter PPR vs league "
            "team-score comparison:"
        )

        comparable = 0
        exact_matches = 0
        mismatches = 0
        missing_players = 0

        for matchup in (
            matchup_records
        ):
            roster_id = (
                matchup.get(
                    "roster_id"
                )
            )

            starters = (
                _valid_player_ids(
                    matchup.get(
                        "starters"
                    )
                )
            )

            league_points = (
                _effective_team_points(
                    matchup
                )
            )

            starter_points: list[
                float
            ] = []

            missing: list[
                str
            ] = []

            for player_id in (
                starters
            ):
                point_value = (
                    actual_ppr_points(
                        stat_lookup.get(
                            player_id
                        )
                    )
                )

                if point_value is None:
                    missing.append(
                        player_id
                    )

                else:
                    starter_points.append(
                        point_value
                    )

            if missing:
                missing_players += len(
                    missing
                )

                print(
                    f"  roster {roster_id}: "
                    f"cannot compare; "
                    f"missing pts_ppr for "
                    f"{missing}"
                )

                continue

            if league_points is None:
                print(
                    f"  roster {roster_id}: "
                    "league score missing"
                )

                continue

            ppr_total = sum(
                starter_points
            )

            difference = (
                ppr_total
                - league_points
            )

            comparable += 1

            if abs(
                difference
            ) <= 0.01:
                exact_matches += 1

            else:
                mismatches += 1

            print(
                f"  roster {roster_id}: "
                f"starter pts_ppr="
                f"{ppr_total:.2f} | "
                f"league score="
                f"{league_points:.2f} | "
                f"difference="
                f"{difference:+.2f}"
            )

        print()
        print(
            "Audit summary:"
        )

        print(
            f"  comparable teams: "
            f"{comparable}"
        )

        print(
            f"  exact matches:    "
            f"{exact_matches}"
        )

        print(
            f"  mismatches:       "
            f"{mismatches}"
        )

        print(
            f"  missing player "
            f"stat rows:         "
            f"{missing_players}"
        )

    print()
    print("=" * 78)
    print(
        "PROBE COMPLETE — "
        "nothing was written."
    )
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )