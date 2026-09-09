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