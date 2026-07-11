# WX-10.9 — Approved Decision → Execution Plan Boundary

Implemented on top of the accepted WX-10.8 baseline.

## Scope
- Added migration `003_execution_plan.sql`.
- Added append-only `decision_execution_plans` table.
- Added authoritative `POST /v1/decisions/{decision_id}/execution-plan`.
- Added thin platform BFF proxy at `/api/v1/decisions/{decision_id}/execution-plan`.
- Requires an approved decision and matching approved review, review id, candidate lineage, tenant, and idempotency key.
- Creates exactly one `planned` execution-plan record and one `EXECUTION_PLAN_CREATED` outbox row in the same transaction.
- Mirror/SoR-off mode fails closed.
- No dispatch, task creation, equipment command, actuator call, or automatic execution.

## Verification performed locally
- Python compile: PASS.
- JSON waiver validation: PASS.
- Static/contract tests: 5 passed.
- Real-Postgres test suite added and wired into the Decision Service Tests CI job; not executed locally because no Postgres runtime was available in this environment.
- Ruff was not available in the execution environment; CI remains the final lint proof.

## CI proof required
- migration 003 apply + migration check
- approved/rejected/wrong-tenant paths
- lineage/review mismatch handling
- idempotent replay and payload mismatch
- concurrent create: exactly one plan and one conflict
- exactly one outbox row
- append-only UPDATE/DELETE rejection
