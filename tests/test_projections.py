from unittest.mock import Mock, patch

import pytest
import requests

from src.projections import (
    DEFAULT_USER_AGENT,
    PlayerProjection,
    ProjectionAPIError,
    SleeperProjectionProvider,
    get_projected_points,
    normalize_week_projection_payload,
)


def test_normalizes_list_projection_shape() -> None:
    payload = [
        {
            "player_id": "4984",
            "season": "2026",
            "week": 1,
            "stats": {
                "pts_ppr": 21.11,
                "rec_yd": 85.0,
            },
        }
    ]

    projections = normalize_week_projection_payload(
        payload,
        season="2026",
        week=1,
    )

    assert len(projections) == 1
    assert projections[0].player_id == "4984"
    assert projections[0].stats["pts_ppr"] == 21.11


def test_normalizes_player_id_keyed_shape() -> None:
    payload = {
        "4984": {
            "pts_ppr": 21.11,
            "rec_yd": 85.0,
        }
    }

    projections = normalize_week_projection_payload(
        payload,
        season="2026",
        week=1,
    )

    assert len(projections) == 1
    assert projections[0].player_id == "4984"
    assert projections[0].stats["pts_ppr"] == 21.11


def test_get_projected_points_returns_float() -> None:
    projection = PlayerProjection(
        player_id="4984",
        season="2026",
        week=1,
        stats={"pts_ppr": 21},
    )

    assert get_projected_points(
        projection,
        "pts_ppr",
    ) == 21.0


def test_missing_projection_field_returns_none() -> None:
    projection = PlayerProjection(
        player_id="4984",
        season="2026",
        week=1,
        stats={},
    )

    assert (
        get_projected_points(
            projection,
            "pts_ppr",
        )
        is None
    )


def test_non_numeric_projection_field_is_rejected() -> None:
    projection = PlayerProjection(
        player_id="4984",
        season="2026",
        week=1,
        stats={"pts_ppr": "unknown"},
    )

    with pytest.raises(
        ProjectionAPIError,
        match="is not numeric",
    ):
        get_projected_points(
            projection,
            "pts_ppr",
        )


@patch("src.projections.requests.get")
def test_provider_fetches_week(mock_get: Mock) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "4984": {
            "pts_ppr": 21.11,
        }
    }

    mock_get.return_value = fake_response

    provider = SleeperProjectionProvider()

    projections = provider.get_week_projections(
        season="2026",
        week=1,
    )

    assert len(projections) == 1
    assert projections[0].player_id == "4984"

    mock_get.assert_called_once_with(
        "https://api.sleeper.com/projections/nfl/2026/1",
        params={
            "season_type": "regular",
        },
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
        },
        timeout=30.0,
    )


@patch("src.projections.requests.get")
def test_projection_network_failure_is_clear(
    mock_get: Mock,
) -> None:
    mock_get.side_effect = requests.RequestException(
        "connection failed"
    )

    provider = SleeperProjectionProvider()

    with pytest.raises(
        ProjectionAPIError,
        match="Projection request failed",
    ):
        provider.get_week_projections(
            season="2026",
            week=1,
        )


def test_projection_week_must_be_positive() -> None:
    provider = SleeperProjectionProvider()

    with pytest.raises(
        ValueError,
        match="week must be at least 1",
    ):
        provider.get_week_projections(
            season="2026",
            week=0,
        )