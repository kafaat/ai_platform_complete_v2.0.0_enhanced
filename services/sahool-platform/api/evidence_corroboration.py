"""
api/evidence_corroboration.py — تظافر القرائن ودرجات التوصية

المبدأ (اتّفقنا عليه): **تظافر القرائن المستقلّة المتّفقة يرقى بدرجة الثقة.**
قرينة ضعيفة واحدة (استشعار، قرينة إقليميّة من مزارع مجاورة، ملاحظة ميدانيّة)
لا تكفي وحدها لقرار تسميد؛ لكنّ **عدّة قرائن مستقلّة تتّفق** ترفع الثقة درجةً.
ومع ذلك تبقى التوصية **موسومة بدرجتها**، مع حضّ المزارع على فحص تربة/مياه
للارتقاء للدرجة الأعلى (المختبر).

درجات التوصية (سُلَّم صريح):
  INDICATIVE   (إرشاديّة)  — قرينة واحدة ضعيفة أو متوسّطة → اتّجاه عامّ فقط
  CORROBORATED (مؤيَّدة)   — ≥2 قرينة مستقلّة تتّفق → ثقة أعلى، ما زالت دون المختبر
  CONFIRMED    (مؤكَّدة)   — قياس مختبري للحقل موجود → الدرجة العليا

القرائن وأوزانها (مستقلّة = من مصادر مختلفة الطبيعة):
  • lab_field      : تحليل مختبري للحقل نفسه          (قويّة جدّاً — حاسمة)
  • regional_prior : عيّنات مزارع مجاورة (نفس المنطقة)  (متوسّطة)
  • remote_sensing : مؤشّر قمر صناعي (NDVI/SI/BSI)      (ضعيفة-متوسّطة)
  • field_obs      : ملاحظة ميدانيّة/أعراض مرئيّة         (ضعيفة)
  • historical     : سجلّ مواسم سابقة للحقل             (متوسّطة)

⚠ حدّ صارم محفوظ: الفوسفور والمغذّيات الدقيقة تتغيّر حقلاً بحقل ولا توقيع
استشعاري موثوق لها → لا ترقى أبداً لـCONFIRMED دون مختبر الحقل، مهما تظافرت
القرائن غير المختبريّة. هذا يجسّد "الاستشعار يوجّه / المختبر يحكم".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class RecommendationTier(str, Enum):
    INDICATIVE = "indicative"      # إرشاديّة (قرينة ضعيفة)
    CORROBORATED = "corroborated"  # مؤيَّدة (قرائن متظافرة)
    CONFIRMED = "confirmed"        # مؤكَّدة (مختبر الحقل)


class EvidenceType(str, Enum):
    LAB_FIELD = "lab_field"
    REGIONAL_PRIOR = "regional_prior"
    REMOTE_SENSING = "remote_sensing"
    FIELD_OBS = "field_obs"
    HISTORICAL = "historical"
    CROP_MODEL = "crop_model"  # نموذج حسابي فيزيائي (FAO-56 ميزان الماء، WOFOST)
    COMMUNITY_KNOWLEDGE = "community_knowledge"  # معرفة مجتمعيّة/تقويم زراعي تجريبي


# أوزان القرائن (قوّة كلّ نوع منفرداً)
_EVIDENCE_WEIGHT: Dict[EvidenceType, float] = {
    EvidenceType.LAB_FIELD: 1.0,
    EvidenceType.REGIONAL_PRIOR: 0.5,
    EvidenceType.HISTORICAL: 0.5,
    # نموذج المحصول: حساب فيزيائي معايَر (FAO-56) — متين، لكن لا يرى واقع
    # الحقل الفعلي (لا يقيس التربة/الآفات مباشرةً) → أقوى من الاستشعار، أدنى من المختبر
    EvidenceType.CROP_MODEL: 0.45,
    EvidenceType.REMOTE_SENSING: 0.4,
    EvidenceType.FIELD_OBS: 0.3,
    # المعرفة المجتمعيّة: قرينة تجريبيّة مشروعة (ملاحظة تراكميّة عبر أجيال)
    # لكن غير موثّقة وقد تخلط السبب بالوكيل → وزن منخفض، لا تُرجّح وحدها قراراً
    EvidenceType.COMMUNITY_KNOWLEDGE: 0.25,
}

_EVIDENCE_AR: Dict[EvidenceType, str] = {
    EvidenceType.LAB_FIELD: "تحليل مختبري للحقل",
    EvidenceType.REGIONAL_PRIOR: "عيّنات مزارع مجاورة",
    EvidenceType.REMOTE_SENSING: "مؤشّر استشعار (قمر صناعي)",
    EvidenceType.FIELD_OBS: "ملاحظة ميدانيّة",
    EvidenceType.HISTORICAL: "سجلّ مواسم سابقة",
    EvidenceType.CROP_MODEL: "نموذج حسابي (ميزان الماء FAO-56)",
    EvidenceType.COMMUNITY_KNOWLEDGE: "معرفة مجتمعيّة/تقويم زراعي محلّي",
}

# عناصر تتغيّر حقلاً بحقل: لا ترقى لـCONFIRMED دون مختبر الحقل
_LAB_GATED_NUTRIENTS = {"phosphorus", "micronutrients", "potassium"}


def _has_non_community_signal(agreeing: List["Evidence"]) -> bool:
    """هل في القرائن المتّفقة قرينة موضوعيّة واحدة على الأقلّ (لا مجتمعيّة فقط)؟"""
    return any(e.etype != EvidenceType.COMMUNITY_KNOWLEDGE for e in agreeing)


@dataclass
class Evidence:
    """قرينة واحدة تشير لنتيجة."""
    etype: EvidenceType
    agrees: bool                 # هل تتّفق مع بقيّة القرائن على نفس الاتّجاه؟
    note_ar: str = ""


@dataclass
class CorroborationResult:
    tier: RecommendationTier
    tier_ar: str
    evidence_score: float
    n_independent: int
    n_agreeing: int
    has_field_lab: bool
    nudge_ar: Optional[str]      # حضّ على الفحص (لو لم يبلغ CONFIRMED)
    explanation_ar: str
    evidence_summary: List[Dict]

    def to_dict(self) -> Dict:
        return {
            "tier": self.tier.value,
            "tier_ar": self.tier_ar,
            "evidence_score": round(self.evidence_score, 2),
            "n_independent": self.n_independent,
            "n_agreeing": self.n_agreeing,
            "has_field_lab": self.has_field_lab,
            "nudge_ar": self.nudge_ar,
            "explanation_ar": self.explanation_ar,
            "evidence_summary": self.evidence_summary,
        }


_TIER_AR = {
    RecommendationTier.INDICATIVE: "إرشاديّة",
    RecommendationTier.CORROBORATED: "مؤيَّدة بقرائن متظافرة",
    RecommendationTier.CONFIRMED: "مؤكَّدة بتحليل مختبري",
}


def corroborate(
    evidences: List[Evidence],
    *,
    recommendation_key: str = "general",
    test_type_ar: str = "تربة",
) -> CorroborationResult:
    """يحدّد درجة التوصية بناءً على تظافر القرائن.

    Args:
        evidences: القرائن المتاحة.
        recommendation_key: نوع التوصية (لتطبيق حدّ المختبر على بعضها).
        test_type_ar: نوع الفحص المقترح في الحضّ ("تربة" أو "مياه").
    """
    agreeing = [e for e in evidences if e.agrees]
    n_independent = len({e.etype for e in evidences})
    n_agreeing = len({e.etype for e in agreeing})

    has_field_lab = any(
        e.etype == EvidenceType.LAB_FIELD and e.agrees for e in evidences
    )
    # مجموع أوزان القرائن المتّفقة (مستقلّة)
    score = sum(_EVIDENCE_WEIGHT[t] for t in {e.etype for e in agreeing})

    is_lab_gated = recommendation_key in _LAB_GATED_NUTRIENTS

    # تحديد الدرجة
    if has_field_lab:
        tier = RecommendationTier.CONFIRMED
    elif is_lab_gated:
        # عناصر حقل-بحقل: لا ترقى فوق إرشاديّة دون مختبر مهما تظافرت
        tier = RecommendationTier.INDICATIVE
    elif n_agreeing >= 2 and score >= 0.8 and _has_non_community_signal(agreeing):
        # ترقى لمؤيَّدة فقط لو التظافر يشمل قرينة موضوعيّة واحدة على الأقلّ
        # (المعرفة المجتمعيّة وحدها لا ترفع الدرجة — تجريبيّة لا مقيسة)
        tier = RecommendationTier.CORROBORATED
    else:
        tier = RecommendationTier.INDICATIVE

    # الحضّ على الفحص (لكلّ ما دون CONFIRMED)
    nudge = None
    if tier != RecommendationTier.CONFIRMED:
        if is_lab_gated:
            nudge = (
                f"هذه التوصية إرشاديّة فقط. {recommendation_key} يتغيّر من حقل لآخر "
                f"ولا يُحدَّد بدقّة إلّا بفحص {test_type_ar} مختبري لحقلك. "
                "أنصح بإجراء الفحص قبل أيّ تطبيق."
            )
        elif tier == RecommendationTier.CORROBORATED:
            nudge = (
                f"التوصية مؤيَّدة بـ{n_agreeing} قرائن متّفقة — ثقة جيّدة للتوجيه. "
                f"للارتقاء لأعلى دقّة، أجرِ فحص {test_type_ar} مختبري لحقلك "
                "(يرفعها إلى 'مؤكَّدة')."
            )
        else:
            nudge = (
                f"التوصية إرشاديّة (قرينة محدودة). لتوصية أدقّ، أجرِ فحص "
                f"{test_type_ar} مختبري لحقلك — هو الأعلى أثراً الآن."
            )

    # شرح شفّاف
    parts = []
    if has_field_lab:
        parts.append("يوجد تحليل مختبري للحقل (الدرجة العليا)")
    else:
        if n_agreeing >= 2:
            parts.append(f"{n_agreeing} قرائن مستقلّة تتّفق (تظافر)")
        elif n_agreeing == 1:
            parts.append("قرينة واحدة فقط")
        else:
            parts.append("لا قرائن متّفقة")
        if is_lab_gated:
            parts.append(f"لكنّ '{recommendation_key}' يتغيّر حقلاً بحقل → يبقى إرشاديّاً دون مختبر")
    explanation = "؛ ".join(parts) + "."

    return CorroborationResult(
        tier=tier, tier_ar=_TIER_AR[tier], evidence_score=score,
        n_independent=n_independent, n_agreeing=n_agreeing,
        has_field_lab=has_field_lab, nudge_ar=nudge,
        explanation_ar=explanation,
        evidence_summary=[
            {"type_ar": _EVIDENCE_AR[e.etype], "agrees": e.agrees, "note_ar": e.note_ar}
            for e in evidences
        ],
    )
