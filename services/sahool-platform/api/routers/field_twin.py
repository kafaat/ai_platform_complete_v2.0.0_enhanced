"""api/routers/field_twin.py — التوأم الرقميّ للحقل (المرحلة B، الشريحة 6).

نقطة قراءة تُجمِّع حالة الحقل من الجداول القائمة (معزولةً بـRLS) في لقطة واحدة عبر
`core.field_twin`: المؤشّرات النباتيّة الأحدث (من raster-service، W1-21) + القرارات المفتوحة
(dispatch_decisions) + آخر تنفيذ (execution_ledger) + بيانات الحقل (fields) ⇒ حالة مشتقّة
صريحة (سليم/يحتاج انتباهاً/محجوب/قديم). محروسة بعلم `SAHOOL_DECISION_DISPATCH`.

قراءة فقط، نقيّة التجميع (المنطق في core)، تربط مخرجات حلقة المرحلة A ببيانات الحقل.

W1-21 (fields-8): كانت المؤشّرات تُقرأ من ``field_indicators`` ولا كاتب حيّ له. تُقرأ الآن
من raster-service (``latest_index_points``: أحدث متوسّط مرصود لكلّ مؤشّر وتاريخه) بعد إغلاق
اتّصال القاعدة. مؤشّر تعذّرت قراءته يُعلَن في ``indicator_source.unavailable`` ولا يُختلَق.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from core.field_twin import active_season_context, assemble_twin, finite_indicator_readings
from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.raster_service_client import latest_index_points

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

    ind_rows, unavailable = await _latest_indicator_rows(field_id, str(user.tenant_id))
    indices, index_observed_at = finite_indicator_readings(ind_rows)
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
    out["season_context"] = active_season_context(season_row)
    out["indicator_source"] = {
        "source": "raster-service:/v1/fields/{id}/timeseries",
        "unavailable": unavailable,
    }
    return out


async def _latest_indicator_rows(field_id: str, tenant_id: str) -> tuple[list[dict], list[str]]:
    """أحدث قراءة مرصودة لكلّ مؤشّر غطاء من raster-service، بشكل صفّ المؤشّر (indicator_id/
    value/recorded_at). يعيد أيضاً المؤشّرات التي تعذّرت قراءتها (raster غير متاح)."""
    results = await asyncio.gather(
        *(
            latest_index_points(field_id, tenant_id=tenant_id, index=index, count=1)
            for index in _TWIN_INDICATORS
        )
    )
    rows: list[dict] = []
    unavailable: list[str] = []
    for index, points in zip(_TWIN_INDICATORS, results, strict=True):
        if points is None:
            unavailable.append(index)
        elif points:
            rows.append(
                {
                    "indicator_id": index,
                    "value": points[0]["mean"],
                    "recorded_at": points[0]["datetime"],
                }
            )
    return rows, unavailable
