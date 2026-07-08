# P1 Weather Ownership Contract Implementation Report

## Scope

Implemented the safe weather boundary phase on top of P0 ownership guards and P1 raster boundary.
This phase does **not** move weather runtime out of `sahool-platform`, because source verification shows
`services/weather-service/main.py` is still an honest stub. Instead, it freezes the target ownership and
adds CI guards to prevent further weather-domain growth inside `sahool-platform`.

## Files added

- `docs/architecture/WEATHER_OWNERSHIP_CONTRACT.md`
- `docs/architecture/weather_boundary_allowlist.json`
- `services/sahool-platform/tests/test_p1_weather_boundary_guard.py`
- `P1_WEATHER_OWNERSHIP_CONTRACT_REPORT.md`

## Files changed

- `docs/architecture/platform_extraction_map.json`
- `services/weather-service/main.py`

## Key changes

1. Reclassified weather-like platform routes to target `weather-service` in the extraction map.
   - 13 route owner entries were corrected from legacy/raster classifications to `weather-service`.
2. Added a weather allowlist that records every existing platform file allowed to keep temporary weather logic.
3. Added static guards that fail when:
   - a weather-like platform route is not assigned to `weather-service`;
   - weather provider/runtime markers appear outside the allowlist;
   - weather-owned tables have a writer other than `weather-service`;
   - `weather-service` stops being an honest stub without exposing the expected contract surface.
4. Updated `weather-service` stub to expose:
   - `/contract`
   - `/weather/{path:path}` returning 501
   - `/v1/weather/{path:path}` returning 501

## Test command

```bash
pytest -q \
  services/sahool-platform/tests/test_p0_platform_route_ownership_guard.py \
  services/sahool-platform/tests/test_p0_db_ownership_guard.py \
  services/sahool-platform/tests/test_p0_platform_module_growth_guard.py \
  services/sahool-platform/tests/test_p1_raster_boundary_guard.py \
  services/sahool-platform/tests/test_p1_weather_boundary_guard.py
```

## Result

```text
14 passed
```

## Closure criteria met

- Weather target ownership is now codified.
- Weather runtime growth inside platform is blocked except for documented legacy/facade files.
- Weather database ownership is guarded.
- `weather-service` advertises a truthful contract stub instead of silently pretending runtime support.

## Remaining work

The next safe phase is **P1 Decision / Outcome / Learning Bridge**:

- consolidate recommendation/decision/execution/verification/outcome/learning lineage;
- prevent new decision/outcome domain logic from growing inside random platform routers;
- guard that learning updates trace back to an outcome and source decision;
- do not extract decision runtime until lineage is locked.
