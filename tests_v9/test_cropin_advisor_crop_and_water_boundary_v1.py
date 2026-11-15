"""Advisor reads reference crop identity and canonical water without inventing decisions."""

import pytest

pytest.importorskip("fastapi")
from services.ai_agronomist import ai_evidence_runtime as ER  # noqa: E402


def test_field_crop_overrides_untrusted_request_scope():
    state = {
        "field_id": "field-a",
        "ai_context_pack": {
            "crop_knowledge": {"status": "reference_only", "crop_id": "wheat"},
        },
    }
    assert ER._trusted_crop_for_retrieval("maize", state, "field-a") == "wheat"


def test_field_with_no_governed_crop_must_not_retrieve_unscoped_graph():
    state = {
        "field_id": "field-a",
        "ai_context_pack": {"crop_knowledge": {"status": "unavailable"}},
    }
    assert ER._trusted_crop_for_retrieval("maize", state, "field-a") is None


def test_general_crop_question_can_use_declared_reference_crop():
    assert ER._trusted_crop_for_retrieval(" barley ", None, None) == "barley"


def test_water_tool_reads_owner_product_and_does_not_invent_productivity():
    field_state = {
        "field_id": "field-a",
        "canonical_field_state": {
            "water": {
                "field_id": "field-a",
                "quality_status": "verified",
                "depletion_mm": 12.5,
                "water_state_digest": "digest-1",
            },
        },
    }
    fetcher = ER._build_agent_tool_fetcher(
        field_state=field_state, ai_pack={"field_id": "field-a"}, annotations={}
    )
    result = fetcher("get_water_productivity", {"field_id": "field-a"})
    assert result["canonical_water_owner_present"] is True
    assert result["water_productivity"]["depletion_mm"] == 12.5
    assert result["productivity_measured"] is False


def test_water_tool_rejects_mismatched_owner_field():
    fetcher = ER._build_agent_tool_fetcher(
        field_state={
            "field_id": "field-a",
            "canonical_field_state": {"water": {"field_id": "field-b", "depletion_mm": 1}},
        },
        ai_pack={"field_id": "field-a"},
        annotations={},
    )
    with pytest.raises(ValueError, match="canonical_water_field_identity_mismatch"):
        fetcher("get_water_productivity", {"field_id": "field-a"})
