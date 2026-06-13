"""اختبارات تصعيد الشكّ لإنسان (offline) — عتبات + actionable + جسر البوّابة.

يتحقّق من: ثقة عالية → لا تصعيد؛ متوسّطة → مراجعة مرشد؛ منخفضة/بلا سند → محجوب
(لا تأليف)؛ وتحويل نتيجة confidence_gate إلى طلب تصعيد actionable (مستلِم/أولويّة/مجهول).
"""

from core.engines.human_escalation import (
    EscalationLevel,
    assess_escalation,
    escalation_from_gate,
)

# ─── assess_escalation (أيّ مصدر ثقة: محرّك/RAG) ──────────────────────────


def test_high_confidence_no_escalation():
    out = assess_escalation(0.9, source="rag")
    assert out["level"] == EscalationLevel.NONE.value
    assert out["needs_escalation"] is False
    assert out["priority"] == "none"


def test_medium_confidence_escalates_to_agronomist_review():
    out = assess_escalation(0.65, source="irrigation")
    assert out["level"] == EscalationLevel.REVIEW.value
    assert out["needs_escalation"] is True
    assert "مرشد" in out["recipient_role_ar"]
    assert out["priority"] == "medium"


def test_low_confidence_is_blocked_high_priority():
    out = assess_escalation(0.30, source="rag")
    assert out["level"] == EscalationLevel.BLOCKED.value
    assert out["priority"] == "high"


def test_no_answer_blocks_without_fabrication():
    # بلا سند (مثلاً RAG بلا مصدر) ⇒ محجوب، لا إجابة مولّدة (صدق)
    out = assess_escalation(None, source="knowledge_qa", has_answer=False)
    assert out["level"] == EscalationLevel.BLOCKED.value
    assert out["needs_escalation"] is True
    assert out["confidence"] is None
    assert "لا" in out["reason_ar"]


def test_uncertain_points_passed_through():
    out = assess_escalation(0.6, source="diagnosis", uncertain_points=["لا تحليل تربة حديث"])
    assert out["uncertain_points_ar"] == ["لا تحليل تربة حديث"]


# ─── escalation_from_gate (جسر confidence_gate القائم) ────────────────────


def test_gate_confident_no_escalation():
    out = escalation_from_gate(
        {"decision": "confident", "overall_confidence": 0.9, "per_engine": []}
    )
    assert out["needs_escalation"] is False
    assert out["gate_decision"] == "confident"


def test_gate_review_becomes_actionable_request():
    gate = {
        "decision": "review",
        "overall_confidence": 0.6,
        "per_engine": [{"engine": "nutrient", "data_gaps_ar": ["لا تحليل تربة"]}],
    }
    out = escalation_from_gate(gate)
    assert out["level"] == EscalationLevel.REVIEW.value
    assert out["needs_escalation"] is True
    assert "لا تحليل تربة" in out["uncertain_points_ar"]
    assert "مرشد" in out["recipient_role_ar"]


def test_gate_blocked_maps_to_blocked_escalation():
    gate = {
        "decision": "blocked",
        "overall_confidence": 0.0,
        "per_engine": [{"engine": "diagnosis", "blocking_reason_ar": "لا مؤشّر حديث"}],
    }
    out = escalation_from_gate(gate)
    assert out["level"] == EscalationLevel.BLOCKED.value
    assert out["priority"] == "high"
    assert any("لا مؤشّر حديث" in p for p in out["uncertain_points_ar"])


def test_gate_review_with_low_confidence_stays_review_not_blocked():
    # قرار البوّابة review لكن الثقة دون عتبة المراجعة — يجب أن يبقى REVIEW (قرار
    # البوّابة)، لا يُصعَّد BLOCKED بسبب القصّ من جهة واحدة فقط.
    out = escalation_from_gate({"decision": "review", "overall_confidence": 0.30, "per_engine": []})
    assert out["level"] == EscalationLevel.REVIEW.value
    assert out["gate_decision"] == "review"
