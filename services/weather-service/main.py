"""SAHOOL Weather Service entrypoint.

P2 decomposition shell: Open-Meteo access, cache fallback, operation-window logic,
and tile/wind-grid handlers live in ``weather_runtime.py``. This file owns only
FastAPI route registration and keeps the public contract unchanged.
"""

from __future__ import annotations

from fastapi import FastAPI

import weather_runtime as rt

app = FastAPI(title="SAHOOL Weather Service", version="10.0")

# Compatibility re-exports: existing tests/operators monkeypatch these names on ``main``.
fetch_current = rt.fetch_current
fetch_forecast = rt.fetch_forecast
fetch_historical = rt.fetch_historical
fetch_tile_sample = rt.fetch_tile_sample
readiness_probe = rt.readiness_probe


app.get("/healthz")(rt.healthz)
app.get("/health")(rt.health)
app.get("/readyz")(rt.readyz)
app.get("/")(rt.root)
app.get("/contract")(rt.contract)
app.get("/v1/weather/current")(rt.current_weather)
app.get("/v1/weather/forecast")(rt.forecast_weather)
app.get("/v1/weather/historical")(rt.historical_weather)
app.get("/v1/weather/operation-window")(rt.operation_window)
app.get("/v1/weather/operation-plan")(rt.operation_plan)
app.get("/v1/weather/tile-data/{z}/{x}/{y}")(rt.tile_data)
app.get("/v1/weather/operation-tile-data/{z}/{x}/{y}")(rt.operation_tile_data)
app.get("/v1/weather/tile-series/{z}/{x}/{y}")(rt.tile_series)
app.get("/v1/weather/wind-grid/{z}/{x}/{y}")(rt.wind_grid)
app.get("/v1/weather/cache-stats")(rt.tile_cache_stats)
