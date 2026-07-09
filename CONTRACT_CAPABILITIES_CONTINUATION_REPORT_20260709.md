# SAHOOL v9.0 — Contract/Capabilities Continuation Report

Date: 2026-07-09
Base artifact: sahool_ai_platform_6bf6465_route_main_comprehensive_fixed.zip
Output artifact: sahool_ai_platform_6bf6465_contract_capabilities_fixed.zip

## Objective

Continue the route/main.py governance hardening by making `/contract` and `/capabilities`
endpoints machine-checkable. These endpoints are service-specific, but they now expose a
minimum common envelope so operators and clients can safely discover service ownership and
runtime capability status.

## Changes Implemented

### 1. Common `/contract` envelope

Updated services:

- `services/decision-service/main.py`
- `services/weather-service/main.py`

Contract endpoints now expose at least:

- `service`
- `contract_version`
- `implemented_runtime`

Existing service-specific fields are preserved.

### 2. Common `/capabilities` envelope

Updated services:

- `services/edge-inference/main.py`
- `services/indicators-service/main.py`

Capabilities endpoints now expose at least:

- `service`
- `schema_version`
- `capabilities`

Existing service-specific fields are preserved.

### 3. Contract/capabilities schema guard

Added:

- `scripts/ci/contract_capabilities_schema_guard.py`
- `tests_v9/test_contract_capabilities_schema_guard.py`
- `.github/workflows/contract-capabilities-schema.yml`
- `contract_capabilities_inventory.generated.json`
- `contract_capabilities_inventory.csv`

The guard scans `services/**/main.py` and `bots/**/main.py` for direct `/contract` and
`/capabilities` FastAPI endpoints. It fails if any endpoint misses the required envelope keys.

### 4. Inventory refresh

Regenerated after the endpoint schema changes:

- `service_inventory.generated.json`
- `route_inventory.generated.json`
- `SERVICE_REGISTRY.md`
- `api_versioning_inventory.generated.json`
- `api_versioning_inventory.csv`
- `api_versioning_legacy_allowlist.generated.json`

## Verification

### Targeted tests

Command:

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
  tests_v9/test_contract_capabilities_schema_guard.py \
  tests_v9/test_unit_test_environment_dependencies.py \
  tests_v9/test_dockerfile_pip_mirror_guard.py
```

Result:

```text
40 passed, 1 skipped in 18.45s
```

The skipped test is the optional live Redis integration test requiring
`WEATHER_REDIS_INTEGRATION_URL`.

### CI guards

Successful guards:

```text
✓ PyPI-default + Alibaba override pip mirror contract guard passed
✓ monorepo service dependency pin guard passed
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
internal_graphql_security_guard_ok
health_alias_contract_guard_ok
contract_capabilities_schema_check_ok
✓ edge model contract guard passed
✓ edge production readiness guard passed
✓ production honesty guard passed
test_dependency_inventory_check_ok
```

## Status

The artifact is now a governed runtime-real release candidate with:

- route/main.py ambiguity controls
- internal route service-token controls
- GraphQL security budget controls
- health alias cleanup
- API versioning inventory/freeze policy
- `/contract` and `/capabilities` common schema envelopes

## Remaining Honest Gaps

1. Full branch CI remains the final certification gate.
2. Transitive dependency locks still require connected CI or an internal mirror.
3. Redis live integration requires a real Redis URL.
4. Edge production readiness requires operator-provisioned ONNX model files.
5. A full migration of legacy unversioned business routes to `/v1` is intentionally deferred because it may break existing clients.
