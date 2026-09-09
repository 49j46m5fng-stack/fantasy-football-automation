from unittest.mock import Mock, patch

import pytest
import requests

from src.projections import (
    DEFAULT_USER_AGENT,
    PlayerProjection,
    ProjectionAPIError,
    SleeperProjectionProvider,
    build_projection_lookup,
    filter_projection_category,
    get_projected_points,
    normalize_week_projection_payload,
)


def test_normalizes_list_shape_and_preserves_metadata() -> None:
    payload = [
        {
            "player_id": "4984",
            "category": "proj",
            "company": "sleeper",
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

    projection = projections[0]

    assert projection.player_id == "4984"
    assert projection.category == "proj"
    assert projection.company == "sleeper"
    assert projection.stats["pts_ppr"] == 21.11


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


def test_filter_projection_category_keeps_only_proj() -> None:
    projections = [
        PlayerProjection(
            player_id="1",
            season="2026",
            week=1,
            stats={"pts_ppr": 10.0},
            category="proj",
        ),
        PlayerProjection(
            player_id="1",
            season="2026",
            week=1,
            stats={"adp_dd_ppr": 50.0},
            category="adp",
        ),
    ]

    filtered = filter_projection_category(
        projections,
        "proj",
    )

    assert len(filtered) == 1
    assert filtered[0].category == "proj"
    assert filtered[0].stats["pts_ppr"] == 10.0


def test_build_projection_lookup_rejects_duplicates() -> None:
    projections = [
        PlayerProjection(
            player_id="1",
            season="2026",
            week=1,
            stats={},
        ),
        PlayerProjection(
            player_id="1",
            season="2026",
            week=1,
            stats={},
        ),
    ]

    with pytest.raises(
        ProjectionAPIError,
        match="Duplicate projection record",
    ):
        build_projection_lookup(projections)


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
def test_provider_filters_to_proj_by_default(
    mock_get: Mock,
) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None

    fake_response.json.return_value = [
        {
            "player_id": "4984",
            "category": "proj",
            "stats": {
                "pts_ppr": 21.11,
            },
        },
        {
            "player_id": "4984",
            "category": "adp",
            "stats": {
                "adp_dd_ppr": 10.0,
            },
        },
    ]

    mock_get.return_value = fake_response

    provider = SleeperProjectionProvider()

    projections = provider.get_week_projections(
        season="2026",
        week=1,
    )

    assert len(projections) == 1
    assert projections[0].category == "proj"

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
def test_provider_can_return_all_categories(
    mock_get: Mock,
) -> None:
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None

    fake_response.json.return_value = [
        {
            "player_id": "1",
            "category": "proj",
            "stats": {},
        },
        {
            "player_id": "1",
            "category": "adp",
            "stats": {},
        },
    ]

    mock_get.return_value = fake_response

    provider = SleeperProjectionProvider()

    projections = provider.get_week_projections(
        season="2026",
        week=1,
        category=None,
    )

    assert len(projections) == 2


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