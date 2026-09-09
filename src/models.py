"""Internal data models used throughout the fantasy project."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FantasyRoster:
    """Normalized representation of one fantasy roster."""

    league_key: str
    league_id: str
    roster_id: int
    owner_id: str | None
    manager_name: str


@dataclass(frozen=True)
class FantasyMatchup:
    """Normalized pairing of two fantasy rosters."""

    league_key: str
    league_id: str
    week: int
    matchup_id: int
    roster_a_id: int
    roster_b_id: int

    def opponent_of(self, roster_id: int) -> int:
        """Return the opponent roster ID for one side of the matchup."""

        if roster_id == self.roster_a_id:
            return self.roster_b_id

        if roster_id == self.roster_b_id:
            return self.roster_a_id

        raise ValueError(
            f"Roster {roster_id} is not part of matchup {self.matchup_id}"
        )