# sahool-platform/api/main.py Sub-Inventory

## Summary

- File: `services/sahool-platform/api/main.py`
- Total lines: `2518`
- Import lines: `144`
- Top-level symbols: `45`
- Direct route decorators: `0`
- Status: `route_free_with_embedded_business_logic`

## Category totals

| Category | Classification | Symbols | LOC |
|---|---|---:|---:|
| `idempotency_outbox_events` | `embedded_business_logic` | 7 | 367 |
| `field_task_alert_helpers` | `embedded_business_logic` | 3 | 269 |
| `parsers_mappers_serializers` | `compatibility_runtime` | 8 | 161 |
| `auth_jwt_permissions` | `security_runtime` | 8 | 153 |
| `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 9 | 130 |
| `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 6 | 92 |
| `middleware_and_rate_limit` | `middleware_runtime` | 1 | 41 |
| `workflow_compatibility` | `compatibility_runtime` | 2 | 34 |
| `shutdown_hooks` | `bootstrap_runtime` | 1 | 5 |

## Business-logic note

- Embedded business logic still present in platform main: `636` LOC.
- This does not reopen P1 because direct routes remain zero, but it makes P3 a real runtime extraction, not a cosmetic cleanup.
- Uncategorized/residual line estimate after imports and categorized symbols: `1122` LOC. This must be reviewed before any P3 extraction plan is finalized.

## Largest top-level symbols

| Symbol | Category | Classification | LOC | Lines |
|---|---|---|---:|---|
| `_start_scheduler` | `idempotency_outbox_events` | `embedded_business_logic` | 229 | 287-515 |
| `_evaluate_field_alerts_persist` | `field_task_alert_helpers` | `embedded_business_logic` | 183 | 1640-1822 |
| `_log_alert_deliveries` | `field_task_alert_helpers` | `embedded_business_logic` | 60 | 1568-1627 |
| `get_current_user` | `auth_jwt_permissions` | `security_runtime` | 50 | 1125-1174 |
| `_emit_domain_event` | `idempotency_outbox_events` | `embedded_business_logic` | 45 | 691-735 |
| `_start_outbox_worker` | `idempotency_outbox_events` | `embedded_business_logic` | 42 | 527-568 |
| `rate_limit_middleware` | `middleware_and_rate_limit` | `middleware_runtime` | 41 | 847-887 |
| `_init_db_pool` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 39 | 236-274 |
| `require_permission` | `auth_jwt_permissions` | `security_runtime` | 31 | 1177-1207 |
| `_reverse_geocode` | `parsers_mappers_serializers` | `compatibility_runtime` | 29 | 1255-1283 |
| `_build_denylist` | `auth_jwt_permissions` | `security_runtime` | 27 | 1093-1119 |
| `_row_to_task` | `parsers_mappers_serializers` | `compatibility_runtime` | 26 | 1435-1460 |
| `_build_walk_plan` | `field_task_alert_helpers` | `embedded_business_logic` | 26 | 2073-2098 |
| `tenant_connection` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 24 | 634-657 |
| `_row_to_activity` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1397-1420 |
| `_row_to_soil_test` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1476-1499 |
| `_build_versioned_update` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 1010-1032 |
| `_get_workflow_store` | `workflow_compatibility` | `compatibility_runtime` | 23 | 2450-2472 |
| `_build_rate_redis` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 21 | 800-820 |
| `_issue_tags_from_event` | `idempotency_outbox_events` | `embedded_business_logic` | 21 | 2022-2042 |

## Recommendations

- Extract remaining bootstrap/runtime helpers into api/platform_bootstrap_runtime.py and api/platform_auth_runtime.py.
- Category auth_jwt_permissions exceeds 120 LOC; extract a dedicated runtime module.
- Category idempotency_outbox_events exceeds 140 LOC; extract a dedicated runtime module.
- Category field_task_alert_helpers exceeds 220 LOC; extract a dedicated runtime module.

## Decision

The platform main file is route-free after P1, but it still embeds event/outbox and field-alert business runtime. Treat further extraction as P3 business-runtime extraction, not as bootstrap cleanup, and do not begin it until the production certification blockers are closed.
