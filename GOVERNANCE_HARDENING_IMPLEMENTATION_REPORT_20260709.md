# Governance Hardening Implementation Report — 2026-07-09

## Scope

Implemented the Runtime-Real Governance Hardening package for `sahool_ai_platform_6bf6465`:

- Generated service and route inventory from source code.
- Regenerated `SERVICE_REGISTRY.md` from actual services/routes.
- Added CI drift guard for inventory/registry.
- Added smoke/static tests for previously zero-test critical services.
- Added Edge `/capabilities` and degraded readiness semantics.
- Hardened Weather `/readyz` with Open-Meteo probe, Redis-capable cache, and circuit breaker.
- Moved stale compose files to `legacy/compose/` to reduce runtime drift.
- Added strict dependency pin guard for hardened Weather/Edge services.

## Modified / Added Files

### Governance inventory

- `scripts/ci/generate_service_inventory.py`
- `SERVICE_REGISTRY.md`
- `service_inventory.generated.json`
- `route_inventory.generated.json`
- `service_inventory.csv`
- `route_inventory.csv`
- `.github/workflows/service-inventory-drift.yml`

### Weather service hardening

- `services/weather-service/main.py`
- `services/weather-service/open_meteo.py`
- `services/weather-service/cache.py`
- `services/weather-service/requirements.txt`

Implemented:

- `/readyz` now reports `ready` or `degraded` based on a real Open-Meteo readiness probe.
- `upstream_open_meteo` readiness details.
- `circuit_breaker` state.
- Optional Redis cache via `WEATHER_REDIS_URL` or `REDIS_URL`.
- Memory fallback if Redis is absent/unavailable.
- Stale cache semantics preserved.

### Edge inference hardening

- `services/edge-inference/main.py`
- `services/edge-inference/requirements.txt`
- `services/edge-inference/tests/test_edge_capabilities_and_fail_closed.py`

Implemented:

- `/capabilities` endpoint.
- `/readyz` degraded/ready semantics based on token + active ONNX capabilities.
- Capability details per model: file path, file presence, onnxruntime availability, active flag, reason.
- Tests for missing models, degraded readiness, and token rejection.

### Zero-test service smoke coverage

Added static route smoke tests:

- `services/mcp_servers/tests/test_mcp_servers_static_route_smoke.py`
- `services/agriai-engine/tests/test_agriai_engine_static_route_smoke.py`
- `services/knowledge-graph/tests/test_knowledge_graph_static_route_smoke.py`
- `services/rag-retrieval/tests/test_rag_retrieval_static_route_smoke.py`
- `services/indicators-service/tests/test_indicators_service_static_route_smoke.py`

### Compose drift cleanup

- `docker-compose.v9.yml` updated as production-reference runtime:
  - Weather gets `WEATHER_REDIS_URL` and Open-Meteo breaker envs.
  - Edge requires `EDGE_SYNC_TOKEN` and `SAHOOL_AGENT_TOKEN`.
- Moved to `legacy/compose/`:
  - `docker-compose.fixed.yml`
  - `docker-compose.unified.yml`
- Added `legacy/compose/README.md`.

### Dependency guard

- `scripts/ci/dependency_pin_guard.py`

Strictly enforces exact dependency pins for:

- `services/weather-service/requirements.txt`
- `services/edge-inference/requirements.txt`

## Verification

Executed successfully:

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
24 passed in 2.55s
```

Contract / CI gates executed successfully:

```bash
python scripts/ci/edge_inference_service_contract_gate.py
python scripts/ci/weather_service_real_contract_gate.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/generate_service_inventory.py --check
```

Results:

```text
✓ Edge inference service contract gate passed
✓ Weather-service real runtime contract gate passed
✓ strict dependency pin guard passed for weather-service and edge-inference
inventory_check_ok
```

## Current inventory baseline

Generated inventory now reports:

- Services: 28
- Routes: 869 using AST route decorators
- Previously zero-test critical services now have at least one smoke/static route test.

Note: the earlier manual count found 936 routes using broader grep-style discovery. The committed generator uses AST decorator parsing for CI determinism and avoids false positives from strings/docs/tests.

## Remaining honest gaps

- Full monorepo dependency lock is not complete; this patch enforces exact pins for Weather and Edge only and adds a guard for those hardened services.
- ONNX model binaries are still not included. Edge is capability-aware and fail-closed, but pest/yield inference remains dormant until operators provision real models.
- Weather Redis cache is optional and configured in `docker-compose.v9.yml`; production must provide Redis credentials.
- Circuit breaker is process-local. A distributed breaker would require Redis/shared state if multiple weather-service replicas are used.
