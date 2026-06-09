"""
api/confidence_gate.py — بوابة الثقة الموحّدة

مُستلهَمة من فكرة "Confidence Gate" في مستندات DSS، لكن **مُكيّفة بصدق**:
ليست ensemble ML غامض، بل طبقة قرار شفّافة تجمع مخرجات محرّكاتنا (الريّ،
التسميد 4R، التشخيص، المناطق) وتقرّر مستوى الثقة بصراحة:

  CONFIDENT  → بيانات كافية + لا تضارب → توصية جاهزة
  REVIEW     → ثقة متوسّطة أو نقص جزئي → تحتاj مراجعة بشريّة (مهندس)
  BLOCKED    → نقص بيانات حاكمة (لا تحليل مختبر، لا مؤشّر حديث) → لا توصية

تجسّد ثلاثة مبادئ:
  • "الاستشعار يوجّه / المختبر يحكم" → نقص المختبر = BLOCKED
  • "rule-based before ML" → لا نموذج غامض؛ قواعد شفّافة
  • human-in-the-loop → الشكّ يُحوّل لإنسان، لا يُبتّ آليّاً

⚠ لا تتنبّأ بشيء جديد — تنظّم صدق ما تنتجه المحرّكات. كلّ قرار مُعلَّل.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class GateDecision(str, Enum):
    CONFIDENT = "confident"   # توصية جاهزة
    REVIEW = "review"         # مراجعة بشريّة
    BLOCKED = "blocked"       # محجوبة (نقص حاكم)


@dataclass
class EngineSignal:
    """إشارة من محرّك واحد للبوابة."""
    engine: str               # "irrigation" | "nutrient" | "diagnosis" | "zones"
    has_recommendation: bool  # هل أنتج المحرّك توصية؟
    confidence: float         # 0-1 (ثقة المحرّك في توصيته)
    blocking_reason_ar: Optional[str] = None  # سبب الحجب إن وُجد
    data_gaps_ar: List[str] = field(default_factory=list)  # بيانات ناقصة


@dataclass
class GateResult:
    decision: GateDecision
    overall_confidence: float
    reason_ar: str
    next_action_ar: str
    per_engine: List[Dict]

    def to_dict(self) -> Dict:
        return {
            "decision": self.decision.value,
            "overall_confidence": round(self.overall_confidence, 2),
            "reason_ar": self.reason_ar,
            "next_action_ar": self.next_action_ar,
            "per_engine": self.per_engine,
        }


# عتبات الثقة (شفّافة، قابلة للضبط)
_CONFIDENT_THRESHOLD = 0.80
_REVIEW_THRESHOLD = 0.50


def evaluate(signals: List[EngineSignal]) -> GateResult:
    """يقيّم إشارات المحرّكات ويقرّر مستوى الثقة الموحّد.

    منطق القرار (مرتّب بالأولويّة):
      ١. أيّ محرّك BLOCKED لسبب حاكم (نقص مختبر) → BLOCKED كلّيّاً
      ٢. متوسّط الثقة عالٍ + كلّها أنتجت → CONFIDENT
      ٣. غير ذلك → REVIEW (مراجعة بشريّة)
    """
    if not signals:
        return GateResult(
            decision=GateDecision.REVIEW, overall_confidence=0.0,
            reason_ar="لا إشارات من المحرّكات.",
            next_action_ar="أدخل بيانات الحقل أوّلاً.",
            per_engine=[],
        )

    per_engine = []
    blocked_reasons = []
    all_gaps = []
    confidences = []

    for s in signals:
        per_engine.append({
            "engine": s.engine,
            "has_recommendation": s.has_recommendation,
            "confidence": round(s.confidence, 2),
            "blocking_reason_ar": s.blocking_reason_ar,
            "data_gaps_ar": s.data_gaps_ar,
        })
        if not s.has_recommendation and s.blocking_reason_ar:
            blocked_reasons.append(f"{s.engine}: {s.blocking_reason_ar}")
        all_gaps.extend(s.data_gaps_ar)
        if s.has_recommendation:
            confidences.append(s.confidence)

    # ١. حجب حاكم
    if blocked_reasons:
        return GateResult(
            decision=GateDecision.BLOCKED,
            overall_confidence=0.0,
            reason_ar="محجوب: " + "؛ ".join(blocked_reasons),
            next_action_ar=(
                "وفّر البيانات الناقصة (غالباً تحليل مختبري) قبل أيّ توصية. "
                "الاستشعار يوجّه لكنّ المختبر يحكم."
            ),
            per_engine=per_engine,
        )

    overall = sum(confidences) / len(confidences) if confidences else 0.0

    # ٢. واثقة
    if overall >= _CONFIDENT_THRESHOLD and not all_gaps:
        return GateResult(
            decision=GateDecision.CONFIDENT,
            overall_confidence=overall,
            reason_ar=f"إجماع المحرّكات بثقة {overall:.0%} وبيانات كافية.",
            next_action_ar="التوصية جاهزة للعرض على المزارع.",
            per_engine=per_engine,
        )

    # ٣. مراجعة بشريّة
    gap_note = (" ملاحظات نقص: " + "، ".join(set(all_gaps))) if all_gaps else ""
    return GateResult(
        decision=GateDecision.REVIEW,
        overall_confidence=overall,
        reason_ar=f"ثقة {overall:.0%} دون عتبة اليقين ({_CONFIDENT_THRESHOLD:.0%}).{gap_note}",
        next_action_ar=(
            "حوّل لمراجعة مهندس زراعي قبل التنفيذ. لا تُصدر توصية آليّة عند الشكّ."
        ),
        per_engine=per_engine,
    )
