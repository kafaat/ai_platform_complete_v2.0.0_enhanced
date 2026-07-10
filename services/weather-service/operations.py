from __future__ import annotations

from typing import Any

SUPPORTED_OPERATIONS = {"spraying", "harvesting", "sowing", "fertilizing", "irrigation"}


def _num(sample: dict[str, Any], key: str, default: float | None = None) -> float | None:
    value = sample.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status(score: float, unsafe: bool = False) -> str:
    if unsafe or score < 0.25:
        return "unsafe"
    if score < 0.55:
        return "poor"
    if score < 0.78:
        return "acceptable"
    return "optimal"


# مدخلات حرِجة للسلامة لكلّ عمليّة — غيابها لا يُعوَّض بافتراض «طبيعيّ» يُوهِم الأمان.
# (سابقاً: رياح مفقودة ⇒ 0 ⇒ نافذة رشّ «آمنة» زوراً؛ مطر مفقود ⇒ 0 ⇒ «لا مطر».)
_SAFETY_CRITICAL: dict[str, list[str]] = {
    "spraying": ["wind", "precip"],
    "harvesting": ["precip"],
    "sowing": ["precip"],
    "fertilizing": ["wind", "precip"],
    "irrigation": ["precip"],
}


def _wind_kmh(sample: dict[str, Any]) -> float | None:
    w = _num(sample, "wind_speed_10m_kmh", None)
    if w is not None:
        return w
    ms = _num(sample, "wind_speed_ms", None)
    return ms * 3.6 if ms is not None else None


def operation_suitability(sample: dict[str, Any], operation: str) -> dict[str, Any]:
    op = (operation or "spraying").lower()
    if op not in SUPPORTED_OPERATIONS:
        op = "spraying"

    # قراءة صادقة: None = مفقود (لا افتراض طبيعيّ لمدخل سلامة).
    temp = _num(sample, "temperature_c", None)
    rh = _num(sample, "humidity_pct", None)
    wind = _wind_kmh(sample)
    gust = _num(sample, "wind_gusts_10m_kmh", None)
    if gust is None:
        gust = wind  # تقدير محافظ من سرعة الرياح إن غابت الهبّة (وإلّا يبقى None)
    precip = _num(sample, "precipitation_mm", None)
    soil_moisture = _num(sample, "soil_moisture_1_to_3cm_m3m3", None)
    soil_temp = _num(sample, "soil_temperature_6cm_c", None)
    if soil_temp is None:
        soil_temp = temp
    vpd = _num(sample, "vpd_kpa", None)

    # fail-closed: أيّ مدخل سلامة حرِج مفقود ⇒ لا حكم بالأمان (لا نافذة زائفة).
    present = {"wind": wind is not None, "precip": precip is not None, "temp": temp is not None}
    missing = [k for k in _SAFETY_CRITICAL[op] if not present.get(k, True)]
    if missing:
        return {
            "operation": op,
            "score": 0.0,
            "suitability": "insufficient_data",
            "limiting_factors": [f"missing_{m}" for m in missing],
            "safe": False,
            "status": "insufficient_data",
            "missing_inputs": missing,
        }

    factors: list[str] = []
    score = 1.0

    def penalize(condition: bool, amount: float, factor: str) -> None:
        nonlocal score
        if condition:
            score = max(0.0, score - amount)
            factors.append(factor)

    if op == "spraying":
        penalize(wind > 18, 0.45, "wind_speed_high")
        penalize(gust is not None and gust > 29, 0.25, "wind_gust_high")
        penalize(
            temp is not None and (temp < 5 or temp > 30), 0.25, "temperature_outside_spray_window"
        )
        penalize(rh is not None and rh > 85, 0.15, "humidity_high")
        penalize(precip > 0.1, 0.35, "rain_present")
        if vpd is not None:
            penalize(vpd < 0.2 or vpd > 3.5, 0.10, "vpd_outside_preferred_range")
    elif op == "harvesting":
        penalize(wind is not None and wind > 36, 0.20, "wind_high")
        penalize(rh is not None and rh > 70, 0.30, "humidity_high")
        penalize(precip > 0.1, 0.45, "rain_present")
        penalize(temp is not None and temp < 0, 0.20, "temperature_below_minimum")
    elif op == "sowing":
        penalize(
            soil_temp is not None and (soil_temp < 8 or soil_temp > 35),
            0.35,
            "soil_temperature_outside_window",
        )
        penalize(precip > 8, 0.20, "heavy_rain_risk")
        if soil_moisture is not None:
            penalize(soil_moisture < 0.12, 0.25, "soil_too_dry")
    elif op == "fertilizing":
        penalize(wind > 25, 0.25, "wind_high")
        penalize(precip > 0.2, 0.45, "rain_present")
        penalize(temp is not None and temp > 35, 0.15, "heat_loss_risk")
    elif op == "irrigation":
        penalize(precip > 2, 0.50, "rain_expected_or_present")
        penalize(temp is not None and temp < 2, 0.20, "cold_conditions")
        if soil_moisture is not None:
            penalize(soil_moisture > 0.35, 0.35, "soil_already_wet")
            if soil_moisture < 0.18:
                factors.append("soil_moisture_low")
                score = min(1.0, score + 0.08)

    suitability = _status(score)
    return {
        "operation": op,
        "score": round(max(0.0, min(1.0, score)), 3),
        "suitability": suitability,
        "limiting_factors": factors,
        "safe": suitability not in {"unsafe"},
        "status": "ok",
    }


def best_operation_frame(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not frames:
        return None
    return max(frames, key=lambda f: (f.get("operation") or {}).get("score", 0))


def advice_ar(decision: dict[str, Any] | None) -> str:
    if not decision:
        return "لا توجد نافذة موثوقة."
    op = decision.get("operation", "operation")
    suitability = decision.get("suitability", "poor")
    if suitability == "insufficient_data":
        return f"بيانات الطقس ناقصة — لا يمكن تأكيد سلامة {op}."
    if suitability == "optimal":
        return f"النافذة مناسبة جداً لتنفيذ {op}."
    if suitability == "acceptable":
        return f"يمكن تنفيذ {op} مع مراقبة العوامل المحددة."
    if suitability == "poor":
        return f"يفضل تأجيل {op} إن لم تكن العملية عاجلة."
    return f"لا ينصح بتنفيذ {op} حالياً."
