# P3.1 Weather Service Core — Implementation Report

## Scope

Implemented the first real runtime surface inside `services/weather-service`, replacing the previous honest 501 stub behavior for core weather facts.

## Added/changed

- `services/weather-service/open_meteo.py`
  - Open-Meteo forecast/archive provider calls.
  - Normalized current, daily forecast, historical, and tile sample payloads.
- `services/weather-service/main.py`
  - `GET /v1/weather/current`
  - `GET /v1/weather/forecast`
  - `GET /v1/weather/historical`
  - runtime `/contract`, `/healthz`, `/readyz`
- `services/weather-service/cache.py`
  - Small in-memory cache for tile/operation sampling.
- `services/weather-service/requirements.txt`
  - Added `httpx==0.28.1`.

## Contract change

`weather-service` now reports:

```json
{"mode": "runtime", "implemented_runtime": true}
```

rather than returning 501 for all weather work.

## Guarding

Updated the P1 weather boundary guard to require the P3 runtime contract.
