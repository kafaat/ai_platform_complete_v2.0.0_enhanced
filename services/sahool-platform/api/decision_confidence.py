"""api/decision_confidence.py — دمج ثقة القرار (Decision Confidence Fusion، read-only)

يجمع مصادر الثقة الأربعة في **ثقة قرار موحَّدة شفّافة** لحقل:

    Decision Confidence = Satellite + Weather + Sensor Confidence + Evidence

كلّ مصدر **اختياريّ**: المتوفّر يُوزَن ويُدمَج؛ الغائب **يُعلَن** ولا يُفترَض. هذه طبقة
**عرض ثقة** ترفع موثوقيّة القرار الموحَّد — **لا تُعدّل القرار** ولا تنفّذ شيئاً.

**نمط الصدق**: التركيبة معادلة موزونة **مُوثَّقة** (لا نموذج معايَر) على المكوّنات
المتوفّرة فقط (إعادة تطبيع الأوزان)؛ لا مكوّن أصلاً ⇒ ``insufficient`` (لا «ثقة
افتراضيّة»). الأوزان تقديريّة موسومة. ``calibrated`` غير منطبق ⇒ ``not_applicable``.

نقيّ حتميّ (لا قاعدة، لا I/O) — قابل للاختبار offline؛ يستهلكه ``routers/decision_confidence``.
"""

from __future__ import annotations

# أوزان مصادر الثقة (تُطبَّع على المتوفّر فقط). ⚠ تقديريّة موسومة، غير معايَرة.
_WEIGHTS = {
    "sensor": 0.30,  # ثقة الحسّاس (صحّة أجهزة الحقل) — أقوى إشارة آنيّة
    "evidence": 0.25,  # الدليل المُدام (تحقّق ميدانيّ متراكم)
    "satellite": 0.25,  # نضارة الاستشعار (حداثة NDVI)
    "weather": 0.20,  # ثقة تنبّؤ الطقس
}
_SOURCES = ("sensor", "evidence", "satellite", "weather")

_SOURCE_AR = {
    "sensor": "ثقة الحسّاس",
    "evidence": "الدليل الميدانيّ",
    "satellite": "نضارة الاستشعار",
    "weather": "ثقة الطقس",
}

_LEVEL_AR = {
    "high": "عالية",
    "medium": "متوسّطة",
    "low": "منخفضة",
    "insufficient": "غير كافية (يحتاج بيانات)",
}


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def fuse_decision_confidence(components: dict, *, generated_at: str | None = None) -> dict:
    """يدمج مصادر الثقة المتوفّرة في ثقة قرار موحَّدة — نقيّ حتميّ، عرض فقط.

    ``components``: قاموس لكلّ مصدر (sensor/evidence/satellite/weather) قيمته
    ``{"value": float|None (0..1), "detail_ar": str|None}`` — ``value`` None يعني المصدر
    غير متوفّر (يُعلَن missing لا يُفترَض).

    الناتج: ``confidence`` (0..1 أو None)، ``level`` (high/medium/low/insufficient) +
    ``level_ar``، ``components`` (لكلّ مصدر value/weight/available/detail) + ``missing`` +
    ``provenance``. صدق: التركيبة على المتوفّر فقط؛ لا مصدر ⇒ insufficient.
    """
    c = components or {}
    present: dict[str, float] = {}
    out_components: list[dict] = []
    missing: list[str] = []

    for key in _SOURCES:
        comp = c.get(key) or {}
        raw = comp.get("value")
        available = raw is not None
        value = _clamp(raw) if available else None
        if available:
            present[key] = value
        else:
            missing.append(key)
        out_components.append(
            {
                "source": key,
                "label_ar": _SOURCE_AR[key],
                "weight": _WEIGHTS[key],
                "value": round(value, 3) if value is not None else None,
                "available": available,
                "detail_ar": comp.get("detail_ar"),
            }
        )

    if present:
        wsum = sum(_WEIGHTS[k] for k in present)
        confidence = round(_clamp(sum(present[k] * _WEIGHTS[k] for k in present) / wsum), 3)
    else:
        confidence = None

    if confidence is None:
        level = "insufficient"
    elif confidence >= 0.75:
        level = "high"
    elif confidence >= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "generated_at": generated_at,
        "confidence": confidence,
        "level": level,
        "level_ar": _LEVEL_AR[level],
        "components": out_components,
        "present_count": len(present),
        "missing": missing,
        "provenance": {
            "calibrated": "not_applicable",
            "note_ar": (
                "ثقة القرار تركيبة موزونة شفّافة (حسّاس/دليل/استشعار/طقس) على المصادر "
                "المتوفّرة فقط — الأوزان تقديريّة غير معايَرة، والمصدر الغائب يُعلَن missing "
                "ولا يُفترَض. عرض فقط لا يُعدّل القرار."
            ),
        },
    }
