# WX-10.10 — Execution Plan → Dispatch Authorization Boundary

## Scope

This increment adds a decision-service-owned, append-only authorization boundary for one planned
execution plan. It records authorization evidence only. It does not dispatch, create a task,
issue an equipment command, invoke an actuator, or write outcome/learning records.

## Added

- `services/decision-service/migrations/004_dispatch_authorization.sql`
- `POST /v1/execution-plans/{execution_plan_id}/authorize-dispatch`
- `POST /api/v1/execution-plans/{execution_plan_id}/authorize-dispatch`
- Dedicated `Permission.DECISION_DISPATCH_AUTHORIZE` (Owner + Manager only)
- Transactional `DISPATCH_AUTHORIZATION_CREATED` outbox event
- Append-only dispatch authorization audit record
- Real-Postgres concurrency/idempotency/tenant/append-only test suite
- `scripts/ci/dispatch_authorization_boundary_gate.py`
- CI wiring for migration 004 and WX-10.10 real-Postgres tests

## Contract

Success requires authoritative and persisted proof with matching execution-plan, decision,
review, candidate-lineage, policy, weather snapshot, and resource snapshot identifiers.
Mirror mode fails closed with HTTP 503. The same idempotency key and payload replays the original
authorization; a changed payload conflicts. A unique tenant+plan constraint guarantees exactly
one authorization under a race.

## Local verification

- Python compile: PASS
- Boundary guard: PASS
- WX-10.9 + WX-10.10 + endpoint-coverage focused tests: 23 passed
- Endpoint UI coverage gate: PASS (457 core endpoints)
- Real PostgreSQL suite: 7 tests present, skipped locally because `DATABASE_URL` is unavailable

CI remains the authority for migration 004 apply/check and the real-Postgres race proof.
