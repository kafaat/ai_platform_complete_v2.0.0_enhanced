#!/usr/bin/env python3
"""Weather-service real-runtime contract gate.

Prevents regression to the old "stub + platform fallback" pattern:
- weather-service must expose real runtime endpoints, not 501 placeholders;
- provider calls/cache/tile/operation logic must live in services/weather-service;
- sahool-platform weather endpoints stay thin BFF facades to weather_service_client;
- field-intelligence adapters must not call Open-Meteo directly;
- local scripts must probe /healthz, not stale /health or WOFOST labels.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEATHER = ROOT / "services" / "weather-service"
PLATFORM = ROOT / "services" / "sahool-platform"

REQUIRED_SERVICE_MARKERS = [
    '@app.get("/v1/weather/current")',
    '@app.get("/v1/weather/forecast")',
    '@app.get("/v1/weather/historical")',
    '@app.get("/v1/weather/operation-window")',
    '@app.get("/v1/weather/operation-plan")',
    '@app.get("/v1/weather/tile-data/{z}/{x}/{y}")',
    '@app.get("/v1/weather/wind-grid/{z}/{x}/{y}")',
    'source": "open-meteo+sahool-rules"',
]


def fail(msg: str) -> None:
    raise SystemExit(f"✗ {msg}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_weather_service_runtime_source() -> None:
    main = read(WEATHER / "main.py")
    missing = [m for m in REQUIRED_SERVICE_MARKERS if m not in main]
    if missing:
        fail("weather-service missing real runtime markers: " + repr(missing))
    forbidden = ["HTTPException(status_code=501", "status_code=501", "not implemented", "TODO stub"]
    found = [m for m in forbidden if m.lower() in main.lower()]
    if found:
        fail("weather-service main.py contains stub/not-implemented markers: " + repr(found))
    provider = read(WEATHER / "open_meteo.py")
    for marker in ["httpx.AsyncClient", "api.open-meteo.com/v1/forecast", "archive-api.open-meteo.com/v1/archive", "et0_fao_evapotranspiration"]:
        if marker not in provider:
            fail(f"weather-service provider adapter missing {marker!r}")
    print("✓ weather-service runtime/provider source is real, not 501 stub")


def check_platform_is_thin_facade() -> None:
    router = read(PLATFORM / "api" / "routers" / "weather.py")
    required_calls = [
        "return await get_current_weather(lat, lon)",
        "return await get_weather_forecast(lat, lon, days=days)",
        "return await get_weather_historical(lat, lon, start_date=start_date, end_date=end_date)",
        "return await get_weather_tile_data(",
        "return await get_operation_tile_data(",
    ]
    missing = [m for m in required_calls if m not in router]
    if missing:
        fail("platform weather BFF no longer delegates to weather_service_client: " + repr(missing))
    client = read(PLATFORM / "api" / "weather_service_client.py")
    for marker in ["DEFAULT_WEATHER_SERVICE_URL", "sahool-weather-service", "weather_get_json", "/v1/weather/current", "/v1/weather/forecast"]:
        if marker not in client:
            fail(f"weather_service_client missing {marker!r}")
    print("✓ sahool-platform weather routes are thin weather-service facades")


def check_no_field_intelligence_openmeteo_fallback() -> None:
    adapters = read(PLATFORM / "core" / "field_intelligence_adapters.py")
    forbidden = ["api.open-meteo.com", "OPENMETEO_FORECAST_URL", "resp = client.get(OPENMETEO"]
    found = [m for m in forbidden if m in adapters]
    if found:
        fail("field_intelligence_adapters still calls Open-Meteo directly: " + repr(found))
    required = ["/v1/weather/current", "/v1/weather/forecast", "WEATHER_SERVICE_URL"]
    missing = [m for m in required if m not in adapters]
    if missing:
        fail("field_intelligence_adapters does not use weather-service endpoints: " + repr(missing))
    print("✓ field-intelligence adapters use weather-service, not direct Open-Meteo fallback")


def check_compose_and_local_scripts() -> None:
    compose_text = "\n".join(read(p) for p in ROOT.glob("docker-compose*.yml"))
    if "WEATHER_SERVICE_URL" not in compose_text or "sahool-weather-service:8000" not in compose_text:
        fail("compose files do not wire WEATHER_SERVICE_URL to sahool-weather-service internal port")
    local_scripts = "\n".join(read(p) for p in [ROOT / "frontend" / "run_all.sh", ROOT / "frontend" / "run_all.ps1"] if p.exists())
    forbidden = ["localhost:8092/health'", "localhost:8092/health ", "weather-service (WOFOST)", "8092:/health:"]
    found = [m for m in forbidden if m in local_scripts]
    if found:
        fail("local weather probes still use stale /health or WOFOST labels: " + repr(found))
    if "localhost:8092/healthz" not in local_scripts:
        fail("local scripts must probe weather-service /healthz")
    print("✓ compose/local scripts use the real weather-service runtime contract")


def check_runtime_contract_with_testclient() -> None:
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # pragma: no cover
        fail(f"fastapi TestClient unavailable; install weather-service requirements: {exc}")

    sys.path.insert(0, str(WEATHER))
    spec = importlib.util.spec_from_file_location("sahool_weather_service_main", WEATHER / "main.py")
    if not spec or not spec.loader:
        fail("unable to import weather-service main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    async def fake_current(lat: float, lon: float, *, model: str = "best_match"):
        return {"location": {"lat": lat, "lon": lon}, "temperature_c": 28.0, "source": "open-meteo", "time": "2026-07-09T00:00"}

    async def fake_forecast(lat: float, lon: float, *, days: int = 7, model: str = "best_match"):
        return {"location": {"lat": lat, "lon": lon}, "source": "open-meteo", "daily": [{"date": "2026-07-09", "et0_mm": 5.1}]}

    module.fetch_current = fake_current
    module.fetch_forecast = fake_forecast

    async def fake_readiness_probe(lat: float = 15.3694, lon: float = 44.1910):
        return {"ok": True, "provider": "open-meteo", "time": "2026-07-09T00:00", "circuit_breaker": {"state": "closed"}}

    module.readiness_probe = fake_readiness_probe
    client = TestClient(module.app)
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz").json()
    assert ready["implemented_runtime"] is True
    assert ready["upstream_open_meteo"]["ok"] is True
    assert "circuit_breaker" in ready
    contract = client.get("/contract").json()
    assert contract["implemented_runtime"] is True
    assert "current-weather" in contract["capabilities"]["p3_1_core"]
    current = client.get("/v1/weather/current?lat=15.4&lon=44.2").json()
    assert current["source"] == "open-meteo"
    forecast = client.get("/v1/weather/forecast?lat=15.4&lon=44.2&days=3").json()
    assert forecast["daily"][0]["et0_mm"] == 5.1
    print("✓ weather-service runtime contract works under TestClient without network")


def main() -> None:
    check_weather_service_runtime_source()
    check_platform_is_thin_facade()
    check_no_field_intelligence_openmeteo_fallback()
    check_compose_and_local_scripts()
    check_runtime_contract_with_testclient()
    print("✓ Weather-service real runtime contract gate passed")


if __name__ == "__main__":
    main()
