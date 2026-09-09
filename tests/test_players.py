import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.players import (
    PlayerCacheError,
    get_player_map,
    get_player_name,
    load_player_cache,
    save_player_cache,
)


def test_save_and_load_player_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "players.json"

    players = {
        "4984": {
            "player_id": "4984",
            "full_name": "Example Player",
            "position": "WR",
        }
    }

    save_player_cache(players, cache_path)

    loaded = load_player_cache(cache_path)

    assert loaded == players


def test_existing_cache_avoids_api_call(tmp_path: Path) -> None:
    cache_path = tmp_path / "players.json"

    players = {
        "4984": {
            "player_id": "4984",
            "full_name": "Cached Player",
        }
    }

    save_player_cache(players, cache_path)

    client = Mock()

    result = get_player_map(
        client,
        cache_path=cache_path,
    )

    assert result["4984"]["full_name"] == "Cached Player"

    client.get_players.assert_not_called()


def test_missing_cache_fetches_and_saves(tmp_path: Path) -> None:
    cache_path = tmp_path / "players.json"

    client = Mock()
    client.get_players.return_value = {
        "4984": {
            "player_id": "4984",
            "full_name": "Fetched Player",
        }
    }

    result = get_player_map(
        client,
        cache_path=cache_path,
    )

    assert result["4984"]["full_name"] == "Fetched Player"
    assert cache_path.exists()

    client.get_players.assert_called_once_with("nfl")


def test_refresh_fetches_even_when_cache_exists(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "players.json"

    save_player_cache(
        {
            "old": {
                "player_id": "old",
            }
        },
        cache_path,
    )

    client = Mock()
    client.get_players.return_value = {
        "new": {
            "player_id": "new",
        }
    }

    result = get_player_map(
        client,
        cache_path=cache_path,
        refresh=True,
    )

    assert "new" in result
    assert "old" not in result

    client.get_players.assert_called_once_with("nfl")


def test_missing_player_name_is_visible() -> None:
    players = {}

    assert (
        get_player_name("missing-player", players)
        == "UNKNOWN (missing-player)"
    )


def test_defense_name_has_safe_fallback() -> None:
    players = {
        "BUF": {
            "player_id": "BUF",
            "position": "DEF",
            "team": "BUF",
        }
    }

    assert get_player_name("BUF", players) == "BUF DEF"


def test_invalid_cache_is_rejected(tmp_path: Path) -> None:
    cache_path = tmp_path / "players.json"

    cache_path.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "players": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        PlayerCacheError,
        match="schema version",
    ):
        load_player_cache(cache_path)