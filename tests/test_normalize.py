import pytest

from src.normalize import (
    NormalizationError,
    normalize_rosters,
    pair_matchups,
)


LEAGUE_KEY = "goats"
LEAGUE_ID = "1400610465024839680"


def test_normalize_rosters_connects_owner_to_user() -> None:
    users = [
        {
            "user_id": "user-123",
            "display_name": "Tim",
        }
    ]

    rosters = [
        {
            "roster_id": 1,
            "owner_id": "user-123",
        }
    ]

    normalized = normalize_rosters(
        LEAGUE_KEY,
        LEAGUE_ID,
        users,
        rosters,
    )

    assert len(normalized) == 1

    roster = normalized[0]

    assert roster.roster_id == 1
    assert roster.owner_id == "user-123"
    assert roster.manager_name == "Tim"


def test_unknown_owner_is_marked_explicitly() -> None:
    users = []

    rosters = [
        {
            "roster_id": 1,
            "owner_id": "missing-user",
        }
    ]

    normalized = normalize_rosters(
        LEAGUE_KEY,
        LEAGUE_ID,
        users,
        rosters,
    )

    assert normalized[0].manager_name == "UNKNOWN"


def test_two_records_with_same_matchup_id_are_opponents() -> None:
    raw_matchups = [
        {
            "roster_id": 3,
            "matchup_id": 2,
        },
        {
            "roster_id": 8,
            "matchup_id": 2,
        },
    ]

    matchups = pair_matchups(
        LEAGUE_KEY,
        LEAGUE_ID,
        week=1,
        matchup_records=raw_matchups,
    )

    assert len(matchups) == 1

    matchup = matchups[0]

    assert matchup.roster_a_id == 3
    assert matchup.roster_b_id == 8

    assert matchup.opponent_of(3) == 8
    assert matchup.opponent_of(8) == 3


def test_matchup_requires_exactly_two_rosters() -> None:
    raw_matchups = [
        {
            "roster_id": 3,
            "matchup_id": 2,
        }
    ]

    with pytest.raises(
        NormalizationError,
        match="exactly 2 rosters",
    ):
        pair_matchups(
            LEAGUE_KEY,
            LEAGUE_ID,
            week=1,
            matchup_records=raw_matchups,
        )


def test_opponent_lookup_rejects_unrelated_roster() -> None:
    raw_matchups = [
        {
            "roster_id": 3,
            "matchup_id": 2,
        },
        {
            "roster_id": 8,
            "matchup_id": 2,
        },
    ]

    matchup = pair_matchups(
        LEAGUE_KEY,
        LEAGUE_ID,
        week=1,
        matchup_records=raw_matchups,
    )[0]

    with pytest.raises(
        ValueError,
        match="is not part of matchup",
    ):
        matchup.opponent_of(99)