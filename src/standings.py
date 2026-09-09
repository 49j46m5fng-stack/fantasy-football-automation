"""Standings, all-play, and schedule-luck analytics.

This module is intentionally independent of Sleeper's live API.

Weekly inputs consist only of:

- final fantasy team scores
- scheduled matchup pairs

Historical standings are then aggregated from those deterministic
weekly results.

"Analytical rank" is not claimed to be Sleeper's official playoff
seeding. It sorts by:

1. actual win equivalent
2. points for
3. roster_id

Official league seeding rules can be layered on separately.
"""

from dataclasses import dataclass
import math


class StandingsAnalyticsError(ValueError):
    """Raised when standings analytics cannot be calculated safely."""


@dataclass(frozen=True)
class TeamWeekScore:
    """One fantasy team's completed weekly score."""

    roster_id: int
    manager_name: str
    points: float


@dataclass(frozen=True)
class ScheduledMatchup:
    """One scheduled fantasy matchup."""

    roster_id_1: int
    roster_id_2: int


@dataclass(frozen=True)
class WeeklyTeamResult:
    """Weekly record, all-play result, and luck for one team."""

    roster_id: int
    manager_name: str

    points_for: float

    opponent_roster_id: int
    points_against: float

    win: int
    loss: int
    tie: int

    actual_win_equivalent: float

    all_play_wins: int
    all_play_losses: int
    all_play_ties: int

    expected_wins: float
    luck_wins: float


@dataclass(frozen=True)
class WeeklyLeagueResults:
    """Completed weekly analytics for one league."""

    season: str
    week: int
    league_key: str

    teams: tuple[
        WeeklyTeamResult,
        ...,
    ]


@dataclass(frozen=True)
class SeasonTeamStanding:
    """Cumulative deterministic standings analytics."""

    analytical_rank: int

    roster_id: int
    manager_name: str

    games: int

    wins: int
    losses: int
    ties: int

    actual_win_equivalent: float
    record_percentage: float

    points_for: float
    points_against: float

    all_play_wins: int
    all_play_losses: int
    all_play_ties: int

    all_play_percentage: float

    expected_wins: float
    luck_wins: float


@dataclass(frozen=True)
class SeasonStandings:
    """Season-to-date standings analytics."""

    season: str
    league_key: str
    through_week: int

    teams: tuple[
        SeasonTeamStanding,
        ...,
    ]


def _validate_number(
    value: float,
    description: str,
) -> float:
    """Require a finite numeric value."""

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
        raise StandingsAnalyticsError(
            f"{description} must be numeric"
        )

    normalized = float(
        value
    )

    if not math.isfinite(
        normalized
    ):
        raise StandingsAnalyticsError(
            f"{description} must be finite"
        )

    return normalized


def _compare_scores(
    left: float,
    right: float,
) -> int:
    """Compare two fantasy scores.

    Returns:
        1 if left wins
        0 if tied
       -1 if left loses
    """

    if math.isclose(
        left,
        right,
        abs_tol=1e-9,
        rel_tol=0.0,
    ):
        return 0

    if left > right:
        return 1

    return -1


def calculate_weekly_results(
    season: str,
    week: int,
    league_key: str,
    scores: list[TeamWeekScore],
    matchups: list[ScheduledMatchup],
) -> WeeklyLeagueResults:
    """Calculate actual record, all-play record, and weekly luck."""

    if (
        not isinstance(
            season,
            str,
        )
        or not season
    ):
        raise StandingsAnalyticsError(
            "season must be a non-empty string"
        )

    if (
        not isinstance(
            week,
            int,
        )
        or week < 1
    ):
        raise StandingsAnalyticsError(
            "week must be a positive integer"
        )

    if (
        not isinstance(
            league_key,
            str,
        )
        or not league_key
    ):
        raise StandingsAnalyticsError(
            "league_key must be a non-empty string"
        )

    if len(
        scores
    ) < 2:
        raise StandingsAnalyticsError(
            "At least two team scores are required"
        )

    if (
        len(
            scores
        )
        % 2
        != 0
    ):
        raise StandingsAnalyticsError(
            "Weekly fantasy team count must be even"
        )

    score_lookup: dict[
        int,
        TeamWeekScore,
    ] = {}

    for score in scores:
        if not isinstance(
            score.roster_id,
            int,
        ):
            raise StandingsAnalyticsError(
                "roster_id must be an integer"
            )

        if (
            not isinstance(
                score.manager_name,
                str,
            )
            or not score.manager_name
        ):
            raise StandingsAnalyticsError(
                f"Roster {score.roster_id} "
                "must have a manager_name"
            )

        if (
            score.roster_id
            in score_lookup
        ):
            raise StandingsAnalyticsError(
                "Duplicate team score for roster "
                f"{score.roster_id}"
            )

        points = _validate_number(
            score.points,
            (
                f"Roster {score.roster_id} "
                "points"
            ),
        )

        score_lookup[
            score.roster_id
        ] = TeamWeekScore(
            roster_id=(
                score.roster_id
            ),
            manager_name=(
                score.manager_name
            ),
            points=points,
        )

    expected_matchups = (
        len(
            score_lookup
        )
        // 2
    )

    if (
        len(
            matchups
        )
        != expected_matchups
    ):
        raise StandingsAnalyticsError(
            "Weekly matchup count does not "
            "cover every fantasy team exactly once"
        )

    opponent_lookup: dict[
        int,
        int,
    ] = {}

    for matchup in matchups:
        roster_1 = (
            matchup.roster_id_1
        )

        roster_2 = (
            matchup.roster_id_2
        )

        if (
            not isinstance(
                roster_1,
                int,
            )
            or not isinstance(
                roster_2,
                int,
            )
        ):
            raise StandingsAnalyticsError(
                "Matchup roster IDs must be integers"
            )

        if (
            roster_1
            == roster_2
        ):
            raise StandingsAnalyticsError(
                f"Roster {roster_1} cannot "
                "play itself"
            )

        for roster_id in (
            roster_1,
            roster_2,
        ):
            if (
                roster_id
                not in score_lookup
            ):
                raise StandingsAnalyticsError(
                    "Matchup references unknown roster "
                    f"{roster_id}"
                )

            if (
                roster_id
                in opponent_lookup
            ):
                raise StandingsAnalyticsError(
                    f"Roster {roster_id} appears "
                    "in multiple weekly matchups"
                )

        opponent_lookup[
            roster_1
        ] = roster_2

        opponent_lookup[
            roster_2
        ] = roster_1

    if (
        set(
            opponent_lookup
        )
        != set(
            score_lookup
        )
    ):
        raise StandingsAnalyticsError(
            "Weekly matchups do not cover "
            "every fantasy roster"
        )

    results: list[
        WeeklyTeamResult
    ] = []

    total_opponents = (
        len(
            score_lookup
        )
        - 1
    )

    for roster_id in sorted(
        score_lookup
    ):
        team = (
            score_lookup[
                roster_id
            ]
        )

        opponent_id = (
            opponent_lookup[
                roster_id
            ]
        )

        opponent = (
            score_lookup[
                opponent_id
            ]
        )

        actual_comparison = (
            _compare_scores(
                team.points,
                opponent.points,
            )
        )

        if actual_comparison > 0:
            win = 1
            loss = 0
            tie = 0

        elif actual_comparison < 0:
            win = 0
            loss = 1
            tie = 0

        else:
            win = 0
            loss = 0
            tie = 1

        actual_win_equivalent = (
            float(
                win
            )
            + 0.5
            * float(
                tie
            )
        )

        all_play_wins = 0
        all_play_losses = 0
        all_play_ties = 0

        for (
            other_roster_id,
            other_team,
        ) in score_lookup.items():
            if (
                other_roster_id
                == roster_id
            ):
                continue

            comparison = (
                _compare_scores(
                    team.points,
                    other_team.points,
                )
            )

            if comparison > 0:
                all_play_wins += 1

            elif comparison < 0:
                all_play_losses += 1

            else:
                all_play_ties += 1

        expected_wins = (
            (
                float(
                    all_play_wins
                )
                + 0.5
                * float(
                    all_play_ties
                )
            )
            / float(
                total_opponents
            )
        )

        luck_wins = (
            actual_win_equivalent
            - expected_wins
        )

        results.append(
            WeeklyTeamResult(
                roster_id=roster_id,
                manager_name=(
                    team.manager_name
                ),
                points_for=(
                    team.points
                ),
                opponent_roster_id=(
                    opponent_id
                ),
                points_against=(
                    opponent.points
                ),
                win=win,
                loss=loss,
                tie=tie,
                actual_win_equivalent=(
                    round(
                        actual_win_equivalent,
                        8,
                    )
                ),
                all_play_wins=(
                    all_play_wins
                ),
                all_play_losses=(
                    all_play_losses
                ),
                all_play_ties=(
                    all_play_ties
                ),
                expected_wins=(
                    round(
                        expected_wins,
                        8,
                    )
                ),
                luck_wins=(
                    round(
                        luck_wins,
                        8,
                    )
                ),
            )
        )

    return WeeklyLeagueResults(
        season=season,
        week=week,
        league_key=league_key,
        teams=tuple(
            results
        ),
    )


def aggregate_season_standings(
    weeks: list[
        WeeklyLeagueResults
    ],
) -> SeasonStandings:
    """Aggregate completed weekly analytics into season standings."""

    if not weeks:
        raise StandingsAnalyticsError(
            "At least one completed week is required"
        )

    ordered_weeks = sorted(
        weeks,
        key=lambda result: (
            result.week
        ),
    )

    reference = (
        ordered_weeks[0]
    )

    seen_weeks: set[
        int
    ] = set()

    reference_rosters = {
        team.roster_id
        for team
        in reference.teams
    }

    if not reference_rosters:
        raise StandingsAnalyticsError(
            "Weekly results contain no teams"
        )

    accumulators: dict[
        int,
        dict[str, float | int | str],
    ] = {}

    for weekly in (
        ordered_weeks
    ):
        if (
            weekly.season
            != reference.season
        ):
            raise StandingsAnalyticsError(
                "Cannot aggregate different seasons"
            )

        if (
            weekly.league_key
            != reference.league_key
        ):
            raise StandingsAnalyticsError(
                "Cannot aggregate different leagues"
            )

        if (
            weekly.week
            in seen_weeks
        ):
            raise StandingsAnalyticsError(
                f"Duplicate completed week "
                f"{weekly.week}"
            )

        seen_weeks.add(
            weekly.week
        )

        roster_ids = {
            team.roster_id
            for team
            in weekly.teams
        }

        if (
            roster_ids
            != reference_rosters
        ):
            raise StandingsAnalyticsError(
                "Fantasy roster set changed "
                "between completed weeks"
            )

        for team in (
            weekly.teams
        ):
            accumulator = (
                accumulators.setdefault(
                    team.roster_id,
                    {
                        "manager_name": (
                            team.manager_name
                        ),
                        "games": 0,
                        "wins": 0,
                        "losses": 0,
                        "ties": 0,
                        "actual_win_equivalent": 0.0,
                        "points_for": 0.0,
                        "points_against": 0.0,
                        "all_play_wins": 0,
                        "all_play_losses": 0,
                        "all_play_ties": 0,
                        "expected_wins": 0.0,
                        "luck_wins": 0.0,
                    },
                )
            )

            # Use the most recently observed display name.
            accumulator[
                "manager_name"
            ] = (
                team.manager_name
            )

            accumulator[
                "games"
            ] = int(
                accumulator[
                    "games"
                ]
            ) + 1

            accumulator[
                "wins"
            ] = int(
                accumulator[
                    "wins"
                ]
            ) + team.win

            accumulator[
                "losses"
            ] = int(
                accumulator[
                    "losses"
                ]
            ) + team.loss

            accumulator[
                "ties"
            ] = int(
                accumulator[
                    "ties"
                ]
            ) + team.tie

            accumulator[
                "actual_win_equivalent"
            ] = float(
                accumulator[
                    "actual_win_equivalent"
                ]
            ) + (
                team.actual_win_equivalent
            )

            accumulator[
                "points_for"
            ] = float(
                accumulator[
                    "points_for"
                ]
            ) + (
                team.points_for
            )

            accumulator[
                "points_against"
            ] = float(
                accumulator[
                    "points_against"
                ]
            ) + (
                team.points_against
            )

            accumulator[
                "all_play_wins"
            ] = int(
                accumulator[
                    "all_play_wins"
                ]
            ) + (
                team.all_play_wins
            )

            accumulator[
                "all_play_losses"
            ] = int(
                accumulator[
                    "all_play_losses"
                ]
            ) + (
                team.all_play_losses
            )

            accumulator[
                "all_play_ties"
            ] = int(
                accumulator[
                    "all_play_ties"
                ]
            ) + (
                team.all_play_ties
            )

            accumulator[
                "expected_wins"
            ] = float(
                accumulator[
                    "expected_wins"
                ]
            ) + (
                team.expected_wins
            )

            accumulator[
                "luck_wins"
            ] = float(
                accumulator[
                    "luck_wins"
                ]
            ) + (
                team.luck_wins
            )

    unsorted: list[
        dict[str, float | int | str]
    ] = []

    for (
        roster_id,
        accumulator,
    ) in accumulators.items():
        games = int(
            accumulator[
                "games"
            ]
        )

        actual_win_equivalent = float(
            accumulator[
                "actual_win_equivalent"
            ]
        )

        record_percentage = (
            actual_win_equivalent
            / float(
                games
            )
        )

        all_play_wins = int(
            accumulator[
                "all_play_wins"
            ]
        )

        all_play_losses = int(
            accumulator[
                "all_play_losses"
            ]
        )

        all_play_ties = int(
            accumulator[
                "all_play_ties"
            ]
        )

        all_play_games = (
            all_play_wins
            + all_play_losses
            + all_play_ties
        )

        if all_play_games == 0:
            raise StandingsAnalyticsError(
                "All-play record contains zero games"
            )

        all_play_percentage = (
            (
                float(
                    all_play_wins
                )
                + 0.5
                * float(
                    all_play_ties
                )
            )
            / float(
                all_play_games
            )
        )

        unsorted.append(
            {
                "roster_id": (
                    roster_id
                ),
                "manager_name": str(
                    accumulator[
                        "manager_name"
                    ]
                ),
                "games": games,
                "wins": int(
                    accumulator[
                        "wins"
                    ]
                ),
                "losses": int(
                    accumulator[
                        "losses"
                    ]
                ),
                "ties": int(
                    accumulator[
                        "ties"
                    ]
                ),
                "actual_win_equivalent": (
                    round(
                        actual_win_equivalent,
                        8,
                    )
                ),
                "record_percentage": (
                    round(
                        record_percentage,
                        8,
                    )
                ),
                "points_for": (
                    round(
                        float(
                            accumulator[
                                "points_for"
                            ]
                        ),
                        8,
                    )
                ),
                "points_against": (
                    round(
                        float(
                            accumulator[
                                "points_against"
                            ]
                        ),
                        8,
                    )
                ),
                "all_play_wins": (
                    all_play_wins
                ),
                "all_play_losses": (
                    all_play_losses
                ),
                "all_play_ties": (
                    all_play_ties
                ),
                "all_play_percentage": (
                    round(
                        all_play_percentage,
                        8,
                    )
                ),
                "expected_wins": (
                    round(
                        float(
                            accumulator[
                                "expected_wins"
                            ]
                        ),
                        8,
                    )
                ),
                "luck_wins": (
                    round(
                        float(
                            accumulator[
                                "luck_wins"
                            ]
                        ),
                        8,
                    )
                ),
            }
        )

    ranked = sorted(
        unsorted,
        key=lambda team: (
            -float(
                team[
                    "actual_win_equivalent"
                ]
            ),
            -float(
                team[
                    "points_for"
                ]
            ),
            int(
                team[
                    "roster_id"
                ]
            ),
        ),
    )

    standings: list[
        SeasonTeamStanding
    ] = []

    for rank, team in enumerate(
        ranked,
        start=1,
    ):
        standings.append(
            SeasonTeamStanding(
                analytical_rank=rank,
                roster_id=int(
                    team[
                        "roster_id"
                    ]
                ),
                manager_name=str(
                    team[
                        "manager_name"
                    ]
                ),
                games=int(
                    team[
                        "games"
                    ]
                ),
                wins=int(
                    team[
                        "wins"
                    ]
                ),
                losses=int(
                    team[
                        "losses"
                    ]
                ),
                ties=int(
                    team[
                        "ties"
                    ]
                ),
                actual_win_equivalent=float(
                    team[
                        "actual_win_equivalent"
                    ]
                ),
                record_percentage=float(
                    team[
                        "record_percentage"
                    ]
                ),
                points_for=float(
                    team[
                        "points_for"
                    ]
                ),
                points_against=float(
                    team[
                        "points_against"
                    ]
                ),
                all_play_wins=int(
                    team[
                        "all_play_wins"
                    ]
                ),
                all_play_losses=int(
                    team[
                        "all_play_losses"
                    ]
                ),
                all_play_ties=int(
                    team[
                        "all_play_ties"
                    ]
                ),
                all_play_percentage=float(
                    team[
                        "all_play_percentage"
                    ]
                ),
                expected_wins=float(
                    team[
                        "expected_wins"
                    ]
                ),
                luck_wins=float(
                    team[
                        "luck_wins"
                    ]
                ),
            )
        )

    return SeasonStandings(
        season=(
            reference.season
        ),
        league_key=(
            reference.league_key
        ),
        through_week=max(
            seen_weeks
        ),
        teams=tuple(
            standings
        ),
    )