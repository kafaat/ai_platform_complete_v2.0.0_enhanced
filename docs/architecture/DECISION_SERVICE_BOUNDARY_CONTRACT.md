# P4 Decision / Outcome / Learning Boundary Contract

## Owner
`decision-service` is the write-side owner for the closed-loop decision domain.

## Owned tables
- `decision_record`
- `dispatch_decisions`
- `outcome_record`
- `recommendation_outcomes`
- `online_learning_updates`
- `recommendation_feedback` remains deprecated and has no runtime writer.

## Platform role
`sahool-platform` is allowed to remain a BFF/read facade during migration. It must not introduce new loop-table write semantics outside `api/decision_service_client.py` and documented transitional legacy routers.

## P4 sub-phases
- P4.1 Decision Service Contract and runtime skeleton.
- P4.2 Outcome Service Contract and write endpoint.
- P4.3 Learning Summary / Learning Update Facade.
- P4.4 DB Ownership Guard for loop tables.

## Rules
1. Learning updates without source lineage must be rejected or marked `rejected_untraceable`.
2. Outcome reconciliation must continue to read both `outcome_record` and `recommendation_outcomes` until the historical data model is consolidated.
3. `sahool-platform` may shape responses, apply auth, and forward tenant context only.
4. The service boundary must keep `X-Tenant-Id` and `X-Agent-Token` forwarding centralized in `api/decision_service_client.py`.

## P4.5 Legacy Decision Write Routers Facade Conversion
The first high-risk legacy write routers in `sahool-platform` are converted to BFF/facade mode:

- `POST /api/v1/decision/record` delegates persistence to `decision-service`.
- `POST /api/v1/outcome/record` computes pure metrics for compatibility, then delegates persistence to `decision-service`.
- `POST /api/v1/decision/dispatch/execute` keeps guardrail evaluation in platform, then delegates dispatch persistence to `decision-service`.
- `POST /api/v1/recommendations/outcomes` validates request shape, then delegates recommendation-outcome persistence to `decision-service`.

These routers must not call `tenant_connection`, `_emit_domain_event`, or direct `INSERT INTO` loop tables on their write paths.
