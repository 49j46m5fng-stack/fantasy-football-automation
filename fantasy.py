"""Command-line entry point for fantasy-football automation."""

import argparse
from datetime import datetime

from src.orchestration import (
    OrchestrationError,
    run_auto,
    run_baseline,
    run_context,
    run_final,
    run_sunday,
)
from src.schedule import (
    ScheduleError,
    due_week_for_stage,
    load_weekly_schedule,
)


def _resolve_week(
    stage: str,
    explicit_week: int | None,
) -> tuple[
    int,
    object,
]:
    """Resolve an explicit or currently scheduled fantasy week."""

    schedule = (
        load_weekly_schedule()
    )

    if explicit_week is not None:
        if (
            explicit_week < 1
            or explicit_week
            > schedule.regular_season_weeks
        ):
            raise ScheduleError(
                f"Week must be between 1 and "
                f"{schedule.regular_season_weeks}"
            )

        return (
            explicit_week,
            schedule,
        )

    now = datetime.now(
        schedule.timezone
    )

    week = due_week_for_stage(
        schedule=schedule,
        stage=stage,
        moment=now,
        minimum_week=1,
    )

    if week is None:
        raise ScheduleError(
            f"No {stage} stage is scheduled "
            "for the current execution window. "
            "Use --week with --check-only if "
            "you want to inspect another week."
        )

    return (
        week,
        schedule,
    )


def _validate_explicit_week(
    week: int,
    schedule: object,
) -> None:
    """Validate a manually supplied fantasy week."""

    regular_season_weeks = (
        schedule.regular_season_weeks
    )

    if (
        week < 1
        or week
        > regular_season_weeks
    ):
        raise ScheduleError(
            f"Week must be between 1 and "
            f"{regular_season_weeks}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the project CLI parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Fantasy football automation"
        )
    )

    subparsers = (
        parser.add_subparsers(
            dest="command",
            required=True,
        )
    )

    for command in (
        "baseline",
        "sunday",
        "final",
    ):
        stage_parser = (
            subparsers.add_parser(
                command
            )
        )

        stage_parser.add_argument(
            "--week",
            type=int,
            default=None,
            help=(
                "Fantasy week. When omitted, "
                "resolve the currently scheduled week."
            ),
        )

        stage_parser.add_argument(
            "--check-only",
            action="store_true",
            help=(
                "Fetch and validate without "
                "writing official snapshots."
            ),
        )

    context_parser = (
        subparsers.add_parser(
            "context"
        )
    )

    context_parser.add_argument(
        "--stage",
        required=True,
        choices=(
            "baseline",
            "sunday",
            "final",
        ),
        help=(
            "Stored historical stage from "
            "which to build AI context."
        ),
    )

    context_parser.add_argument(
        "--week",
        required=True,
        type=int,
        help=(
            "Fantasy week whose immutable "
            "snapshot should be transformed."
        ),
    )

    auto_parser = (
        subparsers.add_parser(
            "auto"
        )
    )

    auto_parser.add_argument(
        "--check-only",
        action="store_true",
    )

    auto_parser.add_argument(
        "--min-week",
        type=int,
        default=None,
        help=(
            "Ignore earlier weeks. "
            "Used while Week 1 fallback "
            "automation remains active."
        ),
    )

    return parser


def main() -> int:
    """Execute the selected fantasy command."""

    parser = build_parser()

    args = parser.parse_args()

    try:
        if args.command == "auto":
            schedule = (
                load_weekly_schedule()
            )

            return run_auto(
                schedule=schedule,
                check_only=(
                    args.check_only
                ),
                minimum_week=(
                    args.min_week
                ),
            )

        if args.command == "context":
            schedule = (
                load_weekly_schedule()
            )

            _validate_explicit_week(
                args.week,
                schedule,
            )

            return run_context(
                stage=args.stage,
                week=args.week,
                schedule=schedule,
            )

        week, schedule = (
            _resolve_week(
                stage=args.command,
                explicit_week=(
                    args.week
                ),
            )
        )

        if args.command == "baseline":
            return run_baseline(
                week=week,
                schedule=schedule,
                check_only=(
                    args.check_only
                ),
            )

        if args.command == "sunday":
            return run_sunday(
                week=week,
                schedule=schedule,
                check_only=(
                    args.check_only
                ),
            )

        if args.command == "final":
            return run_final(
                week=week,
                schedule=schedule,
                check_only=(
                    args.check_only
                ),
            )

        parser.error(
            f"Unknown command: "
            f"{args.command}"
        )

    except (
        OrchestrationError,
        ScheduleError,
    ) as exc:
        print()
        print(
            f"ERROR: {exc}"
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )