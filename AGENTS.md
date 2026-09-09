# Instructions for AI Coding Agents

Before modifying this project, read:

1. README.md
2. RULES.md
3. ARCHITECTURE.md
4. DATA_MODEL.md

## Critical Invariants

Do not overwrite an existing weekly baseline snapshot.

Do not change GOATs or DOATs promotion/relegation rules without explicit user instruction.

Do not invent standings tiebreakers.

Do not silently treat missing projection data as valid zero projections.

Historical snapshots should remain readable after code changes.

## Architecture Rules

Keep external API calls separate from league-rule calculations.

Keep report formatting separate from analysis logic.

Prefer small descriptive functions over giant scripts.

Use type hints and docstrings where practical.

Avoid unnecessary frameworks and dependencies.

Do not introduce a database unless file-based storage has become meaningfully difficult to maintain.

## Development Process

Make small changes.

Run the test suite after meaningful changes:

python -m pytest

Add or update tests when business rules change.

Do not add GitHub Actions automation until equivalent manual commands are working reliably.

Never commit secrets, tokens, passwords, or credentials.