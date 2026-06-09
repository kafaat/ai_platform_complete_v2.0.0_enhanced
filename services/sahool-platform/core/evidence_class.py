"""
sahool_core.evidence_class
===========================
تقنين التمييز: بعض المؤشّرات قرينة (indication)، وبعضها دليل (evidence).

الملاحظة الجوهرية: المؤشّر الطيفي يشير ويرجّح — لا يُثبت ويُلزِم.
التحليل المخبري يُثبت ويحكم. خلط الاثنين يكسر صدق المنصّة.

  قرينة (INDICATION):  ترجّح وتوجّه — لا تبني قراراً قاطعاً
    أمثلة: NDVI, BSI, SI, LAI, تقدير النسيج (مؤشّرات طيفية)
    → ثقة منخفضة، توجّه لأخذ دليل، لا ترفع BLOCKED

  دليل (EVIDENCE):     يُثبت ويَحكم — يبني قراراً قاطعاً
    أمثلة: EC مخبري, pH مخبري, كيمياء المياه (تحاليل)
    → ثقة عالية، يرفع BLOCKED، يفتح التوصية الدقيقة

هذه الوحدة تفرض القاعدة برمجياً: لا قرينة تُعامَل معاملة دليل.
تربط أنواع مصفوفة المشاهدات بطبيعتها (قرينة/دليل) وتفرض الحدود.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class EvidenceClass(str, Enum):
    INDICATION = "indication"   # قرينة — ترجّح لا تُلزِم
    EVIDENCE = "evidence"       # دليل — يُثبت ويَحكم


# ربط أنواع مصفوفة المشاهدات بطبيعتها (قرينة/دليل)
_TYPE_TO_CLASS = {
    # أدلّة: تبني قرارات قاطعة، ترفع BLOCKED
    "governing": EvidenceClass.EVIDENCE,
    "governing_strict": EvidenceClass.EVIDENCE,
    "governing_trees": EvidenceClass.EVIDENCE,
    "calibration": EvidenceClass.EVIDENCE,    # معايرة من قياس حقيقي
    "feasibility": EvidenceClass.EVIDENCE,
    # قرائن: ترجّح وتوجّه، لا تُلزِم
    "diagnostic": EvidenceClass.INDICATION,   # المؤشّرات الطيفية
    "modifying": EvidenceClass.INDICATION,    # عوامل مُعدِّلة (ترجّح)
}


@dataclass
class EvidenceRuling:
    """حكم على مشاهدة: أقرينة هي أم دليل، وما يجوز بناؤه عليها."""
    observable_id: str
    observation_type: str
    evidence_class: EvidenceClass
    can_govern_decision: bool   # هل تبني قراراً قاطعاً؟
    can_lift_blocked: bool      # هل ترفع حالة BLOCKED؟
    max_confidence: str         # سقف الثقة المسموح
    note_ar: str


def classify_evidence(observable_id: str, observation_type: str) -> EvidenceRuling:
    """يصنّف مشاهدة كقرينة أو دليل، ويحدّد ما يجوز بناؤه عليها.
    القاعدة المركزية: القرينة لا تُلزِم، الدليل يُلزِم."""
    ec = _TYPE_TO_CLASS.get(observation_type, EvidenceClass.INDICATION)  # الافتراض الآمن: قرينة

    if ec == EvidenceClass.EVIDENCE:
        return EvidenceRuling(
            observable_id=observable_id,
            observation_type=observation_type,
            evidence_class=ec,
            can_govern_decision=True,
            can_lift_blocked=True,
            max_confidence="high",
            note_ar=f"{observable_id}: دليل — يبني قراراً قاطعاً ويرفع BLOCKED",
        )
    return EvidenceRuling(
        observable_id=observable_id,
        observation_type=observation_type,
        evidence_class=ec,
        can_govern_decision=False,
        can_lift_blocked=False,
        max_confidence="low",   # القرينة سقفها ثقة منخفضة
        note_ar=f"{observable_id}: قرينة — ترجّح وتوجّه، لا تبني قراراً قاطعاً "
                f"ولا ترفع BLOCKED. تحتاج دليلاً (تحليل) للحسم",
    )


def enforce_indication_ceiling(observable_id: str, observation_type: str,
                               proposed_confidence: str) -> dict:
    """يفرض سقف ثقة القرينة: حتى لو اقترح النظام ثقة عالية لقرينة، تُخفَّض.
    يمنع معاملة القرينة معاملة الدليل (خطأ يكسر الصدق)."""
    ruling = classify_evidence(observable_id, observation_type)
    levels = {"none": 0, "low": 1, "medium": 2, "high": 3}
    proposed = levels.get(proposed_confidence, 1)
    ceiling = levels.get(ruling.max_confidence, 1)

    if ruling.evidence_class == EvidenceClass.INDICATION and proposed > ceiling:
        return {
            "allowed_confidence": ruling.max_confidence,
            "was_capped": True,
            "note_ar": (f"{observable_id} قرينة طيفية — خُفضت الثقة من "
                        f"'{proposed_confidence}' إلى '{ruling.max_confidence}'. "
                        f"القرينة لا تُعامَل معاملة الدليل."),
        }
    return {
        "allowed_confidence": proposed_confidence,
        "was_capped": False,
        "note_ar": f"{observable_id}: الثقة '{proposed_confidence}' ضمن المسموح",
    }


def explain_evidence_principle_ar() -> str:
    """شرح المبدأ للعرض في الواجهة/التوثيق."""
    return (
        "في سهول، نميّز بين القرينة والدليل:\n"
        "• القرينة (مؤشّر طيفي كـ NDVI أو نوع تربة تقديري): ترجّح وتوجّه — "
        "تساعدك تعرف أين تنظر، لكنها لا تحسم وحدها.\n"
        "• الدليل (تحليل مخبري كـ EC أو pH): يحسم ويبني التوصية الدقيقة.\n"
        "لهذا قد نقول 'تربتك تبدو مالحة (قرينة من الأقمار) — حلّلها لنتأكّد (دليل)'. "
        "هذا ليس ضعفاً، بل صدق: لا نبني قراراً قاطعاً على قرينة."
    )


# ════════════════════════════════════════════════════════════
# تضافر القرائن (Corroboration): قرائن متّفقة قد ترقى — بحدود
# ════════════════════════════════════════════════════════════
@dataclass
class Corroboration:
    """نتيجة تضافر عدّة قرائن حول نفس الاستنتاج."""
    target_ar: str              # ما تشير إليه (مثل: ملوحة)
    n_indications: int          # عدد القرائن
    n_independent_sources: int  # عدد المصادر المستقلّة فعلاً
    agree: bool                 # هل تتّفق؟
    elevated_confidence: str    # الثقة بعد التضافر
    can_govern: bool            # هل ترقى لتحكم؟ (شبه دائماً False للحاكمات)
    lifts_blocked: bool         # هل ترفع BLOCKED؟
    note_ar: str


# تصنيف مصدر كل قرينة (للحكم على الاستقلال)
_INDICATION_SOURCE = {
    "NDVI": "optical_satellite", "NDMI": "optical_satellite",
    "NDWI": "optical_satellite", "SI": "optical_satellite",
    "BSI": "optical_satellite", "LAI": "optical_satellite",
    "CWSI": "thermal", "RVI": "radar", "RSMI": "radar",
    "district_context": "neighbor_data", "farmer_obs": "ground",
}


def corroborate_indications(
    target_ar: str,
    indications: "list[tuple[str, bool]]",  # (observable_id, agrees_with_target)
    *,
    is_strict_governor: bool = False,       # هل الهدف حاكم صارم (ملوحة/pH/سلامة)؟
) -> Corroboration:
    """يقيّم تضافر عدّة قرائن. ترقى الثقة مع الاتفاق والاستقلال —
    لكن لا تبلغ الدليل المخبري للحاكمات الصارمة.

    المبدأ: تضافر القرائن المستقلّة المتّفقة يرفع الثقة (low→medium)،
    لكن قرائن من نفس المصدر (كلها أقمار بصرية) تشترك في الخطأ فلا
    تتضافر بالكامل. والحاكم الصارم يبقى يتطلّب دليلاً مخبرياً."""
    agreeing = [(oid, a) for oid, a in indications if a]
    disagreeing = [(oid, a) for oid, a in indications if not a]
    n = len(agreeing)
    n_conflict = len(disagreeing)
    # عدّ المصادر المستقلّة (لا القرائن — قرائن نفس المصدر تُحسب مرّة)
    sources = {_INDICATION_SOURCE.get(oid, "unknown") for oid, _ in agreeing}
    n_independent = len(sources)

    # قرينة مخالفة تُضعف التضافر (لا تُتجاهَل). التناقض يقلّل الثقة.
    # إن خالفت قرينة واحدة أو أكثر، لا يُسمح بالترقّي الكامل.
    if n_conflict > 0:
        if n_conflict >= n:
            # المخالف ≥ المتّفق → لا تضافر موثوق
            return Corroboration(target_ar, n, n_independent, False, "low",
                False, False,
                f"{target_ar}: قرائن متضاربة ({n} مع، {n_conflict} ضد) — "
                f"التناقض يلغي التضافر. تبقى ثقة منخفضة، يلزم دليل للحسم")
        # أقلّية مخالفة → ترقٍّ مكبوح بدرجة واحدة (التناقض يُضعف)
        _conflict_penalty = True
    else:
        _conflict_penalty = False

    if n < 2:
        return Corroboration(target_ar, n, n_independent, False, "low",
            False, False,
            f"{target_ar}: قرينة واحدة فقط — لا تضافر. تبقى ثقة منخفضة")

    if not (n >= 2 and all(a for _, a in agreeing)):
        return Corroboration(target_ar, n, n_independent, False, "low",
            False, False,
            f"{target_ar}: القرائن لا تتّفق — لا ترقى")

    # الترقّي يعتمد على الاستقلال: مصادر مستقلّة متعدّدة ترفع أكثر
    if n_independent >= 3:
        elevated = "high" if not is_strict_governor else "medium"
    elif n_independent >= 2:
        elevated = "medium"
    else:
        # قرائن متعدّدة لكن من مصدر واحد (كلها بصرية) — ترقّ محدود
        elevated = "low_plus"

    # الحدّ الحاسم: الحاكم الصارم لا يُحسم بالقرائن مهما تضافرت
    if is_strict_governor:
        can_gov, lifts = False, False
        verdict = (f"قرائن متضافرة قوية على {target_ar} "
                   f"({n} قرينة من {n_independent} مصدر مستقلّ) → "
                   f"ثقة {elevated}. **أولوية عالية للتحليل المخبري** — "
                   f"لكن الحاكم الصارم يبقى يتطلّب دليلاً مخبرياً، "
                   f"لا تُحسمه القرائن.")
    else:
        # غير الحاكم: تضافر قوي قد يكفي لقرار غير حرج
        can_gov = (n_independent >= 3)
        lifts = False  # التضافر لا يرفع BLOCKED، حتى لغير الحاكم
        verdict = (f"قرائن متضافرة على {target_ar} "
                   f"({n} قرينة من {n_independent} مصدر) → ثقة {elevated}. "
                   f"{'كافية لقرار استرشادي قوي' if can_gov else 'ترجّح بقوّة'}.")

    return Corroboration(target_ar, n, n_independent, True, elevated,
        can_gov, lifts, verdict)
