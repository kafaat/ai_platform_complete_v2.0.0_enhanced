"""core/evidence_graph.py — رسم أدلّة الحقل (Evidence Graph) — منطق صرف.

يحوّل مخرَج بطاقة ذكاء الحقل إلى **رسم أدلّة**: عُقَد (الحقل + كلّ دليل حاضر: مشهد فضائيّ/
حالة/تربة/طقس/تضاريس/نبات/ماء/مناطق) + حوافّ (الحقل → دليل، ثمّ دليل → توصية). كلّ عقدة
تحمل مصدرها. الغرض (رؤية «Sahool Evidence Graph»): تفسير التوصيات، إثبات مصدر كلّ
معلومة، وإظهار **ما ينقص** صراحةً (فجوات معرفة، لا عُقَد ملفّقة).

**صدق حاسم:** لا عقدة لدليل غائب — الأقسام المفقودة تُدرَج في ``knowledge_gaps`` بسببها.
منطق صرف: يستهلك مخرَج ``analyze`` (ومعه البطاقة) المُمرَّر فقط — لا جلب ولا خدمات.
"""

from __future__ import annotations

from typing import Any

_SCHEMA = "sahool.evidence_graph/1"

# مفتاح قسم البطاقة → (نوع العقدة، تسمية، مصدر ثابت|None يعني يُقرأ من القسم).
_EVIDENCE_TYPES: dict[str, tuple[str, str, str | None]] = {
    "latest_scene": ("satellite_scene", "مشهد فضائيّ", None),  # المصدر = provider القسم
    "field_condition": ("crop_condition", "حالة الحقل", "canonical_state"),
    "soil_baseline": ("soil_baseline", "خطّ أساس التربة", "soilgrids"),
    "weather_window": ("weather", "نافذة الطقس", "open_meteo"),
    "terrain": ("terrain", "التضاريس", "copernicus_dem"),
    "ndvi_vs_historical": ("vegetation_index", "NDVI مقابل التاريخيّ", "sentinel2"),
    "water_deficit": ("water", "العجز المائيّ", "fao56"),
    "weak_zones": ("weak_zones", "المناطق الضعيفة", "productivity_zones"),
}


def _attrs(section: dict[str, Any]) -> dict[str, Any]:
    """سمات العقدة = محتوى القسم بلا حقلَي الحالة/السبب (بيانات الدليل فقط)."""
    return {k: v for k, v in section.items() if k not in ("status", "reason")}


def _source_of(key: str, section: dict[str, Any]) -> str | None:
    _t, _label, fixed = _EVIDENCE_TYPES[key]
    if fixed is not None:
        return fixed
    # latest_scene: المصدر الفعليّ من القسم (element84/cdse/…)، لا ثابت مُختلَق.
    prov = section.get("provider")
    return str(prov) if prov else "satellite"


def build_evidence_graph(analyze: dict[str, Any]) -> dict[str, Any]:
    """يبني رسم أدلّة من مخرَج ``analyze`` + بطاقته. صادق: لا عقدة بلا دليل حاضر.

    عُقَد: ``field`` (الجذر) + عقدة لكلّ قسم دليل **حاضر** + ``recommendation`` (إن وُجِد
    قرار سياسة). حوافّ: ``has_evidence`` (الحقل→دليل) و``supports`` (دليل→توصية). الأقسام
    الغائبة ⇒ ``knowledge_gaps`` بسببها (ما لا نعرفه بعد). كلّ عقدة دليل تحمل ``sources``.
    """
    analyze = analyze if isinstance(analyze, dict) else {}
    card = analyze.get("field_intelligence_card")
    card = card if isinstance(card, dict) else {}
    sections = card.get("sections") if isinstance(card.get("sections"), dict) else {}
    field_id = analyze.get("field_id") or card.get("field_id")

    nodes: list[dict[str, Any]] = [
        {"id": "field", "type": "field", "label": "الحقل", "field_id": field_id}
    ]
    edges: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for key, (ntype, label, _fixed) in _EVIDENCE_TYPES.items():
        sec = sections.get(key)
        if isinstance(sec, dict) and sec.get("status") == "present":
            node_id = f"evidence:{key}"
            nodes.append(
                {
                    "id": node_id,
                    "type": ntype,
                    "label": label,
                    "attrs": _attrs(sec),
                    "source": _source_of(key, sec),
                }
            )
            edges.append({"from": "field", "to": node_id, "rel": "has_evidence"})
        else:
            reason = sec.get("reason") if isinstance(sec, dict) else "not_supplied"
            gaps.append({"key": key, "label": label, "reason": reason or "not_supplied"})

    # عقدة التوصية + حوافّ الأدلّة الداعمة (تفسير: أيّ دليل ساند القرار).
    decision = analyze.get("policy_decision")
    if isinstance(decision, dict) and decision:
        rec_id = "recommendation"
        nodes.append(
            {
                "id": rec_id,
                "type": "recommendation",
                "label": "توصية",
                "attrs": {
                    "action_type": decision.get("action_type"),
                    "executable": analyze.get("executable"),
                    "confidence": analyze.get("confidence"),
                },
            }
        )
        for node in nodes:
            if isinstance(node["id"], str) and node["id"].startswith("evidence:"):
                edges.append({"from": node["id"], "to": rec_id, "rel": "supports"})

    evidence_count = sum(1 for n in nodes if n["type"] not in ("field", "recommendation"))
    return {
        "schema": _SCHEMA,
        "field_id": field_id,
        "nodes": nodes,
        "edges": edges,
        "knowledge_gaps": gaps,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "evidence_count": evidence_count,
            "gap_count": len(gaps),
            "has_recommendation": any(n["type"] == "recommendation" for n in nodes),
        },
    }
