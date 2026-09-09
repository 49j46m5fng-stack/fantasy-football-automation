# Fantasy Football Automation — Core Rules

This file contains business rules that should not be changed casually.

Changes to these rules should include corresponding test changes.

## GOATs

GOATs is Tier 1.

For the 2026 season:

- 10 teams participate.
- The top 8 regular-season finishers make the playoffs.
- The top 8 remain in GOATs for the following season.
- The bottom 2 regular-season finishers are relegated to DOATs.

The last safe position is therefore 8th place.

Positions 9 and 10 are the relegation zone.

Standings tiebreakers must not be invented by this project.
Sleeper league configuration and documented behavior must be inspected before custom tiebreaker logic is implemented.

## DOATs

DOATs is Tier 2.

Exactly two managers are promoted each season.

### Promotion Slot 1

The DOATs regular-season champion is promoted.

### Promotion Slot 2

The DOATs playoff champion is promoted unless that manager already earned promotion by winning the regular season.

If the same manager wins both the regular-season championship and playoff championship, the playoff runner-up receives the second promotion slot.

Therefore there should always be:

- 2 GOATs managers relegated
- 2 DOATs managers promoted

Promotion reasons should eventually be recorded as:

- regular_season_champion
- playoff_champion
- playoff_runner_up_duplicate_champion_rule

## Weekly Baseline

The weekly baseline represents information frozen before the first NFL game of the fantasy week.

A baseline must preserve at least:

- baseline starting lineup
- baseline player projections
- baseline team projection
- matchup information

Once a baseline snapshot has been created, normal program execution must not overwrite it.

Baseline immutability is a core system invariant.

### Missing Projection Data

Missing projected points must not be silently converted to zero.

The system should distinguish between:

- a real projection of 0.0
- a projection record with no usable fantasy-point field
- no projection record at all

Reports should flag missing projection data visibly.

### Empty Starting Slots

Raw starting-lineup arrays should be preserved in snapshots.

Empty Sleeper starter values such as `0` or null must not be treated as player IDs.

Reports should flag an incomplete starting lineup when relevant.

## Later Snapshots

Later projections and scores must be stored separately from the baseline.

Examples include:

- baseline_projection
- sunday_projection
- live_projection
- final_actual

Changing projections later in the week must never alter the original baseline.

## Boom / Bust

Initial player performance ratio:

actual_points / baseline_projection

Initial classifications:

### BOOM

Actual points are at least 1.50 times baseline projection.

### HIT / NORMAL

Actual points are at least 0.80 times baseline projection and less than 1.50 times baseline projection.

### BUST

Actual points are less than 0.80 times baseline projection.

Zero and near-zero projections require special handling and must not cause division-by-zero or misleading ratios.

Thresholds are configurable in config.json.

## Historical Data

Historical weekly snapshots are evidence.

They should not be silently rewritten because projection sources, scoring logic, manager names, or APIs change in the future.

If a correction system is introduced later, corrections should preserve the original historical record.