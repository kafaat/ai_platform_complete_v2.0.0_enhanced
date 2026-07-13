# M2.4–M2.6 Sequential Irrigation Engineering Completion Report

Date: 2026-07-13
Base: sahool_7d338ad_m2.3_water-source-well-digital-twin-complete

## Scope completed

### M2.4 Pump and Hydraulic Network Capability
- Added `api/canonical_hydraulic_capability.py`.
- Certified pump-curve interpolation.
- Darcy-Weisbach friction with Swamee-Jain friction factor.
- Minor losses, elevation head, terminal pressure, TDH.
- Bisection search for maximum deliverable flow.
- Pump/motor efficiency, electrical power and specific energy.
- Fail-closed reasons for head, flow, velocity, pressure rating and missing evidence.
- MPC constraint adapter.
- Added migration `v170_pump_hydraulic_network_capability.sql`.

### M2.5 Irrigation Machine Capability
- Added `api/canonical_irrigation_machine_capability.py`.
- Supports center pivot, sector pivot and linear families.
- Correct application formula: `mm/day = 8.64 × Q_lps / A_ha`.
- Full-cycle depth and speed envelope.
- Requires certified machine, controller status telemetry and verified hydraulic capability.
- MPC constraint adapter.
- Added migration `v171_irrigation_machine_capability.sql`.

### M2.6 Sprinkler Package and Runoff Capability
- Added `api/canonical_sprinkler_runoff_capability.py`.
- Requires certified field-tested peak application rate.
- Combines root-zone infiltration, terrain slope and measured wind.
- Computes adjusted application rate, runoff margin and safety factor.
- Blocks high runoff risk and excessive wind.
- MPC constraint adapter.
- Added migration `v172_sprinkler_runoff_capability.sql`.

## Data governance
All new tables are tenant-bound and use `ENABLE ROW LEVEL SECURITY` plus `FORCE ROW LEVEL SECURITY`. Canonical snapshots carry full SHA-256 digests.

## Verification
- New focused tests: 7 passed.
- Combined irrigation truth/decision regression suite: 81 passed, 0 failed.
- M2.1 guard: PASS.
- M2.2 guard: PASS.
- M2.3 guard: PASS.
- M2.4 guard: PASS.
- M2.5 guard: PASS.
- M2.6 guard: PASS.
- Python compilation: PASS.
- Ruff not run because the executable is not installed in this environment.

## Deliberate limits
- Migrations were not executed against a live PostgreSQL instance.
- No live pump, controller, SCADA or telemetry connection was certified.
- The new capability adapters are not yet wired into the operational MPC route.
- Energy/PV/battery dispatch remains the next stage.

## Next stage
M2.7 Energy and Agricultural Microgrid Capability:
PV forecast, hybrid inverter, LiFePO4 battery, generator/grid, starting kVA, load priorities, hourly energy envelope and fail-closed MPC constraints.
