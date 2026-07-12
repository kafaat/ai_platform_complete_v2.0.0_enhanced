# SAHOOL — Agronomic Model Lifecycle Lineage Continuation

Date: 2026-07-12
Source: `sahool_de0c61d_agronomic_learning_lineage_continued.zip`

## Scope

This continuation closes the next gap after Decision → Outcome → Learning Attribution → Calibration Dataset: propagation of the exact agronomic cohort composition into model evaluation, promotion, and activation.

## Changes

### Migration 022

Added `services/decision-service/migrations/022_model_agronomic_cohort_lineage.sql`.

It adds immutable cohort fields to:

- `decision_model_evaluation_runs`
- `decision_model_promotion_decisions`
- `decision_model_activation_requests`

Fields:

- `agronomic_cohorts jsonb`
- `agronomic_cohort_fingerprint sha256`

Database triggers reject promotion or activation records whose cohort lineage differs from the authoritative upstream record.

### Evaluation fingerprint repair

The evaluation registration path previously rebuilt the calibration fingerprint without the newly required agronomic lineage fields. That could reject a valid calibration dataset or evaluate a materially different dataset representation.

The path now joins `decision_record` and includes:

- agronomic context snapshot
- vegetation snapshot
- field-history snapshot
- feature manifest identity/hash
- crop
- cultivar
- season

The same canonical fingerprint function is now used for the calibration read and evaluation write path.

### Cohort manifest

A deterministic server-side manifest is derived from the calibrated samples using:

`crop_id | cultivar_id | season_id`

The sorted manifest receives its own SHA-256 fingerprint. Clients cannot provide or replace this lineage.

### Lifecycle propagation

The exact cohort manifest and fingerprint now flow through:

`Calibration Dataset → Evaluation Run → Promotion Decision → Activation Request`

They are also returned in authoritative API responses and included in outbox events.

### CI repair

The existing `vegetation-agriai-production.yml` contained a malformed step where a command was incorrectly nested under `run`. The workflow was rewritten and YAML-parsed successfully.

Added:

- `scripts/ci/agronomic_model_lifecycle_lineage_gate.py`
- `services/decision-service/tests/test_agronomic_model_lifecycle_lineage.py`

## Verification

- Python compileall: PASS
- Vegetation/AgriAI production gate: PASS
- Vegetation/AgriAI full closure gate: PASS
- Agronomic decision lineage gate: PASS
- Agronomic lineage integrity gate: PASS
- Agronomic learning lineage gate: PASS
- Agronomic model lifecycle lineage gate: PASS
- GitHub Actions YAML parse: PASS
- Vegetation focused tests: 5 passed
- AgriAI focused tests: 10 passed
- Decision agronomic tests: 11 passed, 1 skipped

The skipped test requires a live PostgreSQL `DATABASE_URL`. Migration 022 triggers and concurrency semantics are therefore code-complete but not certified against a real database in this environment.

## Closed chain

`Vegetation / Field History / Agronomic Context`
→ `Decision`
→ `Verified Outcome`
→ `Learning Attribution`
→ `Calibration Dataset`
→ `Evaluation Run`
→ `Promotion Decision`
→ `Activation Request`

## Remaining external certification

- Apply migrations 018–022 to real PostgreSQL.
- Verify RLS, composite foreign keys, triggers, and replay behavior.
- Run a real Sentinel/Weather/Soil/Crop-card dataset through the lifecycle.
- Establish per-cohort minimum sample and metric thresholds before production activation.
