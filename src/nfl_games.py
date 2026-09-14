"""NFL game-state provider for remaining-player analytics."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests


class NFLGameAPIError(RuntimeError):
    """Raised when NFL game-state data cannot be loaded safely."""


@dataclass(frozen=True)
class NFLGame:
    """One NFL game."""

    game_id: str
    season: int
    week: int
    kickoff: datetime
    away_team: str
    home_team: str
    status: str


@dataclass(frozen=True)
class TeamGameState:
    """Resolved game state for one NFL team."""

    team: str
    game_id: str | None
    kickoff: datetime | None
    opponent: str | None
    status: str


TEAM_ALIASES = {
    "JAC": "JAX",
    "WSH": "WAS",
    "LA": "LAR",
    "STL": "LAR",
    "OAK": "LV",
    "SD": "LAC",
}


def normalize_team_abbreviation(
    value: str,
) -> str:
    """Normalize NFL team abbreviations."""

    team = value.strip().upper()

    return TEAM_ALIASES.get(
        team,
        team,
    )


def normalize_game_status(
    value: str | None,
) -> str:
    """Normalize provider-specific game state."""

    if not isinstance(
        value,
        str,
    ):
        return "unknown"

    state = value.strip().lower()

    if state in {
        "pre",
        "scheduled",
        "created",
    }:
        return "scheduled"

    if state in {
        "in",
        "live",
        "in_progress",
    }:
        return "in_progress"

    if state in {
        "post",
        "final",
        "closed",
    }:
        return "final"

    return "unknown"


def parse_kickoff(
    value: Any,
) -> datetime:
    """Parse an ISO-8601 kickoff timestamp."""

    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise NFLGameAPIError(
            "NFL game is missing a valid kickoff timestamp"
        )

    raw = value.strip()

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        kickoff = datetime.fromisoformat(
            raw
        )
    except ValueError as exc:
        raise NFLGameAPIError(
            f"Invalid NFL kickoff timestamp: {value!r}"
        ) from exc

    if kickoff.tzinfo is None:
        raise NFLGameAPIError(
            "NFL kickoff timestamp must include a timezone"
        )

    return kickoff


def parse_espn_game(
    event: dict[str, Any],
    *,
    season: int,
    week: int,
) -> NFLGame:
    """Normalize one ESPN scoreboard event."""

    game_id = event.get("id")

    if (
        not isinstance(game_id, str)
        or not game_id
    ):
        raise NFLGameAPIError(
            "NFL event is missing an id"
        )

    competitions = event.get(
        "competitions"
    )

    if (
        not isinstance(competitions, list)
        or not competitions
        or not isinstance(
            competitions[0],
            dict,
        )
    ):
        raise NFLGameAPIError(
            f"NFL event {game_id} "
            "is missing competition data"
        )

    competition = competitions[0]

    competitors = competition.get(
        "competitors"
    )

    if not isinstance(
        competitors,
        list,
    ):
        raise NFLGameAPIError(
            f"NFL event {game_id} "
            "is missing competitors"
        )

    home_team: str | None = None
    away_team: str | None = None

    for competitor in competitors:
        if not isinstance(
            competitor,
            dict,
        ):
            continue

        side = competitor.get(
            "homeAway"
        )

        team_data = competitor.get(
            "team"
        )

        if not isinstance(
            team_data,
            dict,
        ):
            continue

        abbreviation = team_data.get(
            "abbreviation"
        )

        if (
            not isinstance(
                abbreviation,
                str,
            )
            or not abbreviation
        ):
            continue

        normalized = (
            normalize_team_abbreviation(
                abbreviation
            )
        )

        if side == "home":
            home_team = normalized

        elif side == "away":
            away_team = normalized

    if (
        home_team is None
        or away_team is None
    ):
        raise NFLGameAPIError(
            f"NFL event {game_id} "
            "is missing home/away teams"
        )

    status_data = event.get(
        "status"
    )

    state: str | None = None

    if isinstance(
        status_data,
        dict,
    ):
        type_data = status_data.get(
            "type"
        )

        if isinstance(
            type_data,
            dict,
        ):
            raw_state = type_data.get(
                "state"
            )

            if isinstance(
                raw_state,
                str,
            ):
                state = raw_state

    kickoff_value = (
        competition.get("date")
        or event.get("date")
    )

    kickoff = parse_kickoff(
        kickoff_value
    )

    return NFLGame(
        game_id=game_id,
        season=season,
        week=week,
        kickoff=kickoff,
        away_team=away_team,
        home_team=home_team,
        status=normalize_game_status(
            state
        ),
    )


def build_team_game_state_lookup(
    games: list[NFLGame],
) -> dict[str, TeamGameState]:
    """Build one game-state record per NFL team."""

    result: dict[
        str,
        TeamGameState,
    ] = {}

    for game in games:
        sides = (
            (
                game.away_team,
                game.home_team,
            ),
            (
                game.home_team,
                game.away_team,
            ),
        )

        for team, opponent in sides:
            if team in result:
                raise NFLGameAPIError(
                    "Multiple games found "
                    f"for NFL team {team}"
                )

            result[team] = TeamGameState(
                team=team,
                game_id=game.game_id,
                kickoff=game.kickoff,
                opponent=opponent,
                status=game.status,
            )

    return result


def unknown_team_game_state(
    team: str,
) -> TeamGameState:
    """Return an explicit unresolved game state."""

    normalized = (
        normalize_team_abbreviation(
            team
        )
    )

    return TeamGameState(
        team=normalized,
        game_id=None,
        kickoff=None,
        opponent=None,
        status="unknown",
    )


class ESPNNFLGameProvider:
    """Read NFL schedule/game-state data from ESPN."""

    BASE_URL = (
        "https://site.api.espn.com/apis/"
        "site/v2/sports/football/nfl/"
        "scoreboard"
    )

    def __init__(
        self,
        timeout: float = 30.0,
    ) -> None:
        self.timeout = timeout

    def _get(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=self.timeout,
            )

            response.raise_for_status()

        except requests.RequestException as exc:
            raise NFLGameAPIError(
                "Could not load NFL schedule data"
            ) from exc

        try:
            payload = response.json()

        except ValueError as exc:
            raise NFLGameAPIError(
                "NFL schedule response "
                "was not valid JSON"
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise NFLGameAPIError(
                "NFL schedule response "
                "must be a JSON object"
            )

        return payload

    def get_week_games(
        self,
        *,
        season: int,
        week: int,
        season_type: int = 2,
    ) -> list[NFLGame]:
        """Fetch and normalize games for one NFL week."""

        payload = self._get(
            {
                "dates": season,
                "seasontype": season_type,
                "week": week,
                "limit": 100,
            }
        )

        events = payload.get(
            "events"
        )

        if not isinstance(
            events,
            list,
        ):
            raise NFLGameAPIError(
                "NFL schedule response "
                "is missing events"
            )

        games: list[NFLGame] = []

        for event in events:
            if not isinstance(
                event,
                dict,
            ):
                continue

            games.append(
                parse_espn_game(
                    event,
                    season=season,
                    week=week,
                )
            )

        if not games:
            raise NFLGameAPIError(
                "No NFL games found for "
                f"season={season} week={week}"
            )

        return games

    def get_team_states(
        self,
        *,
        season: int,
        week: int,
        season_type: int = 2,
    ) -> dict[str, TeamGameState]:
        """Fetch game states for every NFL team."""

        games = self.get_week_games(
            season=season,
            week=week,
            season_type=season_type,
        )

        return build_team_game_state_lookup(
            games
        )

    def get_team_game_state(
        self,
        team: str,
        *,
        season: int,
        week: int,
        season_type: int = 2,
    ) -> TeamGameState:
        """Resolve one NFL team's weekly game state."""

        normalized = (
            normalize_team_abbreviation(
                team
            )
        )

        states = self.get_team_states(
            season=season,
            week=week,
            season_type=season_type,
        )

        return states.get(
            normalized,
            unknown_team_game_state(
                normalized
            ),
        )