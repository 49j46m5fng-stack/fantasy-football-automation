"""Resolve recurring fantasy-football automation dates and windows."""

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


class ScheduleError(ValueError):
    """Raised when automation scheduling data is invalid."""


@dataclass(frozen=True)
class WeeklySchedule:
    """Validated automation schedule configuration."""

    season: str
    timezone_name: str
    regular_season_weeks: int
    minimum_generic_week: int
    stages: dict[str, dict[str, Any]]

    @property
    def timezone(self) -> ZoneInfo:
        """Return the configured timezone."""

        return ZoneInfo(
            self.timezone_name
        )


@dataclass(frozen=True)
class StageWindow:
    """One fantasy week's permitted execution window."""

    stage: str
    week: int
    opens_at: datetime
    closes_at: datetime

    def contains(
        self,
        moment: datetime,
    ) -> bool:
        """Return whether a moment is inside the execution window."""

        if moment.tzinfo is None:
            raise ScheduleError(
                "Scheduled moments must be timezone-aware"
            )

        local = moment.astimezone(
            self.opens_at.tzinfo
        )

        return (
            self.opens_at
            <= local
            < self.closes_at
        )


@dataclass(frozen=True)
class DueStage:
    """A stage currently eligible for automated execution."""

    stage: str
    week: int
    window: StageWindow


def _parse_time(
    value: Any,
    description: str,
) -> time:
    """Parse an HH:MM schedule time."""

    if not isinstance(value, str):
        raise ScheduleError(
            f"{description} must be a string"
        )

    try:
        return time.fromisoformat(
            value
        )

    except ValueError as exc:
        raise ScheduleError(
            f"Invalid {description}: {value!r}"
        ) from exc


def _parse_date(
    value: Any,
    description: str,
) -> date:
    """Parse an ISO date."""

    if not isinstance(value, str):
        raise ScheduleError(
            f"{description} must be a string"
        )

    try:
        return date.fromisoformat(
            value
        )

    except ValueError as exc:
        raise ScheduleError(
            f"Invalid {description}: {value!r}"
        ) from exc


def load_weekly_schedule(
    path: Path = Path(
        "automation_schedule.json"
    ),
) -> WeeklySchedule:
    """Read and validate the automation schedule."""

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ScheduleError(
            f"Could not read schedule: {path}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ScheduleError(
            "Schedule root must be a JSON object"
        )

    if payload.get(
        "schema_version"
    ) != 1:
        raise ScheduleError(
            "Unsupported schedule schema version"
        )

    season = payload.get(
        "season"
    )

    timezone_name = payload.get(
        "timezone"
    )

    regular_season_weeks = (
        payload.get(
            "regular_season_weeks"
        )
    )

    minimum_generic_week = (
        payload.get(
            "minimum_generic_week"
        )
    )

    stages = payload.get(
        "stages"
    )

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise ScheduleError(
            "Schedule is missing season"
        )

    if (
        not isinstance(
            timezone_name,
            str,
        )
        or not timezone_name
    ):
        raise ScheduleError(
            "Schedule is missing timezone"
        )

    try:
        ZoneInfo(
            timezone_name
        )

    except Exception as exc:
        raise ScheduleError(
            f"Unknown timezone: {timezone_name}"
        ) from exc

    if (
        not isinstance(
            regular_season_weeks,
            int,
        )
        or regular_season_weeks < 1
    ):
        raise ScheduleError(
            "regular_season_weeks must be positive"
        )

    if (
        not isinstance(
            minimum_generic_week,
            int,
        )
        or minimum_generic_week < 1
    ):
        raise ScheduleError(
            "minimum_generic_week must be positive"
        )

    if not isinstance(
        stages,
        dict,
    ):
        raise ScheduleError(
            "Schedule is missing stages"
        )

    for stage in (
        "baseline",
        "sunday",
        "final",
    ):
        config = stages.get(
            stage
        )

        if not isinstance(
            config,
            dict,
        ):
            raise ScheduleError(
                f"Schedule is missing {stage} stage"
            )

        if not isinstance(
            config.get(
                "enabled"
            ),
            bool,
        ):
            raise ScheduleError(
                f"{stage}.enabled must be boolean"
            )

        anchor_week = config.get(
            "anchor_week"
        )

        if (
            not isinstance(
                anchor_week,
                int,
            )
            or anchor_week < 1
        ):
            raise ScheduleError(
                f"{stage}.anchor_week must be positive"
            )

        _parse_date(
            config.get(
                "anchor_date"
            ),
            f"{stage}.anchor_date",
        )

        _parse_time(
            config.get(
                "window_start"
            ),
            f"{stage}.window_start",
        )

        _parse_time(
            config.get(
                "window_end"
            ),
            f"{stage}.window_end",
        )

        overrides = config.get(
            "date_overrides",
            {},
        )

        if not isinstance(
            overrides,
            dict,
        ):
            raise ScheduleError(
                f"{stage}.date_overrides must be an object"
            )

        for week_text, date_text in (
            overrides.items()
        ):
            try:
                week = int(
                    week_text
                )

            except ValueError as exc:
                raise ScheduleError(
                    f"Invalid {stage} override week "
                    f"{week_text!r}"
                ) from exc

            if week < 1:
                raise ScheduleError(
                    f"Invalid {stage} override week "
                    f"{week}"
                )

            _parse_date(
                date_text,
                (
                    f"{stage}.date_overrides"
                    f"[{week}]"
                ),
            )

    return WeeklySchedule(
        season=season,
        timezone_name=(
            timezone_name
        ),
        regular_season_weeks=(
            regular_season_weeks
        ),
        minimum_generic_week=(
            minimum_generic_week
        ),
        stages=stages,
    )


def scheduled_date(
    schedule: WeeklySchedule,
    stage: str,
    week: int,
) -> date:
    """Return the scheduled calendar date for one stage/week."""

    if (
        week < 1
        or week
        > schedule.regular_season_weeks
    ):
        raise ScheduleError(
            f"Week {week} is outside "
            "the configured regular season"
        )

    config = schedule.stages.get(
        stage
    )

    if not isinstance(
        config,
        dict,
    ):
        raise ScheduleError(
            f"Unknown stage: {stage}"
        )

    overrides = config.get(
        "date_overrides",
        {},
    )

    override = overrides.get(
        str(week)
    )

    if override is not None:
        return _parse_date(
            override,
            (
                f"{stage} Week {week} "
                "date override"
            ),
        )

    anchor_week = int(
        config["anchor_week"]
    )

    anchor_date = (
        _parse_date(
            config["anchor_date"],
            f"{stage}.anchor_date",
        )
    )

    return (
        anchor_date
        + timedelta(
            weeks=(
                week
                - anchor_week
            )
        )
    )


def stage_window(
    schedule: WeeklySchedule,
    stage: str,
    week: int,
) -> StageWindow:
    """Return the allowed execution window for one stage/week."""

    config = schedule.stages.get(
        stage
    )

    if not isinstance(
        config,
        dict,
    ):
        raise ScheduleError(
            f"Unknown stage: {stage}"
        )

    scheduled = scheduled_date(
        schedule,
        stage,
        week,
    )

    start_time = _parse_time(
        config["window_start"],
        f"{stage}.window_start",
    )

    end_time = _parse_time(
        config["window_end"],
        f"{stage}.window_end",
    )

    timezone = schedule.timezone

    opens_at = datetime.combine(
        scheduled,
        start_time,
        tzinfo=timezone,
    )

    closes_at = datetime.combine(
        scheduled,
        end_time,
        tzinfo=timezone,
    )

    if closes_at <= opens_at:
        raise ScheduleError(
            f"{stage} execution window "
            "must close after it opens"
        )

    return StageWindow(
        stage=stage,
        week=week,
        opens_at=opens_at,
        closes_at=closes_at,
    )


def due_week_for_stage(
    schedule: WeeklySchedule,
    stage: str,
    moment: datetime,
    minimum_week: int = 1,
) -> int | None:
    """Return the stage's week if its execution window is currently open."""

    config = schedule.stages.get(
        stage
    )

    if not isinstance(
        config,
        dict,
    ):
        raise ScheduleError(
            f"Unknown stage: {stage}"
        )

    if not config.get(
        "enabled",
        False,
    ):
        return None

    first_week = max(
        1,
        minimum_week,
    )

    for week in range(
        first_week,
        schedule.regular_season_weeks
        + 1,
    ):
        window = stage_window(
            schedule,
            stage,
            week,
        )

        if window.contains(
            moment
        ):
            return week

    return None


def resolve_due_stage(
    schedule: WeeklySchedule,
    moment: datetime,
    minimum_week: int | None = None,
) -> DueStage | None:
    """Resolve the single automation stage due at a moment."""

    if moment.tzinfo is None:
        raise ScheduleError(
            "Automation time must be timezone-aware"
        )

    if minimum_week is None:
        minimum_week = (
            schedule.minimum_generic_week
        )

    matches: list[
        DueStage
    ] = []

    for stage in (
        "baseline",
        "sunday",
        "final",
    ):
        week = due_week_for_stage(
            schedule=schedule,
            stage=stage,
            moment=moment,
            minimum_week=minimum_week,
        )

        if week is None:
            continue

        matches.append(
            DueStage(
                stage=stage,
                week=week,
                window=stage_window(
                    schedule,
                    stage,
                    week,
                ),
            )
        )

    if len(matches) > 1:
        descriptions = ", ".join(
            (
                f"{match.stage} "
                f"Week {match.week}"
            )
            for match in matches
        )

        raise ScheduleError(
            "Multiple automation stages are due: "
            f"{descriptions}"
        )

    if not matches:
        return None

    return matches[0]