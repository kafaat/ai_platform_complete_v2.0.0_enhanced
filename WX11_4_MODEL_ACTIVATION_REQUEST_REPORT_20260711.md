# WX-11.4 — Governed Model Activation Request Boundary

## Delivered

- Migration `011_model_activation_request.sql`.
- Append-only `decision_model_activation_requests` table.
- Decision-Service `POST /v1/learning/activation-requests`.
- Platform BFF `POST /api/v1/learning/activation-requests`.
- Dedicated `decision:model-activation-request` permission for OWNER and MANAGER.
- Eligibility gate: only `promotion_eligible` decisions can create a request.
- State is fixed to `pending_activation_approval`.
- Target environment is restricted to `staging|production`.
- Tenant isolation, idempotency, one request per promotion/environment, and transactional outbox event `MODEL_ACTIVATION_REQUEST_CREATED`.

## Deliberately excluded

No model registry alias change, active-model mutation, deployment, model fitting, automated rollout, dispatch, MQTT, or actuator operation is performed.

## Verification

Local structural and focused tests validate the boundary. Real PostgreSQL migration, concurrency, uniqueness, append-only, tenant isolation, and outbox assertions remain CI evidence.
