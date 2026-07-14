# SAHOOL WX-I1 Native Hourly ETc Implementation Report

Date: 2026-07-14
Baseline: `sahool_ai_platform_8678b4d_irrigation_runtime_closed_loop_inventory_refreshed`

## Scope delivered

WX-I1 replaces the temporary daily-ETc temporal disaggregation used by M3 with a canonical provider-native hourly product owned by Weather Engine.

Pipeline:

```text
Open-Meteo hourly et0_fao_evapotranspiration + precipitation (UTC)
→ Weather Engine normalization
→ dated Season/Phenology Kc policy
→ hourly ETc
→ proportional governed runoff allocation
→ effective rainfall
→ net crop demand
→ per-hour and product SHA-256 digests
→ M3 hourly irrigation orchestrator
```

## New and changed components

- `services/weather-service/hourly_etc.py`
  - canonical `hourly_etc.v1` product
  - finite/non-negative validation
  - fail-closed missing-hour behavior
  - effective-rain computation using provider precipitation minus proportionally allocated governed daily runoff
  - per-hour and product content digests
  - provenance and quality contract
- `services/weather-service/open_meteo.py`
  - provider-native hourly FAO ET0 + precipitation fetch in UTC
- `services/weather-service/weather_runtime.py`
  - `HourlyEtcRequest`
  - cache-aware `agro_hourly_etc` handler
  - no stale or local ET0 fallback on provider failure
- `services/weather-service/main.py`
  - `POST /v1/weather/agro/etc/hourly`
- `services/sahool-platform/api/weather_service_client.py`
  - `get_hourly_etc_product`
- `services/sahool-platform/api/canonical_water_state.py`
  - canonical location included in evidence for downstream server-owned weather resolution
- `services/sahool-platform/api/irrigation_runtime_orchestrator.py`
  - consumes Weather Engine hourly ETc directly
  - joins exact UTC hours to governed energy windows
  - blocks on missing/misaligned hours
  - removes `DAILY_ETC_TEMPORALLY_DISAGGREGATED...` limitation
  - records hourly weather product digest and quality in schedule lineage
- `scripts/ci/weather_hourly_etc_wx_i1_guard.py`
  - locks provider-native ET0, UTC, route, digest, no-local-fallback, M3 consumption, and removal of old disaggregation
- `.github/workflows/ci.yml`
  - WX-I1 guard wired as a dedicated CI step

## Safety behavior

- M3 never calls Open-Meteo directly.
- Weather Engine remains the single ET0 product owner.
- No Penman-Monteith or Hargreaves fallback is introduced in the hourly product.
- Missing ET0, precipitation, Kc, or horizon hours returns a blocked product.
- Missing correspondence between weather hours and energy windows blocks orchestration.
- Actuator dispatch remains disabled; schedules remain recommendation-only.

## Verification

Weather tests:

```text
30 passed
0 failed
0 DeprecationWarnings
```

Irrigation/MPC regression tests:

```text
83 passed
0 failed
0 DeprecationWarnings
```

Combined related total:

```text
113 passed
0 failed
0 DeprecationWarnings
```

Guards:

```text
FastAPI lifespan guard: PASS
Weather engine formula guard: PASS
WX-I1 native hourly ETc guard: PASS
M3 hourly MPC guard: PASS
Runtime orchestrator guard: PASS
Closed-loop runtime guard: PASS
Irrigation RLS guard: PASS
Migration manifest: PASS — 190 migrations
CI workflow YAML parse: PASS
Release package validation: PASS — 4,387 checksums
```

## Remaining production evidence

This source-level completion does not claim:

- application of migrations through v184 on a live PostgreSQL instance;
- live Open-Meteo/staging HTTP evidence;
- cross-tenant RLS certification;
- controller/actuator dispatch certification;
- 7–14 day soak/chaos certification.

Keep execution bridge and actuator dispatch disabled until those runtime gates pass.
