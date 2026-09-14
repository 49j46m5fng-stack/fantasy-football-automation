"""Read-only Week 1 MNF remaining-player probe."""

import json
from pathlib import Path

from src.nfl_games import ESPNNFLGameProvider
from src.players import get_player_map
from src.projections import (
    SleeperProjectionProvider,
    build_projection_lookup,
)
from src.sleeper import SleeperClient
from src.sunday_remaining import build_remaining_lookup
from src.team_projections import (
    load_week_projection_overrides,
)


SEASON = "2026"
WEEK = 1


def load_config() -> dict:
    return json.loads(
        Path("config.json").read_text(
            encoding="utf-8"
        )
    )


def main() -> int:
    config = load_config()

    sleeper = SleeperClient()

    print("Refreshing player metadata...")

    players = get_player_map(
        sleeper,
        refresh=True,
    )

    print("Fetching fresh Week 1 projections...")

    projection_records = (
        SleeperProjectionProvider()
        .get_week_projections(
            season=SEASON,
            week=WEEK,
        )
    )

    projection_lookup = (
        build_projection_lookup(
            projection_records
        )
    )

    overrides = (
        load_week_projection_overrides(
            Path(
                f"data/{SEASON}/"
                "projection_overrides.json"
            ),
            week=WEEK,
        )
    )

    print("Fetching NFL game states...")

    team_states = (
        ESPNNFLGameProvider()
        .get_team_states(
            season=int(SEASON),
            week=WEEK,
        )
    )

    print(
        f"NFL team states: {len(team_states)}"
    )

    for league_key in (
        "goats",
        "doats",
    ):
        league_config = (
            config[
                "leagues"
            ][
                league_key
            ]
        )

        league_id = str(
            league_config[
                "league_id"
            ]
        )

        league_name = (
            league_config[
                "name"
            ]
        )

        users = sleeper.get_users(
            league_id
        )

        rosters = sleeper.get_rosters(
            league_id
        )

        matchups = sleeper.get_matchups(
            league_id,
            week=WEEK,
        )

        users_by_id = {
            str(
                user.get(
                    "user_id"
                )
            ): user
            for user in users
        }

        manager_lookup = {}

        for roster in rosters:
            roster_id = roster.get(
                "roster_id"
            )

            owner_id = str(
                roster.get(
                    "owner_id"
                )
            )

            user = users_by_id.get(
                owner_id,
                {},
            )

            manager_lookup[
                roster_id
            ] = (
                user.get(
                    "display_name"
                )
                or user.get(
                    "username"
                )
                or "UNKNOWN"
            )

        remaining = (
            build_remaining_lookup(
                matchup_records=matchups,
                projection_lookup=(
                    projection_lookup
                ),
                players=players,
                overrides=overrides,
                team_states=team_states,
            )
        )

        print()
        print("=" * 80)
        print(
            f"{league_name.upper()} "
            "— MNF REMAINING"
        )
        print("=" * 80)

        teams_with_players_left = 0
        total_remaining_players = 0

        for roster_id, result in sorted(
            remaining.items()
        ):
            manager = (
                manager_lookup.get(
                    roster_id,
                    "UNKNOWN",
                )
            )

            if (
                result.remaining_player_count
                <= 0
            ):
                continue

            teams_with_players_left += 1

            total_remaining_players += (
                result.remaining_player_count
            )

            print()
            print(
                f"{manager} "
                f"(roster {roster_id})"
            )

            print(
                f"  current points: "
                f"{result.current_points:.2f}"
            )

            print(
                "  remaining projected: "
                f"{result.remaining_projected_points}"
            )

            print(
                "  projected final: "
                f"{result.projected_final_estimate}"
            )

            print(
                "  remaining players:"
            )

            for starter in (
                result.starters
            ):
                if not starter.still_to_play:
                    continue

                print(
                    "    "
                    f"{starter.player_name}"
                    f" | {starter.position}"
                    f" | {starter.nfl_team}"
                    f" | proj="
                    f"{starter.remaining_projection}"
                )

        print()
        print(
            f"Teams with players remaining: "
            f"{teams_with_players_left}"
        )

        print(
            f"Remaining players: "
            f"{total_remaining_players}"
        )

    print()
    print("=" * 80)
    print("PROBE COMPLETE — nothing was written.")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )