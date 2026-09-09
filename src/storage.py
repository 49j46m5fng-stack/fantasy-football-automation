"""Durable storage for immutable weekly fantasy snapshots."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_SCHEMA_VERSION = 1

VALID_SNAPSHOT_STAGES = frozenset(
    {
        "baseline",
        "sunday",
        "final",
    }
)


class SnapshotStorageError(RuntimeError):
    """Raised when a snapshot cannot be stored or loaded safely."""


class SnapshotExistsError(SnapshotStorageError):
    """Raised when code attempts to overwrite an existing snapshot."""


class SnapshotValidationError(SnapshotStorageError):
    """Raised when stored snapshot data is invalid or unsupported."""


def build_snapshot_path(
    data_root: Path,
    season: str,
    league_key: str,
    week: int,
    stage: str,
) -> Path:
    """Return the canonical path for one official weekly snapshot."""

    if not season:
        raise ValueError("season cannot be empty")

    if not league_key:
        raise ValueError("league_key cannot be empty")

    if week < 1:
        raise ValueError("week must be at least 1")

    if stage not in VALID_SNAPSHOT_STAGES:
        raise ValueError(
            f"Unsupported snapshot stage: {stage}"
        )

    return (
        data_root
        / season
        / league_key
        / f"week_{week:02d}_{stage}.json"
    )


def build_snapshot_document(
    season: str,
    week: int,
    league_key: str,
    league_id: str,
    stage: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Wrap snapshot contents in a consistent metadata envelope."""

    if not season:
        raise ValueError("season cannot be empty")

    if week < 1:
        raise ValueError("week must be at least 1")

    if not league_key:
        raise ValueError("league_key cannot be empty")

    if not league_id:
        raise ValueError("league_id cannot be empty")

    if stage not in VALID_SNAPSHOT_STAGES:
        raise ValueError(
            f"Unsupported snapshot stage: {stage}"
        )

    if not isinstance(data, dict):
        raise ValueError("snapshot data must be a dictionary")

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "season": season,
        "week": week,
        "league_key": league_key,
        "league_id": league_id,
        "stage": stage,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "data": data,
    }


def _write_json_exclusive(
    path: Path,
    document: dict[str, Any],
) -> None:
    """Write JSON only if the destination does not already exist."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    created_file = False

    try:
        with path.open(
            "x",
            encoding="utf-8",
        ) as file:
            created_file = True

            json.dump(
                document,
                file,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )

            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

    except FileExistsError as exc:
        raise SnapshotExistsError(
            f"Snapshot already exists and will not "
            f"be overwritten: {path}"
        ) from exc

    except (OSError, TypeError, ValueError) as exc:
        if created_file:
            try:
                path.unlink()
            except OSError:
                pass

        raise SnapshotStorageError(
            f"Could not safely write snapshot: {path}"
        ) from exc


def write_snapshot(
    data_root: Path,
    season: str,
    week: int,
    league_key: str,
    league_id: str,
    stage: str,
    data: dict[str, Any],
) -> Path:
    """Create one immutable official weekly snapshot."""

    path = build_snapshot_path(
        data_root=data_root,
        season=season,
        league_key=league_key,
        week=week,
        stage=stage,
    )

    document = build_snapshot_document(
        season=season,
        week=week,
        league_key=league_key,
        league_id=league_id,
        stage=stage,
        data=data,
    )

    _write_json_exclusive(
        path,
        document,
    )

    return path


def read_snapshot(
    path: Path,
) -> dict[str, Any]:
    """Read and validate one stored snapshot."""

    if not path.exists():
        raise SnapshotStorageError(
            f"Snapshot does not exist: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            document = json.load(file)

    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotStorageError(
            f"Could not read snapshot: {path}"
        ) from exc

    if not isinstance(document, dict):
        raise SnapshotValidationError(
            "Snapshot root must be a JSON object"
        )

    if (
        document.get("schema_version")
        != SNAPSHOT_SCHEMA_VERSION
    ):
        raise SnapshotValidationError(
            "Unsupported snapshot schema version"
        )

    season = document.get("season")
    league_key = document.get("league_key")
    league_id = document.get("league_id")
    week = document.get("week")
    stage = document.get("stage")
    data = document.get("data")

    if not isinstance(season, str) or not season:
        raise SnapshotValidationError(
            "Snapshot is missing a valid season"
        )

    if not isinstance(league_key, str) or not league_key:
        raise SnapshotValidationError(
            "Snapshot is missing a valid league_key"
        )

    if not isinstance(league_id, str) or not league_id:
        raise SnapshotValidationError(
            "Snapshot is missing a valid league_id"
        )

    if not isinstance(week, int) or week < 1:
        raise SnapshotValidationError(
            "Snapshot is missing a valid week"
        )

    if stage not in VALID_SNAPSHOT_STAGES:
        raise SnapshotValidationError(
            "Snapshot contains an unsupported stage"
        )

    if not isinstance(data, dict):
        raise SnapshotValidationError(
            "Snapshot is missing a valid data object"
        )

    return document