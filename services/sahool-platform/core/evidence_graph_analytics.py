"""core/evidence_graph_analytics.py — تحليلات رسم الأدلّة عبر الحقول/الزمن — منطق صرف.

يشتقّ من صفوف جدولَي v149 (``evidence_graph_nodes``/``_edges``، **مصدرها لقطة v148 JSONB**)
تجميعات تحليليّة يصعب حسابها على JSONB مباشرةً: أكثر فجوات المعرفة تكراراً عبر حقول
المستأجِر، توزيع الحالات، وعدد الحقول المُحلَّلة. + تسطيح رسم حقل واحد للعرض.

**صدق:** لا تلفيق — مدخل فارغ/شاذّ ⇒ تجميعات صفريّة صريحة. التجميع على **آخر لقطة لكلّ
حقل** (يُمرّرها الراوت عبر ``DISTINCT ON``)؛ هذه الدالّة تُجمِّع الصفوف الجاهزة فقط.
"""

from __future__ import annotations

from typing import Any

_MISSING = "missing"


def shape_gap_analytics(rows: Any) -> dict[str, Any]:
    """يُجمِّع صفوف ``{field_id, node_type, status}`` (آخر لقطة/حقل) إلى تحليلات.

    يُرجِع:
      • ``fields_analyzed``: عدد الحقول المميَّزة ذات لقطة.
      • ``top_gaps``: ``[{node_type, field_count, occurrence_count}]`` تنازليّاً — أكثر
        أنواع الأدلّة **غياباً** عبر الحقول (status=missing). ``field_count`` = حقول
        مميَّزة تنقصها، ``occurrence_count`` = مجموع صفوف الغياب.
      • ``status_distribution``: ``[{status, count}]`` لكلّ الحالات.
    مدخل شاذّ/فارغ ⇒ أصفار صريحة (لا اختلاق).
    """
    fields: set[str] = set()
    status_counts: dict[str, int] = {}
    gap_fields: dict[str, set[str]] = {}
    gap_occurrences: dict[str, int] = {}

    for r in rows if isinstance(rows, (list, tuple)) else []:
        if not isinstance(r, dict):
            continue
        fid = r.get("field_id")
        ntype = r.get("node_type")
        status = r.get("status")
        if not isinstance(status, str) or not status:
            continue
        if isinstance(fid, str) and fid:
            fields.add(fid)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == _MISSING and isinstance(ntype, str) and ntype:
            gap_occurrences[ntype] = gap_occurrences.get(ntype, 0) + 1
            if isinstance(fid, str) and fid:
                gap_fields.setdefault(ntype, set()).add(fid)

    top_gaps = [
        {
            "node_type": nt,
            "field_count": len(gap_fields.get(nt, set())),
            "occurrence_count": occ,
        }
        for nt, occ in gap_occurrences.items()
    ]
    # ترتيب مستقرّ: الأكثر تكراراً أوّلاً، ثمّ الأبجديّ (حتميّ للاختبار/العرض).
    top_gaps.sort(key=lambda g: (-g["occurrence_count"], g["node_type"]))

    status_distribution = [
        {"status": s, "count": c}
        for s, c in sorted(status_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "fields_analyzed": len(fields),
        "top_gaps": top_gaps,
        "status_distribution": status_distribution,
    }


def shape_field_graph(node_rows: Any, edge_rows: Any) -> dict[str, Any]:
    """يُسطِّح صفوف عُقَد/حوافّ آخر لقطة لحقل (v149) إلى بنية عرض مع ملخّص.

    ``available=False`` إن لا عُقَد (لقطة مُطبَّعة غير موجودة بعد — الكاتب fail-soft).
    حمولة العقدة حدّ أدنى (لا أسرار — طُبِّعت أصلاً بلا attrs).
    """
    nodes: list[dict[str, Any]] = []
    for r in node_rows if isinstance(node_rows, (list, tuple)) else []:
        if not isinstance(r, dict):
            continue
        nid = r.get("node_id")
        ntype = r.get("node_type")
        if not isinstance(nid, str) or not isinstance(ntype, str):
            continue
        nodes.append(
            {
                "node_id": nid,
                "node_type": ntype,
                "source": r.get("source"),
                "status": r.get("status"),
                "reason": r.get("reason"),
            }
        )

    edges: list[dict[str, Any]] = []
    for r in edge_rows if isinstance(edge_rows, (list, tuple)) else []:
        if not isinstance(r, dict):
            continue
        eid = r.get("edge_id")
        if not isinstance(eid, str):
            continue
        edges.append(
            {
                "edge_id": eid,
                "edge_type": r.get("edge_type"),
                "from_node": r.get("from_node"),
                "to_node": r.get("to_node"),
            }
        )

    present = sum(1 for n in nodes if n["status"] == "present")
    missing = sum(1 for n in nodes if n["status"] == _MISSING)
    return {
        "available": bool(nodes),
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "present_count": present,
            "gap_count": missing,
        },
    }
