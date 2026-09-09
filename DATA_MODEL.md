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

## Snapshot File Layout

Official weekly snapshots use the path convention:

data/{season}/{league_key}/week_{week}_{stage}.json

Examples:

data/2026/goats/week_01_baseline.json

data/2026/goats/week_01_sunday.json

data/2026/goats/week_01_final.json

Each stored snapshot has a metadata envelope containing:

- schema_version
- season
- week
- league_key
- league_id
- stage
- created_at
- data

The `data` object contains the stage-specific fantasy information.

Official snapshots are created with exclusive-write semantics and must not be silently overwritten.

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
Each baseline starter should eventually preserve:

- starter slot
- player_id
- player name
- position
- projected points
- projection source
- projection reason when applicable

Projection source examples:

- sleeper_pts_ppr
- sleeper_out_zero
- manual_override
- empty_slot

If a projection cannot be resolved safely, the baseline-generation process should flag it rather than silently substituting zero.

## Detailed Baseline Contents

The baseline should preserve both calculated outputs and the source information needed to explain them later.

Each league baseline includes:

- league configuration
- scoring settings
- roster positions
- raw users
- raw rosters
- raw matchup records
- normalized matchup pairings
- manager identity
- raw baseline starter IDs
- rostered player IDs
- starter-level projected points
- projection source and reason
- raw projected statistical fields
- baseline fantasy-team projection
- projection completeness
- warnings
- first-kickoff capture context

Baseline projections for rostered bench players are also retained where available.

This allows future lineup-change and start/sit analysis to use the projections that existed at baseline rather than later projection values.

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

## Baseline-to-Sunday Comparison

Sunday team records will expose:

- `stage_starters_raw`
- `stage_projection`
- `rostered_players`
- `warnings`

The comparison layer produces, per roster:

- baseline starters
- Sunday starters
- added starters
- removed starters
- slot changes
- baseline team projection
- Sunday team projection
- team projection delta
- changed player projections
- baseline warnings
- Sunday warnings

Player projection changes preserve whether the player was present on the roster in each snapshot.

A projection delta is calculated only when both stored point values are numeric.

## Sunday Snapshot

The Sunday stage preserves the current fantasy state without modifying the baseline.

Each Sunday team record includes:

- roster_id
- manager identity
- matchup_id
- opponent roster_id
- stage_starters_raw
- rostered_player_ids
- live_points
- custom_points
- effective_live_points
- stage_projection
- known_projected_points
- projection completeness
- warnings
- detailed starter projections
- detailed rostered-player projections

`live_points` preserves Sleeper's normal team score.

If Sleeper exposes a numeric `custom_points` commissioner override, `effective_live_points` uses the override. Otherwise it uses `live_points`.

A missing live score remains null and must not silently become zero.

### Sunday Projection Semantics

`stage_projection` currently means the sum of the fresh Sleeper `pts_ppr` values for the current starting lineup.

It is not yet an actual-points-plus-remaining-points forecast.

The project must not claim that Sleeper's supplied weekly projection represents remaining in-game production unless that behavior has been explicitly verified.

Raw Sunday matchup data is retained so richer live scoring logic can be added later without reconstructing history.

### Sunday Capture Context

The official Sunday snapshot capture context should preserve:

- local and UTC capture timestamps
- timezone
- stage label
- MNF game identity
- MNF kickoff timestamp
- capture purpose

For the current workflow, the stage label is `sunday_pre_mnf`.

## AI Agent Context

AI-agent context is derived data, not historical source data.

Canonical files are:

- `data/{season}/agent/week_{week}_baseline.json`
- `data/{season}/agent/week_{week}_sunday.json`
- later: `data/{season}/agent/week_{week}_final.json`

The immutable stage snapshots remain authoritative.

Agent context may be regenerated and atomically replaced whenever its formatter improves.

Agent context includes:

- both league definitions and competition rules
- manager identities
- matchup structure
- starter projections
- compact rostered-player projection data
- special projection-resolution notes
- warnings
- precomputed matchup margins
- source snapshot hashes

Sunday context additionally includes:

- live team scores
- current starter projections
- baseline-to-Sunday lineup substitutions
- lineup-slot changes
- player projection movement
- team projection movement

Missing values remain null.

The Sunday current-starter projection must not be described as a final-score or remaining-game forecast. 

## Final Snapshot

The final stage preserves the post-MNF fantasy result for the week.

Each final team record contains:

- roster_id
- owner identity
- manager name
- matchup_id
- opponent roster_id
- final_starters_raw
- rostered_player_ids
- final_points
- custom_points
- effective_final_points
- starter metadata
- rostered-player metadata
- warnings

Each final matchup includes:

- both roster IDs
- both effective final scores
- score completeness
- winner roster ID
- loser roster ID
- final margin
- tie state

A missing final score remains null.

The final snapshot does not currently normalize per-player actual fantasy points.
Raw Sleeper matchup data is retained so player-level scoring can be added after
the source semantics are verified.