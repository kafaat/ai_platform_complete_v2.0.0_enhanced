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


def operation_suitability(sample: dict[str, Any], operation: str) -> dict[str, Any]:
    op = (operation or "spraying").lower()
    if op not in SUPPORTED_OPERATIONS:
        op = "spraying"
    temp = _num(sample, "temperature_c", 20.0) or 20.0
    rh = _num(sample, "humidity_pct", 50.0) or 50.0
    wind = _num(sample, "wind_speed_10m_kmh", None)
    if wind is None:
        wind_ms = _num(sample, "wind_speed_ms", 0.0) or 0.0
        wind = wind_ms * 3.6
    gust = _num(sample, "wind_gusts_10m_kmh", wind) or wind
    precip = _num(sample, "precipitation_mm", 0.0) or 0.0
    soil_moisture = _num(sample, "soil_moisture_1_to_3cm_m3m3", None)
    soil_temp = _num(sample, "soil_temperature_6cm_c", temp) or temp
    vpd = _num(sample, "vpd_kpa", None)

    factors: list[str] = []
    score = 1.0

    def penalize(condition: bool, amount: float, factor: str) -> None:
        nonlocal score
        if condition:
            score = max(0.0, score - amount)
            factors.append(factor)

    if op == "spraying":
        penalize(wind > 18, 0.45, "wind_speed_high")
        penalize(gust > 29, 0.25, "wind_gust_high")
        penalize(temp < 5 or temp > 30, 0.25, "temperature_outside_spray_window")
        penalize(rh > 85, 0.15, "humidity_high")
        penalize(precip > 0.1, 0.35, "rain_present")
        if vpd is not None:
            penalize(vpd < 0.2 or vpd > 3.5, 0.10, "vpd_outside_preferred_range")
    elif op == "harvesting":
        penalize(wind > 36, 0.20, "wind_high")
        penalize(rh > 70, 0.30, "humidity_high")
        penalize(precip > 0.1, 0.45, "rain_present")
        penalize(temp < 0, 0.20, "temperature_below_minimum")
    elif op == "sowing":
        penalize(soil_temp < 8 or soil_temp > 35, 0.35, "soil_temperature_outside_window")
        penalize(precip > 8, 0.20, "heavy_rain_risk")
        if soil_moisture is not None:
            penalize(soil_moisture < 0.12, 0.25, "soil_too_dry")
    elif op == "fertilizing":
        penalize(wind > 25, 0.25, "wind_high")
        penalize(precip > 0.2, 0.45, "rain_present")
        penalize(temp > 35, 0.15, "heat_loss_risk")
    elif op == "irrigation":
        penalize(precip > 2, 0.50, "rain_expected_or_present")
        penalize(temp < 2, 0.20, "cold_conditions")
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
    if suitability == "optimal":
        return f"النافذة مناسبة جداً لتنفيذ {op}."
    if suitability == "acceptable":
        return f"يمكن تنفيذ {op} مع مراقبة العوامل المحددة."
    if suitability == "poor":
        return f"يفضل تأجيل {op} إن لم تكن العملية عاجلة."
    return f"لا ينصح بتنفيذ {op} حالياً."
