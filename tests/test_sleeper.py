from unittest.mock import Mock, patch

import requests
import pytest

from src.sleeper import SleeperAPIError, SleeperClient


GOATS_LEAGUE_ID = "1400610465024839680"


@patch("src.sleeper.requests.get")
def test_get_league_returns_league_data(mock_get: Mock) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "league_id": GOATS_LEAGUE_ID,
        "name": "GOATs",
        "season": "2026",
    }

    mock_get.return_value = fake_response

    client = SleeperClient()
    league = client.get_league(GOATS_LEAGUE_ID)

    assert league["league_id"] == GOATS_LEAGUE_ID
    assert league["name"] == "GOATs"

    mock_get.assert_called_once_with(
        f"https://api.sleeper.app/v1/league/{GOATS_LEAGUE_ID}",
        timeout=15.0,
    )


@patch("src.sleeper.requests.get")
def test_network_failure_becomes_clear_error(mock_get: Mock) -> None:
    mock_get.side_effect = requests.RequestException("connection failed")

    client = SleeperClient()

    with pytest.raises(SleeperAPIError, match="Sleeper request failed"):
        client.get_league(GOATS_LEAGUE_ID)


def test_empty_league_id_is_rejected() -> None:
    client = SleeperClient()

    with pytest.raises(ValueError, match="league_id cannot be empty"):
        client.get_league("")