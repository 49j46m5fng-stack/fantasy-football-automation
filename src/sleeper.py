"""Client for the documented Sleeper fantasy football API."""

from typing import Any

import requests


SLEEPER_BASE_URL = "https://api.sleeper.app/v1"


class SleeperAPIError(RuntimeError):
    """Raised when Sleeper data cannot be retrieved safely."""


class SleeperClient:
    """Small client for retrieving data from Sleeper's public API."""

    def __init__(
        self,
        base_url: str = SLEEPER_BASE_URL,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get(self, path: str) -> Any:
        """Send a GET request to Sleeper and return decoded JSON."""

        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            response = requests.get(
                url,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SleeperAPIError(
                f"Sleeper request failed for {url}: {exc}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise SleeperAPIError(
                f"Sleeper returned invalid JSON for {url}"
            ) from exc

    def _get_list(
        self,
        path: str,
        description: str,
    ) -> list[dict[str, Any]]:
        """Retrieve a Sleeper endpoint expected to return a list of objects."""

        data = self._get(path)

        if not isinstance(data, list):
            raise SleeperAPIError(
                f"Expected {description} to be a JSON list, "
                f"but received {type(data).__name__}"
            )

        if not all(isinstance(item, dict) for item in data):
            raise SleeperAPIError(
                f"Expected every {description} record to be a JSON object"
            )

        return data

    def get_league(self, league_id: str) -> dict[str, Any]:
        """Retrieve metadata for one Sleeper league."""

        if not league_id:
            raise ValueError("league_id cannot be empty")

        data = self._get(f"league/{league_id}")

        if not isinstance(data, dict):
            raise SleeperAPIError(
                f"Expected league data to be a JSON object, "
                f"but received {type(data).__name__}"
            )

        return data

    def get_users(self, league_id: str) -> list[dict[str, Any]]:
        """Retrieve users associated with a Sleeper league."""

        if not league_id:
            raise ValueError("league_id cannot be empty")

        return self._get_list(
            f"league/{league_id}/users",
            "league users",
        )

    def get_rosters(self, league_id: str) -> list[dict[str, Any]]:
        """Retrieve fantasy rosters for a Sleeper league."""

        if not league_id:
            raise ValueError("league_id cannot be empty")

        return self._get_list(
            f"league/{league_id}/rosters",
            "league rosters",
        )

    def get_matchups(
        self,
        league_id: str,
        week: int,
    ) -> list[dict[str, Any]]:
        """Retrieve fantasy matchup records for one league and week."""

        if not league_id:
            raise ValueError("league_id cannot be empty")

        if week < 1:
            raise ValueError("week must be at least 1")

        return self._get_list(
            f"league/{league_id}/matchups/{week}",
            "weekly matchups",
        )