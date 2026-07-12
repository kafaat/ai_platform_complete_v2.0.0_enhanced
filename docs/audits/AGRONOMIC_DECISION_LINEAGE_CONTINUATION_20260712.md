# SAHOOL Agronomic Decision Lineage — Continuation

Date: 2026-07-12
Base: `sahool_de0c61d_full_plan_closed.zip`

## Closed in this increment

- Added authoritative Decision-Service APIs for immutable vegetation, field-history, and agronomic-context snapshots.
- Added strict decision input fields for season, crop, cultivar, three snapshot IDs, and feature-manifest identity/hash.
- Added `DECISION_REQUIRE_AGRONOMIC_CONTEXT` fail-closed gate for governed decisions.
- Added migration `019_decision_agronomic_lineage.sql` with nullable lineage columns, indexes, and foreign keys to immutable evidence snapshots.
- Updated Decision-Service persistence to write the agronomic lineage into `decision_record`.
- Added tenant-scoped snapshot persistence with RLS session binding.
- Added CI lineage guard and wired it into the Vegetation/AgriAI workflow.
- Added focused contract tests for strict rejection and snapshot hash validation.

## Validation

- Python compileall: PASS
- Vegetation tests: 39 passed
- AgriAI tests: 10 passed
- Decision focused tests: 13 passed
- Vegetation/AgriAI production gate: PASS
- Vegetation/AgriAI full closure gate: PASS
- Agronomic decision lineage gate: PASS

## Honest remaining external proof

Migration 018/019 concurrency, RLS, foreign-key behavior, and end-to-end snapshot→decision writes still require a real PostgreSQL staging run. Scientific certification still requires real COGs, crop-card calibration, soil/water observations, weather series, and measured outcomes.
