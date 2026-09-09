"""Capture the immutable 2026 Week 1 Sunday/MNF snapshot."""

import argparse
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.comparison import (
    compare_baseline_to_sunday,
)
from src.players import get_player_map
from src.projections import (
    SleeperProjectionProvider,
    build_projection_lookup,
)
from src.sleeper import SleeperClient
from src.storage import (
    SnapshotExistsError,
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


SEASON = "2026"
WEEK = 1

TIMEZONE_NAME = "America/Chicago"
TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)

CAPTURE_DATE = date(
    2026,
    9,
    14,
)

CAPTURE_WINDOW_START = datetime(
    2026,
    9,
    14,
    18,
    0,
    tzinfo=TIMEZONE,
)

MNF_KICKOFF = datetime(
    2026,
    9,
    14,
    19,
    15,
    tzinfo=TIMEZONE,
)

MNF_GAME = (
    "Denver Broncos at Kansas City Chiefs"
)

DATA_ROOT = Path("data")


class SundayCaptureError(RuntimeError):
    """Raised when Sunday capture cannot proceed safely."""


def capture_window_status(
    now: datetime,
) -> str:
    """Describe whether the Week 1 capture window is open."""

    if now.date() != CAPTURE_DATE:
        return "wrong_date"

    if now < CAPTURE_WINDOW_START:
        return "too_early"

    if now >= MNF_KICKOFF:
        return "too_late"

    return "open"


def snapshot_pair_state(
    paths: dict[str, Path],
    label: str,
) -> str:
    """Describe two-league snapshot state and reject partial history."""

    existence = {
        league_key: path.exists()
        for league_key, path in paths.items()
    }

    if all(existence.values()):
        return "complete"

    if not any(existence.values()):
        return "absent"

    details = ", ".join(
        (
            f"{league_key}="
            f"{'exists' if exists else 'missing'}"
        )
        for league_key, exists
        in existence.items()
    )

    raise SundayCaptureError(
        f"Partial {label} snapshot state detected. "
        f"{details}"
    )


def load_config() -> dict[str, Any]:
    """Load the project configuration."""

    with Path("config.json").open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    if config.get("season") != SEASON:
        raise SundayCaptureError(
            f"Expected season {SEASON}"
        )

    leagues = config.get(
        "leagues"
    )

    if not isinstance(
        leagues,
        dict,
    ):
        raise SundayCaptureError(
            "Config is missing leagues"
        )

    if set(leagues) != {
        "goats",
        "doats",
    }:
        raise SundayCaptureError(
            "Expected goats and doats"
        )

    return config


def snapshot_paths(
    config: dict[str, Any],
    stage: str,
) -> dict[str, Path]:
    """Return official snapshot paths for one stage."""

    return {
        league_key: build_snapshot_path(
            data_root=DATA_ROOT,
            season=SEASON,
            league_key=league_key,
            week=WEEK,
            stage=stage,
        )
        for league_key
        in config["leagues"]
    }


def sha256_file(
    path: Path,
) -> str:
    """Return SHA-256 for one snapshot."""

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_baselines(
    paths: dict[str, Path],
) -> dict[str, dict[str, Any]]:
    """Read both immutable baseline snapshots."""

    return {
        league_key: read_snapshot(
            path
        )
        for league_key, path
        in paths.items()
    }


def build_capture_context() -> dict[str, Any]:
    """Create Sunday/MNF capture metadata."""

    now = datetime.now(
        TIMEZONE
    )

    return {
        "mode": (
            "github_actions_pre_mnf_capture"
            if os.environ.get(
                "GITHUB_ACTIONS"
            )
            == "true"
            else "manual_pre_mnf_capture"
        ),
        "stage_label": (
            "sunday_pre_mnf"
        ),
        "timezone": (
            TIMEZONE_NAME
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
        "mnf_game": MNF_GAME,
        "mnf_kickoff_local": (
            MNF_KICKOFF.isoformat()
        ),
        "mnf_kickoff_utc": (
            MNF_KICKOFF
            .astimezone(
                ZoneInfo("UTC")
            )
            .isoformat()
        ),
        "capture_purpose": (
            "Post-Sunday, pre-MNF "
            "official weekly checkpoint"
        ),
    }


def prepare_sunday_snapshots(
    config: dict[str, Any],
    baselines: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, dict[str, Any]]:
    """Fetch fresh data and build both Sunday snapshots in memory."""

    sleeper = SleeperClient()

    print(
        "Refreshing player metadata..."
    )

    players = get_player_map(
        sleeper,
        refresh=True,
    )

    print(
        "Fetching current Week 1 projections..."
    )

    projection_records = (
        SleeperProjectionProvider()
        .get_week_projections(
            season=SEASON,
            week=WEEK,
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
                f"data/{SEASON}/"
                "projection_overrides.json"
            ),
            week=WEEK,
        )
    )

    capture_context = (
        build_capture_context()
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
            week=WEEK,
        )

        sunday = (
            build_sunday_snapshot_data(
                season=SEASON,
                league_key=league_key,
                league_id=league_id,
                week=WEEK,
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
            "league_id": (
                league_id
            ),
            "league_name": (
                league_name
            ),
            "data": sunday,
        }

    return prepared


def print_prepared_summary(
    prepared: dict[
        str,
        dict[str, Any],
    ],
) -> None:
    """Print Sunday snapshot readiness."""

    print()
    print("=" * 72)
    print("SUNDAY/MNF SNAPSHOT SUMMARY")
    print("=" * 72)

    for item in prepared.values():
        data = item["data"]

        incomplete = [
            team
            for team in data["teams"]
            if not team[
                "projection_complete"
            ]
        ]

        known_scores = [
            team
            for team in data["teams"]
            if team[
                "effective_live_points"
            ]
            is not None
        ]

        print()
        print(
            item["league_name"]
        )

        print(
            f"  teams: "
            f"{len(data['teams'])}"
        )

        print(
            f"  matchups: "
            f"{len(data['matchups'])}"
        )

        print(
            f"  live scores present: "
            f"{len(known_scores)}"
        )

        print(
            f"  incomplete stage projections: "
            f"{len(incomplete)}"
        )

        print(
            f"  warnings: "
            f"{len(data['warnings'])}"
        )

        for warning in data[
            "warnings"
        ]:
            print(
                f"    WARNING: "
                f"{warning}"
            )


def print_comparison_summary(
    baseline: dict[str, Any],
    sunday: dict[str, Any],
    league_name: str,
) -> None:
    """Print baseline-to-Sunday lineup changes."""

    comparison = (
        compare_baseline_to_sunday(
            baseline,
            sunday,
        )
    )

    print()
    print("=" * 72)
    print(
        f"{league_name} "
        "BASELINE-TO-SUNDAY CHANGES"
    )
    print("=" * 72)

    found_changes = False

    for team in comparison.teams:
        if (
            not team.added_starters
            and not team.removed_starters
            and not team.slot_changes
        ):
            continue

        found_changes = True

        print()
        print(
            team.sunday_manager_name
        )

        print(
            f"  added starters: "
            f"{team.added_starters}"
        )

        print(
            f"  removed starters: "
            f"{team.removed_starters}"
        )

        print(
            f"  slot changes: "
            f"{len(team.slot_changes)}"
        )

    if not found_changes:
        print()
        print(
            "No lineup changes."
        )


def write_sunday_snapshots(
    config: dict[str, Any],
    prepared: dict[
        str,
        dict[str, Any],
    ],
    baselines: dict[
        str,
        dict[str, Any],
    ],
) -> None:
    """Write, validate, compare, and prove immutability."""

    if (
        capture_window_status(
            datetime.now(TIMEZONE)
        )
        != "open"
    ):
        raise SundayCaptureError(
            "Capture window closed "
            "while data was being prepared"
        )

    written: dict[
        str,
        Path,
    ] = {}

    print()
    print("=" * 72)
    print("WRITING SUNDAY SNAPSHOTS")
    print("=" * 72)

    for league_key, item in (
        prepared.items()
    ):
        path = write_snapshot(
            data_root=DATA_ROOT,
            season=SEASON,
            week=WEEK,
            league_key=league_key,
            league_id=(
                item["league_id"]
            ),
            stage="sunday",
            data=item["data"],
        )

        written[
            league_key
        ] = path

        print(
            f"CREATED: {path}"
        )

    print()
    print("=" * 72)
    print("READ-BACK VALIDATION")
    print("=" * 72)

    stored_snapshots = {}

    for league_key, path in (
        written.items()
    ):
        stored = read_snapshot(
            path
        )

        stored_snapshots[
            league_key
        ] = stored

        print()
        print(
            league_key.upper()
        )

        print(
            f"  stage: "
            f"{stored['stage']}"
        )

        print(
            f"  teams: "
            f"{len(stored['data']['teams'])}"
        )

        print(
            f"  SHA-256: "
            f"{sha256_file(path)}"
        )

    for league_key, item in (
        prepared.items()
    ):
        print_comparison_summary(
            baseline=(
                baselines[
                    league_key
                ]
            ),
            sunday=(
                stored_snapshots[
                    league_key
                ]
            ),
            league_name=(
                item["league_name"]
            ),
        )

    print()
    print("=" * 72)
    print("IMMUTABILITY CHECK")
    print("=" * 72)

    for league_key, item in (
        prepared.items()
    ):
        try:
            write_snapshot(
                data_root=DATA_ROOT,
                season=SEASON,
                week=WEEK,
                league_key=league_key,
                league_id=(
                    item["league_id"]
                ),
                stage="sunday",
                data=item["data"],
            )

        except SnapshotExistsError:
            print(
                f"PASS: second "
                f"{league_key} Sunday "
                "write was refused."
            )

        else:
            raise SundayCaptureError(
                f"Second {league_key} "
                "Sunday write was not refused"
            )


def main(
    check_only: bool,
) -> int:
    """Run the Week 1 Sunday/MNF capture."""

    config = load_config()

    baseline_paths = (
        snapshot_paths(
            config,
            "baseline",
        )
    )

    sunday_paths = (
        snapshot_paths(
            config,
            "sunday",
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

    now = datetime.now(
        TIMEZONE
    )

    print("=" * 72)
    print("2026 WEEK 1 SUNDAY/MNF CAPTURE")
    print("=" * 72)

    print(
        f"Current time:   "
        f"{now.isoformat()}"
    )

    print(
        f"Capture opens:  "
        f"{CAPTURE_WINDOW_START.isoformat()}"
    )

    print(
        f"MNF kickoff:    "
        f"{MNF_KICKOFF.isoformat()}"
    )

    print(
        f"Baseline state: "
        f"{baseline_state}"
    )

    print(
        f"Sunday state:   "
        f"{sunday_state}"
    )

    if sunday_state == "complete":
        print()
        print(
            "Both Sunday snapshots "
            "already exist. No action required."
        )

        return 0

    if baseline_state != "complete":
        if check_only:
            print()
            print(
                "CHECK ONLY: frozen baselines "
                "do not exist yet."
            )

            print(
                "The Sunday automation is armed, "
                "but a full dry run must wait "
                "for the baseline freeze."
            )

            return 0

        raise SundayCaptureError(
            "Cannot capture Sunday stage "
            "without both frozen baselines"
        )

    baselines = load_baselines(
        baseline_paths
    )

    if check_only:
        print()
        print(
            "CHECK-ONLY MODE: "
            "no Sunday snapshots will be written."
        )

        prepared = (
            prepare_sunday_snapshots(
                config,
                baselines,
            )
        )

        print_prepared_summary(
            prepared
        )

        print()
        print(
            "CHECK ONLY COMPLETE"
        )

        return 0

    status = (
        capture_window_status(
            now
        )
    )

    if status == "wrong_date":
        print()
        print(
            "NO-OP: official Week 1 "
            "Sunday capture only runs "
            "September 14, 2026."
        )

        return 0

    if status == "too_early":
        raise SundayCaptureError(
            "Sunday capture window "
            "has not opened yet"
        )

    if status == "too_late":
        raise SundayCaptureError(
            "MNF kickoff has already occurred"
        )

    prepared = (
        prepare_sunday_snapshots(
            config,
            baselines,
        )
    )

    print_prepared_summary(
        prepared
    )

    write_sunday_snapshots(
        config,
        prepared,
        baselines,
    )

    print()
    print("=" * 72)
    print("SUNDAY/MNF CAPTURE COMPLETE")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "Validate without writing "
            "official Sunday snapshots."
        ),
    )

    args = parser.parse_args()

    try:
        raise SystemExit(
            main(
                check_only=(
                    args.check_only
                )
            )
        )

    except SundayCaptureError as exc:
        print()
        print(
            f"ERROR: {exc}"
        )

        raise SystemExit(1)