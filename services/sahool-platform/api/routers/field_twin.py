"""api/routers/field_twin.py — التوأم الرقميّ للحقل (المرحلة B، الشريحة 6).

نقطة قراءة تُجمِّع حالة الحقل من الجداول القائمة (معزولةً بـRLS) في لقطة واحدة عبر
`core.field_twin`: المؤشّرات النباتيّة الأحدث (field_indicators) + القرارات المفتوحة
(dispatch_decisions) + آخر تنفيذ (execution_ledger) + بيانات الحقل (fields) ⇒ حالة مشتقّة
صريحة (سليم/يحتاج انتباهاً/محجوب/قديم). محروسة بعلم `SAHOOL_DECISION_DISPATCH`.

قراءة فقط، نقيّة التجميع (المنطق في core)، تربط مخرجات حلقة المرحلة A ببيانات الحقل.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from core.field_twin import assemble_twin
from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
# مؤشّرات الغطاء التي نعرضها في التوأم (نباتيّة — الأكثر دلالة على صحّة الحقل).
_TWIN_INDICATORS = ("ndvi", "evi", "savi", "ndmi")


def _dispatch_enabled() -> bool:
    return os.getenv("SAHOOL_DECISION_DISPATCH", "").strip().lower() in _TRUTHY


@router.get("/api/v1/fields/{field_id}/twin")
async def get_field_twin(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يُجمِّع التوأم الرقميّ لحقل: لقطة حالة موحّدة + حالة مشتقّة وأسبابها.

    معزول بـRLS (يرى المستأجِر حقله فقط). 404 إن مُطفأ العلم أو غاب الحقل، 503 عند تعذّر
    القاعدة. التجميع نقيّ في core.field_twin؛ هذه النقطة تقرأ المدخلات فقط.
    """
    if not _dispatch_enabled():
        raise HTTPException(
            status_code=404, detail="ميزة موزِّع القرار غير مُفعَّلة (اضبط SAHOOL_DECISION_DISPATCH)."
        )
    try:
        async with tenant_connection(user) as conn:
            field_row = await conn.fetchrow(
                "SELECT field_id, name, crop FROM fields WHERE field_id = $1", field_id
            )
            if field_row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود (أو لمستأجِر آخر).")

            # أحدث قيمة لكلّ مؤشّر غطاء (DISTINCT ON — الأحدث per indicator_id).
            ind_rows = await conn.fetch(
                """
                SELECT DISTINCT ON (indicator_id) indicator_id, value, recorded_at
                FROM field_indicators
                WHERE field_id = $1 AND indicator_id = ANY($2::text[])
                ORDER BY indicator_id, recorded_at DESC
                """,
                field_id,
                list(_TWIN_INDICATORS),
            )
            # القرارات المفتوحة (محجوبة أو قيد التنفيذ).
            dec_rows = await conn.fetch(
                """
                SELECT state, exec_status FROM dispatch_decisions
                WHERE field_id = $1 AND (exec_status IN ('queued', 'dispatched') OR state = 'blocked')
                """,
                field_id,
            )
            last_exec = await conn.fetchrow(
                """
                SELECT outcome, action_type, recorded_at FROM execution_ledger
                WHERE field_id = $1 ORDER BY recorded_at DESC LIMIT 1
                """,
                field_id,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تجميع التوأم الرقميّ للحقل", e) from e

    indices = {r["indicator_id"]: float(r["value"]) for r in ind_rows}
    observed_at = max((r["recorded_at"] for r in ind_rows), default=None)
    open_decisions = [{"state": r["state"], "exec_status": r["exec_status"]} for r in dec_rows]
    last_execution = None
    if last_exec is not None:
        last_execution = {
            "outcome": last_exec["outcome"],
            "action_type": last_exec["action_type"],
            "recorded_at": last_exec["recorded_at"].isoformat()
            if last_exec["recorded_at"] is not None
            else None,
        }

    twin = assemble_twin(
        field_id,
        crop=field_row["crop"],
        latest_indices=indices,
        observed_at=observed_at,
        now=datetime.now(UTC),
        open_decisions=open_decisions,
        last_execution=last_execution,
    )
    out = twin.to_dict()
    out["field_name"] = field_row["name"]
    return out
