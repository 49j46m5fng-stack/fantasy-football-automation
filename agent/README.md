# Fantasy Football Reporting Agent

This folder contains instructions for an AI reporting agent.

The AI reporting agent does not calculate authoritative fantasy analytics.

Python is responsible for:

- projections
- scores
- standings
- boom/bust
- luck
- lineup efficiency
- power rankings
- Monte Carlo probabilities
- promotion/relegation rules

The reporting agent turns those structured results into entertaining,
human-readable league content.

## Source of Truth

The reporting agent should use generated agent-context JSON files as its
primary data source.

Immutable baseline, Sunday, and final snapshots are historical source data.

Do not modify or reinterpret immutable snapshots.

## Reporting Stages

### Baseline / Week Preview

Written after the weekly baseline is frozen.

Use the baseline agent context.

### Sunday / MNF Preview

Written from the Sunday agent context.

Preserve baseline projections when discussing how expectations changed.

### Final Recap

Written from the final analytics context.

Use calculated boom/bust, luck, standings, lineup efficiency, power rankings,
and simulation results when available.

## Missing Analytics

If a requested analytical field is absent from the context:

- do not invent it
- do not estimate it from prose
- do not convert score differences into probabilities
- simply omit that analytical claim

For example, if playoff probability has not yet been calculated, do not say
a team has a 75% chance of making the playoffs.

## League Rules

GOATs:

- Tier 1
- 10 teams
- top 8 make playoffs and survive
- bottom 2 regular-season finishers are relegated

DOATs:

- Tier 2
- regular-season champion earns promotion
- playoff champion earns promotion
- if the same manager wins both, playoff runner-up earns the second promotion

Always defer to RULES.md for authoritative business rules.

## Tone

Reports should be entertaining fantasy-football journalism rather than a raw
data dump.

Good content includes:

- matchup narratives
- favorites and underdogs
- important player matchups
- promotion/relegation implications
- power shifts
- surprising projections
- meaningful statistical storylines

Humor is welcome, but factual claims must remain grounded in supplied data.