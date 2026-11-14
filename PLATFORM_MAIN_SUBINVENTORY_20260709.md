# sahool-platform/api/main.py Sub-Inventory

## Summary

- File: `services/sahool-platform/api/main.py`
- Total lines: `2499`
- Import lines: `146`
- Top-level symbols: `43`
- Direct route decorators: `0`
- Status: `route_free_with_embedded_business_logic`

## Category totals

| Category | Classification | Symbols | LOC |
|---|---|---:|---:|
| `idempotency_outbox_events` | `embedded_business_logic` | 7 | 367 |
| `field_task_alert_helpers` | `embedded_business_logic` | 3 | 269 |
| `parsers_mappers_serializers` | `compatibility_runtime` | 8 | 161 |
| `auth_jwt_permissions` | `security_runtime` | 8 | 154 |
| `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 8 | 117 |
| `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 6 | 92 |
| `middleware_and_rate_limit` | `middleware_runtime` | 1 | 41 |
| `workflow_compatibility` | `compatibility_runtime` | 2 | 34 |

## Business-logic note

- Embedded business logic still present in platform main: `636` LOC.
- This does not reopen P1 because direct routes remain zero, but it makes P3 a real runtime extraction, not a cosmetic cleanup.
- Uncategorized/residual line estimate after imports and categorized symbols: `1118` LOC. This must be reviewed before any P3 extraction plan is finalized.

## Largest top-level symbols

| Symbol | Category | Classification | LOC | Lines |
|---|---|---|---:|---|
| `_start_scheduler` | `idempotency_outbox_events` | `embedded_business_logic` | 229 | 286-514 |
| `_evaluate_field_alerts_persist` | `field_task_alert_helpers` | `embedded_business_logic` | 183 | 1621-1803 |
| `_log_alert_deliveries` | `field_task_alert_helpers` | `embedded_business_logic` | 60 | 1549-1608 |
| `get_current_user` | `auth_jwt_permissions` | `security_runtime` | 51 | 1105-1155 |
| `_emit_domain_event` | `idempotency_outbox_events` | `embedded_business_logic` | 45 | 670-714 |
| `_start_outbox_worker` | `idempotency_outbox_events` | `embedded_business_logic` | 42 | 526-567 |
| `rate_limit_middleware` | `middleware_and_rate_limit` | `middleware_runtime` | 41 | 826-866 |
| `_init_db_pool` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 39 | 235-273 |
| `require_permission` | `auth_jwt_permissions` | `security_runtime` | 31 | 1158-1188 |
| `_reverse_geocode` | `parsers_mappers_serializers` | `compatibility_runtime` | 29 | 1236-1264 |
| `_build_denylist` | `auth_jwt_permissions` | `security_runtime` | 27 | 1073-1099 |
| `_row_to_task` | `parsers_mappers_serializers` | `compatibility_runtime` | 26 | 1416-1441 |
| `_build_walk_plan` | `field_task_alert_helpers` | `embedded_business_logic` | 26 | 2054-2079 |
| `tenant_connection` | `db_tenant_rls_bootstrap` | `bootstrap_runtime` | 24 | 613-636 |
| `_row_to_activity` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1378-1401 |
| `_row_to_soil_test` | `parsers_mappers_serializers` | `compatibility_runtime` | 24 | 1457-1480 |
| `_build_versioned_update` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 23 | 989-1011 |
| `_get_workflow_store` | `workflow_compatibility` | `compatibility_runtime` | 23 | 2431-2453 |
| `_build_rate_redis` | `misc_bootstrap_compatibility` | `bootstrap_compatibility` | 21 | 779-799 |
| `_issue_tags_from_event` | `idempotency_outbox_events` | `embedded_business_logic` | 21 | 2003-2023 |

## Recommendations

- Extract remaining bootstrap/runtime helpers into api/platform_bootstrap_runtime.py and api/platform_auth_runtime.py.
- Category auth_jwt_permissions exceeds 120 LOC; extract a dedicated runtime module.
- Category idempotency_outbox_events exceeds 140 LOC; extract a dedicated runtime module.
- Category field_task_alert_helpers exceeds 220 LOC; extract a dedicated runtime module.

## Decision

The platform main file is route-free after P1, but it still embeds event/outbox and field-alert business runtime. Treat further extraction as P3 business-runtime extraction, not as bootstrap cleanup, and do not begin it until the production certification blockers are closed.
