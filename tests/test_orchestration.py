from pathlib import Path

import pytest

from src.orchestration import (
    OrchestrationError,
    _validate_sunday_remaining_snapshot,
    run_final_with_derived_analytics,
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


def test_sunday_snapshot_requires_remaining_analytics() -> None:
    data = {
        "teams": [
            {
                "roster_id": 1,
            },
            {
                "roster_id": 2,
            },
        ]
    }

    with pytest.raises(
        OrchestrationError,
        match="missing remaining-player analytics",
    ):
        _validate_sunday_remaining_snapshot(
            data=data,
            league_name="GOATs",
        )


def test_sunday_remaining_rosters_must_match_teams() -> None:
    data = {
        "teams": [
            {
                "roster_id": 1,
            },
            {
                "roster_id": 2,
            },
        ],
        "remaining": {
            "teams": {
                "1": {},
            }
        },
    }

    with pytest.raises(
        OrchestrationError,
        match="roster set",
    ):
        _validate_sunday_remaining_snapshot(
            data=data,
            league_name="GOATs",
        )


def test_sunday_remaining_rosters_accept_complete_set() -> None:
    data = {
        "teams": [
            {
                "roster_id": 1,
            },
            {
                "roster_id": 2,
            },
        ],
        "remaining": {
            "teams": {
                "1": {},
                "2": {},
            }
        },
    }

    _validate_sunday_remaining_snapshot(
        data=data,
        league_name="GOATs",
    )


def test_final_capture_survives_derived_analytics_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A derived failure must not block committing final history."""

    agent_context_calls: list[tuple[str, int, str]] = []

    monkeypatch.setattr(
        "src.orchestration.run_final",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(
        "src.orchestration.load_project_config",
        lambda: {"season": "2026"},
    )
    monkeypatch.setattr(
        "src.orchestration._validate_project_season",
        lambda config, schedule: "2026",
    )
    monkeypatch.setattr(
        "src.orchestration._write_agent_context",
        lambda config, season, week, stage: agent_context_calls.append(
            (season, week, stage)
        ),
    )
    monkeypatch.setattr(
        "src.donut_orchestration.run_donuts",
        lambda **kwargs: 1,
    )
    monkeypatch.setattr(
        "src.season_orchestration.run_analytics",
        lambda **kwargs: 0,
    )

    status = run_final_with_derived_analytics(
        week=3,
        schedule=object(),
        check_only=False,
    )

    assert status == 0
    assert agent_context_calls == [
        ("2026", 3, "final"),
    ]
