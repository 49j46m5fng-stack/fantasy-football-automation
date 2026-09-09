"""Build a disposable TimBot preview context without freezing a baseline.

TEST ONLY.

This script:
- fetches current Sleeper league/users/rosters/matchups
- fetches current Sleeper projections
- builds one combined GOATs + DOATs JSON package
- writes only to data/test/
- never calls immutable baseline storage

The generated file must never be treated as an official baseline.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


CONFIG_PATH = Path("config.json")
PLAYER_CACHE_PATH = Path("data/cache/nfl_players.json")

OUTPUT_DIRECTORY = Path("data/test")

PROJECTION_URL = (
    "https://api.sleeper.com/projections/nfl/"
    "{season}/{week}"
)

SLEEPER_BASE_URL = "https://api.sleeper.app/v1"

USER_AGENT = "TimBot-Test-Context/1.0"


def load_json(path: Path) -> Any:
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
) -> Any:
    response = requests.get(
        url,
        params=params,
        headers={
            "User-Agent": USER_AGENT,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_players() -> dict[str, dict[str, Any]]:
    """Use local cached NFL player metadata when available."""

    if PLAYER_CACHE_PATH.exists():
        payload = load_json(
            PLAYER_CACHE_PATH
        )

        if isinstance(
            payload,
            dict,
        ):
            return payload

    payload = fetch_json(
        f"{SLEEPER_BASE_URL}/players/nfl"
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "Sleeper players endpoint "
            "did not return an object."
        )

    return payload


def player_name(
    player_id: str,
    players: dict[str, dict[str, Any]],
) -> str:
    if player_id in {
        "",
        "0",
    }:
        return "EMPTY SLOT"

    metadata = players.get(
        player_id
    )

    if not isinstance(
        metadata,
        dict,
    ):
        return player_id

    full_name = metadata.get(
        "full_name"
    )

    if (
        isinstance(
            full_name,
            str,
        )
        and full_name
    ):
        return full_name

    first_name = metadata.get(
        "first_name"
    )

    last_name = metadata.get(
        "last_name"
    )

    combined = " ".join(
        value
        for value
        in (
            first_name,
            last_name,
        )
        if isinstance(
            value,
            str,
        )
        and value
    )

    return (
        combined
        if combined
        else player_id
    )


def projection_lookup(
    season: str,
    week: int,
) -> dict[str, dict[str, Any]]:
    payload = fetch_json(
        PROJECTION_URL.format(
            season=season,
            week=week,
        ),
        params={
            "season_type": "regular",
        },
    )

    if not isinstance(
        payload,
        list,
    ):
        raise RuntimeError(
            "Projection endpoint "
            "did not return a list."
        )

    result: dict[
        str,
        dict[str, Any],
    ] = {}

    for record in payload:
        if not isinstance(
            record,
            dict,
        ):
            continue

        player_id = record.get(
            "player_id"
        )

        if player_id is None:
            continue

        result[
            str(player_id)
        ] = record

    return result


def projected_points(
    player_id: str,
    projections: dict[str, dict[str, Any]],
) -> float | None:
    record = projections.get(
        player_id
    )

    if not isinstance(
        record,
        dict,
    ):
        return None

    stats = record.get(
        "stats"
    )

    if not isinstance(
        stats,
        dict,
    ):
        return None

    value = stats.get(
        "pts_ppr"
    )

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

    return round(
        float(value),
        2,
    )


def build_league_context(
    *,
    league_key: str,
    league_config: dict[str, Any],
    season: str,
    week: int,
    players: dict[str, dict[str, Any]],
    projections: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    league_id = str(
        league_config[
            "league_id"
        ]
    )

    league = fetch_json(
        f"{SLEEPER_BASE_URL}/league/{league_id}"
    )

    users = fetch_json(
        f"{SLEEPER_BASE_URL}/league/"
        f"{league_id}/users"
    )

    rosters = fetch_json(
        f"{SLEEPER_BASE_URL}/league/"
        f"{league_id}/rosters"
    )

    matchup_records = fetch_json(
        f"{SLEEPER_BASE_URL}/league/"
        f"{league_id}/matchups/{week}"
    )

    if not all(
        isinstance(
            payload,
            list,
        )
        for payload
        in (
            users,
            rosters,
            matchup_records,
        )
    ):
        raise RuntimeError(
            f"Unexpected Sleeper response "
            f"for {league_key}."
        )

    user_lookup = {
        str(
            user.get(
                "user_id"
            )
        ): user
        for user
        in users
        if isinstance(
            user,
            dict,
        )
    }

    roster_lookup = {
        int(
            roster[
                "roster_id"
            ]
        ): roster
        for roster
        in rosters
        if (
            isinstance(
                roster,
                dict,
            )
            and isinstance(
                roster.get(
                    "roster_id"
                ),
                int,
            )
        )
    }

    matchup_lookup: dict[
        int,
        dict[str, Any],
    ] = {
        int(
            record[
                "roster_id"
            ]
        ): record
        for record
        in matchup_records
        if (
            isinstance(
                record,
                dict,
            )
            and isinstance(
                record.get(
                    "roster_id"
                ),
                int,
            )
        )
    }

    teams: list[
        dict[str, Any]
    ] = []

    for roster_id, roster in sorted(
        roster_lookup.items()
    ):
        owner_id = roster.get(
            "owner_id"
        )

        user = user_lookup.get(
            str(owner_id),
            {},
        )

        manager = (
            user.get(
                "display_name"
            )
            or user.get(
                "username"
            )
            or f"Roster {roster_id}"
        )

        matchup = matchup_lookup.get(
            roster_id,
            {},
        )

        starter_ids = matchup.get(
            "starters",
            [],
        )

        if not isinstance(
            starter_ids,
            list,
        ):
            starter_ids = []

        starter_records: list[
            dict[str, Any]
        ] = []

        projection_total = 0.0
        projection_complete = True

        for raw_player_id in starter_ids:
            if raw_player_id is None:
                player_id = "0"
            else:
                player_id = str(
                    raw_player_id
                )

            points = projected_points(
                player_id,
                projections,
            )

            if points is None:
                projection_complete = False
            else:
                projection_total += points

            metadata = players.get(
                player_id,
                {},
            )

            position = (
                metadata.get(
                    "position"
                )
                if isinstance(
                    metadata,
                    dict,
                )
                else None
            )

            starter_records.append(
                {
                    "player_id": player_id,
                    "player_name": player_name(
                        player_id,
                        players,
                    ),
                    "position": position,
                    "projected_points": points,
                }
            )

        teams.append(
            {
                "roster_id": roster_id,
                "manager": manager,
                "owner_id": owner_id,
                "matchup_id": matchup.get(
                    "matchup_id"
                ),
                "projected_team_points": (
                    round(
                        projection_total,
                        2,
                    )
                    if projection_complete
                    else None
                ),
                "projection_complete": (
                    projection_complete
                ),
                "starters": starter_records,
            }
        )

    grouped: dict[
        int,
        list[dict[str, Any]],
    ] = {}

    for team in teams:
        matchup_id = team.get(
            "matchup_id"
        )

        if isinstance(
            matchup_id,
            int,
        ):
            grouped.setdefault(
                matchup_id,
                [],
            ).append(
                team
            )

    matchups: list[
        dict[str, Any]
    ] = []

    for matchup_id, matchup_teams in sorted(
        grouped.items()
    ):
        if len(
            matchup_teams
        ) != 2:
            continue

        left, right = matchup_teams

        left_projection = left.get(
            "projected_team_points"
        )

        right_projection = right.get(
            "projected_team_points"
        )

        projected_margin = None

        if (
            isinstance(
                left_projection,
                (int, float),
            )
            and isinstance(
                right_projection,
                (int, float),
            )
        ):
            projected_margin = round(
                abs(
                    float(
                        left_projection
                    )
                    - float(
                        right_projection
                    )
                ),
                2,
            )

        matchups.append(
            {
                "matchup_id": matchup_id,
                "team_1": left,
                "team_2": right,
                "projected_margin": (
                    projected_margin
                ),
            }
        )

    return {
        "league_key": league_key,
        "league_name": (
            league_config.get(
                "name"
            )
            or league.get(
                "name"
            )
            or league_key
        ),
        "league_id": league_id,
        "team_count": len(
            teams
        ),
        "matchups": matchups,
    }


def main() -> int:
    config = load_json(
        CONFIG_PATH
    )

    season = str(
        config.get(
            "season",
            "2026",
        )
    )

    week = 1

    leagues = config.get(
        "leagues"
    )

    if not isinstance(
        leagues,
        dict,
    ):
        raise RuntimeError(
            "config.json is missing leagues."
        )

    print(
        "Loading player metadata..."
    )

    players = get_players()

    print(
        "Fetching current Week 1 projections..."
    )

    projections = projection_lookup(
        season,
        week,
    )

    league_contexts: list[
        dict[str, Any]
    ] = []

    for league_key in (
        "goats",
        "doats",
    ):
        league_config = leagues.get(
            league_key
        )

        if not isinstance(
            league_config,
            dict,
        ):
            raise RuntimeError(
                f"Missing league config "
                f"for {league_key}."
            )

        print(
            f"Building TEST context "
            f"for {league_key.upper()}..."
        )

        league_contexts.append(
            build_league_context(
                league_key=league_key,
                league_config=(
                    league_config
                ),
                season=season,
                week=week,
                players=players,
                projections=(
                    projections
                ),
            )
        )

    payload = {
        "schema_version": 1,
        "test_only": True,
        "official_baseline": False,
        "authoritative_for_analytics": False,
        "warning": (
            "TEMPORARY TIMBOT TEST CONTEXT. "
            "This is not the official frozen baseline "
            "and must not be used for historical analytics."
        ),
        "season": season,
        "week": week,
        "stage": "baseline_test",
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "purpose": (
            "Test TimBot preview writing, "
            "formatting, matchup coverage, and tone."
        ),
        "leagues": league_contexts,
    }

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        OUTPUT_DIRECTORY
        / f"TEST_week_{week:02d}_timbot_preview.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            sort_keys=False,
        )

        file.write(
            "\n"
        )

    print()
    print("=" * 72)

    print(
        "TIMBOT TEST CONTEXT CREATED"
    )

    print("=" * 72)

    print(
        f"Output: {output_path}"
    )

    print(
        "Official baseline modified: NO"
    )

    print(
        "Safe for TimBot testing: YES"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )