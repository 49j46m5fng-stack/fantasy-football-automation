from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.freeze_week1_baseline import (
    FreezeBaselineError,
    freeze_window_status,
    snapshot_state,
)


TIMEZONE = ZoneInfo(
    "America/Chicago"
)


def test_freeze_window_before_opening() -> None:
    now = datetime(
        2026,
        9,
        9,
        17,
        59,
        tzinfo=TIMEZONE,
    )

    assert (
        freeze_window_status(now)
        == "too_early"
    )


def test_freeze_window_is_open() -> None:
    now = datetime(
        2026,
        9,
        9,
        18,
        30,
        tzinfo=TIMEZONE,
    )

    assert (
        freeze_window_status(now)
        == "open"
    )


def test_freeze_window_after_kickoff() -> None:
    now = datetime(
        2026,
        9,
        9,
        19,
        20,
        tzinfo=TIMEZONE,
    )

    assert (
        freeze_window_status(now)
        == "too_late"
    )


def test_snapshot_state_absent(
    tmp_path: Path,
) -> None:
    targets = {
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
        snapshot_state(targets)
        == "absent"
    )


def test_snapshot_state_complete(
    tmp_path: Path,
) -> None:
    targets = {
        "goats": (
            tmp_path
            / "goats.json"
        ),
        "doats": (
            tmp_path
            / "doats.json"
        ),
    }

    for path in targets.values():
        path.write_text(
            "{}",
            encoding="utf-8",
        )

    assert (
        snapshot_state(targets)
        == "complete"
    )


def test_partial_snapshot_state_is_rejected(
    tmp_path: Path,
) -> None:
    targets = {
        "goats": (
            tmp_path
            / "goats.json"
        ),
        "doats": (
            tmp_path
            / "doats.json"
        ),
    }

    targets["goats"].write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        FreezeBaselineError,
        match="Partial baseline state",
    ):
        snapshot_state(
            targets
        )