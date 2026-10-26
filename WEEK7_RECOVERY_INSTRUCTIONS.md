# Week 7 recovery patch (2026)

## Install

Replace these four files on your GitHub `main` branch with the versions in this ZIP:

- `.github/workflows/weekly-fantasy.yml`
- `fantasy.py`
- `src/orchestration.py`
- `src/agent_context.py`

Commit and push all four files together. The full-repository ZIP is also supplied as a reference; **do not overwrite newer GitHub files from the older October 20 backup**. Prefer the four-file patch if GitHub has changed since the backup.

## Recover Week 7

In GitHub > Actions > Weekly Fantasy Automation > Run workflow, choose branch `main`.

1. Run `stage=baseline`, `week=7`, `recovery=true`, `check_only=false`.
2. Confirm successful workflow and new `data/2026/goats/week_07_baseline.json`, `data/2026/doats/week_07_baseline.json`, `data/2026/agent/week_07_baseline.json` on `main`.
3. Run `stage=sunday`, `week=7`, `recovery=true`, `check_only=false`.
4. Confirm `data/2026/goats/week_07_sunday.json`, `data/2026/doats/week_07_sunday.json`, `data/2026/agent/week_07_sunday.json` on `main`.

**Historical warning:** Both recovery runs use data available when executed, not data frozen in the original Thursday or Monday window. Source snapshots have `data.capture_context.reconstructed=true`, `historical_window_capture=false`, capture timestamps and a warning. Derived agent JSON has `reconstructed=true`, `reconstruction_sources`, and `reconstruction_warning`. Do not interpret reconstructed Week 7 baselines as authentic Thursday forecasts, nor late Sunday recoveries as pre-MNF snapshots. Live APIs may no longer provide complete historical projections or may fail validations.

Recovery does not overwrite existing immutable snapshots; partially existing league snapshot pairs remain blocked. Normal scheduled runs remain window-locked. The recovery switch is restricted to manually dispatched baseline and sunday stages with explicit week. Tests: `python -m pytest -q` (298 passed on supplied backup).

If a recovery run fails for data validation or API availability, save its logs. The patch addresses the window restriction, not missing historical source data.
