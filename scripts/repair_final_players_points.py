"""Backfill final snapshot players_points and rebuild final agent context.

This is an explicit repair utility for final snapshots created before
players_points preservation was implemented. It changes only the derived
per-player points map inside each final team record; stored team totals,
matchup results, timestamps, and all other snapshot fields are preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.agent_context import write_agent_context_file
from src.orchestration import DATA_ROOT, load_project_config
from src.sleeper import SleeperClient
from src.storage import build_snapshot_path, read_snapshot


def _normalized_players_points(
    record: dict[str, Any],
    roster_id: int,
) -> dict[str, float]:
    raw = record.get("players_points") or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"Sleeper roster {roster_id} players_points is not an object"
        )

    result: dict[str, float] = {}
    for raw_player_id, raw_points in raw.items():
        player_id = str(raw_player_id)
        if not player_id or player_id == "0":
            continue
        if isinstance(raw_points, bool) or not isinstance(
            raw_points, (int, float)
        ):
            raise ValueError(
                f"Sleeper roster {roster_id} players_points[{player_id}] "
                "is not numeric"
            )
        result[player_id] = float(raw_points)
    return result


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def repair_week(
    season: str,
    week: int,
    config: dict[str, Any],
    sleeper: SleeperClient,
    data_root: Path,
) -> list[Path]:
    originals: dict[Path, bytes] = {}
    repaired: list[Path] = []

    try:
        for league_key, league_config in config["leagues"].items():
            league_id = league_config["league_id"]
            path = build_snapshot_path(
                data_root=data_root,
                season=season,
                league_key=league_key,
                week=week,
                stage="final",
            )
            snapshot = read_snapshot(path)

            if snapshot.get("league_id") != league_id:
                raise ValueError(f"League ID mismatch in {path}")
            if snapshot.get("stage") != "final":
                raise ValueError(f"Not a final snapshot: {path}")

            data = snapshot.get("data")
            if not isinstance(data, dict):
                raise ValueError(f"Final snapshot has no data object: {path}")
            teams = data.get("teams")
            if not isinstance(teams, list):
                raise ValueError(f"Final snapshot has no teams list: {path}")

            live_matchups = sleeper.get_matchups(league_id, week=week)
            by_roster: dict[int, dict[str, Any]] = {}
            for record in live_matchups:
                roster_id = record.get("roster_id")
                if not isinstance(roster_id, int):
                    raise ValueError("Sleeper matchup missing integer roster_id")
                by_roster[roster_id] = record

            stored_ids = {
                team.get("roster_id")
                for team in teams
                if isinstance(team, dict)
            }
            if stored_ids != set(by_roster):
                raise ValueError(
                    f"Roster set mismatch for {league_key} week {week}: "
                    f"stored={sorted(stored_ids)} live={sorted(by_roster)}"
                )

            originals[path] = path.read_bytes()

            changed = False
            for team in teams:
                if not isinstance(team, dict):
                    raise ValueError(f"Invalid team object in {path}")
                roster_id = team.get("roster_id")
                if not isinstance(roster_id, int):
                    raise ValueError(f"Invalid roster_id in {path}")

                repaired_points = _normalized_players_points(
                    by_roster[roster_id], roster_id
                )
                if team.get("players_points") != repaired_points:
                    team["players_points"] = repaired_points
                    changed = True

            if changed:
                _write_atomic(path, snapshot)
                repaired.append(path)
                print(f"REPAIRED: {path}")
            else:
                print(f"UNCHANGED: {path}")

        context_path = write_agent_context_file(
            data_root=data_root,
            project_config=config,
            season=season,
            week=week,
            stage="final",
        )
        print(f"WROTE FINAL AGENT CONTEXT: {context_path}")

    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        raise

    return repaired


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--weeks",
        nargs="+",
        type=int,
        required=True,
        help="Completed weeks to repair, for example: --weeks 1 2",
    )
    args = parser.parse_args()

    config = load_project_config()
    season = config.get("season")
    if not isinstance(season, str) or not season:
        raise ValueError("config.json is missing a valid season")

    sleeper = SleeperClient()
    for week in args.weeks:
        if week < 1:
            raise ValueError("week must be at least 1")
        print(f"\n=== REPAIRING {season} WEEK {week} FINAL ACTUALS ===")
        repair_week(
            season=season,
            week=week,
            config=config,
            sleeper=sleeper,
            data_root=DATA_ROOT,
        )

    print("\nRepair complete.")
    print("Run: python fantasy.py final --week <latest_completed_week>")
    print("to refresh donuts, season analytics, and power rankings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
