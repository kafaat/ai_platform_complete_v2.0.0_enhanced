"""core/engines/human_escalation.py — تصعيد الشكّ لإنسان بدل إجابة آليّة مهلوسة.

الاستلهام (من مراجعة AI-CS «تبديل AI↔بشري»، متّسقاً مع confidence_gate القائم):
حين تنقص ثقة المصدر (محرّك قرار، **أو تأصيل RAG**) → **تصعيد لمرشد زراعي** بدل
إصدار توصية/إجابة منخفضة الثقة أو مولّدة بلا سند.

ما يضيفه (الفجوة المسدودة):
  • confidence_gate يقرّر CONFIDENT/REVIEW/BLOCKED للمحرّكات ✓ (موجود)
  • لكن لا **طلب تصعيد actionable** (لِمن؟ بأيّ أولويّة؟ ما المجهول؟) ✗
  • ولا تغطية لمسار **RAG/سؤال المعرفة** (قد يُجيب بلا سند كافٍ) ✗
هذا يعمّم المبدأ: أيّ ثقة (محرّك/RAG) → طلب تصعيد بشريّ شفّاف عند الشكّ.

⚠ المبدأ:
  • **human-in-the-loop**: الشكّ يُحوّل لإنسان، لا يُبتّ آليّاً (مبدأ confidence_gate نفسه)
  • **لا تأليف**: بلا سند كافٍ → لا إجابة مولّدة (BLOCKED) — تصعيد لا هلوسة
  • حتميّ شفّاف: عتبات صريحة، يُظهر المجهول والمستلِم والأولويّة
  • لا يستبدل المحرّكات — يضيف مخرَج التصعيد الـactionable فوقها
"""

from __future__ import annotations

from enum import Enum

# عتبات (شفّافة، تطابق روح confidence_gate: 0.80 يقين، 0.50 مراجعة).
CONFIDENT_FLOOR = 0.80  # ≥ ⇒ آليّ كافٍ (لا تصعيد)
REVIEW_FLOOR = 0.50  # [0.50,0.80) ⇒ مراجعة مرشد؛ دونها ⇒ محجوب (تصعيد حاكم)


class EscalationLevel(str, Enum):
    NONE = "none"  # ثقة كافية — لا تصعيد
    REVIEW = "review"  # مراجعة مرشد زراعي قبل التنفيذ
    BLOCKED = "blocked"  # لا إجابة آليّة (بلا سند/ثقة شديدة الانخفاض) — تصعيد حاكم


_RECIPIENT_AR = {
    EscalationLevel.REVIEW: "مرشد/مهندس زراعي (مراجعة قبل التنفيذ)",
    EscalationLevel.BLOCKED: "مرشد زراعي + توفير البيانات الناقصة (لا إجابة آليّة)",
    EscalationLevel.NONE: "",
}
_PRIORITY = {
    EscalationLevel.REVIEW: "medium",
    EscalationLevel.BLOCKED: "high",
    EscalationLevel.NONE: "none",
}


def assess_escalation(
    confidence: float | None,
    *,
    source: str,
    has_answer: bool = True,
    uncertain_points: list[str] | None = None,
    review_floor: float = REVIEW_FLOOR,
    confident_floor: float = CONFIDENT_FLOOR,
) -> dict:
    """يقرّر تصعيد الشكّ لإنسان من ثقة مصدر (محرّك/RAG) — حتميّ شفّاف.

    has_answer=False (مثلاً RAG بلا سند، أو ثقة None) → BLOCKED (لا تأليف إجابة).
    """
    pts = uncertain_points or []
    if not has_answer or confidence is None:
        level = EscalationLevel.BLOCKED
        reason = "لا سند/ثقة كافية لإجابة آليّة — تصعيد بشريّ (لا تأليف)."
    elif confidence >= confident_floor:
        level = EscalationLevel.NONE
        reason = f"ثقة {confidence:.0%} ≥ عتبة اليقين ({confident_floor:.0%}) — آليّ كافٍ."
    elif confidence >= review_floor:
        level = EscalationLevel.REVIEW
        reason = (
            f"ثقة {confidence:.0%} ضمن نطاق المراجعة "
            f"[{review_floor:.0%}, {confident_floor:.0%}) — مراجعة مرشد قبل التنفيذ."
        )
    else:
        level = EscalationLevel.BLOCKED
        reason = (
            f"ثقة {confidence:.0%} < عتبة المراجعة ({review_floor:.0%}) — تصعيد حاكم (لا إصدار)."
        )

    return {
        "source": source,
        "needs_escalation": level != EscalationLevel.NONE,
        "level": level.value,
        "recipient_role_ar": _RECIPIENT_AR[level],
        "priority": _PRIORITY[level],
        "confidence": round(confidence, 2) if confidence is not None else None,
        "uncertain_points_ar": pts,
        "reason_ar": reason,
        "honesty_note_ar": (
            "الشكّ يُحوّل لإنسان لا يُبتّ آليّاً (مبدأ confidence_gate). بلا سند/ثقة "
            "كافية: لا توصية/إجابة مولّدة — تصعيد لمرشد زراعي. شفّاف: يُظهر المجهول."
        ),
    }


def escalation_from_gate(gate_result: dict) -> dict:
    """يحوّل نتيجة confidence_gate (decision/overall_confidence/per_engine) إلى طلب تصعيد.

    يجسّر مخرَج البوّابة القائم إلى مخرَج تصعيد actionable (مستلِم/أولويّة/مجهول).
    """
    decision = (gate_result or {}).get("decision", "review")
    conf = (gate_result or {}).get("overall_confidence")
    # نقاط المجهول من فجوات بيانات المحرّكات.
    pts: list[str] = []
    for e in (gate_result or {}).get("per_engine", []):
        pts.extend(e.get("data_gaps_ar", []) or [])
        if e.get("blocking_reason_ar"):
            pts.append(f"{e.get('engine')}: {e['blocking_reason_ar']}")

    if decision == "confident":
        out = assess_escalation(conf if conf is not None else 1.0, source="confidence_gate")
    elif decision == "blocked":
        out = assess_escalation(
            None, source="confidence_gate", has_answer=False, uncertain_points=sorted(set(pts))
        )
    else:  # review
        # ثقة ضمن نطاق المراجعة (نضمن REVIEW حتى لو conf مفقودة).
        c = conf if conf is not None else (REVIEW_FLOOR + CONFIDENT_FLOOR) / 2
        out = assess_escalation(
            min(c, CONFIDENT_FLOOR - 0.01),
            source="confidence_gate",
            uncertain_points=sorted(set(pts)),
        )
    out["gate_decision"] = decision
    return out
