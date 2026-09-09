"""Legal optimal-lineup and lineup-efficiency analytics."""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.actuals import (
    PlayerActual,
)


class LineupAnalyticsError(ValueError):
    """Raised when lineup analytics cannot be calculated safely."""


NON_STARTER_SLOTS = {
    "BN",
    "IR",
}

SUPPORTED_STARTER_SLOTS = {
    "QB",
    "RB",
    "WR",
    "TE",
    "FLEX",
    "K",
    "DEF",
}


@dataclass(frozen=True)
class LineupSlot:
    """One unique starting-lineup slot."""

    index: int
    slot_type: str
    label: str


@dataclass(frozen=True)
class LineupPlayer:
    """One resolved final-roster player."""

    player_id: str
    player_name: str | None
    position: str
    exact_points: float


@dataclass(frozen=True)
class LineupAssignment:
    """One player assignment to one starting slot."""

    slot_index: int
    slot_type: str
    slot_label: str

    player_id: str | None
    player_name: str | None
    position: str | None

    exact_points: float | None
    empty: bool


@dataclass(frozen=True)
class TeamLineupEfficiency:
    """Exact lineup-efficiency result for one roster."""

    roster_id: int
    manager_name: str

    actual_lineup_complete: bool
    optimization_complete: bool

    actual_lineup_points: float | None
    optimal_lineup_points: float | None

    lineup_efficiency_pct: float | None
    points_left_on_bench: float | None
    bench_points: float | None

    sleeper_final_points: float | None
    score_reconciliation_delta: float | None

    actual_lineup: tuple[
        LineupAssignment,
        ...,
    ]

    optimal_lineup: tuple[
        LineupAssignment,
        ...,
    ]

    should_start: tuple[
        LineupPlayer,
        ...,
    ]

    should_bench: tuple[
        LineupPlayer,
        ...,
    ]

    unresolved_player_ids: tuple[
        str,
        ...,
    ]


@dataclass(frozen=True)
class WeekLineupEfficiency:
    """Lineup-efficiency analytics for one league and fantasy week."""

    season: str
    week: int
    league_key: str

    teams: tuple[
        TeamLineupEfficiency,
        ...,
    ]


def _optional_number(
    value: Any,
    description: str,
) -> float | None:
    """Normalize an optional numeric value."""

    if value is None:
        return None

    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            (int, float),
        )
    ):
        raise LineupAnalyticsError(
            f"{description} must be numeric or null"
        )

    return float(
        value
    )


def _validate_final_identity(
    final_snapshot: dict[str, Any],
) -> tuple[
    str,
    int,
    str,
    dict[str, Any],
]:
    """Validate final snapshot identity and return its data."""

    if (
        final_snapshot.get(
            "stage"
        )
        != "final"
    ):
        raise LineupAnalyticsError(
            "Lineup efficiency requires "
            "a final snapshot"
        )

    season = final_snapshot.get(
        "season"
    )

    week = final_snapshot.get(
        "week"
    )

    league_key = final_snapshot.get(
        "league_key"
    )

    data = final_snapshot.get(
        "data"
    )

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing season"
        )

    if not isinstance(
        week,
        int,
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing week"
        )

    if (
        not isinstance(
            league_key,
            str,
        )
        or not league_key
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing league_key"
        )

    if not isinstance(
        data,
        dict,
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing data"
        )

    return (
        season,
        week,
        league_key,
        data,
    )


def _starting_slots(
    data: dict[str, Any],
) -> tuple[
    LineupSlot,
    ...,
]:
    """Build unique starting slots from stored league configuration."""

    league = data.get(
        "league"
    )

    if not isinstance(
        league,
        dict,
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing league data"
        )

    roster_positions = (
        league.get(
            "roster_positions"
        )
    )

    if not isinstance(
        roster_positions,
        list,
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing "
            "roster_positions"
        )

    starter_types = [
        str(
            position
        )
        for position
        in roster_positions
        if str(
            position
        )
        not in NON_STARTER_SLOTS
    ]

    if not starter_types:
        raise LineupAnalyticsError(
            "No starting lineup slots found"
        )

    unsupported = [
        slot
        for slot
        in starter_types
        if slot
        not in SUPPORTED_STARTER_SLOTS
    ]

    if unsupported:
        raise LineupAnalyticsError(
            "Unsupported starting lineup slots: "
            f"{unsupported}"
        )

    totals = Counter(
        starter_types
    )

    seen: Counter[
        str
    ] = Counter()

    slots: list[
        LineupSlot
    ] = []

    for index, slot_type in (
        enumerate(
            starter_types,
            start=1,
        )
    ):
        seen[
            slot_type
        ] += 1

        if (
            totals[
                slot_type
            ]
            == 1
        ):
            label = slot_type

        else:
            label = (
                f"{slot_type}"
                f"{seen[slot_type]}"
            )

        slots.append(
            LineupSlot(
                index=index,
                slot_type=(
                    slot_type
                ),
                label=label,
            )
        )

    return tuple(
        slots
    )


def _normalize_position(
    player_id: str,
    record: dict[str, Any],
) -> str | None:
    """Resolve final-roster fantasy position."""

    position = record.get(
        "position"
    )

    if (
        isinstance(
            position,
            str,
        )
        and position
    ):
        return position

    # Sleeper defense IDs are team abbreviations such as SEA.
    if (
        player_id.isalpha()
        and 2
        <= len(
            player_id
        )
        <= 4
    ):
        return "DEF"

    return None


def _eligible(
    position: str,
    slot_type: str,
) -> bool:
    """Return whether a player position can fill a starting slot."""

    if position == slot_type:
        return True

    if (
        slot_type == "FLEX"
        and position
        in {
            "RB",
            "FB",
            "WR",
            "TE",
        }
    ):
        return True

    # Sleeper may classify traditional fullbacks separately while their
    # fantasy eligibility is effectively running back.
    if (
        slot_type == "RB"
        and position == "FB"
    ):
        return True

    return False


def _validate_actual_period(
    actual: PlayerActual,
    season: str,
    week: int,
) -> None:
    """Require a player actual to belong to the analyzed week."""

    if (
        actual.season
        != season
        or actual.week
        != week
    ):
        raise LineupAnalyticsError(
            f"Actual score for player "
            f"{actual.player_id} belongs "
            "to the wrong season/week"
        )


def _optimize_lineup(
    slots: tuple[
        LineupSlot,
        ...,
    ],
    players: tuple[
        LineupPlayer,
        ...,
    ],
) -> tuple[
    float,
    tuple[
        LineupAssignment,
        ...,
    ],
] | None:
    """Find the highest-scoring legal lineup using dynamic programming."""

    ordered_players = tuple(
        sorted(
            players,
            key=lambda player: (
                player.player_id
            ),
        )
    )

    @lru_cache(
        maxsize=None
    )
    def solve(
        slot_index: int,
        used_mask: int,
    ) -> tuple[
        float,
        tuple[
            int,
            ...,
        ],
    ] | None:
        if (
            slot_index
            == len(
                slots
            )
        ):
            return (
                0.0,
                (),
            )

        slot = slots[
            slot_index
        ]

        best: tuple[
            float,
            tuple[
                int,
                ...,
            ],
        ] | None = None

        for player_index, player in (
            enumerate(
                ordered_players
            )
        ):
            bit = (
                1
                << player_index
            )

            if (
                used_mask
                & bit
            ):
                continue

            if not _eligible(
                player.position,
                slot.slot_type,
            ):
                continue

            remainder = solve(
                slot_index + 1,
                used_mask | bit,
            )

            if remainder is None:
                continue

            total = (
                player.exact_points
                + remainder[0]
            )

            chosen = (
                player_index,
            ) + remainder[1]

            if (
                best is None
                or total
                > best[0]
                + 1e-9
            ):
                best = (
                    total,
                    chosen,
                )

        return best

    result = solve(
        0,
        0,
    )

    if result is None:
        return None

    total, selected_indices = (
        result
    )

    assignments: list[
        LineupAssignment
    ] = []

    for slot, player_index in zip(
        slots,
        selected_indices,
        strict=True,
    ):
        player = (
            ordered_players[
                player_index
            ]
        )

        assignments.append(
            LineupAssignment(
                slot_index=(
                    slot.index
                ),
                slot_type=(
                    slot.slot_type
                ),
                slot_label=(
                    slot.label
                ),
                player_id=(
                    player.player_id
                ),
                player_name=(
                    player.player_name
                ),
                position=(
                    player.position
                ),
                exact_points=(
                    player.exact_points
                ),
                empty=False,
            )
        )

    return (
        round(
            total,
            8,
        ),
        tuple(
            assignments
        ),
    )


def analyze_final_lineup_efficiency(
    final_snapshot: dict[str, Any],
    actuals: dict[
        str,
        PlayerActual,
    ],
) -> WeekLineupEfficiency:
    """Calculate legal optimal-lineup analytics from a final snapshot."""

    (
        season,
        week,
        league_key,
        data,
    ) = _validate_final_identity(
        final_snapshot
    )

    slots = _starting_slots(
        data
    )

    teams = data.get(
        "teams"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise LineupAnalyticsError(
            "Final snapshot is missing teams"
        )

    team_results: list[
        TeamLineupEfficiency
    ] = []

    for team in teams:
        if not isinstance(
            team,
            dict,
        ):
            raise LineupAnalyticsError(
                "Final team must be an object"
            )

        roster_id = team.get(
            "roster_id"
        )

        manager_name = team.get(
            "manager_name"
        )

        if not isinstance(
            roster_id,
            int,
        ):
            raise LineupAnalyticsError(
                "Final team is missing roster_id"
            )

        if not isinstance(
            manager_name,
            str,
        ):
            raise LineupAnalyticsError(
                f"Roster {roster_id} is "
                "missing manager_name"
            )

        rostered_players = (
            team.get(
                "rostered_players"
            )
        )

        starters = team.get(
            "starters"
        )

        if not isinstance(
            rostered_players,
            list,
        ):
            raise LineupAnalyticsError(
                f"Roster {roster_id} "
                "rostered_players must be a list"
            )

        if not isinstance(
            starters,
            list,
        ):
            raise LineupAnalyticsError(
                f"Roster {roster_id} "
                "starters must be a list"
            )

        if (
            len(
                starters
            )
            != len(
                slots
            )
        ):
            raise LineupAnalyticsError(
                f"Roster {roster_id} has "
                f"{len(starters)} final starter "
                f"records but {len(slots)} "
                "starting slots"
            )

        roster_lookup: dict[
            str,
            dict[str, Any],
        ] = {}

        for record in (
            rostered_players
        ):
            if not isinstance(
                record,
                dict,
            ):
                raise LineupAnalyticsError(
                    "Rostered player must be an object"
                )

            raw_player_id = (
                record.get(
                    "player_id"
                )
            )

            if raw_player_id is None:
                continue

            player_id = str(
                raw_player_id
            )

            if (
                not player_id
                or player_id == "0"
            ):
                continue

            if (
                player_id
                in roster_lookup
            ):
                raise LineupAnalyticsError(
                    f"Roster {roster_id} contains "
                    f"duplicate player {player_id}"
                )

            roster_lookup[
                player_id
            ] = record

        resolved_players: list[
            LineupPlayer
        ] = []

        resolved_player_lookup: dict[
            str,
            LineupPlayer,
        ] = {}

        unresolved_for_optimization: set[
            str
        ] = set()

        for (
            player_id,
            record,
        ) in roster_lookup.items():
            position = (
                _normalize_position(
                    player_id,
                    record,
                )
            )

            if position is None:
                unresolved_for_optimization.add(
                    player_id
                )
                continue

            could_start = any(
                _eligible(
                    position,
                    slot.slot_type,
                )
                for slot
                in slots
            )

            if not could_start:
                continue

            actual = actuals.get(
                player_id
            )

            if actual is None:
                unresolved_for_optimization.add(
                    player_id
                )
                continue

            _validate_actual_period(
                actual,
                season,
                week,
            )

            player = LineupPlayer(
                player_id=player_id,
                player_name=(
                    record.get(
                        "player_name"
                    )
                ),
                position=position,
                exact_points=(
                    actual.exact_points
                ),
            )

            resolved_players.append(
                player
            )

            resolved_player_lookup[
                player_id
            ] = player

        actual_assignments: list[
            LineupAssignment
        ] = []

        actual_player_ids: set[
            str
        ] = set()

        actual_complete = True
        actual_total = 0.0

        for slot, starter in zip(
            slots,
            starters,
            strict=True,
        ):
            if not isinstance(
                starter,
                dict,
            ):
                raise LineupAnalyticsError(
                    "Starter must be an object"
                )

            raw_player_id = (
                starter.get(
                    "player_id"
                )
            )

            if (
                raw_player_id is None
                or not str(
                    raw_player_id
                )
                or str(
                    raw_player_id
                )
                == "0"
            ):
                # An intentionally empty lineup slot has a known score
                # of zero. This is different from a missing player stat.
                actual_assignments.append(
                    LineupAssignment(
                        slot_index=(
                            slot.index
                        ),
                        slot_type=(
                            slot.slot_type
                        ),
                        slot_label=(
                            slot.label
                        ),
                        player_id=None,
                        player_name=(
                            "EMPTY SLOT"
                        ),
                        position=None,
                        exact_points=0.0,
                        empty=True,
                    )
                )

                continue

            player_id = str(
                raw_player_id
            )

            if (
                player_id
                in actual_player_ids
            ):
                raise LineupAnalyticsError(
                    f"Roster {roster_id} has "
                    f"duplicate starter {player_id}"
                )

            actual_player_ids.add(
                player_id
            )

            roster_record = (
                roster_lookup.get(
                    player_id
                )
            )

            if roster_record is None:
                raise LineupAnalyticsError(
                    f"Roster {roster_id} starter "
                    f"{player_id} is not present "
                    "in final rostered_players"
                )

            position = (
                _normalize_position(
                    player_id,
                    roster_record,
                )
            )

            if (
                position is not None
                and not _eligible(
                    position,
                    slot.slot_type,
                )
            ):
                raise LineupAnalyticsError(
                    f"Roster {roster_id} player "
                    f"{player_id} is not eligible "
                    f"for {slot.slot_type}"
                )

            actual = actuals.get(
                player_id
            )

            if actual is None:
                actual_complete = False
                exact_points: (
                    float | None
                ) = None

            else:
                _validate_actual_period(
                    actual,
                    season,
                    week,
                )

                exact_points = (
                    actual.exact_points
                )

                actual_total += (
                    exact_points
                )

            actual_assignments.append(
                LineupAssignment(
                    slot_index=(
                        slot.index
                    ),
                    slot_type=(
                        slot.slot_type
                    ),
                    slot_label=(
                        slot.label
                    ),
                    player_id=player_id,
                    player_name=(
                        roster_record.get(
                            "player_name"
                        )
                    ),
                    position=position,
                    exact_points=(
                        exact_points
                    ),
                    empty=False,
                )
            )

        actual_lineup_points = (
            round(
                actual_total,
                8,
            )
            if actual_complete
            else None
        )

        bench_player_ids = (
            set(
                roster_lookup
            )
            - actual_player_ids
        )

        bench_total = 0.0
        bench_complete = True

        for player_id in (
            bench_player_ids
        ):
            actual = actuals.get(
                player_id
            )

            if actual is None:
                bench_complete = False
                continue

            _validate_actual_period(
                actual,
                season,
                week,
            )

            bench_total += (
                actual.exact_points
            )

        bench_points = (
            round(
                bench_total,
                8,
            )
            if bench_complete
            else None
        )

        optimization_complete = (
            not unresolved_for_optimization
        )

        optimal_assignments: tuple[
            LineupAssignment,
            ...,
        ] = ()

        optimal_points: (
            float | None
        ) = None

        should_start: tuple[
            LineupPlayer,
            ...,
        ] = ()

        should_bench: tuple[
            LineupPlayer,
            ...,
        ] = ()

        if optimization_complete:
            optimized = (
                _optimize_lineup(
                    slots=slots,
                    players=tuple(
                        resolved_players
                    ),
                )
            )

            if optimized is None:
                raise LineupAnalyticsError(
                    f"Roster {roster_id} cannot "
                    "form a legal starting lineup"
                )

            (
                optimal_points,
                optimal_assignments,
            ) = optimized

            optimal_ids = {
                assignment.player_id
                for assignment
                in optimal_assignments
                if assignment.player_id
                is not None
            }

            start_ids = (
                optimal_ids
                - actual_player_ids
            )

            bench_ids = (
                actual_player_ids
                - optimal_ids
            )

            should_start = tuple(
                sorted(
                    (
                        resolved_player_lookup[
                            player_id
                        ]
                        for player_id
                        in start_ids
                    ),
                    key=lambda player: (
                        -player.exact_points,
                        player.player_id,
                    ),
                )
            )

            should_bench = tuple(
                sorted(
                    (
                        resolved_player_lookup[
                            player_id
                        ]
                        for player_id
                        in bench_ids
                        if player_id
                        in resolved_player_lookup
                    ),
                    key=lambda player: (
                        player.exact_points,
                        player.player_id,
                    ),
                )
            )

        lineup_efficiency: (
            float | None
        ) = None

        points_left: (
            float | None
        ) = None

        if (
            actual_lineup_points
            is not None
            and optimal_points
            is not None
        ):
            difference = (
                optimal_points
                - actual_lineup_points
            )

            if difference < -0.01:
                raise LineupAnalyticsError(
                    f"Roster {roster_id} actual "
                    "lineup exceeds calculated "
                    "optimal lineup"
                )

            points_left = max(
                0.0,
                round(
                    difference,
                    8,
                ),
            )

            if optimal_points > 0:
                lineup_efficiency = round(
                    (
                        actual_lineup_points
                        / optimal_points
                        * 100.0
                    ),
                    4,
                )

        sleeper_final_points = (
            _optional_number(
                team.get(
                    "final_points"
                ),
                (
                    f"Roster {roster_id} "
                    "final_points"
                ),
            )
        )

        reconciliation_delta: (
            float | None
        ) = None

        if (
            sleeper_final_points
            is not None
            and actual_lineup_points
            is not None
        ):
            reconciliation_delta = round(
                (
                    actual_lineup_points
                    - sleeper_final_points
                ),
                8,
            )

        team_results.append(
            TeamLineupEfficiency(
                roster_id=roster_id,
                manager_name=(
                    manager_name
                ),
                actual_lineup_complete=(
                    actual_complete
                ),
                optimization_complete=(
                    optimization_complete
                ),
                actual_lineup_points=(
                    actual_lineup_points
                ),
                optimal_lineup_points=(
                    optimal_points
                ),
                lineup_efficiency_pct=(
                    lineup_efficiency
                ),
                points_left_on_bench=(
                    points_left
                ),
                bench_points=(
                    bench_points
                ),
                sleeper_final_points=(
                    sleeper_final_points
                ),
                score_reconciliation_delta=(
                    reconciliation_delta
                ),
                actual_lineup=tuple(
                    actual_assignments
                ),
                optimal_lineup=(
                    optimal_assignments
                ),
                should_start=(
                    should_start
                ),
                should_bench=(
                    should_bench
                ),
                unresolved_player_ids=tuple(
                    sorted(
                        unresolved_for_optimization
                    )
                ),
            )
        )

    return (
        WeekLineupEfficiency(
            season=season,
            week=week,
            league_key=league_key,
            teams=tuple(
                team_results
            ),
        )
    )