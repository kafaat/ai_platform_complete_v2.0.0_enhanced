# SAHOOL — Open-Meteo Weather Map Engine v8

## Scope
Implemented the improved architecture requested by the user:

Open-Meteo is the data source, and SAHOOL renders tiles, animation, legends, layer controls, time selection, probe popups, and agronomic operation suitability.

## Backend changes

### `services/sahool-platform/api/connectors/openmeteo.py`
- Extended hourly variables to include forecast-time versions of temperature, RH, precipitation, wind, pressure, cloud cover, ET0, VPD, soil temperature, and soil moisture.
- Added `time_key` handling: `now`, `+1h`, `+3h`, `+6h`, `+12h`, `+24h`, `+48h`.
- Added optional `model` passthrough while preserving Open-Meteo `best_match` default behavior.
- `fetch_weather_tile_data()` now returns time-aware weather samples.

### `services/sahool-platform/api/routers/weather.py`
- Enhanced `/api/v1/weather/tile-data/{z}/{x}/{y}` with:
  - `time`
  - `model`
  - cache key isolation per tile/time/model.
- Added `/api/v1/weather/operation-tile-data/{z}/{x}/{y}` for agronomic operation suitability:
  - `spraying`
  - `harvesting`
  - `sowing`
  - `irrigation`
- Added `/api/v1/weather/probe` for map-click point inspection.
- Added `/api/v1/weather/tile-series/{z}/{x}/{y}` for time-series animation support.

## Frontend changes

### `frontend/src/components/maphub/OverlayMarkers.tsx`
- Extended weather layers with operation decision layers:
  - `operation_spraying`
  - `operation_irrigation`
  - `operation_harvesting`
  - `operation_sowing`
- Added weather presets:
  - Spray mode
  - Irrigation mode
  - Harvest mode
  - Sowing mode
- Added time selector:
  - Now, +1h, +3h, +6h, +12h, +24h, +48h
- Added click probe popup showing:
  - temperature
  - wind speed/direction
  - precipitation
  - VPD
  - ET0
  - soil moisture
  - operation suitability scores
- Weather tiles are still rendered as Leaflet GridLayer SVG tiles by SAHOOL.
- Open-Meteo remains a data provider, not a tile provider.

## Verification

Executed:

```bash
python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core
```

Result: passed.

Frontend build was not executed because `frontend/node_modules` is not present in this environment.
