"""Compound diurnal thermal-stress product (deterministic, crop×stage-conditioned).

يغطّي فجوة زراعيّة حقيقيّة: التفاعل بين حرّ النهار وبرد الليل (لا العتبة المفردة).
يحسب إشارات حراريّة **حتميّة** من سلسلة حرارة ساعيّة + حدّي اليوم Tmax/Tmin، ثمّ
يصنّفها إلى مخاطرة مشروطة بـ(المحصول × المرحلة). صدق صارم:

- **fail-closed:** محصول/مرحلة مجهولان أو بلا عتبات ⇒ ``status="insufficient_context"``
  بلا مخاطرة مُختلَقة.
- **الدور دليلاً ``supporting`` لا ``decision_blocking``** حتّى المعايرة الميدانيّة —
  العتبات هنا افتراضات أدبيّة عامّة تحتاج ضبطاً محليّاً (صنف/مناخ)، تماماً كسياسات
  H5/C5 «مُصلَحة تحتاج معايرة».
- **رطوبة الأوراق تقدير مُعلَّم** (``estimated_not_measured``) لا قياس.
- لا نُصدِر «ساعات» إن غابت السلسلة الساعيّة — نُعلن ``requires_hourly`` بدل الاختلاق.

الحدود المعماريّة: هذا المحرّك يحسب الإشارة الفيزيائيّة فقط؛ تفسير أثرها على النبات
(Vegetation) واختيار الإجراء (Decision) خارج نطاقه.
"""

from __future__ import annotations

from typing import Any

PRODUCT_ID = "compound_thermal_stress"
PRODUCT_VERSION = "1.0.0"
THRESHOLD_SET_VERSION = "thermal_thresholds_v1_uncalibrated"

# عتبات حراريّة افتراضيّة (°م) — heat = فوقها إجهاد حرّ؛ cold = تحتها إجهاد برد؛
# frost = خطر صقيع. قيم أدبيّة عامّة (FAO/إرشاد) **غير مُعايَرة محليّاً** ⇒ الدور
# supporting. ``stages`` يشدّد العتبات في المراحل التكاثريّة الحسّاسة.
THERMAL_THRESHOLDS_V1: dict[str, dict[str, Any]] = {
    "wheat": {
        "heat_c": 30.0,
        "cold_c": 4.0,
        "frost_c": 0.0,
        "stages": {"flowering": {"heat_c": 26.0}, "grain_filling": {"heat_c": 28.0}},
    },
    "maize": {
        "heat_c": 35.0,
        "cold_c": 8.0,
        "frost_c": 2.0,
        "stages": {"flowering": {"heat_c": 33.0}, "silking": {"heat_c": 33.0}},
    },
    "tomato": {
        "heat_c": 32.0,
        "cold_c": 10.0,
        "frost_c": 2.0,
        "stages": {"flowering": {"heat_c": 29.0, "cold_c": 12.0}, "fruit_set": {"heat_c": 30.0}},
    },
    "pepper": {
        "heat_c": 32.0,
        "cold_c": 12.0,
        "frost_c": 3.0,
        "stages": {"flowering": {"heat_c": 30.0, "cold_c": 15.0}},
    },
    "cucumber": {
        "heat_c": 33.0,
        "cold_c": 12.0,
        "frost_c": 3.0,
        "stages": {"flowering": {"heat_c": 30.0, "cold_c": 14.0}},
    },
    "potato": {
        "heat_c": 30.0,
        "cold_c": 5.0,
        "frost_c": 0.0,
        "stages": {"tuberization": {"heat_c": 28.0}},
    },
    "grape": {
        "heat_c": 35.0,
        "cold_c": 5.0,
        "frost_c": 0.0,
        "stages": {"flowering": {"heat_c": 32.0, "cold_c": 10.0}, "veraison": {"heat_c": 35.0}},
    },
    "almond": {
        "heat_c": 35.0,
        "cold_c": 2.0,
        "frost_c": -1.5,
        "stages": {"bloom": {"cold_c": 4.0, "frost_c": 0.0}},
    },
    "date_palm": {"heat_c": 45.0, "cold_c": 5.0, "frost_c": -2.0, "stages": {}},
    "coffee": {
        "heat_c": 30.0,
        "cold_c": 8.0,
        "frost_c": 2.0,
        "stages": {"flowering": {"heat_c": 28.0, "cold_c": 10.0}},
    },
}

_RISK_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "severe": 4}


def resolve_thresholds(crop: str | None, stage: str | None) -> dict[str, float] | None:
    """عتبات (heat_c, cold_c, frost_c) لمحصول/مرحلة، أو None عند الجهل (fail-closed)."""
    key = (crop or "").strip().lower()
    base = THERMAL_THRESHOLDS_V1.get(key)
    if base is None:
        return None
    resolved = {
        "heat_c": float(base["heat_c"]),
        "cold_c": float(base["cold_c"]),
        "frost_c": float(base["frost_c"]),
    }
    stage_key = (stage or "").strip().lower()
    stage_over = (base.get("stages") or {}).get(stage_key)
    if isinstance(stage_over, dict):
        for k, v in stage_over.items():
            resolved[k] = float(v)
    return resolved


def _finite(values: list[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f and f not in (float("inf"), float("-inf")):  # NaN/inf-safe
            out.append(f)
    return out


def compute_compound_thermal_stress(
    *,
    crop: str | None,
    stage: str | None,
    daily_max_c: list[Any],
    daily_min_c: list[Any],
    hourly_temp_c: list[Any] | None = None,
    hourly_is_daytime: list[Any] | None = None,
    hourly_rh_pct: list[Any] | None = None,
) -> dict[str, Any]:
    """يحسب عقد ``compound_thermal_stress`` بصدق (لا اختلاق عند نقص المدخلات).

    daily_max_c/daily_min_c: سلسلة يوميّة (Tmax/Tmin) — المدخل الأدنى المطلوب.
    hourly_*: اختياريّة؛ عند توفّرها تُحسب «ساعات» الإجهاد بدل عدّ الأيّام/الليالي.
    """
    provenance: dict[str, Any] = {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "threshold_set": THRESHOLD_SET_VERSION,
        "leaf_wetness": "estimated_not_measured",
        "temporal_resolution": "hourly" if hourly_temp_c else "daily",
    }

    thresholds = resolve_thresholds(crop, stage)
    d_max = _finite(daily_max_c or [])
    d_min = _finite(daily_min_c or [])

    # fail-closed: بلا سياق محصول/مرحلة أو بلا بيانات ⇒ لا مخاطرة مُختلَقة.
    if thresholds is None or not d_max or not d_min:
        reason = (
            "unknown_crop_or_stage" if thresholds is None else "insufficient_temperature_series"
        )
        return {
            "status": "insufficient_context",
            "crop": crop,
            "growth_stage": stage,
            "risk": None,
            "evidence_role": "supporting",
            "limiting_factors": [reason],
            "provenance": provenance,
        }

    n = min(len(d_max), len(d_min))
    d_max, d_min = d_max[:n], d_min[:n]
    heat_c, cold_c, frost_c = thresholds["heat_c"], thresholds["cold_c"], thresholds["frost_c"]

    diurnal_ranges = [mx - mn for mx, mn in zip(d_max, d_min, strict=False)]
    heat_stress_days = sum(1 for mx in d_max if mx > heat_c)
    cold_stress_nights = sum(1 for mn in d_min if mn < cold_c)
    frost_nights = sum(1 for mn in d_min if mn <= frost_c)

    # أطول تتابع ليالٍ باردة (إجهاد برد متراكم).
    consecutive_cold = 0
    run = 0
    for mn in d_min:
        run = run + 1 if mn < cold_c else 0
        consecutive_cold = max(consecutive_cold, run)

    # شدّة اليوم الأسوأ (0..1): تطبيع تجاوز الحرّ/البرد على نطاق 10°م، مقصوص.
    def _sev(over: float) -> float:
        return max(0.0, min(1.0, over / 10.0))

    worst_heat = max((_sev(mx - heat_c) for mx in d_max), default=0.0)
    worst_cold = max((_sev(cold_c - mn) for mn in d_min), default=0.0)
    max_dtr = max(diurnal_ranges, default=0.0)
    # مؤشّر مركّب: الحرّ والبرد يجتمعان (لا DTR وحده)؛ يُعزَّز قليلاً عند تباين كبير.
    swing_boost = 0.10 if max_dtr >= 20.0 else 0.0
    compound_index = round(
        min(
            1.0, 0.6 * max(worst_heat, worst_cold) + 0.4 * min(worst_heat, worst_cold) + swing_boost
        ),
        3,
    )

    limiting: list[str] = []
    if worst_heat >= 0.3:
        limiting.append("extreme_daytime_heat")
    if worst_cold >= 0.3:
        limiting.append("cold_night_stress")
    if frost_nights > 0:
        limiting.append("frost_risk")
    if max_dtr >= 20.0:
        limiting.append("large_diurnal_swing")
    if (stage or "").strip().lower() in {
        "flowering",
        "grain_filling",
        "fruit_set",
        "silking",
        "bloom",
        "tuberization",
        "veraison",
    }:
        limiting.append("sensitive_reproductive_stage")

    if frost_nights > 0 or compound_index >= 0.7:
        risk = "high"
    elif compound_index >= 0.4:
        risk = "moderate"
    elif compound_index > 0.0:
        risk = "low"
    else:
        risk = "none"

    # ثقة: أعلى مع أفق أقصر وسلسلة أطول (تقديريّة، صريحة).
    confidence = round(max(0.4, min(0.85, 0.85 - 0.05 * max(0, n - 3))), 2)

    result: dict[str, Any] = {
        "status": "ok",
        "crop": crop,
        "growth_stage": stage,
        "horizon_days": n,
        "day_max_c": round(max(d_max), 1),
        "night_min_c": round(min(d_min), 1),
        "max_diurnal_range_c": round(max_dtr, 1),
        "heat_stress_days": heat_stress_days,
        "cold_stress_nights": cold_stress_nights,
        "frost_nights": frost_nights,
        "consecutive_cold_nights": consecutive_cold,
        "compound_index": compound_index,
        "risk": risk,
        "confidence": confidence,
        "evidence_role": "supporting",
        "limiting_factors": limiting,
        "thresholds_applied": {"heat_c": heat_c, "cold_c": cold_c, "frost_c": frost_c},
        "provenance": provenance,
    }

    # ساعات الإجهاد الفعليّة فقط عند توفّر السلسلة الساعيّة (لا اختلاق).
    if hourly_temp_c:
        temps = hourly_temp_c
        day_flags = hourly_is_daytime or [None] * len(temps)
        day_heat_hours = 0
        night_cold_hours = 0
        for t, dflag in zip(temps, day_flags, strict=False):
            try:
                tv = float(t)
            except (TypeError, ValueError):
                continue
            if tv != tv:
                continue
            is_day = bool(dflag) if dflag is not None else None
            if tv > heat_c and (is_day is None or is_day):
                day_heat_hours += 1
            if tv < cold_c and (is_day is None or not is_day):
                night_cold_hours += 1
        result["day_heat_stress_hours"] = day_heat_hours
        result["night_cold_stress_hours"] = night_cold_hours
        # تقدير رطوبة الأوراق: ساعات RH>=90% (تقريب مُعلَّم، لا قياس).
        if hourly_rh_pct:
            rh = _finite(hourly_rh_pct)
            result["dew_leaf_wetness_estimate_hours"] = sum(1 for r in rh if r >= 90.0)
    else:
        result["hours_note"] = "requires_hourly_series"

    return result
