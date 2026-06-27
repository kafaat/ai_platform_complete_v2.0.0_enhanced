from __future__ import annotations

import pytest
from core.canonical_field_state_lock import (
    DecisionFirewallError,
    FieldAnnotation,
    FieldSignal,
    compose_locked_field_state,
)
from core.conversation_tree import ConversationNode, ConversationTree
from core.daily_ai_brief import build_daily_ai_brief
from core.hybrid_rag_retrieval import RagChunk, hybrid_retrieve
from core.mcp_service_servers import default_mcp_servers
from core.prescription_exports import (
    MachineProfile,
    PrescriptionZoneRate,
    export_geojson,
    export_isoxml,
)

pytestmark = pytest.mark.unit


def _chunk(cid: str, tenant: str, doc: str, idx: int, text: str, **meta):
    metadata = {"evidence_level": "manual", "crop": "wheat", **meta}
    return RagChunk(
        chunk_id=cid,
        tenant_id=tenant,
        document_id=doc,
        chunk_index=idx,
        total_chunks=3,
        text=text,
        metadata=metadata,
    )


def test_hybrid_rag_filters_tenant_expands_neighbors_and_reranks():
    corpus = [
        _chunk("a0", "t1", "doc-a", 0, "مقدمة عن القمح"),
        _chunk("a1", "t1", "doc-a", 1, "ملوحة التربة EC تؤثر على القمح"),
        _chunk("a2", "t1", "doc-a", 2, "إدارة الري"),
        _chunk("b1", "t2", "doc-b", 1, "tenant آخر لا يجب أن يظهر"),
    ]
    out = hybrid_retrieve(
        query="EC القمح",
        dense_ranked=[corpus[1], corpus[3]],
        sparse_ranked=[corpus[1], corpus[0]],
        corpus=corpus,
        tenant_id="t1",
        metadata_filters={"crop": "wheat"},
        top_k=3,
    )
    assert [r.chunk.tenant_id for r in out] == ["t1", "t1", "t1"]
    assert out[0].chunk.chunk_id == "a1"
    assert any(r.role == "neighbor" for r in out)
    assert all(r.annotation["verified"] is False for r in out)


def test_rag_chunk_cannot_claim_lab_evidence():
    with pytest.raises(ValueError):
        _chunk("x", "t1", "doc", 0, "lab", evidence_level="lab")


def test_canonical_field_state_firewall_excludes_rag_and_kg_from_decision_inputs():
    state = compose_locked_field_state(
        field_id="F1",
        tenant_id="T1",
        signals=[
            FieldSignal("soil_ec", "lab", 4.2, True, "governing", "lab"),
            FieldSignal("ndvi", "satellite", 0.55, False, "indication", "sentinel"),
        ],
        annotations=[
            FieldAnnotation("rag_note", "rag", {"text": "manual says irrigate"}, "rag"),
            FieldAnnotation("kg_edge", "kg", {"relation": "historically_limits"}, "kg"),
        ],
    )
    assert state.recommendation_inputs == {"soil_ec": 4.2}
    assert len(state.explanatory_annotations) == 2
    assert all(a["verified"] is False for a in state.explanatory_annotations)


def test_annotation_cannot_be_verified_evidence():
    with pytest.raises(DecisionFirewallError):
        FieldAnnotation("kg", "kg", {}, "kg", verified=True)


def test_daily_ai_brief_compresses_actions_and_blocks_precise_fertilization_without_lab():
    brief = build_daily_ai_brief(
        field_id="F1",
        field_state={"irrigation_state": "due", "salinity_risk": "high", "has_lab": False},
        weather_alerts=["الرياح غير مناسبة للرش بعد الظهر"],
        tasks_due=[{"title": "أخذ عينة تربة"}],
        equipment_alerts=["المضخة 2 تحتاج فحص"],
        review_queue_count=1,
    )
    assert "إجراء" in brief.headline_ar
    assert len(brief.items) == 6
    assert any("التسميد الدقيق" in b for b in brief.blocked)
    artifact = brief.as_artifact()
    assert artifact["artifact_type"] == "daily_ai_brief"


def test_prescription_export_geojson_and_isoxml_fail_closed_without_machine_profile():
    zone = PrescriptionZoneRate(
        zone_id="Z1",
        rate=120,
        unit="kg/ha",
        geometry={"type": "Polygon", "coordinates": []},
    )
    geojson = export_geojson([zone])
    assert geojson["type"] == "FeatureCollection"
    assert geojson["features"][0]["properties"]["rate"] == 120
    with pytest.raises(ValueError):
        export_isoxml("rx1", [zone], None)
    xml = export_isoxml("rx1", [zone], MachineProfile("John Deere", "Gen4", True))
    assert b"ISO11783_TaskData" in xml
    assert b"kg/ha" in xml


def test_mcp_server_specs_cover_real_services_and_keep_rag_kg_annotation_only():
    specs = default_mcp_servers()
    names = {s.name for s in specs}
    assert {
        "weather-mcp-server",
        "lab-mcp-server",
        "satellite-mcp-server",
        "rag-mcp-server",
        "kg-mcp-server",
    }.issubset(names)
    for spec in specs:
        if spec.service in {"rag", "knowledge-graph"}:
            assert spec.output_contract == "annotation"


def test_conversation_tree_branch_diff_and_path():
    tree = ConversationTree()
    tree.add(ConversationNode("root", None, "base", "ري 30 مم", {"policy": "lab"}))
    a = tree.branch("root", "a", "lab only", "ري 30 مم", {"policy": "lab"})
    b = tree.branch("root", "b", "lab plus rag", "ري 35 مم", {"policy": "lab+rag"})
    assert "35" in tree.diff(a.node_id, b.node_id)
    assert [n.node_id for n in tree.path_to_root("b")] == ["root", "b"]
