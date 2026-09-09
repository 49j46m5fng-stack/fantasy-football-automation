"""Convert raw Sleeper records into stable internal data models."""

from collections import defaultdict
from typing import Any

from src.models import FantasyMatchup, FantasyRoster


class NormalizationError(ValueError):
    """Raised when raw Sleeper data cannot be normalized safely."""


def build_user_name_lookup(
    users: list[dict[str, Any]],
) -> dict[str, str]:
    """Map Sleeper user IDs to display names."""

    lookup: dict[str, str] = {}

    for user in users:
        user_id = user.get("user_id")

        if not user_id:
            continue

        display_name = user.get("display_name") or "UNKNOWN"

        lookup[str(user_id)] = str(display_name)

    return lookup


def normalize_rosters(
    league_key: str,
    league_id: str,
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
) -> list[FantasyRoster]:
    """Connect Sleeper roster records to their owning users."""

    user_names = build_user_name_lookup(users)

    normalized: list[FantasyRoster] = []

    for roster in rosters:
        roster_id = roster.get("roster_id")

        if not isinstance(roster_id, int):
            raise NormalizationError(
                "Roster record is missing a valid integer roster_id"
            )

        raw_owner_id = roster.get("owner_id")

        owner_id = (
            str(raw_owner_id)
            if raw_owner_id is not None
            else None
        )

        manager_name = (
            user_names.get(owner_id, "UNKNOWN")
            if owner_id is not None
            else "UNKNOWN"
        )

        normalized.append(
            FantasyRoster(
                league_key=league_key,
                league_id=league_id,
                roster_id=roster_id,
                owner_id=owner_id,
                manager_name=manager_name,
            )
        )

    return normalized


def pair_matchups(
    league_key: str,
    league_id: str,
    week: int,
    matchup_records: list[dict[str, Any]],
) -> list[FantasyMatchup]:
    """Group weekly Sleeper records into two-roster matchups."""

    groups: dict[int, list[int]] = defaultdict(list)

    for record in matchup_records:
        matchup_id = record.get("matchup_id")
        roster_id = record.get("roster_id")

        if not isinstance(matchup_id, int):
            raise NormalizationError(
                "Matchup record is missing a valid integer matchup_id"
            )

        if not isinstance(roster_id, int):
            raise NormalizationError(
                "Matchup record is missing a valid integer roster_id"
            )

        groups[matchup_id].append(roster_id)

    normalized: list[FantasyMatchup] = []

    for matchup_id, roster_ids in sorted(groups.items()):
        if len(roster_ids) != 2:
            raise NormalizationError(
                f"Expected matchup_id {matchup_id} to contain exactly "
                f"2 rosters, but found {len(roster_ids)}"
            )

        normalized.append(
            FantasyMatchup(
                league_key=league_key,
                league_id=league_id,
                week=week,
                matchup_id=matchup_id,
                roster_a_id=roster_ids[0],
                roster_b_id=roster_ids[1],
            )
        )

    return normalized


def get_starting_player_ids(
    matchup_record: dict[str, Any],
) -> list[str]:
    """Return populated starter IDs without inventing empty players."""

    starters = matchup_record.get("starters") or []

    if not isinstance(starters, list):
        raise NormalizationError(
            "Matchup starters must be a list"
        )

    return [
        str(player_id)
        for player_id in starters
        if player_id
        and str(player_id) != "0"
    ]