# Decision-service SoR Shadow Promotion Contract

This phase adds a hard boundary between **readiness** and **promotion**.

## Modes

`SAHOOL_DECISION_WRITE_MODE` is interpreted by `sahool-platform`:

- `platform_sor` — default. Platform writes DB and mirrors best-effort to decision-service.
- `shadow` — platform still writes DB and mirrors; used for staging comparisons.
- `decision_service_sor` — allowed only after every production promotion gate is true.

## Promotion gates

The platform must not stop writing decision/outcome/learning tables until all are true:

- `DECISION_SERVICE_SOR_ENABLED=true`
- `DECISION_SERVICE_MIGRATIONS_VERIFIED=true`
- `DECISION_SERVICE_BACKFILL_VERIFIED=true`
- `DECISION_SERVICE_TENANT_ISOLATION_VERIFIED=true`
- `DECISION_SERVICE_OUTBOX_VERIFIED=true`
- `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true`

Decision-service additionally exposes `/v1/cutover/readiness` so operators can inspect
`can_enable_sor`, `can_demote_platform`, and missing gates at runtime.

## Non-goal

This phase does **not** demote `sahool-platform`. It creates the control surface that
prevents accidental demotion before real Postgres staging/prod evidence exists.
