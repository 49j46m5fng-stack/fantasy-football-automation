from pathlib import Path

import pytest

from src.orchestration import (
    OrchestrationError,
    preview_report_path,
    snapshot_pair_state,
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
            "baseline",
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
            "baseline",
        )
        == "complete"
    )


def test_partial_snapshot_pair_rejected(
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
        OrchestrationError,
        match="Partial baseline",
    ):
        snapshot_pair_state(
            paths,
            "baseline",
        )


def test_preview_report_path() -> None:
    path = preview_report_path(
        season="2026",
        league_key="goats",
        week=7,
    )

    assert path == Path(
        "reports/2026/"
        "goats_week_07_preview.md"
    )