"""تحقّق — تطبيع رسم الأدلّة إلى صفوف عُقَد/حوافّ (المرحلة 2، منطق صرف).

- يشتقّ عُقَداً حاضرة من nodes + غائبة (gap:*) من knowledge_gaps بسببها.
- يشتقّ حوافّ من edges (edge_id = from->rel->to).
- لا تكرار node/edge لنفس اللقطة؛ لا أسرار في source؛ لا attrs (حمولة حدّ أدنى).
"""

from __future__ import annotations

from core.evidence_graph_normalize import normalize_graph_to_rows

_GRAPH = {
    "nodes": [
        {"id": "field", "type": "field"},
        {"id": "evidence:soil_baseline", "type": "soil_baseline", "source": "soilgrids"},
        {"id": "recommendation", "type": "recommendation"},
    ],
    "edges": [
        {"from": "field", "to": "evidence:soil_baseline", "rel": "has_evidence"},
        {"from": "evidence:soil_baseline", "to": "recommendation", "rel": "supports"},
    ],
    "knowledge_gaps": [{"key": "terrain", "label": "التضاريس", "reason": "no_terrain_supplied"}],
}


def test_derives_present_nodes_and_missing_gap_nodes():
    rows = normalize_graph_to_rows(_GRAPH)
    by_id = {n["node_id"]: n for n in rows["nodes"]}
    assert by_id["evidence:soil_baseline"]["status"] == "present"
    assert by_id["evidence:soil_baseline"]["source"] == "soilgrids"
    # فجوة ⇒ عقدة missing بسببها (node_id=gap:terrain).
    assert by_id["gap:terrain"]["status"] == "missing"
    assert by_id["gap:terrain"]["reason"] == "no_terrain_supplied"
    assert by_id["gap:terrain"]["source"] is None


def test_derives_edges_with_synthesized_id():
    rows = normalize_graph_to_rows(_GRAPH)
    eids = {e["edge_id"]: e for e in rows["edges"]}
    assert "field->has_evidence->evidence:soil_baseline" in eids
    supp = eids["evidence:soil_baseline->supports->recommendation"]
    assert supp["edge_type"] == "supports" and supp["from_node"] == "evidence:soil_baseline"


def test_no_duplicate_nodes_or_edges_and_minimal_payload():
    dup = {
        "nodes": [
            {"id": "field", "type": "field"},
            {"id": "field", "type": "field"},  # مكرّر
        ],
        "edges": [
            {"from": "a", "to": "b", "rel": "supports"},
            {"from": "a", "to": "b", "rel": "supports"},  # مكرّر
        ],
    }
    rows = normalize_graph_to_rows(dup)
    assert len([n for n in rows["nodes"] if n["node_id"] == "field"]) == 1
    assert len(rows["edges"]) == 1
    # حمولة حدّ أدنى: لا attrs (لا أسرار تُطبَّع).
    for n in rows["nodes"]:
        assert set(n.keys()) == {"node_id", "node_type", "source", "status", "reason"}


def test_source_that_looks_like_secret_is_dropped():
    g = {"nodes": [{"id": "x", "type": "t", "source": "Bearer secret_token_123"}]}
    n = normalize_graph_to_rows(g)["nodes"][0]
    assert n["source"] is None  # أمن: لا نُطبِّع قيمة تشبه سرّاً


def test_malformed_graph_yields_empty_rows():
    assert normalize_graph_to_rows(None) == {"nodes": [], "edges": []}
    assert normalize_graph_to_rows({"nodes": [42], "edges": ["x"]}) == {"nodes": [], "edges": []}
