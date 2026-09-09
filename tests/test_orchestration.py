from pathlib import Path

import pytest

from src.orchestration import (
    OrchestrationError,
    snapshot_pair_state,
    snapshot_paths,
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


def test_snapshot_paths_use_canonical_layout(
    tmp_path: Path,
) -> None:
    config = {
        "leagues": {
            "goats": {},
            "doats": {},
        }
    }

    paths = snapshot_paths(
        config=config,
        season="2026",
        week=7,
        stage="baseline",
        data_root=tmp_path,
    )

    assert (
        paths["goats"]
        == tmp_path
        / "2026"
        / "goats"
        / "week_07_baseline.json"
    )

    assert (
        paths["doats"]
        == tmp_path
        / "2026"
        / "doats"
        / "week_07_baseline.json"
    )