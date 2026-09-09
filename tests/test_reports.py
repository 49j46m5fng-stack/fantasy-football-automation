from pathlib import Path

import pytest

from src.reports import (
    ReportError,
    generate_baseline_preview_markdown,
    write_preview_report,
)
from src.storage import write_snapshot


def sample_baseline_data():
    return {
        "league": {
            "name": "Test League",
        },
        "projection_method": {
            "provider": "test",
            "category": "proj",
            "point_field": "pts_ppr",
            "exact_league_scoring": False,
        },
        "matchups": [
            {
                "matchup_id": 1,
                "roster_a_id": 1,
                "roster_b_id": 2,
            }
        ],
        "teams": [
            {
                "roster_id": 1,
                "manager_name": "Manager One",
                "baseline_projection": 125.5,
                "starters": [
                    {
                        "player_name": "Normal Player",
                        "projected_points": 15.5,
                        "projection_source": (
                            "sleeper_pts_ppr"
                        ),
                        "projection_reason": None,
                    }
                ],
            },
            {
                "roster_id": 2,
                "manager_name": "Manager Two",
                "baseline_projection": 110.0,
                "starters": [
                    {
                        "player_name": "Out Player",
                        "projected_points": 0.0,
                        "projection_source": (
                            "sleeper_out_zero"
                        ),
                        "projection_reason": (
                            "Sleeper reports player Out."
                        ),
                    }
                ],
            },
        ],
        "warnings": [
            "Example lineup warning."
        ],
    }


def sample_snapshot():
    return {
        "schema_version": 1,
        "season": "2026",
        "week": 1,
        "league_key": "goats",
        "league_id": "test-league",
        "stage": "baseline",
        "created_at": (
            "2026-09-09T23:00:00+00:00"
        ),
        "data": sample_baseline_data(),
    }


def test_preview_contains_matchup() -> None:
    report = (
        generate_baseline_preview_markdown(
            sample_snapshot()
        )
    )

    assert (
        "Manager One vs Manager Two"
        in report
    )

    assert "125.50" in report
    assert "110.00" in report


def test_preview_contains_special_projection_note() -> None:
    report = (
        generate_baseline_preview_markdown(
            sample_snapshot()
        )
    )

    assert "Out Player" in report

    assert (
        "sleeper_out_zero"
        in report
    )


def test_preview_contains_warning() -> None:
    report = (
        generate_baseline_preview_markdown(
            sample_snapshot()
        )
    )

    assert (
        "Example lineup warning."
        in report
    )


def test_preview_rejects_non_baseline_stage() -> None:
    snapshot = sample_snapshot()
    snapshot["stage"] = "final"

    with pytest.raises(
        ReportError,
        match="baseline snapshot",
    ):
        generate_baseline_preview_markdown(
            snapshot
        )


def test_preview_rejects_unknown_matchup_roster() -> None:
    snapshot = sample_snapshot()

    snapshot["data"][
        "matchups"
    ][0][
        "roster_b_id"
    ] = 999

    with pytest.raises(
        ReportError,
        match="unknown roster",
    ):
        generate_baseline_preview_markdown(
            snapshot
        )


def test_write_preview_report(
    tmp_path: Path,
) -> None:
    snapshot_path = write_snapshot(
        data_root=tmp_path,
        season="2026",
        week=1,
        league_key="goats",
        league_id="test-league",
        stage="baseline",
        data=sample_baseline_data(),
    )

    report_path = (
        tmp_path
        / "reports"
        / "week_01_preview.md"
    )

    result = write_preview_report(
        snapshot_path,
        report_path,
    )

    assert result == report_path
    assert report_path.exists()

    contents = report_path.read_text(
        encoding="utf-8",
    )

    assert (
        "# Test League — 2026 Week 1 Preview"
        in contents
    )