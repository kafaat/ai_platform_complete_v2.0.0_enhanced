# IRR-F01 main execution report — 2026-07-23

Source archive: `sahool_main_3f2a010.zip`.

## Implemented

1. Preserved correlation/causation across the reservation-dispatch path without changing the global event-table schema:
   - `EventEnvelope.to_emit_args()` now exposes both trace fields.
   - reservation dispatch payloads carry stable `correlation_id` and `causation_id`.
   - `OutboxWorker` promotes those fields into the published envelope.
   - dispatch-failure compensation preserves the reservation correlation thread, with backward compatibility for older execution ports.

2. Completed capacity-evaluation evidence population:
   - authoritative capability digest is persisted.
   - `maximum_safe_flow_m3h` is populated from the authoritative resolved envelope.
   - `remaining_allocatable_flow_m3h` is calculated after locked overlap evaluation.

3. Added the missing runtime lifecycle worker:
   - cross-tenant due-reservation discovery using the dedicated jobs role.
   - tenant-scoped short transactions.
   - governed `transition_irrigation_reservation` path through `expire_due`.
   - concurrent-worker safety inherited from `FOR UPDATE SKIP LOCKED`.
   - opt-in Compose service under profile `irrigation-runtime`.

4. Added lifecycle-worker tests and retained the existing convergence and delivery-versus-fulfillment boundaries.

## Verification performed

- Focused irrigation suite: 90 tests passed.
- Irrigation convergence guard: LOCKED/PASS.
- Python compilation for modified irrigation/event modules: PASS.
- Docker Compose YAML parsing: PASS.

## Honest remaining live gates

The archive does not by itself certify production operation. These require infrastructure that was not available in this execution environment:

- PostgreSQL 16/PostGIS migration apply and two-session concurrency test.
- RLS under the restricted production roles.
- NATS/JetStream durable delivery and acknowledgement test.
- decision-service inbox plus authorized fulfillment into the existing execution-request aggregate.
- actuator claim/receipt and failure-compensation E2E.
- compose runtime health and worker heartbeat evidence.

No parallel irrigation asset, execution, evidence, topology-version, or closure-table SoR was introduced.
