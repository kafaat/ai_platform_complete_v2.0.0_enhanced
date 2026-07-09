# P2 Main.py Decomposition Complete — 2026-07-09

## Scope

P2 services decomposed conservatively without changing public HTTP contracts:

- `services/actuator-service/main.py`
- `services/sam2-inference/main.py`
- `services/weather-service/main.py`

## Changes

### 1. Actuator Service

Created:

- `services/actuator-service/actuator_runtime.py`

`main.py` is now a compatibility shell that re-exports the runtime symbols. The heavy physical actuation runtime remains intact in `actuator_runtime.py`:

- MQTT command publishing
- physical-safety feature flags
- JWT/device-control authorization
- idempotency and cluster dedup
- Saga compensation hook
- automation rule evaluation
- command logging
- MQTT telemetry listener
- FastAPI app construction and router registration

LOC after decomposition:

- `main.py`: 12 lines
- `actuator_runtime.py`: 816 lines

Router modules were updated to import `actuator_runtime` instead of the shell module.

### 2. SAM2 Inference

Created:

- `services/sam2-inference/sam2_runtime.py`

Extracted CUDA/SAM2/STAC/raster/post-processing runtime:

- model loading
- service token validation
- STAC latest visual lookup
- RGB raster reading
- prompt construction
- mask-to-polygon conversion
- geometry post-processing helpers

`main.py` now owns only:

- FastAPI app
- startup hook
- `/predict`
- `/healthz`
- legacy `/health`
- `/readyz`

LOC after decomposition:

- `main.py`: 133 lines
- `sam2_runtime.py`: 562 lines

### 3. Weather Service

Created:

- `services/weather-service/weather_runtime.py`

Extracted Open-Meteo/cache/operation/tile runtime:

- readiness probe handling
- current/forecast/historical handlers
- cached tile sample path
- operation-window logic
- operation-plan ranking
- tile-data and interpolation
- operation tile-data
- tile series
- wind grid
- cache stats

`main.py` now owns only route registration and compatibility re-exports for existing tests/operators that monkeypatch `main.fetch_*` and `main.readiness_probe`.

LOC after decomposition:

- `main.py`: 38 lines
- `weather_runtime.py`: 379 lines

## New Guard

Added:

- `scripts/ci/p2_main_decomposition_guard.py`
- `tests_v9/test_p2_main_decomposition_guard.py`
- `.github/workflows/p2-main-decomposition.yml`

The guard enforces:

- actuator `main.py <= 80 LOC`
- SAM2 `main.py <= 170 LOC`
- weather `main.py <= 80 LOC`
- heavy runtime functions must stay out of the shell `main.py` files
- runtime modules must remain present

## Inventory/Guard Support Updates

Updated route inventory and mount guards to support programmatic route registration patterns such as:

```python
app.get("/path")(runtime.handler)
```

Updated:

- `scripts/ci/generate_service_inventory.py`
- `scripts/ci/route_mount_contract_guard.py`

Regenerated:

- `SERVICE_REGISTRY.md`
- `service_inventory.generated.json/csv`
- `route_inventory.generated.json/csv`
- `route_mount_inventory.generated.json/csv`
- `api_versioning_inventory.generated.json/csv`
- `health_readiness_inventory.generated.json/csv`
- `contract_capabilities_inventory.generated.json/csv`
- `test_dependency_inventory.generated.json/csv`
- `dependency_inventory.generated.json/csv`
- `dependency_conflicts.generated.json/csv`

## Verification

### Tests

Weather service tests:

```text
15 passed, 1 skipped
```

Non-weather service tests:

```text
18 passed
```

Guard tests:

```text
9 passed
```

The skipped test is the optional Redis live integration requiring `WEATHER_REDIS_INTEGRATION_URL`.

### Guards

Successful direct guard checks included:

- `p2_main_decomposition_guard.py`
- `p1_main_decomposition_guard.py`
- `auth_main_decomposition_guard.py`
- `ai_agronomist_main_decomposition_guard.py`
- `route_mount_contract_guard.py --check`
- `api_versioning_policy_guard.py --check`
- `health_readiness_schema_guard.py --check`
- `contract_capabilities_schema_guard.py --check`
- `test_requirements_inventory_guard.py --check`
- `dependency_pin_guard.py`
- `dependency_inventory_guard.py --check`
- `service_dependency_conflict_guard.py --check`
- `build_service_dependency_bundle.py --check`
- `pip_mirror_contract_guard.py`
- `internal_graphql_security_guard.py`
- `health_alias_contract_guard.py`
- `edge_model_contract_guard.py`
- `edge_production_readiness_guard.py`
- `production_honesty_guard.py`
- `generate_service_inventory.py --check`

## Result

Completed:

- P0: `auth/main.py`
- P0: `ai_agronomist/main.py`
- P1: `sahool-platform/api/main.py` residual bootstrap
- P1: `odoo-bridge/main.py`
- P1: `vegetation-analysis-service/main.py`
- P2: `actuator-service/main.py`
- P2: `sam2-inference/main.py`
- P2: `weather-service/main.py`

Remaining production certification items are not main.py decomposition items:

- full branch CI
- connected transitive lock generation
- Redis live integration
- ONNX/SAM2 model provisioning on real deployment hosts
