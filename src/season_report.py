"""Markdown reporting for season-to-date analytics.

Formatting only. Every value rendered here was already calculated by the
deterministic analytics layer. Unavailable analytics are reported as
unavailable rather than estimated.
"""

from pathlib import Path

from src.season_analytics import (
    LUCK_LUCKY,
    LUCK_UNLUCKY,
    SeasonAnalytics,
)


def _points(
    value: float | None,
) -> str:
    """Format an optional fantasy score."""

    if value is None:
        return "unresolved"

    return f"{value:.2f}"


def _signed(
    value: float | None,
) -> str:
    """Format a signed luck value."""

    if value is None:
        return "—"

    return f"{value:+.2f}"


def _probability(
    value: float | None,
) -> str:
    """Format an optional probability as a percentage."""

    if value is None:
        return "—"

    return f"{value * 100:.1f}%"


def _fraction_percent(
    value: float | None,
) -> str:
    """Format a 0-to-1 fraction as a percentage."""

    if value is None:
        return "—"

    return f"{value * 100:.1f}%"


def _rank_change(
    value: int | None,
) -> str:
    """Format a power-ranking movement value."""

    if value is None:
        return "new"

    if value > 0:
        return f"▲{value}"

    if value < 0:
        return f"▼{abs(value)}"

    return "—"


def generate_season_report_markdown(
    analytics: SeasonAnalytics,
) -> str:
    """Render the Tuesday season analytics report."""

    lines: list[str] = [
        (
            f"# {analytics.season} Season Report — "
            f"Through Week {analytics.through_week}"
        ),
        "",
    ]

    relegation_warnings = [
        team
        for league in analytics.leagues
        for team in league.watch
        if team.warning is not None
    ]

    if relegation_warnings:
        lines.extend(
            [
                "## Relegation Warnings",
                "",
            ]
        )

        for team in relegation_warnings:
            probability = _probability(
                team.relegation_probability
            )

            suffix = (
                f" Simulated relegation probability: "
                f"{probability}."
                if team.relegation_probability
                is not None
                else ""
            )

            lines.append(
                f"- **{team.manager_name}** "
                f"({team.league_key.upper()}) — "
                f"{team.warning}{suffix}"
            )

        lines.append(
            ""
        )

    lines.extend(
        [
            "## Luck Tracker",
            "",
            (
                "Luck compares what the schedule "
                "returned against what the week's "
                "scoring earned. Expected wins come "
                "from all-play performance inside each "
                "league. Cross-league rank compares "
                "every team in both leagues combined."
            ),
            "",
        ]
    )

    latest = (
        analytics.luck.weeks[-1]
        if analytics.luck.weeks
        else None
    )

    if latest is not None:
        lines.extend(
            [
                f"### Week {latest.week}",
                "",
                (
                    "| Manager | League | Points | "
                    "Result | Cross-League Rank | "
                    "Expected Wins | Luck |"
                ),
                (
                    "| --- | --- | ---: | --- | ---: "
                    "| ---: | ---: |"
                ),
            ]
        )

        for team in sorted(
            latest.teams,
            key=lambda item: item.luck_wins,
        ):
            lines.append(
                f"| {team.manager_name} "
                f"| {team.league_key.upper()} "
                f"| {_points(team.points_for)} "
                f"| {team.result} "
                f"| {team.cross_league_score_rank} of "
                f"{team.cross_league_team_count} "
                f"| {team.expected_wins:.2f} "
                f"| {_signed(team.luck_wins)} |"
            )

        lines.append(
            ""
        )

        notable = [
            team
            for team in latest.teams
            if team.classification
            in (
                LUCK_UNLUCKY,
                LUCK_LUCKY,
            )
        ]

        if notable:
            lines.extend(
                [
                    (
                        f"**Week {latest.week} "
                        "storylines**"
                    ),
                    "",
                ]
            )

            for team in sorted(
                notable,
                key=lambda item: item.luck_wins,
            ):
                label = (
                    "Unlucky"
                    if team.classification
                    == LUCK_UNLUCKY
                    else "Lucky"
                )

                lines.append(
                    f"- **{label} — "
                    f"{team.manager_name} "
                    f"({team.league_key.upper()})**: "
                    f"{team.note}"
                )

            lines.append(
                ""
            )

    lines.extend(
        [
            "### Season Luck",
            "",
            (
                "| Manager | League | Games | Actual | "
                "Expected | Luck | Unlucky Wks | "
                "Lucky Wks |"
            ),
            (
                "| --- | --- | ---: | ---: | ---: | "
                "---: | ---: | ---: |"
            ),
        ]
    )

    for team in analytics.luck.teams:
        lines.append(
            f"| {team.manager_name} "
            f"| {team.league_key.upper()} "
            f"| {team.games} "
            f"| {team.actual_win_equivalent:.1f} "
            f"| {team.expected_wins:.2f} "
            f"| {_signed(team.luck_wins)} "
            f"| {team.unlucky_weeks} "
            f"| {team.lucky_weeks} |"
        )

    lines.append(
        ""
    )

    for league in analytics.leagues:
        lines.extend(
            [
                f"## {league.league_name}",
                "",
                "### Standings",
                "",
                (
                    "| Rank | Manager | Record | "
                    "Points For | All-Play % | Luck |"
                ),
                (
                    "| ---: | --- | --- | ---: | ---: "
                    "| ---: |"
                ),
            ]
        )

        for team in league.standings.teams:
            record = (
                f"{team.wins}-{team.losses}"
                + (
                    f"-{team.ties}"
                    if team.ties
                    else ""
                )
            )

            lines.append(
                f"| {team.analytical_rank} "
                f"| {team.manager_name} "
                f"| {record} "
                f"| {_points(team.points_for)} "
                f"| {_fraction_percent(team.all_play_percentage)} "
                f"| {_signed(team.luck_wins)} |"
            )

        lines.append(
            ""
        )

        lines.extend(
            [
                "### Power Rankings",
                "",
            ]
        )

        if league.power_rankings is not None:
            lines.extend(
                [
                    (
                        "| Rank | Move | Manager | "
                        "Composite | PPG | All-Play % "
                        "| Lineup Eff. |"
                    ),
                    (
                        "| ---: | :-: | --- | ---: | "
                        "---: | ---: | ---: |"
                    ),
                ]
            )

            for team in league.power_rankings.teams:
                lines.append(
                    f"| {team.current_rank} "
                    f"| {_rank_change(team.rank_change)} "
                    f"| {team.manager_name} "
                    f"| {team.composite_score:.1f} "
                    f"| {team.points_per_game:.2f} "
                    f"| {_fraction_percent(team.all_play_percentage)} "
                    f"| {team.lineup_efficiency_pct:.1f}% |"
                )

        else:
            lines.append(
                "Power rankings are not available for "
                "this run."
            )

        lines.append(
            ""
        )

        lines.extend(
            [
                "### Season Outlook",
                "",
            ]
        )

        if league.simulation is not None:
            simulation = league.simulation

            lines.extend(
                [
                    (
                        f"{simulation.simulations:,} "
                        "Monte Carlo simulations, seed "
                        f"{simulation.random_seed}."
                    ),
                    "",
                    (
                        "| Manager | Exp. Wins | "
                        "Playoffs | Relegation | "
                        "Promotion |"
                    ),
                    (
                        "| --- | ---: | ---: | ---: | "
                        "---: |"
                    ),
                ]
            )

            for team in simulation.teams:
                lines.append(
                    f"| {team.manager_name} "
                    f"| {team.expected_regular_season_wins:.1f} "
                    f"| {_probability(team.playoff_probability)} "
                    f"| {_probability(team.relegation_probability)} "
                    f"| {_probability(team.promotion_probability)} |"
                )

        else:
            lines.append(
                "Season simulations are not available "
                "for this run."
            )

        lines.append(
            ""
        )

        if league.warnings:
            lines.extend(
                [
                    "### Notes",
                    "",
                ]
            )

            for warning in league.warnings:
                lines.append(
                    f"- {warning}"
                )

            lines.append(
                ""
            )

    lines.extend(
        [
            "## Method",
            "",
            (
                "Standings, all-play, and luck are "
                "calculated from stored final "
                "snapshots. Expected wins are "
                "`(all_play_wins + 0.5 * all_play_ties) "
                "/ (league_team_count - 1)`. Luck is "
                "`actual_win_equivalent - "
                "expected_wins`."
            ),
            "",
            (
                "Luck is a schedule-result metric. It "
                "is not a claim about managerial skill."
            ),
            "",
            (
                "Power rankings and simulation "
                "probabilities are analytical. They are "
                "not official Sleeper standings, "
                "playoff seeds, or final promotion and "
                "relegation positions."
            ),
            "",
        ]
    )

    return "\n".join(
        lines
    )


def write_season_report(
    analytics: SeasonAnalytics,
    report_path: Path,
) -> Path:
    """Write the season analytics report to disk."""

    markdown = (
        generate_season_report_markdown(
            analytics
        )
    )

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path.write_text(
        markdown,
        encoding="utf-8",
    )

    return report_path
