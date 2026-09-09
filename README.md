# Fantasy Football Automation

Automated analytics and reporting for the GOATs and DOATs Sleeper fantasy football leagues.

## Leagues

### GOATs

Tier 1.

Sleeper League ID:

1400610465024839680

The top 8 regular-season teams remain in GOATs and make the playoffs.

The bottom 2 are relegated to DOATs.

### DOATs

Tier 2.

Sleeper League ID:

1400610568489947136

Two managers are promoted each season:

1. Regular-season champion
2. Playoff champion

If the same manager wins both championships, the playoff runner-up receives the second promotion slot.

See RULES.md for the authoritative business rules.

## Project Goals

The system will eventually:

- collect Sleeper fantasy data
- freeze immutable weekly projections
- produce matchup previews
- produce Sunday/MNF reports
- produce final weekly recaps
- track player boom/bust performance
- track fantasy-team projection performance
- track promotion and relegation
- calculate matchup win probabilities
- estimate future playoff, relegation, and promotion probabilities
- run automatically through GitHub Actions

## Development Philosophy

Correctness comes before automation.

Historical data should be preserved.

External API access, business rules, calculations, storage, and reporting should remain separate wherever practical.

## Documentation

- RULES.md — permanent league and baseline rules
- ARCHITECTURE.md — software architecture and design principles
- DATA_MODEL.md — planned snapshot and history structures
- AGENTS.md — instructions for ChatGPT, Copilot, and other coding agents

## Current Status

PProject foundation established.

Initial Sleeper API integration supports league metadata, users, rosters, and weekly matchups.

Historical snapshot storage, projections, and reporting have not yet been implemented.

## Development Setup

Activate the project's Python environment:

```bash
source .venv/bin/activate

## Weekly CLI

The production automation entry point is `fantasy.py`.

Commands:

```bash
python fantasy.py baseline
python fantasy.py sunday
python fantasy.py final
python fantasy.py auto

## AI Agent Context

Generate structured context for a narrative AI agent:

```bash
python fantasy.py context --stage baseline --week 4
python fantasy.py context --stage sunday --week 4