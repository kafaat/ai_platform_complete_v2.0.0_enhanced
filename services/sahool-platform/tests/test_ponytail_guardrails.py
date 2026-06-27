import pytest
from core.recommendation_ponytail import (
    InsufficientEvidenceError,
    PonytailEvidence,
    PonytailIntent,
    RecommendationPonytail,
)


def test_simple_irrigation_uses_direct_answer_without_rag():
    decision = RecommendationPonytail().filter(
        PonytailIntent(intent_type="irrigation", complexity="simple_query"),
        PonytailEvidence(has_field_state=True, confidence="medium"),
        field_state={"irrigation_state": "due_tomorrow"},
    )
    assert decision.action == "direct_answer"
    assert decision.allowed_tools == []
    assert decision.max_chunks == 0


def test_fertilization_requires_lab_evidence():
    with pytest.raises(InsufficientEvidenceError):
        RecommendationPonytail().filter(
            PonytailIntent(intent_type="fertilization"),
            PonytailEvidence(has_lab=False, confidence="medium"),
        )


def test_pesticide_goes_to_human_review_and_never_prescription():
    decision = RecommendationPonytail().filter(
        PonytailIntent(intent_type="pesticide", risk_domain="pesticide"),
        PonytailEvidence(has_phi=True, confidence="high"),
    )
    assert decision.action == "human_review"
    assert decision.requires_human_review is True
    assert decision.may_create_prescription is False
    with pytest.raises(AttributeError):
        _ = decision.recommendation
