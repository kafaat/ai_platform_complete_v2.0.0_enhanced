"""api/device_models.py — نماذج أجهزة IoT والقياسات (Devices & Telemetry)
=========================================================================
كتلة نماذج «الأجهزة» المستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

مكتفية ذاتيّاً: ``pydantic`` + المكتبة القياسيّة فقط، بلا أيّ اعتماد على رموز
أخرى من ``api.main``. مستهلِكها الوحيد ``api/routers/devices.py``. النماذج
منسوخة حرفيّاً للحفاظ على السلوك/مخطّط OpenAPI دون تغيير.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── أجهزة IoT (سجلّ + صحّة + telemetry) — الطبقة ٤ (v24) ─────────
class DeviceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(soil_moisture|weather_station|water_meter|camera|actuator|other)$")
    field_id: str | None = None
    firmware_version: str | None = None


class TelemetryRequest(BaseModel):
    sensor_type: str = Field(min_length=1, max_length=40)
    # قياسٌ عدديّ محدود: NaN/±inf و`true`/`false` ليست قراءات (`float(True) == 1.0` كانت
    # تصير قراءةَ رطوبة 1٪). الأعدادُ الصحيحة تبقى مقبولة (`21` ⇒ `21.0`).
    value: float = Field(allow_inf_nan=False)
    unit: str | None = None
    recorded_at: str | None = None  # ISO datetime اختياري (افتراض: الآن)
    # عمقُ القياس ومعايرتُه **كما يعلنها الجهاز** (اختياريّة): تُمرَّر إلى شاهد التربة
    # القانونيّ حين تُعلَن، ولا تُخمَّن حين تغيب.
    depth_from_cm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    depth_to_cm: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    calibration_id: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("value", "depth_from_cm", "depth_to_cm", mode="before")
    @classmethod
    def _reject_boolean(cls, v):
        if isinstance(v, bool):
            raise ValueError("boolean is not a measurement")
        return v

    @model_validator(mode="after")
    def _depth_pair(self) -> TelemetryRequest:
        if (self.depth_from_cm is None) != (self.depth_to_cm is None):
            raise ValueError("depth_from_cm and depth_to_cm must be given together")
        if self.depth_from_cm is not None and self.depth_to_cm <= self.depth_from_cm:
            raise ValueError("depth_to_cm must be greater than depth_from_cm")
        return self


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
