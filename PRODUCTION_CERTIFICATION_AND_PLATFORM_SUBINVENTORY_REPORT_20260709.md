# Production Certification Checklist + Platform main.py Sub-Inventory

Date: 2026-07-09

## Scope

This continuation implements the two requested post-P2 controls:

1. A production certification checklist for the four remaining blockers.
2. A sub-inventory for `services/sahool-platform/api/main.py` to determine whether its remaining large LOC surface is acceptable bootstrap or hidden post-P2 debt.

## Added artifacts

- `docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md`
- `production_certification_checklist.generated.json`
- `production_certification_checklist.csv`
- `scripts/ci/production_certification_checklist_guard.py`
- `tests_v9/test_production_certification_checklist_guard.py`
- `.github/workflows/production-certification-checklist.yml`
- `platform_main_subinventory.generated.json`
- `platform_main_subinventory.csv`
- `PLATFORM_MAIN_SUBINVENTORY_20260709.md`
- `scripts/ci/platform_main_subinventory_guard.py`
- `tests_v9/test_platform_main_subinventory_guard.py`
- `.github/workflows/platform-main-subinventory.yml`

## Production certification checklist

Current certification state is intentionally frozen as:

```text
release_candidate_not_production_certified
```

The four blockers are:

| ID | Blocker | Severity | Status |
|---|---|---|---|
| P-CERT-1 | Full branch CI | critical | pending_external_ci |
| P-CERT-2 | Connected transitive lock generation | critical | pending_connected_index_or_internal_mirror |
| P-CERT-3 | Redis live integration | medium-critical | pending_live_redis_endpoint |
| P-CERT-4 | ONNX/SAM2 model provisioning | critical | pending_operator_model_artifacts |

The guard prevents silent drift of this checklist and prevents the repository from implying production certification without fresh branch/deployment evidence.

## Platform main.py sub-inventory

`services/sahool-platform/api/main.py` remains route-free but large.

Summary:

| Metric | Value |
|---|---:|
| Total lines | 2511 |
| Import lines | 122 |
| Top-level symbols | 45 |
| Direct route decorators | 0 |
| Status | bootstrap_large_but_route_free |

Largest remaining categories:

| Category | Symbols | LOC |
|---|---:|---:|
| idempotency_outbox_events | 9 | 390 |
| field_task_alert_helpers | 3 | 268 |
| auth_jwt_permissions | 8 | 165 |
| parsers_mappers_serializers | 8 | 161 |
| db_tenant_rls_bootstrap | 7 | 103 |

Decision:

```text
P1 is complete because direct routes are removed, but platform main.py remains a large bootstrap/compatibility surface.
Further extraction is P3, not a blocker before the four production certification blockers.
```

Recommended P3 extraction candidates after certification blockers:

1. `api/platform_events_runtime.py` for scheduler/outbox/idempotency/domain events.
2. `api/platform_field_alert_runtime.py` for alert evaluation/delivery and walk-plan helpers.
3. `api/platform_auth_runtime.py` for JWT/permission/denylist helpers.
4. `api/platform_parsers.py` for row mappers/date/geocode helpers.

## Verification performed

Tests:

```text
35 passed, 1 skipped in 5.73s
```

Included:

- weather-service tests
- edge-inference tests
- zero-test service static smoke tests
- indicators-service tests
- production certification checklist guard test
- platform main sub-inventory guard test

Direct guard verification:

```text
production_certification_checklist_ok
platform_main_subinventory_check_ok
p1_main_decomposition_guard_ok
p2_main_decomposition_guard_ok
route_mount_inventory_check_ok
api_versioning_policy_check_ok
health_readiness_schema_guard_ok
contract_capabilities_schema_check_ok
test_dependency_inventory_check_ok
PyPI-default + Alibaba override pip mirror contract guard passed
dependency_inventory_check_ok
dependency_conflict_inventory_check_ok
direct_dependency_bundle_check_ok
internal_graphql_security_guard_ok
health_alias_contract_guard_ok
edge model contract guard passed
edge production readiness guard passed
production honesty guard passed
```

## Remaining blockers

No new code-refactor blocker was opened by this audit. Remaining blockers are operational/certification blockers only:

1. Full branch CI.
2. Connected transitive lock generation.
3. Redis live integration.
4. ONNX/SAM2 model provisioning.
