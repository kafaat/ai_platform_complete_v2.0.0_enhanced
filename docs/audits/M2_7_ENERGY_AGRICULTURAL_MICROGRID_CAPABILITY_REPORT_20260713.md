# M2.7 Energy and Agricultural Microgrid Capability

Date: 2026-07-13

## Scope

Implemented the governed, recommendation-only energy capability layer for irrigation assets. The stage converts certified PV, inverter, battery, generator/grid, load and weather facts into deterministic hourly energy envelopes consumable by the irrigation MPC boundary.

## Added files

- `services/sahool-platform/api/canonical_energy_microgrid_capability.py`
- `migrations/v173_energy_agricultural_microgrid_capability.sql`
- `scripts/ci/irrigation_energy_m2_7_guard.py`
- `tests_v9/test_canonical_energy_microgrid_capability.py`

## Canonical product

`CanonicalEnergyMicrogridCapability` contains:

- certified system identity and lineage;
- inverter continuous kW and peak kVA;
- LiFePO4 and other supported battery chemistry metadata;
- live battery SoC, SoH, BMS state and temperature;
- protected minimum/emergency reserve SoC;
- PV output forecast per hour;
- generator/grid availability and energy price;
- certified load continuous kW and starting kVA;
- permitted and blocked load IDs per hour;
- renewable fraction and deterministic SHA-256 capability digest.

## Fail-closed rules

The product blocks operational eligibility when any material safety input is absent or invalid, including:

- uncertified energy system;
- incomplete inverter limits;
- incomplete battery limits;
- BMS not ready;
- battery temperature outside 0–45 C;
- battery SoH below 70%;
- grid voltage/frequency outside limits;
- uncertified generator;
- uncertified/incomplete load start profile;
- missing or ungoverned hourly solar forecast.

Battery discharge is reduced to zero when SoC reaches the protected reserve; this is a limitation, not an invented source of energy.

## Energy model

PV AC power uses a conservative nameplate model:

- irradiance ratio relative to 1000 W/m2;
- approximate cell temperature from ambient temperature and irradiance;
- configurable temperature coefficient;
- configurable system derate;
- cap at PV nameplate.

Starting feasibility is evaluated independently from continuous kW. Explicit `starting_kva` takes precedence; otherwise it is derived from rated kW, power factor, start method and starting multiplier. Supported start methods are VFD, soft starter, star-delta and direct-on-line.

## Database

Migration v173 adds:

- `irrigation_pv_arrays`
- `irrigation_hybrid_inverters`
- `irrigation_battery_systems`
- `irrigation_generators`
- `irrigation_grid_connections`
- `irrigation_energy_loads`
- `canonical_energy_capabilities`
- `hourly_energy_envelopes`

All tables include tenant ownership, composite tenant-bound foreign keys where applicable, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and tenant `USING/WITH CHECK` policies.

## MPC boundary

`energy_capability_to_mpc_constraints()` exposes only verified constraints:

- hourly maximum available power kW;
- hourly maximum starting kVA;
- maximum battery discharge kW;
- protected reserve SoC;
- permitted loads;
- energy cost;
- renewable fraction;
- canonical capability digest.

No dispatch, controller write or automatic execution path was added.

## Verification

Focused tests:

- 7 passed, 0 failed.

Combined irrigation truth/engineering/MPC regression:

- 88 passed, 0 failed;
- 14 pre-existing FastAPI `on_event` deprecation warnings.

Repository guards:

- M2.1 PASS
- M2.2 PASS
- M2.3 PASS
- M2.4 PASS
- M2.5 PASS
- M2.6 PASS
- M2.7 PASS

Python compilation passed for the new module, tests and guard.

## Not certified in this environment

- applying v173 against a live PostgreSQL instance;
- live cross-tenant RLS denial test;
- live BMS/inverter/generator/grid telemetry;
- calibrated PV forecast against field measurements;
- end-to-end consumption by the operational MPC route;
- physical command dispatch.

## Next stage

M2.8 should build the Unified Irrigation Capability Graph and combine verified Well, Hydraulic, Machine, Sprinkler/Runoff, Energy and Controller capabilities under weakest-link semantics before the operational MPC can consume them.
