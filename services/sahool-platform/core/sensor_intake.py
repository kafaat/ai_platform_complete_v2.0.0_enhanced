"""
sahool_core.sensor_intake
==========================
بوّابة استقبال قراءات المستشعرات — تصبّ في `observations` الموجود
لا تُنشئ جدولاً منفصلاً (لا تكرار، لا كسر).

الفجوة المسدودة: مزارع تستخدم حسّاسات (DHT، رطوبة تربة، EC ميداني)
لم يكن لها بوّابة موحّدة للدخول. observations EAV يقبل أي قياس، لكن
بلا تحقّق صحيح: الوحدات، النطاقات، الثقة (حسّاس ≠ مختبر).

المبادئ المحفوظة:
  • الحسّاس قرينة عالية الثقة، لا دليل مخبري (سقف medium افتراضياً)
  • النواة محايدة البروتوكول (لا MQTT broker — JSON/REST يكفيان)
  • التحقّق صارم: نطاق فيزيائي، وحدة، طابع زمني، خط أحمر للجنون
  • الصدق: قراءة معطّلة (None) لا تُخترع — تُرفض بسبب صريح

مستوحى من GitHub (smart-farming, soil-moisture-sensor): تيار JSON
بسيط {device_id, timestamp, type, value, unit}. لا حاجة لاستيراد
بروتوكول كامل — هذه طبقة تحقّق وتحويل خفيفة.

التكامل: ingest_reading() يحوّل القراءة إلى observation جاهز للحفظ
في الجدول الموجود (نمط EAV)، مع source='sensor' وثقة معقّلة.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


# نطاقات فيزيائية معقولة (حسب نوع المستشعر)
# قيمة خارج النطاق = خلل في الحسّاس، لا قياس صحيح
_SENSOR_RANGES = {
    "soil_moisture":      (0.0,   100.0, "%"),      # نسبة مئوية
    "soil_temperature":   (-10.0, 70.0,  "°C"),
    "air_temperature":    (-20.0, 60.0,  "°C"),
    "air_humidity":       (0.0,   100.0, "%"),
    "soil_ec":            (0.0,   30.0,  "dS/m"),
    "soil_ph":            (3.0,   11.0,  "pH"),
    "leaf_wetness":       (0.0,   100.0, "%"),
    "rainfall":           (0.0,   500.0, "mm"),     # يومي
    "solar_radiation":    (0.0,   1400.0, "W/m²"),
    "wind_speed":         (0.0,   60.0,  "m/s"),
}

# ربط نوع المستشعر بـobservable_id في الجدول
_OBSERVABLE_MAP = {
    "soil_moisture": "soil_moisture_vol",
    "soil_temperature": "soil_temp_c",
    "air_temperature": "air_temp_c",
    "air_humidity": "rh_pct",
    "soil_ec": "soil_ec_ds_m",
    "soil_ph": "soil_ph_value",
    "leaf_wetness": "leaf_wetness_pct",
    "rainfall": "rainfall_mm",
    "solar_radiation": "solar_radiation_w_m2",
    "wind_speed": "wind_speed_m_s",
}


@dataclass
class IntakeResult:
    accepted: bool
    observation: dict | None = None   # جاهز للحفظ في observations
    rejection_reason_ar: str | None = None
    warnings_ar: list[str] = field(default_factory=list)


def ingest_reading(
    *,
    tenant_id: str,
    field_id: str,
    sensor_type: str,
    value: float | None,
    unit: str | None = None,
    device_id: str | None = None,
    timestamp_iso: str | None = None,
    lon: float | None = None,
    lat: float | None = None,
) -> IntakeResult:
    """يستقبل قراءة من مستشعر ويُرجعها كـobservation موثوق أو يرفضها بسبب.

    لا اختراع: قيمة None → رفض صريح، لا "صفر افتراضي".
    لا قبول أعمى: قيمة خارج النطاق الفيزيائي → رفض (حسّاس معطّل غالباً).
    سقف الثقة: medium (الحسّاس قرينة قويّة لا دليل مخبري)."""

    # ١. القيمة موجودة؟
    if value is None:
        return IntakeResult(
            accepted=False,
            rejection_reason_ar="قراءة فارغة (None) — حسّاس معطّل أو انقطاع اتصال")

    # ٢. نوع المستشعر معروف؟
    if sensor_type not in _SENSOR_RANGES:
        return IntakeResult(
            accepted=False,
            rejection_reason_ar=f"نوع المستشعر '{sensor_type}' غير مدعوم")

    # ٣. القيمة ضمن النطاق الفيزيائي؟
    lo, hi, expected_unit = _SENSOR_RANGES[sensor_type]
    if not (lo <= value <= hi):
        return IntakeResult(
            accepted=False,
            rejection_reason_ar=(
                f"القيمة {value} {unit or expected_unit} خارج النطاق الفيزيائي "
                f"[{lo}, {hi}] {expected_unit} — راجع المستشعر"))

    warnings: list[str] = []

    # ٤. الوحدة تطابق المتوقّع؟ (تحذير لا رفض — قد يكون اختلاف صياغة)
    if unit and unit.lower() not in (expected_unit.lower(), expected_unit.replace("°", "").lower()):
        warnings.append(
            f"الوحدة المرسلة '{unit}' لا تطابق المتوقّعة '{expected_unit}' — "
            "تحقّق من معايرة الحسّاس")

    # ٥. الطابع الزمني (إن لم يُرسل، نستخدم الآن — لكن نحذّر)
    ts = timestamp_iso
    if not ts:
        ts = datetime.now(timezone.utc).isoformat()
        warnings.append("لا طابع زمني — استُخدم وقت الاستقبال (قد يفقد دقّة)")

    # ٦. ابنِ observation جاهزة للجدول الموجود
    observation = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "observable_id": _OBSERVABLE_MAP[sensor_type],
        "value": value,
        "unit": expected_unit,
        "source": "sensor",                  # ميّز عن manual/lab/satellite
        "method": f"sensor:{sensor_type}",
        "device_id": device_id,
        "measured_at": ts,
        "confidence": "medium",              # الحسّاس قرينة قويّة، سقف medium
        "lon": lon,
        "lat": lat,
    }
    # تنظيف None
    observation = {k: v for k, v in observation.items() if v is not None}
    return IntakeResult(accepted=True, observation=observation, warnings_ar=warnings)


def ingest_batch(readings: list[dict]) -> dict:
    """يستقبل دفعة قراءات (نمط JSON من الجهاز/البوّابة).

    كل قراءة dict تحوي على الأقلّ: tenant_id, field_id, sensor_type, value.
    يُرجع ملخّصاً: مقبول/مرفوض + قائمة observations الجاهزة + الأخطاء."""
    accepted_obs: list[dict] = []
    rejections: list[dict] = []
    all_warnings: list[str] = []

    for i, r in enumerate(readings):
        try:
            result = ingest_reading(
                tenant_id=r["tenant_id"], field_id=r["field_id"],
                sensor_type=r.get("sensor_type") or r.get("type"),
                value=r.get("value"),
                unit=r.get("unit"),
                device_id=r.get("device_id"),
                timestamp_iso=r.get("timestamp") or r.get("ts"),
                lon=r.get("lon"), lat=r.get("lat"))
        except KeyError as e:
            rejections.append({"index": i, "reason": f"حقل ناقص: {e}"})
            continue

        if result.accepted:
            accepted_obs.append(result.observation)
            all_warnings.extend(result.warnings_ar)
        else:
            rejections.append({"index": i, "reason": result.rejection_reason_ar})

    return {
        "accepted_count": len(accepted_obs),
        "rejected_count": len(rejections),
        "observations": accepted_obs,
        "rejections": rejections,
        "warnings": all_warnings,
        "summary_ar": (f"قُبل {len(accepted_obs)} قراءة، رُفض {len(rejections)} "
                       f"(تحذيرات: {len(all_warnings)})"),
    }
