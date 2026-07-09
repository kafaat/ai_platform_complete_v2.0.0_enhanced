# AUTH_MAIN_DECOMPOSITION_P0_REPORT_20260709

## Scope
Continuation from `sahool_ai_platform_6bf6465_health_readiness_schema_fixed.zip`.

Targeted the first P0 item from the main.py decomposition backlog:

- `services/auth/main.py`

## Changes

### 1. Extracted MFA runtime from auth main

Added:

- `services/auth/mfa_runtime.py`

Moved the security-sensitive MFA runtime helpers out of `services/auth/main.py`:

- `_ip_hash`
- `_emit_mfa_audit`
- `_store_recovery_codes`
- `_consume_recovery_code`
- `_register_mfa_failure`
- `_mfa_reset_and_maybe_migrate`
- `_consume_totp_step`
- `mfa_login_verify`
- `_verify_caller_mfa`

`services/auth/main.py` now re-exports those symbols to preserve the existing router/test contract. Existing routers still call `main._verify_caller_mfa`, `main.mfa_login_verify`, etc.

### 2. Reduced auth main.py size

Before:

- `services/auth/main.py`: 1275 lines

After:

- `services/auth/main.py`: 963 lines
- `services/auth/mfa_runtime.py`: 354 lines

This is a conservative decomposition: no route path or public API contract was intentionally changed.

### 3. Added auth decomposition guard

Added:

- `scripts/ci/auth_main_decomposition_guard.py`
- `tests_v9/test_auth_main_decomposition_guard.py`
- `.github/workflows/auth-main-decomposition.yml`

The guard enforces:

- `services/auth/main.py` stays below the decomposition ceiling.
- `services/auth/mfa_runtime.py` exists.
- key MFA helpers remain in `mfa_runtime.py`.
- `main.py` re-exports the MFA helpers for router compatibility.
- `_verify_caller_mfa` and `mfa_login_verify` do not drift back into `main.py`.

### 4. Hardened two auth tests against top-level `main` module collisions

Updated:

- `tests_v9/test_auth_mfa_enforcement.py`
- `tests_v9/test_auth_admin_stepup_mfa.py`

The tests now evict an already-loaded non-auth `main` module before importing `services/auth/main.py`. This prevents service-to-service top-level module-name collisions such as `weather-service/main.py` being inspected as auth `main.py`.

## Verification

### Tests

Executed targeted guarded suite:

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
  tests_v9/test_auth_main_decomposition_guard.py \
  tests_v9/test_unit_test_environment_dependencies.py \
  tests_v9/test_dockerfile_pip_mirror_guard.py
```

Result:

```text
42 passed, 1 skipped in 23.59s
```

The skipped test is the optional Redis live weather test requiring `WEATHER_REDIS_INTEGRATION_URL`.

### Guards

Executed successfully:

```bash
python scripts/ci/auth_main_decomposition_guard.py
python scripts/ci/generate_service_inventory.py --check
python scripts/ci/route_mount_contract_guard.py --check
python scripts/ci/api_versioning_policy_guard.py --check
python scripts/ci/health_readiness_schema_guard.py --check
python scripts/ci/contract_capabilities_schema_guard.py --check
python scripts/ci/test_requirements_inventory_guard.py --check
python scripts/ci/dependency_inventory_guard.py --check
python scripts/ci/service_dependency_conflict_guard.py --check
python scripts/ci/build_service_dependency_bundle.py --check
python scripts/ci/pip_mirror_contract_guard.py
python scripts/ci/internal_graphql_security_guard.py
python scripts/ci/health_alias_contract_guard.py
python scripts/ci/edge_model_contract_guard.py
python scripts/ci/edge_production_readiness_guard.py
python scripts/ci/production_honesty_guard.py
```

Notable output:

```text
✓ auth main decomposition guard passed
route_mount_inventory_check_ok
api_versioning_policy_check_ok
health_readiness_schema_guard_ok
contract_capabilities_schema_check_ok
test_dependency_inventory_check_ok
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
✓ PyPI-default + Alibaba override pip mirror contract guard passed
internal_graphql_security_guard_ok
health_alias_contract_guard_ok
✓ edge model contract guard passed
✓ edge production readiness guard passed
✓ production honesty guard passed
```

## Status

Completed:

- P0 auth/main.py decomposition started and guarded.
- MFA runtime extracted without changing route contracts.

Still remaining:

- P0 `ai_agronomist/main.py`
- P1 `sahool-platform/api/main.py` residual bootstrap
- P1 `odoo-bridge/main.py`
- P1 `vegetation-analysis-service/main.py`
- P2 `actuator-service/main.py`
- P2 `sam2-inference/main.py`
- P2 `weather-service/main.py` before ensemble expansion
- Full branch CI
- connected-CI transitive locks
- Redis live integration
- ONNX model provisioning
