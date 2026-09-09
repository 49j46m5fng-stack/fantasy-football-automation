"""Compare an immutable baseline with a later Sunday snapshot."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.storage import read_snapshot


class SnapshotComparisonError(ValueError):
    """Raised when two snapshots cannot be compared safely."""


@dataclass(frozen=True)
class StarterSlotChange:
    """One lineup slot that differs between baseline and Sunday."""

    slot: int
    baseline_player_id: str | None
    sunday_player_id: str | None
    baseline_player_name: str | None
    sunday_player_name: str | None


@dataclass(frozen=True)
class PlayerProjectionChange:
    """Projection movement for one player between snapshots."""

    player_id: str
    player_name: str
    baseline_present: bool
    sunday_present: bool
    baseline_points: float | None
    sunday_points: float | None
    delta: float | None
    baseline_source: str | None
    sunday_source: str | None


@dataclass(frozen=True)
class TeamSnapshotComparison:
    """Baseline-to-Sunday changes for one fantasy roster."""

    roster_id: int
    baseline_manager_name: str
    sunday_manager_name: str
    baseline_starters: tuple[str | None, ...]
    sunday_starters: tuple[str | None, ...]
    added_starters: tuple[str, ...]
    removed_starters: tuple[str, ...]
    slot_changes: tuple[StarterSlotChange, ...]
    baseline_team_projection: float | None
    sunday_team_projection: float | None
    team_projection_delta: float | None
    projection_changes: tuple[PlayerProjectionChange, ...]
    baseline_warnings: tuple[str, ...]
    sunday_warnings: tuple[str, ...]


@dataclass(frozen=True)
class WeekSnapshotComparison:
    """Comparison of one league's baseline and Sunday snapshots."""

    league_key: str
    league_id: str
    season: str
    week: int
    teams: tuple[TeamSnapshotComparison, ...]


def _snapshot_data(
    snapshot: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """Return the snapshot data object."""

    data = snapshot.get("data")

    if not isinstance(data, dict):
        raise SnapshotComparisonError(
            f"{label} snapshot is missing a valid data object"
        )

    return data


def _team_lookup(
    data: dict[str, Any],
    label: str,
) -> dict[int, dict[str, Any]]:
    """Build a roster lookup while rejecting duplicate IDs."""

    teams = data.get("teams")

    if not isinstance(teams, list):
        raise SnapshotComparisonError(
            f"{label} snapshot is missing teams"
        )

    lookup: dict[int, dict[str, Any]] = {}

    for team in teams:
        if not isinstance(team, dict):
            raise SnapshotComparisonError(
                f"{label} team record must be an object"
            )

        roster_id = team.get("roster_id")

        if not isinstance(roster_id, int):
            raise SnapshotComparisonError(
                f"{label} team is missing a valid roster_id"
            )

        if roster_id in lookup:
            raise SnapshotComparisonError(
                f"{label} snapshot contains duplicate "
                f"roster_id {roster_id}"
            )

        lookup[roster_id] = team

    return lookup


def _starter_slots(
    team: dict[str, Any],
    field: str,
    label: str,
) -> tuple[str | None, ...]:
    """Normalize starter slots while preserving empty lineup positions."""

    raw_starters = team.get(field)

    if not isinstance(raw_starters, list):
        raise SnapshotComparisonError(
            f"{label} team is missing {field}"
        )

    starters: list[str | None] = []

    for raw_player_id in raw_starters:
        if (
            raw_player_id is None
            or not raw_player_id
            or str(raw_player_id) == "0"
        ):
            starters.append(None)
            continue

        starters.append(
            str(raw_player_id)
        )

    populated = [
        player_id
        for player_id in starters
        if player_id is not None
    ]

    if len(populated) != len(set(populated)):
        raise SnapshotComparisonError(
            f"{label} lineup contains a duplicate starter"
        )

    return tuple(starters)


def _rostered_player_lookup(
    team: dict[str, Any],
    label: str,
) -> dict[str, dict[str, Any]]:
    """Build a lookup of stored rostered-player projection records."""

    records = team.get("rostered_players")

    if not isinstance(records, list):
        raise SnapshotComparisonError(
            f"{label} team is missing rostered_players"
        )

    lookup: dict[str, dict[str, Any]] = {}

    for record in records:
        if not isinstance(record, dict):
            raise SnapshotComparisonError(
                f"{label} rostered player record "
                "must be an object"
            )

        raw_player_id = record.get("player_id")

        if (
            raw_player_id is None
            or not str(raw_player_id)
            or str(raw_player_id) == "0"
        ):
            raise SnapshotComparisonError(
                f"{label} rostered player record "
                "is missing player_id"
            )

        player_id = str(raw_player_id)

        if player_id in lookup:
            raise SnapshotComparisonError(
                f"{label} roster contains duplicate "
                f"player_id {player_id}"
            )

        lookup[player_id] = record

    return lookup


def _optional_points(
    value: Any,
    description: str,
) -> float | None:
    """Read optional numeric fantasy points without inventing zero."""

    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise SnapshotComparisonError(
            f"{description} must be numeric or null"
        )

    return float(value)


def _projection_points(
    record: dict[str, Any],
    label: str,
) -> float | None:
    """Return one stored player projection."""

    return _optional_points(
        record.get("projected_points"),
        f"{label} projected_points",
    )


def _projection_source(
    record: dict[str, Any],
) -> str | None:
    """Return one stored projection source."""

    source = record.get("projection_source")

    if source is None:
        return None

    return str(source)


def _player_name(
    player_id: str,
    baseline_players: dict[str, dict[str, Any]],
    sunday_players: dict[str, dict[str, Any]],
) -> str:
    """Resolve a stored player name without querying live metadata."""

    for lookup in (
        sunday_players,
        baseline_players,
    ):
        record = lookup.get(player_id)

        if record is None:
            continue

        name = record.get("player_name")

        if isinstance(name, str) and name:
            return name

    return player_id


def _ordered_difference(
    primary: tuple[str | None, ...],
    comparison: tuple[str | None, ...],
) -> tuple[str, ...]:
    """Return populated IDs present only in the primary lineup."""

    comparison_ids = {
        player_id
        for player_id in comparison
        if player_id is not None
    }

    return tuple(
        player_id
        for player_id in primary
        if (
            player_id is not None
            and player_id not in comparison_ids
        )
    )


def _points_equal(
    left: float | None,
    right: float | None,
) -> bool:
    """Compare optional fantasy-point values."""

    if left is None or right is None:
        return left is right

    return abs(left - right) < 1e-9


def _projection_changes(
    baseline_players: dict[str, dict[str, Any]],
    sunday_players: dict[str, dict[str, Any]],
) -> tuple[PlayerProjectionChange, ...]:
    """Find stored player projection or roster-presence changes."""

    changes: list[PlayerProjectionChange] = []

    player_ids = sorted(
        set(baseline_players)
        | set(sunday_players)
    )

    for player_id in player_ids:
        baseline_record = baseline_players.get(
            player_id
        )

        sunday_record = sunday_players.get(
            player_id
        )

        baseline_present = (
            baseline_record is not None
        )

        sunday_present = (
            sunday_record is not None
        )

        baseline_points = (
            _projection_points(
                baseline_record,
                f"Baseline player {player_id}",
            )
            if baseline_record is not None
            else None
        )

        sunday_points = (
            _projection_points(
                sunday_record,
                f"Sunday player {player_id}",
            )
            if sunday_record is not None
            else None
        )

        baseline_source = (
            _projection_source(
                baseline_record
            )
            if baseline_record is not None
            else None
        )

        sunday_source = (
            _projection_source(
                sunday_record
            )
            if sunday_record is not None
            else None
        )

        changed = (
            baseline_present != sunday_present
            or not _points_equal(
                baseline_points,
                sunday_points,
            )
            or baseline_source != sunday_source
        )

        if not changed:
            continue

        delta = None

        if (
            baseline_points is not None
            and sunday_points is not None
        ):
            delta = (
                sunday_points
                - baseline_points
            )

        changes.append(
            PlayerProjectionChange(
                player_id=player_id,
                player_name=_player_name(
                    player_id,
                    baseline_players,
                    sunday_players,
                ),
                baseline_present=baseline_present,
                sunday_present=sunday_present,
                baseline_points=baseline_points,
                sunday_points=sunday_points,
                delta=delta,
                baseline_source=baseline_source,
                sunday_source=sunday_source,
            )
        )

    return tuple(changes)


def _warnings(
    team: dict[str, Any],
    label: str,
) -> tuple[str, ...]:
    """Read stored team warnings."""

    warnings = team.get(
        "warnings",
        [],
    )

    if not isinstance(warnings, list):
        raise SnapshotComparisonError(
            f"{label} warnings must be a list"
        )

    return tuple(
        str(warning)
        for warning in warnings
    )


def _validate_identity(
    baseline: dict[str, Any],
    sunday: dict[str, Any],
) -> None:
    """Require two snapshots to represent the same league and week."""

    if baseline.get("stage") != "baseline":
        raise SnapshotComparisonError(
            "First snapshot must be baseline stage"
        )

    if sunday.get("stage") != "sunday":
        raise SnapshotComparisonError(
            "Second snapshot must be sunday stage"
        )

    for field in (
        "season",
        "week",
        "league_key",
        "league_id",
    ):
        if baseline.get(field) != sunday.get(field):
            raise SnapshotComparisonError(
                f"Snapshot identity mismatch for {field}"
            )


def compare_baseline_to_sunday(
    baseline: dict[str, Any],
    sunday: dict[str, Any],
) -> WeekSnapshotComparison:
    """Compare one immutable baseline against its Sunday snapshot."""

    _validate_identity(
        baseline,
        sunday,
    )

    baseline_data = _snapshot_data(
        baseline,
        "Baseline",
    )

    sunday_data = _snapshot_data(
        sunday,
        "Sunday",
    )

    baseline_teams = _team_lookup(
        baseline_data,
        "Baseline",
    )

    sunday_teams = _team_lookup(
        sunday_data,
        "Sunday",
    )

    if set(baseline_teams) != set(sunday_teams):
        raise SnapshotComparisonError(
            "Baseline and Sunday roster sets do not match"
        )

    comparisons: list[
        TeamSnapshotComparison
    ] = []

    for roster_id in sorted(
        baseline_teams
    ):
        baseline_team = baseline_teams[
            roster_id
        ]

        sunday_team = sunday_teams[
            roster_id
        ]

        baseline_starters = _starter_slots(
            baseline_team,
            "baseline_starters_raw",
            "Baseline",
        )

        sunday_starters = _starter_slots(
            sunday_team,
            "stage_starters_raw",
            "Sunday",
        )

        if (
            len(baseline_starters)
            != len(sunday_starters)
        ):
            raise SnapshotComparisonError(
                f"Roster {roster_id} starter slot "
                "counts do not match"
            )

        baseline_players = (
            _rostered_player_lookup(
                baseline_team,
                "Baseline",
            )
        )

        sunday_players = (
            _rostered_player_lookup(
                sunday_team,
                "Sunday",
            )
        )

        added_starters = (
            _ordered_difference(
                sunday_starters,
                baseline_starters,
            )
        )

        removed_starters = (
            _ordered_difference(
                baseline_starters,
                sunday_starters,
            )
        )

        slot_changes: list[
            StarterSlotChange
        ] = []

        for index, (
            baseline_player_id,
            sunday_player_id,
        ) in enumerate(
            zip(
                baseline_starters,
                sunday_starters,
                strict=True,
            ),
            start=1,
        ):
            if (
                baseline_player_id
                == sunday_player_id
            ):
                continue

            slot_changes.append(
                StarterSlotChange(
                    slot=index,
                    baseline_player_id=(
                        baseline_player_id
                    ),
                    sunday_player_id=(
                        sunday_player_id
                    ),
                    baseline_player_name=(
                        _player_name(
                            baseline_player_id,
                            baseline_players,
                            sunday_players,
                        )
                        if baseline_player_id
                        is not None
                        else None
                    ),
                    sunday_player_name=(
                        _player_name(
                            sunday_player_id,
                            baseline_players,
                            sunday_players,
                        )
                        if sunday_player_id
                        is not None
                        else None
                    ),
                )
            )

        baseline_team_projection = (
            _optional_points(
                baseline_team.get(
                    "baseline_projection"
                ),
                (
                    f"Roster {roster_id} "
                    "baseline_projection"
                ),
            )
        )

        sunday_team_projection = (
            _optional_points(
                sunday_team.get(
                    "stage_projection"
                ),
                (
                    f"Roster {roster_id} "
                    "stage_projection"
                ),
            )
        )

        team_projection_delta = None

        if (
            baseline_team_projection
            is not None
            and sunday_team_projection
            is not None
        ):
            team_projection_delta = (
                sunday_team_projection
                - baseline_team_projection
            )

        comparisons.append(
            TeamSnapshotComparison(
                roster_id=roster_id,
                baseline_manager_name=str(
                    baseline_team.get(
                        "manager_name",
                        f"Roster {roster_id}",
                    )
                ),
                sunday_manager_name=str(
                    sunday_team.get(
                        "manager_name",
                        f"Roster {roster_id}",
                    )
                ),
                baseline_starters=(
                    baseline_starters
                ),
                sunday_starters=(
                    sunday_starters
                ),
                added_starters=(
                    added_starters
                ),
                removed_starters=(
                    removed_starters
                ),
                slot_changes=tuple(
                    slot_changes
                ),
                baseline_team_projection=(
                    baseline_team_projection
                ),
                sunday_team_projection=(
                    sunday_team_projection
                ),
                team_projection_delta=(
                    team_projection_delta
                ),
                projection_changes=(
                    _projection_changes(
                        baseline_players,
                        sunday_players,
                    )
                ),
                baseline_warnings=(
                    _warnings(
                        baseline_team,
                        "Baseline",
                    )
                ),
                sunday_warnings=(
                    _warnings(
                        sunday_team,
                        "Sunday",
                    )
                ),
            )
        )

    return WeekSnapshotComparison(
        league_key=str(
            baseline["league_key"]
        ),
        league_id=str(
            baseline["league_id"]
        ),
        season=str(
            baseline["season"]
        ),
        week=int(
            baseline["week"]
        ),
        teams=tuple(
            comparisons
        ),
    )


def compare_snapshot_files(
    baseline_path: Path,
    sunday_path: Path,
) -> WeekSnapshotComparison:
    """Read two stored snapshots and compare them."""

    baseline = read_snapshot(
        baseline_path
    )

    sunday = read_snapshot(
        sunday_path
    )

    return compare_baseline_to_sunday(
        baseline,
        sunday,
    )