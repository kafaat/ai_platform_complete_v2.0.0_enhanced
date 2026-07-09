# Sahool Governance Hardening Continuation 3 — 2026-07-09

## Scope
This continuation closes the remaining governance gap that could not honestly be called a full transitive lock in the previous package. It adds:

1. Cross-service dependency conflict inventory.
2. Deterministic direct-dependency bundle.
3. Connected-CI script for true transitive lock compilation with pip-tools.
4. Edge production-required readiness policy.
5. CI workflows for the new guards.

## Implemented Changes

### Dependency conflict governance
Added:

- `scripts/ci/service_dependency_conflict_guard.py`
- `dependency_conflicts.generated.json`
- `dependency_conflicts.csv`
- `.github/workflows/dependency-conflict-inventory.yml`

Current result:

- 199 direct service dependencies
- 0 unpinned/ranged direct dependencies
- 15 packages with cross-service version divergence

This does not fail the build by default because Sahool uses service-local images; different services may intentionally pin different versions. The report prevents hidden drift and explains why a single global Python environment is unsafe.

### Direct dependency bundle
Added:

- `scripts/ci/build_service_dependency_bundle.py`
- `requirements.services.direct.lock`

This is explicitly labelled as a direct lock bundle, not a transitive resolver output.

### True transitive lock compilation path
Added:

- `scripts/ci/compile_transitive_service_locks.sh`
- `.github/workflows/transitive-lock-compile-manual.yml`

This script uses pip-tools in connected CI to compile per-service `requirements.lock` files with hashes. It was not run in this offline container because true transitive resolution requires package-index access or an internal mirror.

### Edge production-required readiness policy
Modified:

- `services/edge-inference/main.py`
- `services/edge-inference/tests/test_edge_capabilities_and_fail_closed.py`
- `docker-compose.v9.yml`

Added:

- `EDGE_PRODUCTION_REQUIRED=true|false`
- `scripts/ci/edge_production_readiness_guard.py`
- `.github/workflows/edge-production-readiness.yml`

Behavior:

- Development/optional deployments may keep `EDGE_READINESS_MODE=partial` and receive HTTP 200 degraded readiness when models are missing.
- Production-required deployments set `EDGE_PRODUCTION_REQUIRED=true`; this forces strict readiness and returns HTTP 503 unless all required ONNX models are present and onnxruntime is available.

## Verification

### Tests

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
31 passed, 1 skipped in 2.78s
```

The skipped test is the optional live Redis integration test, which requires `WEATHER_REDIS_INTEGRATION_URL`.

### CI guards

Executed successfully:

```bash
python scripts/ci/edge_inference_service_contract_gate.py
python scripts/ci/weather_service_real_contract_gate.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/compose_reference_guard.py
python scripts/ci/nginx_weather_edge_path_guard.py
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
```

Notes:

- The long combined command timed out in the container after printing most guard successes, so the remaining Edge guards were run immediately afterward and passed.
- `generate_service_inventory.py --write-registry` was run first to refresh `SERVICE_REGISTRY.md`, then `--check` passed.

## Remaining Honest Gaps

1. ONNX models are still operator-provisioned and not included in the repository.
2. True transitive locks were not generated in this offline environment. The connected-CI workflow and compile script are now present.
3. Redis live integration remains optional and requires an external Redis URL.

## Verdict

The package is now:

```text
Governed runtime-real baseline
+ monorepo direct dependency pins
+ dependency conflict inventory
+ direct lock bundle
+ connected-CI transitive lock compiler
+ Edge production-required readiness policy
```
