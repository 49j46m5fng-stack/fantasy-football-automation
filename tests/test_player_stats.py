import pytest

from src.player_stats import (
    PlayerStatsError,
    PlayerWeekStat,
    actual_ppr_points,
    build_week_stat_lookup,
    parse_week_stats_payload,
)


def test_parse_mapping_payload() -> None:
    records = (
        parse_week_stats_payload(
            payload={
                "123": {
                    "pts_ppr": 18.5,
                    "rec": 5,
                }
            },
            season="2025",
            week=1,
        )
    )

    assert len(
        records
    ) == 1

    assert (
        records[0].player_id
        == "123"
    )

    assert (
        records[0].stats[
            "pts_ppr"
        ]
        == 18.5
    )


def test_parse_list_with_nested_stats() -> None:
    records = (
        parse_week_stats_payload(
            payload=[
                {
                    "player_id": "123",
                    "category": "stat",
                    "company": (
                        "sportradar"
                    ),
                    "stats": {
                        "pts_ppr": 14.25,
                        "rec": 4,
                    },
                }
            ],
            season="2025",
            week=1,
        )
    )

    assert len(
        records
    ) == 1

    record = records[0]

    assert (
        record.player_id
        == "123"
    )

    assert (
        record.category
        == "stat"
    )

    assert (
        record.company
        == "sportradar"
    )

    assert (
        record.stats["rec"]
        == 4
    )


def test_parse_list_with_flat_stats() -> None:
    records = (
        parse_week_stats_payload(
            payload=[
                {
                    "player_id": "123",
                    "category": "stat",
                    "season": "2025",
                    "week": 1,
                    "team": "AAA",
                    "pts_ppr": 22.0,
                    "rush_yd": 100,
                }
            ],
            season="2025",
            week=1,
        )
    )

    assert (
        records[0].stats[
            "pts_ppr"
        ]
        == 22.0
    )

    assert (
        records[0].stats[
            "rush_yd"
        ]
        == 100
    )

    assert (
        "season"
        not in records[0].stats
    )


def test_team_aggregate_rows_are_ignored() -> None:
    records = (
        parse_week_stats_payload(
            payload={
                "TEAM_SEA": {
                    "pts_ppr": 99.0,
                },
                "123": {
                    "pts_ppr": 12.0,
                },
            },
            season="2025",
            week=1,
        )
    )

    assert [
        record.player_id
        for record
        in records
    ] == [
        "123"
    ]


def test_defense_abbreviation_is_not_ignored() -> None:
    records = (
        parse_week_stats_payload(
            payload={
                "SEA": {
                    "pts_ppr": 8.0,
                }
            },
            season="2025",
            week=1,
        )
    )

    assert len(
        records
    ) == 1

    assert (
        records[0].player_id
        == "SEA"
    )


def test_non_stat_category_is_ignored() -> None:
    records = (
        parse_week_stats_payload(
            payload=[
                {
                    "player_id": "123",
                    "category": (
                        "projection"
                    ),
                    "stats": {
                        "pts_ppr": 20.0,
                    },
                },
                {
                    "player_id": "456",
                    "category": "stat",
                    "stats": {
                        "pts_ppr": 10.0,
                    },
                },
            ],
            season="2025",
            week=1,
        )
    )

    assert [
        record.player_id
        for record
        in records
    ] == [
        "456"
    ]


def test_missing_ppr_stays_missing() -> None:
    record = PlayerWeekStat(
        player_id="123",
        season="2025",
        week=1,
        stats={
            "rush_yd": 25,
        },
    )

    assert (
        actual_ppr_points(
            record
        )
        is None
    )


def test_invalid_ppr_value_is_rejected() -> None:
    record = PlayerWeekStat(
        player_id="123",
        season="2025",
        week=1,
        stats={
            "pts_ppr": "12.5",
        },
    )

    with pytest.raises(
        PlayerStatsError,
        match="must be numeric",
    ):
        actual_ppr_points(
            record
        )


def test_duplicate_player_stats_are_rejected() -> None:
    records = [
        PlayerWeekStat(
            player_id="123",
            season="2025",
            week=1,
            stats={
                "pts_ppr": 10.0,
            },
        ),
        PlayerWeekStat(
            player_id="123",
            season="2025",
            week=1,
            stats={
                "pts_ppr": 11.0,
            },
        ),
    ]

    with pytest.raises(
        PlayerStatsError,
        match="Duplicate",
    ):
        build_week_stat_lookup(
            records
        )


def test_malformed_payload_is_rejected() -> None:
    with pytest.raises(
        PlayerStatsError,
        match=(
            "must be a list "
            "or object"
        ),
    ):
        parse_week_stats_payload(
            payload="bad",
            season="2025",
            week=1,
        )