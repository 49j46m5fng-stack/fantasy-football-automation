from datetime import datetime
from zoneinfo import ZoneInfo

from src.schedule import (
    due_week_for_stage,
    load_weekly_schedule,
    resolve_due_stage,
    scheduled_date,
    stage_window,
)


TIMEZONE = ZoneInfo(
    "America/Chicago"
)


def schedule():
    return load_weekly_schedule()


def test_week1_baseline_is_wednesday() -> None:
    value = scheduled_date(
        schedule(),
        "baseline",
        1,
    )

    assert str(value) == "2026-09-09"


def test_week2_baseline_is_thursday() -> None:
    value = scheduled_date(
        schedule(),
        "baseline",
        2,
    )

    assert str(value) == "2026-09-17"


def test_week3_baseline_advances_seven_days() -> None:
    value = scheduled_date(
        schedule(),
        "baseline",
        3,
    )

    assert str(value) == "2026-09-24"


def test_week1_sunday_checkpoint_is_monday() -> None:
    value = scheduled_date(
        schedule(),
        "sunday",
        1,
    )

    assert str(value) == "2026-09-14"


def test_baseline_window_runs_around_noon() -> None:
    window = stage_window(
        schedule(),
        "baseline",
        2,
    )

    assert (
        window.opens_at.hour
        == 11
    )

    assert (
        window.opens_at.minute
        == 30
    )

    assert (
        window.closes_at.hour
        == 13
    )


def test_due_baseline_resolves_week2() -> None:
    now = datetime(
        2026,
        9,
        17,
        11,
        45,
        tzinfo=TIMEZONE,
    )

    week = due_week_for_stage(
        schedule(),
        "baseline",
        now,
    )

    assert week == 2


def test_due_sunday_resolves_week2() -> None:
    now = datetime(
        2026,
        9,
        21,
        11,
        45,
        tzinfo=TIMEZONE,
    )

    week = due_week_for_stage(
        schedule(),
        "sunday",
        now,
    )

    assert week == 2


def test_no_stage_due_outside_window() -> None:
    now = datetime(
        2026,
        9,
        17,
        15,
        0,
        tzinfo=TIMEZONE,
    )

    result = resolve_due_stage(
        schedule(),
        now,
    )

    assert result is None


def test_generic_scheduler_ignores_week1() -> None:
    now = datetime(
        2026,
        9,
        9,
        11,
        45,
        tzinfo=TIMEZONE,
    )

    result = resolve_due_stage(
        schedule(),
        now,
    )

    assert result is None


def test_final_stage_is_disabled() -> None:
    now = datetime(
        2026,
        9,
        22,
        11,
        45,
        tzinfo=TIMEZONE,
    )

    result = due_week_for_stage(
        schedule(),
        "final",
        now,
    )

    assert result is None