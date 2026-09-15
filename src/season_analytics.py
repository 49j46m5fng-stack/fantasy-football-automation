"""Season-to-date analytics assembled from immutable final snapshots.

This module is the wiring layer between stored historical snapshots and
the existing deterministic analytics engines:

- standings / all-play / luck      (src.standings)
- power rankings                   (src.power_rankings)
- Monte Carlo season outcomes      (src.simulation)

It adds one new analytic of its own: a cross-league luck tracker that
compares every team's weekly score against all teams in both leagues
combined, so a strong score that still lost is visible as a bad-schedule
outcome rather than a bad team.

Design rules:

- Every input is read from stored final and baseline snapshots.
- Nothing here fabricates a missing value. When an input is unavailable
  the dependent analytic is omitted with a visible warning instead of
  being estimated.
- Results are derived artifacts and safe to recompute on every run.
"""

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.power_rankings import (
    PowerRankingError,
    PowerRankings,
    build_power_rankings,
)
from src.simulation import (
    LeagueSimulationResult,
    LeagueSimulationRules,
    RemainingGame,
    SimulationError,
    TeamSimulationState,
    load_simulation_config,
    simulate_league,
)
from src.standings import (
    ScheduledMatchup,
    SeasonStandings,
    StandingsAnalyticsError,
    TeamWeekScore,
    WeeklyLeagueResults,
    aggregate_season_standings,
    calculate_weekly_results,
)
from src.storage import (
    SnapshotStorageError,
    build_snapshot_path,
    read_snapshot,
)


DEFAULT_UNLUCKY_THRESHOLD = 0.5

DEFAULT_LUCKY_THRESHOLD = 0.5

LUCK_UNLUCKY = "unlucky"

LUCK_LUCKY = "lucky"

LUCK_NEUTRAL = "neutral"


class SeasonAnalyticsError(ValueError):
    """Raised when season analytics cannot be assembled safely."""


@dataclass(frozen=True)
class LuckConfig:
    """Thresholds for weekly luck classification."""

    unlucky_threshold: float
    lucky_threshold: float


@dataclass(frozen=True)
class LuckTeamWeek:
    """One team's weekly result with within- and cross-league context."""

    season: str
    week: int

    league_key: str
    roster_id: int
    manager_name: str

    points_for: float
    points_against: float

    opponent_roster_id: int
    opponent_manager_name: str

    result: str

    all_play_wins: int
    all_play_losses: int
    all_play_ties: int

    expected_wins: float
    luck_wins: float

    league_score_rank: int
    league_team_count: int

    cross_league_score_rank: int
    cross_league_team_count: int

    classification: str
    note: str

    @property
    def team_key(self) -> str:
        """Return the cross-league identity key."""

        return f"{self.league_key}:{self.roster_id}"


@dataclass(frozen=True)
class LuckWeek:
    """Every team's luck record for one completed fantasy week."""

    week: int
    teams: tuple[LuckTeamWeek, ...]


@dataclass(frozen=True)
class LuckSeasonTeam:
    """Season-to-date luck totals for one team."""

    league_key: str
    roster_id: int
    manager_name: str

    games: int

    actual_win_equivalent: float
    expected_wins: float
    luck_wins: float

    unlucky_weeks: int
    lucky_weeks: int

    best_cross_league_rank: int
    worst_cross_league_rank: int


@dataclass(frozen=True)
class LuckTracker:
    """Cross-league luck analytics for a season to date."""

    season: str
    through_week: int

    weeks: tuple[LuckWeek, ...]
    teams: tuple[LuckSeasonTeam, ...]

    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RelegationWatchTeam:
    """One team's promotion or relegation exposure."""

    league_key: str
    roster_id: int
    manager_name: str

    analytical_rank: int

    in_relegation_zone: bool
    in_promotion_position: bool

    relegation_probability: float | None
    promotion_probability: float | None
    playoff_probability: float | None

    warning: str | None


@dataclass(frozen=True)
class LeagueSeasonAnalytics:
    """Complete derived season analytics for one league."""

    league_key: str
    league_name: str
    through_week: int

    weekly_results: tuple[WeeklyLeagueResults, ...]
    standings: SeasonStandings

    power_rankings: PowerRankings | None
    simulation: LeagueSimulationResult | None

    watch: tuple[RelegationWatchTeam, ...]

    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SeasonAnalytics:
    """Season analytics across every configured league."""

    season: str
    through_week: int

    leagues: tuple[LeagueSeasonAnalytics, ...]
    luck: LuckTracker

    warnings: tuple[str, ...]


def load_luck_config(
    project_config: dict[str, Any],
) -> LuckConfig:
    """Read analytics.luck thresholds, falling back to defaults."""

    analytics = (
        project_config.get(
            "analytics"
        )
        if isinstance(
            project_config,
            dict,
        )
        else None
    )

    raw = (
        analytics.get(
            "luck"
        )
        if isinstance(
            analytics,
            dict,
        )
        else None
    )

    if raw is None:
        return LuckConfig(
            unlucky_threshold=(
                DEFAULT_UNLUCKY_THRESHOLD
            ),
            lucky_threshold=(
                DEFAULT_LUCKY_THRESHOLD
            ),
        )

    if not isinstance(
        raw,
        dict,
    ):
        raise SeasonAnalyticsError(
            "analytics.luck must be an object"
        )

    def _threshold(
        key: str,
        default: float,
    ) -> float:
        value = raw.get(
            key,
            default,
        )

        if isinstance(
            value,
            bool,
        ) or not isinstance(
            value,
            (int, float),
        ):
            raise SeasonAnalyticsError(
                f"analytics.luck.{key} must be numeric"
            )

        numeric = float(
            value
        )

        if (
            not math.isfinite(
                numeric
            )
            or numeric < 0
        ):
            raise SeasonAnalyticsError(
                f"analytics.luck.{key} must be a "
                "non-negative finite number"
            )

        return numeric

    return LuckConfig(
        unlucky_threshold=_threshold(
            "unlucky_threshold",
            DEFAULT_UNLUCKY_THRESHOLD,
        ),
        lucky_threshold=_threshold(
            "lucky_threshold",
            DEFAULT_LUCKY_THRESHOLD,
        ),
    )


def _team_points(
    team: dict[str, Any],
    league_key: str,
) -> float | None:
    """Return one team's effective final score, or None if unresolved."""

    value = team.get(
        "effective_final_points"
    )

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ) or not isinstance(
        value,
        (int, float),
    ):
        raise SeasonAnalyticsError(
            f"{league_key} effective_final_points must "
            "be numeric or null"
        )

    numeric = float(
        value
    )

    if not math.isfinite(
        numeric
    ):
        raise SeasonAnalyticsError(
            f"{league_key} effective_final_points must "
            "be finite"
        )

    return numeric


def completed_final_weeks(
    data_root: Path,
    season: str,
    league_keys: tuple[str, ...],
    max_week: int,
) -> tuple[int, ...]:
    """Return the leading run of weeks complete for every league."""

    weeks: list[int] = []

    for week in range(
        1,
        max_week + 1,
    ):
        complete = all(
            build_snapshot_path(
                data_root=data_root,
                season=season,
                league_key=league_key,
                week=week,
                stage="final",
            ).exists()
            for league_key
            in league_keys
        )

        if not complete:
            break

        weeks.append(
            week
        )

    return tuple(
        weeks
    )


def read_final_snapshot(
    data_root: Path,
    season: str,
    league_key: str,
    week: int,
) -> dict[str, Any]:
    """Read one stored final snapshot."""

    path = build_snapshot_path(
        data_root=data_root,
        season=season,
        league_key=league_key,
        week=week,
        stage="final",
    )

    try:
        return read_snapshot(
            path
        )

    except SnapshotStorageError as exc:
        raise SeasonAnalyticsError(
            f"Could not read week {week} final snapshot "
            f"for {league_key}"
        ) from exc


def build_weekly_league_results(
    snapshot: dict[str, Any],
) -> WeeklyLeagueResults:
    """Convert one final snapshot into weekly standings analytics."""

    league_key = snapshot.get(
        "league_key"
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

    if not isinstance(
        data,
        dict,
    ):
        raise SeasonAnalyticsError(
            "Final snapshot is missing data"
        )

    teams = data.get(
        "teams"
    )

    matchups = data.get(
        "matchups"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise SeasonAnalyticsError(
            f"{league_key} week {week} final snapshot "
            "is missing teams"
        )

    if not isinstance(
        matchups,
        list,
    ):
        raise SeasonAnalyticsError(
            f"{league_key} week {week} final snapshot "
            "is missing matchups"
        )

    scores: list[
        TeamWeekScore
    ] = []

    for team in teams:
        points = _team_points(
            team,
            league_key,
        )

        if points is None:
            raise SeasonAnalyticsError(
                f"{league_key} week {week} roster "
                f"{team.get('roster_id')} has no "
                "resolved final score. Standings and "
                "luck cannot be calculated from missing "
                "scores."
            )

        scores.append(
            TeamWeekScore(
                roster_id=team["roster_id"],
                manager_name=(
                    team["manager_name"]
                ),
                points=points,
            )
        )

    scheduled = [
        ScheduledMatchup(
            roster_id_1=(
                matchup["roster_a_id"]
            ),
            roster_id_2=(
                matchup["roster_b_id"]
            ),
        )
        for matchup
        in matchups
    ]

    try:
        return calculate_weekly_results(
            season=season,
            week=week,
            league_key=league_key,
            scores=scores,
            matchups=scheduled,
        )

    except StandingsAnalyticsError as exc:
        raise SeasonAnalyticsError(
            f"Could not calculate {league_key} week "
            f"{week} standings: {exc}"
        ) from exc


def _classify_luck(
    luck_wins: float,
    config: LuckConfig,
) -> str:
    """Classify a weekly luck value."""

    if luck_wins <= -config.unlucky_threshold:
        return LUCK_UNLUCKY

    if luck_wins >= config.lucky_threshold:
        return LUCK_LUCKY

    return LUCK_NEUTRAL


def _rank_scores(
    entries: list[tuple[str, float]],
) -> dict[str, int]:
    """Rank team keys by descending score, sharing ties."""

    ordered = sorted(
        entries,
        key=lambda item: -item[1],
    )

    ranks: dict[
        str,
        int,
    ] = {}

    previous_points: float | None = None

    previous_rank = 0

    for position, (
        team_key,
        points,
    ) in enumerate(
        ordered,
        start=1,
    ):
        if (
            previous_points is not None
            and math.isclose(
                points,
                previous_points,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        ):
            ranks[
                team_key
            ] = previous_rank

            continue

        ranks[
            team_key
        ] = position

        previous_rank = position

        previous_points = points

    return ranks


def _luck_note(
    classification: str,
    result: str,
    cross_rank: int,
    cross_count: int,
    all_play_wins: int,
    all_play_losses: int,
) -> str:
    """Write a factual one-line explanation of the weekly luck value."""

    placing = (
        f"{cross_rank} of {cross_count} across both "
        "leagues"
    )

    all_play = (
        f"all-play {all_play_wins}-{all_play_losses}"
    )

    if (
        classification == LUCK_UNLUCKY
        and result == "loss"
    ):
        return (
            f"Lost despite scoring {placing} "
            f"({all_play})."
        )

    if classification == LUCK_UNLUCKY:
        return (
            f"Scored {placing} ({all_play}) but the "
            "schedule returned less than that "
            "performance earned."
        )

    if (
        classification == LUCK_LUCKY
        and result == "win"
    ):
        return (
            f"Won while scoring {placing} "
            f"({all_play})."
        )

    if classification == LUCK_LUCKY:
        return (
            f"Scored {placing} ({all_play}) but the "
            "schedule returned more than that "
            "performance earned."
        )

    return (
        f"Scored {placing} ({all_play}); the result "
        "matched the performance."
    )


def build_luck_tracker(
    season: str,
    weekly_by_league: dict[str, list[WeeklyLeagueResults]],
    config: LuckConfig,
) -> LuckTracker:
    """Build the cross-league weekly luck tracker."""

    if not weekly_by_league:
        raise SeasonAnalyticsError(
            "At least one league is required for the "
            "luck tracker"
        )

    by_week: dict[
        int,
        list[tuple[str, WeeklyLeagueResults]],
    ] = {}

    for league_key, results in weekly_by_league.items():
        for result in results:
            by_week.setdefault(
                result.week,
                [],
            ).append(
                (
                    league_key,
                    result,
                )
            )

    warnings: list[str] = []

    weeks: list[LuckWeek] = []

    for week in sorted(
        by_week
    ):
        entries = by_week[
            week
        ]

        if len(
            entries
        ) != len(
            weekly_by_league
        ):
            warnings.append(
                f"Week {week} is missing results for at "
                "least one league. Cross-league ranks "
                "for that week cover only the leagues "
                "present."
            )

        cross_entries: list[
            tuple[str, float]
        ] = []

        league_entries: dict[
            str,
            list[tuple[str, float]],
        ] = {}

        lookup: dict[
            str,
            Any,
        ] = {}

        for league_key, result in entries:
            for team in result.teams:
                team_key = (
                    f"{league_key}:"
                    f"{team.roster_id}"
                )

                cross_entries.append(
                    (
                        team_key,
                        team.points_for,
                    )
                )

                league_entries.setdefault(
                    league_key,
                    [],
                ).append(
                    (
                        team_key,
                        team.points_for,
                    )
                )

                lookup[
                    team_key
                ] = (
                    league_key,
                    team,
                )

        cross_ranks = _rank_scores(
            cross_entries
        )

        league_ranks: dict[
            str,
            int,
        ] = {}

        for league_key, items in league_entries.items():
            league_ranks.update(
                _rank_scores(
                    items
                )
            )

        team_records: list[
            LuckTeamWeek
        ] = []

        for team_key in sorted(
            lookup
        ):
            league_key, team = lookup[
                team_key
            ]

            opponent_key = (
                f"{league_key}:"
                f"{team.opponent_roster_id}"
            )

            opponent = lookup.get(
                opponent_key
            )

            opponent_name = (
                opponent[1].manager_name
                if opponent is not None
                else f"roster {team.opponent_roster_id}"
            )

            if team.win:
                result_label = "win"

            elif team.loss:
                result_label = "loss"

            else:
                result_label = "tie"

            classification = _classify_luck(
                team.luck_wins,
                config,
            )

            cross_rank = cross_ranks[
                team_key
            ]

            note = _luck_note(
                classification=classification,
                result=result_label,
                cross_rank=cross_rank,
                cross_count=len(
                    cross_entries
                ),
                all_play_wins=(
                    team.all_play_wins
                ),
                all_play_losses=(
                    team.all_play_losses
                ),
            )

            team_records.append(
                LuckTeamWeek(
                    season=season,
                    week=week,
                    league_key=league_key,
                    roster_id=team.roster_id,
                    manager_name=(
                        team.manager_name
                    ),
                    points_for=(
                        team.points_for
                    ),
                    points_against=(
                        team.points_against
                    ),
                    opponent_roster_id=(
                        team.opponent_roster_id
                    ),
                    opponent_manager_name=(
                        opponent_name
                    ),
                    result=result_label,
                    all_play_wins=(
                        team.all_play_wins
                    ),
                    all_play_losses=(
                        team.all_play_losses
                    ),
                    all_play_ties=(
                        team.all_play_ties
                    ),
                    expected_wins=(
                        team.expected_wins
                    ),
                    luck_wins=(
                        team.luck_wins
                    ),
                    league_score_rank=(
                        league_ranks[
                            team_key
                        ]
                    ),
                    league_team_count=len(
                        league_entries[
                            league_key
                        ]
                    ),
                    cross_league_score_rank=(
                        cross_rank
                    ),
                    cross_league_team_count=len(
                        cross_entries
                    ),
                    classification=(
                        classification
                    ),
                    note=note,
                )
            )

        weeks.append(
            LuckWeek(
                week=week,
                teams=tuple(
                    team_records
                ),
            )
        )

    totals: dict[
        str,
        dict[str, Any],
    ] = {}

    for luck_week in weeks:
        for team in luck_week.teams:
            entry = totals.setdefault(
                team.team_key,
                {
                    "league_key": (
                        team.league_key
                    ),
                    "roster_id": (
                        team.roster_id
                    ),
                    "manager_name": (
                        team.manager_name
                    ),
                    "games": 0,
                    "actual": 0.0,
                    "expected": 0.0,
                    "luck": 0.0,
                    "unlucky": 0,
                    "lucky": 0,
                    "best": team.cross_league_score_rank,
                    "worst": team.cross_league_score_rank,
                },
            )

            actual = (
                1.0
                if team.result == "win"
                else 0.5
                if team.result == "tie"
                else 0.0
            )

            entry["games"] += 1

            entry["actual"] += actual

            entry["expected"] += (
                team.expected_wins
            )

            entry["luck"] += team.luck_wins

            if team.classification == LUCK_UNLUCKY:
                entry["unlucky"] += 1

            if team.classification == LUCK_LUCKY:
                entry["lucky"] += 1

            entry["best"] = min(
                entry["best"],
                team.cross_league_score_rank,
            )

            entry["worst"] = max(
                entry["worst"],
                team.cross_league_score_rank,
            )

    season_teams = tuple(
        sorted(
            (
                LuckSeasonTeam(
                    league_key=(
                        entry["league_key"]
                    ),
                    roster_id=(
                        entry["roster_id"]
                    ),
                    manager_name=(
                        entry["manager_name"]
                    ),
                    games=entry["games"],
                    actual_win_equivalent=(
                        entry["actual"]
                    ),
                    expected_wins=(
                        entry["expected"]
                    ),
                    luck_wins=entry["luck"],
                    unlucky_weeks=(
                        entry["unlucky"]
                    ),
                    lucky_weeks=(
                        entry["lucky"]
                    ),
                    best_cross_league_rank=(
                        entry["best"]
                    ),
                    worst_cross_league_rank=(
                        entry["worst"]
                    ),
                )
                for entry
                in totals.values()
            ),
            key=lambda team: (
                team.luck_wins,
                team.league_key,
                team.roster_id,
            ),
        )
    )

    return LuckTracker(
        season=season,
        through_week=(
            max(
                by_week
            )
            if by_week
            else 0
        ),
        weeks=tuple(
            weeks
        ),
        teams=season_teams,
        warnings=tuple(
            warnings
        ),
    )


def build_team_simulation_states(
    standings: SeasonStandings,
    weekly_results: list[WeeklyLeagueResults],
) -> list[TeamSimulationState]:
    """Derive simulation inputs from completed weekly scores."""

    scores_by_roster: dict[
        int,
        list[float],
    ] = {}

    for result in weekly_results:
        for team in result.teams:
            scores_by_roster.setdefault(
                team.roster_id,
                [],
            ).append(
                team.points_for
            )

    states: list[
        TeamSimulationState
    ] = []

    for team in standings.teams:
        points = scores_by_roster.get(
            team.roster_id,
            [],
        )

        if not points:
            raise SeasonAnalyticsError(
                f"No completed scores for roster "
                f"{team.roster_id}; simulation inputs "
                "cannot be derived"
            )

        mean_points = (
            statistics.fmean(
                points
            )
        )

        stddev_points = (
            statistics.stdev(
                points
            )
            if len(
                points
            )
            > 1
            else 0.0
        )

        states.append(
            TeamSimulationState(
                roster_id=team.roster_id,
                manager_name=(
                    team.manager_name
                ),
                wins=team.wins,
                losses=team.losses,
                ties=team.ties,
                points_for=(
                    team.points_for
                ),
                mean_points=mean_points,
                stddev_points=(
                    stddev_points
                ),
            )
        )

    return states


def build_league_simulation_rules(
    league_config: dict[str, Any],
    promotion_rules: dict[str, Any],
) -> LeagueSimulationRules:
    """Translate project configuration into simulation rules."""

    playoff_spots = league_config.get(
        "playoff_spots"
    )

    if playoff_spots is None:
        playoff_spots = league_config.get(
            "promotion_spots",
            0,
        )

    return LeagueSimulationRules(
        playoff_teams=int(
            playoff_spots or 0
        ),
        relegation_spots=int(
            league_config.get(
                "relegation_spots",
                0,
            )
            or 0
        ),
        regular_season_champion_promoted=bool(
            league_config.get(
                "promotion_spots"
            )
            and promotion_rules.get(
                "doats_regular_season_champion_promoted",
                False,
            )
        ),
        playoff_champion_promoted=bool(
            league_config.get(
                "promotion_spots"
            )
            and promotion_rules.get(
                "doats_playoff_champion_promoted",
                False,
            )
        ),
        if_same_champion_promote_playoff_runner_up=bool(
            league_config.get(
                "promotion_spots"
            )
            and promotion_rules.get(
                "if_same_champion_promote_playoff_runner_up",
                False,
            )
        ),
    )


def build_relegation_watch(
    league_key: str,
    standings: SeasonStandings,
    league_config: dict[str, Any],
    simulation: LeagueSimulationResult | None,
) -> tuple[RelegationWatchTeam, ...]:
    """Flag relegation exposure and promotion position."""

    team_count = len(
        standings.teams
    )

    relegation_spots = int(
        league_config.get(
            "relegation_spots",
            0,
        )
        or 0
    )

    promotion_spots = int(
        league_config.get(
            "promotion_spots",
            0,
        )
        or 0
    )

    simulation_lookup = (
        {
            team.roster_id: team
            for team
            in simulation.teams
        }
        if simulation is not None
        else {}
    )

    watch: list[
        RelegationWatchTeam
    ] = []

    for team in standings.teams:
        in_relegation_zone = bool(
            relegation_spots
            and team.analytical_rank
            > team_count - relegation_spots
        )

        in_promotion_position = bool(
            promotion_spots
            and team.analytical_rank
            <= promotion_spots
        )

        simulated = simulation_lookup.get(
            team.roster_id
        )

        warning: str | None = None

        if in_relegation_zone:
            warning = (
                f"{team.manager_name} is currently "
                f"{team.analytical_rank} of {team_count} "
                "and sits in the relegation zone."
            )

        watch.append(
            RelegationWatchTeam(
                league_key=league_key,
                roster_id=team.roster_id,
                manager_name=(
                    team.manager_name
                ),
                analytical_rank=(
                    team.analytical_rank
                ),
                in_relegation_zone=(
                    in_relegation_zone
                ),
                in_promotion_position=(
                    in_promotion_position
                ),
                relegation_probability=(
                    simulated.relegation_probability
                    if simulated is not None
                    else None
                ),
                promotion_probability=(
                    simulated.promotion_probability
                    if simulated is not None
                    else None
                ),
                playoff_probability=(
                    simulated.playoff_probability
                    if simulated is not None
                    else None
                ),
                warning=warning,
            )
        )

    return tuple(
        watch
    )


def baseline_projected_starter_points(
    data_root: Path,
    season: str,
    league_key: str,
    week: int,
) -> dict[int, float]:
    """Read frozen baseline starting-lineup projections for one week."""

    path = build_snapshot_path(
        data_root=data_root,
        season=season,
        league_key=league_key,
        week=week,
        stage="baseline",
    )

    if not path.exists():
        raise SeasonAnalyticsError(
            f"No baseline snapshot for {league_key} "
            f"week {week}"
        )

    snapshot = read_snapshot(
        path
    )

    teams = snapshot.get(
        "data",
        {},
    ).get(
        "teams"
    )

    if not isinstance(
        teams,
        list,
    ):
        raise SeasonAnalyticsError(
            f"{league_key} week {week} baseline "
            "snapshot is missing teams"
        )

    projections: dict[
        int,
        float,
    ] = {}

    for team in teams:
        value = team.get(
            "team_projection"
        )

        if value is None:
            value = team.get(
                "known_projected_points"
            )

        if value is None:
            raise SeasonAnalyticsError(
                f"{league_key} week {week} roster "
                f"{team.get('roster_id')} has no "
                "baseline projection. Power rankings "
                "will not invent one."
            )

        projections[
            team["roster_id"]
        ] = float(
            value
        )

    return projections


def build_league_analytics(
    data_root: Path,
    season: str,
    league_key: str,
    league_name: str,
    league_config: dict[str, Any],
    project_config: dict[str, Any],
    weeks: tuple[int, ...],
    remaining_games: list[RemainingGame] | None = None,
    lineup_efficiency_pct: dict[int, float] | None = None,
    previous_ranks: dict[int, int] | None = None,
) -> LeagueSeasonAnalytics:
    """Assemble every season analytic available for one league."""

    warnings: list[str] = []

    weekly_results = [
        build_weekly_league_results(
            read_final_snapshot(
                data_root=data_root,
                season=season,
                league_key=league_key,
                week=week,
            )
        )
        for week
        in weeks
    ]

    try:
        standings = (
            aggregate_season_standings(
                weekly_results
            )
        )

    except StandingsAnalyticsError as exc:
        raise SeasonAnalyticsError(
            f"Could not aggregate {league_key} "
            f"standings: {exc}"
        ) from exc

    through_week = weeks[-1]

    power = None

    if lineup_efficiency_pct is None:
        warnings.append(
            "Power rankings were skipped because "
            "season lineup efficiency was not supplied. "
            "Lineup efficiency requires actual player "
            "statistics and is never estimated."
        )

    else:
        try:
            projections = (
                baseline_projected_starter_points(
                    data_root=data_root,
                    season=season,
                    league_key=league_key,
                    week=through_week,
                )
            )

            power = build_power_rankings(
                standings=standings,
                weekly_results=weekly_results,
                projected_starter_points=(
                    projections
                ),
                lineup_efficiency_pct=(
                    lineup_efficiency_pct
                ),
                project_config=(
                    project_config
                ),
                previous_ranks=(
                    previous_ranks
                ),
            )

        except (
            PowerRankingError,
            SeasonAnalyticsError,
        ) as exc:
            warnings.append(
                f"Power rankings unavailable: {exc}"
            )

    simulation = None

    if remaining_games is None:
        warnings.append(
            "Season simulations were skipped because "
            "the remaining schedule was not supplied."
        )

    else:
        try:
            simulation = simulate_league(
                season=season,
                league_key=league_key,
                through_week=through_week,
                teams=(
                    build_team_simulation_states(
                        standings=standings,
                        weekly_results=(
                            weekly_results
                        ),
                    )
                ),
                remaining_games=(
                    remaining_games
                ),
                rules=(
                    build_league_simulation_rules(
                        league_config=(
                            league_config
                        ),
                        promotion_rules=(
                            project_config.get(
                                "promotion_rules",
                                {},
                            )
                        ),
                    )
                ),
                config=(
                    load_simulation_config(
                        project_config
                    )
                ),
            )

        except (
            SimulationError,
            SeasonAnalyticsError,
        ) as exc:
            warnings.append(
                f"Season simulation unavailable: {exc}"
            )

    watch = build_relegation_watch(
        league_key=league_key,
        standings=standings,
        league_config=league_config,
        simulation=simulation,
    )

    return LeagueSeasonAnalytics(
        league_key=league_key,
        league_name=league_name,
        through_week=through_week,
        weekly_results=tuple(
            weekly_results
        ),
        standings=standings,
        power_rankings=power,
        simulation=simulation,
        watch=watch,
        warnings=tuple(
            warnings
        ),
    )


def build_season_analytics(
    data_root: Path,
    season: str,
    project_config: dict[str, Any],
    max_week: int,
    remaining_games: dict[str, list[RemainingGame]] | None = None,
    lineup_efficiency_pct: dict[str, dict[int, float]] | None = None,
    previous_ranks: dict[str, dict[int, int]] | None = None,
) -> SeasonAnalytics:
    """Assemble season analytics for every configured league."""

    leagues = project_config.get(
        "leagues"
    )

    if not isinstance(
        leagues,
        dict,
    ) or not leagues:
        raise SeasonAnalyticsError(
            "Project config is missing leagues"
        )

    league_keys = tuple(
        leagues
    )

    weeks = completed_final_weeks(
        data_root=data_root,
        season=season,
        league_keys=league_keys,
        max_week=max_week,
    )

    if not weeks:
        raise SeasonAnalyticsError(
            "No completed final snapshots are available "
            "for season analytics"
        )

    warnings: list[str] = []

    league_analytics: list[
        LeagueSeasonAnalytics
    ] = []

    weekly_by_league: dict[
        str,
        list[WeeklyLeagueResults],
    ] = {}

    for league_key, league_config in leagues.items():
        analytics = build_league_analytics(
            data_root=data_root,
            season=season,
            league_key=league_key,
            league_name=(
                league_config.get(
                    "name",
                    league_key,
                )
            ),
            league_config=league_config,
            project_config=project_config,
            weeks=weeks,
            remaining_games=(
                remaining_games.get(
                    league_key
                )
                if remaining_games is not None
                else None
            ),
            lineup_efficiency_pct=(
                lineup_efficiency_pct.get(
                    league_key
                )
                if lineup_efficiency_pct is not None
                else None
            ),
            previous_ranks=(
                previous_ranks.get(
                    league_key
                )
                if previous_ranks is not None
                else None
            ),
        )

        league_analytics.append(
            analytics
        )

        weekly_by_league[
            league_key
        ] = list(
            analytics.weekly_results
        )

        warnings.extend(
            f"{league_key}: {warning}"
            for warning
            in analytics.warnings
        )

    luck = build_luck_tracker(
        season=season,
        weekly_by_league=weekly_by_league,
        config=load_luck_config(
            project_config
        ),
    )

    warnings.extend(
        luck.warnings
    )

    return SeasonAnalytics(
        season=season,
        through_week=weeks[-1],
        leagues=tuple(
            league_analytics
        ),
        luck=luck,
        warnings=tuple(
            warnings
        ),
    )


def season_analytics_context(
    analytics: SeasonAnalytics,
) -> dict[str, Any]:
    """Build replaceable AI-agent context for season analytics."""

    return {
        "season_analytics_format_version": 1,
        "season": analytics.season,
        "through_week": analytics.through_week,
        "leagues": [
            {
                "league_key": league.league_key,
                "league_name": league.league_name,
                "standings": [
                    {
                        "analytical_rank": (
                            team.analytical_rank
                        ),
                        "roster_id": team.roster_id,
                        "manager_name": (
                            team.manager_name
                        ),
                        "wins": team.wins,
                        "losses": team.losses,
                        "ties": team.ties,
                        "points_for": (
                            team.points_for
                        ),
                        "points_against": (
                            team.points_against
                        ),
                        "all_play_percentage": (
                            team.all_play_percentage
                        ),
                        "expected_wins": (
                            team.expected_wins
                        ),
                        "luck_wins": (
                            team.luck_wins
                        ),
                    }
                    for team
                    in league.standings.teams
                ],
                "power_rankings": (
                    [
                        {
                            "current_rank": (
                                team.current_rank
                            ),
                            "previous_rank": (
                                team.previous_rank
                            ),
                            "rank_change": (
                                team.rank_change
                            ),
                            "roster_id": (
                                team.roster_id
                            ),
                            "manager_name": (
                                team.manager_name
                            ),
                            "composite_score": (
                                team.composite_score
                            ),
                        }
                        for team
                        in league.power_rankings.teams
                    ]
                    if league.power_rankings is not None
                    else None
                ),
                "simulation": (
                    {
                        "simulations": (
                            league.simulation.simulations
                        ),
                        "random_seed": (
                            league.simulation.random_seed
                        ),
                        "teams": [
                            {
                                "roster_id": (
                                    team.roster_id
                                ),
                                "manager_name": (
                                    team.manager_name
                                ),
                                "playoff_probability": (
                                    team.playoff_probability
                                ),
                                "relegation_probability": (
                                    team.relegation_probability
                                ),
                                "promotion_probability": (
                                    team.promotion_probability
                                ),
                                "expected_regular_season_wins": (
                                    team.expected_regular_season_wins
                                ),
                            }
                            for team
                            in league.simulation.teams
                        ],
                    }
                    if league.simulation is not None
                    else None
                ),
                "watch": [
                    {
                        "roster_id": team.roster_id,
                        "manager_name": (
                            team.manager_name
                        ),
                        "analytical_rank": (
                            team.analytical_rank
                        ),
                        "in_relegation_zone": (
                            team.in_relegation_zone
                        ),
                        "in_promotion_position": (
                            team.in_promotion_position
                        ),
                        "relegation_probability": (
                            team.relegation_probability
                        ),
                        "promotion_probability": (
                            team.promotion_probability
                        ),
                        "warning": team.warning,
                    }
                    for team
                    in league.watch
                ],
                "warnings": list(
                    league.warnings
                ),
            }
            for league
            in analytics.leagues
        ],
        "luck": {
            "through_week": (
                analytics.luck.through_week
            ),
            "weeks": [
                {
                    "week": luck_week.week,
                    "teams": [
                        {
                            "league_key": (
                                team.league_key
                            ),
                            "roster_id": (
                                team.roster_id
                            ),
                            "manager_name": (
                                team.manager_name
                            ),
                            "points_for": (
                                team.points_for
                            ),
                            "points_against": (
                                team.points_against
                            ),
                            "opponent_manager_name": (
                                team.opponent_manager_name
                            ),
                            "result": team.result,
                            "expected_wins": (
                                team.expected_wins
                            ),
                            "luck_wins": (
                                team.luck_wins
                            ),
                            "league_score_rank": (
                                team.league_score_rank
                            ),
                            "cross_league_score_rank": (
                                team.cross_league_score_rank
                            ),
                            "cross_league_team_count": (
                                team.cross_league_team_count
                            ),
                            "classification": (
                                team.classification
                            ),
                            "note": team.note,
                        }
                        for team
                        in luck_week.teams
                    ],
                }
                for luck_week
                in analytics.luck.weeks
            ],
            "season": [
                {
                    "league_key": team.league_key,
                    "roster_id": team.roster_id,
                    "manager_name": (
                        team.manager_name
                    ),
                    "games": team.games,
                    "actual_win_equivalent": (
                        team.actual_win_equivalent
                    ),
                    "expected_wins": (
                        team.expected_wins
                    ),
                    "luck_wins": team.luck_wins,
                    "unlucky_weeks": (
                        team.unlucky_weeks
                    ),
                    "lucky_weeks": (
                        team.lucky_weeks
                    ),
                    "best_cross_league_rank": (
                        team.best_cross_league_rank
                    ),
                    "worst_cross_league_rank": (
                        team.worst_cross_league_rank
                    ),
                }
                for team
                in analytics.luck.teams
            ],
        },
        "warnings": list(
            analytics.warnings
        ),
    }
