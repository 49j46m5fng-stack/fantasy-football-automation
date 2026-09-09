"""Retrieve and normalize actual NFL player statistics from Sleeper.

The bulk Sleeper stats feed is not part of the currently documented
core Sleeper API, so this module deliberately isolates its wire format
from the rest of the application.

The normalized records preserve raw statistics and never silently turn
a missing fantasy-points value into zero.
"""

from dataclasses import dataclass
from typing import Any

import requests


STATS_BASE_URL = (
    "https://api.sleeper.com/stats/nfl"
)


class PlayerStatsError(RuntimeError):
    """Raised when player-stat data cannot be retrieved or normalized."""


@dataclass(frozen=True)
class PlayerWeekStat:
    """Normalized actual statistics for one player and NFL week."""

    player_id: str
    season: str
    week: int
    stats: dict[str, Any]
    category: str | None = None
    company: str | None = None


_METADATA_FIELDS = {
    "player_id",
    "player",
    "season",
    "week",
    "season_type",
    "category",
    "company",
    "sport",
    "team",
    "opponent",
    "date",
    "game_id",
    "last_modified",
    "updated_at",
}


def _normalize_stats_dict(
    row: dict[str, Any],
) -> dict[str, Any]:
    """Extract the actual statistic mapping from one Sleeper record."""

    nested_stats = row.get(
        "stats"
    )

    if nested_stats is not None:
        if not isinstance(
            nested_stats,
            dict,
        ):
            raise PlayerStatsError(
                "Player stats field must be an object"
            )

        return dict(
            nested_stats
        )

    # Some Sleeper stats responses expose the counting statistics
    # directly on the player row rather than under "stats".
    return {
        key: value
        for key, value
        in row.items()
        if key
        not in _METADATA_FIELDS
    }


def _normalize_one_record(
    raw: dict[str, Any],
    season: str,
    week: int,
    player_id_hint: str | None = None,
) -> PlayerWeekStat | None:
    """Normalize one stats row while ignoring team aggregate records."""

    raw_player_id = raw.get(
        "player_id",
        player_id_hint,
    )

    if raw_player_id is None:
        raise PlayerStatsError(
            "Stats record is missing player_id"
        )

    player_id = str(
        raw_player_id
    )

    if not player_id:
        raise PlayerStatsError(
            "Stats record contains an empty player_id"
        )

    # The bulk stats feed can contain TEAM_XXX aggregate rows.
    # They are not fantasy D/ST player IDs and must not enter
    # player-level analytics.
    if player_id.startswith(
        "TEAM_"
    ):
        return None

    category = raw.get(
        "category"
    )

    if (
        category is not None
        and not isinstance(
            category,
            str,
        )
    ):
        raise PlayerStatsError(
            f"Stats category for {player_id} "
            "must be a string or null"
        )

    # Only actual-stat rows belong in this module.
    # Older response shapes may omit category entirely.
    if (
        category is not None
        and category != "stat"
    ):
        return None

    company = raw.get(
        "company"
    )

    if (
        company is not None
        and not isinstance(
            company,
            str,
        )
    ):
        raise PlayerStatsError(
            f"Stats company for {player_id} "
            "must be a string or null"
        )

    return PlayerWeekStat(
        player_id=player_id,
        season=season,
        week=week,
        stats=_normalize_stats_dict(
            raw
        ),
        category=category,
        company=company,
    )


def parse_week_stats_payload(
    payload: Any,
    season: str,
    week: int,
) -> list[PlayerWeekStat]:
    """Normalize supported Sleeper bulk-stats response shapes."""

    if not season:
        raise PlayerStatsError(
            "season cannot be empty"
        )

    if week < 1:
        raise PlayerStatsError(
            "week must be at least 1"
        )

    normalized: list[
        PlayerWeekStat
    ] = []

    if isinstance(
        payload,
        list,
    ):
        for raw in payload:
            if not isinstance(
                raw,
                dict,
            ):
                raise PlayerStatsError(
                    "Stats list entries must be objects"
                )

            record = (
                _normalize_one_record(
                    raw=raw,
                    season=season,
                    week=week,
                )
            )

            if record is not None:
                normalized.append(
                    record
                )

        return normalized

    if isinstance(
        payload,
        dict,
    ):
        for key, raw in (
            payload.items()
        ):
            if not isinstance(
                raw,
                dict,
            ):
                raise PlayerStatsError(
                    "Stats mapping entries "
                    "must be objects"
                )

            record = (
                _normalize_one_record(
                    raw=raw,
                    season=season,
                    week=week,
                    player_id_hint=str(
                        key
                    ),
                )
            )

            if record is not None:
                normalized.append(
                    record
                )

        return normalized

    raise PlayerStatsError(
        "Sleeper stats payload must "
        "be a list or object"
    )


def build_week_stat_lookup(
    records: list[PlayerWeekStat],
) -> dict[str, PlayerWeekStat]:
    """Build player_id -> actual stat while rejecting duplicates."""

    lookup: dict[
        str,
        PlayerWeekStat,
    ] = {}

    for record in records:
        if (
            record.player_id
            in lookup
        ):
            raise PlayerStatsError(
                "Duplicate actual-stat record "
                f"for player {record.player_id}"
            )

        lookup[
            record.player_id
        ] = record

    return lookup


def actual_ppr_points(
    record: PlayerWeekStat | None,
) -> float | None:
    """Return actual PPR points without treating missing data as zero."""

    if record is None:
        return None

    value = record.stats.get(
        "pts_ppr"
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
        raise PlayerStatsError(
            f"pts_ppr for player "
            f"{record.player_id} must "
            "be numeric or null"
        )

    return float(
        value
    )


class SleeperPlayerStatsProvider:
    """Client for Sleeper's bulk weekly NFL actual-stat feed."""

    def __init__(
        self,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.session = (
            session
            if session is not None
            else requests.Session()
        )

    def get_week_stats(
        self,
        season: str,
        week: int,
        season_type: str = "regular",
    ) -> list[PlayerWeekStat]:
        """Fetch and normalize actual statistics for one NFL week."""

        if not season:
            raise PlayerStatsError(
                "season cannot be empty"
            )

        if week < 1:
            raise PlayerStatsError(
                "week must be at least 1"
            )

        if season_type not in {
            "regular",
            "post",
            "pre",
        }:
            raise PlayerStatsError(
                f"Unsupported season_type: "
                f"{season_type}"
            )

        url = (
            f"{STATS_BASE_URL}/"
            f"{season}/{week}"
        )

        try:
            response = (
                self.session.get(
                    url,
                    params={
                        "season_type": (
                            season_type
                        ),
                    },
                    timeout=(
                        self.timeout
                    ),
                )
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise PlayerStatsError(
                "Sleeper player-stats "
                f"request failed: {url}"
            ) from exc

        try:
            payload = (
                response.json()
            )

        except ValueError as exc:
            raise PlayerStatsError(
                "Sleeper player-stats "
                "response was not valid JSON"
            ) from exc

        return (
            parse_week_stats_payload(
                payload=payload,
                season=season,
                week=week,
            )
        )