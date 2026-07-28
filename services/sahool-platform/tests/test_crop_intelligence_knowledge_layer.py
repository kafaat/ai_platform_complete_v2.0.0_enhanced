import pytest
from core.crop_intelligence.knowledge_layer import (
    KnowledgeAnnotation,
    build_crop_knowledge_snapshot,
    resolve_thermal_knowledge,
)


def test_builds_versioned_deterministic_crop_knowledge_snapshot():
    first = build_crop_knowledge_snapshot(crop_id="wheat")
    second = build_crop_knowledge_snapshot(crop_id="wheat")
    assert first["schema"] == "crop_knowledge_snapshot.v1"
    assert first["knowledge_digest"] == second["knowledge_digest"]
    assert first["core"]["thermal"]["gdd_to_maturity"] == 2000
    assert first["decision_boundary"]["is_decision"] is False


def test_variety_must_match_parent_crop():
    with pytest.raises(ValueError, match="parent crop"):
        build_crop_knowledge_snapshot(crop_id="barley", variety_id="wheat_aziz")


def test_unverified_regional_annotation_fails_closed():
    annotation = KnowledgeAnnotation(
        annotation_id="a1",
        kind="regional",
        payload={"note": "x"},
        source_type="district_baseline",
        source_id="district:1",
        version="1",
        verified=False,
    )
    with pytest.raises(ValueError, match="unverified regional"):
        build_crop_knowledge_snapshot(crop_id="wheat", annotations=[annotation])


def test_verified_annotation_is_provenanced_and_caps_confidence():
    annotation = KnowledgeAnnotation(
        annotation_id="a1",
        kind="regional",
        payload={"planting_window": "example"},
        source_type="district_baseline",
        source_id="district:1",
        version="2",
        verified=True,
    )
    out = build_crop_knowledge_snapshot(crop_id="wheat", annotations=[annotation])
    assert "knowledge:district:1@2" in out["source_ids"]
    assert out["confidence"] == "medium"


def test_community_knowledge_never_becomes_governing_high_confidence():
    annotation = KnowledgeAnnotation(
        annotation_id="folk-1",
        kind="community",
        payload={"observation": "rain marker"},
        source_type="farmer",
        source_id="farmer-note:1",
        version="1",
        verified=False,
    )
    out = build_crop_knowledge_snapshot(crop_id="wheat", annotations=[annotation])
    assert out["confidence"] == "low"
    assert out["decision_boundary"]["local_annotations_may_modify_not_override_governing"] is True


def test_duplicate_annotation_ids_fail_closed():
    item = KnowledgeAnnotation("dup", "community", {}, "farmer", "f:1", "1")
    with pytest.raises(ValueError, match="duplicate knowledge annotation ids"):
        build_crop_knowledge_snapshot(crop_id="wheat", annotations=[item, item])


def test_thermal_resolution_requires_canonical_snapshot():
    with pytest.raises(ValueError, match="not canonical"):
        resolve_thermal_knowledge({"schema": "other"})


def test_crop_engine_surfaces_knowledge_provenance_without_polluting_weather_evidence():
    from core.crop_intelligence.engine import build_crop_intelligence_state
    from core.crop_intelligence.models import CropIntelligenceInput

    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=100,
            gdd_to_maturity=None,
            source_ids=["field-source"],
        )
    )
    assert out["canonical_input_sources"]["crop_knowledge"] == "governed_knowledge_layer"
    assert out["knowledge_provenance"]["schema"] == "crop_knowledge_snapshot.v1"
    assert out["knowledge_provenance"]["knowledge_digest"]
    assert out["evidence_ids"] == ["field-source"]
