"""Calculate player-level points remaining for a fantasy matchup."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.nfl_games import (
    TeamGameState,
    normalize_team_abbreviation,
)
from src.players import get_player_name
from src.projections import PlayerProjection
from src.team_projections import (
    ProjectionOverride,
    resolve_player_projection,
)


class RemainingProjectionError(ValueError):
    """Raised when remaining-point data cannot be calculated safely."""


@dataclass(frozen=True)
class RemainingStarter:
    """Current Monday state for one fantasy starter."""

    slot: int
    player_id: str | None
    player_name: str
    position: str | None
    nfl_team: str | None

    actual_points: float | None
    actual_source: str | None

    fresh_projection: float
    projection_source: str

    game_state: str
    game_id: str | None
    opponent: str | None
    kickoff: datetime | None

    still_to_play: bool
    remaining_projection: float | None

    reason: str | None = None


@dataclass(frozen=True)
class RemainingTeamProjection:
    """Remaining-point estimate for one fantasy team."""

    roster_id: int

    current_points: float

    remaining_projected_points: float | None
    projected_final_estimate: float | None

    remaining_player_count: int

    starters: tuple[RemainingStarter, ...]
    warnings: tuple[str, ...]


def _numeric_points(
    value: Any,
) -> float | None:
    """Return a numeric points value or None."""

    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float),
        )
    ):
        return None

    return float(value)


def _player_team(
    player_id: str,
    player_metadata: dict[str, Any],
) -> str | None:
    """Resolve the NFL team for one player."""

    raw_team = player_metadata.get(
        "team"
    )

    if (
        isinstance(raw_team, str)
        and raw_team.strip()
    ):
        return normalize_team_abbreviation(
            raw_team
        )

    position = player_metadata.get(
        "position"
    )

    if (
        isinstance(position, str)
        and position.upper() == "DEF"
    ):
        return normalize_team_abbreviation(
            player_id
        )

    return None


def _player_actual_points(
    matchup_record: dict[str, Any],
    player_id: str,
    game_state: str,
) -> tuple[
    float | None,
    str | None,
]:
    """Resolve current Sleeper points for one player."""

    players_points = matchup_record.get(
        "players_points"
    )

    if isinstance(
        players_points,
        dict,
    ):
        raw_points = players_points.get(
            player_id
        )

        points = _numeric_points(
            raw_points
        )

        if points is not None:
            return (
                points,
                "sleeper_matchup_players_points",
            )

    # A scheduled game has not started yet, so an absent
    # live player total is safely zero at this checkpoint.
    if game_state == "scheduled":
        return (
            0.0,
            "not_started_zero",
        )

    return (
        None,
        None,
    )


def _game_state_for_player(
    nfl_team: str | None,
    team_states: dict[
        str,
        TeamGameState,
    ],
) -> TeamGameState | None:
    """Resolve game state from the player's NFL team."""

    if nfl_team is None:
        return None

    return team_states.get(
        nfl_team
    )


def build_remaining_team_projection(
    matchup_record: dict[str, Any],
    *,
    current_points: float,
    projection_lookup: dict[
        str,
        PlayerProjection,
    ],
    players: dict[
        str,
        dict[str, Any],
    ],
    overrides: dict[
        str,
        ProjectionOverride,
    ],
    team_states: dict[
        str,
        TeamGameState,
    ],
    point_field: str = "pts_ppr",
) -> RemainingTeamProjection:
    """Build Monday/MNF remaining-point data for one fantasy team."""

    roster_id = matchup_record.get(
        "roster_id"
    )

    if not isinstance(
        roster_id,
        int,
    ):
        raise RemainingProjectionError(
            "Matchup record is missing a valid roster_id"
        )

    if (
        isinstance(current_points, bool)
        or not isinstance(
            current_points,
            (int, float),
        )
    ):
        raise RemainingProjectionError(
            "current_points must be numeric"
        )

    starters = matchup_record.get(
        "starters"
    )

    if not isinstance(
        starters,
        list,
    ):
        raise RemainingProjectionError(
            "Matchup starters must be a list"
        )

    resolved: list[
        RemainingStarter
    ] = []

    warnings: list[str] = []

    remaining_total = 0.0
    remaining_unresolved = False
    remaining_player_count = 0

    for slot, raw_player_id in enumerate(
        starters,
        start=1,
    ):
        if (
            raw_player_id is None
            or str(raw_player_id) == "0"
            or str(raw_player_id) == ""
        ):
            resolved.append(
                RemainingStarter(
                    slot=slot,
                    player_id=None,
                    player_name="EMPTY SLOT",
                    position=None,
                    nfl_team=None,
                    actual_points=0.0,
                    actual_source="empty_slot",
                    fresh_projection=0.0,
                    projection_source="empty_slot",
                    game_state="empty_slot",
                    game_id=None,
                    opponent=None,
                    kickoff=None,
                    still_to_play=False,
                    remaining_projection=0.0,
                    reason=(
                        "Empty starter slot contributes "
                        "0.0 remaining points."
                    ),
                )
            )

            continue

        player_id = str(
            raw_player_id
        )

        metadata = players.get(
            player_id
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        player_name = get_player_name(
            player_id,
            players,
        )

        raw_position = metadata.get(
            "position"
        )

        position = (
            str(raw_position)
            if raw_position is not None
            else None
        )

        nfl_team = _player_team(
            player_id,
            metadata,
        )

        starter_projection = (
            resolve_player_projection(
                slot=slot,
                player_id=player_id,
                projection_lookup=projection_lookup,
                players=players,
                overrides=overrides,
                point_field=point_field,
            )
        )

        if starter_projection.points is None:
            raise RemainingProjectionError(
                "Projection resolver returned "
                f"None for player {player_id}; "
                "missing projections must resolve "
                "to 0.0 before remaining-point analysis."
            )

        fresh_projection = float(
            starter_projection.points
        )

        game = _game_state_for_player(
            nfl_team,
            team_states,
        )

        if game is None:
            game_state = "unknown"
            game_id = None
            opponent = None
            kickoff = None

        else:
            game_state = game.status
            game_id = game.game_id
            opponent = game.opponent
            kickoff = game.kickoff

        actual_points, actual_source = (
            _player_actual_points(
                matchup_record,
                player_id,
                game_state,
            )
        )

        still_to_play = False
        remaining_projection: float | None

        if game_state == "scheduled":
            still_to_play = True

            remaining_projection = (
                fresh_projection
            )

            remaining_player_count += 1

            remaining_total += (
                remaining_projection
            )

        elif game_state == "final":
            remaining_projection = 0.0

        elif game_state == "in_progress":
            remaining_projection = None
            remaining_unresolved = True

            warnings.append(
                f"Roster {roster_id}: "
                f"{player_name} is currently playing; "
                "full-game projection cannot be treated "
                "as remaining projection."
            )

        else:
            remaining_projection = None
            remaining_unresolved = True

            warnings.append(
                f"Roster {roster_id}: "
                f"{player_name} has unresolved NFL "
                "game state."
            )

        if (
            actual_points is None
            and game_state == "final"
        ):
            warnings.append(
                f"Roster {roster_id}: "
                f"{player_name} has no player-level "
                "actual points in the matchup record."
            )

        resolved.append(
            RemainingStarter(
                slot=slot,
                player_id=player_id,
                player_name=player_name,
                position=position,
                nfl_team=nfl_team,
                actual_points=actual_points,
                actual_source=actual_source,
                fresh_projection=(
                    fresh_projection
                ),
                projection_source=(
                    starter_projection.source
                ),
                game_state=game_state,
                game_id=game_id,
                opponent=opponent,
                kickoff=kickoff,
                still_to_play=still_to_play,
                remaining_projection=(
                    remaining_projection
                ),
                reason=(
                    starter_projection.reason
                ),
            )
        )

    if remaining_unresolved:
        remaining_projected_points = None
        projected_final_estimate = None

    else:
        remaining_projected_points = round(
            remaining_total,
            2,
        )

        projected_final_estimate = round(
            float(current_points)
            + remaining_total,
            2,
        )

    return RemainingTeamProjection(
        roster_id=roster_id,
        current_points=round(
            float(current_points),
            2,
        ),
        remaining_projected_points=(
            remaining_projected_points
        ),
        projected_final_estimate=(
            projected_final_estimate
        ),
        remaining_player_count=(
            remaining_player_count
        ),
        starters=tuple(
            resolved
        ),
        warnings=tuple(
            warnings
        ),
    )