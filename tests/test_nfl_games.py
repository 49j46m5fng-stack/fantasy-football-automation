"""Tests for NFL game-state normalization."""

from datetime import datetime, timezone

import pytest

from src.nfl_games import (
    NFLGame,
    NFLGameAPIError,
    build_team_game_state_lookup,
    normalize_game_status,
    normalize_team_abbreviation,
    parse_espn_game,
    parse_kickoff,
    unknown_team_game_state,
)


def test_normalize_team_abbreviation() -> None:
    assert normalize_team_abbreviation("kc") == "KC"
    assert normalize_team_abbreviation("WSH") == "WAS"
    assert normalize_team_abbreviation("JAC") == "JAX"


def test_normalize_scheduled_status() -> None:
    assert normalize_game_status("pre") == "scheduled"
    assert normalize_game_status("scheduled") == "scheduled"


def test_normalize_in_progress_status() -> None:
    assert normalize_game_status("in") == "in_progress"
    assert normalize_game_status("live") == "in_progress"


def test_normalize_final_status() -> None:
    assert normalize_game_status("post") == "final"
    assert normalize_game_status("closed") == "final"


def test_unknown_status() -> None:
    assert normalize_game_status(None) == "unknown"
    assert normalize_game_status("something-new") == "unknown"


def test_parse_kickoff() -> None:
    result = parse_kickoff(
        "2026-09-15T00:15:00Z"
    )

    assert result == datetime(
        2026,
        9,
        15,
        0,
        15,
        tzinfo=timezone.utc,
    )


def test_parse_kickoff_rejects_naive_datetime() -> None:
    with pytest.raises(NFLGameAPIError):
        parse_kickoff(
            "2026-09-15T00:15:00"
        )


def test_parse_espn_game() -> None:
    event = {
        "id": "game-1",
        "date": "2026-09-15T00:15:00Z",
        "status": {
            "type": {
                "state": "pre",
            }
        },
        "competitions": [
            {
                "date": "2026-09-15T00:15:00Z",
                "competitors": [
                    {
                        "homeAway": "away",
                        "team": {
                            "abbreviation": "DEN",
                        },
                    },
                    {
                        "homeAway": "home",
                        "team": {
                            "abbreviation": "KC",
                        },
                    },
                ],
            }
        ],
    }

    result = parse_espn_game(
        event,
        season=2026,
        week=1,
    )

    assert result.game_id == "game-1"
    assert result.season == 2026
    assert result.week == 1
    assert result.away_team == "DEN"
    assert result.home_team == "KC"
    assert result.status == "scheduled"


def test_build_team_game_state_lookup() -> None:
    game = NFLGame(
        game_id="game-1",
        season=2026,
        week=1,
        kickoff=datetime(
            2026,
            9,
            15,
            0,
            15,
            tzinfo=timezone.utc,
        ),
        away_team="DEN",
        home_team="KC",
        status="scheduled",
    )

    result = build_team_game_state_lookup(
        [game]
    )

    assert result["DEN"].team == "DEN"
    assert result["DEN"].opponent == "KC"
    assert result["DEN"].status == "scheduled"

    assert result["KC"].team == "KC"
    assert result["KC"].opponent == "DEN"
    assert result["KC"].status == "scheduled"


def test_duplicate_team_game_is_rejected() -> None:
    kickoff = datetime(
        2026,
        9,
        15,
        0,
        15,
        tzinfo=timezone.utc,
    )

    games = [
        NFLGame(
            game_id="game-1",
            season=2026,
            week=1,
            kickoff=kickoff,
            away_team="DEN",
            home_team="KC",
            status="scheduled",
        ),
        NFLGame(
            game_id="game-2",
            season=2026,
            week=1,
            kickoff=kickoff,
            away_team="KC",
            home_team="LV",
            status="scheduled",
        ),
    ]

    with pytest.raises(NFLGameAPIError):
        build_team_game_state_lookup(
            games
        )


def test_unknown_team_state() -> None:
    result = unknown_team_game_state(
        "DEN"
    )

    assert result.team == "DEN"
    assert result.status == "unknown"
    assert result.game_id is None
    assert result.kickoff is None
    assert result.opponent is None