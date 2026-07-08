# P3.4 Platform Weather Facade Report

## Scope

P3.4 moves the primary weather read paths in `sahool-platform` behind a dedicated weather-service facade. The goal is not to delete all legacy composite weather consumers yet; it is to stop the public/core weather routes from owning provider calls, tile math, wind grid interpolation, and operation scoring.

## Added

- `services/sahool-platform/api/weather_service_client.py`
- `services/sahool-platform/tests/test_p3_4_platform_weather_facade_guard.py`

## Converted platform routes

- `GET /api/v1/weather/current`
- `GET /api/v1/weather/forecast`
- `GET /api/v1/weather/historical`
- `GET /api/v1/weather/tile-data/{z}/{x}/{y}`
- `GET /api/v1/weather/operation-tile-data/{z}/{x}/{y}`
- `GET /api/v1/weather/operation-window`
- `GET /api/v1/weather/operation-plan`
- `GET /api/v1/weather/tile-series/{z}/{x}/{y}`
- `GET /api/v1/weather/wind-grid/{z}/{x}/{y}`
- `GET /api/v1/weather/tile-cache/stats`

## Boundary rule

`weather-service` owns:

- Open-Meteo/provider calls
- weather tile cache state
- weather tile center/grid math
- wind-grid interpolation
- operation-window and operation-plan scoring

`sahool-platform` owns only:

- API compatibility routes
- rate-limit/auth/BFF surface
- orchestration with task/alert/recommendation domains

## Honest residuals

The following remain intentionally outside this P3.4 cut because they are cross-domain aggregators:

- `field-weather-summary`
- `weather-action-recommendation`
- `weather-alerts`
- `task/recommendation from operation plan`
- field/season consumers that combine weather with crop/field state

These should be addressed in P3.5/P4 with a final direct-wiring sweep and domain boundary split.
