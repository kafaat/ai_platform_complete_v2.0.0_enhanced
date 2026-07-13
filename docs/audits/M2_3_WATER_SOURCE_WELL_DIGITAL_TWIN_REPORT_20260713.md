# M2.3 Water Source and Well Digital Twin — Completion Report

Date: 2026-07-13

## Scope

Implemented a canonical, tenant-bound well capability product that combines:

- commissioned water-source limits;
- certified pumping tests;
- recent static/dynamic well measurements;
- drawdown and specific capacity;
- recovery rate and minimum rest policy;
- daily and seasonal allocation balances;
- water-quality/salinity evidence;
- immutable SHA-256 provenance;
- fail-closed translation into MPC constraints.

## Added files

- `services/sahool-platform/api/canonical_well_capability.py`
- `services/sahool-platform/tests/test_canonical_well_capability.py`
- `migrations/v169_water_source_well_digital_twin.sql`
- `scripts/ci/irrigation_well_digital_twin_m2_3_guard.py`

## Database model

The migration adds:

- `irrigation_well_pumping_tests`
- `irrigation_well_measurements`
- `irrigation_water_quality_samples`
- `irrigation_water_allocations`
- `canonical_well_capabilities`

It also extends existing source/well records with:

- `maximum_allowed_ec_ds_m`
- `maximum_drawdown_m`
- `minimum_rest_hours`

All new tables use tenant-bound composite foreign keys, RLS, FORCE RLS, and immutable evidence-oriented records.

## Canonical capability rules

The product blocks operational use when:

- no certified pumping test exists;
- water levels are missing or contradictory;
- well measurement is stale;
- pumping test is stale;
- drawdown exceeds the certified limit;
- daily or seasonal allocation is exhausted;
- water quality is stale or missing where required;
- EC exceeds the configured source limit;
- no positive legal sustainable flow remains.

Maximum operational flow is the weakest applicable limit among:

- certified sustainable pumping-test flow;
- tested flow;
- well sustainable flow;
- commissioned source flow;
- remaining legal daily allocation converted to average L/s.

The daily volume conversion is `remaining_m3 / 86.4` to L/s.

## MPC bridge

`well_capability_to_mpc_constraints()` returns only governed constraints:

- `source_well_id`
- `maximum_source_flow_lps`
- `remaining_daily_volume_m3`
- `remaining_seasonal_volume_m3`
- `minimum_rest_hours`
- `well_capability_digest`

Blocked or degraded capability remains fail-closed.

## Verification

- Python compilation: PASS
- M2.1 guard: PASS
- M2.2 guard: PASS
- M2.3 guard: PASS
- focused contracts/tests: 11 passed
- combined canonical water/root-zone/MPC tests: 69 passed, 0 failed
- 14 pre-existing FastAPI `on_event` deprecation warnings

## Explicit limits

This environment did not certify:

- executing migration v169 on a real PostgreSQL instance;
- live RLS cross-tenant denial;
- live well telemetry ingestion;
- actual pumping-test workflow signatures;
- runtime persistence of canonical capability snapshots;
- end-to-end MPC use of the capability inside a production recommendation route.

The next stage should be M2.4 pump and hydraulic network capability, consuming this canonical well capability as its upstream source envelope.
