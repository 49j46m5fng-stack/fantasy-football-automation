"""One-time automation for freezing the official 2026 Week 1 baseline."""

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.baseline import build_baseline_snapshot_data
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
from src.team_projections import (
    load_week_projection_overrides,
)


SEASON = "2026"
WEEK = 1

TIMEZONE_NAME = "America/Chicago"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

FREEZE_WINDOW_START = datetime(
    2026,
    9,
    9,
    18,
    0,
    tzinfo=TIMEZONE,
)

FIRST_KICKOFF = datetime(
    2026,
    9,
    9,
    19,
    20,
    tzinfo=TIMEZONE,
)

FIRST_GAME = (
    "New England Patriots at Seattle Seahawks"
)

DATA_ROOT = Path("data")


class FreezeBaselineError(RuntimeError):
    """Raised when the scheduled baseline cannot be frozen safely."""


def freeze_window_status(
    now: datetime,
) -> str:
    """Describe whether the official freeze window is currently open."""

    if now.date() != FIRST_KICKOFF.date():
        return "wrong_date"

    if now < FREEZE_WINDOW_START:
        return "too_early"

    if now >= FIRST_KICKOFF:
        return "too_late"

    return "open"


def get_target_paths(
    config: dict[str, Any],
) -> dict[str, Path]:
    """Return official Week 1 baseline paths for every configured league."""

    return {
        league_key: build_snapshot_path(
            data_root=DATA_ROOT,
            season=SEASON,
            league_key=league_key,
            week=WEEK,
            stage="baseline",
        )
        for league_key in config["leagues"]
    }


def snapshot_state(
    targets: dict[str, Path],
) -> str:
    """Return baseline state while rejecting dangerous partial freezes."""

    existence = {
        league_key: path.exists()
        for league_key, path in targets.items()
    }

    if all(existence.values()):
        return "complete"

    if not any(existence.values()):
        return "absent"

    details = ", ".join(
        f"{league_key}={'exists' if exists else 'missing'}"
        for league_key, exists in existence.items()
    )

    raise FreezeBaselineError(
        "Partial baseline state detected. "
        "Refusing automated changes. "
        f"{details}"
    )


def sha256_file(
    path: Path,
) -> str:
    """Return the SHA-256 checksum of one stored snapshot."""

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_config() -> dict[str, Any]:
    """Load and validate the project configuration."""

    path = Path("config.json")

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(file)

    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeBaselineError(
            "Could not read config.json"
        ) from exc

    if config.get("season") != SEASON:
        raise FreezeBaselineError(
            f"Expected config season {SEASON}, "
            f"found {config.get('season')!r}"
        )

    leagues = config.get("leagues")

    if not isinstance(leagues, dict):
        raise FreezeBaselineError(
            "config.json is missing leagues"
        )

    if set(leagues) != {"goats", "doats"}:
        raise FreezeBaselineError(
            "Expected exactly goats and doats leagues"
        )

    return config


def build_capture_context() -> dict[str, Any]:
    """Build metadata explaining when and how this baseline was captured."""

    now = datetime.now(TIMEZONE)

    github_actions = (
        os.environ.get("GITHUB_ACTIONS") == "true"
    )

    return {
        "mode": (
            "github_actions_scheduled_freeze"
            if github_actions
            else "manual_freeze"
        ),
        "timezone": TIMEZONE_NAME,
        "captured_at_local": now.isoformat(),
        "captured_at_utc": (
            now
            .astimezone(ZoneInfo("UTC"))
            .isoformat()
        ),
        "first_game": FIRST_GAME,
        "first_kickoff_local": (
            FIRST_KICKOFF.isoformat()
        ),
        "first_kickoff_utc": (
            FIRST_KICKOFF
            .astimezone(ZoneInfo("UTC"))
            .isoformat()
        ),
        "kickoff_source": (
            "NFL Week 1 schedule manually verified"
        ),
    }


def prepare_baselines(
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Fetch fresh data and prepare both baseline documents in memory."""

    sleeper = SleeperClient()

    print("Refreshing NFL player metadata...")
    players = get_player_map(
        sleeper,
        refresh=True,
    )

    print("Fetching fresh Week 1 projections...")
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
            f"Fetching {league_name}..."
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

        matchup_records = (
            sleeper.get_matchups(
                league_id,
                week=WEEK,
            )
        )

        baseline = (
            build_baseline_snapshot_data(
                league_key=league_key,
                league_id=league_id,
                week=WEEK,
                league=league,
                users=users,
                rosters=rosters,
                matchup_records=(
                    matchup_records
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
            for team in baseline["teams"]
            if not team[
                "projection_complete"
            ]
        ]

        if incomplete:
            print()
            print(
                f"{league_name} has incomplete "
                "team projections:"
            )

            for team in incomplete:
                print(
                    f"  roster="
                    f"{team['roster_id']} "
                    f"manager="
                    f"{team['manager_name']}"
                )

                for warning in team[
                    "warnings"
                ]:
                    print(
                        f"    WARNING: "
                        f"{warning}"
                    )

            raise FreezeBaselineError(
                f"{league_name} contains "
                "incomplete projections"
            )

        expected_rosters = (
            league.get(
                "total_rosters"
            )
        )

        if (
            isinstance(
                expected_rosters,
                int,
            )
            and len(
                baseline["teams"]
            )
            != expected_rosters
        ):
            raise FreezeBaselineError(
                f"{league_name} team count "
                "does not match Sleeper"
            )

        prepared[league_key] = {
            "league_id": league_id,
            "league_name": league_name,
            "baseline": baseline,
        }

    return prepared


def print_summary(
    prepared: dict[
        str,
        dict[str, Any],
    ],
) -> None:
    """Print the prepared baseline summary."""

    print()
    print("=" * 72)
    print("PREPARED BASELINE SUMMARY")
    print("=" * 72)

    for item in prepared.values():
        baseline = item["baseline"]

        print()
        print(item["league_name"])

        print(
            f"  teams:    "
            f"{len(baseline['teams'])}"
        )

        print(
            f"  matchups: "
            f"{len(baseline['matchups'])}"
        )

        print(
            f"  warnings: "
            f"{len(baseline['warnings'])}"
        )

        for warning in (
            baseline["warnings"]
        ):
            print(
                f"    WARNING: "
                f"{warning}"
            )


def freeze_prepared_baselines(
    prepared: dict[
        str,
        dict[str, Any],
    ],
) -> None:
    """Write and validate both official immutable snapshots."""

    now = datetime.now(TIMEZONE)

    if freeze_window_status(now) != "open":
        raise FreezeBaselineError(
            "Freeze window closed while "
            "baseline data was being prepared"
        )

    print()
    print("=" * 72)
    print("WRITING OFFICIAL BASELINES")
    print("=" * 72)

    written_paths: dict[
        str,
        Path,
    ] = {}

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
            stage="baseline",
            data=item["baseline"],
        )

        written_paths[
            league_key
        ] = path

        print(
            f"CREATED: {path}"
        )

    print()
    print("=" * 72)
    print("READ-BACK VALIDATION")
    print("=" * 72)

    for league_key, path in (
        written_paths.items()
    ):
        stored = read_snapshot(
            path
        )

        print()
        print(
            league_key.upper()
        )

        print(
            f"  stage:    "
            f"{stored['stage']}"
        )

        print(
            f"  season:   "
            f"{stored['season']}"
        )

        print(
            f"  week:     "
            f"{stored['week']}"
        )

        print(
            f"  teams:    "
            f"{len(stored['data']['teams'])}"
        )

        print(
            f"  matchups: "
            f"{len(stored['data']['matchups'])}"
        )

        print(
            f"  SHA-256:  "
            f"{sha256_file(path)}"
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
                stage="baseline",
                data=item["baseline"],
            )

        except SnapshotExistsError:
            print(
                f"PASS: second "
                f"{league_key} write "
                "was refused."
            )

        else:
            raise FreezeBaselineError(
                f"Second {league_key} "
                "baseline write was not refused"
            )


def main(
    check_only: bool,
) -> int:
    """Run validation or the official scheduled freeze."""

    config = load_config()

    targets = get_target_paths(
        config
    )

    state = snapshot_state(
        targets
    )

    now = datetime.now(
        TIMEZONE
    )

    print("=" * 72)
    print("2026 WEEK 1 BASELINE AUTOMATION")
    print("=" * 72)

    print(
        f"Current time:   "
        f"{now.isoformat()}"
    )

    print(
        f"Freeze opens:   "
        f"{FREEZE_WINDOW_START.isoformat()}"
    )

    print(
        f"First kickoff:  "
        f"{FIRST_KICKOFF.isoformat()}"
    )

    print(
        f"Snapshot state: "
        f"{state}"
    )

    print()

    if state == "complete":
        print(
            "Both official Week 1 "
            "baselines already exist."
        )

        print(
            "No action is required."
        )

        return 0

    if check_only:
        print(
            "CHECK-ONLY MODE: "
            "no official files will be written."
        )

        prepared = (
            prepare_baselines(
                config
            )
        )

        print_summary(
            prepared
        )

        print()
        print(
            "CHECK ONLY COMPLETE"
        )

        print(
            "No baseline snapshots "
            "were written."
        )

        return 0

    status = (
        freeze_window_status(
            now
        )
    )

    if status == "wrong_date":
        print(
            "NO-OP: this automation "
            "only freezes on "
            "September 9, 2026."
        )

        return 0

    if status == "too_early":
        raise FreezeBaselineError(
            "The official freeze "
            "window has not opened yet"
        )

    if status == "too_late":
        raise FreezeBaselineError(
            "The first Week 1 kickoff "
            "has already occurred"
        )

    prepared = (
        prepare_baselines(
            config
        )
    )

    print_summary(
        prepared
    )

    freeze_prepared_baselines(
        prepared
    )

    print()
    print("=" * 72)
    print("BASELINE FREEZE COMPLETE")
    print("=" * 72)

    print(
        "Both official Week 1 "
        "baseline snapshots were "
        "created and validated."
    )

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "Fetch and validate the "
            "baseline without writing "
            "official snapshot files."
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

    except FreezeBaselineError as exc:
        print()
        print(
            f"ERROR: {exc}"
        )

        raise SystemExit(1)