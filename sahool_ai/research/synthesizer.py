"""التوليف الحتميّ لنتائج الأبحاث الزراعيّة.

Deterministic rule-based synthesizer for the SAHOOL Agronomic Research Pipeline.
Produces Arabic summaries, factor lists, and recommendations.
"""

from __future__ import annotations

from sahool_ai.research.extractor import (
    extract_causal_links,
    extract_numeric_values,
    extract_temporal_patterns,
)
from sahool_ai.research.models import Factor, Synthesis

# ── عتبات اتّخاذ القرار / Decision thresholds ──────────────────────────────
_RAINFALL_BASELINE_MM: float = 80.0
_MOISTURE_LOW: float = 25.0
_MOISTURE_CRITICAL: float = 18.0
_ADHERENCE_LOW: float = 60.0
_ADHERENCE_CRITICAL: float = 45.0
_NDVI_DECLINE_MODERATE: float = -15.0
_NDVI_DECLINE_SEVERE: float = -25.0


def _classify_severity(value: float, moderate_threshold: float, severe_threshold: float) -> str:
    """تصنيف شدّة العامل بناءً على القيمة والعتبات.

    للقيم السالبة (مثل نسبة انخفاض NDVI): السالب الأكبر = الأشدّ.
    """
    if abs(value) >= abs(severe_threshold):
        return "high"
    if abs(value) >= abs(moderate_threshold):
        return "medium"
    return "low"


def synthesize_findings(extracted: dict, query: str) -> Synthesis:
    """توليف نتائج الاستخراج في تقرير زراعي موحَّد.

    كلّ المنطق حتميّ: نفس المدخلات تُنتج دائماً نفس المخرجات.

    Args:
        extracted: قاموس يحتوي على نتائج من ``retrieve_all`` (raw results dict
            keyed by source), أو قاموس يحتوي على مفاتيح استخراج مسبق.
            يُعالَج عبر استدعاء دوال الاستخراج داخليّاً.
        query: نص الاستعلام الأصلي بالعربية أو الإنجليزية.

    Returns:
        :class:`~sahool_ai.research.models.Synthesis` مع ملخّص وعوامل وتوصيات.
    """
    # الاستخراج الداخلي من النتائج الخام
    numeric = extract_numeric_values(extracted)
    causal = extract_causal_links(extracted)
    temporal = extract_temporal_patterns(extracted)

    factors: list[Factor] = []
    recommendations: list[str] = []

    ndvi_change = numeric.get("ndvi_change_pct", 0.0)
    ndvi_trend = numeric.get("ndvi_trend", "unknown")
    rainfall_deficit = numeric.get("rainfall_deficit_mm", 0.0)
    rainfall_mm = numeric.get("rainfall_mm", _RAINFALL_BASELINE_MM)
    adherence = numeric.get("irrigation_adherence_pct", 100.0)
    moisture = numeric.get("soil_moisture_pct", 30.0)
    missed_count = numeric.get("irrigation_missed", 0)
    temp_c = numeric.get("avg_temp_c", 25.0)
    anomalies = numeric.get("weather_anomalies", [])
    npk = numeric.get("npk", {})

    # ── عامل 1: عجز مطري ──────────────────────────────────────────────────
    if rainfall_deficit > 0:
        severity = _classify_severity(rainfall_deficit, 20.0, 50.0)
        conf_base = min(0.95, 0.5 + rainfall_deficit / 160.0)
        factors.append(
            Factor(
                name="عجز مطري",
                description=(
                    f"الأمطار المرصودة {rainfall_mm:.1f} مم مقابل"
                    f" خطّ الأساس {_RAINFALL_BASELINE_MM:.0f} مم"
                    f" (عجز {rainfall_deficit:.1f} مم)."
                ),
                severity=severity,
                confidence=conf_base,
            )
        )
        if severity == "high":
            recommendations.append(
                "زيادة تكرار الري إلى يومياً لمدة أسبوع للتعويض عن العجز المطري الحادّ."
            )
        elif severity == "medium":
            recommendations.append(
                "زيادة جرعات الري بنسبة 30% خلال الأسبوعين المقبلين حتّى تعود الأمطار."
            )
        else:
            recommendations.append("مراقبة مستويات الرطوبة أسبوعيّاً وضبط جدول الري عند الحاجة.")

    # ── عامل 2: تأخّر الري أو ضعف الالتزام ──────────────────────────────
    if adherence < _ADHERENCE_LOW or missed_count > 3:
        severity = "high" if adherence < _ADHERENCE_CRITICAL else "medium"
        conf_irr = min(0.90, 0.4 + (1.0 - adherence / 100.0) + missed_count / 30.0)
        factors.append(
            Factor(
                name="تأخّر ري",
                description=(
                    f"نسبة الالتزام بجدول الري {adherence:.1f}% ({missed_count} يوم فائت)."
                ),
                severity=severity,
                confidence=conf_irr,
            )
        )
        if severity == "high":
            recommendations.append(
                "مراجعة نظام الري فوراً وإعادة جدولة الدورات الفائتة خلال 48 ساعة."
            )
        else:
            recommendations.append("تحسين جدولة الري وتفعيل التنبيهات التلقائيّة للمسؤولين.")

    # ── عامل 3: جفاف التربة ─────────────────────────────────────────────
    if moisture < _MOISTURE_LOW:
        severity = "high" if moisture < _MOISTURE_CRITICAL else "medium"
        conf_soil = min(0.88, 0.5 + (_MOISTURE_LOW - moisture) / 40.0)
        factors.append(
            Factor(
                name="جفاف التربة",
                description=(
                    f"رطوبة التربة {moisture:.1f}% دون العتبة الدنيا {_MOISTURE_LOW:.0f}%."
                ),
                severity=severity,
                confidence=conf_soil,
            )
        )
        recommendations.append("إضافة طبقة من المهاد العضوي (5 سم) للحدّ من فقد الرطوبة بالتبخّر.")

    # ── عامل 4: شذوذ مناخي / موجة حرارة ─────────────────────────────────
    high_anomalies = [a for a in anomalies if a.get("severity") in ("high", "medium")]
    if high_anomalies:
        severity = "high" if any(a["severity"] == "high" for a in high_anomalies) else "medium"
        factors.append(
            Factor(
                name="شذوذ مناخي",
                description=(
                    f"رُصدت {len(high_anomalies)} شذوذات مناخيّة (متوسّط الحرارة {temp_c:.1f}°م)."
                ),
                severity=severity,
                confidence=0.78,
            )
        )
        recommendations.append(
            "تشغيل مضخّات التبريد وضبط مواعيد الري للفجر والمساء خلال فترة موجة الحرارة."
        )

    # ── عامل 5: انخفاض NDVI ─────────────────────────────────────────────
    if ndvi_trend == "declining" and ndvi_change < _NDVI_DECLINE_MODERATE:
        severity = _classify_severity(ndvi_change, _NDVI_DECLINE_MODERATE, _NDVI_DECLINE_SEVERE)
        conf_ndvi = min(0.92, 0.55 + abs(ndvi_change) / 100.0)
        factors.append(
            Factor(
                name="انخفاض NDVI",
                description=(
                    f"انخفض مؤشّر الغطاء النباتي بنسبة {abs(ndvi_change):.1f}% خلال الفترة المرصودة."
                ),
                severity=severity,
                confidence=conf_ndvi,
            )
        )
        recommendations.append(
            "رصد NDVI بصور جوّيّة أسبوعيّة وتوثيق أيّ بقع صفراء قبل التدخّل الكيميائي."
        )

    # ── عامل 6: نقص NPK ──────────────────────────────────────────────────
    if npk:
        nitrogen = npk.get("n", 30.0)
        if nitrogen < 15.0:
            factors.append(
                Factor(
                    name="نقص نيتروجين",
                    description=f"مستوى النيتروجين في التربة {nitrogen:.1f} (دون الحدّ الأدنى 15).",
                    severity="medium",
                    confidence=0.70,
                )
            )
            recommendations.append(
                "إضافة سماد نيتروجيني (يوريا 46%) بمعدّل 50 كغ/هكتار خلال الأسبوع القادم."
            )

    # ── تأكّد من وجود توصية واحدة على الأقل ──────────────────────────────
    if not recommendations:
        recommendations.append(
            "الاستمرار في المراقبة الدوريّة للمحاصيل وتوثيق أيّ تغيّرات في الغطاء النباتي."
        )

    # ── حساب الثقة الكليّة ────────────────────────────────────────────────
    if factors:
        avg_conf = sum(f.confidence for f in factors) / len(factors)
        # وزّن ثقة قاعدة المعرفة
        rag_conf = numeric.get("rag_confidence", 0.5)
        overall_conf = 0.7 * avg_conf + 0.3 * rag_conf
    else:
        overall_conf = 0.3

    # ── بناء الملخّص العربي ───────────────────────────────────────────────
    factor_names = "، ".join(f.name for f in factors) if factors else "لا عوامل بارزة"
    causal_summary = ""
    if causal:
        first_link = causal[0]
        causal_summary = (
            f" الرابط السببي الرئيسي: {first_link.cause} ← {first_link.effect}"
            f" (ثقة {first_link.confidence:.0%})."
        )

    # إثراء الملخّص بالأنماط الزمنيّة (إن وُجدت أحداث تأخّر)
    delay_note = ""
    delay_events = temporal.get("delay_events", [])
    if delay_events:
        total_delay_days = sum(ev.get("days", 0) for ev in delay_events)
        delay_note = f" أيّام التأخّر التراكميّة في الري: {total_delay_days} يوم."

    summary = (
        f"تحليل الاستعلام: «{query}».\n"
        f"رُصدت العوامل التالية: {factor_names}.{causal_summary}{delay_note}\n"
        f"التوصيات: {len(recommendations)} إجراء مقترح بمستوى ثقة إجمالي {overall_conf:.0%}."
    )

    return Synthesis(
        summary=summary,
        factors=factors,
        recommendations=recommendations,
        confidence=overall_conf,
    )
