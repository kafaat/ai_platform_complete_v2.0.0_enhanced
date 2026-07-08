# P4.5 Legacy Decision Write Routers Facade Conversion

## Goal
Continue P4 by converting the highest-risk legacy decision/outcome/learning write routes inside `sahool-platform` into BFF/facade calls to `decision-service`.

## Converted write paths

- `services/sahool-platform/api/routers/decision_record.py`
  - `POST /api/v1/decision/record`
  - `POST /api/v1/outcome/record`
- `services/sahool-platform/api/routers/decision_dispatch.py`
  - `POST /api/v1/decision/dispatch/execute`
- `services/sahool-platform/api/routers/recommendations.py`
  - `POST /api/v1/recommendations/outcomes`

## Boundary rule
`decision-service` owns persistence semantics for:

- `decision_record`
- `dispatch_decisions`
- `outcome_record`
- `recommendation_outcomes`
- `online_learning_updates`

`sahool-platform` keeps auth, request validation, compatibility response shaping, and pure calculations that are not DB ownership.

## Guard added
`services/sahool-platform/tests/test_p4_5_legacy_decision_write_routers_facade_guard.py`

The guard fails if the converted endpoints reintroduce direct loop-table writes, `tenant_connection`, `_emit_domain_event`, or local idempotent DB command-store ownership on these write paths.

## Honest limitation
P4.5 does not remove all historical read paths from `sahool-platform`; read-side consolidation remains for later phases because many dashboards still read existing tables for compatibility.
