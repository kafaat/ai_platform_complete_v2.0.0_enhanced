"""api/device_models.py — نماذج أجهزة IoT والقياسات (Devices & Telemetry)
=========================================================================
كتلة نماذج «الأجهزة» المستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

مكتفية ذاتيّاً: ``pydantic`` + المكتبة القياسيّة فقط، بلا أيّ اعتماد على رموز
أخرى من ``api.main``. مستهلِكها الوحيد ``api/routers/devices.py``. النماذج
منسوخة حرفيّاً للحفاظ على السلوك/مخطّط OpenAPI دون تغيير.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── أجهزة IoT (سجلّ + صحّة + telemetry) — الطبقة ٤ (v24) ─────────
class DeviceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(soil_moisture|weather_station|water_meter|camera|actuator|other)$")
    field_id: str | None = None
    firmware_version: str | None = None


class TelemetryRequest(BaseModel):
    sensor_type: str = Field(min_length=1, max_length=40)
    value: float
    unit: str | None = None
    recorded_at: str | None = None  # ISO datetime اختياري (افتراض: الآن)


_DEVICE_ONLINE_WINDOW_MIN = 15  # جهاز يُعتبر online إن ظهر خلال هذه المدّة


def telemetry_freshness(recorded_at, now, window_min: int = _DEVICE_ONLINE_WINDOW_MIN) -> dict:
    """عمر القراءة وكونها قديمة — يُحسَب في الخادم بالنافذة نفسها التي تحكم «online».

    العطلُ الذي وُجد هذا لأجله (2026-11-02): ``GET /devices/{id}/telemetry`` كان يعيد القيمة
    ووقتها فقط، والواجهة تعرضها «قراءات حيّة»؛ فقراءةٌ عمرها يومان تُقرأ كأنّها الآن.
    بلا وقت قراءة ⇒ ``stale: True`` و``age_sec: None`` (لا نفترض حداثةً لا نعرفها). وقتٌ في
    المستقبل (انحراف ساعة الجهاز) ⇒ عمرٌ صفر، لا عمرٌ سالب.
    """
    if recorded_at is None:
        return {"age_sec": None, "stale": True, "stale_after_sec": window_min * 60}
    age = max(0, int((now - recorded_at).total_seconds()))
    return {"age_sec": age, "stale": age > window_min * 60, "stale_after_sec": window_min * 60}
