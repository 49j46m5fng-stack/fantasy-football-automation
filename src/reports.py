"""Generate human-readable reports from immutable fantasy snapshots."""

from pathlib import Path
from typing import Any

from src.storage import read_snapshot


class ReportError(ValueError):
    """Raised when report data is invalid or incomplete."""


def _format_points(
    value: float | int | None,
) -> str:
    """Format fantasy points consistently."""

    if value is None:
        return "INCOMPLETE"

    return f"{float(value):.2f}"


def _team_lookup(
    snapshot_data: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """Return roster ID -> team data."""

    teams = snapshot_data.get("teams")

    if not isinstance(teams, list):
        raise ReportError(
            "Snapshot data is missing teams"
        )

    lookup: dict[
        int,
        dict[str, Any],
    ] = {}

    for team in teams:
        if not isinstance(team, dict):
            raise ReportError(
                "Snapshot team must be an object"
            )

        roster_id = team.get(
            "roster_id"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise ReportError(
                "Snapshot team is missing "
                "a valid roster_id"
            )

        if roster_id in lookup:
            raise ReportError(
                f"Duplicate roster_id "
                f"{roster_id}"
            )

        lookup[roster_id] = team

    return lookup


def _special_starter_lines(
    team: dict[str, Any],
) -> list[str]:
    """Describe starters whose projections used special resolution."""

    starters = team.get(
        "starters",
        [],
    )

    if not isinstance(
        starters,
        list,
    ):
        raise ReportError(
            "Team starters must be a list"
        )

    lines: list[str] = []

    for starter in starters:
        if not isinstance(
            starter,
            dict,
        ):
            raise ReportError(
                "Starter record must be "
                "an object"
            )

        source = starter.get(
            "projection_source"
        )

        if source == "sleeper_pts_ppr":
            continue

        name = starter.get(
            "player_name",
            "Unknown Player",
        )

        points = _format_points(
            starter.get(
                "projected_points"
            )
        )

        if source == "empty_slot":
            lines.append(
                f"- **{team['manager_name']}**: "
                f"empty starter slot "
                f"(0.00 projected points)"
            )

            continue

        reason = starter.get(
            "projection_reason"
        )

        line = (
            f"- **{team['manager_name']}** — "
            f"{name}: {points} projected points "
            f"(`{source}`)"
        )

        if reason:
            line += f" — {reason}"

        lines.append(line)

    return lines


def generate_baseline_preview_markdown(
    snapshot: dict[str, Any],
) -> str:
    """Generate one league's Markdown preview from a baseline snapshot."""

    if snapshot.get("stage") != "baseline":
        raise ReportError(
            "Preview reports require "
            "a baseline snapshot"
        )

    season = snapshot.get(
        "season"
    )

    week = snapshot.get(
        "week"
    )

    data = snapshot.get(
        "data"
    )

    if not isinstance(data, dict):
        raise ReportError(
            "Snapshot is missing data"
        )

    league = data.get(
        "league"
    )

    if not isinstance(
        league,
        dict,
    ):
        raise ReportError(
            "Snapshot is missing league data"
        )

    league_name = league.get(
        "name",
        snapshot.get(
            "league_key",
            "League",
        ),
    )

    projection_method = data.get(
        "projection_method",
        {},
    )

    if not isinstance(
        projection_method,
        dict,
    ):
        raise ReportError(
            "projection_method must "
            "be an object"
        )

    point_field = projection_method.get(
        "point_field",
        "unknown",
    )

    exact_scoring = projection_method.get(
        "exact_league_scoring"
    )

    team_lookup = _team_lookup(
        data
    )

    matchups = data.get(
        "matchups"
    )

    if not isinstance(
        matchups,
        list,
    ):
        raise ReportError(
            "Snapshot is missing matchups"
        )

    lines = [
        f"# {league_name} — {season} Week {week} Preview",
        "",
        "## Baseline",
        "",
        (
            "This preview is generated from the immutable "
            "pre-kickoff baseline snapshot."
        ),
        "",
        f"- Projection field: `{point_field}`",
        (
            "- Exact custom-league scoring: "
            f"{'yes' if exact_scoring else 'no'}"
        ),
        "",
        "## Projected Matchups",
        "",
    ]

    for matchup in matchups:
        if not isinstance(
            matchup,
            dict,
        ):
            raise ReportError(
                "Matchup record must be "
                "an object"
            )

        matchup_id = matchup.get(
            "matchup_id"
        )

        roster_a_id = matchup.get(
            "roster_a_id"
        )

        roster_b_id = matchup.get(
            "roster_b_id"
        )

        team_a = team_lookup.get(
            roster_a_id
        )

        team_b = team_lookup.get(
            roster_b_id
        )

        if (
            team_a is None
            or team_b is None
        ):
            raise ReportError(
                f"Matchup {matchup_id} "
                "references unknown roster"
            )

        score_a = _format_points(
            team_a.get(
                "baseline_projection"
            )
        )

        score_b = _format_points(
            team_b.get(
                "baseline_projection"
            )
        )

        manager_a = team_a.get(
            "manager_name",
            f"Roster {roster_a_id}",
        )

        manager_b = team_b.get(
            "manager_name",
            f"Roster {roster_b_id}",
        )

        lines.extend(
            [
                (
                    f"### Matchup {matchup_id}: "
                    f"{manager_a} vs {manager_b}"
                ),
                "",
                (
                    f"- **{manager_a}:** "
                    f"{score_a}"
                ),
                (
                    f"- **{manager_b}:** "
                    f"{score_b}"
                ),
                "",
            ]
        )

    special_lines: list[str] = []

    for roster_id in sorted(
        team_lookup
    ):
        special_lines.extend(
            _special_starter_lines(
                team_lookup[
                    roster_id
                ]
            )
        )

    lines.extend(
        [
            "## Projection Notes",
            "",
        ]
    )

    if special_lines:
        lines.extend(
            special_lines
        )

    else:
        lines.append(
            "No special starter projection "
            "resolutions were required."
        )

    warnings = data.get(
        "warnings",
        [],
    )

    if not isinstance(
        warnings,
        list,
    ):
        raise ReportError(
            "Snapshot warnings must be a list"
        )

    lines.extend(
        [
            "",
            "## Lineup Warnings",
            "",
        ]
    )

    if warnings:
        for warning in warnings:
            lines.append(
                f"- {warning}"
            )
    else:
        lines.append(
            "No lineup warnings."
        )

    lines.extend(
        [
            "",
            "## Projection Method",
            "",
            (
                "Team totals use the projection values "
                "stored in the frozen baseline."
            ),
            "",
            (
                "The current MVP uses Sleeper's supplied "
                "`pts_ppr` projection rather than recalculating "
                "every projected statistic through the league's "
                "custom scoring settings."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def write_preview_report(
    snapshot_path: Path,
    report_path: Path,
) -> Path:
    """Read one baseline snapshot and create its Markdown preview."""

    snapshot = read_snapshot(
        snapshot_path
    )

    markdown = (
        generate_baseline_preview_markdown(
            snapshot
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