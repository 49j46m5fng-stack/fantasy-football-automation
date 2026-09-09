import json
from pathlib import Path

from src.projections import PlayerProjection
from src.team_projections import (
    ProjectionOverride,
    calculate_team_projection,
    load_week_projection_overrides,
)


def test_normal_projection_uses_pts_ppr() -> None:
    matchup = {
        "roster_id": 1,
        "starters": ["player-1"],
    }

    projections = {
        "player-1": PlayerProjection(
            player_id="player-1",
            season="2026",
            week=1,
            stats={
                "pts_ppr": 12.5,
            },
        )
    }

    players = {
        "player-1": {
            "full_name": "Normal Player",
            "position": "RB",
            "injury_status": "NA",
        }
    }

    result = calculate_team_projection(
        matchup,
        projections,
        players,
        overrides={},
    )

    assert result.complete is True
    assert result.projected_points == 12.5
    assert result.starters[0].source == "sleeper_pts_ppr"


def test_explicit_out_player_without_ppr_gets_zero() -> None:
    matchup = {
        "roster_id": 1,
        "starters": ["player-1"],
    }

    projections = {
        "player-1": PlayerProjection(
            player_id="player-1",
            season="2026",
            week=1,
            stats={},
        )
    }

    players = {
        "player-1": {
            "full_name": "Out Player",
            "position": "RB",
            "injury_status": "Out",
        }
    }

    result = calculate_team_projection(
        matchup,
        projections,
        players,
        overrides={},
    )

    assert result.complete is True
    assert result.projected_points == 0.0
    assert result.starters[0].source == "sleeper_out_zero"


def test_missing_ppr_without_safe_status_is_unresolved() -> None:
    matchup = {
        "roster_id": 1,
        "starters": ["player-1"],
    }

    projections = {
        "player-1": PlayerProjection(
            player_id="player-1",
            season="2026",
            week=1,
            stats={},
        )
    }

    players = {
        "player-1": {
            "full_name": "Unknown Status Player",
            "position": "RB",
            "injury_status": "NA",
        }
    }

    result = calculate_team_projection(
        matchup,
        projections,
        players,
        overrides={},
    )

    assert result.complete is False
    assert result.projected_points is None
    assert result.starters[0].points is None
    assert (
        result.starters[0].source
        == "missing_projected_points"
    )


def test_manual_override_resolves_missing_projection() -> None:
    matchup = {
        "roster_id": 1,
        "starters": ["player-1"],
    }

    projections = {
        "player-1": PlayerProjection(
            player_id="player-1",
            season="2026",
            week=1,
            stats={},
        )
    }

    players = {
        "player-1": {
            "full_name": "Override Player",
            "position": "RB",
            "injury_status": "NA",
        }
    }

    overrides = {
        "player-1": ProjectionOverride(
            points=0.0,
            reason="Confirmed out.",
        )
    }

    result = calculate_team_projection(
        matchup,
        projections,
        players,
        overrides,
    )

    assert result.complete is True
    assert result.projected_points == 0.0
    assert result.starters[0].source == "manual_override"


def test_only_starting_players_count() -> None:
    matchup = {
        "roster_id": 1,
        "starters": [
            "starter-1",
            "starter-2",
        ],
        "players": [
            "starter-1",
            "starter-2",
            "bench-player",
        ],
    }

    projections = {
        "starter-1": PlayerProjection(
            player_id="starter-1",
            season="2026",
            week=1,
            stats={"pts_ppr": 10.0},
        ),
        "starter-2": PlayerProjection(
            player_id="starter-2",
            season="2026",
            week=1,
            stats={"pts_ppr": 20.0},
        ),
        "bench-player": PlayerProjection(
            player_id="bench-player",
            season="2026",
            week=1,
            stats={"pts_ppr": 100.0},
        ),
    }

    players = {
        player_id: {
            "full_name": player_id,
            "position": "RB",
        }
        for player_id in projections
    }

    result = calculate_team_projection(
        matchup,
        projections,
        players,
        overrides={},
    )

    assert result.projected_points == 30.0


def test_empty_starter_slot_contributes_zero_with_warning() -> None:
    matchup = {
        "roster_id": 6,
        "starters": [
            "player-1",
            "0",
        ],
    }

    projections = {
        "player-1": PlayerProjection(
            player_id="player-1",
            season="2026",
            week=1,
            stats={"pts_ppr": 10.0},
        )
    }

    players = {
        "player-1": {
            "full_name": "Player One",
            "position": "RB",
        }
    }

    result = calculate_team_projection(
        matchup,
        projections,
        players,
        overrides={},
    )

    assert result.complete is True
    assert result.projected_points == 10.0
    assert result.starters[1].source == "empty_slot"
    assert result.starters[1].points == 0.0
    assert len(result.warnings) == 1


def test_load_week_projection_override(tmp_path: Path) -> None:
    path = tmp_path / "projection_overrides.json"

    payload = {
        "schema_version": 1,
        "season": "2026",
        "weeks": {
            "1": {
                "5850": {
                    "points": 0.0,
                    "reason": "Confirmed out.",
                }
            }
        },
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    overrides = load_week_projection_overrides(
        path,
        week=1,
    )

    assert overrides["5850"].points == 0.0
    assert overrides["5850"].reason == "Confirmed out."