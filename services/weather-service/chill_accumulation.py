"""Chill accumulation product for deciduous perennials — deterministic.

فجوة تغطية حقيقيّة (كانت تغطية بسيطة فقط): الأشجار المتساقطة (لوز/فستق/عنب/تفّاح)
تحتاج ساعات برودة لكسر السكون؛ نقصها ⇒ إزهار غير منتظم وضعف عقد. المحرّك يحسب من
سلسلة حرارة ساعيّة نموذجين قياسيّين:

- **Chilling Hours** (النموذج الكلاسيكيّ): ساعات بين 0 و7.2°م.
- **Utah Chill Units**: أوزان حسب نطاق الحرارة (تشمل قيماً سالبة فوق 15.9°م).

**النموذج الديناميكيّ (Chill Portions/Erez) غير مُطبَّق هنا — لا نُزيّف تقريباً**؛
يُعلَن ``dynamic_model: not_implemented`` (صدق: لا نُصدِر نموذجاً معقّداً بتقريب خاطئ).

صدق: محصول غير معمِّر/بلا متطلّب معروف ⇒ not_applicable. بلا سلسلة ساعيّة ⇒
insufficient_context. الدور ``supporting`` (المتطلّبات تختلف بالصنف — تحتاج معايرة).
"""

from __future__ import annotations

from typing import Any

PRODUCT_ID = "chill_accumulation"
PRODUCT_VERSION = "1.0.0"
THRESHOLD_SET_VERSION = "chill_requirements_v1_uncalibrated"

# متطلّب ساعات البرودة التقريبيّ (Chilling Hours) لكسر السكون. قيم أدبيّة عامّة
# لأصناف شائعة — تختلف كثيراً بالصنف ⇒ الدور supporting (تحتاج معايرة محليّة).
CHILL_REQUIREMENT_HOURS_V1: dict[str, float] = {
    "almond": 300.0,
    "pistachio": 800.0,
    "grape": 150.0,
    "apple": 900.0,
    "pear": 700.0,
    "peach": 600.0,
    "apricot": 400.0,
    "fig": 100.0,
    "pomegranate": 150.0,
    "walnut": 700.0,
}


def _utah_unit(temp_c: float) -> float:
    """وحدة برودة Utah لساعة بحرارة temp_c (المعيار الكلاسيكيّ)."""
    if temp_c <= 1.4:
        return 0.0
    if temp_c <= 2.4:
        return 0.5
    if temp_c <= 9.1:
        return 1.0
    if temp_c <= 12.4:
        return 0.5
    if temp_c <= 15.9:
        return 0.0
    if temp_c <= 18.0:
        return -0.5
    return -1.0


def compute_chill_accumulation(
    *,
    crop: str | None,
    hourly_temp_c: list[Any] | None,
) -> dict[str, Any]:
    """يحسب Chilling Hours + Utah Chill Units من سلسلة حرارة ساعيّة."""
    provenance: dict[str, Any] = {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "threshold_set": THRESHOLD_SET_VERSION,
        "dynamic_model": "not_implemented",  # صدق: لا نُزيّف Chill Portions
    }
    key = (crop or "").strip().lower()
    requirement = CHILL_REQUIREMENT_HOURS_V1.get(key)

    if requirement is None:
        return {
            "status": "not_applicable",
            "crop": crop,
            "reason": "crop_not_a_known_chill_dependent_perennial",
            "evidence_role": "supporting",
            "provenance": provenance,
        }

    temps: list[float] = []
    for v in hourly_temp_c or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:  # NaN-safe
            temps.append(f)

    if not temps:
        return {
            "status": "insufficient_context",
            "crop": crop,
            "evidence_role": "supporting",
            "limiting_factors": ["no_hourly_temperature_series"],
            "provenance": provenance,
        }

    chilling_hours = sum(1 for t in temps if 0.0 <= t <= 7.2)
    utah_units = round(sum(_utah_unit(t) for t in temps), 1)
    utah_units = max(0.0, utah_units)  # لا رصيد سالب مُبلَّغ
    pct = round(min(1.0, chilling_hours / requirement) * 100.0, 1) if requirement > 0 else None

    return {
        "status": "ok",
        "crop": crop,
        "hours_analyzed": len(temps),
        "chilling_hours": chilling_hours,
        "utah_chill_units": utah_units,
        "requirement_hours": requirement,
        "requirement_met_pct": pct,
        "requirement_met": bool(pct is not None and pct >= 100.0),
        "confidence": 0.6,
        "evidence_role": "supporting",
        "provenance": provenance,
    }
