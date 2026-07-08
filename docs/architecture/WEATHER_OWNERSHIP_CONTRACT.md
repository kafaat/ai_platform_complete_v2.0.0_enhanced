# Weather Ownership Contract — P1 Boundary

This contract freezes the weather boundary before any extraction from `sahool-platform`.
It is deliberately a **contract/guard phase**, not a functional migration phase, because
`services/weather-service/main.py` is still an honest stub in the current source tree.

## Target owner

`weather-service` owns weather facts and weather-derived operational windows after extraction.

## Current state verified from source

- `services/weather-service/main.py` exposes health/readiness and returns `501` for weather work.
- `services/sahool-platform/api/routers/weather.py` still contains the runtime implementation for
  Open-Meteo calls, tile cache, probes, operation windows, operation plans, weather alerts, and
  weather-derived task/recommendation helpers.
- Therefore extraction must be staged through facades and guards, not direct deletion.

## Ownership rule

`sahool-platform` may temporarily host legacy weather endpoints only as compatibility/facade code.
It must not gain new weather provider clients, new weather caches, new weather rate-limit stores,
or new weather-derived operational-window implementations outside the allowlisted files.

## Target responsibilities

| Capability | Target owner | Notes |
|---|---|---|
| Current weather | `weather-service` | External provider calls move here. |
| Forecast | `weather-service` | Unified provider/model contract. |
| Historical weather | `weather-service` | Includes historical backfill contracts. |
| Weather tiles / wind grid | `weather-service` | Tile cache may later split into a weather tile worker, but not platform. |
| Operation windows | `weather-service` | Spray/harvest/sowing/fertilizer suitability windows. |
| Weather alerts/signals | `weather-service` + workers | Workers emit signal events; platform consumes summaries. |
| Weather-based recommendation creation | `agriai-engine` + `weather-service` | Weather provides facts; AI/decision services decide. |

## Platform allowed behavior during migration

- Proxy/facade endpoints for existing UI/API compatibility.
- Tenant/field ownership checks before calling `weather-service`.
- Aggregated read models/cards that consume weather facts.
- Legacy helpers listed in `weather_boundary_allowlist.json` until replaced.

## Platform forbidden behavior after this guard

- New direct Open-Meteo/NASA/Metno provider implementation outside allowlist.
- New long-lived weather cache or weather rate-limit state outside allowlist.
- New weather operation-window algorithm outside allowlist.
- New database writer ownership for weather-owned tables/signals.

## Extraction sequence

1. Keep current platform endpoints stable.
2. Add real `weather-service` endpoints behind the same contract.
3. Switch platform weather routes to HTTP clients/facades.
4. Move frontend/gateway routing to `weather-service` where safe.
5. Remove legacy platform implementation after deprecation.
