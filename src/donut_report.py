"""Markdown reporting for the cross-league donut survival pool.

Report formatting is deliberately separated from donut analytics. This
module performs no calculations and no external requests. It renders
already-derived DonutPoolState values.
"""

from pathlib import Path

from src.donuts import (
    DonutPoolState,
    DonutWeekResult,
    STATUS_ASSIGNED,
    STATUS_BLOCKED,
    STATUS_NO_ELIGIBLE_SCORES,
    STATUS_UNRESOLVED_TIE,
)


def _points(
    value: float | None,
) -> str:
    """Format an optional fantasy score."""

    if value is None:
        return "unresolved"

    return f"{value:.2f}"


def _margin(
    value: float | None,
) -> str:
    """Format an optional margin."""

    if value is None:
        return "—"

    return f"{value:.2f}"


def _week(
    value: int | None,
) -> str:
    """Format an optional week number."""

    if value is None:
        return "—"

    return str(value)


def _status_label(
    result: DonutWeekResult,
) -> str:
    """Return a human-readable weekly status."""

    if result.status == STATUS_ASSIGNED:
        return "Assigned"

    if result.status == STATUS_UNRESOLVED_TIE:
        return "Unresolved tie"

    if result.status == STATUS_NO_ELIGIBLE_SCORES:
        return "No eligible scores"

    if result.status == STATUS_BLOCKED:
        return "Not evaluated"

    return result.status


def generate_donut_report_markdown(
    state: DonutPoolState,
) -> str:
    """Render the donut survival pool as Markdown."""

    lines: list[str] = [
        f"# Donut Survival Pool — {state.season}",
        "",
        (
            f"Through completed week {state.through_week} "
            f"of {state.total_weeks}."
        ),
        "",
        (
            f"{len(state.entrants)} entrants. "
            f"{len(state.eliminated)} on the hook. "
            f"{len(state.survivors)} still unDOUGHfeated."
        ),
        "",
    ]

    if state.blocked_week is not None:
        lines.extend(
            [
                (
                    f"**Pool blocked.** Week {state.blocked_week} "
                    "ended in a scoring tie that has not been ruled "
                    "on. Later weeks are not evaluated until a "
                    "commissioner override is committed."
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## On the Hook",
            "",
        ]
    )

    if state.next_delivery is not None:
        assignment = state.next_delivery

        lines.extend(
            [
                (
                    f"**{assignment.manager_name}** "
                    f"({assignment.league_key.upper()}) brings "
                    f"donuts in week {assignment.delivery_week}."
                ),
                "",
                (
                    f"Week {assignment.scoring_week} low score: "
                    f"{_points(assignment.points)} points, "
                    f"{_margin(assignment.margin_to_next_lowest)} "
                    "behind the next-lowest eligible team."
                ),
                "",
            ]
        )

        if assignment.tie_broken:
            lines.extend(
                [
                    (
                        "This assignment came from a tie resolved by "
                        f"`{assignment.resolution}`."
                    ),
                    "",
                ]
            )

            if assignment.reason:
                lines.extend(
                    [
                        f"> {assignment.reason}",
                        "",
                    ]
                )

    else:
        lines.extend(
            [
                "No donut duty has been assigned yet.",
                "",
            ]
        )

    if state.undoughfeated is not None:
        survivor = state.undoughfeated

        lines.extend(
            [
                "## unDOUGHfeated Champion",
                "",
                (
                    f"**{survivor.manager_name}** "
                    f"({survivor.league_key.upper()}) survived all "
                    f"{survivor.weeks_survived} weeks without ever "
                    "posting the lowest score."
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Donut Ledger",
            "",
            (
                "| Week | Delivers | Manager | League | Points | "
                "Margin | Resolution |"
            ),
            (
                "| ---: | ---: | --- | --- | ---: | ---: | --- |"
            ),
        ]
    )

    if state.eliminated:
        for assignment in state.eliminated:
            lines.append(
                f"| {assignment.scoring_week} "
                f"| {assignment.delivery_week} "
                f"| {assignment.manager_name} "
                f"| {assignment.league_key.upper()} "
                f"| {_points(assignment.points)} "
                f"| {_margin(assignment.margin_to_next_lowest)} "
                f"| {assignment.resolution} |"
            )

    else:
        lines.append(
            "| — | — | No assignments yet | — | — | — | — |"
        )

    lines.extend(
        [
            "",
            "## Still Alive",
            "",
            (
                "| Manager | League | Weeks Survived | "
                "Closest Call | Week | Season Low |"
            ),
            (
                "| --- | --- | ---: | ---: | ---: | ---: |"
            ),
        ]
    )

    if state.survivors:
        for survivor in state.survivors:
            lines.append(
                f"| {survivor.manager_name} "
                f"| {survivor.league_key.upper()} "
                f"| {survivor.weeks_survived} "
                f"| {_margin(survivor.closest_call_margin)} "
                f"| {_week(survivor.closest_call_week)} "
                f"| {_points(survivor.lowest_weekly_points)} |"
            )

    else:
        lines.append(
            "| — | — | — | — | — | — |"
        )

    lines.extend(
        [
            "",
            (
                "Closest call is the smallest number of points a "
                "manager finished above that week's donut-winning "
                "score."
            ),
            "",
            "## Weekly Detail",
            "",
            (
                "| Week | Status | Low Score | Eligible Before | "
                "Eligible After |"
            ),
            "| ---: | --- | ---: | ---: | ---: |",
        ]
    )

    for result in state.results:
        lines.append(
            f"| {result.scoring_week} "
            f"| {_status_label(result)} "
            f"| {_points(result.lowest_points)} "
            f"| {len(result.eligible_before)} "
            f"| {len(result.eligible_after)} |"
        )

    lines.extend(
        [
            "",
            "## Warnings",
            "",
        ]
    )

    if state.warnings:
        for warning in state.warnings:
            lines.append(f"- {warning}")

    else:
        lines.append("No donut-pool warnings.")

    lines.extend(
        [
            "",
            "## Method",
            "",
            (
                "Donut duty is assigned to the lowest completed "
                "score across every pool league combined, using each "
                "team's effective final points from the immutable "
                "final snapshot."
            ),
            "",
            (
                "A manager may only be assigned donut duty once. "
                "Assigned managers are removed from the eligible "
                "pool for all later weeks."
            ),
            "",
            (
                "A missing or unresolved weekly score is never "
                "treated as zero and can never win the donut."
            ),
            "",
            (
                f"The active tie policy is `{state.tie_policy}`."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def write_donut_report(
    state: DonutPoolState,
    report_path: Path,
) -> Path:
    """Write the donut survival pool report to disk."""

    markdown = generate_donut_report_markdown(
        state
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
