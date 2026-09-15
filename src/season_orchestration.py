"""Orchestration for derived season analytics.

Season analytics are derived artifacts. They never write immutable stage
snapshots and are always safe to rerun: every execution recomputes state
from stored snapshots and replaces the derived outputs.

Two inputs cannot be read from stored snapshots alone:

- season lineup efficiency, which needs actual player statistics
- the remaining regular-season schedule, which needs future matchups

Both are fetched through the existing isolated providers. When a fetch
fails the dependent analytic is omitted with a visible warning rather
than estimated.
"""

from pathlib import Path
from typing import Any

from src.actuals import (
    ActualScoringError,
    build_player_actual_lookup,
)
from src.donut_orchestration import (
    _write_json_atomic_replace,
)
from src.lineup import (
    LineupAnalyticsError,
    analyze_final_lineup_efficiency,
)
from src.orchestration import (
    DATA_ROOT,
    OrchestrationError,
    load_project_config,
)
from src.player_stats import (
    PlayerStatsError,
    SleeperPlayerStatsProvider,
)
from src.season_analytics import (
    SeasonAnalyticsError,
    build_season_analytics,
    completed_final_weeks,
    read_final_snapshot,
    season_analytics_context,
)
from src.season_report import (
    write_season_report,
)
from src.simulation import (
    RemainingGame,
)
from src.sleeper import (
    SleeperAPIError,
    SleeperClient,
)


REPORTS_ROOT = Path("reports")


def season_context_path(
    season: str,
    data_root: Path = DATA_ROOT,
) -> Path:
    """Return the derived season-analytics context path."""

    return (
        data_root
        / season
        / "agent"
        / "season_analytics.json"
    )


def season_report_path(
    season: str,
    reports_root: Path = REPORTS_ROOT,
) -> Path:
    """Return the human-readable season report path."""

    return (
        reports_root
        / season
        / "season_report.md"
    )


def build_season_lineup_efficiency(
    data_root: Path,
    season: str,
    league_keys: tuple[str, ...],
    weeks: tuple[int, ...],
    season_type: str = "regular",
    stats_provider: Any | None = None,
) -> tuple[
    dict[str, dict[int, float]],
    list[str],
]:
    """Average exact lineup efficiency across completed weeks.

    Returns a mapping of league key to roster efficiency percentage, plus
    any warnings. A league is omitted entirely when efficiency cannot be
    resolved for every one of its rosters, because power rankings must
    not receive a partially invented component.
    """

    provider = (
        stats_provider
        if stats_provider is not None
        else SleeperPlayerStatsProvider()
    )

    warnings: list[str] = []

    totals: dict[
        str,
        dict[int, list[float]],
    ] = {}

    for week in weeks:
        try:
            records = provider.get_week_stats(
                season=season,
                week=week,
                season_type=season_type,
            )

        except PlayerStatsError as exc:
            warnings.append(
                f"Actual player statistics for week "
                f"{week} were unavailable: {exc}"
            )

            continue

        for league_key in league_keys:
            snapshot = read_final_snapshot(
                data_root=data_root,
                season=season,
                league_key=league_key,
                week=week,
            )

            scoring_settings = (
                snapshot.get(
                    "data",
                    {},
                )
                .get(
                    "league",
                    {},
                )
                .get(
                    "scoring_settings"
                )
            )

            if not isinstance(
                scoring_settings,
                dict,
            ):
                warnings.append(
                    f"{league_key} week {week} final "
                    "snapshot has no scoring settings; "
                    "lineup efficiency skipped."
                )

                continue

            try:
                actuals = (
                    build_player_actual_lookup(
                        records=records,
                        scoring_settings=(
                            scoring_settings
                        ),
                    )
                )

                efficiency = (
                    analyze_final_lineup_efficiency(
                        final_snapshot=snapshot,
                        actuals=actuals,
                    )
                )

            except (
                ActualScoringError,
                LineupAnalyticsError,
            ) as exc:
                warnings.append(
                    f"{league_key} week {week} lineup "
                    f"efficiency failed: {exc}"
                )

                continue

            for team in efficiency.teams:
                if team.lineup_efficiency_pct is None:
                    continue

                totals.setdefault(
                    league_key,
                    {},
                ).setdefault(
                    team.roster_id,
                    [],
                ).append(
                    team.lineup_efficiency_pct
                )

    resolved: dict[
        str,
        dict[int, float],
    ] = {}

    for league_key, rosters in totals.items():
        resolved[
            league_key
        ] = {
            roster_id: (
                sum(
                    values
                )
                / len(
                    values
                )
            )
            for roster_id, values
            in rosters.items()
            if values
        }

    return (
        resolved,
        warnings,
    )


def build_remaining_schedule(
    config: dict[str, Any],
    through_week: int,
    regular_season_weeks: int,
    client: Any | None = None,
) -> tuple[
    dict[str, list[RemainingGame]],
    list[str],
]:
    """Fetch remaining regular-season matchups for every league."""

    sleeper = (
        client
        if client is not None
        else SleeperClient()
    )

    warnings: list[str] = []

    remaining: dict[
        str,
        list[RemainingGame],
    ] = {}

    for league_key, league_config in config[
        "leagues"
    ].items():
        league_id = league_config.get(
            "league_id"
        )

        if not league_id:
            warnings.append(
                f"{league_key} has no league_id; "
                "simulations skipped."
            )

            continue

        games: list[RemainingGame] = []

        failed = False

        for week in range(
            through_week + 1,
            regular_season_weeks + 1,
        ):
            try:
                records = sleeper.get_matchups(
                    league_id=league_id,
                    week=week,
                )

            except SleeperAPIError as exc:
                warnings.append(
                    f"{league_key} week {week} "
                    f"schedule unavailable: {exc}"
                )

                failed = True

                break

            pairs: dict[
                Any,
                list[int],
            ] = {}

            for record in records:
                matchup_id = record.get(
                    "matchup_id"
                )

                roster_id = record.get(
                    "roster_id"
                )

                if (
                    matchup_id is None
                    or not isinstance(
                        roster_id,
                        int,
                    )
                ):
                    continue

                pairs.setdefault(
                    matchup_id,
                    [],
                ).append(
                    roster_id
                )

            for matchup_id, roster_ids in sorted(
                pairs.items(),
                key=lambda item: str(
                    item[0]
                ),
            ):
                if len(
                    roster_ids
                ) != 2:
                    warnings.append(
                        f"{league_key} week {week} "
                        f"matchup {matchup_id} did not "
                        "contain exactly two rosters; "
                        "it was skipped."
                    )

                    continue

                games.append(
                    RemainingGame(
                        week=week,
                        roster_id_1=sorted(
                            roster_ids
                        )[0],
                        roster_id_2=sorted(
                            roster_ids
                        )[1],
                    )
                )

        if not failed:
            remaining[
                league_key
            ] = games

    return (
        remaining,
        warnings,
    )


def run_analytics(
    through_week: int | None = None,
    config_path: Path = Path("config.json"),
    data_root: Path = DATA_ROOT,
    reports_root: Path = REPORTS_ROOT,
    check_only: bool = False,
    skip_live_inputs: bool = False,
) -> int:
    """Recompute season analytics and refresh derived outputs."""

    config = load_project_config(
        config_path
    )

    season = config["season"]

    league_keys = tuple(
        config["leagues"]
    )

    regular_season_weeks = int(
        config.get(
            "regular_season_weeks",
            18,
        )
    )

    max_week = (
        through_week
        if through_week is not None
        else regular_season_weeks
    )

    weeks = completed_final_weeks(
        data_root=data_root,
        season=season,
        league_keys=league_keys,
        max_week=max_week,
    )

    if not weeks:
        raise OrchestrationError(
            "No completed final snapshots are "
            "available for season analytics"
        )

    completed_through = weeks[-1]

    warnings: list[str] = []

    lineup_efficiency = None

    remaining_games = None

    if skip_live_inputs:
        warnings.append(
            "Live inputs were skipped. Power rankings "
            "and simulations are omitted."
        )

    else:
        (
            lineup_efficiency,
            efficiency_warnings,
        ) = build_season_lineup_efficiency(
            data_root=data_root,
            season=season,
            league_keys=league_keys,
            weeks=weeks,
            season_type=config.get(
                "season_type",
                "regular",
            ),
        )

        warnings.extend(
            efficiency_warnings
        )

        (
            remaining_games,
            schedule_warnings,
        ) = build_remaining_schedule(
            config=config,
            through_week=completed_through,
            regular_season_weeks=(
                regular_season_weeks
            ),
        )

        warnings.extend(
            schedule_warnings
        )

    try:
        analytics = build_season_analytics(
            data_root=data_root,
            season=season,
            project_config=config,
            max_week=max_week,
            remaining_games=remaining_games,
            lineup_efficiency_pct=(
                lineup_efficiency
            ),
        )

    except SeasonAnalyticsError as exc:
        raise OrchestrationError(
            str(exc)
        ) from exc

    print()
    print("=" * 72)
    print(
        f"{season} SEASON ANALYTICS — THROUGH WEEK "
        f"{analytics.through_week}"
    )
    print("=" * 72)

    for league in analytics.leagues:
        print()
        print(
            f"{league.league_name}: "
            f"{len(league.standings.teams)} teams"
        )

        zone = [
            team
            for team in league.watch
            if team.in_relegation_zone
        ]

        if zone:
            print(
                "  Relegation zone: "
                + ", ".join(
                    f"{team.manager_name} "
                    f"(#{team.analytical_rank})"
                    for team in zone
                )
            )

        print(
            "  Power rankings: "
            + (
                "available"
                if league.power_rankings is not None
                else "unavailable"
            )
        )

        print(
            "  Simulations:    "
            + (
                "available"
                if league.simulation is not None
                else "unavailable"
            )
        )

    if analytics.luck.weeks:
        latest = analytics.luck.weeks[-1]

        unlucky = sorted(
            latest.teams,
            key=lambda team: team.luck_wins,
        )[:1]

        for team in unlucky:
            print()
            print(
                f"Week {latest.week} unluckiest: "
                f"{team.manager_name} "
                f"({team.league_key}) — "
                f"{team.note}"
            )

    for warning in (
        list(
            warnings
        )
        + list(
            analytics.warnings
        )
    ):
        print(f"WARNING: {warning}")

    if check_only:
        print()
        print(
            "Check-only run. No analytics artifacts "
            "were written."
        )

        return 0

    context_path = season_context_path(
        season=season,
        data_root=data_root,
    )

    document = season_analytics_context(
        analytics
    )

    document["warnings"] = (
        list(
            document.get(
                "warnings",
                [],
            )
        )
        + warnings
    )

    _write_json_atomic_replace(
        path=context_path,
        document=document,
    )

    report_path = write_season_report(
        analytics=analytics,
        report_path=season_report_path(
            season=season,
            reports_root=reports_root,
        ),
    )

    print()
    print(
        f"Wrote season analytics context: "
        f"{context_path}"
    )

    print(
        f"Wrote season report: {report_path}"
    )

    return 0
