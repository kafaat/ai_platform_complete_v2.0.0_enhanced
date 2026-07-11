# WX-11.6 — Registry Adapter Claim, Activation Receipt, and Rollback Command

Implemented on top of WX-11.5.

## Boundary

- Migration `013_registry_adapter_receipt_rollback.sql`
- One atomic adapter claim per activation command
- Terminal activation receipt (`activated` or `failed`)
- Successful receipt must prove the exact candidate SHA-256 digest
- Separate queued rollback command derived from the immutable previous-artifact pointer
- Append-only claim, receipt, and rollback evidence
- Transactional outbox events for claim, receipt, and rollback-command creation
- Tenant isolation and idempotency controls

## Routes

- `POST /v1/learning/activation-commands/{activation_command_id}/claim`
- `POST /v1/learning/activation-commands/{activation_command_id}/receipt`
- `POST /v1/learning/activation-receipts/{activation_receipt_id}/rollback-command`
- Equivalent `/api/v1/...` BFF routes with `decision:model-registry-execute`

## Safety

This increment does not directly call a model registry, mutate an alias, deploy a model, shift traffic, fit a model, publish MQTT, or invoke an actuator. The external registry adapter performs the actual change and returns proof through the receipt boundary.

## Local evidence

- Python compile: PASS
- WX-11.6 structural boundary guard: PASS
- WX-11.5 + WX-11.6 focused tests: PASS (8 tests)
- Real PostgreSQL migration/concurrency suite: not run locally; CI/operator environment still required.
