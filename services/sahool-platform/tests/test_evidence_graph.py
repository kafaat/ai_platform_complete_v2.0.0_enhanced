"""تحقّق — رسم أدلّة الحقل (Evidence Graph) منطق صرف.

- عقدة لكلّ دليل حاضر فقط؛ الأقسام الغائبة ⇒ knowledge_gaps بسببها (لا عقدة ملفّقة).
- حوافّ has_evidence (الحقل→دليل) + supports (دليل→توصية) عند وجود قرار.
- كلّ عقدة دليل تحمل مصدرها؛ latest_scene مصدره provider الفعليّ لا ثابت.
"""

from __future__ import annotations

from core.evidence_graph import build_evidence_graph


def _analyze_with(sections: dict, *, decision: dict | None = None) -> dict:
    return {
        "field_id": "f-1",
        "confidence": 0.7,
        "executable": False,
        "policy_decision": decision,
        "field_intelligence_card": {"sections": sections},
    }


def test_present_sections_become_nodes_missing_become_gaps():
    sections = {
        "latest_scene": {
            "status": "present",
            "provider": "element84",
            "acquisition_date": "2026-07-01",
        },
        "soil_baseline": {"status": "present", "texture": "طَفال", "ph": 7.4},
        "terrain": {"status": "missing", "reason": "no_terrain_supplied"},
        "weather_window": {"status": "missing", "reason": "no_weather_window_supplied"},
    }
    g = build_evidence_graph(_analyze_with(sections))
    ids = {n["id"] for n in g["nodes"]}
    assert "field" in ids and "evidence:latest_scene" in ids and "evidence:soil_baseline" in ids
    assert "evidence:terrain" not in ids  # غائب ⇒ لا عقدة (صدق)
    gap_keys = {gp["key"] for gp in g["knowledge_gaps"]}
    assert "terrain" in gap_keys and "weather_window" in gap_keys
    # حافّة has_evidence للحقل.
    assert {"from": "field", "to": "evidence:latest_scene", "rel": "has_evidence"} in g["edges"]


def test_scene_source_is_actual_provider_not_fabricated():
    sections = {"latest_scene": {"status": "present", "provider": "cdse"}}
    g = build_evidence_graph(_analyze_with(sections))
    scene = next(n for n in g["nodes"] if n["id"] == "evidence:latest_scene")
    assert scene["source"] == "cdse"  # المصدر الفعليّ من القسم
    soil_fixed = build_evidence_graph(
        _analyze_with({"soil_baseline": {"status": "present", "ph": 7.0}})
    )
    sb = next(n for n in soil_fixed["nodes"] if n["id"] == "evidence:soil_baseline")
    assert sb["source"] == "soilgrids"


def test_recommendation_node_and_supports_edges():
    sections = {
        "field_condition": {"status": "present", "effective_status": "salinity_limited"},
        "water_deficit": {"status": "present", "value": 18.0},
    }
    g = build_evidence_graph(_analyze_with(sections, decision={"action_type": "soil_remediation"}))
    assert g["summary"]["has_recommendation"] is True
    supports = [e for e in g["edges"] if e["rel"] == "supports"]
    # كلّ دليل حاضر يساند التوصية.
    assert {e["from"] for e in supports} == {"evidence:field_condition", "evidence:water_deficit"}
    assert all(e["to"] == "recommendation" for e in supports)


def test_no_recommendation_when_no_decision_and_honest_summary():
    g = build_evidence_graph(_analyze_with({"terrain": {"status": "missing", "reason": "x"}}))
    assert g["summary"]["has_recommendation"] is False
    assert g["summary"]["evidence_count"] == 0 and g["summary"]["gap_count"] >= 1
    # عقدة الحقل دائماً حاضرة.
    assert g["nodes"][0]["type"] == "field"


def test_empty_analyze_does_not_crash():
    g = build_evidence_graph({})
    assert g["schema"] == "sahool.evidence_graph/1"
    assert g["nodes"] == [{"id": "field", "type": "field", "label": "الحقل", "field_id": None}]
    assert g["edges"] == []
