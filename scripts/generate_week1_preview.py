"""Generate Week 1 Markdown previews from frozen baseline snapshots."""

from pathlib import Path

from src.reports import write_preview_report


SEASON = "2026"
WEEK = 1

LEAGUES = (
    "goats",
    "doats",
)


def main() -> int:
    for league_key in LEAGUES:
        snapshot_path = Path(
            f"data/{SEASON}/"
            f"{league_key}/"
            f"week_{WEEK:02d}_baseline.json"
        )

        report_path = Path(
            f"reports/{SEASON}/"
            f"{league_key}_"
            f"week_{WEEK:02d}_preview.md"
        )

        if not snapshot_path.exists():
            raise SystemExit(
                "Cannot generate official preview. "
                f"Frozen baseline does not exist: "
                f"{snapshot_path}"
            )

        result = write_preview_report(
            snapshot_path,
            report_path,
        )

        print(
            f"CREATED: {result}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )