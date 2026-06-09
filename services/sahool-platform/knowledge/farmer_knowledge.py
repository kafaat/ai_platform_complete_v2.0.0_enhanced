"""
knowledge.farmer_knowledge
==========================
المعرفة المحلية المهيكلة — المحور الأول في إطار FAO.

ليست نصاً حرّاً، بل أصل معرفي قابل للتحقق. كل معرفة تمرّ بنفس صرامة
دستور بناء المعلومة: نوع + نطاق + آلية + تحقّق + ثقة + صلاحية.

التصنيف الخماسي (حاسم — يمنع تسرّب الخرافة):
  spatial    (١) ملاحظة مكانية: "هذه البقعة مالحة" — قيمة عالية، تسدّ فجوة المراصد
  temporal   (٢) ملاحظة زمنية: "الرياح الشرقية تجفّف" — أنماط مناخية محلية
  varietal   (٣) معرفة الأصناف: "العلس يتحمّل الجفاف" — كنز، تحتاج تحقّق
  practice   (٤) ممارسة تراثية: "الري الفجري أفضل" — تُفحص (حكمة أم عادة؟)
  causal     (٥) تفسير سببي: "القمر رفع الماء" — تُرفض إن بلا آلية فيزيائية

القاعدة الذهبية: المعرفة المحلية = prior بايزي قابل للتحقق، لا حقيقة مطلقة.
  - تؤكّدها البيانات → ترفع الثقة (prior قوي)
  - تناقضها البيانات → تُسجّل كتعارض للدراسة (لا تُرفض ولا تُتّبع عمياء)

الفخاخ المحصَّن ضدها: تحيّز البقاء، الارتباط الوهمي، التقادم المناخي، التعميم.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class KnowledgeType(str, Enum):
    SPATIAL = "spatial"       # مكانية — أعلى قيمة، أقل عرضة للتحيّز
    TEMPORAL = "temporal"     # زمنية — أنماط محلية
    VARIETAL = "varietal"     # أصناف — كنز نادر
    PRACTICE = "practice"     # ممارسة — تُفحص
    CAUSAL = "causal"         # سببية — تُرفض إن بلا آلية


class VerificationStatus(str, Enum):
    PENDING = "pending"           # لم يُتحقّق بعد
    CONFIRMED = "confirmed"       # البيانات تؤكّدها
    CONTRADICTED = "contradicted" # البيانات تناقضها — للدراسة
    UNVERIFIABLE = "unverifiable" # لا سبيل للتحقّق حالياً
    REJECTED = "rejected"         # لا آلية فيزيائية (خرافة)


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


# أنواع لا تُقبل بلا آلية فيزيائية مُثبتة (حماية من الخرافة)
_REQUIRES_MECHANISM = {KnowledgeType.CAUSAL}

# قيمة كل نوع كـ prior (مدى موثوقيته المبدئية قبل التحقق)
_TYPE_PRIOR_STRENGTH = {
    KnowledgeType.SPATIAL: 0.7,    # ملاحظة مباشرة متكررة
    KnowledgeType.TEMPORAL: 0.5,   # عرضة للتحيّز الزمني
    KnowledgeType.VARIETAL: 0.6,   # قيّمة لكن تحتاج تأكيداً
    KnowledgeType.PRACTICE: 0.4,   # قد تكون عادة لا حكمة
    KnowledgeType.CAUSAL: 0.1,     # افتراضياً ضعيفة حتى تُثبت الآلية
}

# سقف صارم لوزن المعرفة المحلية/المجتمعية (قرار المستخدم).
# تُرجّح وتوجّه، لكنها لا تُحدّد القرار. متّسق مع conservative_rag (الأدبيات ≤0.15).
COMMUNITY_WEIGHT_CEILING = 0.15

# مراصد حاكمة/فيزيائية: المعرفة المحلية لا تمسّها إطلاقاً (وزن = صفر مطلق).
# الفيزياء والمختبر يحكمان هنا، مهما بلغ إجماع المزارعين.
GOVERNING_PHYSICS_OBSERVABLES = {
    "S3", "S4", "S5", "I3", "L3",       # الحاكمات الصارمة
    "ET0", "ETc", "ETa",                # الحسابات الفيزيائية
}


def applicable_weight(fk: "FarmerKnowledge", target_observable: str) -> float:
    """الوزن الفعّال للمعرفة عند تطبيقها على مرصد معيّن.
    صفر مطلق على الحاكمات/الفيزياء — القاعدة الذهبية: المعرفة لا تكسر الفيزياء."""
    if target_observable in GOVERNING_PHYSICS_OBSERVABLES:
        return 0.0
    return fk.prior_weight


@dataclass
class FarmerKnowledge:
    """وحدة معرفة محلية مهيكلة وقابلة للتحقق."""
    knowledge_id: str
    knowledge_type: KnowledgeType
    content_ar: str                       # ما قاله المزارع
    tenant_id: str
    district_id: str
    spatial_scope: str                    # النطاق المكاني الدقيق (حقل/منطقة/بقعة)
    farmer_confidence: Confidence         # ثقة المزارع نفسه
    mechanism_ar: str = ""                # الآلية الفيزيائية المقترحة (إن وُجدت)
    verification_method: str = ""         # كيف نتحقّق (ndvi/lab/trial...)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    data_agreement: bool | None = None    # هل البيانات تطابقها؟
    review_year: int | None = None        # متى نراجع (drift مناخي)
    source_ar: str = "المزارع/الخبرة المتراكمة"

    def __post_init__(self):
        # حماية: نوع سببي بلا آلية → يُرفض تلقائياً
        if self.knowledge_type in _REQUIRES_MECHANISM and not self.mechanism_ar:
            self.verification_status = VerificationStatus.REJECTED

    @property
    def computed_confidence(self) -> Confidence:
        """الثقة = دالة (النوع، حالة التحقق، تطابق البيانات).
        لا تُمنح ثقة عالية بلا تحقق — حتى لو كان المزارع واثقاً."""
        if self.verification_status == VerificationStatus.REJECTED:
            return Confidence.UNKNOWN
        if self.verification_status == VerificationStatus.CONFIRMED and self.data_agreement:
            return Confidence.HIGH
        if self.verification_status == VerificationStatus.CONTRADICTED:
            return Confidence.LOW   # تعارض — لا تُتّبع
        if self.verification_status == VerificationStatus.PENDING:
            # prior فقط — لم يُتحقّق بعد
            strength = _TYPE_PRIOR_STRENGTH[self.knowledge_type]
            return Confidence.MEDIUM if strength >= 0.6 else Confidence.LOW
        return Confidence.UNKNOWN

    @property
    def prior_weight(self) -> float:
        """وزن بايزي محافظ. قرار المستخدم: المعرفة المحلية وزن صغير
        مقابل المصادر الأخرى — سقف صارم 0.15 (كـ conservative_rag).
        صفر إن مرفوضة أو متعارضة."""
        if self.verification_status in (
            VerificationStatus.REJECTED, VerificationStatus.CONTRADICTED
        ):
            return 0.0
        # النوع يحدّد نسبة من السقف؛ التحقّق يرفع ضمن السقف، لا فوقه.
        base = _TYPE_PRIOR_STRENGTH[self.knowledge_type]   # 0.1..0.7
        scaled = base * COMMUNITY_WEIGHT_CEILING           # ≤ 0.105
        if self.verification_status == VerificationStatus.CONFIRMED and self.data_agreement:
            scaled = min(scaled * 1.4, COMMUNITY_WEIGHT_CEILING)  # يبلغ السقف بالتحقّق
        return round(scaled, 3)

    def explain_ar(self) -> str:
        status_ar = {
            "pending": "قيد التحقّق", "confirmed": "مؤكّدة بالبيانات",
            "contradicted": "تعارضها البيانات", "unverifiable": "غير قابلة للتحقّق",
            "rejected": "مرفوضة (بلا آلية)",
        }
        return (
            f"[{self.knowledge_type.value}] {self.content_ar} | "
            f"النطاق: {self.spatial_scope} | "
            f"{status_ar.get(self.verification_status.value)} | "
            f"ثقة: {self.computed_confidence.value}"
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["knowledge_type"] = self.knowledge_type.value
        d["farmer_confidence"] = self.farmer_confidence.value
        d["verification_status"] = self.verification_status.value
        d["computed_confidence"] = self.computed_confidence.value
        d["prior_weight"] = round(self.prior_weight, 3)
        return d


def verify_against_data(
    knowledge: FarmerKnowledge,
    data_supports: bool,
) -> FarmerKnowledge:
    """تحديث حالة التحقّق بناءً على مقارنة البيانات (NDVI/مخبري/تجربة).

    لا تُرفض المعرفة عند التعارض — تُسجّل للدراسة (قد يكون الحساس مخطئاً،
    أو المعرفة متقادمة). الشفافية لا الإقصاء."""
    if knowledge.verification_status == VerificationStatus.REJECTED:
        return knowledge   # سببية بلا آلية تبقى مرفوضة
    knowledge.data_agreement = data_supports
    knowledge.verification_status = (
        VerificationStatus.CONFIRMED if data_supports
        else VerificationStatus.CONTRADICTED
    )
    return knowledge
