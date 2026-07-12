import pytest

try:
    from services.sahool_platform.core.decision_contracts import (
        DecisionContractViolation,
        EvidenceItem,
        EvidenceStrength,
        assert_no_decision_keys,
        compose_confidence,
        recommendation_inputs_from_context,
    )
    from services.sahool_platform.core.runtime_guardrail_adapter import (
        MissingCanonicalFieldState,
        guarded_runtime_context,
    )
except ModuleNotFoundError:
    from services.ai_agronomist.decision_contracts import (
        DecisionContractViolation,
        EvidenceItem,
        EvidenceStrength,
        assert_no_decision_keys,
        compose_confidence,
        recommendation_inputs_from_context,
    )
    from services.ai_agronomist.runtime_guardrail_adapter import (
        MissingCanonicalFieldState,
        guarded_runtime_context,
    )


def test_contract_scans_keys_not_free_text():
    assert_no_decision_keys({"note": "no recommendation available"}, layer="rag")
    with pytest.raises(DecisionContractViolation):
        assert_no_decision_keys({"recommendation": {"text": "irrigate"}}, layer="tool")


def test_rag_kg_are_annotations_not_recommendation_inputs():
    context = {
        "signals": {
            "lab": {"ec": 2.1},
            "weather": {"et0": 4.2},
            "rag": {"chunks": [1]},
            "kg": {"relations": [1]},
        }
    }
    inputs = recommendation_inputs_from_context(context)
    assert "lab" in inputs
    assert "weather" in inputs
    assert "rag" not in inputs
    assert "kg" not in inputs


def test_confidence_lab_outweighs_unverified_rag():
    confidence = compose_confidence(
        [
            EvidenceItem(EvidenceStrength.RAG, 1.0, verified=False),
            EvidenceItem(EvidenceStrength.LAB, 0.7, verified=True),
        ]
    )
    assert 0.7 <= confidence < 0.9


def test_runtime_requires_canonical_field_state():
    with pytest.raises(MissingCanonicalFieldState):
        guarded_runtime_context({"signals": {"weather": {"et0": 4.0}}})


def test_runtime_adapter_outputs_context_not_recommendation():
    out = guarded_runtime_context(
        {
            "canonical_field_state": {"field_id": "F-1", "status": "ready"},
            "signals": {"lab": {"ph": 7.1}, "rag": {"text": "supporting only"}},
            "tool_outputs": {"weather": {"note": "no recommendation available"}},
        }
    )
    assert out["canonical_field_state"]["status"] == "ready"
    assert "recommendation" not in out
    assert "rag" not in out["recommendation_inputs"]
