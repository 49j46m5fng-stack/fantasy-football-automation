"""Inspect live Sleeper matchup response shapes without writing data."""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.sleeper import SleeperClient


SEASON = "2026"
WEEK = 1
TIMEZONE = ZoneInfo("America/Chicago")

SCHEDULED_PROBE_DATE = date(
    2026,
    9,
    10,
)

LEAGUES = {
    "GOATs": "1400610465024839680",
    "DOATs": "1400610568489947136",
}

DOCUMENTED_MATCHUP_KEYS = {
    "starters",
    "roster_id",
    "players",
    "matchup_id",
    "points",
    "custom_points",
}


def print_value_summary(
    key: str,
    value: object,
) -> None:
    """Print a compact summary of one undocumented value."""

    if isinstance(value, dict):
        print(
            f"    {key}: dict "
            f"({len(value)} entries)"
        )

        for item_key, item_value in list(
            value.items()
        )[:12]:
            print(
                f"      {item_key}: "
                f"{item_value!r}"
            )

        return

    if isinstance(value, list):
        print(
            f"    {key}: list "
            f"({len(value)} entries)"
        )

        print(
            f"      sample: "
            f"{value[:12]!r}"
        )

        return

    print(
        f"    {key}: {value!r}"
    )


def main() -> int:
    """Inspect raw Week 1 matchup records."""

    now = datetime.now(
        TIMEZONE
    )

    event_name = os.environ.get(
        "GITHUB_EVENT_NAME"
    )

    if (
        event_name == "schedule"
        and now.date()
        != SCHEDULED_PROBE_DATE
    ):
        print(
            "NO-OP: scheduled probe is only "
            "for September 10, 2026."
        )

        return 0

    print("=" * 72)
    print("WEEK 1 LIVE MATCHUP SHAPE PROBE")
    print("=" * 72)
    print(
        f"Captured: "
        f"{now.isoformat()}"
    )

    client = SleeperClient()

    for league_name, league_id in (
        LEAGUES.items()
    ):
        records = client.get_matchups(
            league_id,
            week=WEEK,
        )

        all_keys = sorted(
            {
                key
                for record in records
                for key in record
            }
        )

        undocumented = sorted(
            set(all_keys)
            - DOCUMENTED_MATCHUP_KEYS
        )

        print()
        print("=" * 72)
        print(league_name)
        print("=" * 72)

        print(
            f"Records: "
            f"{len(records)}"
        )

        print(
            f"All keys: "
            f"{all_keys}"
        )

        print(
            f"Undocumented keys: "
            f"{undocumented}"
        )

        for record in records:
            roster_id = record.get(
                "roster_id"
            )

            print()
            print(
                f"Roster {roster_id}"
            )

            print(
                f"  points: "
                f"{record.get('points')!r}"
            )

            print(
                f"  custom_points: "
                f"{record.get('custom_points')!r}"
            )

            for key in undocumented:
                if key not in record:
                    continue

                print_value_summary(
                    key,
                    record[key],
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )