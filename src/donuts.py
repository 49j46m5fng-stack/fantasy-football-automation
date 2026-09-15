"""Cross-league donut survival pool analytics.

The donut pool is a single elimination-by-futility contest spanning both
leagues at once.

Each completed fantasy week, the lowest scoring fantasy team across
GOATs and DOATs combined brings donuts the following week.

Once a manager has been assigned donut duty they are permanently removed
from the eligible pool. With 18 entrants and a 17-week season including
playoffs, exactly one manager should finish unDOUGHfeated.

This module is deterministic analytics only. It performs no HTTP
requests and never writes immutable stage snapshots. Pool state is a
derived artifact recomputed from stored final snapshots, in the same
spirit as agent context.

Design invariants:

- Cross-league identity is (league_key, roster_id), never manager name.
- A missing weekly score is unresolved. It is never treated as zero and
  therefore never wins the donut.
- Ties are not silently broken. The default tie policy leaves the week
  unresolved and blocks later weeks until a commissioner override is
  committed with a written reason.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.storage import (
    SnapshotStorageError,
    build_snapshot_path,
    read_snapshot,
)


SCORE_TOLERANCE = 1e-9

VALID_TIE_POLICIES = (
    "unresolved",
    "all_tied",
    "lowest_season_points",
)

STATUS_ASSIGNED = "assigned"
STATUS_UNRESOLVED_TIE = "unresolved_tie"
STATUS_NO_ELIGIBLE_SCORES = "no_eligible_scores"
STATUS_BLOCKED = "blocked"


class DonutPoolError(ValueError):
    """Raised when donut-pool analytics cannot be calculated safely."""


@dataclass(frozen=True)
class DonutConfig:
    """Validated donut-pool settings."""

    enabled: bool
    leagues: tuple[str, ...]
    total_weeks: int
    delivery_offset_weeks: int
    tie_policy: str


@dataclass(frozen=True)
class DonutEntrant:
    """One fantasy team competing in the cross-league donut pool."""

    league_key: str
    roster_id: int
    manager_name: str

    @property
    def team_key(self) -> str:
        """Return the stable cross-league identity key."""

        return f"{self.league_key}:{self.roster_id}"


@dataclass(frozen=True)
class DonutWeekScore:
    """One fantasy team's completed weekly score for the donut pool."""

    league_key: str
    roster_id: int
    manager_name: str
    points: float | None

    @property
    def team_key(self) -> str:
        """Return the stable cross-league identity key."""

        return f"{self.league_key}:{self.roster_id}"


@dataclass(frozen=True)
class DonutAssignment:
    """A resolved weekly donut obligation."""

    scoring_week: int
    delivery_week: int

    league_key: str
    roster_id: int
    manager_name: str

    points: float

    margin_to_next_lowest: float | None

    tie_broken: bool
    resolution: str
    reason: str | None


@dataclass(frozen=True)
class DonutWeekResult:
    """Outcome of one donut-pool week."""

    scoring_week: int
    delivery_week: int
    status: str

    assignments: tuple[DonutAssignment, ...]

    eligible_before: tuple[str, ...]
    eligible_after: tuple[str, ...]

    tied_team_keys: tuple[str, ...]
    lowest_points: float | None

    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DonutSurvivor:
    """A manager still eligible to be assigned donut duty."""

    league_key: str
    roster_id: int
    manager_name: str

    weeks_survived: int

    closest_call_margin: float | None
    closest_call_week: int | None

    lowest_weekly_points: float | None
    lowest_weekly_points_week: int | None


@dataclass(frozen=True)
class DonutPoolState:
    """Complete derived donut-pool state through a given week."""

    season: str
    through_week: int
    total_weeks: int
    tie_policy: str

    entrants: tuple[DonutEntrant, ...]
    results: tuple[DonutWeekResult, ...]

    eliminated: tuple[DonutAssignment, ...]
    survivors: tuple[DonutSurvivor, ...]

    next_delivery: DonutAssignment | None
    undoughfeated: DonutSurvivor | None

    complete: bool
    blocked_week: int | None

    warnings: tuple[str, ...]


def load_donut_config(
    project_config: dict[str, Any],
) -> DonutConfig:
    """Read and validate analytics.donut_pool from config.json."""

    try:
        analytics = project_config["analytics"]
        settings = analytics["donut_pool"]

    except (KeyError, TypeError) as exc:
        raise DonutPoolError(
            "Missing analytics.donut_pool configuration"
        ) from exc

    if not isinstance(settings, dict):
        raise DonutPoolError(
            "analytics.donut_pool must be an object"
        )

    enabled = settings.get("enabled", True)

    if not isinstance(enabled, bool):
        raise DonutPoolError(
            "donut_pool.enabled must be true or false"
        )

    raw_leagues = settings.get("leagues")

    if (
        not isinstance(raw_leagues, list)
        or not raw_leagues
    ):
        raise DonutPoolError(
            "donut_pool.leagues must be a non-empty list"
        )

    leagues: list[str] = []

    for raw_league in raw_leagues:
        if (
            not isinstance(raw_league, str)
            or not raw_league.strip()
        ):
            raise DonutPoolError(
                "donut_pool.leagues entries must be league keys"
            )

        league_key = raw_league.strip()

        if league_key in leagues:
            raise DonutPoolError(
                f"Duplicate donut_pool league: {league_key}"
            )

        leagues.append(league_key)

    configured_leagues = project_config.get("leagues")

    if isinstance(configured_leagues, dict):
        for league_key in leagues:
            if league_key not in configured_leagues:
                raise DonutPoolError(
                    f"donut_pool league {league_key} is not "
                    "a configured league"
                )

    total_weeks = settings.get("total_weeks")

    if (
        isinstance(total_weeks, bool)
        or not isinstance(total_weeks, int)
        or total_weeks < 1
    ):
        raise DonutPoolError(
            "donut_pool.total_weeks must be a positive integer"
        )

    delivery_offset_weeks = settings.get(
        "delivery_offset_weeks",
        1,
    )

    if (
        isinstance(delivery_offset_weeks, bool)
        or not isinstance(delivery_offset_weeks, int)
        or delivery_offset_weeks < 0
    ):
        raise DonutPoolError(
            "donut_pool.delivery_offset_weeks must be a "
            "non-negative integer"
        )

    tie_policy = settings.get(
        "tie_policy",
        "unresolved",
    )

    if tie_policy not in VALID_TIE_POLICIES:
        raise DonutPoolError(
            "donut_pool.tie_policy must be one of "
            f"{', '.join(VALID_TIE_POLICIES)}"
        )

    return DonutConfig(
        enabled=enabled,
        leagues=tuple(leagues),
        total_weeks=total_weeks,
        delivery_offset_weeks=delivery_offset_weeks,
        tie_policy=tie_policy,
    )


def load_donut_overrides(
    path: Path,
) -> dict[int, dict[str, Any]]:
    """Load committed commissioner tie rulings.

    The override file exists so that a genuine scoring tie is resolved by
    a recorded human decision rather than an invented computer rule.
    """

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

    except (OSError, json.JSONDecodeError) as exc:
        raise DonutPoolError(
            f"Could not read donut overrides: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise DonutPoolError(
            "Donut override file must contain a JSON object"
        )

    if payload.get("schema_version") != 1:
        raise DonutPoolError(
            "Unsupported donut override schema version"
        )

    weeks = payload.get("weeks", {})

    if not isinstance(weeks, dict):
        raise DonutPoolError(
            "Donut override weeks must be a JSON object"
        )

    overrides: dict[int, dict[str, Any]] = {}

    for raw_week, raw_override in weeks.items():
        try:
            week = int(raw_week)

        except (TypeError, ValueError) as exc:
            raise DonutPoolError(
                f"Donut override week {raw_week!r} is not an integer"
            ) from exc

        if week < 1:
            raise DonutPoolError(
                "Donut override weeks must be at least 1"
            )

        if not isinstance(raw_override, dict):
            raise DonutPoolError(
                f"Donut override for week {week} must be an object"
            )

        league_key = raw_override.get("league_key")
        roster_id = raw_override.get("roster_id")
        reason = raw_override.get("reason")

        if (
            not isinstance(league_key, str)
            or not league_key.strip()
        ):
            raise DonutPoolError(
                f"Donut override for week {week} must contain "
                "a league_key"
            )

        if (
            isinstance(roster_id, bool)
            or not isinstance(roster_id, int)
        ):
            raise DonutPoolError(
                f"Donut override for week {week} must contain "
                "an integer roster_id"
            )

        if (
            not isinstance(reason, str)
            or not reason.strip()
        ):
            raise DonutPoolError(
                f"Donut override for week {week} must contain "
                "a written reason"
            )

        overrides[week] = {
            "league_key": league_key.strip(),
            "roster_id": roster_id,
            "reason": reason.strip(),
        }

    return overrides


def _finite_points(
    value: Any,
    description: str,
) -> float | None:
    """Return a finite score, or None when the score is unavailable."""

    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise DonutPoolError(
            f"{description} must be numeric or null"
        )

    points = float(value)

    if not math.isfinite(points):
        raise DonutPoolError(
            f"{description} must be finite"
        )

    return points


def _scores_tied(
    left: float,
    right: float,
) -> bool:
    """Return whether two fantasy scores are equal within tolerance."""

    return math.isclose(
        left,
        right,
        abs_tol=SCORE_TOLERANCE,
        rel_tol=0.0,
    )


def extract_week_scores(
    snapshot: dict[str, Any],
) -> list[DonutWeekScore]:
    """Read donut-pool scores from one stored final snapshot."""

    league_key = snapshot.get("league_key")
    stage = snapshot.get("stage")
    data = snapshot.get("data")

    if (
        not isinstance(league_key, str)
        or not league_key
    ):
        raise DonutPoolError(
            "Snapshot is missing a valid league_key"
        )

    if stage != "final":
        raise DonutPoolError(
            "Donut scoring requires final-stage snapshots. "
            f"Received stage: {stage}"
        )

    if not isinstance(data, dict):
        raise DonutPoolError(
            "Snapshot is missing a valid data object"
        )

    teams = data.get("teams")

    if not isinstance(teams, list) or not teams:
        raise DonutPoolError(
            f"Final snapshot for {league_key} contains no teams"
        )

    scores: list[DonutWeekScore] = []
    seen: set[int] = set()

    for team in teams:
        if not isinstance(team, dict):
            raise DonutPoolError(
                f"Final snapshot for {league_key} contains "
                "an invalid team record"
            )

        roster_id = team.get("roster_id")

        if (
            isinstance(roster_id, bool)
            or not isinstance(roster_id, int)
        ):
            raise DonutPoolError(
                f"Final snapshot for {league_key} contains "
                "a team without an integer roster_id"
            )

        if roster_id in seen:
            raise DonutPoolError(
                f"Duplicate roster {roster_id} in {league_key} "
                "final snapshot"
            )

        seen.add(roster_id)

        manager_name = team.get("manager_name")

        if (
            not isinstance(manager_name, str)
            or not manager_name.strip()
        ):
            manager_name = f"{league_key} roster {roster_id}"

        points = _finite_points(
            team.get("effective_final_points"),
            (
                f"{league_key} roster {roster_id} "
                "effective_final_points"
            ),
        )

        scores.append(
            DonutWeekScore(
                league_key=league_key,
                roster_id=roster_id,
                manager_name=manager_name.strip(),
                points=points,
            )
        )

    return scores


def load_final_week_scores(
    data_root: Path,
    season: str,
    league_keys: tuple[str, ...],
    week: int,
) -> list[DonutWeekScore]:
    """Load one week of donut scores across every pool league."""

    scores: list[DonutWeekScore] = []

    for league_key in league_keys:
        path = build_snapshot_path(
            data_root=data_root,
            season=season,
            league_key=league_key,
            week=week,
            stage="final",
        )

        try:
            snapshot = read_snapshot(path)

        except SnapshotStorageError as exc:
            raise DonutPoolError(
                f"Could not read week {week} final snapshot "
                f"for {league_key}: {exc}"
            ) from exc

        scores.extend(
            extract_week_scores(snapshot)
        )

    return scores


def load_season_week_scores(
    data_root: Path,
    season: str,
    league_keys: tuple[str, ...],
    through_week: int,
) -> tuple[dict[int, list[DonutWeekScore]], list[str]]:
    """Load contiguous completed donut weeks starting at week 1.

    Loading stops at the first week that is not complete for every pool
    league. Skipping a gap would silently corrupt eligibility for every
    later week.
    """

    if through_week < 1:
        raise DonutPoolError(
            "through_week must be at least 1"
        )

    weekly_scores: dict[int, list[DonutWeekScore]] = {}
    warnings: list[str] = []

    for week in range(1, through_week + 1):
        paths = [
            build_snapshot_path(
                data_root=data_root,
                season=season,
                league_key=league_key,
                week=week,
                stage="final",
            )
            for league_key in league_keys
        ]

        missing = [
            path
            for path in paths
            if not path.exists()
        ]

        if missing:
            if len(missing) != len(paths):
                warnings.append(
                    f"Week {week} final snapshots are partially "
                    "available. The donut pool requires every pool "
                    "league before a week can be scored."
                )

            warnings.append(
                f"Donut pool stopped before week {week}. "
                "Later weeks are not evaluated until every earlier "
                "week is complete."
            )

            break

        weekly_scores[week] = load_final_week_scores(
            data_root=data_root,
            season=season,
            league_keys=league_keys,
            week=week,
        )

    return weekly_scores, warnings


def build_entrants(
    scores: list[DonutWeekScore],
) -> tuple[DonutEntrant, ...]:
    """Build the entrant field from one week of scores."""

    if not scores:
        raise DonutPoolError(
            "Cannot build donut entrants from an empty score list"
        )

    entrants: list[DonutEntrant] = []
    seen: set[str] = set()

    for score in scores:
        if score.team_key in seen:
            raise DonutPoolError(
                f"Duplicate donut entrant: {score.team_key}"
            )

        seen.add(score.team_key)

        entrants.append(
            DonutEntrant(
                league_key=score.league_key,
                roster_id=score.roster_id,
                manager_name=score.manager_name,
            )
        )

    return tuple(
        sorted(
            entrants,
            key=lambda entrant: (
                entrant.league_key,
                entrant.roster_id,
            ),
        )
    )


def _season_points_through(
    weekly_scores: dict[int, list[DonutWeekScore]],
    through_week: int,
) -> dict[str, float]:
    """Total each team's resolved points through a given week."""

    totals: dict[str, float] = {}

    for week in sorted(weekly_scores):
        if week > through_week:
            break

        for score in weekly_scores[week]:
            if score.points is None:
                continue

            totals[score.team_key] = (
                totals.get(score.team_key, 0.0)
                + score.points
            )

    return totals


def _resolve_tie(
    tied: list[DonutWeekScore],
    scoring_week: int,
    config: DonutConfig,
    override: dict[str, Any] | None,
    weekly_scores: dict[int, list[DonutWeekScore]],
) -> tuple[list[DonutWeekScore], str, str | None, list[str]]:
    """Apply commissioner override or the configured tie policy."""

    warnings: list[str] = []

    tied_names = ", ".join(
        f"{score.manager_name} ({score.league_key})"
        for score in tied
    )

    if override is not None:
        chosen = [
            score
            for score in tied
            if score.league_key == override["league_key"]
            and score.roster_id == override["roster_id"]
        ]

        if not chosen:
            raise DonutPoolError(
                f"Week {scoring_week} donut override names "
                f"{override['league_key']} roster "
                f"{override['roster_id']}, which is not one of the "
                f"tied teams: {tied_names}"
            )

        return (
            chosen,
            "commissioner_override",
            override["reason"],
            warnings,
        )

    if config.tie_policy == "all_tied":
        warnings.append(
            f"Week {scoring_week} ended in a scoring tie. "
            f"Policy all_tied assigned donut duty to every tied "
            f"team: {tied_names}."
        )

        return (
            list(tied),
            "tie_policy_all_tied",
            (
                "Configured tie policy assigns donut duty to every "
                "tied team."
            ),
            warnings,
        )

    if config.tie_policy == "lowest_season_points":
        totals = _season_points_through(
            weekly_scores=weekly_scores,
            through_week=scoring_week,
        )

        ranked = sorted(
            tied,
            key=lambda score: (
                totals.get(
                    score.team_key,
                    0.0,
                ),
                score.league_key,
                score.roster_id,
            ),
        )

        lowest_total = totals.get(
            ranked[0].team_key,
            0.0,
        )

        still_tied = [
            score
            for score in ranked
            if _scores_tied(
                totals.get(
                    score.team_key,
                    0.0,
                ),
                lowest_total,
            )
        ]

        if len(still_tied) > 1:
            warnings.append(
                f"Week {scoring_week} tie could not be broken by "
                "season points. A commissioner override is required."
            )

            return (
                [],
                "unresolved",
                None,
                warnings,
            )

        warnings.append(
            f"Week {scoring_week} ended in a scoring tie between "
            f"{tied_names}. Policy lowest_season_points selected "
            f"{ranked[0].manager_name}."
        )

        return (
            [ranked[0]],
            "tie_policy_lowest_season_points",
            (
                "Configured tie policy selected the tied team with "
                "the fewest season points."
            ),
            warnings,
        )

    warnings.append(
        f"Week {scoring_week} ended in a scoring tie between "
        f"{tied_names}. No donut was assigned. Commit a commissioner "
        "ruling to data/<season>/donut_overrides.json to continue."
    )

    return (
        [],
        "unresolved",
        None,
        warnings,
    )


def resolve_donut_week(
    scoring_week: int,
    scores: list[DonutWeekScore],
    eligible_keys: set[str],
    config: DonutConfig,
    override: dict[str, Any] | None = None,
    weekly_scores: dict[int, list[DonutWeekScore]] | None = None,
) -> DonutWeekResult:
    """Resolve donut duty for one completed fantasy week."""

    if scoring_week < 1:
        raise DonutPoolError(
            "scoring_week must be at least 1"
        )

    delivery_week = (
        scoring_week
        + config.delivery_offset_weeks
    )

    warnings: list[str] = []

    eligible_before = tuple(
        sorted(eligible_keys)
    )

    score_lookup = {
        score.team_key: score
        for score in scores
    }

    if len(score_lookup) != len(scores):
        raise DonutPoolError(
            f"Week {scoring_week} contains duplicate team scores"
        )

    candidates: list[DonutWeekScore] = []

    for team_key in eligible_before:
        score = score_lookup.get(team_key)

        if score is None:
            warnings.append(
                f"Week {scoring_week} has no score record for "
                f"{team_key}. The team cannot be assigned donut duty "
                "for this week."
            )

            continue

        if score.points is None:
            warnings.append(
                f"Week {scoring_week} score for "
                f"{score.manager_name} ({score.league_key}) is "
                "unresolved. Missing scores are never treated as zero."
            )

            continue

        candidates.append(score)

    if not candidates:
        warnings.append(
            f"Week {scoring_week} produced no eligible scores. "
            "No donut was assigned."
        )

        return DonutWeekResult(
            scoring_week=scoring_week,
            delivery_week=delivery_week,
            status=STATUS_NO_ELIGIBLE_SCORES,
            assignments=(),
            eligible_before=eligible_before,
            eligible_after=eligible_before,
            tied_team_keys=(),
            lowest_points=None,
            warnings=tuple(warnings),
        )

    lowest_points = min(
        score.points
        for score in candidates
        if score.points is not None
    )

    tied = [
        score
        for score in candidates
        if score.points is not None
        and _scores_tied(
            score.points,
            lowest_points,
        )
    ]

    remainder = [
        score.points
        for score in candidates
        if score.points is not None
        and not _scores_tied(
            score.points,
            lowest_points,
        )
    ]

    margin_to_next_lowest = (
        min(remainder) - lowest_points
        if remainder
        else None
    )

    resolution = "lowest_score"
    reason: str | None = None
    chosen = tied
    tie_broken = False

    if len(tied) > 1:
        tie_broken = True

        (
            chosen,
            resolution,
            reason,
            tie_warnings,
        ) = _resolve_tie(
            tied=tied,
            scoring_week=scoring_week,
            config=config,
            override=override,
            weekly_scores=weekly_scores or {},
        )

        warnings.extend(tie_warnings)

    elif override is not None:
        warnings.append(
            f"Week {scoring_week} has a committed donut override but "
            "the week was not tied. The override was ignored."
        )

    if not chosen:
        return DonutWeekResult(
            scoring_week=scoring_week,
            delivery_week=delivery_week,
            status=STATUS_UNRESOLVED_TIE,
            assignments=(),
            eligible_before=eligible_before,
            eligible_after=eligible_before,
            tied_team_keys=tuple(
                sorted(
                    score.team_key
                    for score in tied
                )
            ),
            lowest_points=lowest_points,
            warnings=tuple(warnings),
        )

    assignments = tuple(
        DonutAssignment(
            scoring_week=scoring_week,
            delivery_week=delivery_week,
            league_key=score.league_key,
            roster_id=score.roster_id,
            manager_name=score.manager_name,
            points=(
                score.points
                if score.points is not None
                else lowest_points
            ),
            margin_to_next_lowest=margin_to_next_lowest,
            tie_broken=tie_broken,
            resolution=resolution,
            reason=reason,
        )
        for score in sorted(
            chosen,
            key=lambda item: (
                item.league_key,
                item.roster_id,
            ),
        )
    )

    eliminated_keys = {
        score.team_key
        for score in chosen
    }

    eligible_after = tuple(
        sorted(
            eligible_keys - eliminated_keys
        )
    )

    return DonutWeekResult(
        scoring_week=scoring_week,
        delivery_week=delivery_week,
        status=STATUS_ASSIGNED,
        assignments=assignments,
        eligible_before=eligible_before,
        eligible_after=eligible_after,
        tied_team_keys=tuple(
            sorted(
                score.team_key
                for score in tied
            )
        ),
        lowest_points=lowest_points,
        warnings=tuple(warnings),
    )


def _build_survivors(
    entrants: tuple[DonutEntrant, ...],
    eliminated_keys: set[str],
    weekly_scores: dict[int, list[DonutWeekScore]],
    results: list[DonutWeekResult],
) -> tuple[DonutSurvivor, ...]:
    """Summarize every manager who has avoided donut duty so far."""

    lowest_by_week = {
        result.scoring_week: result.lowest_points
        for result in results
        if result.lowest_points is not None
    }

    survivors: list[DonutSurvivor] = []

    for entrant in entrants:
        if entrant.team_key in eliminated_keys:
            continue

        weeks_survived = 0

        closest_margin: float | None = None
        closest_week: int | None = None

        lowest_points: float | None = None
        lowest_week: int | None = None

        for week in sorted(weekly_scores):
            score = next(
                (
                    item
                    for item in weekly_scores[week]
                    if item.team_key == entrant.team_key
                ),
                None,
            )

            if score is None or score.points is None:
                continue

            weeks_survived += 1

            if (
                lowest_points is None
                or score.points < lowest_points
            ):
                lowest_points = score.points
                lowest_week = week

            week_low = lowest_by_week.get(week)

            if week_low is None:
                continue

            margin = score.points - week_low

            if (
                closest_margin is None
                or margin < closest_margin
            ):
                closest_margin = margin
                closest_week = week

        survivors.append(
            DonutSurvivor(
                league_key=entrant.league_key,
                roster_id=entrant.roster_id,
                manager_name=entrant.manager_name,
                weeks_survived=weeks_survived,
                closest_call_margin=closest_margin,
                closest_call_week=closest_week,
                lowest_weekly_points=lowest_points,
                lowest_weekly_points_week=lowest_week,
            )
        )

    return tuple(
        sorted(
            survivors,
            key=lambda survivor: (
                (
                    survivor.closest_call_margin
                    if survivor.closest_call_margin is not None
                    else math.inf
                ),
                survivor.league_key,
                survivor.roster_id,
            ),
        )
    )


def calculate_donut_pool(
    season: str,
    entrants: tuple[DonutEntrant, ...],
    weekly_scores: dict[int, list[DonutWeekScore]],
    config: DonutConfig,
    overrides: dict[int, dict[str, Any]] | None = None,
    extra_warnings: list[str] | None = None,
) -> DonutPoolState:
    """Walk every completed week and derive full donut-pool state."""

    if not season:
        raise DonutPoolError(
            "season cannot be empty"
        )

    if not entrants:
        raise DonutPoolError(
            "The donut pool requires at least one entrant"
        )

    overrides = overrides or {}

    warnings: list[str] = list(
        extra_warnings or []
    )

    entrant_keys = {
        entrant.team_key
        for entrant in entrants
    }

    expected_entrants = config.total_weeks + 1

    if len(entrants) != expected_entrants:
        warnings.append(
            f"The pool has {len(entrants)} entrants and "
            f"{config.total_weeks} scored weeks. Exactly one "
            "unDOUGHfeated survivor requires "
            f"{expected_entrants} entrants."
        )

    eligible_keys = set(entrant_keys)

    results: list[DonutWeekResult] = []
    eliminated: list[DonutAssignment] = []

    blocked_week: int | None = None
    through_week = 0

    for week in sorted(weekly_scores):
        scores = weekly_scores[week]

        unknown = {
            score.team_key
            for score in scores
        } - entrant_keys

        if unknown:
            raise DonutPoolError(
                f"Week {week} contains teams that are not donut "
                f"entrants: {', '.join(sorted(unknown))}"
            )

        if blocked_week is not None:
            results.append(
                DonutWeekResult(
                    scoring_week=week,
                    delivery_week=(
                        week
                        + config.delivery_offset_weeks
                    ),
                    status=STATUS_BLOCKED,
                    assignments=(),
                    eligible_before=tuple(
                        sorted(eligible_keys)
                    ),
                    eligible_after=tuple(
                        sorted(eligible_keys)
                    ),
                    tied_team_keys=(),
                    lowest_points=None,
                    warnings=(
                        (
                            f"Week {week} was not evaluated because "
                            f"week {blocked_week} is unresolved."
                        ),
                    ),
                )
            )

            continue

        if not eligible_keys:
            warnings.append(
                f"Every entrant had been assigned donut duty before "
                f"week {week}. The pool is already complete."
            )

            break

        result = resolve_donut_week(
            scoring_week=week,
            scores=scores,
            eligible_keys=eligible_keys,
            config=config,
            override=overrides.get(week),
            weekly_scores=weekly_scores,
        )

        results.append(result)

        warnings.extend(result.warnings)

        through_week = week

        if result.status == STATUS_UNRESOLVED_TIE:
            blocked_week = week

            continue

        eliminated.extend(result.assignments)

        eligible_keys = set(result.eligible_after)

    eliminated_keys = {
        f"{assignment.league_key}:{assignment.roster_id}"
        for assignment in eliminated
    }

    survivors = _build_survivors(
        entrants=entrants,
        eliminated_keys=eliminated_keys,
        weekly_scores=weekly_scores,
        results=results,
    )

    next_delivery = (
        eliminated[-1]
        if eliminated
        else None
    )

    complete = (
        blocked_week is None
        and through_week >= config.total_weeks
    )

    undoughfeated = (
        survivors[0]
        if complete and len(survivors) == 1
        else None
    )

    return DonutPoolState(
        season=season,
        through_week=through_week,
        total_weeks=config.total_weeks,
        tie_policy=config.tie_policy,
        entrants=entrants,
        results=tuple(results),
        eliminated=tuple(eliminated),
        survivors=survivors,
        next_delivery=next_delivery,
        undoughfeated=undoughfeated,
        complete=complete,
        blocked_week=blocked_week,
        warnings=tuple(warnings),
    )


def build_donut_pool_from_snapshots(
    data_root: Path,
    season: str,
    config: DonutConfig,
    through_week: int,
    overrides_path: Path | None = None,
) -> DonutPoolState:
    """Derive donut-pool state directly from stored final snapshots."""

    weekly_scores, warnings = load_season_week_scores(
        data_root=data_root,
        season=season,
        league_keys=config.leagues,
        through_week=through_week,
    )

    if not weekly_scores:
        raise DonutPoolError(
            "No completed final snapshots are available for the "
            "donut pool"
        )

    first_week = min(weekly_scores)

    entrants = build_entrants(
        weekly_scores[first_week]
    )

    overrides = (
        load_donut_overrides(overrides_path)
        if overrides_path is not None
        else {}
    )

    return calculate_donut_pool(
        season=season,
        entrants=entrants,
        weekly_scores=weekly_scores,
        config=config,
        overrides=overrides,
        extra_warnings=warnings,
    )


def build_donut_agent_context(
    state: DonutPoolState,
) -> dict[str, Any]:
    """Build replaceable AI-agent context for the donut pool."""

    return {
        "donut_pool_format_version": 1,
        "season": state.season,
        "through_week": state.through_week,
        "total_weeks": state.total_weeks,
        "tie_policy": state.tie_policy,
        "complete": state.complete,
        "blocked_week": state.blocked_week,
        "entrant_count": len(state.entrants),
        "survivor_count": len(state.survivors),
        "next_delivery": (
            {
                "scoring_week": (
                    state.next_delivery.scoring_week
                ),
                "delivery_week": (
                    state.next_delivery.delivery_week
                ),
                "league_key": (
                    state.next_delivery.league_key
                ),
                "roster_id": (
                    state.next_delivery.roster_id
                ),
                "manager_name": (
                    state.next_delivery.manager_name
                ),
                "points": state.next_delivery.points,
                "margin_to_next_lowest": (
                    state.next_delivery.margin_to_next_lowest
                ),
            }
            if state.next_delivery is not None
            else None
        ),
        "undoughfeated": (
            {
                "league_key": (
                    state.undoughfeated.league_key
                ),
                "roster_id": (
                    state.undoughfeated.roster_id
                ),
                "manager_name": (
                    state.undoughfeated.manager_name
                ),
                "weeks_survived": (
                    state.undoughfeated.weeks_survived
                ),
            }
            if state.undoughfeated is not None
            else None
        ),
        "eliminated": [
            {
                "scoring_week": assignment.scoring_week,
                "delivery_week": assignment.delivery_week,
                "league_key": assignment.league_key,
                "roster_id": assignment.roster_id,
                "manager_name": assignment.manager_name,
                "points": assignment.points,
                "margin_to_next_lowest": (
                    assignment.margin_to_next_lowest
                ),
                "tie_broken": assignment.tie_broken,
                "resolution": assignment.resolution,
                "reason": assignment.reason,
            }
            for assignment in state.eliminated
        ],
        "survivors": [
            {
                "league_key": survivor.league_key,
                "roster_id": survivor.roster_id,
                "manager_name": survivor.manager_name,
                "weeks_survived": survivor.weeks_survived,
                "closest_call_margin": (
                    survivor.closest_call_margin
                ),
                "closest_call_week": (
                    survivor.closest_call_week
                ),
                "lowest_weekly_points": (
                    survivor.lowest_weekly_points
                ),
                "lowest_weekly_points_week": (
                    survivor.lowest_weekly_points_week
                ),
            }
            for survivor in state.survivors
        ],
        "weeks": [
            {
                "scoring_week": result.scoring_week,
                "delivery_week": result.delivery_week,
                "status": result.status,
                "lowest_points": result.lowest_points,
                "tied_team_keys": list(
                    result.tied_team_keys
                ),
                "eligible_before": len(
                    result.eligible_before
                ),
                "eligible_after": len(
                    result.eligible_after
                ),
                "warnings": list(result.warnings),
            }
            for result in state.results
        ],
        "warnings": list(state.warnings),
    }
