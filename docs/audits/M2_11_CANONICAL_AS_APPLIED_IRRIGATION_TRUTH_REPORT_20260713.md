# M2.11 Canonical As-Applied Irrigation Truth

## Scope
Implemented the governed, non-dispatching as-applied irrigation truth that binds one authorized execution plan to controller receipts and measured flow, pressure, runtime, and position evidence.

## Added
- `services/sahool-platform/api/canonical_as_applied_irrigation.py`
- `migrations/v177_canonical_as_applied_irrigation_truth.sql`
- `tests_v9/test_canonical_as_applied_irrigation.py`
- `scripts/ci/irrigation_as_applied_m2_11_guard.py`

## Main contracts
- `AuthorizedIrrigationPlan`
- `IrrigationExecutionReceipt`
- `AsAppliedObservation`
- `CanonicalAsAppliedIrrigationTruth`

## Integrity rules
- Tenant, field, machine, controller, and execution-plan identity binding.
- Immutable SHA-256 lineage to decision, authorization, capability graph, commissioning certificate, plan, receipts, and observations.
- Receipt and observation replay/out-of-order detection.
- Terminal completed receipt required.
- Flow, pressure, runtime, and position evidence required.
- Telemetry freshness enforced.
- Position coverage acceptance threshold enforced.
- Planned-versus-applied volume tolerance enforced.
- Water-ledger event emitted only from verified measured truth.
- No actuator, MQTT publish, or Modbus write path.

## Calculation
- `actual_volume_m3 = mean_flow_lps × runtime_minutes × 0.06`
- `actual_area_ha = planned_area_ha × position_coverage_percent / 100`
- `actual_depth_mm = actual_volume_m3 / (actual_area_ha × 10)`

## Database
The v177 migration adds append-oriented run, receipt, observation, and canonical-truth tables with tenant-bound foreign keys, unique replay constraints, RLS, FORCE RLS, and WITH CHECK policies.

## Verification
- M2.11 focused tests: `7 passed`.
- Water/MPC/engineering regression selection: `86 passed`.
- Deprecation warnings promoted to errors: no failures.
- FastAPI lifespan guard: PASS.
- Irrigation M2.1-M2.11 static guards: PASS.
- Python compilation: PASS.

## Certification boundary
Not certified in this environment:
- PostgreSQL v177 migration execution.
- Live cross-tenant RLS test.
- Live controller, flow meter, pressure sensor, or position telemetry.
- Durable persistence and transaction/idempotency checks.
- Actual water-ledger write and depletion reconciliation.
- End-to-end decision-to-outcome staging run.
