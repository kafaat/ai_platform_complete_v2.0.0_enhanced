# sahool-platform/api/main.py Sub-Inventory

## Summary

- File: `services/sahool-platform/api/main.py`
- Total lines: `2520`
- Import lines: `149`
- Top-level symbols: `46`
- Direct route decorators: `0`
- Status: `route_free_with_embedded_business_logic`

## Category totals

| Category | Classification | Symbols | LOC |
|---|---|---:|---:|
| `idempotency_outbox_events` | `embedded_business_logic` | 7 | 340 |
| `field_task_alert_helpers` | `embedded_business_logic` | 3 | 267 |
| `auth_jwt_permissions` | `security_runtime` | 8 | 163 |
| `parsers_mappers_serializers` | `compatibility_runtime` | 8 | 161 |
| `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 10 | 142 |
| `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 6 | 94 |
| `middleware_and_rate_limit` | `middleware_runtime` | 1 | 41 |
| `workflow_compatibility` | `compatibility_runtime` | 2 | 34 |
| `shutdown_hooks` | `bootstrap_runtime` | 1 | 5 |

## Business-logic note

- Embedded business logic still present in platform main: `607` LOC.
- This does not reopen P1 because direct routes remain zero, but it makes P3 a real runtime extraction, not a cosmetic cleanup.
- Uncategorized/residual line estimate after imports and categorized symbols: `1124` LOC. This must be reviewed before any P3 extraction plan is finalized.

## Largest top-level symbols

| Symbol | Category | Classification | LOC | Lines |
|---|---|---|---:|---|
| `_start_scheduler` | `idempotency_outbox_events` | `embedded_business_logic` | 196 | 292-487 |
| `_evaluate_field_alerts_persist` | `field_task_alert_helpers` | `embedded_business_logic` | 181 | 1644-1824 |
| `_log_alert_deliveries` | `field_task_alert_helpers` | `embedded_business_logic` | 60 | 1572-1631 |
| `_start_outbox_worker` | `idempotency_outbox_events` | `embedded_business_logic` | 47 | 500-546 |
| `get_current_user` | `auth_jwt_permissions` | `security_runtime` | 46 | 1109-1154 |
| `_emit_domain_event` | `idempotency_outbox_events` | `embedded_business_logic` | 45 | 672-716 |
| `require_permission` | `auth_jwt_permissions` | `security_runtime` | 45 | 1167-1211 |
| `rate_limit_middleware` | `middleware_and_rate_limit` | `middleware_runtime` | 41 | 829-869 |
| `_init_db_pool` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 39 | 241-279 |
| `_reverse_geocode` | `parsers_mappers_serializers` | `compatibility_runtime` | 29 | 1259-1287 |
| `_build_denylist` | `auth_jwt_permissions` | `security_runtime` | 27 | 1077-1103 |
| `tenant_connection` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 26 | 613-638 |
| `_row_to_task` | `parsers_mappers_serializers` | `compatibility_runtime` | 26 | 1439-1464 |
| `_build_walk_plan` | `field_task_alert_helpers` | `embedded_business_logic` | 26 | 2075-2100 |
| `_row_to_activity` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1401-1424 |
| `_row_to_soil_test` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1480-1503 |
| `_lifespan` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 179-201 |
| `_build_versioned_update` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 992-1014 |
| `_get_workflow_store` | `workflow_compatibility` | `compatibility_runtime` | 23 | 2452-2474 |
| `_build_rate_redis` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 21 | 782-802 |

## Recommendations

- Extract remaining bootstrap/runtime helpers into api/platform_bootstrap_runtime.py and api/platform_auth_runtime.py.
- Category auth_jwt_permissions exceeds 120 LOC; extract a dedicated runtime module.
- Category idempotency_outbox_events exceeds 140 LOC; extract a dedicated runtime module.
- Category field_task_alert_helpers exceeds 220 LOC; extract a dedicated runtime module.

## Decision

The platform main file is route-free after P1, but it still embeds event/outbox and field-alert business runtime. Treat further extraction as P3 business-runtime extraction, not as bootstrap cleanup, and do not begin it until the production certification blockers are closed.
