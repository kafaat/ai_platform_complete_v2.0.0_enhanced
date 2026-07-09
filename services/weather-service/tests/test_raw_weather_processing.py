from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

main = importlib.import_module("main")


def test_raw_weather_current_process_is_provenance_only(monkeypatch):
    async def fake_current(lat, lon, model="best_match"):
        return {
            "location": {"lat": lat, "lon": lon},
            "temperature_c": 25.5,
            "humidity_pct": 60,
            "wind_speed_ms": 2.5,
            "source": "open-meteo",
            "model": model,
        }

    monkeypatch.setattr(main, "fetch_current", fake_current)
    client = TestClient(main.app)
    response = client.post(
        "/v1/weather/raw/process",
        json={"lat": 15, "lon": 44, "source_kind": "current", "include_payload": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "weather-service"
    assert payload["source_kind"] == "current"
    assert payload["flags"]["raw_data_processing"] is True
    assert payload["flags"]["fabricated_weather"] is False
    assert payload["flags"]["operation_window_computed"] is False
    assert payload["flags"]["indicator_computed"] is False
    assert payload["raw_payload"]["temperature_c"] == 25.5
    assert payload["numeric_summary"]["temperature_c"]["count"] == 1


def test_raw_weather_forecast_summarizes_nested_days(monkeypatch):
    async def fake_forecast(lat, lon, days=7, model="best_match"):
        return {
            "location": {"lat": lat, "lon": lon},
            "days": [
                {"date": "2026-07-09", "temp_max_c": 30, "precipitation_mm": 0},
                {"date": "2026-07-10", "temp_max_c": 32, "precipitation_mm": 2},
            ][:days],
            "source": "open-meteo",
            "model": model,
        }

    monkeypatch.setattr(main, "fetch_forecast", fake_forecast)
    client = TestClient(main.app)
    response = client.post(
        "/v1/weather/raw/process",
        json={"lat": 15, "lon": 44, "source_kind": "forecast", "days": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_observation_count"] == 2
    assert payload["raw_payload"] is None
    assert payload["numeric_summary"]["days.temp_max_c"]["max"] == 32
    assert payload["provenance"]["raw_payload_included"] is False


def test_raw_weather_historical_requires_dates():
    client = TestClient(main.app)
    response = client.post(
        "/v1/weather/raw/process",
        json={"lat": 15, "lon": 44, "source_kind": "historical"},
    )
    assert response.status_code == 422
