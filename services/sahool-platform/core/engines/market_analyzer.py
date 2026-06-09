"""
sahool_core.engines.market
===========================
Market gap & price-risk WITHOUT fabricated price forecasts.

The critique was right: no organised Yemeni commodity exchange exists, so
forecast_price() would be fiction. Instead we use:

  1. Coefficient of Variation (CV) of historical price -> volatility risk.
     CV = std(price) / mean(price). CV > 0.4 => high price risk.
  2. Import-substitution gap: (import_price - local_price)/local_price.
     gap > 0.3 => opportunity to substitute imports.

Both work on WHATEVER price series is available (manual market surveys,
WhatsApp groups, FAO-GIEWS if available). They degrade gracefully: with
no data they return UNKNOWN, never a fake number.

Source: CV as volatility proxy is standard; import-substitution gap is a
practical proxy where absolute price forecasting is infeasible.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum


class PriceRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass
class MarketSignal:
    crop_id: str
    price_risk: PriceRisk
    cv: float | None
    gap_score: float | None
    opportunity_ar: str
    data_quality: str            # "good" | "sparse" | "none"


def coefficient_of_variation(prices: list[float]) -> float | None:
    """CV = std/mean. Needs >= 3 points to be meaningful."""
    clean = [p for p in prices if p and p > 0]
    if len(clean) < 3:
        return None
    mean = statistics.mean(clean)
    if mean == 0:
        return None
    return statistics.pstdev(clean) / mean


def classify_price_risk(cv: float | None) -> PriceRisk:
    if cv is None:
        return PriceRisk.UNKNOWN
    if cv > 0.4:
        return PriceRisk.HIGH
    if cv > 0.2:
        return PriceRisk.MODERATE
    return PriceRisk.LOW


def import_substitution_gap(
    local_price: float | None, import_price: float | None
) -> float | None:
    """(import - local)/local. Positive => local is cheaper => substitution
    opportunity. Needs both prices."""
    if not (local_price and import_price) or local_price <= 0:
        return None
    return (import_price - local_price) / local_price


def analyse_market(
    crop_id: str,
    historical_prices: list[float],
    local_price: float | None = None,
    import_price: float | None = None,
) -> MarketSignal:
    cv = coefficient_of_variation(historical_prices)
    risk = classify_price_risk(cv)
    gap = import_substitution_gap(local_price, import_price)

    if cv is None and gap is None:
        quality = "none"
        opp = "لا بيانات سوقية كافية — قرار السوق غير متاح (لا تخمين)"
    elif cv is None or gap is None:
        quality = "sparse"
        opp = "بيانات سوقية محدودة — مؤشر استرشادي فقط"
    else:
        quality = "good"
        if gap > 0.3:
            opp = "فرصة استبدال واردات — المنتج المحلي أرخص من المستورد"
        elif risk == PriceRisk.HIGH:
            opp = "خطر سعري عالٍ — السعر متقلب، تجنّب الاعتماد الكامل"
        else:
            opp = "سوق مستقر نسبياً"

    return MarketSignal(
        crop_id=crop_id,
        price_risk=risk,
        cv=round(cv, 3) if cv is not None else None,
        gap_score=round(gap, 3) if gap is not None else None,
        opportunity_ar=opp,
        data_quality=quality,
    )


# ── مؤشّر العرض الإقليمي النسبي (اتجاه لا رقم مطلق) ──
def regional_supply_signal(
    current_season_lai: list[float],
    historical_avg_lai: float | None,
) -> dict:
    """يقدّر *اتجاه* العرض الإقليمي من LAI حقول المنصّة (لا رقم مطلق).

    فكرة استخبارات السوق — بصدق:
      ✅ "الكتلة الحيوية هذا الموسم أقوى/أضعف من المعتاد" (اتجاه)
      ❌ "العرض = X طن" (يحتاج تصنيف محصول + معايرة إنتاج لا نملكها)

    يعمل على حقول المنصّة المشتركة فقط (احترام الخصوصية — لا مسح
    حقول الآخرين سرّاً). أداة تنبيه مبكّر للاتجاه، لا تنبّؤ سعر.
    """
    valid = [x for x in current_season_lai if x is not None and x >= 0]
    if not valid:
        return {"signal": "unknown", "confidence": "none",
                "note_ar": "لا بيانات LAI كافية لإشارة العرض"}
    n = len(valid)
    current_avg = sum(valid) / n

    if historical_avg_lai is None or n < 5:
        return {"signal": "unknown", "confidence": "low",
                "current_avg_lai": round(current_avg, 2),
                "note_ar": (f"متوسط LAI الحالي ≈ {current_avg:.1f} (من {n} حقل). "
                            f"لا تاريخ كافٍ للمقارنة — يلزم ≥5 حقول وتاريخ موسمي")}

    ratio = current_avg / historical_avg_lai if historical_avg_lai > 0 else 1.0
    if ratio >= 1.15:
        signal, ar = "above_normal", "أقوى من المعتاد → عرض محتمل أعلى → ضغط هبوطي محتمل على السعر"
    elif ratio <= 0.85:
        signal, ar = "below_normal", "أضعف من المعتاد → عرض محتمل أقل → ضغط صعودي محتمل على السعر"
    else:
        signal, ar = "normal", "قريب من المعتاد → عرض متوقّع طبيعي"

    return {
        "signal": signal,
        "current_avg_lai": round(current_avg, 2),
        "historical_avg_lai": round(historical_avg_lai, 2),
        "ratio": round(ratio, 2),
        "n_fields": n,
        "confidence": "low",  # اتجاه استرشادي، لا تنبّؤ
        "note_ar": (f"إشارة العرض الإقليمي ({n} حقل بالمنصّة): {ar}. "
                    f"اتجاه استرشادي من الكتلة الحيوية — ليس تنبّؤ سعر."),
    }
