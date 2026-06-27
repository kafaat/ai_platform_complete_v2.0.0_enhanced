# P3 Legacy Endpoints + Indicator Availability UI Fix Report — 2026-06-26

## Scope
Implemented P3 non-critical runtime cleanup on top of `sahool_p2_runtime_observability_soil_fix_20260626.zip`.

## Fixes

### 1. Legacy health aliases
Added exact nginx aliases so shell probes no longer fall through to wrong upstreams or prefixes:

- `GET /api/indicators/readyz` → `indicators-service /readyz`
- `GET /api/weather/readyz` → `weather-service /readyz`
- `GET /api/vegetation/readyz` → `vegetation-analysis-service /readyz`

Also added sahool-platform compatibility fallbacks for deployments where nginx still routes these paths to platform.

### 2. Legacy vegetation endpoints
Added platform compatibility pass-throughs for misrouted legacy vegetation requests:

- `GET /api/vegetation/v1/all_fields`
- `GET /api/vegetation/v1/analyze`

These preserve query string and Authorization/X-Tenant-Id headers and forward to `VEGETATION_SERVICE_URL`.

### 3. Indicator availability UX
Updated `FieldIndicatorMap.tsx` to show availability state before/while selecting an index:

- `جاري التحقق: INDEX`
- `متاح: INDEX`
- `غير متاح: INDEX`

The map now surfaces backend `user_message`, `note`, or `reason` when TileJSON is unavailable.

## Tests

```text
pytest -q tests_v9/test_p3_legacy_routes_and_indicator_ui.py
3 passed
```
