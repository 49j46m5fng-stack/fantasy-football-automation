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

Projection-feed records must be category-aware.

Do not create a player projection lookup from mixed projection-feed categories.

For weekly fantasy projections, use the `proj` category unless the architecture is deliberately changed and tested.

Duplicate player IDs must not silently overwrite one another.

Missing projected points are not automatically zero.

A missing projection may become zero only through a tested explicit rule, such as Sleeper reporting the player as Out, or through a documented historical projection override.

Do not hardcode exceptional player IDs inside projection calculation code.

Week-specific projection corrections belong in the committed projection override data.

Official weekly snapshots must be written through the storage layer.

Do not write baseline, Sunday, or final snapshot files directly with normal file-write mode.

Do not replace an existing official snapshot.

If snapshot correction functionality is introduced later, it must preserve the original historical record and be explicitly tested.

Historical comparisons must use stored snapshot data only.

Do not fetch current projections to reconstruct a baseline-to-Sunday comparison.

Compare fantasy teams by `roster_id`, not manager display name.

Lineup membership changes and lineup-slot changes are separate concepts.

Missing historical projections must remain unresolved and must not silently become zero.

Use `fantasy.py` and `src/orchestration.py` for recurring weekly execution.

Do not add one-off week-specific automation scripts for future weeks unless there is a documented exceptional reason.

Recurring dates and execution windows belong in `automation_schedule.json`.

The generic GitHub workflow must remain idempotent: repeated scheduled attempts must either create missing historical outputs once or safely no-op when those outputs already exist.

Do not bypass the storage layer from orchestration code.

Week 1 temporary workflows are transitional safeguards and should be retired after their Week 1 responsibilities are complete.

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

Official reports must use the appropriate stored snapshot as their historical source.

Do not re-query current projections when generating a report that represents an earlier stage.

A baseline preview must use the immutable baseline snapshot.

Later Sunday and final reports must preserve the baseline values separately from newer live or final values.

Do not promote undocumented live Sleeper matchup fields into normalized business logic merely because they appear in one response.

Preserve unexpected source fields in raw snapshot data and verify their meaning first.

The Sunday/MNF snapshot may contain incomplete current projections. Capture the historical state rather than inventing replacements.

AI-facing context files are derived artifacts.

Never treat an agent-context file as the authoritative historical source when an immutable stage snapshot exists.

Do not query current Sleeper data to rewrite historical agent context.

Precompute arithmetic and league-rule outcomes in Python whenever practical so downstream narrative agents receive facts rather than being asked to infer them.

Narrative generation does not belong in the core Python analytics layer.

Final-stage team results come from the immutable final snapshot.

Do not infer player fantasy points from team scores.

Do not calculate boom/bust until a verified per-player actual-scoring source
has been normalized.

A missing Sunday checkpoint must not cause the system to discard an otherwise
valid final weekly result.