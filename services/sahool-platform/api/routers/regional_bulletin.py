"""api/routers/regional_bulletin.py — نشرة حالة المحاصيل الإقليميّة (V66.1، وصل end-to-end).

يصل منطق النشرة الصرف (``core.regional_bulletin``) بنقطة HTTP مُقيَّدة بالمستأجِر (RLS).
يجمّع NDVI لكلّ حقل (الحاليّ + المتوسّط التاريخيّ من ``zonal_stats``) مع محافظة الحقل
(``fields.gov``) ثمّ يبني النشرة على مستوى المحافظة/المديريّة مع أرضيّة الخصوصيّة.

صدق: القاعدة غير مفعّلة ⇒ نشرة فارغة + سبب (لا قيود مخترَعة)؛ لا NDVI لحقل ⇒ حالته
``unknown`` (لا تخمين). العزل بالمستأجِر عبر ``tenant_connection`` (RLS)، والخصوصيّة
عبر أرضيّة k-anonymity في المنطق الصرف. الاستعلام يُغطّى باختبارات التكامل (لا الوحدة).
"""

from __future__ import annotations

import logging

from core.regional_bulletin import build_regional_bulletin, bulletin_rows_to_records
from fastapi import APIRouter, Depends, HTTPException, Query

from api import main as api_main
from api.main import (
    Permission,
    UserSchema,
    require_permission,
    tenant_connection,
)

router = APIRouter()
logger = logging.getLogger("sahool.regional_bulletin")

# NDVI لكلّ حقل: أحدث قيمة + متوسّط تاريخيّ + عدد المشاهد، من zonal_stats (RLS)، مع
# محافظة الحقل. LATERAL join يبقي صفّاً واحداً لكلّ حقل حتّى بلا بيانات NDVI (⇒ NULL).
_BULLETIN_SQL = """
SELECT f.field_id,
       f.gov,
       f.tenant_id,
       zl.mean          AS ndvi_current,
       zh.mean_hist     AS ndvi_historical_mean,
       zh.n             AS scene_count
FROM fields f
LEFT JOIN LATERAL (
    SELECT z.mean FROM zonal_stats z
    WHERE z.field_id = f.field_id AND z.index_name = 'ndvi'
    ORDER BY z.stat_date DESC LIMIT 1
) zl ON TRUE
LEFT JOIN LATERAL (
    SELECT AVG(z.mean) AS mean_hist, COUNT(*) AS n FROM zonal_stats z
    WHERE z.field_id = f.field_id AND z.index_name = 'ndvi'
) zh ON TRUE
"""


@router.get("/api/v1/regional/bulletin")
async def regional_bulletin(
    period: str | None = Query(None, description="وسم فترة اختياريّ للنشرة"),
    min_fields_privacy: int = Query(5, ge=1, le=100, description="أرضيّة k-anonymity"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """نشرة حالة المحاصيل الإقليميّة (محافظة → مديريّات) — معزولة بالمستأجِر + آمنة الخصوصيّة.

    صدق: القاعدة غير مفعّلة ⇒ نشرة فارغة موثَّقة؛ المجموعات دون أرضيّة الخصوصيّة مكتومة
    بلا أرقام؛ لا معرّفات حقول في المخرَج؛ لا NDVI ⇒ حالة ``unknown`` (لا تخمين).
    """
    if api_main._DB_POOL is None:
        return {
            **build_regional_bulletin([], period=period, min_fields_privacy=min_fields_privacy),
            "note_db": "القاعدة غير مفعّلة (DATABASE_URL) — لا بيانات حقول للتجميع",
        }
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(_BULLETIN_SQL)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — تعذّر القاعدة ⇒ 503 موثَّق (لا اختلاق)
        logger.warning("regional bulletin query failed: %s", exc)
        raise HTTPException(status_code=503, detail="تعذّر بناء النشرة الإقليميّة مؤقّتاً") from exc

    records = bulletin_rows_to_records([dict(r) for r in rows])
    return build_regional_bulletin(records, period=period, min_fields_privacy=min_fields_privacy)
