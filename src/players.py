"""Cache and look up Sleeper NFL player metadata."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.sleeper import SleeperClient


DEFAULT_PLAYER_CACHE_PATH = Path("data/cache/nfl_players.json")
PLAYER_CACHE_SCHEMA_VERSION = 1


class PlayerCacheError(RuntimeError):
    """Raised when the local player metadata cache is invalid."""


def save_player_cache(
    players: dict[str, dict[str, Any]],
    cache_path: Path = DEFAULT_PLAYER_CACHE_PATH,
) -> None:
    """Save Sleeper player metadata to a local cache file."""

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": PLAYER_CACHE_SCHEMA_VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players": players,
    }

    temporary_path = cache_path.with_suffix(
        cache_path.suffix + ".tmp"
    )

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    temporary_path.replace(cache_path)


def load_player_cache(
    cache_path: Path = DEFAULT_PLAYER_CACHE_PATH,
) -> dict[str, dict[str, Any]]:
    """Load and validate the local Sleeper player cache."""

    if not cache_path.exists():
        raise PlayerCacheError(
            f"Player cache does not exist: {cache_path}"
        )

    try:
        with cache_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise PlayerCacheError(
            f"Could not read player cache: {cache_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise PlayerCacheError(
            "Player cache root must be a JSON object"
        )

    if payload.get("schema_version") != PLAYER_CACHE_SCHEMA_VERSION:
        raise PlayerCacheError(
            "Unsupported player cache schema version"
        )

    players = payload.get("players")

    if not isinstance(players, dict):
        raise PlayerCacheError(
            "Player cache is missing a valid players object"
        )

    return players


def get_player_map(
    client: SleeperClient,
    cache_path: Path = DEFAULT_PLAYER_CACHE_PATH,
    refresh: bool = False,
) -> dict[str, dict[str, Any]]:
    """Return cached players, fetching from Sleeper only when needed."""

    if cache_path.exists() and not refresh:
        return load_player_cache(cache_path)

    players = client.get_players("nfl")
    save_player_cache(players, cache_path)

    return players


def get_player(
    player_id: str,
    players: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Return metadata for one Sleeper player ID, if available."""

    return players.get(player_id)


def get_player_name(
    player_id: str,
    players: dict[str, dict[str, Any]],
) -> str:
    """Return a human-readable name without hiding missing metadata."""

    player = get_player(player_id, players)

    if player is None:
        return f"UNKNOWN ({player_id})"

    full_name = player.get("full_name")

    if full_name:
        return str(full_name)

    first_name = player.get("first_name")
    last_name = player.get("last_name")

    name_parts = [
        str(part)
        for part in (first_name, last_name)
        if part
    ]

    if name_parts:
        return " ".join(name_parts)

    if player.get("position") == "DEF":
        team = player.get("team") or player_id
        return f"{team} DEF"

    return f"UNKNOWN ({player_id})"