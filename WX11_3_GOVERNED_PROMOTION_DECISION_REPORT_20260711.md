# WX-11.3 — Governed Candidate Promotion Decision

Implemented an immutable, tenant-scoped policy decision over one evaluated candidate artifact.

## Boundary

- `POST /v1/learning/promotion-decisions`
- `POST /api/v1/learning/promotion-decisions`
- migration `010_model_promotion_decision.sql`
- states: `promotion_eligible | promotion_rejected`
- deterministic primary-metric threshold and guardrail regression evaluation
- idempotent, append-only, outbox-backed

## Explicit exclusions

No model fitting, registry promotion, active alias mutation, deployment, redispatch, MQTT, or actuator call.

## Next

WX-11.4 may convert an eligible decision into a separately approved registry activation request. It must not directly mutate the active model from this boundary.
