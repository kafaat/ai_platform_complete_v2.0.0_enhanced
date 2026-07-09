# Container Fleet Review and Fix Report — 2026-07-09

## Scope

Reviewed the remaining service containers after the dedicated `indicators-service` and `vegetation-analysis-service` passes.

Focus areas:

- Dockerfile runtime copy completeness after P0/P1/P2 decomposition.
- Docker `HEALTHCHECK` liveness semantics.
- Python package install governance: official PyPI default, Alibaba override, timeout/retries.
- Known startup import risks caused by Dockerfiles copying only selected files.

## Findings fixed

### 1. `auth` Dockerfile missed the P0 MFA runtime module

`services/auth/main.py` imports `mfa_runtime.py` after P0 decomposition, but the image copied `main.py`, routers, `otp.py`, and `mfa_crypto.py` only.

Fixed by adding:

```dockerfile
COPY services/auth/mfa_runtime.py /app/mfa_runtime.py
```

### 2. `mcp_servers` Dockerfile missed market authorization helper

`market_server.py` imports `market_db_authz.py`, but the Dockerfile copied selected MCP server files and omitted the helper.

Fixed by adding:

```dockerfile
COPY services/mcp_servers/market_db_authz.py /app/
```

### 3. `qdrant-seed` Dockerfile missed Al Jawf knowledge module

`seed.py` can import `aljawf_knowledge.py`, but the image copied only `seed.py`.

Fixed by adding:

```dockerfile
COPY services/qdrant-seed/aljawf_knowledge.py /app/aljawf_knowledge.py
```

### 4. Docker liveness probes were using readiness endpoints

For HTTP service containers, Docker health is process liveness. Dependency readiness belongs to `/readyz` and orchestrator readiness checks, not Docker liveness.

Updated the following Dockerfiles to use `/healthz`:

- `services/auth/Dockerfile`
- `services/field-segmentation/Dockerfile`
- `services/soil-service/Dockerfile`
- `services/weather-service/Dockerfile`
- `services/supervisor-agent/Dockerfile`
- `services/sahool-platform/Dockerfile`
- `services/sam2-inference/Dockerfile`

This prevents containers from being marked unhealthy solely because DB/upstream/model readiness is degraded while the process is alive.

## Guard added

Added:

```text
scripts/ci/container_fleet_contract_guard.py
tests_v9/test_container_fleet_contract_guard.py
.github/workflows/container-fleet-contract.yml
```

The guard enforces:

- `auth` image copies `mfa_runtime.py`.
- `mcp_servers` image copies `market_db_authz.py`.
- `qdrant-seed` image copies `aljawf_knowledge.py`.
- selected HTTP Docker healthchecks use `/healthz`, not `/readyz`.
- known startup import regressions cannot return silently.

The guard was also added to:

```text
scripts/ci/runtime_real_smoke.sh
```

## Audit artifacts

Generated:

```text
container_fleet_audit.generated.json
container_fleet_audit.csv
```

## Verification

Commands run:

```bash
python scripts/ci/container_fleet_contract_guard.py
pytest -q tests_v9/test_container_fleet_contract_guard.py
python -m py_compile scripts/ci/container_fleet_contract_guard.py tests_v9/test_container_fleet_contract_guard.py
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/pip_audit_resolution_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
```

Results:

```text
container_fleet_contract_guard_ok
1 passed
PyPI-default + Alibaba override pip mirror contract guard passed
pip_audit_resolution_guard_ok
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
route_mount_inventory_check_ok
test_dependency_inventory_check_ok
```

## Current judgement

The remaining containers are now more consistent with the post-decomposition runtime shape. The most important concrete fixes were startup-copy completeness for `auth`, `mcp_servers`, and `qdrant-seed`, and avoiding `/readyz` as Docker liveness where readiness can legitimately degrade.

This is still not a full Docker build matrix result. A connected CI runner should run the container build matrix as part of Production Certification.
