# Sahool Governance Hardening Continuation 2 — 2026-07-09

## Scope

This continuation closes the remaining operational hardening gaps left after the first governance baseline:

- monorepo-wide direct dependency pinning,
- Redis cache integration coverage for weather-service,
- explicit Edge ONNX model provisioning contract,
- CI guards preventing model-contract drift,
- stricter Edge readiness validation tests.

## Changes implemented

### 1. Monorepo-wide service dependency pinning

All `services/**/requirements*.txt` direct dependencies are now exact-pinned using `==`.

Updated guard:

- `scripts/ci/dependency_pin_guard.py`

The guard now scans all service requirements files, not just the previously hardened subset.

Updated inventory guard:

- `scripts/ci/dependency_inventory_guard.py`

`--check` now fails on any unpinned service dependency, not only strict-service dependencies.

Generated artifacts were refreshed:

- `dependency_inventory.generated.json`
- `dependency_inventory.csv`

Current result:

```text
199 direct service dependencies
0 unpinned/ranged dependencies
0 strict-service violations
```

### 2. Redis cache coverage for weather-service

Added positive Redis-backend coverage with an in-process fake Redis module:

- `services/weather-service/tests/test_weather_readyz_and_cache_backend.py`

Added optional live Redis integration test:

- `services/weather-service/tests/test_weather_redis_live_optional.py`

Added helper runner:

- `scripts/ci/run_weather_redis_integration.sh`

This uses `docker-compose.test.yml` and `WEATHER_REDIS_INTEGRATION_URL` to run a live Redis roundtrip without making the default unit suite depend on Docker.

### 3. Edge model provisioning contract

Added explicit model manifest:

- `services/edge-inference/models_manifest/edge_models.required.json`

Added operator documentation:

- `services/edge-inference/MODEL_PROVISIONING.md`

The repository intentionally does not package ONNX weights. Operators must provision:

- `/models/pest_detector_int8.onnx`
- `/models/yield_estimator_int8.onnx`

### 4. Edge model contract guard

Added:

- `scripts/ci/edge_model_contract_guard.py`
- `.github/workflows/edge-model-contract.yml`

The guard verifies:

- `EDGE_READINESS_MODE` is supported by runtime and compose,
- required model env/path contracts are present,
- ONNX model files are not accidentally committed into the service repository.

### 5. Edge readiness tests strengthened

Updated:

- `services/edge-inference/tests/test_edge_capabilities_and_fail_closed.py`

New coverage proves:

- strict readiness returns `503` when models are absent,
- strict readiness returns `200` only when both model files are present and `onnxruntime` is available,
- partial readiness remains degraded but HTTP-200 for optional Edge deployments.

### 6. Compose exposure for readiness policy

Updated:

- `docker-compose.v9.yml`

Added:

```yaml
EDGE_READINESS_MODE: ${EDGE_READINESS_MODE:-partial}
```

## Verification run

### Targeted tests

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
30 passed, 1 skipped in 2.49s
```

The skipped test is the optional live Redis integration test, which runs only when `WEATHER_REDIS_INTEGRATION_URL` is set.

### CI guards

```bash
python scripts/ci/edge_inference_service_contract_gate.py
python scripts/ci/weather_service_real_contract_gate.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/compose_reference_guard.py
python scripts/ci/nginx_weather_edge_path_guard.py
python scripts/ci/edge_model_contract_guard.py
```

Result:

```text
✓ Edge inference service contract gate passed
✓ Weather-service real runtime contract gate passed
✓ monorepo service dependency pin guard passed
dependency_inventory_check_ok
✓ compose reference guard passed
✓ nginx weather/edge path guard passed
✓ edge model contract guard passed
```

## Final status

The package is now:

```text
Governed runtime-real baseline + monorepo direct dependency pins + explicit Edge model provisioning contract
```

Remaining honest limitations:

1. Edge ONNX model weights are still not shipped, by design. Operators must provision them.
2. Dependency locking is now exact for direct service requirements, but no transitive lock file has been resolved offline.
3. Redis live integration is available but optional; default CI still uses fake Redis to stay deterministic without Docker.
