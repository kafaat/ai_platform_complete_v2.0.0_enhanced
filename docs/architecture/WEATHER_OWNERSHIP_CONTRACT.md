# Weather Ownership Contract — P3 Runtime Realization

This contract defines the ownership boundary for weather after P3.1–P3.3.
The P1 state was an honest contract/stub; P3 now gives `weather-service` a real runtime surface while keeping `sahool-platform` compatibility routes intact until P3.4.

## Target owner

`weather-service` owns weather facts and weather-derived operational windows.

## Current state after P3.1–P3.3

- `services/weather-service/main.py` now exposes runtime endpoints instead of 501 stubs.
- `services/weather-service/open_meteo.py` owns Open-Meteo provider calls and response normalization.
- `services/weather-service/operations.py` owns operation suitability rules.
- `services/weather-service/tiles.py` owns tile math, tile layer values, and wind-grid interpolation points.
- `services/weather-service/cache.py` owns the local runtime cache used by the weather-service.
- `sahool-platform` still contains legacy compatibility routes in `api/routers/weather.py`; these are target-owned by `weather-service` in `platform_extraction_map.json` and must become facades in P3.4.

## Runtime capabilities now owned by `weather-service`

| Capability | Endpoint(s) | Phase |
|---|---|---|
| Current weather | `GET /v1/weather/current` | P3.1 |
| Forecast | `GET /v1/weather/forecast` | P3.1 |
| Historical weather | `GET /v1/weather/historical` | P3.1 |
| Runtime contract/readiness | `GET /contract`, `/readyz`, `/healthz` | P3.1 |
| Operation window | `GET /v1/weather/operation-window` | P3.2 |
| Operation plan | `GET /v1/weather/operation-plan` | P3.2 |
| Operation tile | `GET /v1/weather/operation-tile-data/{z}/{x}/{y}` | P3.2 |
| Weather tile data | `GET /v1/weather/tile-data/{z}/{x}/{y}` | P3.3 |
| Tile time series | `GET /v1/weather/tile-series/{z}/{x}/{y}` | P3.3 |
| Wind grid | `GET /v1/weather/wind-grid/{z}/{x}/{y}` | P3.3 |
| Tile cache status | `GET /v1/weather/tile-cache/stats` | P3.3 |

## Platform allowed behavior during P3.4 migration

- Proxy/facade endpoints for existing UI/API compatibility.
- Tenant/field ownership checks before calling `weather-service`.
- Aggregated read models/cards that consume weather facts.
- Legacy helpers listed in `weather_boundary_allowlist.json` until replaced.

## Platform forbidden behavior after P3 realization

- New direct Open-Meteo/NASA/Metno provider implementation outside allowlist.
- New long-lived weather cache or weather rate-limit state outside allowlist.
- New weather operation-window algorithm outside allowlist.
- New database writer ownership for weather-owned tables/signals.

## Next extraction sequence

1. Keep current platform weather endpoints stable.
2. Switch platform weather routes to a `weather_service_client` facade.
3. Move frontend/gateway routing to `weather-service` where safe.
4. Remove legacy platform implementation after deprecation and lower platform route budget.
