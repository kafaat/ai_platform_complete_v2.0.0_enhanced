# Weather Direct Wiring Final Sweep Contract (P3.5)

Status: **P3.5 — Weather Direct Wiring Final Sweep**

## Rule

Direct Open-Meteo wiring in `services/sahool-platform` — importing `api.connectors.openmeteo`
or calling `fetch_current` / `fetch_daily_forecast` / `fetch_historical` /
`fetch_weather_tile_data` — is allowed in exactly two legitimate homes:

1. `api/connectors/openmeteo.py` — the **Open-Meteo provider adapter** (the only place that
   speaks to the Open-Meteo HTTP provider, with its circuit breaker).
2. `api/weather_service_client.py` — the **weather-service boundary transport** added in P3.4
   (thin HTTP client to the weather-service system-of-record). It does not import Open-Meteo
   connectors, but is the sanctioned weather transport home.

Every OTHER platform file that still references those markers is a **cross-domain composite
residual** (`composite_residuals_pending_p4`): an aggregator that pulls weather alongside
soil/raster/agronomy/season facts. Each such file is enumerated with an honest reason in
[`weather_direct_wiring_allowlist.json`](weather_direct_wiring_allowlist.json) and is pending
P4 consolidation behind the weather facade.

The guard test `services/sahool-platform/tests/test_p3_5_weather_direct_wiring_final_sweep.py`
scans `api/**/*.py` and **fails on any new offender** — a file that references a direct marker
but is neither a legitimate home nor a listed residual. This prevents direct Open-Meteo wiring
from quietly re-spreading through unrelated platform modules.

## Residuals (pending P4)

- `api/routers/weather.py` — 9 core routes are P3.4 facades; residual local endpoints (probe,
  field-weather-summary, alerts) still derive from the provider adapter.
- `api/main.py`, `api/field_context.py`, `api/routers/fields.py`, `api/routers/etc_dual.py`,
  `api/routers/field_ai_context.py`, `api/routers/season_workspace.py`, `api/routers/seasons.py`,
  `api/weather_automation.py` — cross-domain aggregators/automation.

## Neutral-tile guarantee (across the network hop)

The pre-extraction map guarantee — *do not flood the map with a 502 per tile when the provider
is down* — is preserved across the new platform→weather-service hop. In
`api/weather_service_client.py`, `get_weather_tile_data` and `get_operation_tile_data` catch a
`502` (weather-service unreachable) and return a **neutral tile**:

```
{"tile": {...}, "layer": ..., "value": null, "sample": null, "available": false,
 "cache_state": "service_unavailable", "upstream_error": "weather-service unreachable",
 "rendered_by": "sahool-client-gridlayer"}
```

weather-service itself already returns a neutral tile (200, `value=null`) on a total upstream
failure with no cache (see `services/weather-service/tests/test_p3_tile_neutral_resilience.py`);
the facade fallback covers the complementary case where weather-service is entirely unreachable.

## Related

- P3.4 platform weather facade: [`WEATHER_OWNERSHIP_CONTRACT.md`](WEATHER_OWNERSHIP_CONTRACT.md)
- Facade neutral fallback test: `services/sahool-platform/tests/test_p3_4_weather_facade_neutral.py`
- weather-service runtime coverage: `services/weather-service/tests/test_p3_4_weather_service_runtime_coverage.py`
