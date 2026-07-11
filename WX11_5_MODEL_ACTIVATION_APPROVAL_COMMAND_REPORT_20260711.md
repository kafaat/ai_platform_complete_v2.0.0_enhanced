# WX-11.5 — Model Activation Approval + Registry Command Boundary

## Scope

This increment converts one pending activation request into one immutable approval or rejection. Approval creates one queued registry activation command carrying both the candidate artifact and an explicit previous-artifact rollback pointer. It does **not** mutate a registry alias or deploy a model.

## Added

- `migrations/012_model_activation_approval_command.sql`
- `decision_model_activation_reviews` append-only audit table
- `decision_model_registry_activation_commands` append-only command table
- Decision-Service endpoint: `POST /v1/learning/activation-requests/{activation_request_id}/review`
- BFF endpoint with dedicated `decision:model-activation-approve` permission
- Owner-only approval permission in this increment
- Outbox events:
  - `MODEL_ACTIVATION_REQUEST_REVIEWED`
  - `MODEL_REGISTRY_ACTIVATION_COMMAND_CREATED` (approval only)
- CI boundary gate and focused contract tests

## Invariants

- One review per activation request and tenant.
- Rejection requires a reason and creates no registry command.
- Approval requires registry alias, previous artifact URI, and SHA-256 digest.
- The queued command preserves candidate and rollback pointers.
- Idempotent replay is allowed only for the same request payload.
- No alias mutation, deployment, traffic shift, fitting, MQTT, or actuator call is present.

## Local verification

- Python compile: PASS
- WX-11.4 regression boundary: PASS
- WX-11.5 boundary: PASS
- Focused tests: 8 passed
- Waiver JSON: valid
- Endpoint/UI coverage gate: PASS

Real PostgreSQL migration, concurrency, tenant-isolation, append-only, and outbox-count proofs remain CI responsibilities.
