# Sahool Governance Hardening — Health/Readiness Schema Continuation

Date: 2026-07-09
Base package: `sahool_ai_platform_6bf6465_contract_capabilities_fixed.zip`
Output package: `sahool_ai_platform_6bf6465_health_readiness_schema_fixed.zip`

## Objective

Close the remaining non-breaking governance gap around liveness/readiness response envelopes.

Previous hardening standardized route mounts, `/internal/*`, GraphQL budgets, health aliases, API versioning freeze, `/contract`, and `/capabilities`. This continuation adds a static guard for `/healthz` and `/readyz` so operational probes receive a predictable machine-readable contract.

## Changes

### 1. Added static health/readiness schema guard

New files:

- `scripts/ci/health_readiness_schema_guard.py`
- `tests_v9/test_health_readiness_schema_guard.py`
- `.github/workflows/health-readiness-schema.yml`
- `health_readiness_inventory.generated.json`
- `health_readiness_inventory.csv`

The guard scans `services/**/main.py` and `bots/**/main.py` without importing runtime dependencies.

Required minimum envelope:

- `/healthz` must expose `status` and `service` either directly or through the canonical platform handler.
- `/readyz` must expose `status`, `service`, and readiness meaning via `ready`, `implemented_runtime`, or the canonical platform handler.

### 2. Normalized readiness envelopes in high-signal services

Updated:

- `services/agriai-engine/main.py`
- `services/field-segmentation/main.py`
- `services/local-ai-rag/main.py`
- `services/sam2-inference/main.py`
- `services/decision-service/main.py`
- `services/ai_agronomist/main.py`
- `services/edge-inference/main.py`

Examples of fixed drift:

- `agriai-engine /readyz` now returns `service` and `implemented_runtime`.
- `field-segmentation /readyz` now returns `service` and `implemented_runtime`.
- `local-ai-rag /healthz` and `/readyz` now include `service`.
- `sam2-inference /readyz` now includes `service` and `implemented_runtime`.
- `decision-service /readyz` now has both `status` and `service`, while preserving `ready`.
- `edge-inference /healthz` response model now includes `status` and `service`.
- `ai-agronomist /readyz` now includes `service` in success and dependency-failure details.

### 3. Regenerated inventories

Regenerated:

- `SERVICE_REGISTRY.md`
- `service_inventory.generated.json`
- `route_inventory.generated.json`
- `service_inventory.csv`
- `route_inventory.csv`
- `route_mount_inventory.generated.json`
- `route_mount_inventory.csv`
- `api_versioning_inventory.generated.json`
- `api_versioning_inventory.csv`
- `api_versioning_legacy_allowlist.generated.json`
- `contract_capabilities_inventory.generated.json`
- `contract_capabilities_inventory.csv`
- `health_readiness_inventory.generated.json`
- `health_readiness_inventory.csv`

## Verification

### Tests

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
  tests_v9/test_health_readiness_schema_guard.py \
  tests_v9/test_unit_test_environment_dependencies.py \
  tests_v9/test_dockerfile_pip_mirror_guard.py
```

Observed result:

```text
41 passed, 1 skipped in 24.56s
```

The single skipped test is the optional Redis live integration test requiring `WEATHER_REDIS_INTEGRATION_URL`.

### Guards

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
python scripts/ci/contract_capabilities_schema_guard.py --check
python scripts/ci/health_readiness_schema_guard.py --check
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
python scripts/ci/production_honesty_guard.py
python scripts/ci/test_requirements_inventory_guard.py --check
```

Notable outputs:

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
health_readiness_schema_guard_ok
✓ edge model contract guard passed
✓ edge production readiness guard passed
✓ production honesty guard passed
test_dependency_inventory_check_ok
```

## Result

The package is now a stronger governed runtime-real release candidate with:

- route/main.py controls
- internal route guard
- GraphQL guard
- health alias cleanup
- API versioning freeze policy
- `/contract` schema guard
- `/capabilities` schema guard
- `/healthz` and `/readyz` schema guard

## Remaining honest gaps

Still requires external/connected validation:

1. Full branch CI.
2. Transitive dependency lock generation in connected CI.
3. Redis live integration with a real Redis URL.
4. ONNX model provisioning for strict Edge production readiness.
5. Full `/v1` migration only if client-breaking change is accepted.
