import json
from pathlib import Path

import pytest

from src.storage import (
    SnapshotExistsError,
    SnapshotStorageError,
    SnapshotValidationError,
    build_snapshot_path,
    read_snapshot,
    write_snapshot,
)


SEASON = "2026"
LEAGUE_KEY = "goats"
LEAGUE_ID = "1400610465024839680"


def test_snapshot_path_uses_expected_layout(
    tmp_path: Path,
) -> None:
    path = build_snapshot_path(
        data_root=tmp_path,
        season=SEASON,
        league_key=LEAGUE_KEY,
        week=1,
        stage="baseline",
    )

    assert path == (
        tmp_path
        / "2026"
        / "goats"
        / "week_01_baseline.json"
    )


def test_snapshot_path_rejects_bad_week(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="week must be at least 1",
    ):
        build_snapshot_path(
            data_root=tmp_path,
            season=SEASON,
            league_key=LEAGUE_KEY,
            week=0,
            stage="baseline",
        )


def test_snapshot_path_rejects_unknown_stage(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported snapshot stage",
    ):
        build_snapshot_path(
            data_root=tmp_path,
            season=SEASON,
            league_key=LEAGUE_KEY,
            week=1,
            stage="mystery",
        )


def test_write_snapshot_creates_metadata_envelope(
    tmp_path: Path,
) -> None:
    path = write_snapshot(
        data_root=tmp_path,
        season=SEASON,
        week=1,
        league_key=LEAGUE_KEY,
        league_id=LEAGUE_ID,
        stage="baseline",
        data={
            "example": "value",
        },
    )

    stored = read_snapshot(path)

    assert stored["schema_version"] == 1
    assert stored["season"] == SEASON
    assert stored["week"] == 1
    assert stored["league_key"] == LEAGUE_KEY
    assert stored["league_id"] == LEAGUE_ID
    assert stored["stage"] == "baseline"
    assert stored["data"]["example"] == "value"
    assert isinstance(stored["created_at"], str)


def test_existing_snapshot_is_never_overwritten(
    tmp_path: Path,
) -> None:
    path = write_snapshot(
        data_root=tmp_path,
        season=SEASON,
        week=1,
        league_key=LEAGUE_KEY,
        league_id=LEAGUE_ID,
        stage="baseline",
        data={
            "version": "ORIGINAL",
        },
    )

    with pytest.raises(
        SnapshotExistsError,
        match="will not be overwritten",
    ):
        write_snapshot(
            data_root=tmp_path,
            season=SEASON,
            week=1,
            league_key=LEAGUE_KEY,
            league_id=LEAGUE_ID,
            stage="baseline",
            data={
                "version": "REPLACEMENT",
            },
        )

    stored = read_snapshot(path)

    assert stored["data"]["version"] == "ORIGINAL"


def test_read_snapshot_returns_stored_data(
    tmp_path: Path,
) -> None:
    path = write_snapshot(
        data_root=tmp_path,
        season=SEASON,
        week=5,
        league_key=LEAGUE_KEY,
        league_id=LEAGUE_ID,
        stage="sunday",
        data={
            "score": 123.45,
        },
    )

    stored = read_snapshot(path)

    assert stored["week"] == 5
    assert stored["stage"] == "sunday"
    assert stored["data"]["score"] == 123.45


def test_invalid_json_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "broken.json"

    path.write_text(
        "{not valid json",
        encoding="utf-8",
    )

    with pytest.raises(
        SnapshotStorageError,
        match="Could not read snapshot",
    ):
        read_snapshot(path)


def test_unsupported_schema_version_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "future.json"

    path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "season": "2026",
                "week": 1,
                "league_key": "goats",
                "league_id": LEAGUE_ID,
                "stage": "baseline",
                "created_at": "example",
                "data": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        SnapshotValidationError,
        match="schema version",
    ):
        read_snapshot(path)