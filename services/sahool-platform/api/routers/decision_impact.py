"""api/routers/decision_impact.py — قياس الأثر + التعلُّم + الذكاء الاقتصاديّ (المرحلة C).

ثلاث نقاط قراءة تُغلِق حلقة «هل نفع؟» فوق سجلّ التنفيذ (execution_ledger، المرحلة A):

  • `GET  …/decision/impact`   — الأثر المُحقَّق (نُفِّذ/فشل، نسبة نجاح، ماء موفَّر) من
    سجلّ التنفيذ، بربط القرار بأمره (الماء المطلوب) ونتيجته (المُطبَّق). الشريحة 8.
  • `GET  …/decision/learning` — اقتراحات معايرة مُسنَدة بالأثر (human-in-the-loop، لا
    تُطبَّق آليّاً) عبر core.decision_learning. الشريحة 9.
  • `GET  …/decision/economics`— ترجمة الأثر إلى قيمة اقتصاديّة (ماء موفَّر ⇒ تكلفة
    متجنَّبة) عبر core.economic_intelligence. الشريحة 10.

محروسة بعلم `SAHOOL_DECISION_DISPATCH`. قراءة فقط، معزولة بـRLS، المنطق نقيّ في core/.
"""

from __future__ import annotations

import json as _json
import os

from core.decision_learning import derive_learning_suggestions
from core.economic_intelligence import summarize_economics
from core.impact_measurement import ImpactRecord, measure_impact
from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _dispatch_enabled() -> bool:
    return os.getenv("SAHOOL_DECISION_DISPATCH", "").strip().lower() in _TRUTHY


def _require_enabled() -> None:
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )


def _loads(v):
    if v is None:
        return None
    return _json.loads(v) if isinstance(v, str) else v


async def _collect_impact_records(conn, field_id: str | None, limit: int) -> list[ImpactRecord]:
    """يقرأ سجلّ التنفيذ + يربطه بقرار التوزيع لاستخراج كمّيّات الماء (نقيّ التجميع).

    الماء المطلوب من command.payload (قرار التوزيع)، والمُطبَّق من ledger.detail (النتيجة
    البشريّة). يُستخرَج بحذر — غيابه ⇒ None (يُستثنى من حساب الماء بصدق).
    """
    if field_id:
        rows = await conn.fetch(
            """
            SELECT l.outcome, l.action_type, l.detail, d.command
            FROM execution_ledger l
            LEFT JOIN dispatch_decisions d ON d.decision_id = l.decision_id
            WHERE l.field_id = $1
            ORDER BY l.recorded_at DESC LIMIT $2
            """,
            field_id,
            limit,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT l.outcome, l.action_type, l.detail, d.command
            FROM execution_ledger l
            LEFT JOIN dispatch_decisions d ON d.decision_id = l.decision_id
            ORDER BY l.recorded_at DESC LIMIT $1
            """,
            limit,
        )

    records: list[ImpactRecord] = []
    for r in rows:
        detail = _loads(r["detail"]) or {}
        command = _loads(r["command"]) or {}
        payload = command.get("payload", {}) if isinstance(command, dict) else {}
        req = payload.get("water_mm") if isinstance(payload, dict) else None
        app = detail.get("water_mm") if isinstance(detail, dict) else None
        records.append(
            ImpactRecord(
                action_type=r["action_type"],
                outcome=r["outcome"],
                water_requested_mm=req,
                water_applied_mm=app,
            )
        )
    return records


@router.get("/api/v1/decision/impact")
async def get_impact(
    field_id: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """الأثر المُحقَّق من سجلّ التنفيذ (نُفِّذ/فشل، نسبة نجاح، ماء موفَّر). الشريحة 8."""
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            records = await _collect_impact_records(conn, field_id, limit)
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قياس الأثر", e) from e
    return measure_impact(records).to_dict()


@router.get("/api/v1/decision/learning")
async def get_learning(
    min_sample: int = Query(5, ge=1, le=100),
    limit: int = Query(500, ge=1, le=2000),
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
) -> dict:
    """اقتراحات معايرة مُسنَدة بالأثر (human-in-the-loop، لا تُطبَّق آليّاً). الشريحة 9."""
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            records = await _collect_impact_records(conn, None, limit)
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("اشتقاق اقتراحات التعلُّم", e) from e
    summary = measure_impact(records)
    suggestions = derive_learning_suggestions(summary.by_action, min_sample=min_sample)
    return {
        "suggestions": [s.to_dict() for s in suggestions],
        "count": len(suggestions),
        "advisory_only": True,  # صدق: اقتراحات لا تُطبَّق آليّاً (human-in-the-loop)
        "based_on": {"total_decisions": summary.total_decisions, "min_sample": min_sample},
    }


@router.get("/api/v1/decision/economics")
async def get_decision_economics(
    field_id: str | None = None,
    area_ha: float | None = None,
    water_cost_per_m3: float | None = None,
    currency: str = "YER",
    limit: int = Query(500, ge=1, le=2000),
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
) -> dict:
    """ترجمة الأثر إلى قيمة اقتصاديّة (ماء موفَّر ⇒ تكلفة متجنَّبة). الشريحة 10.

    صدق: الحجم/القيمة يُحسَبان فقط مع المساحة/التكلفة — وإلّا None + ملاحظة صريحة.
    """
    _require_enabled()
    try:
        async with tenant_connection(user) as conn:
            records = await _collect_impact_records(conn, field_id, limit)
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("ترجمة الأثر الاقتصاديّ", e) from e
    impact = measure_impact(records)
    econ = summarize_economics(
        impact.to_dict(),
        currency=currency,
        area_ha=area_ha,
        water_cost_per_m3=water_cost_per_m3,
    )
    out = econ.to_dict()
    out["impact"] = impact.to_dict()
    return out
