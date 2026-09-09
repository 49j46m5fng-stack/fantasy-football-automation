import pytest

from src.player_stats import (
    PlayerWeekStat,
)
from src.scoring import (
    FantasyScoringError,
    normalize_scoring_settings,
    score_player_week,
    score_raw_stats,
)


OFFENSE_SCORING = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -1.0,
    "pass_2pt": 2.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rush_2pt": 2.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "rec_2pt": 2.0,
    "fum_lost": -2.0,
}


KICKER_SCORING = {
    "fgm_0_19": 3.0,
    "fgm_20_29": 3.0,
    "fgm_30_39": 3.0,
    "fgm_40_49": 4.0,
    "fgm_50_59": 5.0,
    "fgm_60p": 6.0,
    "fgmiss": -1.0,
    "xpm": 1.0,
    "xpmiss": -1.0,
}


DEFENSE_SCORING = {
    "sack": 1.0,
    "int": 2.0,
    "ff": 1.0,
    "fum_rec": 2.0,
    "safe": 2.0,
    "blk_kick": 2.0,
    "def_td": 6.0,
    "def_st_td": 6.0,
    "def_st_ff": 1.0,
    "def_st_fum_rec": 1.0,
    "def_2pt": 2.0,
    "pts_allow_0": 5.0,
    "pts_allow_1_6": 4.0,
    "pts_allow_7_13": 2.0,
    "pts_allow_14_20": 1.0,
    "pts_allow_21_27": 0.0,
    "pts_allow_28_34": -1.0,
    "pts_allow_35p": -4.0,
    "yds_allow_0_100": 5.0,
    "yds_allow_100_199": 4.0,
    "yds_allow_200_299": 2.0,
    "yds_allow_300_349": 1.0,
    "yds_allow_350_399": 0.0,
    "yds_allow_400_449": -1.0,
    "yds_allow_450_499": -4.0,
    "yds_allow_500_549": -5.0,
    "yds_allow_550p": -5.0,
}


def test_standard_ppr_offensive_scoring() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "pass_yd": 250,
                "pass_td": 2,
                "pass_int": 1,
                "rush_yd": 25,
                "rec": 2,
                "rec_yd": 18,
            },
            scoring_settings=(
                OFFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        23.3
    )


def test_receiving_touchdown_and_ppr() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "rec": 7,
                "rec_yd": 84,
                "rec_td": 1,
            },
            scoring_settings=(
                OFFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        21.4
    )


def test_negative_yardage_is_preserved() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "rec": 1,
                "rec_yd": -3,
            },
            scoring_settings=(
                OFFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        0.7
    )


def test_missing_counting_stat_contributes_zero() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "rush_yd": 50,
            },
            scoring_settings=(
                OFFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        5.0
    )


def test_missing_player_record_stays_missing() -> None:
    assert (
        score_player_week(
            None,
            OFFENSE_SCORING,
        )
        is None
    )


def test_score_player_week_preserves_identity() -> None:
    record = PlayerWeekStat(
        player_id="123",
        season="2025",
        week=1,
        stats={
            "rec": 5,
            "rec_yd": 50,
        },
    )

    scored = (
        score_player_week(
            record,
            OFFENSE_SCORING,
        )
    )

    assert scored is not None

    assert (
        scored.player_id
        == "123"
    )

    assert (
        scored.points
        == pytest.approx(
            10.0
        )
    )


def test_points_allowed_bucket_is_derived() -> None:
    points, contributions = (
        score_raw_stats(
            stats={
                "pts_allow": 10,
            },
            scoring_settings=(
                DEFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        2.0
    )

    assert (
        contributions[0]
        .scoring_key
        == "pts_allow_7_13"
    )

    assert (
        contributions[0]
        .source
        == "derived"
    )


def test_shutout_sparse_direct_bucket_is_preserved() -> None:
    points, contributions = (
        score_raw_stats(
            stats={
                "pts_allow_0": 1,
            },
            scoring_settings=(
                DEFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        5.0
    )

    assert (
        contributions[0]
        .source
        == "raw"
    )


def test_yards_allowed_bucket_is_derived() -> None:
    points, contributions = (
        score_raw_stats(
            stats={
                "yds_allow": 280,
            },
            scoring_settings=(
                DEFENSE_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        2.0
    )

    assert (
        contributions[0]
        .scoring_key
        == "yds_allow_200_299"
    )


def test_complete_defense_scoring() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "sack": 3,
                "int": 1,
                "ff": 1,
                "pts_allow": 10,
                "yds_allow": 280,
            },
            scoring_settings=(
                DEFENSE_SCORING
            ),
        )
    )

    # 3 sacks
    # +2 interception
    # +1 forced fumble
    # +2 points allowed
    # +2 yards allowed
    assert points == pytest.approx(
        10.0
    )


def test_kicker_distance_scoring() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "fgm": 3,
                "fgm_20_29": 1,
                "fgm_40_49": 1,
                "fgm_50_59": 1,
                "fgmiss": 1,
                "xpm": 2,
            },
            scoring_settings=(
                KICKER_SCORING
            ),
        )
    )

    # 3 + 4 + 5 - 1 + 2
    assert points == pytest.approx(
        13.0
    )


def test_zero_to_nineteen_field_goal_is_derived() -> None:
    points, contributions = (
        score_raw_stats(
            stats={
                "fgm": 2,
                "fgm_20_29": 1,
            },
            scoring_settings=(
                KICKER_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        6.0
    )

    short = [
        contribution
        for contribution
        in contributions
        if (
            contribution.scoring_key
            == "fgm_0_19"
        )
    ]

    assert len(
        short
    ) == 1

    assert (
        short[0].source
        == "derived"
    )


def test_direct_short_field_goal_is_not_double_counted() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "fgm": 2,
                "fgm_0_19": 1,
                "fgm_20_29": 1,
            },
            scoring_settings=(
                KICKER_SCORING
            ),
        )
    )

    assert points == pytest.approx(
        6.0
    )


def test_inconsistent_field_goal_buckets_are_rejected() -> None:
    with pytest.raises(
        FantasyScoringError,
        match=(
            "exceed total made"
        ),
    ):
        score_raw_stats(
            stats={
                "fgm": 1,
                "fgm_20_29": 1,
                "fgm_40_49": 1,
            },
            scoring_settings=(
                KICKER_SCORING
            ),
        )


def test_rare_fumble_recovery_touchdown_scores_when_present() -> None:
    points, _ = (
        score_raw_stats(
            stats={
                "fum_rec_td": 1,
            },
            scoring_settings={
                "fum_rec_td": 6,
            },
        )
    )

    assert points == pytest.approx(
        6.0
    )


def test_non_numeric_stat_is_rejected() -> None:
    with pytest.raises(
        FantasyScoringError,
        match="must be numeric",
    ):
        score_raw_stats(
            stats={
                "rec": "5",
            },
            scoring_settings=(
                OFFENSE_SCORING
            ),
        )


def test_non_numeric_scoring_setting_is_rejected() -> None:
    with pytest.raises(
        FantasyScoringError,
        match="must be numeric",
    ):
        normalize_scoring_settings(
            {
                "rec": "1",
            }
        )


def test_bool_scoring_setting_is_rejected() -> None:
    with pytest.raises(
        FantasyScoringError,
        match="must be numeric",
    ):
        normalize_scoring_settings(
            {
                "rec": True,
            }
        )