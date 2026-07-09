# Indicators Service Container Review & Fix Report — 2026-07-09

## Scope

Reviewed `services/indicators-service` as packaged in the current release-candidate branch.

Files reviewed/updated:

- `services/indicators-service/main.py`
- `services/indicators-service/Dockerfile`
- `services/indicators-service/requirements.txt`
- `docker-compose.v9.yml`
- `services/indicators-service/tests/*`
- CI guards related to health/readiness, contract/capabilities, production honesty, and dependency inventory.

## Final container role

`indicators-service` is intentionally **health-only** in this build.

It does **not** own real indicator computation yet. Indicator computation remains owned by:

- `sahool-platform`
- `raster-service`

Therefore the service must be treated as a boundary placeholder and must not fabricate indicator results.

## Findings and fixes

### 1. Dockerfile liveness check corrected

**Finding:** The service reports `/readyz` as `degraded` honestly while it remains health-only. Docker liveness must not use degraded readiness as the process health signal.

**Fix:** Dockerfile `HEALTHCHECK` now uses:

```text
/healthz
```

not:

```text
/readyz
```

### 2. Removed unused runtime dependencies

**Finding:** `requirements.txt` included DB/cache/event dependencies that are not used by a health-only service:

- `asyncpg`
- `nats-py`
- `redis`
- `prometheus-client`
- `pydantic`

This increased image surface area and could create false deployment coupling.

**Fix:** `requirements.txt` is now minimal:

```text
fastapi==0.136.3
uvicorn[standard]==0.30.6
```

### 3. Removed unnecessary Compose infrastructure coupling

**Finding:** `docker-compose.v9.yml` passed unused env vars and required infra dependencies:

- `DATABASE_URL`
- `REDIS_URL`
- `NATS_URL`
- `depends_on: sahool-postgres`
- `depends_on: sahool-redis`
- `depends_on: sahool-nats`

This could block a health-only container from starting even though it does not use those systems.

**Fix:** Compose now declares only:

```text
CORS_ORIGINS
INDICATORS_RUNTIME_MODE=health-only
```

and keeps a `/healthz` healthcheck.

### 4. Added a dedicated indicators container contract guard

Added:

```text
scripts/ci/indicators_container_contract_guard.py
tests_v9/test_indicators_container_contract_guard.py
.github/workflows/indicators-container-contract.yml
```

The guard enforces:

- health-only requirements are minimal
- Dockerfile liveness uses `/healthz`, not degraded `/readyz`
- no unused DB/Redis/NATS env/depends_on in Compose
- no fabricated compute path
- `INDICATORS_RUNTIME_MODE=health-only` is explicit
- PyPI-default + pip retry/timeout policy remains present

## Current routes

`indicators-service` exposes 7 routes:

| Method | Path | Classification |
|---|---|---|
| GET | `/healthz` | liveness |
| GET | `/health` | legacy hidden alias |
| GET | `/readyz` | honest degraded readiness |
| GET | `/capabilities` | health-only capability contract |
| GET | `/contract` | service contract |
| POST | `/v1/indicators/compute` | fail-closed 501 |
| GET | `/` | informational root |

## Current readiness policy

`/healthz`:

```text
status=alive
```

`/readyz`:

```text
status=degraded
implemented_runtime=false
health_only=true
```

`/v1/indicators/compute`:

```text
HTTP 501
No fabricated indicator result is returned.
```

## Verification

Targeted tests:

```text
7 passed
```

Direct guards:

```text
indicators_container_contract_guard_ok
production honesty guard passed
PyPI-default + Alibaba override pip mirror contract guard passed
monorepo service dependency pin guard passed
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
route_mount_inventory_check_ok
health_readiness_schema_guard_ok
contract_capabilities_schema_check_ok
route_residual_classification_check_ok
test_dependency_inventory_check_ok
production_evidence_pack_check_ok
```

Generated inventories were refreshed after trimming requirements:

- `dependency_inventory.generated.json`
- `dependency_inventory.csv`
- `dependency_conflicts.generated.json`
- `dependency_conflicts.csv`
- `requirements.services.direct.lock`
- `service_inventory.generated.json`
- `route_inventory.generated.json`
- `SERVICE_REGISTRY.md`

## Final judgement

`indicators-service` is now a truthful and lightweight health-only container.

It is not production-ready as an indicator compute service, but it is now safe as a non-authoritative health-only boundary:

```text
alive for liveness
not ready for computation
fail-closed for compute
no fake indicator output
no unnecessary DB/Redis/NATS coupling
```

## Remaining work if indicators-service is promoted later

Before making it authoritative for indicator computation, add:

1. Real indicator engine ownership contract.
2. Raster/tile input contract.
3. Tenant auth and service-token enforcement for compute endpoints.
4. Persistence/event publishing only after real runtime ownership exists.
5. Readiness transition from `degraded` to `ready` only with runtime evidence.
