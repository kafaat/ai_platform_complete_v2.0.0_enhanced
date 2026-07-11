# WX-10.13 — Outcome → Learning Attribution

## Scope
Creates immutable, tenant-scoped attribution lineage from one verified canonical `outcome_record` to a model/feature set. This increment does not fit a model, update weights, calculate rewards, redispatch work, or issue equipment/task commands.

## Delivered
- Migration `008_learning_attribution.sql`
- Append-only `decision_learning_attributions`
- Decision-service endpoint `POST /v1/outcomes/{outcome_id}/learning-attribution`
- Platform BFF endpoint `POST /api/v1/outcomes/{outcome_id}/learning-attribution`
- Permission `decision:learning-attribute`
- Atomic outcome/evidence/label validation
- Deterministic idempotency and concurrency-safe single attribution per outcome/model/feature set
- Transactional outbox event `LEARNING_ATTRIBUTION_CREATED`
- Structural ratchet `learning_attribution_boundary_gate.py`

## Fail-closed rules
- SoR disabled: 503
- Unverified or missing outcome: reject
- Evidence snapshot mismatch: reject
- Success/failure label inconsistent with verified outcome: reject
- Same idempotency key with different payload: conflict
- Existing attribution with different payload: conflict

## Validation performed locally
- Python compile: PASS
- JSON validation: PASS
- WX-10.11a/10.11b/10.12 guards: PASS
- WX-10.13 guard: PASS
- Focused contract/regression tests: 4 passed, 9 PostgreSQL-dependent tests skipped
- Endpoint/UI coverage gate: PASS, 457/457

## CI proof still required
Apply/check migration 008 on real PostgreSQL and prove concurrent single-winner behavior, tenant isolation, append-only enforcement, idempotent replay/mismatch, and exactly one outbox event.
