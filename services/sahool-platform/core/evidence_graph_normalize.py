"""core/evidence_graph_normalize.py — تطبيع رسم الأدلّة إلى صفوف عُقَد/حوافّ — منطق صرف.

المرحلة 2 من الاستمرار: يشتقّ من ``evidence_graph`` (لقطة v148، **مصدر الحقيقة**) صفوفاً
مُسطَّحة لجدولَي ``evidence_graph_nodes`` / ``evidence_graph_edges`` (v149). لا I/O — الإدراج
tenant-scoped في الراوت.

**صدق/أمن:** حمولة العقدة **حدّ أدنى** (node_id/type/source/status/reason) — بلا ``attrs``
فلا أسرار تُطبَّع. العُقَد الحاضرة من ``nodes``؛ **الغائبة** من ``knowledge_gaps`` بحالة
``missing`` وسببها (لا عقدة ملفّقة). حافّة ``edge_id`` مُصنَّعة ``from->rel->to`` (فريدة/لقطة).
"""

from __future__ import annotations

from typing import Any

_SECRET_HINTS = ("password", "token", "secret", "authorization", "credential", "api_key")


def _clean_source(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    low = value.lower()
    if any(h in low for h in _SECRET_HINTS):
        return None  # أمن: لا نُطبِّع قيمة تشبه سرّاً كـsource.
    return value


def normalize_graph_to_rows(evidence_graph: Any) -> dict[str, list[dict[str, Any]]]:
    """يحوّل ``evidence_graph`` إلى ``{"nodes": [...], "edges": [...]}`` صفوفاً مُسطَّحة.

    عُقَد حاضرة من ``nodes`` (status=present)؛ عُقَد غائبة من ``knowledge_gaps``
    (status=missing + reason، node_id=``gap:<key>``). حوافّ من ``edges``. صدق: مدخل شاذّ
    ⇒ قوائم فارغة (لا تلفيق). تكرار node_id/edge_id يُزال (آخر ظهور يفوز — idempotent محلّيّاً).
    """
    graph = evidence_graph if isinstance(evidence_graph, dict) else {}
    nodes_out: dict[str, dict[str, Any]] = {}
    edges_out: dict[str, dict[str, Any]] = {}

    for n in graph.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        ntype = n.get("type")
        if not isinstance(nid, str) or not isinstance(ntype, str):
            continue
        nodes_out[nid] = {
            "node_id": nid,
            "node_type": ntype,
            "source": _clean_source(n.get("source")),
            "status": "present",
            "reason": None,
        }

    for gap in graph.get("knowledge_gaps") or []:
        if not isinstance(gap, dict):
            continue
        key = gap.get("key")
        if not isinstance(key, str) or not key:
            continue
        nid = f"gap:{key}"
        nodes_out.setdefault(
            nid,
            {
                "node_id": nid,
                "node_type": str(key),
                "source": None,
                "status": "missing",
                "reason": str(gap.get("reason") or "not_supplied"),
            },
        )

    for e in graph.get("edges") or []:
        if not isinstance(e, dict):
            continue
        frm, to, rel = e.get("from"), e.get("to"), e.get("rel")
        if not (isinstance(frm, str) and isinstance(to, str) and isinstance(rel, str)):
            continue
        eid = f"{frm}->{rel}->{to}"
        edges_out[eid] = {
            "edge_id": eid,
            "edge_type": rel,
            "from_node": frm,
            "to_node": to,
        }

    return {"nodes": list(nodes_out.values()), "edges": list(edges_out.values())}
