# Sahool Production Certification Checklist

This checklist is intentionally evidence-driven. The repository is a governed release candidate; it is not production-certified until the four blockers below are verified in the target CI/deployment environment.

## Certification state

`release_candidate_not_production_certified`

## Recommended closure order

1. `P-CERT-2` — Connected transitive lock generation
2. `P-CERT-1` — Full branch CI
3. `P-CERT-4` — ONNX/SAM2 model provisioning
4. `P-CERT-3` — Redis live integration

## Known local skipped test

`services/weather-service/tests/test_weather_redis_live_optional.py` is skipped unless `WEATHER_REDIS_INTEGRATION_URL` is set. This skip maps directly to `P-CERT-3`; it is acceptable for offline/local guard runs and unacceptable as final certification evidence.

## Blockers

### P-CERT-1 — Full branch CI

- Severity: `critical`
- Current status: `pending_external_ci`
- Certification rule: 0 failed, no unexpected critical skip, no inventory/guard drift

Required evidence:

- pytest -m unit exits 0
- platform test suite exits 0
- tsc --noEmit exits 0
- vitest run exits 0
- ruff check exits 0
- Docker build matrix exits 0
- release bundle exits 0
- all generated inventories are clean

Commands:

```bash
pytest -m unit
```
```bash
pytest services/sahool-platform/tests
```
```bash
tsc --noEmit
```
```bash
vitest run
```
```bash
ruff check .
```
```bash
docker build matrix
```
```bash
release bundle
```

### P-CERT-2 — Connected transitive lock generation

- Severity: `critical`
- Current status: `pending_connected_index_or_internal_mirror`
- Certification rule: reproducible locks generated from connected PyPI/default index or reviewed internal mirror

Required evidence:

- scripts/ci/compile_transitive_service_locks.sh exits 0 in connected CI
- official PyPI is the default index
- Alibaba mirror is only an explicit override
- Tencent mirror is not a default
- pip install uses --timeout 300 and --retries 10
- generated transitive lock files are committed or attached to the release bundle

Commands:

```bash
scripts/ci/compile_transitive_service_locks.sh
```
```bash
python scripts/ci/pip_mirror_contract_guard.py
```

### P-CERT-3 — Redis live integration

- Severity: `medium-critical`
- Current status: `pending_live_redis_endpoint`
- Certification rule: live Redis passes without downgrading readiness honesty

Required evidence:

- WEATHER_REDIS_INTEGRATION_URL points at a real Redis instance
- weather Redis live optional test exits 0
- cache write/read works
- stale fallback behavior remains verified
- /readyz reports cache backend truthfully

Commands:

```bash
WEATHER_REDIS_INTEGRATION_URL=redis://localhost:6379/0 pytest services/weather-service/tests/test_weather_redis_live_optional.py
```
```bash
scripts/ci/run_weather_redis_integration.sh
```

### P-CERT-4 — ONNX/SAM2 model provisioning

- Severity: `critical`
- Current status: `pending_operator_model_artifacts`
- Certification rule: strict readiness passes only with provisioned artifacts; absent artifacts fail closed

Required evidence:

- /models/pest_detector_int8.onnx exists in deployment environment
- /models/yield_estimator_int8.onnx exists in deployment environment
- SAM2 artifacts exist in deployment environment
- EDGE_READINESS_MODE=strict and EDGE_PRODUCTION_REQUIRED=true
- /readyz is ready when artifacts exist
- missing model still fails closed
- no simulation fallback is used

Commands:

```bash
python scripts/ci/edge_model_contract_guard.py
```
```bash
python scripts/ci/edge_production_readiness_guard.py
```
```bash
EDGE_READINESS_MODE=strict EDGE_PRODUCTION_REQUIRED=true pytest services/edge-inference/tests
```

## Non-negotiable policy

Do not change this checklist to `certified` by editing text. Certification requires fresh branch/deployment evidence for every blocker.
