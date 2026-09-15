"""Build deterministic AI-agent context from immutable fantasy snapshots."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.comparison import (
    TeamSnapshotComparison,
    compare_baseline_to_sunday,
)
from src.storage import (
    build_snapshot_path,
    read_snapshot,
)


AGENT_CONTEXT_SCHEMA_VERSION = 1

SUPPORTED_CONTEXT_STAGES = {
    "baseline",
    "sunday",
}


class AgentContextError(ValueError):
    """Raised when AI-agent context cannot be built safely."""


def agent_context_path(
    data_root: Path,
    season: str,
    week: int,
    stage: str,
) -> Path:
    """Return the canonical derived AI-context path."""

    if week < 1:
        raise AgentContextError(
            "week must be at least 1"
        )

    if stage not in {
        "baseline",
        "sunday",
        "final",
    }:
        raise AgentContextError(
            f"Unsupported context stage: {stage}"
        )

    return (
        data_root
        / season
        / "agent"
        / (
            f"week_{week:02d}_"
            f"{stage}.json"
        )
    )


def _sha256_file(
    path: Path,
) -> str:
    """Return SHA-256 for one source snapshot."""

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _optional_number(
    value: Any,
    description: str,
) -> float | None:
    """Read optional numeric values without inventing zero."""

    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise AgentContextError(
            f"{description} must be numeric or null"
        )

    return float(
        value
    )


def _validate_snapshot_identity(
    snapshot: dict[str, Any],
    season: str,
    week: int,
    league_key: str,
    stage: str,
) -> None:
    """Require a source snapshot to match its requested identity."""

    expected = {
        "season": season,
        "week": week,
        "league_key": league_key,
        "stage": stage,
    }

    for field, value in (
        expected.items()
    ):
        if (
            snapshot.get(field)
            != value
        ):
            raise AgentContextError(
                f"Snapshot identity mismatch "
                f"for {field}: expected "
                f"{value!r}, found "
                f"{snapshot.get(field)!r}"
            )


def _source_descriptor(
    path: Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Describe one authoritative input snapshot."""

    return {
        "path": path.as_posix(),
        "sha256": _sha256_file(
            path
        ),
        "created_at": snapshot.get(
            "created_at"
        ),
        "schema_version": snapshot.get(
            "schema_version"
        ),
        "stage": snapshot.get(
            "stage"
        ),
    }


def _player_context(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Return compact stored player facts suitable for an AI agent."""

    if not isinstance(
        record,
        dict,
    ):
        raise AgentContextError(
            "Player record must be an object"
        )

    result = {
        "player_id": record.get(
            "player_id"
        ),
        "player_name": record.get(
            "player_name"
        ),
        "position": record.get(
            "position"
        ),
        "team": record.get(
            "team"
        ),
        "injury_status": record.get(
            "injury_status"
        ),
        "projected_points": record.get(
            "projected_points"
        ),
        "projection_source": record.get(
            "projection_source"
        ),
        "projection_reason": record.get(
            "projection_reason"
        ),
    }

    if "slot" in record:
        result["slot"] = record.get(
            "slot"
        )

    return result


def _team_lookup(
    data: dict[str, Any],
    description: str,
) -> dict[int, dict[str, Any]]:
    """Build roster ID -> team while rejecting duplicates."""

    teams = data.get(
        "teams"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise AgentContextError(
            f"{description} is missing teams"
        )

    lookup: dict[
        int,
        dict[str, Any],
    ] = {}

    for team in teams:
        if not isinstance(
            team,
            dict,
        ):
            raise AgentContextError(
                f"{description} team must "
                "be an object"
            )

        roster_id = team.get(
            "roster_id"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise AgentContextError(
                f"{description} team is "
                "missing roster_id"
            )

        if roster_id in lookup:
            raise AgentContextError(
                f"{description} contains "
                f"duplicate roster_id "
                f"{roster_id}"
            )

        lookup[
            roster_id
        ] = team

    return lookup


def _special_projection_notes(
    team: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return starter projections that required special handling."""

    starters = team.get(
        "starters",
        [],
    )

    if not isinstance(
        starters,
        list,
    ):
        raise AgentContextError(
            "Team starters must be a list"
        )

    notes: list[
        dict[str, Any]
    ] = []

    for starter in starters:
        if not isinstance(
            starter,
            dict,
        ):
            raise AgentContextError(
                "Starter must be an object"
            )

        source = starter.get(
            "projection_source"
        )

        if source == "sleeper_pts_ppr":
            continue

        notes.append(
            {
                "slot": starter.get(
                    "slot"
                ),
                "player_id": starter.get(
                    "player_id"
                ),
                "player_name": starter.get(
                    "player_name"
                ),
                "projected_points": (
                    starter.get(
                        "projected_points"
                    )
                ),
                "projection_source": (
                    source
                ),
                "projection_reason": (
                    starter.get(
                        "projection_reason"
                    )
                ),
            }
        )

    return notes


def _baseline_team_context(
    team: dict[str, Any],
) -> dict[str, Any]:
    """Build AI-facing baseline facts for one roster."""

    starters = team.get(
        "starters",
        [],
    )

    rostered_players = team.get(
        "rostered_players",
        [],
    )

    if not isinstance(
        starters,
        list,
    ):
        raise AgentContextError(
            "Baseline starters must be a list"
        )

    if not isinstance(
        rostered_players,
        list,
    ):
        raise AgentContextError(
            "Baseline rostered_players "
            "must be a list"
        )

    return {
        "roster_id": team.get(
            "roster_id"
        ),
        "owner_id": team.get(
            "owner_id"
        ),
        "manager_name": team.get(
            "manager_name"
        ),
        "matchup_id": team.get(
            "matchup_id"
        ),
        "opponent_roster_id": (
            team.get(
                "opponent_roster_id"
            )
        ),
        "baseline_projection": (
            team.get(
                "baseline_projection"
            )
        ),
        "known_projected_points": (
            team.get(
                "known_projected_points"
            )
        ),
        "projection_complete": (
            team.get(
                "projection_complete"
            )
        ),
        "starters_raw": team.get(
            "baseline_starters_raw"
        ),
        "starters": [
            _player_context(
                starter
            )
            for starter in starters
        ],
        "rostered_players": [
            _player_context(
                player
            )
            for player in rostered_players
        ],
        "special_projection_notes": (
            _special_projection_notes(
                team
            )
        ),
        "warnings": list(
            team.get(
                "warnings",
                [],
            )
        ),
    }


def _remaining_team_lookup(
    data: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """Return roster-keyed Monday remaining-player analytics.

    Older Sunday snapshots may not contain this additive block. In that
    case an empty lookup is returned so historical context can still be
    generated without inventing remaining-game data.
    """

    remaining = data.get(
        "remaining"
    )

    if remaining is None:
        return {}

    if not isinstance(
        remaining,
        dict,
    ):
        raise AgentContextError(
            "Sunday remaining analytics must be an object"
        )

    teams = remaining.get(
        "teams"
    )

    if teams is None:
        return {}

    if not isinstance(
        teams,
        dict,
    ):
        raise AgentContextError(
            "Sunday remaining teams must be an object"
        )

    lookup: dict[
        int,
        dict[str, Any],
    ] = {}

    for raw_roster_id, record in teams.items():
        try:
            roster_id = int(
                raw_roster_id
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise AgentContextError(
                "Sunday remaining roster key must be an integer"
            ) from exc

        if not isinstance(
            record,
            dict,
        ):
            raise AgentContextError(
                f"Sunday remaining roster {roster_id} must be an object"
            )

        if roster_id in lookup:
            raise AgentContextError(
                f"Duplicate Sunday remaining roster_id {roster_id}"
            )

        lookup[roster_id] = record

    return lookup


def _remaining_player_context(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Return AI-facing actual/game-state/remaining facts for a starter."""

    if not isinstance(
        record,
        dict,
    ):
        raise AgentContextError(
            "Sunday remaining player must be an object"
        )

    return {
        "slot": record.get(
            "slot"
        ),
        "player_id": record.get(
            "player_id"
        ),
        "player_name": record.get(
            "player_name"
        ),
        "position": record.get(
            "position"
        ),
        "nfl_team": record.get(
            "nfl_team"
        ),
        "actual_points": record.get(
            "actual_points"
        ),
        "actual_source": record.get(
            "actual_source"
        ),
        "fresh_projection": record.get(
            "fresh_projection"
        ),
        "projection_source": record.get(
            "projection_source"
        ),
        "game_state": record.get(
            "game_state"
        ),
        "game_id": record.get(
            "game_id"
        ),
        "opponent": record.get(
            "opponent"
        ),
        "kickoff": record.get(
            "kickoff"
        ),
        "still_to_play": record.get(
            "still_to_play"
        ),
        "remaining_projection": record.get(
            "remaining_projection"
        ),
        "reason": record.get(
            "reason"
        ),
    }


def _sunday_team_context(
    team: dict[str, Any],
    remaining_team: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build AI-facing Monday-morning facts for one roster."""

    starters = team.get(
        "starters",
        [],
    )

    rostered_players = team.get(
        "rostered_players",
        [],
    )

    if not isinstance(
        starters,
        list,
    ):
        raise AgentContextError(
            "Sunday starters must be a list"
        )

    if not isinstance(
        rostered_players,
        list,
    ):
        raise AgentContextError(
            "Sunday rostered_players must be a list"
        )

    remaining_players: list[dict[str, Any]] = []
    remaining_player_lookup: dict[str, dict[str, Any]] = {}

    current_points = team.get(
        "effective_live_points"
    )
    remaining_player_count = None
    remaining_projected_points = None
    projected_final_estimate = None
    remaining_warnings: list[Any] = []

    if remaining_team is not None:
        raw_players = remaining_team.get(
            "players",
            [],
        )

        if not isinstance(
            raw_players,
            list,
        ):
            raise AgentContextError(
                "Sunday remaining players must be a list"
            )

        monday_starters = [
            _remaining_player_context(
                record
            )
            for record in raw_players
        ]

        remaining_player_lookup = {
            str(record.get(
                "player_id"
            )): record
            for record in monday_starters
            if record.get(
                "player_id"
            ) is not None
        }

        remaining_players = [
            record
            for record in monday_starters
            if record.get(
                "still_to_play"
            ) is True
        ]

        current_points = remaining_team.get(
            "current_points",
            current_points,
        )
        remaining_player_count = remaining_team.get(
            "remaining_player_count"
        )
        remaining_projected_points = remaining_team.get(
            "remaining_projected_points"
        )
        projected_final_estimate = remaining_team.get(
            "projected_final_estimate"
        )

        raw_warnings = remaining_team.get(
            "warnings",
            [],
        )
        if isinstance(
            raw_warnings,
            list,
        ):
            remaining_warnings = list(
                raw_warnings
            )
    else:
        monday_starters = []

    enriched_starters: list[dict[str, Any]] = []

    for starter in starters:
        base = _player_context(
            starter
        )
        player_id = base.get(
            "player_id"
        )
        remaining_record = remaining_player_lookup.get(
            str(player_id)
        )

        if remaining_record is not None:
            base.update(
                {
                    "actual_points": remaining_record.get(
                        "actual_points"
                    ),
                    "actual_source": remaining_record.get(
                        "actual_source"
                    ),
                    "fresh_projection": remaining_record.get(
                        "fresh_projection"
                    ),
                    "game_state": remaining_record.get(
                        "game_state"
                    ),
                    "game_id": remaining_record.get(
                        "game_id"
                    ),
                    "opponent": remaining_record.get(
                        "opponent"
                    ),
                    "kickoff": remaining_record.get(
                        "kickoff"
                    ),
                    "still_to_play": remaining_record.get(
                        "still_to_play"
                    ),
                    "remaining_projection": remaining_record.get(
                        "remaining_projection"
                    ),
                }
            )

        enriched_starters.append(
            base
        )

    return {
        "roster_id": team.get(
            "roster_id"
        ),
        "owner_id": team.get(
            "owner_id"
        ),
        "manager_name": team.get(
            "manager_name"
        ),
        "matchup_id": team.get(
            "matchup_id"
        ),
        "opponent_roster_id": team.get(
            "opponent_roster_id"
        ),
        "live_points": team.get(
            "live_points"
        ),
        "custom_points": team.get(
            "custom_points"
        ),
        "effective_live_points": team.get(
            "effective_live_points"
        ),
        "current_points": current_points,
        "current_starter_projection": team.get(
            "stage_projection"
        ),
        "remaining_player_count": remaining_player_count,
        "remaining_projected_points": remaining_projected_points,
        "projected_final_estimate": projected_final_estimate,
        "known_projected_points": team.get(
            "known_projected_points"
        ),
        "projection_complete": team.get(
            "projection_complete"
        ),
        "starters_raw": team.get(
            "stage_starters_raw"
        ),
        "starters": enriched_starters,
        "monday_starters": monday_starters,
        "remaining_players": remaining_players,
        "rostered_players": [
            _player_context(
                player
            )
            for player in rostered_players
        ],
        "special_projection_notes": _special_projection_notes(
            team
        ),
        "remaining_warnings": remaining_warnings,
        "warnings": list(
            team.get(
                "warnings",
                [],
            )
        ),
    }

def _lead_summary(
    team_a: dict[str, Any],
    team_b: dict[str, Any],
    field: str,
) -> dict[str, Any]:
    """Precompute a lead/margin so the AI need not do arithmetic."""

    points_a = _optional_number(
        team_a.get(
            field
        ),
        f"Roster {team_a.get('roster_id')} "
        f"{field}",
    )

    points_b = _optional_number(
        team_b.get(
            field
        ),
        f"Roster {team_b.get('roster_id')} "
        f"{field}",
    )

    if (
        points_a is None
        or points_b is None
    ):
        return {
            "leader_roster_id": None,
            "leader_manager_name": None,
            "margin": None,
            "tied": None,
        }

    difference = (
        points_a
        - points_b
    )

    if abs(
        difference
    ) < 1e-9:
        return {
            "leader_roster_id": None,
            "leader_manager_name": None,
            "margin": 0.0,
            "tied": True,
        }

    leader = (
        team_a
        if difference > 0
        else team_b
    )

    return {
        "leader_roster_id": (
            leader.get(
                "roster_id"
            )
        ),
        "leader_manager_name": (
            leader.get(
                "manager_name"
            )
        ),
        "margin": abs(
            difference
        ),
        "tied": False,
    }


def _baseline_matchups(
    data: dict[str, Any],
    teams: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build baseline matchup facts."""

    records = data.get(
        "matchups"
    )

    if not isinstance(
        records,
        list,
    ):
        raise AgentContextError(
            "Baseline snapshot is "
            "missing matchups"
        )

    result: list[
        dict[str, Any]
    ] = []

    for matchup in records:
        roster_a_id = matchup.get(
            "roster_a_id"
        )

        roster_b_id = matchup.get(
            "roster_b_id"
        )

        team_a = teams.get(
            roster_a_id
        )

        team_b = teams.get(
            roster_b_id
        )

        if (
            team_a is None
            or team_b is None
        ):
            raise AgentContextError(
                "Matchup references "
                "unknown roster"
            )

        result.append(
            {
                "matchup_id": (
                    matchup.get(
                        "matchup_id"
                    )
                ),
                "team_a": {
                    "roster_id": (
                        roster_a_id
                    ),
                    "manager_name": (
                        team_a.get(
                            "manager_name"
                        )
                    ),
                    "projection": (
                        team_a.get(
                            "baseline_projection"
                        )
                    ),
                },
                "team_b": {
                    "roster_id": (
                        roster_b_id
                    ),
                    "manager_name": (
                        team_b.get(
                            "manager_name"
                        )
                    ),
                    "projection": (
                        team_b.get(
                            "baseline_projection"
                        )
                    ),
                },
                "projection_lead": (
                    _lead_summary(
                        team_a,
                        team_b,
                        "baseline_projection",
                    )
                ),
            }
        )

    return result


def _sunday_matchups(
    data: dict[str, Any],
    teams: dict[int, dict[str, Any]],
    remaining_teams: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Monday-morning matchup facts with expected-final estimates."""

    records = data.get(
        "matchups"
    )

    if not isinstance(
        records,
        list,
    ):
        raise AgentContextError(
            "Sunday snapshot is missing matchups"
        )

    result: list[dict[str, Any]] = []

    for matchup in records:
        roster_a_id = matchup.get(
            "roster_a_id"
        )
        roster_b_id = matchup.get(
            "roster_b_id"
        )

        team_a = teams.get(
            roster_a_id
        )
        team_b = teams.get(
            roster_b_id
        )

        if (
            team_a is None
            or team_b is None
        ):
            raise AgentContextError(
                "Matchup references unknown roster"
            )

        remaining_a = remaining_teams.get(
            roster_a_id
        )
        remaining_b = remaining_teams.get(
            roster_b_id
        )

        context_a = _sunday_team_context(
            team_a,
            remaining_a,
        )
        context_b = _sunday_team_context(
            team_b,
            remaining_b,
        )

        result.append(
            {
                "matchup_id": matchup.get(
                    "matchup_id"
                ),
                "team_a": {
                    "roster_id": roster_a_id,
                    "manager_name": team_a.get(
                        "manager_name"
                    ),
                    "effective_live_points": team_a.get(
                        "effective_live_points"
                    ),
                    "current_points": context_a.get(
                        "current_points"
                    ),
                    "current_starter_projection": team_a.get(
                        "stage_projection"
                    ),
                    "remaining_player_count": context_a.get(
                        "remaining_player_count"
                    ),
                    "remaining_projected_points": context_a.get(
                        "remaining_projected_points"
                    ),
                    "projected_final_estimate": context_a.get(
                        "projected_final_estimate"
                    ),
                    "remaining_players": context_a.get(
                        "remaining_players",
                        [],
                    ),
                },
                "team_b": {
                    "roster_id": roster_b_id,
                    "manager_name": team_b.get(
                        "manager_name"
                    ),
                    "effective_live_points": team_b.get(
                        "effective_live_points"
                    ),
                    "current_points": context_b.get(
                        "current_points"
                    ),
                    "current_starter_projection": team_b.get(
                        "stage_projection"
                    ),
                    "remaining_player_count": context_b.get(
                        "remaining_player_count"
                    ),
                    "remaining_projected_points": context_b.get(
                        "remaining_projected_points"
                    ),
                    "projected_final_estimate": context_b.get(
                        "projected_final_estimate"
                    ),
                    "remaining_players": context_b.get(
                        "remaining_players",
                        [],
                    ),
                },
                "live_score_lead": _lead_summary(
                    team_a,
                    team_b,
                    "effective_live_points",
                ),
                "current_projection_lead": _lead_summary(
                    team_a,
                    team_b,
                    "stage_projection",
                ),
                "projected_final_lead": _lead_summary(
                    context_a,
                    context_b,
                    "projected_final_estimate",
                ),
            }
        )

    return result

def _player_name_from_team_records(
    player_id: str,
    baseline_team: dict[str, Any],
    sunday_team: dict[str, Any],
) -> str:
    """Resolve a player name only from stored historical records."""

    for team in (
        sunday_team,
        baseline_team,
    ):
        for field in (
            "starters",
            "rostered_players",
        ):
            records = team.get(
                field,
                [],
            )

            if not isinstance(
                records,
                list,
            ):
                continue

            for record in records:
                if not isinstance(
                    record,
                    dict,
                ):
                    continue

                if str(
                    record.get(
                        "player_id"
                    )
                ) != player_id:
                    continue

                name = record.get(
                    "player_name"
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


def _comparison_team_context(
    comparison: TeamSnapshotComparison,
    baseline_team: dict[str, Any],
    sunday_team: dict[str, Any],
) -> dict[str, Any]:
    """Convert comparison dataclass facts into JSON."""

    added = [
        {
            "player_id": player_id,
            "player_name": (
                _player_name_from_team_records(
                    player_id,
                    baseline_team,
                    sunday_team,
                )
            ),
        }
        for player_id
        in comparison.added_starters
    ]

    removed = [
        {
            "player_id": player_id,
            "player_name": (
                _player_name_from_team_records(
                    player_id,
                    baseline_team,
                    sunday_team,
                )
            ),
        }
        for player_id
        in comparison.removed_starters
    ]

    slot_changes = [
        {
            "slot": change.slot,
            "baseline_player_id": (
                change.baseline_player_id
            ),
            "baseline_player_name": (
                change.baseline_player_name
            ),
            "sunday_player_id": (
                change.sunday_player_id
            ),
            "sunday_player_name": (
                change.sunday_player_name
            ),
        }
        for change
        in comparison.slot_changes
    ]

    projection_changes = [
        {
            "player_id": (
                change.player_id
            ),
            "player_name": (
                change.player_name
            ),
            "baseline_present": (
                change.baseline_present
            ),
            "sunday_present": (
                change.sunday_present
            ),
            "baseline_points": (
                change.baseline_points
            ),
            "sunday_points": (
                change.sunday_points
            ),
            "delta": (
                change.delta
            ),
            "baseline_source": (
                change.baseline_source
            ),
            "sunday_source": (
                change.sunday_source
            ),
        }
        for change
        in comparison.projection_changes
    ]

    return {
        "roster_id": (
            comparison.roster_id
        ),
        "manager_name": (
            comparison.sunday_manager_name
        ),
        "lineup_changed": bool(
            added
            or removed
            or slot_changes
        ),
        "added_starters": (
            added
        ),
        "removed_starters": (
            removed
        ),
        "slot_changes": (
            slot_changes
        ),
        "team_projection": {
            "baseline": (
                comparison
                .baseline_team_projection
            ),
            "sunday": (
                comparison
                .sunday_team_projection
            ),
            "delta": (
                comparison
                .team_projection_delta
            ),
        },
        "player_projection_changes": (
            projection_changes
        ),
        "baseline_warnings": list(
            comparison.baseline_warnings
        ),
        "sunday_warnings": list(
            comparison.sunday_warnings
        ),
    }


def _baseline_league_context(
    snapshot: dict[str, Any],
    league_config: dict[str, Any],
) -> dict[str, Any]:
    """Build one league's baseline agent context."""

    data = snapshot.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise AgentContextError(
            "Baseline snapshot is missing data"
        )

    teams = _team_lookup(
        data,
        "Baseline snapshot",
    )

    league_data = data.get(
        "league",
        {},
    )

    return {
        "league_key": snapshot.get(
            "league_key"
        ),
        "league_id": snapshot.get(
            "league_id"
        ),
        "name": (
            league_data.get(
                "name"
            )
            if isinstance(
                league_data,
                dict,
            )
            else league_config.get(
                "name"
            )
        ),
        "tier": league_config.get(
            "tier"
        ),
        "rules": dict(
            league_config
        ),
        "projection_method": data.get(
            "projection_method"
        ),
        "matchups": (
            _baseline_matchups(
                data,
                teams,
            )
        ),
        "teams": [
            _baseline_team_context(
                teams[
                    roster_id
                ]
            )
            for roster_id
            in sorted(
                teams
            )
        ],
        "warnings": list(
            data.get(
                "warnings",
                [],
            )
        ),
    }


def _sunday_league_context(
    baseline_snapshot: dict[str, Any],
    sunday_snapshot: dict[str, Any],
    league_config: dict[str, Any],
) -> dict[str, Any]:
    """Build one league's Monday-noon agent context."""

    baseline_data = (
        baseline_snapshot.get(
            "data"
        )
    )

    sunday_data = (
        sunday_snapshot.get(
            "data"
        )
    )

    if not isinstance(
        baseline_data,
        dict,
    ):
        raise AgentContextError(
            "Baseline snapshot is missing data"
        )

    if not isinstance(
        sunday_data,
        dict,
    ):
        raise AgentContextError(
            "Sunday snapshot is missing data"
        )

    baseline_teams = (
        _team_lookup(
            baseline_data,
            "Baseline snapshot",
        )
    )

    sunday_teams = (
        _team_lookup(
            sunday_data,
            "Sunday snapshot",
        )
    )

    remaining_teams = (
        _remaining_team_lookup(
            sunday_data
        )
    )

    comparison = (
        compare_baseline_to_sunday(
            baseline_snapshot,
            sunday_snapshot,
        )
    )

    comparison_teams = [
        _comparison_team_context(
            team_comparison,
            baseline_teams[
                team_comparison
                .roster_id
            ],
            sunday_teams[
                team_comparison
                .roster_id
            ],
        )
        for team_comparison
        in comparison.teams
    ]

    league_data = sunday_data.get(
        "league",
        {},
    )

    return {
        "league_key": sunday_snapshot.get(
            "league_key"
        ),
        "league_id": sunday_snapshot.get(
            "league_id"
        ),
        "name": (
            league_data.get(
                "name"
            )
            if isinstance(
                league_data,
                dict,
            )
            else league_config.get(
                "name"
            )
        ),
        "tier": league_config.get(
            "tier"
        ),
        "rules": dict(
            league_config
        ),
        "projection_method": (
            sunday_data.get(
                "projection_method"
            )
        ),
        "matchups": (
            _sunday_matchups(
                sunday_data,
                sunday_teams,
                remaining_teams,
            )
        ),
        "teams": [
            _sunday_team_context(
                sunday_teams[
                    roster_id
                ],
                remaining_teams.get(
                    roster_id
                ),
            )
            for roster_id
            in sorted(
                sunday_teams
            )
        ],
        "monday_mnf": {
            "teams_with_players_remaining": [
                _sunday_team_context(
                    sunday_teams[roster_id],
                    remaining_teams.get(
                        roster_id
                    ),
                )
                for roster_id in sorted(
                    sunday_teams
                )
                if (
                    remaining_teams.get(
                        roster_id,
                        {},
                    ).get(
                        "remaining_player_count",
                        0,
                    )
                    > 0
                )
            ],
            "remaining_player_count": sum(
                int(
                    record.get(
                        "remaining_player_count",
                        0,
                    )
                )
                for record in remaining_teams.values()
                if isinstance(
                    record.get(
                        "remaining_player_count",
                        0,
                    ),
                    int,
                )
            ),
        },
        "baseline_comparison": {
            "teams_with_lineup_changes": (
                sum(
                    1
                    for team
                    in comparison_teams
                    if team[
                        "lineup_changed"
                    ]
                )
            ),
            "teams_with_projection_changes": (
                sum(
                    1
                    for team
                    in comparison_teams
                    if team[
                        "player_projection_changes"
                    ]
                )
            ),
            "teams": comparison_teams,
        },
        "warnings": list(
            sunday_data.get(
                "warnings",
                [],
            )
        ),
    }


def build_agent_context_document(
    data_root: Path,
    project_config: dict[str, Any],
    season: str,
    week: int,
    stage: str,
) -> dict[str, Any]:
    """Build combined GOATs/DOATs context strictly from stored snapshots."""

    if stage not in (
        SUPPORTED_CONTEXT_STAGES
    ):
        raise AgentContextError(
            f"Agent context for stage "
            f"{stage!r} is not implemented"
        )

    if (
        project_config.get(
            "season"
        )
        != season
    ):
        raise AgentContextError(
            "Project config season "
            "does not match requested season"
        )

    leagues_config = (
        project_config.get(
            "leagues"
        )
    )

    if not isinstance(
        leagues_config,
        dict,
    ):
        raise AgentContextError(
            "Project config is missing leagues"
        )

    league_contexts: dict[
        str,
        dict[str, Any],
    ] = {}

    derived_from: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, league_config in (
        leagues_config.items()
    ):
        if not isinstance(
            league_config,
            dict,
        ):
            raise AgentContextError(
                f"League config for "
                f"{league_key} must be "
                "an object"
            )

        stage_path = (
            build_snapshot_path(
                data_root=data_root,
                season=season,
                league_key=league_key,
                week=week,
                stage=stage,
            )
        )

        if not stage_path.exists():
            raise AgentContextError(
                f"Required {stage} snapshot "
                f"does not exist: "
                f"{stage_path}"
            )

        stage_snapshot = (
            read_snapshot(
                stage_path
            )
        )

        _validate_snapshot_identity(
            snapshot=stage_snapshot,
            season=season,
            week=week,
            league_key=league_key,
            stage=stage,
        )

        sources = {
            f"{stage}_snapshot": (
                _source_descriptor(
                    stage_path,
                    stage_snapshot,
                )
            )
        }

        if stage == "baseline":
            league_contexts[
                league_key
            ] = (
                _baseline_league_context(
                    stage_snapshot,
                    league_config,
                )
            )

        elif stage == "sunday":
            baseline_path = (
                build_snapshot_path(
                    data_root=data_root,
                    season=season,
                    league_key=(
                        league_key
                    ),
                    week=week,
                    stage="baseline",
                )
            )

            if not baseline_path.exists():
                raise AgentContextError(
                    "Sunday context requires "
                    f"baseline snapshot: "
                    f"{baseline_path}"
                )

            baseline_snapshot = (
                read_snapshot(
                    baseline_path
                )
            )

            _validate_snapshot_identity(
                snapshot=(
                    baseline_snapshot
                ),
                season=season,
                week=week,
                league_key=(
                    league_key
                ),
                stage="baseline",
            )

            sources[
                "baseline_snapshot"
            ] = (
                _source_descriptor(
                    baseline_path,
                    baseline_snapshot,
                )
            )

            league_contexts[
                league_key
            ] = (
                _sunday_league_context(
                    baseline_snapshot,
                    stage_snapshot,
                    league_config,
                )
            )

        derived_from[
            league_key
        ] = sources

    return {
        "schema_version": (
            AGENT_CONTEXT_SCHEMA_VERSION
        ),
        "context_type": (
            "fantasy_agent_context"
        ),
        "authoritative": False,
        "season": season,
        "week": week,
        "stage": stage,
        "source_of_truth": (
            "immutable snapshot files "
            "listed in derived_from"
        ),
        "semantics": {
            "missing_values": (
                "null means unresolved or "
                "unavailable; never assume zero"
            ),
            "baseline_projection": (
                "starter projection total "
                "stored at the baseline"
            ),
            "sunday_current_starter_projection": (
                "fresh current-starter projection "
                "total; not a remaining-game or "
                "final-score forecast"
            ),
            "remaining_projected_points": (
                "fresh projections only for starters whose "
                "NFL games have not started"
            ),
            "projected_final_estimate": (
                "current actual fantasy-team points plus "
                "remaining_projected_points"
            ),
            "game_state": (
                "scheduled means not started; final means complete; "
                "in_progress or unknown makes remaining projection unresolved"
            ),
            "effective_live_points": (
                "commissioner custom_points when "
                "present, otherwise Sleeper points"
            ),
            "projection_scoring": (
                "current MVP uses stored Sleeper "
                "pts_ppr rather than exact custom "
                "league scoring"
            ),
        },
        "competition": {
            "leagues": (
                leagues_config
            ),
            "promotion_rules": (
                project_config.get(
                    "promotion_rules"
                )
            ),
            "analytics": (
                project_config.get(
                    "analytics"
                )
            ),
            "simulation": (
                project_config.get(
                    "simulation"
                )
            ),
        },
        "derived_from": (
            derived_from
        ),
        "leagues": (
            league_contexts
        ),
    }


def _write_json_atomic_replace(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """Atomically replace a derived JSON file."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = Path(
                file.name
            )

            json.dump(
                payload,
                file,
                indent=2,
                sort_keys=True,
            )

            file.write(
                "\n"
            )

            file.flush()

            os.fsync(
                file.fileno()
            )

        os.replace(
            temp_path,
            path,
        )

    except Exception:
        if (
            temp_path is not None
            and temp_path.exists()
        ):
            temp_path.unlink()

        raise


def write_agent_context_file(
    data_root: Path,
    project_config: dict[str, Any],
    season: str,
    week: int,
    stage: str,
) -> Path:
    """Generate and atomically replace one derived agent-context file."""

    document = (
        build_agent_context_document(
            data_root=data_root,
            project_config=(
                project_config
            ),
            season=season,
            week=week,
            stage=stage,
        )
    )

    path = agent_context_path(
        data_root=data_root,
        season=season,
        week=week,
        stage=stage,
    )

    _write_json_atomic_replace(
        path,
        document,
    )

    return path