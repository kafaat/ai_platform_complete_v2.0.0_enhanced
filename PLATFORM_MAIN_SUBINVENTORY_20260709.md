# sahool-platform/api/main.py Sub-Inventory

## Summary

- File: `services/sahool-platform/api/main.py`
- Total lines: `2577`
- Import lines: `136`
- Top-level symbols: `45`
- Direct route decorators: `0`
- Status: `route_free_with_embedded_business_logic`

## Category totals

| Category | Classification | Symbols | LOC |
|---|---|---:|---:|
| `idempotency_outbox_events` | `embedded_business_logic` | 9 | 443 |
| `field_task_alert_helpers` | `embedded_business_logic` | 3 | 269 |
| `auth_jwt_permissions` | `security_runtime` | 8 | 165 |
| `parsers_mappers_serializers` | `compatibility_runtime` | 8 | 155 |
| `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 8 | 117 |
| `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 6 | 90 |
| `middleware_and_rate_limit` | `middleware_runtime` | 1 | 41 |
| `workflow_compatibility` | `compatibility_runtime` | 2 | 34 |

## Business-logic note

- Embedded business logic still present in platform main: `712` LOC.
- This does not reopen P1 because direct routes remain zero, but it makes P3 a real runtime extraction, not a cosmetic cleanup.
- Uncategorized/residual line estimate after imports and categorized symbols: `1127` LOC. This must be reviewed before any P3 extraction plan is finalized.

## Largest top-level symbols

| Symbol | Category | Classification | LOC | Lines |
|---|---|---|---:|---|
| `_start_scheduler` | `idempotency_outbox_events` | `embedded_business_logic` | 232 | 304-535 |
| `_evaluate_field_alerts_persist` | `field_task_alert_helpers` | `embedded_business_logic` | 183 | 1699-1881 |
| `_start_outbox_worker` | `idempotency_outbox_events` | `embedded_business_logic` | 62 | 546-607 |
| `_log_alert_deliveries` | `field_task_alert_helpers` | `embedded_business_logic` | 60 | 1627-1686 |
| `_emit_domain_event` | `idempotency_outbox_events` | `embedded_business_logic` | 45 | 710-754 |
| `rate_limit_middleware` | `middleware_and_rate_limit` | `middleware_runtime` | 41 | 926-966 |
| `get_current_user` | `auth_jwt_permissions` | `security_runtime` | 37 | 1203-1239 |
| `_init_db_pool` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 36 | 231-266 |
| `_idempotent` | `idempotency_outbox_events` | `embedded_business_logic` | 36 | 783-818 |
| `_assert_db_role_rls_safe` | `auth_jwt_permissions` | `security_runtime` | 33 | 269-301 |
| `require_permission` | `auth_jwt_permissions` | `security_runtime` | 31 | 1242-1272 |
| `_reverse_geocode` | `parsers_mappers_serializers` | `compatibility_runtime` | 29 | 1320-1348 |
| `_build_denylist` | `auth_jwt_permissions` | `security_runtime` | 27 | 1171-1197 |
| `_build_walk_plan` | `field_task_alert_helpers` | `embedded_business_logic` | 26 | 2132-2157 |
| `tenant_connection` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 24 | 653-676 |
| `_row_to_activity` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1462-1485 |
| `_row_to_soil_test` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1535-1558 |
| `_build_versioned_update` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 1089-1111 |
| `_get_workflow_store` | `workflow_compatibility` | `compatibility_runtime` | 23 | 2509-2531 |
| `_build_rate_redis` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 21 | 879-899 |

## Recommendations

- Extract remaining bootstrap/runtime helpers into api/platform_bootstrap_runtime.py and api/platform_auth_runtime.py.
- Category auth_jwt_permissions exceeds 120 LOC; extract a dedicated runtime module.
- Category idempotency_outbox_events exceeds 140 LOC; extract a dedicated runtime module.
- Category field_task_alert_helpers exceeds 220 LOC; extract a dedicated runtime module.

## Decision

The platform main file is route-free after P1, but it still embeds event/outbox and field-alert business runtime. Treat further extraction as P3 business-runtime extraction, not as bootstrap cleanup, and do not begin it until the production certification blockers are closed.
