from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEATHER_SERVICE = ROOT / "services" / "weather-service"
MAIN = WEATHER_SERVICE / "main.py"
RUNTIME = WEATHER_SERVICE / "weather_runtime.py"  # P2 shell: المنطق هنا
REQ = WEATHER_SERVICE / "requirements.txt"


def test_p3_1_weather_service_core_is_real_not_stub():
    text = MAIN.read_text(encoding="utf-8", errors="ignore") + RUNTIME.read_text(
        encoding="utf-8", errors="ignore"
    )
    assert '"implemented_runtime": True' in text
    assert 'app.get("/v1/weather/current")' in text
    assert 'app.get("/v1/weather/forecast")' in text
    assert 'app.get("/v1/weather/historical")' in text
    assert "not_implemented_here" not in text


def test_p3_2_operation_window_runtime_exists():
    text = MAIN.read_text(encoding="utf-8", errors="ignore") + RUNTIME.read_text(
        encoding="utf-8", errors="ignore"
    )
    assert 'app.get("/v1/weather/operation-window")' in text
    assert 'app.get("/v1/weather/operation-plan")' in text
    assert 'app.get("/v1/weather/operation-tile-data/{z}/{x}/{y}")' in text
    assert "operation_suitability" in text


def test_p3_3_tiles_and_wind_grid_runtime_exists():
    text = MAIN.read_text(encoding="utf-8", errors="ignore") + RUNTIME.read_text(
        encoding="utf-8", errors="ignore"
    )
    assert 'app.get("/v1/weather/tile-data/{z}/{x}/{y}")' in text
    assert 'app.get("/v1/weather/tile-series/{z}/{x}/{y}")' in text
    assert 'app.get("/v1/weather/wind-grid/{z}/{x}/{y}")' in text
    assert "sahool-client-gridlayer" in text


def test_weather_service_runtime_dependencies_include_httpx():
    req = REQ.read_text(encoding="utf-8", errors="ignore")
    assert "httpx" in req
