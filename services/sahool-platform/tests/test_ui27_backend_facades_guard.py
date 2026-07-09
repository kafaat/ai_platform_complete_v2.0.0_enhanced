from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_ui27_imagery_backend_facade_exists_before_fields_and_uses_raster_service_only():
    src = read("services/sahool-platform/api/routers/field_workspace_imagery.py")
    registry = read("services/sahool-platform/api/router_registry.py")
    assert "field_workspace_imagery.py" in src or "Field Workspace imagery façade" in src
    assert '@router.get("/api/v1/fields/{field_id}/available-dates")' in src
    assert '@router.get("/api/v1/fields/{field_id}/imagery/timeline")' in src
    assert "get_available_dates" in src
    assert "thumbnail_url" in src
    assert "cdse-thumbnail.png" in src
    assert "OBSERVATION_RECORD" in src
    assert "demo" not in src.lower()
    assert "pkgutil.iter_modules" in registry  # auto-registration keeps new facade wired


def test_ui27_weather_backend_facade_adds_field_operation_windows_and_no_frontend_latlon_leak():
    src = read("services/sahool-platform/api/routers/field_workspace_weather.py")
    frontend = read("frontend/src/services/api/fieldWeather.ts")
    assert '@router.get("/api/v1/fields/{field_id}/weather/operation-windows")' in src
    assert "get_operation_plan" in src
    assert "_field_weather_context" in src
    assert "lat, lon" in src
    assert "weather-service" in src
    assert "spraying,irrigation,harvesting,sowing,fertilizing" in src
    assert "لا يتم حساب النوافذ في المتصفح" in src
    assert "/api/v1/fields/${fieldId}/weather/operation-windows" in frontend
    assert (
        "lat"
        not in frontend.split("getFieldWeatherOperationWindows", 1)[1].split("): Promise", 1)[0]
    )


def test_ui27_weather_facade_preserves_disease_and_irrigation_field_endpoints():
    src = read("services/sahool-platform/api/routers/field_workspace_weather.py")
    assert '@router.get("/api/v1/fields/{field_id}/weather/irrigation-advice")' in src
    assert '@router.get("/api/v1/fields/{field_id}/weather/disease-risk")' in src
    assert "irrigation_advice" in src
    assert "disease_risk" in src
    assert "fetch_daily_forecast" in src
    assert "fetch_current" in src
    assert "Open-Meteo" in src


def test_ui27_irrigation_schedules_are_field_owner_checked_and_not_generated_in_frontend():
    router = read("services/sahool-platform/api/routers/irrigation.py")
    api = read("frontend/src/services/api/fieldIrrigation.ts")
    assert '@router.get("/api/v1/irrigation/schedules")' in router
    assert "await _assert_field_in_tenant(conn, field_id)" in router
    assert '_db_unavailable("قراءة جداول الري"' in router
    assert (
        "لا توجد\n    جداول افتراضية" in router
        or "لا توجد" in router
        and "جداول افتراضية" in router
    )
    assert "kongApi.get<FieldIrrigationSchedule[]>('/api/v1/irrigation/schedules'" in api
    assert "params: { field_id: fieldId }" in api
