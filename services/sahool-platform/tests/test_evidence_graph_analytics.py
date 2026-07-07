"""تحقّق — تحليلات رسم الأدلّة (v149، منطق صرف): فجوات عبر الحقول + تسطيح رسم حقل.

- ``shape_gap_analytics``: أكثر الفجوات تكراراً (حقول مميَّزة/تكرارات)، توزيع الحالات،
  عدد الحقول المميَّزة؛ ترتيب حتميّ؛ مدخل شاذّ ⇒ أصفار.
- ``shape_field_graph``: عُقَد/حوافّ آخر لقطة + ملخّص؛ فارغ ⇒ available=False.
"""

from __future__ import annotations

import pytest
from core.evidence_graph_analytics import shape_field_graph, shape_gap_analytics

pytestmark = pytest.mark.unit


def test_gap_analytics_counts_distinct_fields_and_occurrences():
    rows = [
        {"field_id": "fld_a", "node_type": "terrain", "status": "missing"},
        {"field_id": "fld_b", "node_type": "terrain", "status": "missing"},
        {"field_id": "fld_a", "node_type": "soil_baseline", "status": "missing"},
        {"field_id": "fld_a", "node_type": "soil_baseline", "status": "present"},
        {"field_id": "fld_b", "node_type": "soil_baseline", "status": "present"},
    ]
    out = shape_gap_analytics(rows)
    assert out["fields_analyzed"] == 2
    # terrain غائب في حقلَين ⇒ يتصدّر؛ soil_baseline غائب في حقل واحد.
    gaps = {g["node_type"]: g for g in out["top_gaps"]}
    assert gaps["terrain"]["field_count"] == 2
    assert gaps["terrain"]["occurrence_count"] == 2
    assert gaps["soil_baseline"]["field_count"] == 1
    assert out["top_gaps"][0]["node_type"] == "terrain"  # الأكثر تكراراً أوّلاً


def test_gap_analytics_status_distribution_and_deterministic_order():
    rows = [
        {"field_id": "f1", "node_type": "a", "status": "present"},
        {"field_id": "f1", "node_type": "b", "status": "present"},
        {"field_id": "f1", "node_type": "c", "status": "missing"},
    ]
    out = shape_gap_analytics(rows)
    dist = {d["status"]: d["count"] for d in out["status_distribution"]}
    assert dist == {"present": 2, "missing": 1}
    # الأكثر أوّلاً (present قبل missing).
    assert out["status_distribution"][0]["status"] == "present"


def test_gap_analytics_malformed_yields_zeros():
    assert shape_gap_analytics(None) == {
        "fields_analyzed": 0,
        "top_gaps": [],
        "status_distribution": [],
    }
    # صفوف بلا status صالحة تُتجاهَل (لا اختلاق).
    out = shape_gap_analytics([{"field_id": "f", "node_type": "x"}, 42])
    assert out["fields_analyzed"] == 0 and out["top_gaps"] == []


def test_field_graph_flattens_nodes_edges_with_summary():
    node_rows = [
        {
            "node_id": "field",
            "node_type": "field",
            "source": None,
            "status": "present",
            "reason": None,
        },
        {
            "node_id": "gap:terrain",
            "node_type": "terrain",
            "source": None,
            "status": "missing",
            "reason": "no_terrain",
        },
    ]
    edge_rows = [
        {
            "edge_id": "field->has->gap:terrain",
            "edge_type": "has",
            "from_node": "field",
            "to_node": "gap:terrain",
        },
    ]
    out = shape_field_graph(node_rows, edge_rows)
    assert out["available"] is True
    assert out["summary"] == {
        "node_count": 2,
        "edge_count": 1,
        "present_count": 1,
        "gap_count": 1,
    }
    assert out["nodes"][1]["reason"] == "no_terrain"


def test_field_graph_empty_is_unavailable():
    out = shape_field_graph([], [])
    assert out["available"] is False
    assert out["nodes"] == [] and out["edges"] == []
    assert out["summary"]["node_count"] == 0
