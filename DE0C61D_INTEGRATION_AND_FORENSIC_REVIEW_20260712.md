# SAHOOL de0c61d — Integration and Forensic Review

Date: 2026-07-12

## Scope

Compared `sahool_de0c61d.zip` against the latest Vegetation + AgriAI gap-closure package and merged the missing production-safety improvements while preserving the newer WX-12.3 runtime scheduler work already present in de0c61d.

## Findings before merge

The de0c61d package contained the newer Decision-Service runtime scheduling implementation:

- `017_wx12_runtime_schedules.sql`
- runtime schedule endpoints and persistence changes
- runtime scheduler CI gate
- runtime schedule tests

However, it had regressed or omitted the latest Vegetation + AgriAI closure files:

- no `vegetation_contracts.py`
- no `agronomic_context.py`
- no production Vegetation/AgriAI gates
- no strict real-only vegetation snapshot contract
- no authoritative raster timeseries path
- no strict agronomic context binding in AgriAI

## Merged changes

### Vegetation

- Restored `VegetationSnapshot` contract and deterministic hash.
- Restored authoritative-vs-derived indicator separation.
- Restored real-only production mode.
- Restored minimum quality gate and provenance requirements.
- Restored `data_available_at` propagation.
- Restored authoritative raster-service timeseries path.
- Removed synthetic timeseries generation from the public production path.
- Restored production contract tests.

### AgriAI

- Restored strict `AgronomicContext` validation.
- Restored crop/cultivar/growth-stage, soil, irrigation, weather, climate, water-quality, vegetation, history, and feature-manifest binding.
- Restored temporal leakage checks.
- Restored normalized context-to-engine input mapping.
- Restored context and vegetation hashes in outputs.
- Restored strict 422 failure behavior for incomplete production context.

### CI

- Restored Vegetation/AgriAI completion and production gates.
- Restored dedicated Vegetation/AgriAI workflow.
- Preserved WX-12.3 runtime scheduler gate and migration 017.

## Verification actually executed

- Python compilation: PASS
- Vegetation -> AgriAI completion gate: PASS
- Vegetation/AgriAI production gate: PASS
- WX-12.3 runtime scheduler gate: PASS
- Vegetation + AgriAI focused tests: 14 passed
- Runtime adapter contract tests: 6 passed
- Decision-Service runtime schedule PostgreSQL tests: 3 skipped because no `DATABASE_URL` was available

## Important test-runner note

The Vegetation and Decision-Service suites both import modules named `main`. Running them in one pytest process can cause a Python module-cache collision and false 404 failures. They pass when executed as separate CI jobs/processes, which is the correct isolation boundary for independent services. The repository workflows should keep these suites separated.

## Remaining non-code certification work

The merged code closes the identified integration regression. Production certification still requires:

- real PostgreSQL execution for migration 017 and concurrency tests
- real Sentinel COG/raster-service integration
- real soil, weather, water, crop-card, and history snapshots
- staging end-to-end decision lineage validation
- scientific calibration per crop, cultivar, soil, irrigation system, and climate zone

## Final judgment

The package now contains both:

1. the newer de0c61d WX-12.3 scheduler/runtime work; and
2. the Vegetation + AgriAI production-safety and agronomic-context closure.

No known code-level regression remains between those two branches after this merge. Production readiness is still conditional on environment-backed and scientific certification.
