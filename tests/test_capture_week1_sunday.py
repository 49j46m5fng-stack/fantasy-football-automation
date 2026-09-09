from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.capture_week1_sunday import (
    SundayCaptureError,
    capture_window_status,
    snapshot_pair_state,
)


TIMEZONE = ZoneInfo(
    "America/Chicago"
)


def test_wrong_capture_date() -> None:
    now = datetime(
        2026,
        9,
        13,
        12,
        0,
        tzinfo=TIMEZONE,
    )

    assert (
        capture_window_status(now)
        == "wrong_date"
    )


def test_before_capture_window() -> None:
    now = datetime(
        2026,
        9,
        14,
        11,
        29,
        tzinfo=TIMEZONE,
    )

    assert (
        capture_window_status(now)
        == "too_early"
    )


def test_capture_window_is_open() -> None:
    now = datetime(
        2026,
        9,
        14,
        11,
        45,
        tzinfo=TIMEZONE,
    )

    assert (
        capture_window_status(now)
        == "open"
    )


def test_mnf_kickoff_closes_window() -> None:
    now = datetime(
        2026,
        9,
        14,
        19,
        15,
        tzinfo=TIMEZONE,
    )

    assert (
        capture_window_status(now)
        == "too_late"
    )


def test_snapshot_pair_absent(
    tmp_path: Path,
) -> None:
    paths = {
        "goats": (
            tmp_path
            / "goats.json"
        ),
        "doats": (
            tmp_path
            / "doats.json"
        ),
    }

    assert (
        snapshot_pair_state(
            paths,
            "test",
        )
        == "absent"
    )


def test_snapshot_pair_complete(
    tmp_path: Path,
) -> None:
    paths = {
        "goats": (
            tmp_path
            / "goats.json"
        ),
        "doats": (
            tmp_path
            / "doats.json"
        ),
    }

    for path in paths.values():
        path.write_text(
            "{}",
            encoding="utf-8",
        )

    assert (
        snapshot_pair_state(
            paths,
            "test",
        )
        == "complete"
    )


def test_partial_snapshot_pair_is_rejected(
    tmp_path: Path,
) -> None:
    paths = {
        "goats": (
            tmp_path
            / "goats.json"
        ),
        "doats": (
            tmp_path
            / "doats.json"
        ),
    }

    paths[
        "goats"
    ].write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        SundayCaptureError,
        match="Partial test snapshot state",
    ):
        snapshot_pair_state(
            paths,
            "test",
        )