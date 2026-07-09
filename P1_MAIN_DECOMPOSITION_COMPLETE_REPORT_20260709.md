# P1 Main Decomposition Complete Report — 2026-07-09

## Scope

Completed the requested P1 main.py decomposition batch:

- `services/sahool-platform/api/main.py` residual bootstrap
- `services/odoo-bridge/main.py`
- `services/vegetation-analysis-service/main.py`

The refactor was intentionally conservative: preserve public/internal routes, preserve router registry registration, preserve `main.X` compatibility for existing routers/tests, and add CI guards to prevent regression.

## Changes

### 1. sahool-platform/api/main.py residual bootstrap

Extracted direct platform route handlers out of `api/main.py`:

- `/healthz`
- `/metrics`
- `/readyz`
- `/internal/fields/{field_id}/state`
- `/internal/events/ai-advice`

New files:

- `services/sahool-platform/api/routers/platform_health.py`
- `services/sahool-platform/api/routers/internal_service.py`

Updated guard:

- `scripts/ci/internal_graphql_security_guard.py` now verifies internal S2S routes in `api/routers/internal_service.py` while continuing to verify the service-token guard in `api/service_token_auth.py`.
- `scripts/ci/route_mount_contract_guard.py` now correctly treats `services/sahool-platform/api` as the router root for the platform service.

Result:

- `services/sahool-platform/api/main.py` has **0 direct route decorators**.
- `services/sahool-platform/api/main.py` remains the app/bootstrap shell and still calls `register_routers(app)`.

### 2. odoo-bridge/main.py

Extracted ERP/Odoo runtime and sync implementation from `main.py` into:

- `services/odoo-bridge/erp_runtime.py`

Moved runtime responsibilities include:

- ERP provider selection
- Odoo JSON-RPC client
- DB pool and migration helpers
- sync state/log helpers
- product/supplier/warehouse sync
- procurement and field-cost sync
- periodic sync loop

`main.py` now re-exports runtime names so existing routers that use `main.X` keep working.

Result:

- `services/odoo-bridge/main.py`: **187 LOC**
- `services/odoo-bridge/erp_runtime.py`: **883 LOC**

### 3. vegetation-analysis-service/main.py

Extracted vegetation runtime and provider/computation implementation into:

- `services/vegetation-analysis-service/vegetation_runtime.py`

Moved runtime responsibilities include:

- config and flags
- JWT helper functions
- field source/registry logic
- Sentinel Hub/CDSE metadata calls
- synthetic band estimation
- index computation
- raster-service real mean pass-through
- NATS event publishing
- analysis/timeseries/current NDVI helpers
- Prometheus metrics objects

`main.py` now re-exports runtime names so existing routers/tests that use `main.X` keep working.

Result:

- `services/vegetation-analysis-service/main.py`: **120 LOC**
- `services/vegetation-analysis-service/vegetation_runtime.py`: **892 LOC**

### 4. P1 decomposition guard

Added:

- `scripts/ci/p1_main_decomposition_guard.py`
- `tests_v9/test_p1_main_decomposition_guard.py`
- `.github/workflows/p1-main-decomposition.yml`

The guard enforces:

- platform main has no direct route decorators and still delegates to router registry
- platform health/internal routers exist
- odoo main stays below 250 LOC
- odoo heavy sync functions stay in `erp_runtime.py`
- vegetation main stays below 180 LOC
- vegetation heavy runtime functions stay in `vegetation_runtime.py`

## Verification

### Py compile

Passed:

```bash
python -m py_compile \
  services/sahool-platform/api/main.py \
  services/sahool-platform/api/routers/platform_health.py \
  services/sahool-platform/api/routers/internal_service.py \
  services/odoo-bridge/main.py services/odoo-bridge/erp_runtime.py \
  services/vegetation-analysis-service/main.py services/vegetation-analysis-service/vegetation_runtime.py \
  scripts/ci/p1_main_decomposition_guard.py \
  scripts/ci/route_mount_contract_guard.py \
  scripts/ci/internal_graphql_security_guard.py
```

### Targeted tests

Passed selected service/static tests and guard tests. The long combined run timed out in the chat execution environment after most tests had completed, so remaining subsets were re-run separately.

Confirmed pass:

- weather-service tests
- edge-inference tests
- mcp_servers static smoke
- agriai-engine static smoke
- knowledge-graph static smoke
- rag-retrieval static smoke
- indicators-service tests
- route mount contract guard test
- internal/graphql security guard test
- health alias guard test
- API versioning policy guard test
- contract/capabilities schema guard test
- health/readiness schema guard test
- auth main decomposition guard test
- ai-agronomist main decomposition guard test
- P1 main decomposition guard test
- unit test dependency guard test
- Dockerfile pip mirror guard test
- vegetation router decomposition guard test

`services/odoo-bridge/test_odoo_bridge_router_decomposition_guard.py` remains skipped in this local sandbox because `asyncpg` is not installed in the active interpreter. The source files compile successfully and the static P1 guard covers the decomposition contract.

### CI guards

Passed:

```text
route_mount_inventory_check_ok
api_versioning_policy_check_ok
health_readiness_schema_guard_ok
contract_capabilities_schema_check_ok
test_dependency_inventory_check_ok
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
✓ PyPI-default + Alibaba override pip mirror contract guard passed
internal_graphql_security_guard_ok
health_alias_contract_guard_ok
✓ edge model contract guard passed
✓ edge production readiness guard passed
✓ production honesty guard passed
p1_main_decomposition_guard_ok
```

## Updated inventories

Regenerated:

- `SERVICE_REGISTRY.md`
- `service_inventory.generated.json`
- `route_inventory.generated.json`
- `service_inventory.csv`
- `route_inventory.csv`
- `route_mount_inventory.generated.json`
- `route_mount_inventory.csv`
- `api_versioning_inventory.generated.json`
- `api_versioning_inventory.csv`
- `health_readiness_inventory.generated.json`
- `health_readiness_inventory.csv`
- `contract_capabilities_inventory.generated.json`
- `contract_capabilities_inventory.csv`
- `test_dependency_inventory.generated.json`
- `test_dependency_inventory.csv`
- `dependency_inventory.generated.json`
- `dependency_inventory.csv`
- `dependency_conflicts.generated.json`
- `dependency_conflicts.csv`

## Status

P1 is complete in this package:

```text
P1: sahool-platform/api/main.py residual bootstrap — DONE
P1: odoo-bridge/main.py — DONE
P1: vegetation-analysis-service/main.py — DONE
```

Remaining decomposition list:

```text
P2: actuator-service/main.py
P2: sam2-inference/main.py
P2: weather-service/main.py before adding ensemble
```

Remaining release blockers outside P1:

```text
Full branch CI
transitive lock generation in connected CI
Redis live integration
ONNX model provisioning
full /v1 migration only if client-breaking change is accepted
```
