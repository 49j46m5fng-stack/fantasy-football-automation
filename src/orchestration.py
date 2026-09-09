"""Generic weekly fantasy-football stage orchestration."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.baseline import (
    build_baseline_snapshot_data,
)
from src.comparison import (
    compare_baseline_to_sunday,
)
from src.players import (
    get_player_map,
)
from src.projections import (
    SleeperProjectionProvider,
    build_projection_lookup,
)
from src.reports import (
    write_preview_report,
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


DATA_ROOT = Path(
    "data"
)

REPORT_ROOT = Path(
    "reports"
)


class OrchestrationError(RuntimeError):
    """Raised when a weekly stage cannot run safely."""


def load_project_config(
    path: Path = Path(
        "config.json"
    ),
) -> dict[str, Any]:
    """Load the fantasy project configuration."""

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(
                file
            )

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

    if not isinstance(
        config.get(
            "leagues"
        ),
        dict,
    ):
        raise OrchestrationError(
            "Project config is missing leagues"
        )

    return config


def snapshot_paths(
    config: dict[str, Any],
    season: str,
    week: int,
    stage: str,
    data_root: Path = DATA_ROOT,
) -> dict[str, Path]:
    """Return both official snapshot paths for a stage."""

    return {
        league_key: build_snapshot_path(
            data_root=data_root,
            season=season,
            league_key=league_key,
            week=week,
            stage=stage,
        )
        for league_key
        in config["leagues"]
    }


def snapshot_pair_state(
    paths: dict[str, Path],
    label: str,
) -> str:
    """Return absent/complete while rejecting partial historical state."""

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


def preview_report_path(
    season: str,
    league_key: str,
    week: int,
    report_root: Path = REPORT_ROOT,
) -> Path:
    """Return the canonical preview Markdown path."""

    return (
        report_root
        / season
        / (
            f"{league_key}_"
            f"week_{week:02d}_preview.md"
        )
    )


def _validate_project_season(
    config: dict[str, Any],
    schedule: WeeklySchedule,
) -> str:
    """Require project and automation seasons to match."""

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
            "schedule season do not match"
        )

    return season


def _require_execution_window(
    schedule: WeeklySchedule,
    stage: str,
    week: int,
) -> StageWindow:
    """Require the current time to be inside a stage's write window."""

    window = stage_window(
        schedule,
        stage,
        week,
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
    stage: str,
) -> dict[str, Any]:
    """Build generic capture metadata."""

    now = datetime.now(
        schedule.timezone
    )

    return {
        "mode": (
            "generic_weekly_orchestration"
        ),
        "stage_label": stage,
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
    """Fetch player metadata, projections, and overrides once."""

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

    overrides = (
        load_week_projection_overrides(
            Path(
                f"data/{season}/"
                "projection_overrides.json"
            ),
            week=week,
        )
    )

    return (
        sleeper,
        players,
        projection_lookup,
        overrides,
    )


def _ensure_preview_reports(
    season: str,
    week: int,
    paths: dict[str, Path],
) -> None:
    """Create missing previews strictly from frozen baselines."""

    for league_key, snapshot_path in (
        paths.items()
    ):
        report_path = (
            preview_report_path(
                season,
                league_key,
                week,
            )
        )

        if report_path.exists():
            print(
                f"Preview already exists: "
                f"{report_path}"
            )

            continue

        result = write_preview_report(
            snapshot_path,
            report_path,
        )

        print(
            f"CREATED: {result}"
        )


def run_baseline(
    week: int,
    schedule: WeeklySchedule,
    check_only: bool = False,
) -> int:
    """Build or write one week's immutable baselines and previews."""

    config = load_project_config()

    season = _validate_project_season(
        config,
        schedule,
    )

    paths = snapshot_paths(
        config,
        season,
        week,
        "baseline",
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
            _ensure_preview_reports(
                season,
                week,
                paths,
            )

        return 0

    window = stage_window(
        schedule,
        "baseline",
        week,
    )

    if not check_only:
        window = (
            _require_execution_window(
                schedule,
                "baseline",
                week,
            )
        )

    (
        sleeper,
        players,
        projection_lookup,
        overrides,
    ) = _fresh_week_inputs(
        season,
        week,
    )

    capture_context = (
        _capture_context(
            schedule,
            window,
            "baseline",
        )
    )

    prepared: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, league_config in (
        config["leagues"].items()
    ):
        league_id = (
            league_config["league_id"]
        )

        league_name = (
            league_config["name"]
        )

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

        incomplete = [
            team
            for team in baseline[
                "teams"
            ]
            if not team[
                "projection_complete"
            ]
        ]

        if incomplete:
            print()

            for team in incomplete:
                print(
                    f"INCOMPLETE: "
                    f"{team['manager_name']} "
                    f"(roster {team['roster_id']})"
                )

                for warning in team[
                    "warnings"
                ]:
                    print(
                        f"  {warning}"
                    )

            raise OrchestrationError(
                f"{league_name} contains "
                "incomplete baseline projections"
            )

        prepared[
            league_key
        ] = {
            "league_id": league_id,
            "league_name": league_name,
            "data": baseline,
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

    _require_execution_window(
        schedule,
        "baseline",
        week,
    )

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

        print(
            f"CREATED: {path}"
        )

    _ensure_preview_reports(
        season,
        week,
        paths,
    )

    print()
    print(
        "BASELINE + PREVIEW COMPLETE"
    )

    return 0


def run_sunday(
    week: int,
    schedule: WeeklySchedule,
    check_only: bool = False,
) -> int:
    """Build or write one week's Monday-noon Sunday checkpoint."""

    config = load_project_config()

    season = _validate_project_season(
        config,
        schedule,
    )

    baseline_paths = snapshot_paths(
        config,
        season,
        week,
        "baseline",
    )

    sunday_paths = snapshot_paths(
        config,
        season,
        week,
        "sunday",
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
        "SUNDAY/MNF CHECKPOINT"
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

        return 0

    if baseline_state != "complete":
        if check_only:
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
        schedule,
        "sunday",
        week,
    )

    if not check_only:
        window = (
            _require_execution_window(
                schedule,
                "sunday",
                week,
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
        season,
        week,
    )

    capture_context = (
        _capture_context(
            schedule,
            window,
            "sunday_pre_mnf",
        )
    )

    prepared: dict[
        str,
        dict[str, Any],
    ] = {}

    for league_key, league_config in (
        config["leagues"].items()
    ):
        league_id = (
            league_config["league_id"]
        )

        league_name = (
            league_config["name"]
        )

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

        prepared[
            league_key
        ] = {
            "league_id": league_id,
            "league_name": league_name,
            "data": sunday,
        }

    print()
    print("=" * 72)
    print("SUNDAY CHECKPOINT SUMMARY")
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

    _require_execution_window(
        schedule,
        "sunday",
        week,
    )

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

        stored[
            league_key
        ] = read_snapshot(
            path
        )

        print(
            f"CREATED: {path}"
        )

    print()
    print("=" * 72)
    print("BASELINE-TO-SUNDAY CHANGES")
    print("=" * 72)

    for league_key, league_config in (
        config["leagues"].items()
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

        changed = [
            team
            for team in comparison.teams
            if (
                team.added_starters
                or team.removed_starters
                or team.slot_changes
            )
        ]

        print(
            f"{league_config['name']}: "
            f"{len(changed)} teams "
            "with lineup changes"
        )

    print()
    print(
        "SUNDAY SNAPSHOT COMPLETE"
    )

    return 0


def run_final(
    week: int,
    schedule: WeeklySchedule,
    check_only: bool = False,
) -> int:
    """Placeholder until final-stage construction is implemented."""

    raise OrchestrationError(
        "Final-stage orchestration is not "
        "implemented yet. "
        f"Week requested: {week}"
    )


def run_auto(
    schedule: WeeklySchedule,
    check_only: bool = False,
    minimum_week: int | None = None,
) -> int:
    """Run whichever generic stage is due right now."""

    now = datetime.now(
        schedule.timezone
    )

    due = resolve_due_stage(
        schedule=schedule,
        moment=now,
        minimum_week=minimum_week,
    )

    if due is None:
        print(
            "No fantasy automation stage "
            "is due right now."
        )

        return 0

    print(
        f"Resolved automation: "
        f"{due.stage} Week {due.week}"
    )

    if due.stage == "baseline":
        return run_baseline(
            due.week,
            schedule,
            check_only=check_only,
        )

    if due.stage == "sunday":
        return run_sunday(
            due.week,
            schedule,
            check_only=check_only,
        )

    if due.stage == "final":
        return run_final(
            due.week,
            schedule,
            check_only=check_only,
        )

    raise OrchestrationError(
        f"Unsupported stage: {due.stage}"
    )