"""Generic weekly fantasy-football orchestration.

This module coordinates the major weekly stages:

- baseline
- Sunday / pre-MNF checkpoint
- final
- AI-agent context generation

Immutable stage snapshots are the historical source of truth.

AI-agent context files are derived artifacts and may be regenerated from
those immutable snapshots.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.agent_context import (
    AgentContextError,
    write_agent_context_file,
)
from src.baseline import (
    build_baseline_snapshot_data,
)
from src.comparison import (
    compare_baseline_to_sunday,
)
from src.final import (
    build_final_snapshot_data,
)
from src.players import (
    get_player_map,
)
from src.projections import (
    SleeperProjectionProvider,
    build_projection_lookup,
)
from src.schedule import (
    StageWindow,
    WeeklySchedule,
    resolve_due_stage,
    stage_window,
)
from src.sleeper import (
    SleeperClient,
)
from src.storage import (
    build_snapshot_path,
    read_snapshot,
    write_snapshot,
)
from src.sunday import (
    build_sunday_snapshot_data,
)
from src.team_projections import (
    load_week_projection_overrides,
)


DATA_ROOT = Path("data")


class OrchestrationError(RuntimeError):
    """Raised when a weekly stage cannot run safely."""


def load_project_config(
    path: Path = Path("config.json"),
) -> dict[str, Any]:
    """Load and minimally validate the project configuration."""

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(file)

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise OrchestrationError(
            f"Could not read project config: {path}"
        ) from exc

    if not isinstance(
        config,
        dict,
    ):
        raise OrchestrationError(
            "Project config must be a JSON object"
        )

    season = config.get(
        "season"
    )

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise OrchestrationError(
            "Project config is missing season"
        )

    leagues = config.get(
        "leagues"
    )

    if not isinstance(
        leagues,
        dict,
    ):
        raise OrchestrationError(
            "Project config is missing leagues"
        )

    if not leagues:
        raise OrchestrationError(
            "Project config contains no leagues"
        )

    return config


def snapshot_paths(
    config: dict[str, Any],
    season: str,
    week: int,
    stage: str,
    data_root: Path = DATA_ROOT,
) -> dict[str, Path]:
    """Return official snapshot paths for every configured league."""

    leagues = config.get(
        "leagues"
    )

    if not isinstance(
        leagues,
        dict,
    ):
        raise OrchestrationError(
            "Project config is missing leagues"
        )

    return {
        league_key: build_snapshot_path(
            data_root=data_root,
            season=season,
            league_key=league_key,
            week=week,
            stage=stage,
        )
        for league_key
        in leagues
    }


def snapshot_pair_state(
    paths: dict[str, Path],
    label: str,
) -> str:
    """Return absent/complete while rejecting dangerous partial state."""

    existence = {
        league_key: path.exists()
        for league_key, path
        in paths.items()
    }

    if all(
        existence.values()
    ):
        return "complete"

    if not any(
        existence.values()
    ):
        return "absent"

    details = ", ".join(
        (
            f"{league_key}="
            f"{'exists' if exists else 'missing'}"
        )
        for league_key, exists
        in existence.items()
    )

    raise OrchestrationError(
        f"Partial {label} snapshot state detected. "
        f"{details}"
    )


def _validate_project_season(
    config: dict[str, Any],
    schedule: WeeklySchedule,
) -> str:
    """Require project and automation schedule seasons to match."""

    season = config.get(
        "season"
    )

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise OrchestrationError(
            "Project config is missing season"
        )

    if season != schedule.season:
        raise OrchestrationError(
            "Project season and automation "
            "schedule season do not match: "
            f"{season!r} != {schedule.season!r}"
        )

    return season


def _require_execution_window(
    schedule: WeeklySchedule,
    stage: str,
    week: int,
) -> StageWindow:
    """Require the current time to be inside a stage write window."""

    window = stage_window(
        schedule=schedule,
        stage=stage,
        week=week,
    )

    now = datetime.now(
        schedule.timezone
    )

    if not window.contains(
        now
    ):
        raise OrchestrationError(
            f"{stage} Week {week} may only "
            "write during its configured window: "
            f"{window.opens_at.isoformat()} "
            f"through {window.closes_at.isoformat()}"
        )

    return window


def _capture_context(
    schedule: WeeklySchedule,
    window: StageWindow,
    stage_label: str,
) -> dict[str, Any]:
    """Build common metadata describing an automated capture."""

    now = datetime.now(
        schedule.timezone
    )

    return {
        "mode": (
            "generic_weekly_orchestration"
        ),
        "stage_label": (
            stage_label
        ),
        "timezone": (
            schedule.timezone_name
        ),
        "captured_at_local": (
            now.isoformat()
        ),
        "captured_at_utc": (
            now
            .astimezone(
                ZoneInfo("UTC")
            )
            .isoformat()
        ),
        "scheduled_window_open": (
            window.opens_at.isoformat()
        ),
        "scheduled_window_close": (
            window.closes_at.isoformat()
        ),
    }


def _fresh_week_inputs(
    season: str,
    week: int,
) -> tuple[
    SleeperClient,
    dict[str, dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    """Fetch common live inputs once for baseline or Sunday stages."""

    sleeper = SleeperClient()

    print(
        "Refreshing NFL player metadata..."
    )

    players = get_player_map(
        sleeper,
        refresh=True,
    )

    print(
        f"Fetching Week {week} projections..."
    )

    projection_records = (
        SleeperProjectionProvider()
        .get_week_projections(
            season=season,
            week=week,
        )
    )

    projection_lookup = (
        build_projection_lookup(
            projection_records
        )
    )

    overrides_path = Path(
        f"data/{season}/"
        "projection_overrides.json"
    )

    overrides = (
        load_week_projection_overrides(
            overrides_path,
            week=week,
        )
    )

    return (
        sleeper,
        players,
        projection_lookup,
        overrides,
    )


def _write_agent_context(
    config: dict[str, Any],
    season: str,
    week: int,
    stage: str,
) -> Path:
    """Build or rebuild AI-agent context from stored snapshots."""

    try:
        path = (
            write_agent_context_file(
                data_root=DATA_ROOT,
                project_config=config,
                season=season,
                week=week,
                stage=stage,
            )
        )

    except AgentContextError as exc:
        raise OrchestrationError(
            f"Could not build "
            f"{stage} agent context: "
            f"{exc}"
        ) from exc

    print(
        f"AGENT CONTEXT: {path}"
    )

    return path


def _validate_expected_team_count(
    league_name: str,
    league: dict[str, Any],
    snapshot_data: dict[str, Any],
) -> None:
    """Verify built team count against Sleeper when available."""

    expected = league.get(
        "total_rosters"
    )

    teams = snapshot_data.get(
        "teams"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise OrchestrationError(
            f"{league_name} snapshot "
            "is missing teams"
        )

    if (
        isinstance(
            expected,
            int,
        )
        and len(teams)
        != expected
    ):
        raise OrchestrationError(
            f"{league_name} team count "
            "does not match Sleeper: "
            f"{len(teams)} != {expected}"
        )


def run_baseline(
    week: int,
    schedule: WeeklySchedule,
    check_only: bool = False,
) -> int:
    """Build or write one week's immutable baseline snapshots."""

    config = (
        load_project_config()
    )

    season = (
        _validate_project_season(
            config,
            schedule,
        )
    )

    paths = snapshot_paths(
        config=config,
        season=season,
        week=week,
        stage="baseline",
    )

    state = snapshot_pair_state(
        paths,
        "baseline",
    )

    print("=" * 72)
    print(
        f"{season} WEEK {week} BASELINE"
    )
    print("=" * 72)

    print(
        f"Snapshot state: {state}"
    )

    if state == "complete":
        print(
            "Both immutable baseline "
            "snapshots already exist."
        )

        if not check_only:
            _write_agent_context(
                config=config,
                season=season,
                week=week,
                stage="baseline",
            )

        return 0

    window = stage_window(
        schedule=schedule,
        stage="baseline",
        week=week,
    )

    if not check_only:
        window = (
            _require_execution_window(
                schedule=schedule,
                stage="baseline",
                week=week,
            )
        )

    (
        sleeper,
        players,
        projection_lookup,
        overrides,
    ) = _fresh_week_inputs(
        season=season,
        week=week,
    )

    capture_context = (
        _capture_context(
            schedule=schedule,
            window=window,
            stage_label="baseline",
        )
    )

    leagues = config[
        "leagues"
    ]

    prepared: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, league_config in (
        leagues.items()
    ):
        if not isinstance(
            league_config,
            dict,
        ):
            raise OrchestrationError(
                f"League config for "
                f"{league_key} must be "
                "an object"
            )

        league_id = (
            league_config.get(
                "league_id"
            )
        )

        league_name = (
            league_config.get(
                "name",
                league_key,
            )
        )

        if not isinstance(
            league_id,
            str,
        ):
            raise OrchestrationError(
                f"{league_name} is missing "
                "a valid league_id"
            )

        print()
        print(
            f"Preparing {league_name}..."
        )

        league = sleeper.get_league(
            league_id
        )

        users = sleeper.get_users(
            league_id
        )

        rosters = sleeper.get_rosters(
            league_id
        )

        matchups = sleeper.get_matchups(
            league_id,
            week=week,
        )

        baseline = (
            build_baseline_snapshot_data(
                league_key=league_key,
                league_id=league_id,
                week=week,
                league=league,
                users=users,
                rosters=rosters,
                matchup_records=(
                    matchups
                ),
                players=players,
                projection_lookup=(
                    projection_lookup
                ),
                overrides=overrides,
                capture_context=(
                    capture_context
                ),
            )
        )

        _validate_expected_team_count(
            league_name=league_name,
            league=league,
            snapshot_data=baseline,
        )

        incomplete = [
            team
            for team
            in baseline["teams"]
            if not team[
                "projection_complete"
            ]
        ]

        if incomplete:
            print()
            print(
                f"{league_name} has incomplete "
                "baseline projections:"
            )

            for team in incomplete:
                print(
                    f"  roster="
                    f"{team['roster_id']} "
                    f"manager="
                    f"{team['manager_name']}"
                )

                for warning in team.get(
                    "warnings",
                    [],
                ):
                    print(
                        f"    WARNING: "
                        f"{warning}"
                    )

            raise OrchestrationError(
                f"{league_name} contains "
                "incomplete baseline projections"
            )

        prepared[
            league_key
        ] = {
            "league_id": (
                league_id
            ),
            "league_name": (
                league_name
            ),
            "data": (
                baseline
            ),
        }

    print()
    print("=" * 72)
    print("BASELINE SUMMARY")
    print("=" * 72)

    for item in prepared.values():
        data = item[
            "data"
        ]

        print(
            f"{item['league_name']}: "
            f"{len(data['teams'])} teams, "
            f"{len(data['matchups'])} matchups, "
            f"{len(data['warnings'])} warnings"
        )

    if check_only:
        print()
        print(
            "CHECK ONLY COMPLETE — "
            "nothing was written."
        )

        return 0

    # Recheck immediately before immutable writes.
    _require_execution_window(
        schedule=schedule,
        stage="baseline",
        week=week,
    )

    print()
    print("=" * 72)
    print("WRITING BASELINE SNAPSHOTS")
    print("=" * 72)

    for league_key, item in (
        prepared.items()
    ):
        path = write_snapshot(
            data_root=DATA_ROOT,
            season=season,
            week=week,
            league_key=league_key,
            league_id=(
                item["league_id"]
            ),
            stage="baseline",
            data=item["data"],
        )

        stored = read_snapshot(
            path
        )

        if stored.get(
            "stage"
        ) != "baseline":
            raise OrchestrationError(
                f"Stored baseline failed "
                f"read-back validation: {path}"
            )

        print(
            f"CREATED: {path}"
        )

    _write_agent_context(
        config=config,
        season=season,
        week=week,
        stage="baseline",
    )

    print()
    print(
        "BASELINE + AGENT CONTEXT COMPLETE"
    )

    return 0


def run_sunday(
    week: int,
    schedule: WeeklySchedule,
    check_only: bool = False,
) -> int:
    """Build or write one week's Monday-noon Sunday checkpoint."""

    config = (
        load_project_config()
    )

    season = (
        _validate_project_season(
            config,
            schedule,
        )
    )

    baseline_paths = (
        snapshot_paths(
            config=config,
            season=season,
            week=week,
            stage="baseline",
        )
    )

    sunday_paths = (
        snapshot_paths(
            config=config,
            season=season,
            week=week,
            stage="sunday",
        )
    )

    baseline_state = (
        snapshot_pair_state(
            baseline_paths,
            "baseline",
        )
    )

    sunday_state = (
        snapshot_pair_state(
            sunday_paths,
            "Sunday",
        )
    )

    print("=" * 72)
    print(
        f"{season} WEEK {week} "
        "SUNDAY / PRE-MNF CHECKPOINT"
    )
    print("=" * 72)

    print(
        f"Baseline state: {baseline_state}"
    )

    print(
        f"Sunday state:   {sunday_state}"
    )

    if sunday_state == "complete":
        print(
            "Both immutable Sunday "
            "snapshots already exist."
        )

        if not check_only:
            _write_agent_context(
                config=config,
                season=season,
                week=week,
                stage="sunday",
            )

        return 0

    if baseline_state != "complete":
        if check_only:
            print()
            print(
                "CHECK ONLY: baseline snapshots "
                "do not exist yet."
            )

            return 0

        raise OrchestrationError(
            "Sunday stage requires both "
            "immutable baseline snapshots"
        )

    window = stage_window(
        schedule=schedule,
        stage="sunday",
        week=week,
    )

    if not check_only:
        window = (
            _require_execution_window(
                schedule=schedule,
                stage="sunday",
                week=week,
            )
        )

    baselines = {
        league_key: read_snapshot(
            path
        )
        for league_key, path
        in baseline_paths.items()
    }

    (
        sleeper,
        players,
        projection_lookup,
        overrides,
    ) = _fresh_week_inputs(
        season=season,
        week=week,
    )

    capture_context = (
        _capture_context(
            schedule=schedule,
            window=window,
            stage_label=(
                "sunday_pre_mnf"
            ),
        )
    )

    leagues = config[
        "leagues"
    ]

    prepared: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, league_config in (
        leagues.items()
    ):
        if not isinstance(
            league_config,
            dict,
        ):
            raise OrchestrationError(
                f"League config for "
                f"{league_key} must be "
                "an object"
            )

        league_id = (
            league_config.get(
                "league_id"
            )
        )

        league_name = (
            league_config.get(
                "name",
                league_key,
            )
        )

        if not isinstance(
            league_id,
            str,
        ):
            raise OrchestrationError(
                f"{league_name} is missing "
                "a valid league_id"
            )

        print()
        print(
            f"Preparing {league_name}..."
        )

        league = sleeper.get_league(
            league_id
        )

        users = sleeper.get_users(
            league_id
        )

        rosters = sleeper.get_rosters(
            league_id
        )

        matchups = sleeper.get_matchups(
            league_id,
            week=week,
        )

        sunday = (
            build_sunday_snapshot_data(
                season=season,
                league_key=league_key,
                league_id=league_id,
                week=week,
                baseline_snapshot=(
                    baselines[
                        league_key
                    ]
                ),
                league=league,
                users=users,
                rosters=rosters,
                matchup_records=(
                    matchups
                ),
                players=players,
                projection_lookup=(
                    projection_lookup
                ),
                overrides=overrides,
                capture_context=(
                    capture_context
                ),
            )
        )

        _validate_expected_team_count(
            league_name=league_name,
            league=league,
            snapshot_data=sunday,
        )

        prepared[
            league_key
        ] = {
            "league_id": (
                league_id
            ),
            "league_name": (
                league_name
            ),
            "data": (
                sunday
            ),
        }

    print()
    print("=" * 72)
    print("SUNDAY CHECKPOINT SUMMARY")
    print("=" * 72)

    for item in prepared.values():
        data = item[
            "data"
        ]

        incomplete = [
            team
            for team
            in data["teams"]
            if not team[
                "projection_complete"
            ]
        ]

        known_scores = [
            team
            for team
            in data["teams"]
            if team[
                "effective_live_points"
            ]
            is not None
        ]

        print(
            f"{item['league_name']}: "
            f"{len(data['teams'])} teams, "
            f"{len(data['matchups'])} matchups, "
            f"{len(known_scores)} live scores, "
            f"{len(incomplete)} incomplete projections, "
            f"{len(data['warnings'])} warnings"
        )

    if check_only:
        print()
        print(
            "CHECK ONLY COMPLETE — "
            "nothing was written."
        )

        return 0

    # Sunday may legitimately contain incomplete projection values.
    _require_execution_window(
        schedule=schedule,
        stage="sunday",
        week=week,
    )

    print()
    print("=" * 72)
    print("WRITING SUNDAY SNAPSHOTS")
    print("=" * 72)

    stored: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, item in (
        prepared.items()
    ):
        path = write_snapshot(
            data_root=DATA_ROOT,
            season=season,
            week=week,
            league_key=league_key,
            league_id=(
                item["league_id"]
            ),
            stage="sunday",
            data=item["data"],
        )

        snapshot = read_snapshot(
            path
        )

        if snapshot.get(
            "stage"
        ) != "sunday":
            raise OrchestrationError(
                f"Stored Sunday snapshot "
                f"failed read-back validation: "
                f"{path}"
            )

        stored[
            league_key
        ] = snapshot

        print(
            f"CREATED: {path}"
        )

    print()
    print("=" * 72)
    print("BASELINE-TO-SUNDAY CHANGES")
    print("=" * 72)

    for league_key, league_config in (
        leagues.items()
    ):
        comparison = (
            compare_baseline_to_sunday(
                baselines[
                    league_key
                ],
                stored[
                    league_key
                ],
            )
        )

        lineup_changed = [
            team
            for team
            in comparison.teams
            if (
                team.added_starters
                or team.removed_starters
                or team.slot_changes
            )
        ]

        team_projection_changed = [
            team
            for team
            in comparison.teams
            if (
                team.team_projection_delta
                is not None
                and abs(
                    team.team_projection_delta
                )
                >= 1e-9
            )
        ]

        player_projection_changed = [
            team
            for team
            in comparison.teams
            if team.projection_changes
        ]

        print(
            f"{league_config.get('name', league_key)}:"
        )

        print(
            f"  lineup changes: "
            f"{len(lineup_changed)} teams"
        )

        print(
            f"  team projection changes: "
            f"{len(team_projection_changed)} teams"
        )

        print(
            f"  player projection changes: "
            f"{len(player_projection_changed)} teams"
        )

    _write_agent_context(
        config=config,
        season=season,
        week=week,
        stage="sunday",
    )

    print()
    print(
        "SUNDAY SNAPSHOT + AGENT "
        "CONTEXT COMPLETE"
    )

    return 0


def run_context(
    stage: str,
    week: int,
    schedule: WeeklySchedule,
) -> int:
    """Regenerate AI context from immutable stored snapshots."""

    config = (
        load_project_config()
    )

    season = (
        _validate_project_season(
            config,
            schedule,
        )
    )

    print("=" * 72)
    print(
        f"{season} WEEK {week} "
        f"{stage.upper()} AGENT CONTEXT"
    )
    print("=" * 72)

    _write_agent_context(
        config=config,
        season=season,
        week=week,
        stage=stage,
    )

    print()
    print(
        "AGENT CONTEXT COMPLETE"
    )

    return 0


def run_final(
    week: int,
    schedule: WeeklySchedule,
    check_only: bool = False,
) -> int:
    """Build or write one week's immutable final snapshots."""

    config = (
        load_project_config()
    )

    season = (
        _validate_project_season(
            config,
            schedule,
        )
    )

    baseline_paths = (
        snapshot_paths(
            config=config,
            season=season,
            week=week,
            stage="baseline",
        )
    )

    sunday_paths = (
        snapshot_paths(
            config=config,
            season=season,
            week=week,
            stage="sunday",
        )
    )

    final_paths = (
        snapshot_paths(
            config=config,
            season=season,
            week=week,
            stage="final",
        )
    )

    baseline_state = (
        snapshot_pair_state(
            baseline_paths,
            "baseline",
        )
    )

    sunday_state = (
        snapshot_pair_state(
            sunday_paths,
            "Sunday",
        )
    )

    final_state = (
        snapshot_pair_state(
            final_paths,
            "final",
        )
    )

    print("=" * 72)
    print(
        f"{season} WEEK {week} FINAL"
    )
    print("=" * 72)

    print(
        f"Baseline state: {baseline_state}"
    )

    print(
        f"Sunday state:   {sunday_state}"
    )

    print(
        f"Final state:    {final_state}"
    )

    if final_state == "complete":
        print()
        print(
            "Both immutable final "
            "snapshots already exist."
        )

        return 0

    if baseline_state != "complete":
        if check_only:
            print()
            print(
                "CHECK ONLY: baseline snapshots "
                "do not exist yet."
            )

            return 0

        raise OrchestrationError(
            "Final stage requires both "
            "immutable baseline snapshots"
        )

    if sunday_state == "absent":
        print()
        print(
            "WARNING: Sunday snapshots "
            "are absent. Final capture "
            "may still proceed because "
            "final historical truth should "
            "not be lost."
        )

    window = stage_window(
        schedule=schedule,
        stage="final",
        week=week,
    )

    if not check_only:
        window = (
            _require_execution_window(
                schedule=schedule,
                stage="final",
                week=week,
            )
        )

    baselines = {
        league_key: read_snapshot(
            path
        )
        for league_key, path
        in baseline_paths.items()
    }

    sleeper = SleeperClient()

    print()
    print(
        "Refreshing NFL player metadata..."
    )

    players = get_player_map(
        sleeper,
        refresh=True,
    )

    capture_context = (
        _capture_context(
            schedule=schedule,
            window=window,
            stage_label=(
                "final_post_mnf"
            ),
        )
    )

    leagues = config[
        "leagues"
    ]

    prepared: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, league_config in (
        leagues.items()
    ):
        if not isinstance(
            league_config,
            dict,
        ):
            raise OrchestrationError(
                f"League config for "
                f"{league_key} must be "
                "an object"
            )

        league_id = (
            league_config.get(
                "league_id"
            )
        )

        league_name = (
            league_config.get(
                "name",
                league_key,
            )
        )

        if not isinstance(
            league_id,
            str,
        ):
            raise OrchestrationError(
                f"{league_name} is missing "
                "a valid league_id"
            )

        print()
        print(
            f"Preparing {league_name}..."
        )

        league = sleeper.get_league(
            league_id
        )

        users = sleeper.get_users(
            league_id
        )

        rosters = sleeper.get_rosters(
            league_id
        )

        matchups = sleeper.get_matchups(
            league_id,
            week=week,
        )

        final = (
            build_final_snapshot_data(
                season=season,
                league_key=league_key,
                league_id=league_id,
                week=week,
                baseline_snapshot=(
                    baselines[
                        league_key
                    ]
                ),
                league=league,
                users=users,
                rosters=rosters,
                matchup_records=(
                    matchups
                ),
                players=players,
                capture_context=(
                    capture_context
                ),
            )
        )

        _validate_expected_team_count(
            league_name=league_name,
            league=league,
            snapshot_data=final,
        )

        incomplete_scores = [
            team
            for team
            in final["teams"]
            if team[
                "effective_final_points"
            ]
            is None
        ]

        if incomplete_scores:
            print()
            print(
                f"{league_name} has "
                "incomplete final scores:"
            )

            for team in incomplete_scores:
                print(
                    f"  roster="
                    f"{team['roster_id']} "
                    f"manager="
                    f"{team['manager_name']}"
                )

            raise OrchestrationError(
                f"{league_name} contains "
                "incomplete final scores"
            )

        incomplete_matchups = [
            matchup
            for matchup
            in final["matchups"]
            if not matchup[
                "score_complete"
            ]
        ]

        if incomplete_matchups:
            raise OrchestrationError(
                f"{league_name} contains "
                "incomplete final matchups"
            )

        prepared[
            league_key
        ] = {
            "league_id": (
                league_id
            ),
            "league_name": (
                league_name
            ),
            "data": (
                final
            ),
        }

    print()
    print("=" * 72)
    print("FINAL SNAPSHOT SUMMARY")
    print("=" * 72)

    for item in prepared.values():
        data = item[
            "data"
        ]

        completed_matchups = [
            matchup
            for matchup
            in data["matchups"]
            if matchup[
                "score_complete"
            ]
        ]

        print(
            f"{item['league_name']}: "
            f"{len(data['teams'])} teams, "
            f"{len(completed_matchups)} "
            "completed matchups, "
            f"{len(data['warnings'])} warnings"
        )

    if check_only:
        print()
        print(
            "CHECK ONLY COMPLETE — "
            "nothing was written."
        )

        return 0

    # Recheck immediately before immutable final writes.
    _require_execution_window(
        schedule=schedule,
        stage="final",
        week=week,
    )

    print()
    print("=" * 72)
    print("WRITING FINAL SNAPSHOTS")
    print("=" * 72)

    for league_key, item in (
        prepared.items()
    ):
        path = write_snapshot(
            data_root=DATA_ROOT,
            season=season,
            week=week,
            league_key=league_key,
            league_id=(
                item["league_id"]
            ),
            stage="final",
            data=item["data"],
        )

        stored = read_snapshot(
            path
        )

        if stored.get(
            "stage"
        ) != "final":
            raise OrchestrationError(
                f"Stored final snapshot "
                f"failed read-back validation: "
                f"{path}"
            )

        print(
            f"CREATED: {path}"
        )

    print()
    print(
        "FINAL SNAPSHOT COMPLETE"
    )

    return 0


def run_auto(
    schedule: WeeklySchedule,
    check_only: bool = False,
    minimum_week: int | None = None,
) -> int:
    """Run whichever generic weekly stage is due now."""

    now = datetime.now(
        schedule.timezone
    )

    due = resolve_due_stage(
        schedule=schedule,
        moment=now,
        minimum_week=minimum_week,
    )

    print("=" * 72)
    print("AUTOMATIC FANTASY ORCHESTRATION")
    print("=" * 72)

    print(
        f"Current time: "
        f"{now.isoformat()}"
    )

    if due is None:
        print()
        print(
            "No fantasy automation stage "
            "is due right now."
        )

        return 0

    print()
    print(
        f"Resolved stage: "
        f"{due.stage}"
    )

    print(
        f"Resolved week:  "
        f"{due.week}"
    )

    print(
        f"Window opens:   "
        f"{due.window.opens_at.isoformat()}"
    )

    print(
        f"Window closes:  "
        f"{due.window.closes_at.isoformat()}"
    )

    print()

    if due.stage == "baseline":
        return run_baseline(
            week=due.week,
            schedule=schedule,
            check_only=check_only,
        )

    if due.stage == "sunday":
        return run_sunday(
            week=due.week,
            schedule=schedule,
            check_only=check_only,
        )

    if due.stage == "final":
        return run_final(
            week=due.week,
            schedule=schedule,
            check_only=check_only,
        )

    raise OrchestrationError(
        f"Unsupported automation stage: "
        f"{due.stage}"
    )