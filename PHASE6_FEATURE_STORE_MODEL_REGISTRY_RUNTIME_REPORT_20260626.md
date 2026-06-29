# Phase 6 — Feature Store + Model Registry Production Runtime

## Scope
This patch strengthens Phase 10 Continuous Learning by adding production-shaped, dependency-light runtime layers for:

- Feature definitions and feature-set versioning.
- Offline dataset version manifests with content hashes.
- Point-in-time snapshots to prevent training/label leakage.
- Online feature materialization manifests for Redis/Postgres online store adapters.
- Model version registration with artifact hash metadata.
- Serving alias promotion, rollback planning and model-card output.
- Phase 10 integration so every learning cycle emits Feature Store and Model Registry runtime artifacts.

## Files added

- `shared/feature_store/__init__.py`
- `shared/feature_store/runtime.py`
- `shared/mlops/__init__.py`
- `shared/mlops/runtime.py`
- `migrations/v108_phase10_feature_store_model_registry_runtime.sql`
- `tests/phase6/test_feature_store_model_registry_runtime.py`
- `tests/phase6/test_phase6_static_contracts.py`

## Files changed

- `shared/continuous_learning_phase10.py`
- `services/sahool-platform/api/phase10_continuous_learning.py`
- `services/sahool-platform/api/phase_runtime_store.py`
- `migrations/MANIFEST.txt`
- `migrations/MANIFEST.md`

## New API contracts

Under `/v1/phase10/learning`:

- `POST /feature-store/register`
- `POST /feature-store/offline-dataset`
- `POST /feature-store/online-materialization`
- `POST /feature-store/point-in-time`
- `POST /models/register`
- `POST /models/serving/promote`
- `POST /models/serving/rollback`
- `GET /models/serving/{alias}`

## Migration v108

Adds RLS/FORCE-protected runtime tables:

- `feature_definitions_runtime`
- `feature_set_versions_runtime`
- `offline_dataset_versions_runtime`
- `point_in_time_snapshots_runtime`
- `model_versions_runtime`
- `model_serving_aliases_runtime`
- `model_promotion_history_runtime`
- `model_rollback_history_runtime`

## Phase 10 integration

`run_phase10_learning_cycle()` now returns:

- `feature_store_runtime.registry`
- `feature_store_runtime.offline_dataset_version`
- `feature_store_runtime.online_materialization`
- `feature_store_runtime.point_in_time_snapshot`
- `feature_store_runtime.lineage`
- `model_registry_runtime.champion`
- `model_registry_runtime.challenger`
- `model_registry_runtime.serving_promotion`
- `model_registry_runtime.rollback_plan`
- `model_registry_runtime.model_cards`

The existing output keys remain intact for backward compatibility.

## Validation

Executed in this environment:

```text
Python compile: 1335 compiled, 0 failed
YAML parse: docker-compose.v9.yml parsed successfully, 44 services
Security audit: hard failures 0
Targeted tests: 24 passed
```

Targeted tests included:

- Phase 6 feature store/model registry runtime tests.
- Phase 6 static contract checks.
- Phase 3 E2E integration contracts.
- Phase 4 security/observability contracts.
- Existing Phase 10 continuous learning tests.

## Known limitation

Docker runtime was not executed in this environment because Docker is unavailable. Run the following on the deployment host:

```bash
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d
./scripts/security_audit.sh
BASE_URL=http://localhost ./scripts/observability_smoke.sh
BASE_URL=http://localhost ./scripts/runtime_smoke.sh
```
