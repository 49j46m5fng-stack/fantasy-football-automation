# Architecture

## Purpose

This project automates analytics and reporting for two Sleeper fantasy football leagues operating as a promotion/relegation pyramid:

- GOATs — Tier 1
- DOATs — Tier 2

The architecture prioritizes correctness, historical preservation, and beginner-friendly maintenance.

## Core Principles

1. Correctness before automation.
2. Historical data must be preserved.
3. Baseline snapshots are immutable.
4. External API access is separated from analysis logic.
5. League rules are separated from API code.
6. Report formatting is separated from calculations.
7. Automated commands must be safe to rerun.
8. Missing or questionable data should produce visible warnings.
9. Important business rules require automated tests.
10. Prefer standard Python and simple files before adding infrastructure.

## Planned Layers

### External Data

Responsible for communicating with outside systems.

Planned modules include:

- Sleeper league API client
- projection provider
- NFL schedule/game-status provider

External API response formats should not leak unnecessarily into analysis code.

### Normalization

Converts external API records into consistent internal structures for:

- leagues
- managers
- rosters
- players
- starters
- matchups
- standings
- projections
- scores

### Storage

Stores durable structured records.

Initial storage formats:

- JSON for detailed weekly snapshots
- CSV for season-long analytical tables
- Markdown for human-readable reports

SQLite may be considered later if multi-season analysis becomes cumbersome with files.

### Rules and Analytics

Contains calculations that do not directly perform HTTP requests.

Examples:

- matchup pairing
- projection aggregation
- boom/bust classification
- GOATs relegation
- DOATs promotion
- win-probability simulations

### Reports

Generates human-readable Markdown from structured data.

Reports should not independently fetch data when the needed information already exists in stored snapshots.

### Orchestration

A future command-line interface will coordinate the other layers.

Planned commands include:

python fantasy.py baseline

python fantasy.py sunday

python fantasy.py final

These commands should operate on both leagues by default.

## Weekly Data Flow

### Baseline

External APIs
→ normalized data
→ immutable baseline snapshot
→ preview report

### Sunday

External APIs
+ stored baseline
→ Sunday snapshot
→ expected-final calculations
→ win-probability simulation
→ Sunday/MNF report

### Final

External APIs
+ stored baseline
+ final starters/results
→ final snapshot
→ history tables
→ final recap

## Idempotency

Running a command multiple times should not silently corrupt historical data.

The most important example is baseline creation.

If a weekly baseline already exists, baseline creation should refuse to replace it.

## Current Status

The repository contains configuration, documentation, test infrastructure, documented Sleeper API access, normalized roster/matchup models, cached NFL player metadata, and an isolated projection provider.

The project currently supports:

- league metadata
- league users
- league rosters
- weekly matchup records
- owner-to-manager normalization
- two-roster matchup pairing
- cached Sleeper NFL player metadata
- player-ID-to-name lookup
- weekly projection retrieval
- normalization of known projection response shapes
- safe detection of missing projected-point fields
- explicit handling of empty Sleeper starter slots
- projection/scoring compatibility auditing
- projection-feed category preservation
- default filtering to the `proj` category
- duplicate-safe player projection lookup
- starter-only fantasy-team projection aggregation
- explicit Out-player zero projection handling
- auditable week-specific projection overrides
- incomplete-projection detection
- empty-lineup-slot warnings
- canonical season/league/week snapshot paths
- versioned snapshot metadata envelopes
- exclusive immutable snapshot writes
- historical snapshot validation and reading

The Sleeper projection feed is treated as an unofficial external dependency and is isolated from the documented Sleeper API client.

Real baseline snapshot construction, standings logic, win-probability analytics, and report generation have not yet been implemented.