from unittest.mock import Mock, patch

import pytest
import requests

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
def test_get_users_returns_list(mock_get: Mock) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = [
        {
            "user_id": "user-1",
            "display_name": "Manager One",
        }
    ]

    mock_get.return_value = fake_response

    client = SleeperClient()
    users = client.get_users(GOATS_LEAGUE_ID)

    assert len(users) == 1
    assert users[0]["display_name"] == "Manager One"


@patch("src.sleeper.requests.get")
def test_get_rosters_returns_list(mock_get: Mock) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = [
        {
            "roster_id": 1,
            "owner_id": "user-1",
        }
    ]

    mock_get.return_value = fake_response

    client = SleeperClient()
    rosters = client.get_rosters(GOATS_LEAGUE_ID)

    assert len(rosters) == 1
    assert rosters[0]["roster_id"] == 1


@patch("src.sleeper.requests.get")
def test_get_matchups_returns_weekly_records(mock_get: Mock) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = [
        {
            "roster_id": 1,
            "matchup_id": 1,
            "points": 125.5,
        },
        {
            "roster_id": 2,
            "matchup_id": 1,
            "points": 118.2,
        },
    ]

    mock_get.return_value = fake_response

    client = SleeperClient()
    matchups = client.get_matchups(GOATS_LEAGUE_ID, week=1)

    assert len(matchups) == 2
    assert matchups[0]["matchup_id"] == 1
    assert matchups[1]["matchup_id"] == 1

    mock_get.assert_called_once_with(
        f"https://api.sleeper.app/v1/league/"
        f"{GOATS_LEAGUE_ID}/matchups/1",
        timeout=15.0,
    )


def test_matchup_week_must_be_positive() -> None:
    client = SleeperClient()

    with pytest.raises(ValueError, match="week must be at least 1"):
        client.get_matchups(GOATS_LEAGUE_ID, week=0)


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