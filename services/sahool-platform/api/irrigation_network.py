"""api/irrigation_network.py — توأم شبكة الريّ: فحص جدوى التنفيذ (Network Twin، P1)

يمثّل **طوبولوجيا شبكة الريّ** (عُقَد + وصلات موجّهة من المصدر إلى المناطق):
``well → pump → filter → fertilizer → main_line → submain → valve → zone`` — ثمّ يفحص
**جدوى تنفيذ** طلب ريّ عليها **قبل** أيّ تشغيل: هل المنطقة موصولة بمصدر؟ هل ماء البئر
يكفي؟ هل تتجاوز الإنتاجيّة حدّ عقدة ناقلة؟ هل تُلبّى حاجة الضغط؟

**توصية فقط، لا تنفيذ**: يُعلِن الجدوى والاختناقات؛ لا يفتح صمّاماً ولا يشغّل مضخّة.

**نمط الصدق**: الطوبولوجيا والقيود **تُمرَّر** (تُبنى من البنية الحقيقيّة) — لا تُلفَّق.
القيد **الغائب** (سعة/إنتاجيّة/ضغط غير محدَّد) يُعلَن ``unchecked`` ولا يُفترَض نجاحه
(لا «جدوى» كاذبة). ``calibrated`` غير منطبق ⇒ ``not_applicable``.

نقيّ حتميّ (لا قاعدة، لا I/O) — قابل للاختبار offline؛ يستهلكه ``routers/irrigation_network``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

_KINDS = (
    "well",
    "pump",
    "filter",
    "fertilizer",
    "main_line",
    "submain",
    "valve",
    "zone",
)


@dataclass
class NetworkNode:
    """عقدة في شبكة الريّ بقيودها (كلّها اختياريّة — الغائب يُعلَن unchecked)."""

    node_id: str
    kind: str  # well|pump|filter|fertilizer|main_line|submain|valve|zone
    capacity_m3: float | None = None  # بئر: حجم الماء المتاح خلال النافذة
    max_throughput_m3: float | None = None  # عقدة ناقلة: أقصى حجم يمرّ خلال النافذة
    max_pressure_bar: float | None = None  # مضخّة: الضغط الذي توفّره
    min_pressure_bar: float | None = None  # منطقة: الضغط المطلوب
    demand_m3: float | None = None  # منطقة: حجم الماء المطلوب


@dataclass
class NetworkEdge:
    """وصلة موجّهة (من الأعلى نحو المنطقة): from_id ⇒ to_id."""

    from_id: str
    to_id: str


def _trace_to_well(
    zone_id: str, parents: dict[str, list[str]], kinds: dict[str, str]
) -> list[str] | None:
    """يتتبّع أقصر مسار عكسيّ من منطقة إلى أوّل بئر — None إن لا بئر موصول (مقطوعة)."""
    seen = {zone_id}
    queue: deque[tuple[str, list[str]]] = deque([(zone_id, [zone_id])])
    while queue:
        node, path = queue.popleft()
        if kinds.get(node) == "well":
            return path
        for parent in parents.get(node, []):
            if parent not in seen:
                seen.add(parent)
                queue.append((parent, path + [parent]))
    return None


def check_network_feasibility(nodes: list[NetworkNode], edges: list[NetworkEdge]) -> dict:
    """يفحص جدوى تنفيذ طلب الريّ على الشبكة — نقيّ حتميّ، **توصية فقط**.

    لكلّ منطقة (``kind="zone"`` بـ``demand_m3``): يتتبّع مسارها إلى بئر، ثمّ يفحص:
      • **اتّصاليّة**: لا بئر موصول ⇒ infeasible (مقطوعة).
      • **توفّر الماء**: مجموع طلبات مناطق البئر ≤ ``capacity_m3`` (وإلّا عجز).
      • **إنتاجيّة**: طلب يمرّ عبر عقدة ناقلة ذات ``max_throughput_m3`` لا يتجاوزه (وإلّا اختناق).
      • **ضغط**: ``min_pressure_bar`` للمنطقة ≤ ``max_pressure_bar`` لأقرب مضخّة عُلويّة.

    القيد غير المحدَّد يُعلَن ``unchecked`` (لا يُفترَض نجاحه). الناتج: ``zones`` (لكلّ
    منطقة status + reasons + unchecked) + ``overall_feasible`` + ``wells`` (حِمل/سعة) +
    ``warnings_ar`` + ``calibrated=not_applicable``.
    """
    kinds = {n.node_id: (n.kind if n.kind in _KINDS else "submain") for n in nodes}
    by_id = {n.node_id: n for n in nodes}
    parents: dict[str, list[str]] = {}
    for e in edges:
        parents.setdefault(e.to_id, []).append(e.from_id)

    zones = [n for n in nodes if n.kind == "zone"]
    well_load: dict[str, float] = {n.node_id: 0.0 for n in nodes if n.kind == "well"}
    node_load: dict[str, float] = {n.node_id: 0.0 for n in nodes}

    # تمرير ١: مسار كلّ منطقة + تجميع الحِمل على البئر والعُقَد الناقلة.
    paths: dict[str, list[str] | None] = {}
    for z in zones:
        path = _trace_to_well(z.node_id, parents, kinds)
        paths[z.node_id] = path
        demand = max(0.0, z.demand_m3 or 0.0)
        if path:
            for node_id in path:
                node_load[node_id] += demand
            well_id = path[-1]
            well_load[well_id] += demand

    # تمرير ٢: حكم الجدوى لكلّ منطقة.
    out_zones: list[dict] = []
    overall = True
    for z in zones:
        path = paths[z.node_id]
        reasons: list[str] = []
        unchecked: list[str] = []
        bottlenecks: list[str] = []
        demand = max(0.0, z.demand_m3 or 0.0)

        if z.demand_m3 is None:
            unchecked.append("demand")
        if path is None:
            reasons.append("مقطوعة: لا بئر موصول بهذه المنطقة")
            status = "infeasible"
        else:
            well = by_id[path[-1]]
            # توفّر الماء (على مستوى البئر، حِمله الكلّيّ).
            if well.capacity_m3 is None:
                unchecked.append(f"well_capacity:{well.node_id}")
            elif well_load[well.node_id] > well.capacity_m3 + 1e-9:
                reasons.append(
                    f"عجز ماء عند البئر {well.node_id}: الطلب {round(well_load[well.node_id], 1)} > السعة {round(well.capacity_m3, 1)} م³"
                )
                bottlenecks.append(well.node_id)
            # إنتاجيّة العُقَد الناقلة على المسار.
            for node_id in path:
                node = by_id[node_id]
                if node.kind in ("well", "zone"):
                    continue
                if node.max_throughput_m3 is None:
                    unchecked.append(f"throughput:{node_id}")
                elif node_load[node_id] > node.max_throughput_m3 + 1e-9:
                    reasons.append(
                        f"اختناق إنتاجيّة عند {node_id}: المرور {round(node_load[node_id], 1)} > الحدّ {round(node.max_throughput_m3, 1)} م³"
                    )
                    bottlenecks.append(node_id)
            # الضغط: أقرب مضخّة عُلويّة على المسار.
            if z.min_pressure_bar is not None:
                pumps = [by_id[n] for n in path if by_id[n].kind == "pump"]
                pump_press = [p.max_pressure_bar for p in pumps if p.max_pressure_bar is not None]
                if not pumps or not pump_press:
                    unchecked.append("pressure")
                elif max(pump_press) + 1e-9 < z.min_pressure_bar:
                    reasons.append(
                        f"نقص ضغط: المطلوب {z.min_pressure_bar} > أقصى مضخّة {max(pump_press)} bar"
                    )
                    bottlenecks.append("pressure")
            status = (
                "infeasible" if reasons else ("feasible_unverified" if unchecked else "feasible")
            )

        if status == "infeasible":
            overall = False
        out_zones.append(
            {
                "zone_id": z.node_id,
                "demand_m3": round(demand, 2),
                "status": status,
                "path": path,
                "reasons_ar": reasons,
                "bottlenecks": list(dict.fromkeys(bottlenecks)),
                "unchecked": unchecked,
            }
        )

    out_wells = [
        {
            "well_id": n.node_id,
            "capacity_m3": round(n.capacity_m3, 2) if n.capacity_m3 is not None else None,
            "load_m3": round(well_load[n.node_id], 2),
            "over_capacity": (
                n.capacity_m3 is not None and well_load[n.node_id] > n.capacity_m3 + 1e-9
            ),
        }
        for n in nodes
        if n.kind == "well"
    ]

    warnings_ar = [
        "فحص جدوى شبكة الريّ — **توصية فقط، لا تنفيذ ولا فتح صمّامات**.",
        "القيد غير المحدَّد يُعلَن unchecked (لا يُفترَض نجاحه) — العتبات تقديريّة غير معايَرة.",
    ]
    disconnected = [z["zone_id"] for z in out_zones if z["path"] is None]
    if disconnected:
        warnings_ar.append("مناطق مقطوعة عن أيّ بئر: " + "، ".join(disconnected))

    return {
        "zones": out_zones,
        "wells": out_wells,
        "overall_feasible": overall,
        "zone_count": len(out_zones),
        "feasible_count": sum(1 for z in out_zones if z["status"] != "infeasible"),
        "calibrated": "not_applicable",
        "thresholds_estimated": True,  # عتبات الجدوى (سعة/إنتاجيّة/ضغط) تقديريّة غير معايَرة
        "warnings_ar": warnings_ar,
    }
