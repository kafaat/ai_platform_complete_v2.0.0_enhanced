# M3 Hourly Energy-Aware Lexicographic MPC

## Scope
Implemented a deterministic recommendation-only hourly irrigation scheduler that consumes canonical water state, unified irrigation capability, commissioning executability, governed hourly weather/crop demand, and hourly energy envelopes.

## Added
- `services/sahool-platform/api/hourly_energy_aware_irrigation_mpc.py`
- `migrations/v178_hourly_energy_aware_irrigation_mpc.sql`
- `tests_v9/test_hourly_energy_aware_irrigation_mpc.py`
- `scripts/ci/irrigation_hourly_mpc_m3_guard.py`

## Safety and governance
- Fail-closed on missing canonical source digests.
- Fail-closed when water state is not operationally eligible.
- Fail-closed when capability graph is blocked.
- Fail-closed without an executable commissioning gate.
- Separate continuous power and starting-kVA checks.
- Enforces permitted load identities.
- Enforces maximum daily and per-event depth.
- Enforces minimum runtime and minimum off interval.
- Produces recommendation-only schedules with `execution_allowed=false`.
- No MQTT, Modbus, controller, or actuator dispatch.

## Lexicographic objectives
1. Minimize critical crop-stress hours.
2. Respect all hard water, hydraulic, runoff, energy, controller, and commissioning constraints.
3. Surface governed yield-floor status without inventing a model.
4. Minimize water and energy use/cost.
5. Minimize starts.
6. Maximize renewable-energy share.

## Persistence contract
Migration v178 adds tenant-bound schedule/action tables with RLS, FORCE RLS, WITH CHECK policies, digest uniqueness, and database checks preventing executable or dispatchable records.

## Verification
- M3 focused tests: 8 passed.
- Water/engineering/controller/MPC regression set: 114 passed.
- Deprecation warnings treated as errors: 0 warnings.
- M2.1-M2.11 guards: passed.
- M3 guard: passed.
- FastAPI lifespan guard: passed.
- Python compilation: passed.

## Not certified in this environment
- PostgreSQL migration execution and live RLS isolation.
- Live Weather Engine hourly ingestion.
- Live energy/BMS/controller telemetry.
- Durable candidate persistence and decision-service submission.
- Staging E2E from recommendation through authorization, execution, receipt, as-applied truth, and water-ledger reconciliation.
