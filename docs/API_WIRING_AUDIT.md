# API Wiring Audit — SAHOOL Web (sprint-wiring-audit)

Goal: ensure every web screen talks to a **real** backend endpoint (no mock/stub
data, no wrong paths/methods). Mock data is allowed only behind the explicit
`VITE_MOCK_MODE=true` flag (the `tryReal()` helper returns its fallback **only**
when `MOCK_MODE` is set; otherwise it makes the real call and lets errors surface).

## Fixes applied in this sprint

### Gap 1 — Indicators dashboard had no real backend
`services/indicators-service` is a health-only stub (no logic). The web called
`:8091/indicators/dashboard`, `/indicators/catalog`, `/v1/indicators/{id}`,
`/indicators/nats/status`, plus `vegetation:/v1/ndvi/all` — none of which existed —
so `useDashboardKPIs` silently swallowed every error and always returned empty
arrays (a pseudo-mock).

Fix (preferred path — real aggregation in the platform, tenant-isolated):
- Added `GET /api/v1/indicators/dashboard` to `services/sahool-platform/api/main.py`
  — live aggregation from `fields` / `seasons` / `alerts` (RLS + `tenant_id`,
  `require_permission(FIELD_VIEW)`, DB error → `_db_unavailable` 503). Returns
  `kpis` (real counts), `alerts` (active), `fields_summary` (per field +
  `has_active_season`). No invented NDVI/weather values.
- Added `GET /api/v1/indicators/catalog` — honest catalog of the indicators the
  platform actually computes (14 entries) with their real source service.
- Pure shaping helpers `_shape_indicators_dashboard` / `_shape_indicator_catalog`
  with offline unit tests (`tests/test_indicators_dashboard.py`, 7 tests).
- Repointed the frontend: `useDashboardKPIs`, `fetchDashboard`,
  `useIndicatorsCatalog`, `fetchIndicatorCatalog` now call `kongApi`
  `/api/v1/indicators/*`. Removed the dead stub-only calls
  (`fetchFieldIndicators`, `fetchSingleIndicator`, `fetchNatsStatus`) — per-field
  spectral indicators come from vegetation/raster, not a fake 33-indicator route.

### Gap 2 — Vegetation method/path mismatch
The web called `POST /v1/analyze`, `/vegetation/field/{id}/timeseries`,
`/vegetation/field/{id}/current-ndvi`, `/vegetation/anomalies` but
`services/vegetation-analysis-service` exposes `GET /v1/analyze` and
`GET /v1/timeseries/{id}`.

Fix:
- Added `GET /v1/ndvi/current/{field_id}` and `GET /v1/all_fields` to the
  vegetation service (reuse `run_analysis`; honest `real_data:false` estimates).
  Pure helper `_current_ndvi_payload` + 2 offline tests.
- Frontend repointed to the real routes: `analyzeVegetation` and
  `useAnalyzeVegetation` now `GET /v1/analyze` (was POST → 405);
  `fetchVegetationTimeseries` → `GET /v1/timeseries/{id}`; `fetchCurrentNDVI` →
  `GET /v1/ndvi/current/{id}`; `useIndicators` derives field indicators from
  `GET /v1/analyze`. Removed the non-existent `/vegetation/anomalies` call.

## Screen → endpoint status (after fixes)

| Screen | Hook / call | Endpoint (real) | Status |
|---|---|---|---|
| HybridIndexPage (Indicators) | `useDashboardKPIs` | `GET /api/v1/indicators/dashboard` (platform) | real (tenant-scoped) |
| Indicators catalog | `useIndicatorsCatalog` / `fetchIndicatorCatalog` | `GET /api/v1/indicators/catalog` (platform) | real |
| SatellitePage — timeseries | `useVegetationTimeseries` | `GET /v1/timeseries/{id}` (vegetation) | real (synthetic estimate, `real_data:false`) |
| SatellitePage — current NDVI | `useCurrentNDVI` | `GET /v1/ndvi/current/{id}` (vegetation) | real (estimate) |
| SatellitePage — analyze | `useAnalyzeVegetation` | `GET /v1/analyze` (vegetation) | real (estimate) |
| SatellitePage — map tiles/grid | `useIndicatorGrid` | `GET /v1/fields/{id}/indicator-grid` (raster) | real (per-pixel) |
| Dashboard field indicators | `useIndicators` | `GET /v1/analyze` (vegetation) | real (estimate) |
| All-fields NDVI | `useAllFieldsNdvi` | `GET /v1/all_fields` (vegetation) | real (estimate) |
| Fields / Farms / Seasons / Activities | `useFields` / `useFarms` / `useActivities` … | `/api/v1/...` (platform) | real (unchanged) |
| Alerts / Recommendations / Reports / Weather advice | `useAlerts` / `useFieldRecommendations` / `useFarmSummary` … | `/api/v1/...` (platform) | real (unchanged) |
| Inventory / Equipment / Devices / Irrigation / Master-data / Documents / Governance | respective hooks | `/api/v1/...` (platform) | real (unchanged) |
| Auth / MFA / password reset | `login` / `mfaSetup` … | `/auth/...` (auth-service) | real (unchanged) |

## Honesty / source notes
- Vegetation indices are field-mean estimates from deterministic synthetic bands
  (`real_data:false`, `provider_reachable` flag). Real per-pixel processing is in
  raster-service (used by the Satellite map). This is labelled in the service and
  surfaced by the UI's data-source banner — not presented as decoded pixels.
- The indicators dashboard reports only counts that exist in the tenant's tables;
  spectral/weather values per field are fetched from their real services on the
  relevant screens.
- `HybridIndexPage` still renders a static `WOFOST_DATA` / `SPARKLINES` block as
  cosmetic demo decoration (not claimed as live API data). Out of scope for this
  wiring sprint; flagged for a future pass.

## Verification
- `python3 -m py_compile` on all touched Python files — OK.
- `ruff check` + `ruff format --check` — clean.
- `pytest tests/test_indicators_dashboard.py` — 7 passed;
  `pytest test_vegetation_logic.py` — 19 passed.
- `npm ci && npm run typecheck && npm run build` — all green.
