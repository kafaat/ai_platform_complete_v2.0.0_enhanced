# SAHOOL v9.0 Route & main.py Comprehensive Fix Report — 2026-07-09

## Scope

This patch addresses the route/main.py audit findings with low-risk, verifiable changes:

- zero-route `main.py` verification after router decomposition;
- internal service-to-service route security guard;
- GraphQL read facade security controls;
- duplicate `/healthz` + `/health` decorator cleanup;
- API versioning inventory/freeze policy;
- regenerated service/route registry inventory.

## Changes Applied

### 1. Zero-route `main.py` verification

Added:

- `scripts/ci/route_mount_contract_guard.py`
- `tests_v9/test_route_mount_contract_guard.py`
- `route_mount_inventory.generated.json`
- `route_mount_inventory.csv`

Result:

- 25 entrypoints inventoried.
- `main.py` files with no direct route decorators are now classified as one of:
  - `delegated_routes` via `router_registry.register_routers(app)`;
  - `factory_delegated_routes` via app factory (raster-service);
  - `non_http_entrypoint` for documented workers/bots;
  - violation if an unmounted FastAPI app is found.

This closes the audit concern that zero-route `main.py` files may be dead code.

### 2. Internal route security guard

Added:

- `scripts/ci/internal_graphql_security_guard.py`
- `tests_v9/test_internal_graphql_security_guard.py`

The guard verifies both internal platform routes remain protected by service token dependency:

- `GET /internal/fields/{field_id}/state`
- `POST /internal/events/ai-advice`

It also verifies the platform service-token guard references `X-Agent-Token`.

### 3. Knowledge Graph GraphQL controls

Updated:

- `services/knowledge-graph/main.py`

Added GraphQL budget controls:

- `KG_GRAPHQL_MAX_QUERY_BYTES` default `4096`;
- `KG_GRAPHQL_MAX_DEPTH` default `6`;
- `KG_GRAPHQL_MAX_TOKENS` default `120`;
- introspection disabled (`__schema`, `__type`);
- existing tenant guard preserved: `Depends(require_trusted_tenant)`;
- read-only facade preserved; mutation/delete/update still rejected by `graphql_readonly`.

This closes the audit finding that `/graphql` needed explicit depth/complexity controls.

### 4. Duplicate health decorator cleanup

Updated services that had stacked `/healthz` and `/health` decorators on the same function:

- `services/agriai-engine/main.py`
- `services/field-segmentation/main.py`
- `services/indicators-service/main.py`
- `services/local-ai-rag/main.py`
- `services/sam2-inference/main.py`

Policy now:

- `/healthz` is canonical liveness;
- `/health` remains a hidden legacy alias (`include_in_schema=False`) where retained;
- no handler should be decorated with both `/healthz` and `/health`.

Added:

- `scripts/ci/health_alias_contract_guard.py`
- `tests_v9/test_health_alias_contract_guard.py`

### 5. API versioning inventory / freeze policy

Added:

- `scripts/ci/api_versioning_policy_guard.py`
- `tests_v9/test_api_versioning_policy_guard.py`
- `api_versioning_inventory.generated.json`
- `api_versioning_inventory.csv`
- `api_versioning_legacy_allowlist.generated.json`

This does not rewrite all legacy routes because that would be a client-breaking API migration.
Instead it freezes the current inventory and forces future drift review.

Classifications:

- `versioned`
- `infra`
- `internal_s2s`
- `graphql_facade`
- `legacy_unversioned_business`

New business routes should use `/v1` unless explicitly reviewed.

### 6. Regenerated service registry

Ran:

```bash
python scripts/ci/generate_service_inventory.py --write-registry
```

Current generated inventory:

- 28 services
- 872 routes

The route count increased because the new guard/test endpoints added additional static routes and inventory files were regenerated accordingly.

## Verification

### Test subset

```bash
pytest -q \
  services/weather-service/tests \
  services/edge-inference/tests \
  services/mcp_servers/tests \
  services/agriai-engine/tests \
  services/knowledge-graph/tests \
  services/rag-retrieval/tests \
  services/indicators-service/tests \
  tests_v9/test_route_mount_contract_guard.py \
  tests_v9/test_internal_graphql_security_guard.py \
  tests_v9/test_health_alias_contract_guard.py \
  tests_v9/test_api_versioning_policy_guard.py \
  tests_v9/test_unit_test_environment_dependencies.py \
  tests_v9/test_dockerfile_pip_mirror_guard.py
```

Result:

```text
39 passed, 1 skipped in 19.86s
```

The skipped test is the optional live Redis integration test requiring `WEATHER_REDIS_INTEGRATION_URL`.

### Guard verification

Executed successfully:

```bash
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/dependency_pin_guard.py
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/api_versioning_policy_guard.py --check
python scripts/ci/internal_graphql_security_guard.py
python scripts/ci/health_alias_contract_guard.py
python scripts/ci/compose_reference_guard.py
python scripts/ci/nginx_weather_edge_path_guard.py
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
python scripts/ci/production_honesty_guard.py
python scripts/ci/test_requirements_inventory_guard.py --check
```

The first long combined run timed out after printing the early guard successes, so the remaining guards were run directly and passed.

## Honest Remaining Work

1. Full branch CI remains the production gate.
2. API versioning was inventoried and frozen, not fully migrated to `/v1` because that is a breaking client contract change.
3. GraphQL depth/complexity controls are static-budget controls, not a full GraphQL query planner because the service uses a dependency-free read-only GraphQL-like facade.
4. Live Redis and ONNX provisioning remain environment/operator tasks.

## Verdict

The route/main.py audit findings are now addressed as governance-enforced controls:

```text
zero-route main.py ambiguity closed
internal route token guard enforced
GraphQL tenant + budget controls enforced
health alias duplication removed
API versioning drift frozen and inventoried
SERVICE_REGISTRY regenerated
```
