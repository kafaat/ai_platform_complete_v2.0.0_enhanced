from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_ui24_imagery_api_and_panel_use_real_capture_dates_without_demo_fallback():
    api = read("frontend/src/services/api/fieldImagery.ts")
    panel = read("frontend/src/sections/FieldWorkspaceImageryPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    facade = read("frontend/src/services/api.ts")
    assert "getFieldImageryAvailableDates" in api
    assert "/api/v1/fields/${fieldId}/available-dates" in api
    assert "getFieldImageryTimeline" in api
    assert "/api/v1/fields/${fieldId}/imagery/timeline" in api
    assert "acquisition_datetime" in api
    assert "truecolor" in panel
    assert "formatAcquisition" in panel
    assert "لا يتم توليد صور أو تواريخ من الواجهة" in panel
    assert "صور demo" in panel
    assert "<FieldWorkspaceImageryPanel fieldId={fieldId}" in route
    assert "export * from './api/fieldImagery'" in facade


def test_ui25_weather_panel_has_operation_windows_and_disease_risk_states():
    api = read("frontend/src/services/api/fieldWeather.ts")
    panel = read("frontend/src/sections/FieldWorkspaceWeatherPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    facade = read("frontend/src/services/api.ts")
    assert "getFieldWeatherOperationWindows" in api
    assert "/api/v1/fields/${fieldId}/weather/operation-windows" in api
    assert "getFieldDiseaseRisk" in api
    assert "/api/v1/fields/${fieldId}/weather/disease-risk" in api
    assert "DegradedState" in panel
    assert "status === 401 || status === 403" in panel
    assert "لا تعرض الواجهة توقعات بديلة" in panel
    assert "<FieldWorkspaceWeatherPanel fieldId={fieldId} seasonId={seasonId}" in route
    assert "export * from './api/fieldWeather'" in facade


def test_ui26_irrigation_panel_requires_season_and_never_computes_plan_in_frontend():
    api = read("frontend/src/services/api/fieldIrrigation.ts")
    panel = read("frontend/src/sections/FieldWorkspaceIrrigationPanel.tsx")
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    facade = read("frontend/src/services/api.ts")
    assert "getFieldIrrigationAdvice" in api
    assert "/api/v1/fields/${fieldId}/weather/irrigation-advice" in api
    assert "getFieldIrrigationSchedules" in api
    assert "/api/v1/irrigation/schedules" in api
    assert "enabled: Boolean(fieldId && seasonId)" in panel
    assert "لا يوجد موسم نشط للري" in panel
    assert "لا يتم حساب بدائل من الواجهة" in panel
    assert "لا يتم توليد جدول ري من الواجهة" in panel
    assert "<FieldWorkspaceIrrigationPanel fieldId={fieldId} seasonId={seasonId}" in route
    assert "export * from './api/fieldIrrigation'" in facade


def test_ui24_ui26_placeholders_removed_from_workspace_tabs():
    route = read("frontend/src/sections/FieldWorkspaceRouteShell.tsx")
    assert "function PlaceholderPanel" not in route
    assert "activeTab === 'imagery'" in route
    assert "activeTab === 'weather'" in route
    assert "activeTab === 'irrigation'" in route
    assert "يعرض NDVI/NDMI/TrueColor حسب COG/available-dates الفعلية فقط" not in route
