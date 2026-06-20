"""api/evidence_map.py — طبقة تشكيل نقيّة لخريطة الدليل (Evidence Map، #4)

تحوّل تجميعات الدليل المُدام لكلّ حقل (عدد القرارات في ``decision_record`` + عدد القياسات
الميدانيّة في ``outcome_record``) إلى **مستوى دليل لكلّ حقل** للعرض على الخريطة/القائمة:
**لا تعرض النتيجة وحدها، بل مستوى الدليل خلفها**.

المستويات (تتبع مفردات ``evidence_registry`` المُدامة — لا مفردات جديدة):
  • ``field_verified``    (مؤكَّد ميدانيّاً) — قياسات ميدانيّة ≥ عتبة التحقّق.
  • ``field_preliminary`` (مدعوم أوّليّاً)  — 0 < قياسات < العتبة.
  • ``indicative``        (إرشاديّ)        — قرار/نموذج فقط، بلا قياس ميدانيّ بعد.
  • ``needs_data``        (يحتاج بيانات)   — لا قرار ولا قياس لهذا الحقل (لا تلفيق).

**الصدق**: العتبة تقديريّة **موسومة** (تطابق ``evidence_registry._FIELD_VERIFIED_MIN_
SAMPLES``)؛ لا ترقية مستوى دون قياس مُدام فعليّ؛ الحقل بلا دليل يُعلَن ``needs_data``
لا «أخضر» افتراضيّ. ``calibrated`` غير منطبق على تجميع عدّ ⇒ ``not_applicable``.

نقيّ حتميّ (لا قاعدة، لا I/O) — قابل للاختبار offline؛ يستهلكه ``routers/evidence_map``.
"""

from __future__ import annotations

# عتبة التحقّق الميدانيّ (عدد القياسات) — تطابق evidence_registry. ⚠ تقديريّ غير معايَر.
EVIDENCE_VERIFIED_MIN_SAMPLES = 30

# ترتيب المستويات (للأسوأ→الأفضل) + وسوم العرض (لا منطق ألوان في الواجهة يُختلَق).
_TIER_AR = {
    "field_verified": "مؤكَّد ميدانيّاً",
    "field_preliminary": "مدعوم (أوّليّ)",
    "indicative": "إرشاديّ",
    "needs_data": "يحتاج بيانات",
}
_TIER_COLOR = {
    "field_verified": "green",
    "field_preliminary": "amber",
    "indicative": "blue",
    "needs_data": "gray",
}


def _as_int(value) -> int:
    """عدّ خام → int غير سالب (None/شاذّ ⇒ 0). حارس ضدّ قيم القاعدة الشاذّة."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


def _classify(decisions: int, outcomes: int) -> str:
    """يصنّف مستوى دليل حقل من عدد قراراته وقياساته المُدامة — حتميّ شفّاف.

    لا قرار ولا قياس ⇒ needs_data (لا تلفيق). قياسات ≥ العتبة ⇒ field_verified. قياسات
    أقلّ ⇒ field_preliminary. قرار بلا قياس ⇒ indicative (نموذج فقط، لم يُتحقَّق ميدانيّاً).
    """
    if outcomes >= EVIDENCE_VERIFIED_MIN_SAMPLES:
        return "field_verified"
    if outcomes > 0:
        return "field_preliminary"
    if decisions > 0:
        return "indicative"
    return "needs_data"


def _has_coords(field: dict) -> bool:
    """هل للحقل إحداثيّتان رقميّتان حقيقيّتان؟ (لا تَفبرِك موقعاً للرسم)."""
    lat, lon = field.get("lat"), field.get("lon")
    try:
        float(lat)
        float(lon)
    except (TypeError, ValueError):
        return False
    return lat is not None and lon is not None


def shape_evidence_map(fields: list[dict], *, generated_at: str | None = None) -> dict:
    """يبني جسم خريطة الدليل من تجميعات الحقول الخام — نقيّ (لا قاعدة).

    ``fields``: قائمة قواميس لكلّ حقل (best-effort): ``field_id``، ``name``، ``crop``،
    ``gov``، ``lat``/``lon`` (قد تغيب)، ``decisions`` (عدد decision_record)، ``outcomes``
    (عدد outcome_record)، ``successes`` (عدد success=TRUE)، ``last_outcome_at`` (ISO|None).

    الناتج: ``generated_at`` + ``legend`` (المستويات بوسومها) + ``fields`` (لكلّ حقل
    tier/tier_ar/color + has_coords + عدّاداته) + ``totals_by_tier`` + ``provenance``.
    صدق: المستوى من العدّ المُدام فقط؛ needs_data يُعلَن صراحةً.
    """
    out_fields: list[dict] = []
    totals: dict[str, int] = {t: 0 for t in _TIER_AR}
    plottable = 0

    for f in fields or []:
        decisions = _as_int(f.get("decisions"))
        outcomes = _as_int(f.get("outcomes"))
        successes = _as_int(f.get("successes"))
        tier = _classify(decisions, outcomes)
        totals[tier] += 1
        has_coords = _has_coords(f)
        if has_coords:
            plottable += 1
        success_rate = round(successes / outcomes, 3) if outcomes > 0 else None
        out_fields.append(
            {
                "field_id": f.get("field_id"),
                "name": f.get("name"),
                "crop": f.get("crop"),
                "gov": f.get("gov"),
                "lat": f.get("lat") if has_coords else None,
                "lon": f.get("lon") if has_coords else None,
                "has_coords": has_coords,
                "decisions": decisions,
                "outcomes": outcomes,
                "successes": successes,
                "success_rate": success_rate,
                "samples_to_verified": max(0, EVIDENCE_VERIFIED_MIN_SAMPLES - outcomes),
                "last_outcome_at": f.get("last_outcome_at"),
                "tier": tier,
                "tier_ar": _TIER_AR[tier],
                "color": _TIER_COLOR[tier],
            }
        )

    legend = [
        {"tier": t, "tier_ar": _TIER_AR[t], "color": _TIER_COLOR[t]}
        for t in ("field_verified", "field_preliminary", "indicative", "needs_data")
    ]

    return {
        "generated_at": generated_at,
        "legend": legend,
        "fields": out_fields,
        "totals_by_tier": totals,
        "field_count": len(out_fields),
        "plottable_count": plottable,
        "verified_threshold": EVIDENCE_VERIFIED_MIN_SAMPLES,
        "provenance": {
            "calibrated": "not_applicable",
            "note_ar": (
                "مستوى الدليل من القرارات/القياسات المُدامة فقط؛ عتبة التحقّق الميدانيّ "
                f"({EVIDENCE_VERIFIED_MIN_SAMPLES}) تقديريّة غير معايَرة. الحقل بلا دليل ⇒ "
                "needs_data (لا تلوين افتراضيّ، لا تلفيق)."
            ),
        },
    }
