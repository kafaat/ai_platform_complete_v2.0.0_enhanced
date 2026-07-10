"""Guard: the field thermal-stress weather facade is wired to a real producer.

يضمن أنّ منتج الإجهاد الحراريّ له **مستهلِك حقيقيّ** (façade حول field_id) يستدعي
weather-service عبر العميل، لا نقطة يتيمة. صدق الحدود: الحساب في weather-service،
والمنصّة تستهلك فقط.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_client_exposes_thermal_stress_call():
    client = _read("services/sahool-platform/api/weather_service_client.py")
    assert "async def get_thermal_stress(" in client
    assert '"/v1/weather/thermal-stress"' in client


def test_field_facade_consumes_thermal_stress_producer():
    facade = _read("services/sahool-platform/api/routers/field_workspace_weather.py")
    assert '@router.get("/api/v1/fields/{field_id}/weather/thermal-stress")' in facade
    assert "get_thermal_stress(" in facade
    # يمرّر المحصول/المرحلة من سياق الحقل (شرط التصنيف المشروط).
    assert "crop=crop" in facade and "stage=stage" in facade


def test_producer_endpoint_registered_in_weather_service():
    main = _read("services/weather-service/main.py")
    assert 'app.get("/v1/weather/thermal-stress")(rt.thermal_stress)' in main


def test_producer_is_fail_closed_and_supporting():
    src = _read("services/weather-service/thermal_stress.py")
    assert '"status": "insufficient_context"' in src  # fail-closed
    assert '"evidence_role": "supporting"' in src  # لا حجب قبل المعايرة
    assert "estimated_not_measured" in src  # صدق رطوبة الأوراق
