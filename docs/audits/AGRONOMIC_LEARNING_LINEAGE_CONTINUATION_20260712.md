# SAHOOL Agronomic Learning Lineage Continuation

Date: 2026-07-12

## Scope

This increment continues the previously closed Vegetation → AgriAI → Decision lineage by propagating the exact agronomic evidence used by a governed decision into learning attribution and calibration datasets.

## Implemented

### Migration 021

Added `services/decision-service/migrations/021_learning_agronomic_lineage.sql`.

The migration extends `decision_learning_attributions` with immutable inherited lineage:

- `field_id`
- `season_id`
- `crop_id`
- `cultivar_id`
- `agronomic_context_snapshot_id`
- `vegetation_snapshot_id`
- `field_history_snapshot_id`
- `feature_manifest_id`
- `feature_manifest_hash`

It also adds tenant-scoped foreign keys, SHA-256 validation, cohort/context indexes, forced RLS, and an insert trigger that requires exact equality with the source `decision_record`.

### Authoritative inheritance

`create_learning_attribution()` now joins the verified outcome to its source decision and copies lineage from that authoritative decision. Clients cannot provide or override agronomic lineage.

The learning outbox event and authoritative API response now expose the inherited evidence references.

### Calibration dataset integrity

The calibration dataset now includes agronomic lineage in every item and in the dataset fingerprint. A change in crop, cultivar, season, snapshot reference, or feature manifest changes the fingerprint.

Legacy or ungrounded decisions are excluded from calibration datasets unless all required references are present:

- agronomic context snapshot
- vegetation snapshot
- field-history snapshot
- feature manifest id/hash
- season
- crop
- cultivar

The response also includes deterministic crop/cultivar/season cohort counts under `agronomic_cohorts`.

### CI protection

Added:

- `scripts/ci/agronomic_learning_lineage_gate.py`
- `services/decision-service/tests/test_agronomic_learning_lineage.py`

The gate is wired into `.github/workflows/vegetation-agriai-production.yml`.

## Verification

- Python compileall: PASS
- Vegetation/AgriAI production gate: PASS
- Vegetation/AgriAI full closure gate: PASS
- Agronomic decision lineage gate: PASS
- Agronomic lineage integrity gate: PASS
- Agronomic learning lineage gate: PASS
- Workflow YAML parse: PASS
- Vegetation tests: 39 passed
- AgriAI tests: 10 passed
- Focused Decision-Service agronomic tests: 8 passed, 1 skipped

The skipped test requires a real PostgreSQL `DATABASE_URL`. No claim is made that migration 021, RLS, triggers, or concurrent inserts were certified against PostgreSQL in this environment.

## Result

The governed chain is now:

`Vegetation/History/Context snapshots → Decision → Verified Outcome → Learning Attribution → Calibration Dataset`

with exact immutable agronomic evidence propagation and no client-controlled lineage substitution.
