import json

import pytest

from src.donut_report import generate_donut_report_markdown
from src.donuts import (
    DonutConfig,
    DonutEntrant,
    DonutPoolError,
    DonutWeekScore,
    build_donut_agent_context,
    build_donut_pool_from_snapshots,
    build_entrants,
    calculate_donut_pool,
    extract_week_scores,
    load_donut_config,
    load_donut_overrides,
    load_season_week_scores,
    resolve_donut_week,
)
from src.storage import write_snapshot


def _config(
    tie_policy: str = "unresolved",
    total_weeks: int = 3,
    leagues: tuple[str, ...] = ("goats", "doats"),
) -> DonutConfig:
    return DonutConfig(
        enabled=True,
        leagues=leagues,
        total_weeks=total_weeks,
        delivery_offset_weeks=1,
        tie_policy=tie_policy,
    )


def _score(
    league_key: str,
    roster_id: int,
    points: float | None,
) -> DonutWeekScore:
    return DonutWeekScore(
        league_key=league_key,
        roster_id=roster_id,
        manager_name=f"{league_key}-{roster_id}",
        points=points,
    )


def _four_team_week(
    points: tuple[float | None, ...],
) -> list[DonutWeekScore]:
    return [
        _score("goats", 1, points[0]),
        _score("goats", 2, points[1]),
        _score("doats", 1, points[2]),
        _score("doats", 2, points[3]),
    ]


def _four_team_entrants() -> tuple[DonutEntrant, ...]:
    return build_entrants(
        _four_team_week((1.0, 2.0, 3.0, 4.0))
    )


# ---------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------


def test_team_key_is_league_scoped() -> None:
    goats = _score("goats", 1, 100.0)
    doats = _score("doats", 1, 100.0)

    assert goats.team_key == "goats:1"
    assert doats.team_key == "doats:1"
    assert goats.team_key != doats.team_key


def test_build_entrants_rejects_duplicates() -> None:
    with pytest.raises(DonutPoolError):
        build_entrants(
            [
                _score("goats", 1, 10.0),
                _score("goats", 1, 20.0),
            ]
        )


# ---------------------------------------------------------------------
# Weekly resolution
# ---------------------------------------------------------------------


def test_lowest_score_across_both_leagues_wins() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 95.5, 88.25, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(),
    )

    assert result.status == "assigned"
    assert len(result.assignments) == 1

    assignment = result.assignments[0]

    assert assignment.league_key == "doats"
    assert assignment.roster_id == 1
    assert assignment.points == pytest.approx(88.25)
    assert assignment.delivery_week == 2
    assert assignment.tie_broken is False
    assert assignment.margin_to_next_lowest == pytest.approx(7.25)


def test_assigned_manager_is_removed_from_eligibility() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 95.5, 88.25, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(),
    )

    assert "doats:1" in result.eligible_before
    assert "doats:1" not in result.eligible_after
    assert len(result.eligible_after) == 3


def test_ineligible_low_scorer_is_skipped() -> None:
    result = resolve_donut_week(
        scoring_week=2,
        scores=_four_team_week(
            (120.0, 95.5, 10.0, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:2",
        },
        config=_config(),
    )

    assignment = result.assignments[0]

    assert assignment.league_key == "goats"
    assert assignment.roster_id == 2
    assert assignment.points == pytest.approx(95.5)


def test_missing_score_never_becomes_zero() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 95.5, None, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(),
    )

    assignment = result.assignments[0]

    assert assignment.league_key == "goats"
    assert assignment.roster_id == 2
    assert "doats:1" in result.eligible_after
    assert any(
        "unresolved" in warning
        for warning in result.warnings
    )


def test_real_zero_score_can_win_the_donut() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 95.5, 0.0, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(),
    )

    assignment = result.assignments[0]

    assert assignment.league_key == "doats"
    assert assignment.points == pytest.approx(0.0)


def test_no_eligible_scores_assigns_nothing() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (None, None, None, None)
        ),
        eligible_keys={"goats:1"},
        config=_config(),
    )

    assert result.status == "no_eligible_scores"
    assert result.assignments == ()
    assert result.eligible_after == result.eligible_before


# ---------------------------------------------------------------------
# Ties
# ---------------------------------------------------------------------


def test_tie_is_unresolved_by_default() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 88.25, 88.25, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(),
    )

    assert result.status == "unresolved_tie"
    assert result.assignments == ()
    assert result.tied_team_keys == ("doats:1", "goats:2")
    assert result.eligible_after == result.eligible_before


def test_all_tied_policy_assigns_every_tied_team() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 88.25, 88.25, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(tie_policy="all_tied"),
    )

    assert result.status == "assigned"
    assert len(result.assignments) == 2
    assert all(
        assignment.tie_broken
        for assignment in result.assignments
    )
    assert len(result.eligible_after) == 2


def test_lowest_season_points_policy_breaks_tie() -> None:
    weekly_scores = {
        1: _four_team_week((100.0, 50.0, 90.0, 110.0)),
        2: _four_team_week((120.0, 88.25, 88.25, 101.0)),
    }

    result = resolve_donut_week(
        scoring_week=2,
        scores=weekly_scores[2],
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(
            tie_policy="lowest_season_points"
        ),
        weekly_scores=weekly_scores,
    )

    assignment = result.assignments[0]

    assert assignment.league_key == "goats"
    assert assignment.roster_id == 2
    assert assignment.tie_broken is True
    assert (
        assignment.resolution
        == "tie_policy_lowest_season_points"
    )


def test_commissioner_override_resolves_tie() -> None:
    result = resolve_donut_week(
        scoring_week=1,
        scores=_four_team_week(
            (120.0, 88.25, 88.25, 101.0)
        ),
        eligible_keys={
            "goats:1",
            "goats:2",
            "doats:1",
            "doats:2",
        },
        config=_config(),
        override={
            "league_key": "doats",
            "roster_id": 1,
            "reason": "Coin flip at the Tuesday league meeting.",
        },
    )

    assignment = result.assignments[0]

    assert assignment.league_key == "doats"
    assert assignment.resolution == "commissioner_override"
    assert assignment.reason.startswith("Coin flip")


def test_override_must_name_a_tied_team() -> None:
    with pytest.raises(DonutPoolError):
        resolve_donut_week(
            scoring_week=1,
            scores=_four_team_week(
                (120.0, 88.25, 88.25, 101.0)
            ),
            eligible_keys={
                "goats:1",
                "goats:2",
                "doats:1",
                "doats:2",
            },
            config=_config(),
            override={
                "league_key": "goats",
                "roster_id": 1,
                "reason": "Not actually tied.",
            },
        )


# ---------------------------------------------------------------------
# Season walk
# ---------------------------------------------------------------------


def test_no_repeat_assignments_across_season() -> None:
    weekly_scores = {
        1: _four_team_week((10.0, 20.0, 30.0, 40.0)),
        2: _four_team_week((11.0, 21.0, 31.0, 41.0)),
        3: _four_team_week((12.0, 22.0, 32.0, 42.0)),
    }

    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores=weekly_scores,
        config=_config(),
    )

    assigned = [
        (
            assignment.league_key,
            assignment.roster_id,
        )
        for assignment in state.eliminated
    ]

    assert assigned == [
        ("goats", 1),
        ("goats", 2),
        ("doats", 1),
    ]

    assert len(set(assigned)) == len(assigned)


def test_single_survivor_is_undoughfeated() -> None:
    weekly_scores = {
        1: _four_team_week((10.0, 20.0, 30.0, 40.0)),
        2: _four_team_week((11.0, 21.0, 31.0, 41.0)),
        3: _four_team_week((12.0, 22.0, 32.0, 42.0)),
    }

    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores=weekly_scores,
        config=_config(),
    )

    assert state.complete is True
    assert len(state.survivors) == 1
    assert state.undoughfeated is not None
    assert state.undoughfeated.league_key == "doats"
    assert state.undoughfeated.roster_id == 2
    assert state.undoughfeated.weeks_survived == 3


def test_entrant_count_mismatch_warns() -> None:
    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores={
            1: _four_team_week((10.0, 20.0, 30.0, 40.0)),
        },
        config=_config(total_weeks=10),
    )

    assert any(
        "unDOUGHfeated survivor requires" in warning
        for warning in state.warnings
    )


def test_unresolved_tie_blocks_later_weeks() -> None:
    weekly_scores = {
        1: _four_team_week((10.0, 10.0, 30.0, 40.0)),
        2: _four_team_week((11.0, 21.0, 31.0, 41.0)),
    }

    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores=weekly_scores,
        config=_config(),
    )

    assert state.blocked_week == 1
    assert state.eliminated == ()
    assert state.complete is False
    assert state.results[1].status == "blocked"


def test_unknown_team_is_rejected() -> None:
    with pytest.raises(DonutPoolError):
        calculate_donut_pool(
            season="2026",
            entrants=_four_team_entrants(),
            weekly_scores={
                1: _four_team_week(
                    (10.0, 20.0, 30.0, 40.0)
                )
                + [_score("goats", 99, 5.0)],
            },
            config=_config(),
        )


def test_survivor_closest_call_is_tracked() -> None:
    weekly_scores = {
        1: _four_team_week((10.0, 20.0, 30.0, 40.0)),
        2: _four_team_week((99.0, 21.0, 22.0, 41.0)),
    }

    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores=weekly_scores,
        config=_config(),
    )

    survivors = {
        (
            f"{survivor.league_key}:"
            f"{survivor.roster_id}"
        ): survivor
        for survivor in state.survivors
    }

    doats_one = survivors["doats:1"]

    assert doats_one.closest_call_margin == pytest.approx(1.0)
    assert doats_one.closest_call_week == 2
    assert doats_one.lowest_weekly_points == pytest.approx(22.0)


# ---------------------------------------------------------------------
# Config and overrides
# ---------------------------------------------------------------------


def test_load_donut_config_reads_settings() -> None:
    config = load_donut_config(
        {
            "leagues": {
                "goats": {},
                "doats": {},
            },
            "analytics": {
                "donut_pool": {
                    "enabled": True,
                    "leagues": ["goats", "doats"],
                    "total_weeks": 17,
                    "delivery_offset_weeks": 1,
                    "tie_policy": "unresolved",
                }
            },
        }
    )

    assert config.leagues == ("goats", "doats")
    assert config.total_weeks == 17
    assert config.tie_policy == "unresolved"


def test_load_donut_config_rejects_unknown_league() -> None:
    with pytest.raises(DonutPoolError):
        load_donut_config(
            {
                "leagues": {"goats": {}},
                "analytics": {
                    "donut_pool": {
                        "leagues": ["goats", "ghosts"],
                        "total_weeks": 17,
                    }
                },
            }
        )


def test_load_donut_config_rejects_bad_tie_policy() -> None:
    with pytest.raises(DonutPoolError):
        load_donut_config(
            {
                "analytics": {
                    "donut_pool": {
                        "leagues": ["goats"],
                        "total_weeks": 17,
                        "tie_policy": "coin_flip",
                    }
                }
            }
        )


def test_override_requires_written_reason(tmp_path) -> None:
    path = tmp_path / "donut_overrides.json"

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "weeks": {
                    "3": {
                        "league_key": "goats",
                        "roster_id": 4,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DonutPoolError):
        load_donut_overrides(path)


def test_missing_override_file_is_empty(tmp_path) -> None:
    assert (
        load_donut_overrides(
            tmp_path / "absent.json"
        )
        == {}
    )


# ---------------------------------------------------------------------
# Snapshot integration
# ---------------------------------------------------------------------


def _write_final_snapshot(
    data_root,
    season: str,
    league_key: str,
    week: int,
    teams: list[tuple[int, str, float | None]],
) -> None:
    write_snapshot(
        data_root=data_root,
        season=season,
        week=week,
        league_key=league_key,
        league_id=f"id-{league_key}",
        stage="final",
        data={
            "final_format_version": 1,
            "teams": [
                {
                    "roster_id": roster_id,
                    "manager_name": manager_name,
                    "final_points": points,
                    "custom_points": None,
                    "effective_final_points": points,
                }
                for roster_id, manager_name, points in teams
            ],
        },
    )


def test_extract_week_scores_requires_final_stage() -> None:
    with pytest.raises(DonutPoolError):
        extract_week_scores(
            {
                "league_key": "goats",
                "stage": "baseline",
                "data": {"teams": []},
            }
        )


def test_build_pool_from_snapshots(tmp_path) -> None:
    data_root = tmp_path / "data"

    _write_final_snapshot(
        data_root,
        "2026",
        "goats",
        1,
        [
            (1, "Tim", 120.0),
            (2, "Nate", 60.0),
        ],
    )

    _write_final_snapshot(
        data_root,
        "2026",
        "doats",
        1,
        [
            (1, "Kate", 110.0),
            (2, "Gordo", 99.0),
        ],
    )

    state = build_donut_pool_from_snapshots(
        data_root=data_root,
        season="2026",
        config=_config(total_weeks=3),
        through_week=3,
    )

    assert len(state.entrants) == 4
    assert state.next_delivery is not None
    assert state.next_delivery.manager_name == "Nate"
    assert state.next_delivery.delivery_week == 2
    assert state.complete is False


def test_season_loader_stops_at_first_gap(tmp_path) -> None:
    data_root = tmp_path / "data"

    for week in (1, 3):
        _write_final_snapshot(
            data_root,
            "2026",
            "goats",
            week,
            [(1, "Tim", 120.0)],
        )

        _write_final_snapshot(
            data_root,
            "2026",
            "doats",
            week,
            [(1, "Kate", 60.0)],
        )

    weekly_scores, warnings = load_season_week_scores(
        data_root=data_root,
        season="2026",
        league_keys=("goats", "doats"),
        through_week=3,
    )

    assert sorted(weekly_scores) == [1]
    assert any(
        "stopped before week 2" in warning
        for warning in warnings
    )


def test_partial_week_is_flagged(tmp_path) -> None:
    data_root = tmp_path / "data"

    _write_final_snapshot(
        data_root,
        "2026",
        "goats",
        1,
        [(1, "Tim", 120.0)],
    )

    weekly_scores, warnings = load_season_week_scores(
        data_root=data_root,
        season="2026",
        league_keys=("goats", "doats"),
        through_week=1,
    )

    assert weekly_scores == {}
    assert any(
        "partially available" in warning
        for warning in warnings
    )


# ---------------------------------------------------------------------
# Derived artifacts
# ---------------------------------------------------------------------


def test_agent_context_is_json_serializable() -> None:
    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores={
            1: _four_team_week((10.0, 20.0, 30.0, 40.0)),
        },
        config=_config(),
    )

    context = build_donut_agent_context(state)

    encoded = json.dumps(context)

    assert "undoughfeated" in encoded
    assert context["next_delivery"]["delivery_week"] == 2
    assert context["survivor_count"] == 3


def test_report_renders_ledger_and_survivors() -> None:
    state = calculate_donut_pool(
        season="2026",
        entrants=_four_team_entrants(),
        weekly_scores={
            1: _four_team_week((10.0, 20.0, 30.0, 40.0)),
        },
        config=_config(),
    )

    markdown = generate_donut_report_markdown(state)

    assert "Donut Survival Pool — 2026" in markdown
    assert "On the Hook" in markdown
    assert "Donut Ledger" in markdown
    assert "Still Alive" in markdown
    assert "goats-1" in markdown
