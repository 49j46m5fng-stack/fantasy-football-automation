"""One-time repair for Sunday snapshots missing remaining-player analytics.

This command is intentionally narrow. It only recaptures a Sunday checkpoint
when every configured league already has a Sunday snapshot and those snapshots
are missing the ``data.remaining`` block that the generic Week 2+ orchestration
is supposed to write.

The original snapshot bytes are restored if the recapture fails.
"""

import argparse
from pathlib import Path
from typing import Any

from src.orchestration import (
    OrchestrationError,
    load_project_config,
    run_sunday,
    snapshot_paths,
)
from src.schedule import (
    load_weekly_schedule,
)
from src.storage import (
    read_snapshot,
)


class SundayRemainingRepairError(RuntimeError):
    """Raised when a Sunday remaining-data repair is unsafe."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recapture an existing Sunday checkpoint that is missing "
            "remaining-player/MNF analytics."
        )
    )

    parser.add_argument(
        "--week",
        type=int,
        required=True,
        help="Fantasy week to repair.",
    )

    return parser.parse_args()


def _missing_remaining(
    snapshot: dict[str, Any],
) -> bool:
    data = snapshot.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):
        raise SundayRemainingRepairError(
            "Stored Sunday snapshot has invalid data"
        )

    return not isinstance(
        data.get(
            "remaining"
        ),
        dict,
    )


def repair_week(
    week: int,
) -> int:
    """Recapture one bad Sunday checkpoint and restore on failure."""

    if week < 1:
        raise SundayRemainingRepairError(
            "week must be at least 1"
        )

    config = load_project_config()
    schedule = load_weekly_schedule()

    season = config.get(
        "season"
    )

    if not isinstance(
        season,
        str,
    ):
        raise SundayRemainingRepairError(
            "Project config is missing season"
        )

    paths = snapshot_paths(
        config=config,
        season=season,
        week=week,
        stage="sunday",
    )

    agent_path = (
        Path("data")
        / season
        / "agent"
        / f"week_{week:02d}_sunday.json"
    )

    backups: dict[Path, bytes] = {}
    agent_backup = (
        agent_path.read_bytes()
        if agent_path.exists()
        else None
    )

    for league_key, path in paths.items():
        if not path.exists():
            raise SundayRemainingRepairError(
                f"Sunday snapshot does not exist for {league_key}: {path}"
            )

        snapshot = read_snapshot(
            path
        )

        if snapshot.get(
            "stage"
        ) != "sunday":
            raise SundayRemainingRepairError(
                f"Not a Sunday snapshot: {path}"
            )

        if not _missing_remaining(
            snapshot
        ):
            raise SundayRemainingRepairError(
                f"{path} already contains remaining-player analytics; "
                "refusing to recapture it"
            )

        backups[path] = path.read_bytes()

    print(
        f"Repairing {season} Week {week} Sunday remaining-player analytics..."
    )

    try:
        for path in backups:
            path.unlink()

        return run_sunday(
            week=week,
            schedule=schedule,
            check_only=False,
        )

    except Exception:
        for path, contents in backups.items():
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            path.write_bytes(
                contents
            )

        if agent_backup is None:
            if agent_path.exists():
                agent_path.unlink()
        else:
            agent_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            agent_path.write_bytes(
                agent_backup
            )

        raise


def main() -> int:
    args = _parse_args()

    try:
        return repair_week(
            args.week
        )
    except (
        SundayRemainingRepairError,
        OrchestrationError,
    ) as exc:
        raise SystemExit(
            str(exc)
        ) from exc


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
