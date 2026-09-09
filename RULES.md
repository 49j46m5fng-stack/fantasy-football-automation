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

### Missing Projected-Point Resolution

For the initial Sleeper `pts_ppr` projection model:

1. If `pts_ppr` exists, use it.
2. If `pts_ppr` is absent and Sleeper explicitly reports the player as `Out`, use 0.0.
3. A documented week-specific manual override may be used when reliable league information confirms a zero projection but Sleeper metadata is inconsistent.
4. Otherwise, missing `pts_ppr` remains unresolved and must not silently become zero.

Projection overrides must be stored in a committed historical file with a written reason.

### MVP Projection Method

The initial team projection model uses Sleeper's supplied `pts_ppr` field.

This is appropriate as an MVP because GOATs and DOATs use identical full-PPR scoring.

It must not be represented as exact custom-league scoring.

Kicker and defense scoring in particular may differ from the generic supplied projection because not every league scoring category is available as a raw projected statistic.

Future exact scoring should calculate projected fantasy points from raw projected statistics and the league's retrieved `scoring_settings` wherever practical.

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

### Snapshot Immutability

Official baseline, Sunday, and final snapshots are historical records.

Normal execution must create these files only when they do not already exist.

If the target snapshot already exists, the program must stop with a visible error rather than replace it.

There is intentionally no general `--force` overwrite behavior in the MVP.

If a historical correction process is needed later, it should preserve the original record and create an auditable correction rather than silently replacing history.

## Lineup Change Comparison

Baseline-to-Sunday lineup changes are determined from stored snapshot starter IDs.

A player is an added starter when the player appears in the populated Sunday starting lineup but not in the populated baseline starting lineup.

A player is a removed starter when the player appears in the populated baseline starting lineup but not in the populated Sunday starting lineup.

Moving an existing starter between lineup slots is recorded as a slot change but is not by itself a start/sit substitution.

Empty starter values such as `0` or null remain empty slots and are never treated as player IDs.

## Projection Movement

Projection movement must compare values stored in the two historical snapshots.

Current live projection data must not be substituted for either historical value.

If either historical projection is unresolved, projection delta remains unresolved rather than treating the missing value as zero.

## Sunday Stage

The Sunday snapshot is separate from the immutable baseline.

Capturing Sunday data must never alter or regenerate the baseline.

Sunday lineup membership is taken from the current Sleeper matchup `starters` field.

Sleeper team `points` are preserved as the live team score.

If a commissioner `custom_points` override is present, it is preserved separately and may be used as the effective displayed live score.

Missing live points must remain missing rather than silently becoming zero.

### Sunday Forecast Safety

The initial Sunday `stage_projection` is the current supplied projection total for the current starting lineup.

It must not be described as a mathematically derived remaining-game forecast.

A future remaining-projection model must explicitly document its data source and calculation.

## Official Sunday/MNF Capture

The official Sunday stage is a post-Sunday, pre-MNF checkpoint.

For 2026 Week 1, the target capture window is Monday before the standalone Monday Night Football game.

The snapshot must preserve the current live team scores, current starters, current roster, fresh projection-feed records, warnings, and raw Sleeper matchup records.

Incomplete Sunday projection data does not invalidate the snapshot. Missing values must be preserved as missing.

Undocumented Sleeper response fields may be retained in raw source data, but they must not become business-rule inputs until their semantics have been independently verified.

## AI Narrative Boundary

Python owns factual data collection, normalization, historical storage, rules, calculations, and analytics.

The AI agent owns narrative previews, recaps, commentary, and editorial presentation.

The AI should consume derived agent-context data rather than reconstructing facts from live APIs.

Agent context must be derived only from stored snapshots and deterministic analytics.

The AI must not silently convert null or unresolved values to zero.

Agent-context files are replaceable derived artifacts. Immutable stage snapshots are not.

## Final Stage

The final snapshot records the platform-reported post-MNF weekly result.

Final capture must not alter the baseline or Sunday snapshots.

A final snapshot requires the immutable baseline to exist.

A missing Sunday snapshot does not block final capture; losing final historical
truth would be worse than losing the intermediate Sunday checkpoint.

Official final capture refuses incomplete team scores.

Commissioner custom_points are preserved separately and become the effective
final score when present.

Per-player actual fantasy points must not be inferred from team totals.

## Performance and Lineup Analytics

Boom/bust compares the frozen baseline `pts_ppr` projection with the
player's actual Sleeper `pts_ppr`.

This is intentionally an apples-to-apples comparison.

Boom/bust thresholds are:

- boom: actual >= 1.50 x baseline projection
- normal: actual >= 0.80 x baseline projection and < 1.50 x
- bust: actual < 0.80 x baseline projection
- low_projection: baseline projection is below the configured minimum
  projection for ratio analysis
- unresolved: either projection or actual PPR value is unavailable

Exact league scoring is used separately for lineup analytics.

Lineup efficiency uses the final roster and final starting lineup, not
the frozen baseline roster.

The optimal lineup must satisfy the stored league roster positions.

FLEX accepts RB, FB, WR, and TE.

An empty lineup slot is a known zero-point lineup decision. A missing
player actual is unresolved and must never silently become zero.

Points left on the bench are:

`optimal exact lineup points - actual exact lineup points`

Lineup efficiency is:

`actual exact lineup points / optimal exact lineup points`

Exact final starter totals are compared with Sleeper's unadjusted
`final_points` as a scoring reconciliation check.

## All-Play and Luck

All-play compares each fantasy team's completed weekly score against
every other fantasy team in the same league.

For each comparison:

- higher score = all-play win
- equal score = all-play tie
- lower score = all-play loss

Weekly expected wins are:

`(all_play_wins + 0.5 * all_play_ties) / (league_team_count - 1)`

A scheduled win is worth 1.0 actual win equivalent.

A scheduled tie is worth 0.5 actual win equivalent.

A scheduled loss is worth 0.0 actual win equivalent.

Luck wins are:

`actual_win_equivalent - expected_wins`

Positive luck means the actual schedule produced more wins than the
team's all-play scoring performance would suggest.

Negative luck means the actual schedule produced fewer wins than the
team's all-play scoring performance would suggest.

Luck is a schedule-result metric. It is not a claim about managerial
skill or randomness in individual player outcomes.

Season analytical rank currently sorts by:

1. actual win equivalent
2. points for
3. roster ID

Analytical rank is not labeled as official Sleeper playoff seeding.