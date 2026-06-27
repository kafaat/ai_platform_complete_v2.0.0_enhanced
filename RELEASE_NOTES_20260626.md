# SAHOOL Phase 12 Production Candidate — Release Notes 2026-06-26

## Release identity

`SAHOOL_PHASE12_PRODUCTION_CANDIDATE_20260626_PHASE14`

## Summary

This release consolidates the Phase 12 runtime hardening series into a deployable production-candidate bundle. It includes field/imagery/map verification, AI/RAG/KG runtime binding, production security gates, Feature Store and Model Registry runtime, IoT execution adapters, marketplace plugin sandboxing, federated agent consensus, mobile offline sync, reliability harnesses, and production observability dashboards.

## Major capabilities included

- Field imagery and map runtime hardening with date/version-safe TileJSON and cache isolation.
- AI agronomist runtime bound to RAG, Knowledge Graph, guardrails, and CanonicalFieldState.
- Phase 10 Feature Store + Model Registry runtime for dataset/model versioning and promotions.
- Phase 9 IoT execution adapters with dry-run/fail-closed physical actuation policy.
- Phase 11 federated agent consensus with authority envelopes and proposal-only safety.
- Phase 12 marketplace plugin runtime sandbox and output validation.
- Mobile offline sync contracts with manifest/status endpoints and idempotent operation handling.
- Reliability harnesses for load, chaos, and recovery validation.
- Production validation gates for RLS/runtime DB role safety.
- Grafana dashboards and Prometheus alert rules for production observability.
- Release manifest, checksum inventory, and minimal SBOM/source asset inventory.

## Deployment stance

This is a production-candidate source bundle. Full production approval still requires running Docker-based runtime smoke, E2E, load, chaos, and recovery checks in the target environment.

## Rollback stance

Rollback should use the previous zip artifact plus database migration restore/backup procedure. Do not partially roll back code without database and configuration alignment.


## Phase 15 — Deployment Automation + Helm/GitOps Readiness

- Added Helm chart for critical SAHOOL runtime services.
- Added staging and production values overlays.
- Added static deployment validation gate.
- Added staging/production deployment scripts.
- Added Kubernetes security contracts: non-root, probes, NetworkPolicy, secret references, migration hook.

## Phase 16 — CI/CD Quality Gates + Supply Chain Hardening

- Added a blocking GitHub Actions workflow for production/release/deploy/security/observability gates.
- Added local CI parity via `scripts/ci/local_quality_gate.sh`.
- Added a dependency-free CI wiring validator.
- Added CI contract tests to prevent accidental soft-fail workflows or missing release gates.

## Phase 17 — Runtime Bootstrap & Production Environment Doctor

Added a dependency-light runtime doctor for preflight and runtime readiness checks:

- `scripts/runtime/env_doctor.py`
- `scripts/runtime/runtime_doctor.sh`
- `tests/runtime/test_phase17_runtime_bootstrap_doctor.py`
- `PHASE17_RUNTIME_BOOTSTRAP_ENV_DOCTOR_REPORT_20260626.md`

The doctor validates environment contracts, DB runtime roles, required migrations, compose static safety, optional Docker Compose config, local port conflicts, and runtime health/metrics endpoints.


## Phase 18 urgent runtime fixes

- Fixed GitHub Actions shell syntax and added workflow shell `bash -n` validation.
- Made chaos E2E/outbox checks blocking instead of `|| true`.
- Added production fail-closed persistence for Phase 9-12 when `db_pool` or `X-Tenant-Id` is missing.
- Added Phase runtime workers for outbox, plugins, model rollback, and actuator dispatch.
- Added `v113_phase_runtime_workers_jobs.sql` for RLS-safe `sahool_jobs` worker policies.
- Rebuilt `migrations/MANIFEST.md` to mirror `migrations/MANIFEST.txt`.

## Phase 19 — Production Gap Closure

- Fixed `env_doctor.py` `PermissionError` handling for unreadable PATH entries.
- Switched critical CI/runtime script calls to `bash script.sh` to avoid executable-bit dependent failures after ZIP extraction.
- Unified legacy `scripts_v9` migrations with `migrations/MANIFEST.txt`.
- Added migration manifest validation to production/CI gates.
- Renumbered duplicated runtime migration prefixes to `v114`–`v121`.


## Phase 20 — Runtime Worker Side-Effect Hardening

- Added deterministic fail-closed worker contracts for outbox, plugin execution, model promotion/rollback, and actuator dispatch.
- Prevented plugin worker from marking allowed plugin runs as completed without an external executor.
- Added model serving backend checks before promotion/rollback side effects.
- Added actuator adapter configuration checks and `waiting_ack` semantics before any physical effect is acknowledged.
- Updated release manifest requirements and tests for worker-side effects.

## Phase 21 — Production Certification Readiness

- Added legacy runtime quarantine audit for MVP/dev/stub markers in runtime paths.
- Added single-source-of-truth audit to keep FieldTwin/CropTwin/WaterTwin/DigitalTwin as projections of CanonicalFieldState.
- Added 7-14 day soak certification harness and threshold evaluator.
- Added production certification matrix with explicit pending live-runtime stages.
- Integrated Phase 21 audits into production/local CI gates and release assets.

## Phase 22 — RLS WITH CHECK + Tenant Session Hardening

- Added v122 RLS backfill migration for tenant write policies missing `WITH CHECK`.
- Unified tenant session context with `public.sahool_effective_tenant_id()`.
- Phase runtime store/workers now set both `app.current_tenant` and `app.tenant_id`.
- Added CI/production validator for RLS write-policy regressions.
