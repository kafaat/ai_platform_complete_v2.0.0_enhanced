# sahool-platform/api/main.py Sub-Inventory

## Summary

- File: `services/sahool-platform/api/main.py`
- Total lines: `2553`
- Import lines: `149`
- Top-level symbols: `46`
- Direct route decorators: `0`
- Status: `route_free_with_embedded_business_logic`

## Category totals

| Category | Classification | Symbols | LOC |
|---|---|---:|---:|
| `idempotency_outbox_events` | `embedded_business_logic` | 7 | 373 |
| `field_task_alert_helpers` | `embedded_business_logic` | 3 | 267 |
| `auth_jwt_permissions` | `security_runtime` | 8 | 163 |
| `parsers_mappers_serializers` | `compatibility_runtime` | 8 | 161 |
| `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 10 | 142 |
| `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 6 | 94 |
| `middleware_and_rate_limit` | `middleware_runtime` | 1 | 41 |
| `workflow_compatibility` | `compatibility_runtime` | 2 | 34 |
| `shutdown_hooks` | `bootstrap_runtime` | 1 | 5 |

## Business-logic note

- Embedded business logic still present in platform main: `640` LOC.
- This does not reopen P1 because direct routes remain zero, but it makes P3 a real runtime extraction, not a cosmetic cleanup.
- Uncategorized/residual line estimate after imports and categorized symbols: `1124` LOC. This must be reviewed before any P3 extraction plan is finalized.

## Largest top-level symbols

| Symbol | Category | Classification | LOC | Lines |
|---|---|---|---:|---|
| `_start_scheduler` | `idempotency_outbox_events` | `embedded_business_logic` | 229 | 292-520 |
| `_evaluate_field_alerts_persist` | `field_task_alert_helpers` | `embedded_business_logic` | 181 | 1677-1857 |
| `_log_alert_deliveries` | `field_task_alert_helpers` | `embedded_business_logic` | 60 | 1605-1664 |
| `_start_outbox_worker` | `idempotency_outbox_events` | `embedded_business_logic` | 47 | 533-579 |
| `get_current_user` | `auth_jwt_permissions` | `security_runtime` | 46 | 1142-1187 |
| `_emit_domain_event` | `idempotency_outbox_events` | `embedded_business_logic` | 45 | 705-749 |
| `require_permission` | `auth_jwt_permissions` | `security_runtime` | 45 | 1200-1244 |
| `rate_limit_middleware` | `middleware_and_rate_limit` | `middleware_runtime` | 41 | 862-902 |
| `_init_db_pool` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 39 | 241-279 |
| `_reverse_geocode` | `parsers_mappers_serializers` | `compatibility_runtime` | 29 | 1292-1320 |
| `_build_denylist` | `auth_jwt_permissions` | `security_runtime` | 27 | 1110-1136 |
| `tenant_connection` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 26 | 646-671 |
| `_row_to_task` | `parsers_mappers_serializers` | `compatibility_runtime` | 26 | 1472-1497 |
| `_build_walk_plan` | `field_task_alert_helpers` | `embedded_business_logic` | 26 | 2108-2133 |
| `_row_to_activity` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1434-1457 |
| `_row_to_soil_test` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1513-1536 |
| `_lifespan` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 179-201 |
| `_build_versioned_update` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 1025-1047 |
| `_get_workflow_store` | `workflow_compatibility` | `compatibility_runtime` | 23 | 2485-2507 |
| `_build_rate_redis` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 21 | 815-835 |

## Recommendations

- Extract remaining bootstrap/runtime helpers into api/platform_bootstrap_runtime.py and api/platform_auth_runtime.py.
- Category auth_jwt_permissions exceeds 120 LOC; extract a dedicated runtime module.
- Category idempotency_outbox_events exceeds 140 LOC; extract a dedicated runtime module.
- Category field_task_alert_helpers exceeds 220 LOC; extract a dedicated runtime module.

## Decision

The platform main file is route-free after P1, but it still embeds event/outbox and field-alert business runtime. Treat further extraction as P3 business-runtime extraction, not as bootstrap cleanup, and do not begin it until the production certification blockers are closed.
