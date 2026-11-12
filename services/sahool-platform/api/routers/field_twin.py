"""api/routers/field_twin.py — التوأم الرقميّ للحقل (المرحلة B، الشريحة 6).

نقطة قراءة تُجمِّع حالة الحقل من الجداول القائمة (معزولةً بـRLS) في لقطة واحدة عبر
`core.field_twin`: المؤشّرات النباتيّة الأحدث (field_indicators) + القرارات المفتوحة
(dispatch_decisions) + آخر تنفيذ (execution_ledger) + بيانات الحقل (fields) ⇒ حالة مشتقّة
صريحة (سليم/يحتاج انتباهاً/محجوب/قديم). محروسة بعلم `SAHOOL_DECISION_DISPATCH`.

قراءة فقط، نقيّة التجميع (المنطق في core)، تربط مخرجات حلقة المرحلة A ببيانات الحقل.
"""

from __future__ import annotations

import json
import math
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
            # The season is a separate owner from fields.crop; expose it without
            # silently overwriting one identity with the other in a derived view.
            season_row = await conn.fetchrow(
                "SELECT season_id, crops, cultivar, sowing_date FROM seasons "
                "WHERE field_id = $1 AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                field_id,
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

    indices: dict[str, float] = {}
    index_observed_at: dict[str, object] = {}
    for r in ind_rows:
        try:
            value = float(r["value"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        indices[r["indicator_id"]] = value
        index_observed_at[r["indicator_id"]] = r["recorded_at"]
    observed_at = max((v for v in index_observed_at.values() if v is not None), default=None)
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
        index_observed_at=index_observed_at,
        now=datetime.now(UTC),
        open_decisions=open_decisions,
        last_execution=last_execution,
    )
    out = twin.to_dict()
    out["field_name"] = field_row["name"]
    out["legacy_field_crop"] = field_row["crop"]
    out["view_role"] = "derived_read_model_only"
    out["decision_authority"] = "none"
    raw_crops = season_row["crops"] if season_row is not None else []
    if isinstance(raw_crops, str):
        try:
            raw_crops = json.loads(raw_crops)
        except (TypeError, ValueError):
            raw_crops = []
    if not isinstance(raw_crops, list):
        raw_crops = []
    sowing = season_row["sowing_date"] if season_row is not None else None
    out["season_context"] = {
        "source": "seasons",
        "status": "active" if season_row is not None else "missing_active_season",
        "season_id": str(season_row["season_id"]) if season_row is not None else None,
        "crops": raw_crops,
        "cultivar": season_row["cultivar"] if season_row is not None else None,
        "sowing_date": sowing.isoformat() if sowing is not None else None,
    }
    return out
