"""Pollination weather-risk product — deterministic, flowering-window only.

فجوة تغطية حقيقيّة (كانت 0 ملفّات): نجاح العقد/التلقيح حسّاس للطقس **أثناء الإزهار
فقط** — حرارة عالية تُعقِّم اللقاح، برد/صقيع يُتلِف الأزهار، رياح شديدة/مطر يعيقان
نقل اللقاح. المحرّك يحسب الإشارة الجوّيّة أثناء نافذة الإزهار ويصنّفها بعتبات المحصول.

صدق صارم: خارج مرحلة الإزهار ⇒ ``not_applicable`` (لا خطر مُختلَق — الطقس لا يهدّد
تلقيحاً غير جارٍ). محصول مجهول ⇒ insufficient_context. الدور ``supporting`` (إشارة
داعمة لا تشخيص عقد نهائيّ — Vegetation/Decision يدمجانها بأدلّة أخرى).
"""

from __future__ import annotations

from typing import Any

PRODUCT_ID = "pollination_weather_risk"
PRODUCT_VERSION = "1.0.0"
THRESHOLD_SET_VERSION = "pollination_thresholds_v1_uncalibrated"

FLOWERING_STAGES = {"flowering", "bloom", "anthesis", "silking", "tasseling", "fruit_set"}

# عتبات الإزهار (°م ورياح م/ث): heat = فوقها تعقيم لقاح؛ cold = تحتها ضرر برد؛
# frost = تلف؛ wind = فوقها إعاقة نقل. قيم أدبيّة عامّة غير مُعايَرة محليّاً.
POLLINATION_THRESHOLDS_V1: dict[str, dict[str, float]] = {
    "wheat": {"heat_c": 31.0, "cold_c": 4.0, "frost_c": 0.0, "wind_mps": 12.0},
    "maize": {"heat_c": 35.0, "cold_c": 6.0, "frost_c": 1.0, "wind_mps": 10.0},
    "rice": {"heat_c": 35.0, "cold_c": 15.0, "frost_c": 5.0, "wind_mps": 10.0},
    "tomato": {"heat_c": 32.0, "cold_c": 10.0, "frost_c": 2.0, "wind_mps": 9.0},
    "pepper": {"heat_c": 32.0, "cold_c": 12.0, "frost_c": 3.0, "wind_mps": 9.0},
    "grape": {"heat_c": 35.0, "cold_c": 10.0, "frost_c": 0.0, "wind_mps": 11.0},
    "almond": {"heat_c": 30.0, "cold_c": 4.0, "frost_c": -1.0, "wind_mps": 8.0},
    "date_palm": {"heat_c": 45.0, "cold_c": 8.0, "frost_c": 0.0, "wind_mps": 14.0},
    "coffee": {"heat_c": 30.0, "cold_c": 10.0, "frost_c": 2.0, "wind_mps": 9.0},
    "sunflower": {"heat_c": 34.0, "cold_c": 8.0, "frost_c": 1.0, "wind_mps": 11.0},
}


def resolve_thresholds(crop: str | None) -> dict[str, float] | None:
    return POLLINATION_THRESHOLDS_V1.get((crop or "").strip().lower())


def compute_pollination_risk(
    *,
    crop: str | None,
    stage: str | None,
    day_max_c: float | None,
    night_min_c: float | None,
    max_wind_mps: float | None = None,
    rain_mm: float | None = None,
) -> dict[str, Any]:
    """خطر الطقس على التلقيح أثناء الإزهار (حتميّ، fail-closed خارج الإزهار)."""
    provenance: dict[str, Any] = {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "threshold_set": THRESHOLD_SET_VERSION,
    }
    thresholds = resolve_thresholds(crop)
    stage_key = (stage or "").strip().lower()

    if thresholds is None:
        return {
            "status": "insufficient_context",
            "crop": crop,
            "growth_stage": stage,
            "risk": None,
            "evidence_role": "supporting",
            "limiting_factors": ["unknown_crop"],
            "provenance": provenance,
        }
    if stage_key not in FLOWERING_STAGES:
        # صدق: الطقس لا يهدّد تلقيحاً غير جارٍ — لا خطر مُختلَق.
        return {
            "status": "not_applicable",
            "crop": crop,
            "growth_stage": stage,
            "risk": None,
            "evidence_role": "supporting",
            "reason": "outside_flowering_window",
            "provenance": provenance,
        }
    if day_max_c is None or night_min_c is None:
        return {
            "status": "insufficient_context",
            "crop": crop,
            "growth_stage": stage,
            "risk": None,
            "evidence_role": "supporting",
            "limiting_factors": ["no_temperature_series"],
            "provenance": provenance,
        }

    dmax, nmin = float(day_max_c), float(night_min_c)
    limiting: list[str] = []
    severity = 0.0

    def _sev(over: float) -> float:
        return max(0.0, min(1.0, over / 6.0))

    if dmax > thresholds["heat_c"]:
        s = _sev(dmax - thresholds["heat_c"])
        severity = max(severity, s)
        limiting.append("pollen_sterility_heat")
    if nmin < thresholds["cold_c"]:
        s = _sev(thresholds["cold_c"] - nmin)
        severity = max(severity, s)
        limiting.append("cold_flower_damage")
    if nmin <= thresholds["frost_c"]:
        severity = 1.0
        limiting.append("frost_flower_kill")
    if max_wind_mps is not None and float(max_wind_mps) > thresholds["wind_mps"]:
        severity = max(severity, 0.5)
        limiting.append("wind_impedes_pollen_transfer")
    if (rain_mm or 0.0) >= 15.0:
        severity = max(severity, 0.4)
        limiting.append("rain_washout_pollen")

    if severity >= 0.7:
        risk = "high"
    elif severity >= 0.4:
        risk = "moderate"
    elif severity > 0.0:
        risk = "low"
    else:
        risk = "none"

    return {
        "status": "ok",
        "crop": crop,
        "growth_stage": stage,
        "risk": risk,
        "pollination_risk_index": round(severity, 3),
        "day_max_c": round(dmax, 1),
        "night_min_c": round(nmin, 1),
        "thresholds_applied": thresholds,
        "confidence": 0.65,
        "evidence_role": "supporting",
        "limiting_factors": limiting,
        "provenance": provenance,
    }
