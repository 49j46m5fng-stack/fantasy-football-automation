# Data Model

This document describes the planned durable data structures.

The exact JSON schema may evolve while the project is being built, but historical compatibility should be preserved whenever practical.

## Snapshot Identity

Every weekly snapshot should be identifiable by:

- schema version
- season
- week
- league
- league ID
- stage
- creation timestamp

Valid stages will initially include:

- baseline
- sunday
- final

## League Snapshot

A league snapshot will eventually contain information such as:

- league settings
- scoring settings
- managers
- rosters
- matchups
- standings
- starter player IDs
- player metadata
- player projections
- fantasy scores
- warnings

## Baseline Team Data

Each fantasy team should eventually preserve:

- roster_id
- owner_id
- manager name
- baseline starters
- baseline player projections
- baseline team projection
- opponent roster_id
- opening modeled win probability

## Sunday Team Data

Sunday data should preserve the baseline and add information such as:

- current score
- completed starters
- remaining starters
- projected remaining points
- expected final score
- Sunday modeled win probability

## Final Team Data

Final data should include:

- baseline starters
- final starters
- final score
- result
- baseline variance
- percentage variance
- standings information

Keeping both baseline and final starters will allow future lineup-change and start/sit analysis.

## Player-Week History

The planned player_weeks.csv will contain fields such as:

- season
- week
- league
- roster_id
- manager
- player_id
- player_name
- position
- baseline_projection
- actual_points
- variance
- variance_pct
- performance_ratio
- classification

## Team-Week History

The planned team_weeks.csv will contain fields such as:

- season
- week
- league
- roster_id
- manager
- baseline_projection
- sunday_projection
- actual_score
- baseline_variance
- variance_pct
- opening_win_probability
- sunday_win_probability
- result

## Promotion / Relegation History

The planned promotion_relegation.csv will preserve:

- season
- league
- manager
- final_regular_season_rank
- playoff_finish
- promoted
- relegated
- promotion_reason
- relegation_reason

Season-ending promotion and relegation results should be stored rather than reconstructed from a future Sleeper league.