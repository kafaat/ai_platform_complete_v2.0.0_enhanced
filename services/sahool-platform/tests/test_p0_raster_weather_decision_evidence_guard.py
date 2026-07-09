from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"
WEATHER_MAIN = ROOT / "services" / "weather-service" / "main.py"
WEATHER_CLIENT = ROOT / "services" / "sahool-platform" / "api" / "weather_service_client.py"
WEATHER_ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "weather.py"
DECISION_MAIN = ROOT / "services" / "decision-service" / "main.py"
LAYER_REGISTRY = FRONTEND / "lib" / "layerRegistry.ts"
SETTINGS_PAGE = FRONTEND / "sections" / "SettingsPage.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_weather_service_is_runtime_not_documented_as_501_stub() -> None:
    """Weather-service must not regress to the old stub+platform-fallback narrative."""
    main = _read(WEATHER_MAIN)
    assert '"implemented_runtime": True' in main
    for route in (
        '@app.get("/v1/weather/current")',
        '@app.get("/v1/weather/forecast")',
        '@app.get("/v1/weather/historical")',
        '@app.get("/v1/weather/operation-window")',
        '@app.get("/v1/weather/tile-data/{z}/{x}/{y}")',
        '@app.get("/v1/weather/wind-grid/{z}/{x}/{y}")',
    ):
        assert route in main, route

    stale_claims = []
    for path in (FRONTEND / "hooks" / "useApi.ts", FRONTEND / "services" / "api.ts"):
        text = _read(path)
        if "weather-service جذعي" in text or "501 لأيّ مسار طقس" in text:
            stale_claims.append(str(path.relative_to(ROOT)))
    assert stale_claims == [], "stale weather-service stub comments remain: " + repr(stale_claims)


def test_platform_weather_is_bff_over_weather_service_not_duplicate_provider_logic() -> None:
    client = _read(WEATHER_CLIENT)
    router = _read(WEATHER_ROUTER)
    assert "weather-service owns provider calls" in client
    assert "weather_get_json" in client
    assert "get_current_weather" in router
    assert "get_weather_forecast" in router
    assert "get_weather_historical" in router
    assert "BFF facade: weather-service owns" in router


def test_decision_service_is_honest_non_authoritative_until_sor_migration() -> None:
    text = _read(DECISION_MAIN)
    assert "persisted: false" in text or '"persisted": False' in text
    assert "authoritative" in text
    assert "False" in text or "false" in text
    # persisted=True is allowed only after the explicit SoR gate proves a real DB write.
    if '"persisted": True' in text:
        assert "if sor_enabled():" in text
        assert "await persist_decision_record" in text
        assert "DECISION_SERVICE_SOR_ENABLED" in text
        assert "DATABASE_URL" in text
    assert "persisted: true" not in text
    assert "sahool-platform" in text
    assert "non-authoritative" in text or "best-effort mirror" in text


def test_raster_layer_contract_declares_backfill_availability_and_fallback() -> None:
    text = _read(LAYER_REGISTRY)
    for field in ("sourceService", "requiresBackfill", "availabilityEndpoint", "fallbackLayerId"):
        assert field in text
    assert "id: 'truecolor'" in text
    assert "sourceService: 'raster-service'" in text
    assert "requiresBackfill: true" in text
    assert "availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates'" in text
    assert "fallbackLayerId: 'satellite'" in text
    assert "layersRequiringBackfill" in text
    assert "requiresLayerAvailabilityCheck" in text


def test_settings_page_no_longer_hardcodes_weather_service_as_down() -> None:
    text = _read(SETTINGS_PAGE)
    assert "weather-service (:8092)',  ok:false" not in text
    assert "weather-service (:8092)" in text
