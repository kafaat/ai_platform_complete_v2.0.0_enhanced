# Governance Hardening Continuation Report — 2026-07-09

## Scope

Continuation of the governed runtime-real baseline hardening for `sahool_ai_platform_6bf6465_governance_hardened`.

This pass focused on closing the next operational gaps without introducing new product features:

1. Edge readiness policy modes.
2. Weather readiness/cache behavior tests.
3. Hardened-service dependency inventory and strict pin enforcement.
4. Compose reference guard.
5. Nginx weather/edge path guard.
6. Regeneration of service/route/dependency inventories.

## Implemented changes

### Edge inference readiness policy

Modified:

- `services/edge-inference/main.py`
- `services/edge-inference/tests/test_edge_capabilities_and_fail_closed.py`

Added `EDGE_READINESS_MODE`:

- `partial` default: `/readyz` returns HTTP 200 with `status=degraded` when no ONNX models are present. Inference endpoints still fail closed with 503.
- `strict`: `/readyz` returns HTTP 503 unless all required ONNX-backed capabilities are active.

The `/capabilities` and `/readyz` payloads now include:

- `readiness_mode`
- `active_capability_count`
- `required_capability_count`
- `all_required_models_active`
- per-capability `reason`

### Weather readiness/cache tests

Added:

- `services/weather-service/tests/test_weather_readyz_and_cache_backend.py`

Locked behavior:

- `/readyz` reports `ready` when Open-Meteo readiness probe succeeds.
- `/readyz` reports `degraded` when the upstream probe fails.
- Redis-configured-but-unavailable cache falls back to memory without breaking runtime.

### Hardened-service dependency inventory

Added:

- `scripts/ci/dependency_inventory_guard.py`
- `dependency_inventory.generated.json`
- `dependency_inventory.csv`
- `.github/workflows/dependency-inventory-drift.yml`

The guard records all direct Python service requirements and fails in `--check` mode when:

1. Generated dependency inventory drifts from committed inventory.
2. Any hardened service contains an unpinned/ranged direct dependency.

Hardened services now enforced:

- `weather-service`
- `edge-inference`
- `mcp_servers`
- `agriai-engine`
- `knowledge-graph`
- `rag-retrieval`
- `indicators-service`

Pinned additional direct requirements in:

- `services/mcp_servers/requirements.txt`
- `services/agriai-engine/requirements.txt`
- `services/indicators-service/requirements.txt`

Remaining monorepo-wide dependency state is transparent in `dependency_inventory.generated.json`: 199 direct dependency lines discovered; 87 remain ranged/unpinned outside the hardened service set.

### Existing pin guard expanded

Modified:

- `scripts/ci/dependency_pin_guard.py`

It now checks the full hardened service set, not only weather-service and edge-inference.

### Compose reference guard

Added:

- `scripts/ci/compose_reference_guard.py`
- `.github/workflows/compose-reference-guard.yml`

This prevents `docker-compose.fixed.yml` and `docker-compose.unified.yml` from reappearing at repository root, and confirms that `docker-compose.v9.yml` remains the production-reference local runtime.

### Nginx weather/edge path guard

Added:

- `scripts/ci/nginx_weather_edge_path_guard.py`
- `.github/workflows/nginx-weather-edge-paths.yml`

This statically verifies the production nginx config still exposes:

- `/api/weather/`
- `/api/weather/readyz`
- `/api/edge/`

with the expected proxy paths.

### Inventory regeneration

Regenerated:

- `SERVICE_REGISTRY.md`
- `service_inventory.generated.json`
- `route_inventory.generated.json`
- `service_inventory.csv`
- `route_inventory.csv`
- `dependency_inventory.generated.json`
- `dependency_inventory.csv`

Current generated service inventory remains:

- 28 services
- 869 AST-discovered routes

## Verification performed

### Scoped runtime tests

Command:

```bash
pytest -q \
  services/weather-service/tests \
  services/edge-inference/tests \
  services/mcp_servers/tests \
  services/agriai-engine/tests \
  services/knowledge-graph/tests \
  services/rag-retrieval/tests \
  services/indicators-service/tests
```

Result:

```text
28 passed in 2.66s
```

### CI guards

Commands:

```bash
python scripts/ci/edge_inference_service_contract_gate.py
python scripts/ci/weather_service_real_contract_gate.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/compose_reference_guard.py
python scripts/ci/nginx_weather_edge_path_guard.py
```

Result:

```text
✓ Edge inference service contract gate passed
✓ Weather-service real runtime contract gate passed
✓ strict dependency pin guard passed for hardened runtime services
dependency_inventory_check_ok
✓ compose reference guard passed
✓ nginx weather/edge path guard passed
```

### Syntax checks

Command:

```bash
python -m py_compile \
  scripts/ci/dependency_inventory_guard.py \
  scripts/ci/compose_reference_guard.py \
  scripts/ci/nginx_weather_edge_path_guard.py \
  services/edge-inference/main.py \
  services/weather-service/main.py \
  services/weather-service/cache.py
```

Result: passed.

## Remaining honest gaps

1. Edge ONNX models are still not included; edge inference remains fail-closed unless operators provision model files.
2. Full monorepo dependency locking is not complete; the hardened services are pinned and guarded, but 87 direct dependency lines outside the hardened set remain ranged/unpinned.
3. Weather-service has Redis-capable cache and fallback tests, but no live Redis integration test was run in this environment.
4. Nginx path guard is static; deployment should still run live smoke checks against the actual gateway.

## Updated verdict

The package moves from:

`Governed runtime-real baseline`

To:

`Governed runtime-real baseline + hardened-service dependency guard + readiness policy controls`
