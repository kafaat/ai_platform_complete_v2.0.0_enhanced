# P3.5 — Weather Direct Wiring Final Sweep

## Goal

Close out the P3 weather extraction: after P3.4 turned the 9 core platform weather routes into
thin facades to weather-service, sweep the rest of `services/sahool-platform` for direct
Open-Meteo wiring, pin every remaining reference to an honest reason, and lock the boundary
with a guard so it cannot re-spread.

## Rule

Direct Open-Meteo wiring (import of `api.connectors.openmeteo`, or a call to `fetch_current` /
`fetch_daily_forecast` / `fetch_historical` / `fetch_weather_tile_data`) is allowed only in the
two legitimate homes:

- `api/connectors/openmeteo.py` — the Open-Meteo provider adapter.
- `api/weather_service_client.py` — the P3.4 weather-service boundary transport.

All other referencing files are cross-domain composite residuals pending P4.

## Residuals (pending P4)

| File | Reason |
| --- | --- |
| `api/routers/weather.py` | 9 core routes are P3.4 facades; residual local endpoints (probe, field-weather-summary, alerts) still derive from the provider adapter. |
| `api/main.py` | Legacy combined dashboard endpoint composes current + daily forecast inline. |
| `api/field_context.py` | Field-context aggregator pulls historical weather for phenology/season. |
| `api/routers/fields.py` | Fields BFF composes per-field current + forecast weather summary. |
| `api/routers/etc_dual.py` | ETc dual-crop endpoint composes current + forecast with crop coefficients. |
| `api/routers/field_ai_context.py` | AI-context builder reads historical weather to ground agronomy context. |
| `api/routers/season_workspace.py` | Seasonal planning view composes forecast/current weather. |
| `api/routers/seasons.py` | Season retrospectives pull historical weather. |
| `api/weather_automation.py` | Weather-driven automation/alerts worker polls current weather. |

Full reasons: [`docs/architecture/weather_direct_wiring_allowlist.json`](docs/architecture/weather_direct_wiring_allowlist.json).

## Neutral-tile guarantee across the hop

`api/weather_service_client.py` `get_weather_tile_data` / `get_operation_tile_data` catch a 502
(weather-service unreachable) and return a neutral tile (`value=null`, `available=false`,
`cache_state="service_unavailable"`, `rendered_by="sahool-client-gridlayer"`) instead of a
Bad Gateway per tile. Non-502 errors (e.g. 400 bad layer) still propagate. weather-service
itself returns a neutral tile on total upstream failure with no cache.

## Deliverables

- `docs/architecture/weather_direct_wiring_allowlist.json` — homes + residuals + markers.
- `docs/architecture/WEATHER_DIRECT_WIRING_FINAL_SWEEP_CONTRACT.md` — the rule + guarantee.
- `services/sahool-platform/tests/test_p3_5_weather_direct_wiring_final_sweep.py` — scans
  `api/**/*.py`; fails on any new offender; verifies allowlist is not stale.
- `services/sahool-platform/tests/test_p3_4_weather_facade_neutral.py` — facade neutral fallback,
  non-502 propagation, route-proxies-facade, and boundary-client import-safety (no module-level
  fastapi import).
- Import-safety fix: `api/weather_service_client.py` and `api/raster_service_client.py` now
  lazy-import `HTTPException` inside the functions that use it, so both stay importable in the
  pure-logic `pytest -m unit` tier (which runs without fastapi).

## Test migration (P3.4 fallout)

16 platform tests that mocked the old in-platform provider path were migrated: runtime behavior
that moved to weather-service was removed from the platform (with equivalents added to
weather-service where not already covered); platform concerns (observability, prometheus,
action-recommendation task-draft) were converted to mock the operation-plan facade. See the
P3.4 report for the per-file breakdown.
