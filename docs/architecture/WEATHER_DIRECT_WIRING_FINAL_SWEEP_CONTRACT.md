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

## Residuals (pending P4) — W1-22

W1-22 moved every data-path residual behind weather-service and lowered
`composite_residuals_ceiling` to `1`. The one entry left is the provider self-test
`weather_wind_source_selftest` in `api/routers/weather.py` (held at function level by the
guard): it is a live diagnostic of the adapter itself, and the adapter's last executable root.
Removing it needs an owner decision to delete the platform adapter and its breaker, since the
module reachability guard blocks unreachable baseline modules.

- `api/routers/weather.py` — the tile sampler (tile-data / field-weather-summary / alerts), the
  point probe and the wind-source self-test use `weather_service_client.get_point_weather_sample`
  (weather-service `/v1/weather/tile-data` at zoom 18), except the provider self-test above.
  readyz/health declare
  `breaker: {state: delegated, owner: weather-service}` instead of the platform's unused breaker.
- `api/main.py` (field alerts), `api/field_context.py` (3-day historical rain),
  `api/routers/fields.py` (recommendations), `api/routers/etc_dual.py` (ETc),
  `api/routers/season_workspace.py` and `api/weather_automation.py` read typed views through
  the typed readings in `api/weather_service_client.py`, which keep an absent reading as `None`.
- `api/routers/field_ai_context.py` (AI context pack) reads the canonical historical view with the
  tenant identity; an incomplete rain/ET0 total is `None` with the missing-day count, never a sum
  that counts a missing day as a dry one.

The scan now covers every non-test platform package (`api/`, `core/`, `workers/`, root scripts),
so `api.connectors.openmeteo` may be imported only by the connector module itself and the
provider self-test.

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
