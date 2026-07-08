from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

main = importlib.import_module("main")


def _sample(**overrides):
    base = {
        "location": {"lat": 15.0, "lon": 44.0},
        "temperature_c": 24.0,
        "humidity_pct": 55.0,
        "wind_speed_10m_kmh": 10.0,
        "wind_speed_ms": 2.778,
        "wind_direction_10m_deg": 90,
        "wind_gusts_10m_kmh": 14.0,
        "precipitation_mm": 0.0,
        "cloud_cover_pct": 25,
        "et0_mm": 4.2,
        "vpd_kpa": 1.4,
        "soil_temperature_6cm_c": 20.0,
        "soil_temperature_18cm_c": 19.0,
        "soil_temperature_54cm_c": 18.0,
        "soil_moisture_1_to_3cm_m3m3": 0.18,
        "surface_pressure_hpa": 890,
        "time": "2026-07-08T12:00",
        "source": "open-meteo",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def patch_openmeteo(monkeypatch):
    async def fake_current(lat, lon, model="best_match"):
        return _sample(location={"lat": lat, "lon": lon})

    async def fake_forecast(lat, lon, days=7, model="best_match"):
        return {
            "location": {"lat": lat, "lon": lon},
            "days": [
                {
                    "date": "2026-07-08",
                    "temp_max_c": 30,
                    "temp_min_c": 18,
                    "precipitation_mm": 0,
                    "et0_mm": 4.1,
                    "wind_max_ms": 3.0,
                },
                {
                    "date": "2026-07-09",
                    "temp_max_c": 31,
                    "temp_min_c": 19,
                    "precipitation_mm": 1,
                    "et0_mm": 4.0,
                    "wind_max_ms": 4.0,
                },
            ][:days],
            "source": "open-meteo",
            "model": model,
        }

    async def fake_historical(lat, lon, start_date, end_date):
        return {
            "location": {"lat": lat, "lon": lon},
            "range": {"start": start_date, "end": end_date},
            "days": [
                {
                    "date": start_date,
                    "temp_max_c": 29,
                    "temp_min_c": 17,
                    "precipitation_mm": 0,
                    "et0_mm": 3.9,
                }
            ],
            "source": "open-meteo-archive",
            "model": "ERA5",
        }

    async def fake_tile(lat, lon, time_key="now", model="best_match"):
        return _sample(location={"lat": lat, "lon": lon}, time_key=time_key, model=model)

    monkeypatch.setattr(main, "fetch_current", fake_current)
    monkeypatch.setattr(main, "fetch_forecast", fake_forecast)
    monkeypatch.setattr(main, "fetch_historical", fake_historical)
    monkeypatch.setattr(main, "fetch_tile_sample", fake_tile)


def test_p3_1_weather_core_runtime_contract_and_endpoints():
    client = TestClient(main.app)
    contract = client.get("/contract").json()
    assert contract["implemented_runtime"] is True
    assert "current-weather" in contract["capabilities"]["p3_1_core"]

    current = client.get("/v1/weather/current?lat=15&lon=44").json()
    assert current["source"] == "open-meteo"
    assert current["temperature_c"] == 24.0

    forecast = client.get("/v1/weather/forecast?lat=15&lon=44&days=2").json()
    assert len(forecast["days"]) == 2

    historical = client.get(
        "/v1/weather/historical?lat=15&lon=44&start_date=2026-07-01&end_date=2026-07-02"
    ).json()
    assert historical["model"] == "ERA5"


def test_p3_2_operation_windows_and_plan_are_runtime_backed():
    client = TestClient(main.app)
    window = client.get(
        "/v1/weather/operation-window?lat=15&lon=44&operation=spraying&hours=0,1,3"
    ).json()
    assert window["source"] == "open-meteo+sahool-rules"
    assert window["best"]["operation"]["suitability"] in {"optimal", "acceptable", "poor", "unsafe"}
    assert len(window["frames"]) == 3

    plan = client.get(
        "/v1/weather/operation-plan?lat=15&lon=44&operations=spraying,harvesting&hours=0,1"
    ).json()
    assert plan["top_recommendation"]
    assert {item["operation"] for item in plan["operations"]} == {"spraying", "harvesting"}


def test_p3_3_tile_data_operation_tile_series_and_wind_grid():
    client = TestClient(main.app)
    tile = client.get("/v1/weather/tile-data/6/39/27?layer=wind&interpolation=grid").json()
    assert tile["layer"] == "wind"
    assert tile["rendered_by"] == "sahool-client-gridlayer"
    assert tile["interpolation"]["mode"] == "grid"
    assert len(tile["interpolation"]["points"]) == 5

    op_tile = client.get("/v1/weather/operation-tile-data/6/39/27?operation=spraying").json()
    assert op_tile["layer"] == "operation_spraying"
    assert 0 <= op_tile["value"] <= 1

    series = client.get("/v1/weather/tile-series/6/39/27?layer=temperature&hours=0,1,3").json()
    assert len(series["frames"]) == 3

    wind_grid = client.get("/v1/weather/wind-grid/6/39/27").json()
    assert wind_grid["layer"] == "wind"
    assert wind_grid["wind_grid"]["mode"] == "grid"
