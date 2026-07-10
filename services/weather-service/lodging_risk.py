"""Lodging (crop fall-over) weather-risk product — deterministic, crop×stage.

فجوة تغطية حقيقيّة (كانت 0 ملفّات): خطر الرقود = انبطاح النبات بفعل الرياح، أشدّ
في الحبوب الطويلة عند طرد السنابل/امتلاء الحبّ، ويتفاقم مع تربة مُشبَّعة (جذور
أضعف قبضةً). المحرّك يحسب **إشارة الرياح الحتميّة** ويضربها في قابليّة (محصول×مرحلة)؛
ارتفاع النبات ورطوبة التربة **مدخلان اختياريّان** يرفعان الدقّة/الخطر عند توفّرهما.

صدق: محصول مجهول ⇒ insufficient_context (لا خطر مُختلَق). الدور ``supporting``
(عتبات أدبيّة تحتاج معايرة). غياب الارتفاع/الرطوبة يُخفض الثقة ويُعلَن، لا يُختلَق.
"""

from __future__ import annotations

from typing import Any

PRODUCT_ID = "lodging_risk"
PRODUCT_VERSION = "1.0.0"
THRESHOLD_SET_VERSION = "lodging_susceptibility_v1_uncalibrated"

# قابليّة الرقود (0=منخفضة، 1=عالية) حسب المحصول والمرحلة. الحبوب الطويلة عالية عند
# الطرد/الامتلاء؛ المحاصيل القصيرة/الشجيريّة منخفضة. قيم أدبيّة عامّة غير مُعايَرة.
LODGING_SUSCEPTIBILITY_V1: dict[str, dict[str, Any]] = {
    "wheat": {"base": 0.5, "stages": {"heading": 0.8, "grain_filling": 0.9, "flowering": 0.8}},
    "barley": {"base": 0.5, "stages": {"heading": 0.85, "grain_filling": 0.95}},
    "rice": {"base": 0.6, "stages": {"heading": 0.85, "grain_filling": 0.9}},
    "maize": {"base": 0.4, "stages": {"silking": 0.7, "grain_filling": 0.75}},
    "oat": {"base": 0.55, "stages": {"heading": 0.85, "grain_filling": 0.9}},
    "sorghum": {"base": 0.35, "stages": {"grain_filling": 0.6}},
    "sunflower": {"base": 0.4, "stages": {"flowering": 0.6, "grain_filling": 0.7}},
    "canola": {"base": 0.45, "stages": {"flowering": 0.6, "pod_fill": 0.7}},
}


def resolve_susceptibility(crop: str | None, stage: str | None) -> float | None:
    key = (crop or "").strip().lower()
    row = LODGING_SUSCEPTIBILITY_V1.get(key)
    if row is None:
        return None
    stage_key = (stage or "").strip().lower()
    return float((row.get("stages") or {}).get(stage_key, row["base"]))


def compute_lodging_risk(
    *,
    crop: str | None,
    stage: str | None,
    max_wind_gust_mps: float | None,
    max_wind_speed_mps: float | None = None,
    recent_rain_mm: float | None = None,
    forecast_rain_mm: float | None = None,
    plant_height_cm: float | None = None,
    soil_saturated: bool | None = None,
) -> dict[str, Any]:
    """خطر الرقود الحتميّ. الرياح إلزاميّة؛ الارتفاع/التربة اختياريّان (ثقة أعلى)."""
    provenance: dict[str, Any] = {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "threshold_set": THRESHOLD_SET_VERSION,
    }
    susceptibility = resolve_susceptibility(crop, stage)
    gust = max_wind_gust_mps if max_wind_gust_mps is not None else max_wind_speed_mps

    if susceptibility is None:
        return {
            "status": "insufficient_context",
            "crop": crop,
            "growth_stage": stage,
            "risk": None,
            "evidence_role": "supporting",
            "limiting_factors": ["unknown_crop"],
            "provenance": provenance,
        }
    if gust is None:
        return {
            "status": "insufficient_context",
            "crop": crop,
            "growth_stage": stage,
            "risk": None,
            "evidence_role": "supporting",
            "limiting_factors": ["no_wind_forecast"],
            "provenance": provenance,
        }

    try:
        gust = float(gust)
    except (TypeError, ValueError):
        gust = 0.0

    # شدّة الرياح (0..1): عتبة قلق ~10 م/ث، خطر شديد ~20 م/ث (تقريب محافظ).
    wind_sev = max(0.0, min(1.0, (gust - 10.0) / 10.0))

    limiting: list[str] = []
    amplifier = 1.0
    # تربة مُشبَّعة/مطر حديث ⇒ قبضة جذور أضعف ⇒ خطر أعلى (مُعامِل تضخيم).
    wet = bool(soil_saturated) or ((recent_rain_mm or 0.0) + (forecast_rain_mm or 0.0) >= 20.0)
    if wet:
        amplifier *= 1.25
        limiting.append("wet_soil_weak_anchorage")
    # نبات طويل ⇒ عزم أكبر (اختياريّ).
    height_known = plant_height_cm is not None
    if height_known and float(plant_height_cm) >= 80.0:
        amplifier *= 1.15
        limiting.append("tall_canopy")

    score = min(1.0, wind_sev * susceptibility * amplifier)
    if gust >= 17.0 and susceptibility >= 0.7:
        limiting.append("high_gusts_susceptible_stage")

    if score >= 0.6:
        risk = "high"
    elif score >= 0.3:
        risk = "moderate"
    elif score > 0.0:
        risk = "low"
    else:
        risk = "none"

    # ثقة أعلى حين تتوفّر مدخلات الارتفاع/الرطوبة (وإلّا مُعلَن الافتقاد).
    confidence = 0.75 if (height_known and soil_saturated is not None) else 0.6
    if not height_known:
        limiting.append("plant_height_unknown_estimate")

    return {
        "status": "ok",
        "crop": crop,
        "growth_stage": stage,
        "risk": risk,
        "lodging_index": round(score, 3),
        "max_wind_gust_mps": round(gust, 1),
        "susceptibility": round(susceptibility, 2),
        "wet_soil": wet,
        "plant_height_cm": plant_height_cm,
        "confidence": round(confidence, 2),
        "evidence_role": "supporting",
        "limiting_factors": limiting,
        "provenance": provenance,
    }
