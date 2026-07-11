# WX-10.11b — Execution Adapter Delivery + Receipt

## Scope

This increment extends the authoritative execution request created by WX-10.11a with a concurrency-safe adapter claim and one immutable terminal receipt. It does not create outcomes or learning updates.

## Added

- Migration `006_execution_delivery_receipt.sql`.
- Append-preserving `decision_execution_delivery_attempts`.
- Atomic `queued -> delivering -> accepted|failed` state progression.
- `POST /v1/execution-requests/{execution_request_id}/claim`.
- `POST /v1/execution-requests/{execution_request_id}/receipt`.
- Delivery-token hashing; plaintext tokens are never persisted.
- Idempotent claim replay and terminal receipt replay.
- Outbox events `EXECUTION_REQUEST_CLAIMED` and `EXECUTION_RECEIPT_RECORDED`.
- Real-Postgres tests added to the Decision Service Tests CI job.
- Structural boundary guard wired into Repository Structural Lint.

## Explicit exclusions

- No MQTT/Modbus command implementation.
- No direct task-provider implementation.
- No outcome write.
- No learning update.
- No automatic retry inside the endpoint.

## Local verification

- Python compile: PASS.
- WX-10.11a guard: PASS.
- WX-10.11b guard: PASS.
- Focused contract tests: 6 passed.

Real PostgreSQL migration/concurrency/trigger verification remains CI-owned.
