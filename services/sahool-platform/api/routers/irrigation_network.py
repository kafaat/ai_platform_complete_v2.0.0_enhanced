"""api/routers/irrigation_network.py — توأم شبكة الريّ: فحص الجدوى (compute، توصية فقط، P1)

نقطة واحدة محروسة بعلم ``FEATURE_IRRIGATION_NETWORK`` (مُطفأة افتراضاً ⇒ 404):

  • ``POST /api/v1/irrigation/network/feasibility`` — يأخذ طوبولوجيا شبكة الريّ
    (عُقَد + وصلات: بئر→مضخّة→…→منطقة) ويفحص **جدوى تنفيذ** طلب الريّ عليها قبل أيّ
    تشغيل (اتّصاليّة/توفّر ماء/إنتاجيّة/ضغط)، فيُبرز الاختناقات. **توصية فقط، لا تنفيذ**.

**الصدق**: الطوبولوجيا والقيود **يمرّرها المستدعي** (تُبنى من البنية الحقيقيّة — صمّامات/
مضخّات/آبار) لا تُلفَّق؛ الطبقة النقيّة ``check_network_feasibility`` تشكّل الجدوى حتميّاً،
والقيد الغائب ``unchecked`` لا يُفترَض نجاحه. compute صرف (لا قاعدة) — المصادقة فقط حارساً.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.irrigation_network import NetworkEdge, NetworkNode, check_network_feasibility
from api.main import UserSchema, get_current_user

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _irrigation_network_enabled() -> bool:
    """هل ميزة توأم شبكة الريّ مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_IRRIGATION_NETWORK", "").strip().lower() in _TRUTHY


class NetworkNodeModel(BaseModel):
    node_id: str
    kind: str  # well|pump|filter|fertilizer|main_line|submain|valve|zone
    capacity_m3: float | None = None
    max_throughput_m3: float | None = None
    max_pressure_bar: float | None = None
    min_pressure_bar: float | None = None
    demand_m3: float | None = None


class NetworkEdgeModel(BaseModel):
    from_id: str
    to_id: str


class NetworkFeasibilityRequest(BaseModel):
    nodes: list[NetworkNodeModel] = Field(default_factory=list)
    edges: list[NetworkEdgeModel] = Field(default_factory=list)


@router.post("/api/v1/irrigation/network/feasibility")
def network_feasibility_endpoint(
    req: NetworkFeasibilityRequest,
    user: UserSchema = Depends(get_current_user),
) -> dict:
    """يفحص جدوى تنفيذ طلب الريّ على الشبكة — توصية فقط. 404 إن مُطفأ.

    يبني الطوبولوجيا من المدخلات ويفحص الاتّصاليّة/توفّر الماء/الإنتاجيّة/الضغط، فيُعلِن
    الجدوى والاختناقات. صدق: المدخلات مُمرَّرة لا مُختلقة؛ القيد الغائب unchecked؛ **لا تنفيذ**.
    """
    if not _irrigation_network_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة توأم شبكة الريّ غير مُفعَّلة (اضبط FEATURE_IRRIGATION_NETWORK).",
        )
    nodes = [
        NetworkNode(
            node_id=n.node_id,
            kind=n.kind,
            capacity_m3=n.capacity_m3,
            max_throughput_m3=n.max_throughput_m3,
            max_pressure_bar=n.max_pressure_bar,
            min_pressure_bar=n.min_pressure_bar,
            demand_m3=n.demand_m3,
        )
        for n in req.nodes
    ]
    edges = [NetworkEdge(from_id=e.from_id, to_id=e.to_id) for e in req.edges]
    out = check_network_feasibility(nodes, edges)
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذا الفحص
    return out
