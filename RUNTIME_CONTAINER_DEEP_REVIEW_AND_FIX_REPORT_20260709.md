# Runtime Container Deep Review and Fix Report — 2026-07-09

## Scope

Follow-up review after the broad container fleet and AI container sweeps. This pass focused on the high-risk containers that were not yet reviewed service-by-service with the same depth:

- `sahool-auth`
- `sahool-platform`
- `sahool-notification-agent`
- `sahool-raster-service`
- `sahool-soil-service`
- `sahool-field-segmentation`
- supporting requirements/compose contracts

## Findings and fixes

### 1. Compose still used `/readyz` as Docker liveness for several non-AI services

The earlier Dockerfile sweep fixed many image-level healthchecks, but `docker-compose.v9.yml` still had liveness probes pointed at readiness endpoints for:

- `sahool-auth`
- `sahool-platform`
- `sahool-notification-agent`
- `sahool-soil-service`
- `sahool-field-segmentation`

These were corrected to `/healthz`.

**Why this matters:** Docker/Compose healthchecks should test process liveness. Readiness may legitimately degrade because DB/model/upstream dependencies are unavailable; Docker should not restart a live process solely because readiness is degraded.

### 2. Notification agent lacked `/healthz` while compose now probes it

`agents/notification/agent.py` exposed `/health` and `/readyz`, but not `/healthz`. A `/healthz` alias was added to the existing liveness handler.

The notification Dockerfile healthcheck was also changed from `/readyz` to `/healthz`.

### 3. Raster image base was risky for current geospatial pins

`services/raster-service/Dockerfile` used Python 3.12 while the service pins `rasterio==1.3.0`, an older geospatial stack with higher Python 3.12 build risk. The raster image was moved to:

```dockerfile
FROM python:3.11-slim-bookworm
```

This is intentionally conservative until the geospatial stack is upgraded as a separate change.

### 4. Duplicate raster requirement pin removed

`services/raster-service/requirements.txt` contained duplicate `asyncpg==0.29.0` entries. The duplicate pin and stale duplicate comment were removed.

### 5. Malformed inline comments in platform requirements fixed

`services/sahool-platform/api/requirements.txt` had dependency lines with `#` directly attached to the version token. These were normalized to `  #` comments to avoid pip/tooling ambiguity:

- `anthropic==0.69.0  # ...`
- `asyncpg==0.30.0  # ...`

## New guard

Added:

- `scripts/ci/runtime_container_deep_contract_guard.py`
- `tests_v9/test_runtime_container_deep_contract_guard.py`
- `.github/workflows/runtime-container-deep-contract.yml`
- `runtime_container_deep_audit.generated.json`
- `runtime_container_deep_audit.csv`

The guard enforces:

- selected Compose healthchecks use `/healthz`, not `/readyz`
- notification-agent exposes and probes `/healthz`
- raster-service remains on Python 3.11 while `rasterio==1.3.0` is pinned
- raster requirements do not contain duplicate exact pins
- platform requirements do not contain malformed inline comments

## Runtime smoke integration

`runtime_container_deep_contract_guard.py` and its pytest wrapper were added to `scripts/ci/runtime_real_smoke.sh`.

## Verification performed

Commands run successfully:

```bash
python -m py_compile \
  scripts/ci/runtime_container_deep_contract_guard.py \
  tests_v9/test_runtime_container_deep_contract_guard.py \
  agents/notification/agent.py

python scripts/ci/runtime_container_deep_contract_guard.py --check
pytest -q tests_v9/test_runtime_container_deep_contract_guard.py
pytest -q \
  tests_v9/test_runtime_container_deep_contract_guard.py \
  tests_v9/test_container_fleet_contract_guard.py \
  tests_v9/test_ai_container_contract_guard.py \
  tests_v9/test_report_index_guard.py

python scripts/ci/container_fleet_contract_guard.py
python scripts/ci/ai_container_contract_guard.py --check
python scripts/ci/runtime_container_deep_contract_guard.py --check
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/pip_audit_resolution_guard.py
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/health_readiness_schema_guard.py --check
python scripts/ci/contract_capabilities_schema_guard.py --check
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
python scripts/ci/report_index_guard.py
```

Observed results:

- `runtime_container_deep_contract_guard_ok`
- `4 passed` for the focused container/report tests
- dependency inventories regenerated and checks passed
- route/health/contract/report checks passed

## What was not done

Docker is not available in the chat sandbox, so no real Docker build matrix was executed here. This remains required in CI for production certification.

## Final status

The remaining non-AI high-risk containers are now better aligned with the same liveness/readiness policy already applied to `indicators`, `vegetation`, and AI containers.

This still does not make the release production-certified. It reduces static/runtime container contract risk before CI build evidence is attached.
