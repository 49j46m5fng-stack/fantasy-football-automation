"""Audit current Sleeper league scoring configuration.

This is a diagnostic, read-only script.

It fetches the current league objects for all configured leagues and prints:

- roster positions
- every active scoring setting
- differences between league scoring configurations
- scoring categories that deserve special attention before implementing
  exact player-level fantasy scoring

Nothing is written to disk.
"""

import json
from pathlib import Path
from typing import Any

from src.sleeper import SleeperClient


CONFIG_PATH = Path(
    "config.json"
)


# These names are not treated as a complete scoring engine.
# They are grouped only to make the audit output easier to read.
SCORING_GROUPS = {
    "passing": (
        "pass_",
        "cmp",
        "inc",
    ),
    "rushing": (
        "rush_",
    ),
    "receiving": (
        "rec",
        "rec_",
    ),
    "first_downs": (
        "fd_",
        "pass_fd",
        "rush_fd",
        "rec_fd",
    ),
    "returns": (
        "ret_",
        "kr_",
        "pr_",
    ),
    "fumbles": (
        "fum",
    ),
    "kicking": (
        "fg",
        "xpm",
        "fgm",
        "fgmiss",
    ),
    "defense": (
        "def_",
        "sack",
        "int",
        "safe",
        "blk",
        "pts_allow",
        "yds_allow",
    ),
    "bonuses": (
        "bonus",
    ),
    "two_point": (
        "2pt",
    ),
}


def load_config() -> dict[str, Any]:
    """Load project configuration."""

    try:
        with CONFIG_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Could not read config.json"
        ) from exc

    if not isinstance(
        config,
        dict,
    ):
        raise RuntimeError(
            "config.json must contain "
            "a JSON object"
        )

    leagues = config.get(
        "leagues"
    )

    if not isinstance(
        leagues,
        dict,
    ):
        raise RuntimeError(
            "config.json is missing leagues"
        )

    return config


def normalize_scoring_settings(
    value: Any,
) -> dict[str, float]:
    """Normalize Sleeper scoring settings into numeric values."""

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "Sleeper scoring_settings "
            "must be an object"
        )

    result: dict[
        str,
        float,
    ] = {}

    for key, raw_value in (
        value.items()
    ):
        if (
            isinstance(
                raw_value,
                bool,
            )
            or not isinstance(
                raw_value,
                (int, float),
            )
        ):
            raise RuntimeError(
                f"Scoring setting {key!r} "
                "must be numeric"
            )

        result[
            str(
                key
            )
        ] = float(
            raw_value
        )

    return result


def active_scoring_settings(
    settings: dict[str, float],
) -> dict[str, float]:
    """Return only non-zero scoring settings."""

    return {
        key: value
        for key, value
        in settings.items()
        if abs(
            value
        ) > 1e-12
    }


def classify_setting(
    key: str,
) -> str:
    """Place one Sleeper scoring key into a broad audit category."""

    lower_key = (
        key.lower()
    )

    for group, prefixes in (
        SCORING_GROUPS.items()
    ):
        for prefix in prefixes:
            if (
                lower_key == prefix
                or lower_key.startswith(
                    prefix
                )
            ):
                return group

    return "other"


def grouped_settings(
    settings: dict[str, float],
) -> dict[
    str,
    dict[str, float],
]:
    """Group active settings for human-readable inspection."""

    groups: dict[
        str,
        dict[str, float],
    ] = {}

    for key, value in sorted(
        settings.items()
    ):
        group = classify_setting(
            key
        )

        groups.setdefault(
            group,
            {},
        )[
            key
        ] = value

    return groups


def scoring_differences(
    left: dict[str, float],
    right: dict[str, float],
) -> dict[
    str,
    tuple[
        float,
        float,
    ],
]:
    """Return settings whose values differ between two leagues."""

    keys = (
        set(
            left
        )
        | set(
            right
        )
    )

    differences: dict[
        str,
        tuple[
            float,
            float,
        ],
    ] = {}

    for key in sorted(
        keys
    ):
        left_value = left.get(
            key,
            0.0,
        )

        right_value = right.get(
            key,
            0.0,
        )

        if abs(
            left_value
            - right_value
        ) > 1e-12:
            differences[
                key
            ] = (
                left_value,
                right_value,
            )

    return differences


def _print_setting_groups(
    settings: dict[str, float],
) -> None:
    """Print active scoring settings by broad category."""

    groups = grouped_settings(
        settings
    )

    preferred_order = [
        "passing",
        "rushing",
        "receiving",
        "first_downs",
        "two_point",
        "fumbles",
        "returns",
        "kicking",
        "defense",
        "bonuses",
        "other",
    ]

    for group in preferred_order:
        values = groups.get(
            group
        )

        if not values:
            continue

        print()
        print(
            f"[{group}]"
        )

        for key, value in (
            values.items()
        ):
            print(
                f"  {key:<32} "
                f"{value:g}"
            )


def _special_attention(
    settings: dict[str, float],
) -> list[str]:
    """Identify settings that may make generic pts_ppr insufficient."""

    notes: list[
        str
    ] = []

    first_down_keys = [
        key
        for key in settings
        if (
            "fd" in key.lower()
            or "first_down"
            in key.lower()
        )
        and abs(
            settings[key]
        ) > 1e-12
    ]

    bonus_keys = [
        key
        for key in settings
        if "bonus" in key.lower()
        and abs(
            settings[key]
        ) > 1e-12
    ]

    return_keys = [
        key
        for key in settings
        if (
            "ret_" in key.lower()
            or "kr_" in key.lower()
            or "pr_" in key.lower()
        )
        and abs(
            settings[key]
        ) > 1e-12
    ]

    unusual_reception_keys = [
        key
        for key in settings
        if key.startswith(
            "rec_"
        )
        and key not in {
            "rec_yd",
            "rec_td",
            "rec_fd",
            "rec_2pt",
        }
        and abs(
            settings[key]
        ) > 1e-12
    ]

    if first_down_keys:
        notes.append(
            "Points-per-first-down scoring "
            "is active: "
            + ", ".join(
                sorted(
                    first_down_keys
                )
            )
        )

    if bonus_keys:
        notes.append(
            "Bonus scoring is active: "
            + ", ".join(
                sorted(
                    bonus_keys
                )
            )
        )

    if return_keys:
        notes.append(
            "Return scoring is active: "
            + ", ".join(
                sorted(
                    return_keys
                )
            )
        )

    if unusual_reception_keys:
        notes.append(
            "Additional reception-related "
            "scoring is active: "
            + ", ".join(
                sorted(
                    unusual_reception_keys
                )
            )
        )

    return notes


def main() -> int:
    """Run the non-writing scoring-settings audit."""

    config = load_config()

    sleeper = SleeperClient()

    leagues = config[
        "leagues"
    ]

    audited: dict[
        str,
        dict[str, Any],
    ] = {}

    print("=" * 78)
    print(
        "CURRENT LEAGUE SCORING AUDIT"
    )
    print("=" * 78)

    for (
        league_key,
        league_config,
    ) in leagues.items():
        if not isinstance(
            league_config,
            dict,
        ):
            raise RuntimeError(
                f"League config for "
                f"{league_key} is invalid"
            )

        league_id = (
            league_config.get(
                "league_id"
            )
        )

        if not isinstance(
            league_id,
            str,
        ):
            raise RuntimeError(
                f"{league_key} does not "
                "have a valid league_id"
            )

        league = sleeper.get_league(
            league_id
        )

        settings = (
            normalize_scoring_settings(
                league.get(
                    "scoring_settings"
                )
            )
        )

        active = (
            active_scoring_settings(
                settings
            )
        )

        roster_positions = (
            league.get(
                "roster_positions"
            )
        )

        audited[
            league_key
        ] = {
            "name": (
                league_config.get(
                    "name",
                    league_key,
                )
            ),
            "league_id": (
                league_id
            ),
            "settings": (
                settings
            ),
            "active": (
                active
            ),
            "roster_positions": (
                roster_positions
            ),
        }

        print()
        print("=" * 78)
        print(
            str(
                audited[
                    league_key
                ][
                    "name"
                ]
            ).upper()
        )
        print("=" * 78)

        print(
            f"League ID: "
            f"{league_id}"
        )

        print(
            f"Season:    "
            f"{league.get('season')}"
        )

        print(
            f"Teams:     "
            f"{league.get('total_rosters')}"
        )

        print()
        print(
            "Roster positions:"
        )

        if isinstance(
            roster_positions,
            list,
        ):
            print(
                "  "
                + ", ".join(
                    str(
                        value
                    )
                    for value
                    in roster_positions
                )
            )

        else:
            print(
                "  <not supplied>"
            )

        print()
        print(
            f"Scoring keys returned: "
            f"{len(settings)}"
        )

        print(
            f"Active non-zero keys:  "
            f"{len(active)}"
        )

        _print_setting_groups(
            active
        )

        notes = (
            _special_attention(
                active
            )
        )

        print()
        print(
            "Exact-scoring audit notes:"
        )

        if notes:
            for note in notes:
                print(
                    f"  - {note}"
                )

        else:
            print(
                "  - No first-down, bonus, "
                "return, or unusual reception "
                "scoring was detected by this probe."
            )

    league_keys = list(
        audited
    )

    print()
    print("=" * 78)
    print(
        "CROSS-LEAGUE COMPARISON"
    )
    print("=" * 78)

    if len(
        league_keys
    ) < 2:
        print(
            "Fewer than two leagues "
            "were configured."
        )

    else:
        reference_key = (
            league_keys[0]
        )

        reference = audited[
            reference_key
        ]

        for other_key in (
            league_keys[1:]
        ):
            other = audited[
                other_key
            ]

            differences = (
                scoring_differences(
                    reference[
                        "settings"
                    ],
                    other[
                        "settings"
                    ],
                )
            )

            print()
            print(
                f"{reference['name']} "
                f"vs {other['name']}:"
            )

            if not differences:
                print(
                    "  IDENTICAL scoring_settings"
                )

            else:
                print(
                    f"  {len(differences)} "
                    "scoring differences:"
                )

                for (
                    key,
                    values,
                ) in differences.items():
                    left_value, right_value = (
                        values
                    )

                    print(
                        f"  {key:<32} "
                        f"{left_value:g} "
                        f"vs {right_value:g}"
                    )

            if (
                reference[
                    "roster_positions"
                ]
                == other[
                    "roster_positions"
                ]
            ):
                print(
                    "  IDENTICAL roster positions"
                )

            else:
                print(
                    "  DIFFERENT roster positions"
                )

    print()
    print("=" * 78)
    print(
        "INTERPRETATION RULE"
    )
    print("=" * 78)

    print(
        "This probe does NOT declare "
        "pts_ppr equivalent to league scoring."
    )

    print(
        "It exposes the actual Sleeper "
        "scoring configuration so the next "
        "phase can either:"
    )

    print(
        "  A) verify generic pts_ppr is sufficient, or"
    )

    print(
        "  B) build exact fantasy points from "
        "raw player statistics."
    )

    print()
    print(
        "PROBE COMPLETE — "
        "nothing was written."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )