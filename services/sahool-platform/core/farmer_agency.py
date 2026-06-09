"""
sahool_core.farmer_agency
==========================
استقلالية المزارع — درس مستفاد من تجارب عالمية فاشلة.

الدرس (Springer S-level + تجربة الزنجبيل):
  "الاعتماد المفرط على الخوارزميات يُفقد المزارع معرفته الموروثة وحدسه
   العملي. إن لم يفهم قرار الخوارزمية أو يتحدّاه، تضعف وكالته وتفكيره
   النقدي" → ظاهرة "Deskilling".

  مزارعون في تشيلي تخلّوا عن منصّة رقمية لأنها "أخذت منهم قرارهم"،
  واتّبعوها آلياً، وحين أخطأت الخوارزمية خسروا المحصول.

المبدأ: سهول "مساعد حذر" لا "طبيب يُصدر أوامر". كل توصية:
  • تُعرض كاقتراح لا أمر
  • تنتهي بسؤال "هل توافق؟"
  • إن رفض المزارع → يُسأل "لماذا؟" (تغذية راجعة للتعلّم)
  • رفض المزارع المتكرّر لنمط ما = إشارة أن الخوارزمية تخطئ محلياً

هذا يتسق مع مبدأ النواة: "في اليقين المنخفض لا تتظاهر باليقين"
(درس الزنجبيل: حتى لو لم يُحدَّد اسم المرض، يُقال 'مشتبه' لا 'طبيعي').
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FarmerResponse(str, Enum):
    PENDING = "pending"  # لم يردّ بعد
    ACCEPTED = "accepted"  # وافق
    REJECTED = "rejected"  # رفض
    MODIFIED = "modified"  # عدّل


@dataclass
class AdvisoryDecision:
    """توصية مع احتفاظ المزارع بقراره النهائي."""

    recommendation_ar: str
    confidence: str  # من نظام القرينة/الدليل
    response: FarmerResponse = FarmerResponse.PENDING
    why_rejected_ar: str | None = None  # سبب الرفض (للتعلّم)
    farmer_modification_ar: str | None = None
    framed_as_advice: bool = True  # دائماً اقتراح لا أمر

    def to_farmer_prompt(self) -> str:
        """صياغة التوصية كاقتراح ينتهي بسؤال — لا أمر."""
        return (
            f"اقتراح: {self.recommendation_ar}\n"
            f"(ثقة: {self.confidence})\n"
            f"هل توافق؟ يمكنك القبول أو التعديل أو الرفض. "
            f"قرارك النهائي — نحن نساعد لا نأمر."
        )


def record_farmer_response(
    decision: AdvisoryDecision,
    response: FarmerResponse,
    why_rejected_ar: str | None = None,
    modification_ar: str | None = None,
) -> AdvisoryDecision:
    """يسجّل ردّ المزارع. الرفض يتطلّب سبباً (تغذية راجعة للتعلّم)."""
    decision.response = response
    if response == FarmerResponse.REJECTED:
        decision.why_rejected_ar = why_rejected_ar or "(لم يُذكر سبب)"
    if response == FarmerResponse.MODIFIED:
        decision.farmer_modification_ar = modification_ar
    return decision


@dataclass
class RejectionPattern:
    """نمط رفض متكرّر = إشارة أن الخوارزمية قد تخطئ محلياً."""

    recommendation_type_ar: str
    total: int
    rejected: int
    rejection_rate: float
    signal_ar: str


def analyze_rejection_pattern(
    recommendation_type_ar: str,
    decisions: list[AdvisoryDecision],
) -> RejectionPattern:
    """يحلّل رفض المزارعين لنمط توصية. الرفض المتكرّر إشارة تعلّم:
    قد تكون الخوارزمية لا تناسب السياق المحلّي (درس تشيلي)."""
    total = len(decisions)
    rejected = sum(1 for d in decisions if d.response == FarmerResponse.REJECTED)
    rate = round(rejected / total, 2) if total else 0.0

    if total < 5:
        signal = "عيّنة صغيرة — لا نمط موثوق بعد"
    elif rate >= 0.4:
        signal = (
            "⚠️ رفض متكرّر (≥40%) — الخوارزمية قد لا تناسب السياق المحلّي. "
            "راجع التوصية واسمع تعليل المزارعين (حكمتهم الموروثة)"
        )
    elif rate >= 0.2:
        signal = "رفض متوسّط — راقب أسباب الرفض"
    else:
        signal = "قبول جيّد — التوصية متّسقة مع ممارسات المزارعين"

    return RejectionPattern(recommendation_type_ar, total, rejected, rate, signal)
