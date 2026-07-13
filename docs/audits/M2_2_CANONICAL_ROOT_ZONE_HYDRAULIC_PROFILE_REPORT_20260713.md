# M2.2 Canonical Root-Zone Hydraulic Profile — Completion Report

## Scope

This stage replaces generic texture/root-depth fallback in the operational water truth with a governed, tenant-bound root-zone hydraulic product.

## Delivered

- `migrations/v168_canonical_root_zone_hydraulic_profile.sql`
  - `crop_root_policies`
  - `canonical_root_zone_profiles`
  - composite tenant-safe foreign key
  - RLS + FORCE RLS
  - digest/idempotent snapshot uniqueness
- `services/sahool-platform/api/soil_hydraulic_client.py`
  - strict read of soil-service governed hydraulic profile
  - no synthetic fallback on network/auth/product failure
- `services/sahool-platform/api/canonical_root_zone_profile.py`
  - validated root-policy requirement
  - phenology-aware current root depth
  - depth-weighted integration across soil layers
  - coarse-fragment correction
  - TAW/RAW computation
  - weighted FC/WP/AWC
  - conservative infiltration and Ksat envelope
  - salinity evidence capture
  - profile freshness and evidence-origin quality rules
  - immutable SHA-256 digest
  - append-only/idempotent persistence
- `canonical_water_state.py`
  - now consumes the canonical root-zone profile
  - removed operational dependency on `soil_water_params` generic fallback
  - blocks when root policy, governed soil profile, layer coverage, or phenology are missing
- CI ratchet: `scripts/ci/irrigation_root_zone_m2_2_guard.py`
- Focused tests: `tests_v9/test_canonical_root_zone_profile.py`

## Operational eligibility

Operational use requires:

1. validated crop root policy;
2. valid phenology progress;
3. executable soil hydraulic profile;
4. complete layer coverage through current root depth;
5. measured FC/WP evidence;
6. field infiltration measurement;
7. profile freshness within policy.

Pedotransfer values remain usable for degraded advisory/simulation but do not qualify for automatic operational recommendation.

## Verification

- Python compilation: PASS
- M2.1 engineering guard: PASS
- M2.2 root-zone guard: PASS
- Soil P1–P5 guards: PASS
- Relevant water/soil/MPC test suite: `194 passed, 0 failed`
- FastAPI warnings: 14 existing `on_event` deprecation warnings
- Ruff: not executed because the binary is unavailable in the environment

## Not certified in this environment

- Real PostgreSQL migration execution and cross-tenant RLS denial
- Live soil-service HTTP integration
- Production root-policy seed/calibration data
- Staging MPC candidate-to-outcome lifecycle

## Next stage

M2.3 — Water Source and Well Digital Twin:

- well measurements and pumping tests;
- static/dynamic level, drawdown, recovery, sustainable flow;
- water allocation and abstraction limits;
- water-quality linkage;
- canonical well capability product for MPC.
