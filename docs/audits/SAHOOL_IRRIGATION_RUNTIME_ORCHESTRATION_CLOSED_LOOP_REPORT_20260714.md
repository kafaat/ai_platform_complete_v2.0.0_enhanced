# SAHOOL Irrigation Runtime Orchestration & Closed-Loop Return Path

Date: 2026-07-14

## Scope

This increment closes the two source-level gaps that remained after M2–M5:

1. A server-owned runtime orchestration path from canonical water truth through persisted engineering capability and commissioning evidence into hourly MPC.
2. A durable, idempotent return path from measured execution evidence into canonical as-applied truth and the water ledger.

## Added runtime components

- `services/sahool-platform/api/irrigation_runtime_orchestrator.py`
- `services/sahool-platform/api/irrigation_closed_loop_runtime.py`
- `POST /api/v1/fields/{field_id}/irrigation/mpc/hourly-recommendation`
- `POST /api/v1/irrigation/executions/reconcile`

The hourly recommendation endpoint accepts only scheduling controls (`horizon_hours`, `persist`). It does not accept depletion, soil, weather, hydraulic, energy or controller facts from the client.

## Runtime recommendation chain

`tenant + field -> canonical water state -> latest canonical capability graph -> matching unexpired executability gate -> hourly energy/weather join -> hourly lexicographic MPC -> idempotent schedule persistence`

The result remains recommendation-only:

- `execution_allowed=false`
- no actuator call
- no MQTT publish
- no Modbus write

Daily canonical ETc is transparently disaggregated over hourly energy windows until a governed hourly ETc product is available. The limitation is explicitly surfaced in every output.

## Closed-loop return path

`authorized persisted run -> receipts -> measured flow/pressure/runtime/position -> canonical as-applied truth -> measured ledger event -> water_ledger reconciliation`

Safety properties:

- PostgreSQL transaction boundary is owned by the route.
- Advisory transaction lock serializes reconciliation per run.
- Unique reconciliation keys prevent replay/double counting.
- Only verified `water_ledger_eligible` truth is reconciled.
- Planned commands alone never update the ledger.
- Missing plan window, terminal receipt or measured observations fails closed.

## Database

Added migration:

- `v184_irrigation_closed_loop_runtime_reconciliation.sql`

It adds explicit planned execution-window fields to the run record and creates `irrigation_water_ledger_reconciliations` with:

- tenant-bound foreign key
- RLS and FORCE RLS
- USING and WITH CHECK policy
- unique run, as-applied digest and ledger-event digest constraints
- durable reconciliation payload

Manifest and migration runner were updated. Validation result:

`migration manifest validation passed: 190 migrations`

## CI ratchets

- `scripts/ci/irrigation_runtime_orchestrator_guard.py`
- `scripts/ci/irrigation_closed_loop_runtime_guard.py`

Both are wired into `.github/workflows/ci.yml`.

Endpoint coverage waivers were added explicitly:

- hourly recommendation surfaces through the existing Decision/Approvals console until the dedicated Irrigation Workspace is implemented.
- reconciliation is a machine/operations endpoint, not a direct farmer UI action.

Endpoint forward and reverse coverage gates pass.

## Verification

Focused regression suite:

- 87 passed
- 0 failed
- 0 DeprecationWarnings

New runtime tests:

- server-owned orchestration and persistence
- fail-closed missing capability
- verified measured reconciliation
- fail-closed missing run

All M2.1–M2.11, M3, M4, M5, FastAPI lifespan, runtime orchestration and closed-loop runtime guards pass.

## Boundaries not claimed

This source-level increment does not claim:

- migration execution on a live PostgreSQL instance
- live cross-tenant RLS certification
- live controller/BMS telemetry
- real actuator dispatch
- end-to-end staging authorization and receipt delivery
- governed hourly ETc from Weather Engine (daily ETc is currently disclosed temporal disaggregation)

The production bridge and actuator dispatch must remain disabled until live PostgreSQL and staging certification pass.
