# Vegetation Analysis Service Container Review and Fix — 2026-07-09

## Scope

Reviewed `services/vegetation-analysis-service` after P1 decomposition:

- `Dockerfile`
- `requirements.txt`
- `main.py`
- `vegetation_runtime.py`
- `routers/health.py`
- `routers/analysis.py`
- `docker-compose.v9.yml`
- existing vegetation static/behavioral tests

## Findings

### F1 — Docker image did not copy `vegetation_runtime.py`

`main.py` imports `vegetation_runtime`, but the Dockerfile copied only:

- `main.py`
- `router_registry.py`
- `routers/`
- `shared/`

This would make the container fail at startup with `ModuleNotFoundError: vegetation_runtime`.

### F2 — Dockerfile carried unnecessary build/database packages

The service does not own a DB pool. It reads platform fields through platform API and uses HTTP/NATS best-effort paths. `gcc` and `libpq-dev` were unnecessary in this image.

### F3 — malformed inline PyJWT requirement comment

`requirements.txt` had `PyJWT==2.13.0# ...` without spacing before the inline comment. This is easy to misparse across tooling and should be normalized.

### F4 — readiness response was too thin

`/readyz` returned only `{"status":"ready"}`. That was operationally truthful but not descriptive enough for the existing health/readiness schema discipline. It now includes service name, ready flag, implemented runtime, runtime mode, and dependency modes.

### F5 — compose hard-blocked service startup on NATS

Runtime publishing to NATS is best-effort and fail-soft. `depends_on: sahool-nats` made NATS a hard startup dependency, which contradicted the runtime contract.

### F6 — stale tests still inspected `main.py` only

After P1 decomposition, several static and monkeypatch tests still inspected/patched `main.py` only, while the implementation moved to `vegetation_runtime.py`.

## Changes Applied

### Dockerfile

- Added:
  - `COPY services/vegetation-analysis-service/vegetation_runtime.py /app/vegetation_runtime.py`
- Kept liveness on `/healthz`.
- Removed unnecessary `gcc libpq-dev` apt packages.

### requirements.txt

- Normalized PyJWT line:
  - `PyJWT==2.13.0  # ...`

### Health/readiness router

`/healthz` now returns:

```json
{"status":"alive","service":"vegetation-analysis-service"}
```

`/readyz` now returns a richer truthful runtime contract:

```json
{
  "status": "ready",
  "service": "vegetation-analysis-service",
  "ready": true,
  "implemented_runtime": true,
  "runtime_mode": "vegetation-estimate-with-raster-pass-through",
  "dependencies": {
    "platform_api": "optional",
    "raster_service": "optional_fail_soft",
    "nats": "best_effort_publish"
  }
}
```

### Compose

- Removed hard `depends_on: sahool-nats` from `sahool-vegetation-analysis`.
- Added explicit documentation env:
  - `VEGETATION_NATS_PUBLISH_MODE=best_effort`

### Test compatibility after decomposition

Updated stale tests so they inspect/patch both `main.py` and `vegetation_runtime.py`:

- `tests_v9/test_vegetation_raster_ndvi.py`
- `tests_v9/test_sentinel_field_source.py`

### New guard

Added:

- `scripts/ci/vegetation_container_contract_guard.py`
- `tests_v9/test_vegetation_container_contract_guard.py`
- `.github/workflows/vegetation-container-contract.yml`

The guard prevents regressions where:

- Dockerfile stops copying `vegetation_runtime.py`
- Docker liveness switches from `/healthz` to `/readyz`
- unnecessary DB/build packages return
- malformed PyJWT requirement comment returns
- readiness schema loses required truth keys
- compose hard-blocks vegetation startup on NATS again

### Runtime smoke profile

Added vegetation container guard to `scripts/ci/runtime_real_smoke.sh`.

## Verification

### Vegetation focused tests

```text
43 passed in 4.60s
```

Covered:

- `services/vegetation-analysis-service/test_vegetation_logic.py`
- `services/vegetation-analysis-service/test_vegetation_router_decomposition_guard.py`
- `tests_v9/test_vegetation_raster_ndvi.py`
- `tests_v9/test_sentinel_field_source.py`
- `tests_v9/test_vegetation_container_contract_guard.py`

### Guards

Passed:

```text
p1_main_decomposition_guard_ok
vegetation_container_contract_guard_ok
route_mount_inventory_check_ok
health_readiness_schema_guard_ok
test_dependency_inventory_check_ok
dependency inventory: 194 direct deps, 0 unpinned/ranged
dependency conflict report: 15 known cross-service divergences
direct_dependency_bundle_check_ok
PyPI-default + Alibaba override pip mirror contract guard passed
production honesty guard passed
production_evidence_pack_check_ok
```

### Runtime smoke note

`runtime_real_smoke.sh` static guards completed, and its pytest phase reached the later schema guard stage but timed out in this chat execution window. The remaining schema tests were re-run separately and passed:

```text
5 passed in 10.81s
```

The known optional skip remains the weather Redis live test when `WEATHER_REDIS_INTEGRATION_URL` is not set.

## Final Judgment

`vegetation-analysis-service` is now container-consistent after decomposition:

- Docker image ships the runtime module it imports.
- Liveness/readiness are separated correctly.
- NATS is documented and treated as best-effort rather than a hard startup dependency.
- The service remains honest: estimated vegetation values are labeled, raster-service pass-through is fail-soft, and no fabricated real raster output is claimed.

Remaining production certification blockers are unchanged: full branch CI, connected transitive locks, model provisioning, and live Redis evidence.
