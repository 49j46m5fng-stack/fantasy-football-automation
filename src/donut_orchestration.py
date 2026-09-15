"""Orchestration for the cross-league donut survival pool.

The donut pool is a derived artifact. It never writes immutable stage
snapshots and is always safe to rerun: every execution recomputes state
from the stored final snapshots and replaces the derived outputs.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.donut_report import write_donut_report
from src.donuts import (
    DonutPoolError,
    build_donut_agent_context,
    build_donut_pool_from_snapshots,
    load_donut_config,
)
from src.orchestration import (
    DATA_ROOT,
    OrchestrationError,
    load_project_config,
)


REPORTS_ROOT = Path("reports")


def donut_overrides_path(
    season: str,
    data_root: Path = DATA_ROOT,
) -> Path:
    """Return the committed commissioner tie-ruling file path."""

    return (
        data_root
        / season
        / "donut_overrides.json"
    )


def donut_context_path(
    season: str,
    data_root: Path = DATA_ROOT,
) -> Path:
    """Return the derived donut agent-context path."""

    return (
        data_root
        / season
        / "agent"
        / "donut_pool.json"
    )


def donut_report_path(
    season: str,
    reports_root: Path = REPORTS_ROOT,
) -> Path:
    """Return the human-readable donut report path."""

    return (
        reports_root
        / season
        / "donut_pool.md"
    )


def _write_json_atomic_replace(
    path: Path,
    document: dict[str, Any],
) -> None:
    """Replace a derived JSON artifact atomically."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )

    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            handle,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                document,
                file,
                indent=2,
                sort_keys=False,
            )

            file.write("\n")

            file.flush()

            os.fsync(file.fileno())

        os.replace(
            temporary_path,
            path,
        )

    except BaseException:
        temporary_path.unlink(
            missing_ok=True
        )

        raise


def run_donuts(
    through_week: int | None = None,
    config_path: Path = Path("config.json"),
    data_root: Path = DATA_ROOT,
    reports_root: Path = REPORTS_ROOT,
    check_only: bool = False,
) -> int:
    """Recompute the donut survival pool and refresh derived outputs."""

    config = load_project_config(
        config_path
    )

    season = config["season"]

    try:
        donut_config = load_donut_config(
            config
        )

    except DonutPoolError as exc:
        raise OrchestrationError(
            str(exc)
        ) from exc

    if not donut_config.enabled:
        print()
        print(
            "Donut pool is disabled in config.json."
        )

        return 0

    resolved_through_week = (
        through_week
        if through_week is not None
        else donut_config.total_weeks
    )

    if resolved_through_week < 1:
        raise OrchestrationError(
            "through_week must be at least 1"
        )

    try:
        state = build_donut_pool_from_snapshots(
            data_root=data_root,
            season=season,
            config=donut_config,
            through_week=resolved_through_week,
            overrides_path=donut_overrides_path(
                season=season,
                data_root=data_root,
            ),
        )

    except DonutPoolError as exc:
        raise OrchestrationError(
            str(exc)
        ) from exc

    print()
    print(
        f"Donut survival pool — {season}"
    )

    print(
        f"Completed weeks scored: "
        f"{state.through_week}"
    )

    print(
        f"Entrants: {len(state.entrants)}"
    )

    print(
        f"On the hook so far: "
        f"{len(state.eliminated)}"
    )

    print(
        f"Still unDOUGHfeated: "
        f"{len(state.survivors)}"
    )

    if state.next_delivery is not None:
        assignment = state.next_delivery

        print()
        print(
            f"Week {assignment.delivery_week} donuts: "
            f"{assignment.manager_name} "
            f"({assignment.league_key}) "
            f"scored {assignment.points:.2f} in week "
            f"{assignment.scoring_week}."
        )

    if state.undoughfeated is not None:
        print()
        print(
            "unDOUGHfeated champion: "
            f"{state.undoughfeated.manager_name} "
            f"({state.undoughfeated.league_key})"
        )

    for warning in state.warnings:
        print(f"WARNING: {warning}")

    if state.blocked_week is not None:
        print()
        print(
            f"ERROR: Week {state.blocked_week} is an unresolved "
            "tie. Commit a commissioner ruling to "
            f"{donut_overrides_path(season, data_root)} "
            "before later weeks can be scored."
        )

        return 1

    if check_only:
        print()
        print(
            "Check-only run. No donut artifacts were written."
        )

        return 0

    context_path = donut_context_path(
        season=season,
        data_root=data_root,
    )

    _write_json_atomic_replace(
        path=context_path,
        document=build_donut_agent_context(
            state
        ),
    )

    report_path = write_donut_report(
        state=state,
        report_path=donut_report_path(
            season=season,
            reports_root=reports_root,
        ),
    )

    print()
    print(
        f"Wrote donut agent context: {context_path}"
    )

    print(
        f"Wrote donut report: {report_path}"
    )

    return 0
