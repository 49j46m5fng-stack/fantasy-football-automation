import json
from pathlib import Path

import pytest

from src.agent_context import (
    AgentContextError,
    agent_context_path,
    build_agent_context_document,
    write_agent_context_file,
)
from src.storage import (
    write_snapshot,
)


SEASON = "2026"
LEAGUE_ID = "test-league"


def config() -> dict:
    return {
        "season": SEASON,
        "leagues": {
            "goats": {
                "name": "GOATs",
                "tier": 1,
                "league_id": (
                    LEAGUE_ID
                ),
                "playoff_spots": 8,
                "relegation_spots": 2,
            }
        },
        "promotion_rules": {
            "example": True,
        },
        "analytics": {
            "boom_threshold": 1.5,
            "bust_threshold": 0.8,
        },
        "simulation": {
            "simulations": 10000,
        },
    }


def player(
    player_id: str,
    name: str,
    points: float | None,
    source: str = "sleeper_pts_ppr",
    reason: str | None = None,
) -> dict:
    return {
        "player_id": player_id,
        "player_name": name,
        "position": "RB",
        "team": "TST",
        "injury_status": None,
        "projected_points": points,
        "projection_source": source,
        "projection_reason": reason,
    }


def baseline_data() -> dict:
    return {
        "league": {
            "name": "GOATs",
        },
        "projection_method": {
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
                "owner_id": "u1",
                "manager_name": (
                    "Manager One"
                ),
                "matchup_id": 1,
                "opponent_roster_id": 2,
                "baseline_starters_raw": [
                    "a",
                    "b",
                ],
                "baseline_projection": 22.0,
                "known_projected_points": 22.0,
                "projection_complete": True,
                "warnings": [],
                "starters": [
                    {
                        "slot": 1,
                        **player(
                            "a",
                            "Player A",
                            10.0,
                        ),
                    },
                    {
                        "slot": 2,
                        **player(
                            "b",
                            "Player B",
                            12.0,
                            source=(
                                "manual_override"
                            ),
                            reason=(
                                "Test override"
                            ),
                        ),
                    },
                ],
                "rostered_players": [
                    player(
                        "a",
                        "Player A",
                        10.0,
                    ),
                    player(
                        "b",
                        "Player B",
                        12.0,
                        source=(
                            "manual_override"
                        ),
                        reason=(
                            "Test override"
                        ),
                    ),
                    player(
                        "e",
                        "Player E",
                        15.0,
                    ),
                ],
            },
            {
                "roster_id": 2,
                "owner_id": "u2",
                "manager_name": (
                    "Manager Two"
                ),
                "matchup_id": 1,
                "opponent_roster_id": 1,
                "baseline_starters_raw": [
                    "c",
                    "d",
                ],
                "baseline_projection": 30.0,
                "known_projected_points": 30.0,
                "projection_complete": True,
                "warnings": [],
                "starters": [
                    {
                        "slot": 1,
                        **player(
                            "c",
                            "Player C",
                            20.0,
                        ),
                    },
                    {
                        "slot": 2,
                        **player(
                            "d",
                            "Player D",
                            10.0,
                        ),
                    },
                ],
                "rostered_players": [
                    player(
                        "c",
                        "Player C",
                        20.0,
                    ),
                    player(
                        "d",
                        "Player D",
                        10.0,
                    ),
                ],
            },
        ],
        "warnings": [],
    }


def sunday_data() -> dict:
    return {
        "league": {
            "name": "GOATs",
        },
        "projection_method": {
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
                "owner_id": "u1",
                "manager_name": (
                    "Manager One"
                ),
                "matchup_id": 1,
                "opponent_roster_id": 2,
                "stage_starters_raw": [
                    "a",
                    "e",
                ],
                "live_points": 51.0,
                "custom_points": None,
                "effective_live_points": 51.0,
                "stage_projection": 27.0,
                "known_projected_points": 27.0,
                "projection_complete": True,
                "warnings": [],
                "starters": [
                    {
                        "slot": 1,
                        **player(
                            "a",
                            "Player A",
                            12.0,
                        ),
                    },
                    {
                        "slot": 2,
                        **player(
                            "e",
                            "Player E",
                            15.0,
                        ),
                    },
                ],
                "rostered_players": [
                    player(
                        "a",
                        "Player A",
                        12.0,
                    ),
                    player(
                        "b",
                        "Player B",
                        11.0,
                    ),
                    player(
                        "e",
                        "Player E",
                        15.0,
                    ),
                ],
            },
            {
                "roster_id": 2,
                "owner_id": "u2",
                "manager_name": (
                    "Manager Two"
                ),
                "matchup_id": 1,
                "opponent_roster_id": 1,
                "stage_starters_raw": [
                    "c",
                    "d",
                ],
                "live_points": 48.0,
                "custom_points": None,
                "effective_live_points": 48.0,
                "stage_projection": 30.0,
                "known_projected_points": 30.0,
                "projection_complete": True,
                "warnings": [],
                "starters": [
                    {
                        "slot": 1,
                        **player(
                            "c",
                            "Player C",
                            20.0,
                        ),
                    },
                    {
                        "slot": 2,
                        **player(
                            "d",
                            "Player D",
                            10.0,
                        ),
                    },
                ],
                "rostered_players": [
                    player(
                        "c",
                        "Player C",
                        20.0,
                    ),
                    player(
                        "d",
                        "Player D",
                        10.0,
                    ),
                ],
            },
        ],
        "warnings": [],
    }


def write_baseline(
    tmp_path: Path,
) -> Path:
    return write_snapshot(
        data_root=tmp_path,
        season=SEASON,
        week=1,
        league_key="goats",
        league_id=LEAGUE_ID,
        stage="baseline",
        data=baseline_data(),
    )


def write_sunday(
    tmp_path: Path,
) -> Path:
    return write_snapshot(
        data_root=tmp_path,
        season=SEASON,
        week=1,
        league_key="goats",
        league_id=LEAGUE_ID,
        stage="sunday",
        data=sunday_data(),
    )


def test_agent_context_path() -> None:
    path = agent_context_path(
        Path("data"),
        SEASON,
        7,
        "baseline",
    )

    assert path == Path(
        "data/2026/agent/"
        "week_07_baseline.json"
    )


def test_baseline_context_contains_matchup_margin(
    tmp_path: Path,
) -> None:
    write_baseline(
        tmp_path
    )

    document = (
        build_agent_context_document(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="baseline",
        )
    )

    matchup = (
        document["leagues"]
        ["goats"]
        ["matchups"]
        [0]
    )

    assert (
        matchup[
            "projection_lead"
        ][
            "leader_manager_name"
        ]
        == "Manager Two"
    )

    assert (
        matchup[
            "projection_lead"
        ][
            "margin"
        ]
        == 8.0
    )


def test_baseline_context_contains_special_projection_note(
    tmp_path: Path,
) -> None:
    write_baseline(
        tmp_path
    )

    document = (
        build_agent_context_document(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="baseline",
        )
    )

    notes = (
        document["leagues"]
        ["goats"]
        ["teams"]
        [0]
        ["special_projection_notes"]
    )

    assert len(
        notes
    ) == 1

    assert (
        notes[0][
            "player_name"
        ]
        == "Player B"
    )

    assert (
        notes[0][
            "projection_source"
        ]
        == "manual_override"
    )


def test_sunday_context_contains_lineup_change(
    tmp_path: Path,
) -> None:
    write_baseline(
        tmp_path
    )

    write_sunday(
        tmp_path
    )

    document = (
        build_agent_context_document(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="sunday",
        )
    )

    comparison = (
        document["leagues"]
        ["goats"]
        ["baseline_comparison"]
        ["teams"]
        [0]
    )

    assert (
        comparison[
            "lineup_changed"
        ]
        is True
    )

    assert (
        comparison[
            "added_starters"
        ][0][
            "player_name"
        ]
        == "Player E"
    )

    assert (
        comparison[
            "removed_starters"
        ][0][
            "player_name"
        ]
        == "Player B"
    )


def test_sunday_context_contains_live_score_lead(
    tmp_path: Path,
) -> None:
    write_baseline(
        tmp_path
    )

    write_sunday(
        tmp_path
    )

    document = (
        build_agent_context_document(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="sunday",
        )
    )

    lead = (
        document["leagues"]
        ["goats"]
        ["matchups"]
        [0]
        ["live_score_lead"]
    )

    assert (
        lead[
            "leader_manager_name"
        ]
        == "Manager One"
    )

    assert (
        lead["margin"]
        == 3.0
    )


def test_agent_context_records_source_hash(
    tmp_path: Path,
) -> None:
    write_baseline(
        tmp_path
    )

    document = (
        build_agent_context_document(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="baseline",
        )
    )

    source = (
        document[
            "derived_from"
        ][
            "goats"
        ][
            "baseline_snapshot"
        ]
    )

    assert len(
        source["sha256"]
    ) == 64


def test_derived_context_can_be_rebuilt_deterministically(
    tmp_path: Path,
) -> None:
    write_baseline(
        tmp_path
    )

    path = (
        write_agent_context_file(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="baseline",
        )
    )

    first = path.read_bytes()

    write_agent_context_file(
        data_root=tmp_path,
        project_config=config(),
        season=SEASON,
        week=1,
        stage="baseline",
    )

    second = path.read_bytes()

    assert first == second

    parsed = json.loads(
        second
    )

    assert (
        parsed[
            "authoritative"
        ]
        is False
    )


def test_final_context_not_implemented(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        AgentContextError,
        match="not implemented",
    ):
        build_agent_context_document(
            data_root=tmp_path,
            project_config=config(),
            season=SEASON,
            week=1,
            stage="final",
        )