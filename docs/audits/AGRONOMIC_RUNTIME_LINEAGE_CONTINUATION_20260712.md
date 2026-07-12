# SAHOOL Agronomic Runtime Lineage Continuation

Date: 2026-07-12
Base: `sahool_de0c61d_agronomic_model_lifecycle_continued.zip`

## Scope

This continuation closes the missing agronomic cohort lineage after activation request creation and carries the evaluated agricultural population through runtime operations.

## Implemented

### Migration 023

Added `services/decision-service/migrations/023_runtime_agronomic_cohort_lineage.sql`.

The migration adds `agronomic_cohorts` and `agronomic_cohort_fingerprint` to:

- activation reviews
- registry activation commands and receipts
- rollback commands and receipts
- post-activation verifications
- rollout plans and receipts
- monitoring snapshots
- retraining requests and dispatch receipts

It also adds:

- `source_receipt_id` to monitoring snapshots
- `source_monitoring_snapshot_id` and `target_environment` to retraining requests
- SHA-256 fingerprint constraints
- inheritance triggers that reject cohort substitution
- cohort indexes for monitoring and retraining

### Server-side inheritance

Persistence now derives agronomic cohorts from authoritative upstream records:

`Activation Request -> Review -> Activation Command -> Activation Receipt -> Verification -> Rollout`

Monitoring snapshots are bound to the current activated receipt for the exact model, feature set and environment. A client cannot submit an arbitrary cohort manifest.

Retraining requests are bound to a monitoring snapshot. They are rejected when:

- no monitoring evidence exists
- the monitoring snapshot belongs to a different model, feature set or environment
- drift state is `stable`

Only `warning` or `critical` drift can trigger retraining.

### Idempotency

Monitoring and retraining writes now return the authoritative prior record for a byte-equivalent replay and reject a mismatched payload under the same idempotency key.

### API compatibility

`RetrainingRequestIn` now supports:

- `target_environment` with default `production`
- optional `source_monitoring_snapshot_id`

When the source ID is omitted, the latest matching monitoring snapshot is resolved server-side.

### CI

Added:

- `scripts/ci/agronomic_runtime_lineage_gate.py`
- `services/decision-service/tests/test_agronomic_runtime_lineage.py`

The gate is wired into `.github/workflows/vegetation-agriai-production.yml`.

## Verification

- Python compileall: PASS
- Workflow YAML parse: PASS
- Vegetation/AgriAI production gate: PASS
- Vegetation/AgriAI full closure gate: PASS
- Agronomic decision lineage gate: PASS
- Agronomic lineage integrity gate: PASS
- Agronomic learning lineage gate: PASS
- Agronomic model lifecycle lineage gate: PASS
- Agronomic runtime lineage gate: PASS
- Focused tests: 63 passed, 1 skipped

The skipped test requires a real PostgreSQL `DATABASE_URL`. Therefore migration 023 trigger and RLS behavior is implemented and statically verified, but not falsely claimed as executed against a live database in this environment.

## Closed chain

`Vegetation / Field History / Agronomic Context`
`-> Decision`
`-> Verified Outcome`
`-> Learning Attribution`
`-> Calibration Dataset`
`-> Evaluation`
`-> Promotion`
`-> Activation Request`
`-> Activation Command`
`-> Activation Receipt`
`-> Post-activation Verification`
`-> Rollout`
`-> Monitoring`
`-> Retraining Request`

The agronomic cohort fingerprint is now conserved across this chain.
