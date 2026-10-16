"""api/irrigation_models.py — نماذج/مساعِدات الريّ التشغيليّ (صمامات + جداول).

شريحة من تفكيك ``api/main.py`` (نمط B1): النماذج (``ValveRequest`` /
``ValveStateRequest`` / ``ScheduleRequest``) والمساعِد ``_parse_time`` نُقِلت
حرفيّاً إلى هنا. self-contained: pydantic فقط للنماذج، و``datetime`` +
``fastapi.HTTPException`` لـ``_parse_time``. يستوردها ``api.routers.irrigation``.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

# منطق نقيّ (v29.5-op-2/3) مُستخرَج إلى وحدة بلا fastapi كي يُختبَر في طبقة الوحدة؛
# يُعاد تصديره هنا فيبقى api.routers.irrigation يستورده من irrigation_models كما هو.
from api.irrigation_engineering_workspace import ManualIrrigationIntent
from api.irrigation_logic import (  # noqa: F401  (re-export)
    plan_run_ledger_action,
    schedules_overlap,
)


class ValveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    device_id: str | None = None
    valve_type: str = Field(default="solenoid", pattern="^(solenoid|manual|drip_header|gate)$")
    flow_rate_lpm: float | None = Field(default=None, ge=0)


class ValveStateRequest(BaseModel):
    status: str = Field(pattern="^(open|closed)$")
    # اختياريّان (v29.5-op-2): إن حملتهما الحمولة عند الإغلاق يُدوَّن حجم ماء التشغيل
    # في irrigation_runs، وإلّا NULL (لا تلفيق). إضافيّان متوافقان مع القديم.
    volume_l: float | None = Field(default=None, ge=0)
    volume_mm: float | None = Field(default=None, ge=0)


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    valve_id: str | None = None
    start_time: str  # HH:MM أو HH:MM:SS
    duration_min: int = Field(ge=1, le=1440)
    days_of_week: list[int] | None = None
    water_target_mm: float | None = Field(default=None, ge=0)
    enabled: bool = True


def _parse_time(value: str):
    """يحوّل HH:MM[:SS] إلى time؛ 400 على قيمة غير صالحة (لا 500)."""
    from datetime import time as _time

    try:
        return _time.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400, detail="start_time غير صالح — استخدم HH:MM أو HH:MM:SS"
        ) from None


class IrrigationRecommendationRequest(BaseModel):
    crop: str | None = None
    stage: str = "mid"  # initial|development|mid|late
    t_min_c: float
    t_max_c: float
    # **إلزاميّتان بلا افتراضٍ صفريّ.** عميلٌ يُغفِلهما كان يحصل على توصيةٍ محسوبةٍ على
    # «لا مطر» بلا أن يعلم — وهو الانحياز الذي يُغرِق. الحذفُ الآن ⇒ ٥٠٣ صريحة.
    rain_recent_mm: float | None = None
    forecast_rain_mm: float | None = None
    soil_moisture_pct: float | None = None
    kc_override: float | None = None  # Kc دقيق من الفينولوجيا إن توفّر
    # طقس Penman-Monteith (اختياريّ — يسقط إلى Hargreaves عند الغياب)
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    latitude_deg: float = 15.5
    elevation_m: float = 2000.0
    day_of_year: int = 100
    # ── مدخلات الملوحة (فحص مخبريّ) ──
    soil_ece: float | None = None  # ECe من soil_lab_tests
    soil_ec_age_days: int | None = None  # عُمر الفحص (للموثوقيّة)
    crop_salt_tolerance_ece: float | None = None  # عتبة المحصول (FAO-56 T23)
    salt_slope_pct: float | None = None
    # ── مدخلات الغسل (مشروطة) ──
    water_ec: float | None = None  # ECw ماء الريّ
    drainage: str | None = None  # fast|medium|slow
    irrigation_efficiency: float | None = None
    # ── مدخلات الإجهاد المائيّ (استنزاف منطقة الجذور) — تقود قرار الإطلاق ──
    depletion_mm: float | None = None  # Dr من water_ledger عبر الحالة الكنسيّة
    taw_mm: float | None = None  # TAW من soil_water_params
    raw_fraction: float = 0.5  # p (FAO-56)
    water_stress_class: str | None = None  # normal|watch|critical (canonical)
    policy: str | None = None  # water_saving|yield_max|profit_max|sustainability|risk_averse
    water_price_per_m3: float | None = None  # لـ profit_max
    yield_value_per_ha: float | None = None  # لـ profit_max


class FieldIrrigationRequest(BaseModel):
    """المسار الأساسيّ: الطقس يُجلَب آليّاً من محرّك الطقس (WS-D.2c). الحرارة اختياريّة
    كتجاوز يدويّ فقط — لا كمسار أساسيّ. الاستنزاف/TAW/التربة تُقرأ آليّاً من حالة الحقل."""

    # تجاوز يدويّ اختياريّ (ليس المسار الأساسيّ) — None ⇒ جلب تلقائيّ من المحرّك.
    t_min_c: float | None = None
    t_max_c: float | None = None
    solar_rad_mj_m2: float | None = None
    rh_mean_pct: float | None = None
    wind_2m_ms: float | None = None
    day_of_year: int | None = None
    root_depth_m: float | None = None  # عمق الجذور (لاشتقاق TAW)؛ None ⇒ افتراضيّ موسوم
    policy: str | None = None  # سياسة الريّ (water_saving افتراضاً)
    water_price_per_m3: float | None = None
    # مطرُ التجاوز اليدويّ — يُقرأ **فقط** مع تجاوز الحرارة. المسارُ الأساسيّ يجلبه من
    # المحرّك، وغيابُه في التجاوز ⇒ ``dependency_unavailable`` لا صفر.
    rain_recent_mm: float | None = None
    forecast_rain_mm: float | None = None
    # WS-D.2d: تقديم صريح للمرشَّح إلى خدمة القرار (لا تلقائيّ — احترام حوكمة الموافقة).
    submit_to_decision: bool = False
    yield_value_per_ha: float | None = None
    manual_execution: ManualIrrigationIntent | None = None

    def has_manual_evidence_overrides(self) -> bool:
        return any(
            getattr(self, key) is not None
            for key in (
                "t_min_c",
                "t_max_c",
                "root_depth_m",
                "rain_recent_mm",
                "forecast_rain_mm",
                "solar_rad_mj_m2",
                "rh_mean_pct",
                "wind_2m_ms",
                "day_of_year",
            )
        )
