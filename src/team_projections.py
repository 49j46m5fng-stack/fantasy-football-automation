"""Resolve starter projections and aggregate fantasy-team projections."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.players import get_player_name
from src.projections import (
    PlayerProjection,
    get_projected_points,
)


class TeamProjectionError(ValueError):
    """Raised when a fantasy-team projection cannot be processed safely."""


@dataclass(frozen=True)
class ProjectionOverride:
    """Explicit correction for one player's weekly projection."""

    points: float
    reason: str


@dataclass(frozen=True)
class StarterProjection:
    """Resolved projection for one fantasy starting-lineup slot."""

    slot: int
    player_id: str | None
    player_name: str
    position: str | None
    points: float | None
    source: str
    reason: str | None = None


@dataclass(frozen=True)
class TeamProjection:
    """Aggregated fantasy-team projection."""

    roster_id: int
    projected_points: float | None
    known_projected_points: float
    complete: bool
    starters: tuple[StarterProjection, ...]
    warnings: tuple[str, ...]


def load_week_projection_overrides(
    path: Path,
    week: int,
) -> dict[str, ProjectionOverride]:
    """Load explicit player projection overrides for one week."""

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise TeamProjectionError(
            f"Could not read projection overrides: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise TeamProjectionError(
            "Projection override file must contain a JSON object"
        )

    if payload.get("schema_version") != 1:
        raise TeamProjectionError(
            "Unsupported projection override schema version"
        )

    weeks = payload.get("weeks", {})

    if not isinstance(weeks, dict):
        raise TeamProjectionError(
            "Projection override weeks must be a JSON object"
        )

    week_data = weeks.get(str(week), {})

    if not isinstance(week_data, dict):
        raise TeamProjectionError(
            f"Projection overrides for week {week} "
            "must be a JSON object"
        )

    overrides: dict[str, ProjectionOverride] = {}

    for player_id, raw_override in week_data.items():
        if not isinstance(raw_override, dict):
            raise TeamProjectionError(
                f"Projection override for {player_id} "
                "must be a JSON object"
            )

        points = raw_override.get("points")
        reason = raw_override.get("reason")

        if (
            isinstance(points, bool)
            or not isinstance(points, (int, float))
        ):
            raise TeamProjectionError(
                f"Projection override for {player_id} "
                "must contain numeric points"
            )

        if not isinstance(reason, str) or not reason.strip():
            raise TeamProjectionError(
                f"Projection override for {player_id} "
                "must contain a reason"
            )

        overrides[str(player_id)] = ProjectionOverride(
            points=float(points),
            reason=reason.strip(),
        )

    return overrides


def resolve_player_projection(
    slot: int,
    player_id: str,
    projection_lookup: dict[str, PlayerProjection],
    players: dict[str, dict[str, Any]],
    overrides: dict[str, ProjectionOverride],
    point_field: str = "pts_ppr",
) -> StarterProjection:
    """Resolve one starter to projected points without unsafe guessing."""

    player_metadata = players.get(player_id) or {}

    player_name = get_player_name(
        player_id,
        players,
    )

    raw_position = player_metadata.get("position")

    position = (
        str(raw_position)
        if raw_position is not None
        else None
    )

    override = overrides.get(player_id)

    if override is not None:
        return StarterProjection(
            slot=slot,
            player_id=player_id,
            player_name=player_name,
            position=position,
            points=override.points,
            source="manual_override",
            reason=override.reason,
        )

    projection = projection_lookup.get(player_id)

    if projection is None:
        return StarterProjection(
            slot=slot,
            player_id=player_id,
            player_name=player_name,
            position=position,
            points=None,
            source="missing_projection_record",
            reason="No weekly projection record was found.",
        )

    projected_points = get_projected_points(
        projection,
        point_field,
    )

    if projected_points is not None:
        return StarterProjection(
            slot=slot,
            player_id=player_id,
            player_name=player_name,
            position=position,
            points=projected_points,
            source=f"sleeper_{point_field}",
        )

    injury_status = player_metadata.get("injury_status")

    if (
        isinstance(injury_status, str)
        and injury_status.strip().lower() == "out"
    ):
        return StarterProjection(
            slot=slot,
            player_id=player_id,
            player_name=player_name,
            position=position,
            points=0.0,
            source="sleeper_out_zero",
            reason=(
                f"Sleeper reports injury_status="
                f"{injury_status!r} and provides no "
                f"{point_field} value."
            ),
        )

    return StarterProjection(
        slot=slot,
        player_id=player_id,
        player_name=player_name,
        position=position,
        points=None,
        source="missing_projected_points",
        reason=(
            f"Projection record exists but has no "
            f"{point_field}, and no safe zero-point rule applies."
        ),
    )


def calculate_team_projection(
    matchup_record: dict[str, Any],
    projection_lookup: dict[str, PlayerProjection],
    players: dict[str, dict[str, Any]],
    overrides: dict[str, ProjectionOverride],
    point_field: str = "pts_ppr",
) -> TeamProjection:
    """Calculate a starter-only fantasy-team projection."""

    roster_id = matchup_record.get("roster_id")

    if not isinstance(roster_id, int):
        raise TeamProjectionError(
            "Matchup record is missing a valid integer roster_id"
        )

    starters = matchup_record.get("starters") or []

    if not isinstance(starters, list):
        raise TeamProjectionError(
            "Matchup starters must be a list"
        )

    resolved_starters: list[StarterProjection] = []
    warnings: list[str] = []

    known_points = 0.0
    unresolved = False

    for slot, raw_player_id in enumerate(
        starters,
        start=1,
    ):
        if not raw_player_id or str(raw_player_id) == "0":
            resolved_starters.append(
                StarterProjection(
                    slot=slot,
                    player_id=None,
                    player_name="EMPTY SLOT",
                    position=None,
                    points=0.0,
                    source="empty_slot",
                    reason=(
                        "Starting lineup slot is empty "
                        "and contributes 0.0 points."
                    ),
                )
            )

            warnings.append(
                f"Roster {roster_id} starter slot "
                f"{slot} is empty."
            )

            continue

        player_id = str(raw_player_id)

        starter_projection = resolve_player_projection(
            slot=slot,
            player_id=player_id,
            projection_lookup=projection_lookup,
            players=players,
            overrides=overrides,
            point_field=point_field,
        )

        resolved_starters.append(
            starter_projection
        )

        if starter_projection.points is None:
            unresolved = True

            warnings.append(
                f"Roster {roster_id}: "
                f"{starter_projection.player_name} "
                f"has unresolved projection data."
            )

            continue

        known_points += starter_projection.points

    projected_points = (
        None
        if unresolved
        else known_points
    )

    return TeamProjection(
        roster_id=roster_id,
        projected_points=projected_points,
        known_projected_points=known_points,
        complete=not unresolved,
        starters=tuple(resolved_starters),
        warnings=tuple(warnings),
    )