"""Access and normalize Sleeper's unofficial projection feed."""

from dataclasses import dataclass
from typing import Any

import requests


PROJECTIONS_BASE_URL = "https://api.sleeper.com"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; fantasy-football-automation/0.1)"
)


class ProjectionAPIError(RuntimeError):
    """Raised when projection data cannot be retrieved safely."""


@dataclass(frozen=True)
class PlayerProjection:
    """Normalized projection record for one player and week."""

    player_id: str
    season: str
    week: int
    stats: dict[str, Any]


def _build_projection(
    player_id: str,
    raw_record: dict[str, Any],
    season: str,
    week: int,
) -> PlayerProjection:
    """Convert one raw projection record into our internal format."""

    if not player_id:
        raise ProjectionAPIError(
            "Projection record is missing player_id"
        )

    nested_stats = raw_record.get("stats")

    if nested_stats is not None:
        if not isinstance(nested_stats, dict):
            raise ProjectionAPIError(
                f"Projection stats for {player_id} "
                "must be a JSON object"
            )

        stats = dict(nested_stats)
    else:
        # Some versions of the unofficial feed put projected
        # statistics directly on the player-ID record.
        stats = dict(raw_record)

    return PlayerProjection(
        player_id=str(player_id),
        season=str(season),
        week=week,
        stats=stats,
    )


def normalize_week_projection_payload(
    payload: Any,
    season: str,
    week: int,
) -> list[PlayerProjection]:
    """Normalize known Sleeper projection response shapes."""

    projections: list[PlayerProjection] = []

    if isinstance(payload, list):
        for record in payload:
            if not isinstance(record, dict):
                raise ProjectionAPIError(
                    "Projection list contains a non-object record"
                )

            player_id = record.get("player_id")

            if player_id is None:
                player = record.get("player")

                if isinstance(player, dict):
                    player_id = player.get("player_id")

            if player_id is None:
                raise ProjectionAPIError(
                    "Projection record is missing player_id"
                )

            projections.append(
                _build_projection(
                    str(player_id),
                    record,
                    season,
                    week,
                )
            )

        return projections

    if isinstance(payload, dict):
        for player_id, record in payload.items():
            if not isinstance(player_id, str):
                raise ProjectionAPIError(
                    "Projection map contains a non-string player ID"
                )

            if not isinstance(record, dict):
                raise ProjectionAPIError(
                    f"Projection record for {player_id} "
                    "is not a JSON object"
                )

            projections.append(
                _build_projection(
                    player_id,
                    record,
                    season,
                    week,
                )
            )

        return projections

    raise ProjectionAPIError(
        "Expected projection response to be a JSON list or object"
    )


class SleeperProjectionProvider:
    """Retrieve weekly projections from Sleeper's unofficial feed."""

    def __init__(
        self,
        base_url: str = PROJECTIONS_BASE_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_week_projections(
        self,
        season: str,
        week: int,
        season_type: str = "regular",
    ) -> list[PlayerProjection]:
        """Retrieve and normalize projections for one NFL week."""

        if not season:
            raise ValueError("season cannot be empty")

        if week < 1:
            raise ValueError("week must be at least 1")

        if not season_type:
            raise ValueError("season_type cannot be empty")

        url = (
            f"{self.base_url}/projections/nfl/"
            f"{season}/{week}"
        )

        try:
            response = requests.get(
                url,
                params={
                    "season_type": season_type,
                },
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                },
                timeout=self.timeout_seconds,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise ProjectionAPIError(
                f"Projection request failed for {url}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProjectionAPIError(
                f"Projection feed returned invalid JSON for {url}"
            ) from exc

        return normalize_week_projection_payload(
            payload,
            season=season,
            week=week,
        )


def get_projected_points(
    projection: PlayerProjection,
    field: str,
) -> float | None:
    """Return one projected point value without treating missing as zero."""

    value = projection.stats.get(field)

    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise ProjectionAPIError(
            f"Projection field {field!r} for "
            f"{projection.player_id} is not numeric"
        )

    return float(value)