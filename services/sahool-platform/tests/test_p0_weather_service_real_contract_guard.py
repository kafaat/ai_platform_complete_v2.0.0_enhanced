from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_weather_service_has_real_runtime_endpoints_not_501_stub():
    text = (ROOT / "services" / "weather-service" / "main.py").read_text(encoding="utf-8", errors="ignore")
    for marker in [
        '@app.get("/v1/weather/current")',
        '@app.get("/v1/weather/forecast")',
        '@app.get("/v1/weather/operation-window")',
        '@app.get("/v1/weather/tile-data/{z}/{x}/{y}")',
        '@app.get("/v1/weather/wind-grid/{z}/{x}/{y}")',
    ]:
        assert marker in text
    assert "status_code=501" not in text
    assert "not implemented" not in text.lower()


def test_field_intelligence_weather_adapter_uses_weather_service_not_openmeteo_directly():
    text = (ROOT / "services" / "sahool-platform" / "core" / "field_intelligence_adapters.py").read_text(encoding="utf-8", errors="ignore")
    assert "/v1/weather/current" in text
    assert "/v1/weather/forecast" in text
    assert "api.open-meteo.com" not in text
    assert "OPENMETEO_FORECAST_URL" not in text


def test_weather_service_real_contract_gate_is_wired_in_ci():
    workflow = (ROOT / ".github" / "workflows" / "field-workspace-production-closure.yml").read_text(encoding="utf-8", errors="ignore")
    assert "weather_service_real_contract_gate.py" in workflow
    assert "services/weather-service/requirements.txt" in workflow
