from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_nginx_exposes_exact_legacy_health_aliases():
    conf = read("nginx/nginx.v9.conf")
    assert "location = /api/indicators/readyz" in conf
    assert "proxy_pass http://indicators_backend/readyz" in conf
    assert "location = /api/weather/readyz" in conf
    assert "proxy_pass http://weather_backend/readyz" in conf
    assert "location = /api/vegetation/readyz" in conf
    assert "proxy_pass http://vegetation_backend/readyz" in conf


def test_platform_has_fallbacks_for_misrouted_legacy_health_and_vegetation_paths():
    src = read("services/sahool-platform/api/main.py")
    for route in [
        '@app.get("/api/indicators/readyz")',
        '@app.get("/api/weather/readyz")',
        '@app.get("/api/vegetation/readyz")',
        '@app.get("/api/agent/health")',
        '@app.get("/api/vegetation/v1/all_fields")',
        '@app.get("/api/vegetation/v1/analyze")',
    ]:
        assert route in src
    assert "VEGETATION_SERVICE_URL" in src
    assert "/v1/all_fields" in src
    assert "/v1/analyze" in src


def test_field_indicator_map_shows_availability_status_before_user_clicks_tiles():
    src = read("frontend/src/components/FieldIndicatorMap.tsx")
    assert 'aria-label="indicator availability status"' in src
    assert "جاري التحقق" in src
    assert "غير متاح" in src
    assert "متاح:" in src
    assert "tileUnavailableMessage" in src
    assert "user_message" in src
    assert "reason" in src
