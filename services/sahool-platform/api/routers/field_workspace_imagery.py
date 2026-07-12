"""api/routers/field_workspace_imagery.py — Field Workspace imagery façade (UI-27).

واجهة خادمية مستقرة لتبويبة Imagery في Field Workspace. لا تصنع تواريخ أو صوراً
بديلة؛ تقرأ فقط ما يملكه raster-service/COG فعلياً بعد تمرير سياق المستأجر.

المسارات:
* GET /api/v1/fields/{field_id}/available-dates
* GET /api/v1/fields/{field_id}/imagery/timeline

تُسجّل هذه الوحدة أبجدياً قبل ``routers/fields.py``، لذلك تصبح هذه الواجهة هي
المسار الفعلي لهذه القراءات مع إبقاء النسخ القديمة في ``fields.py`` كـ fallback
تاريخي إلى أن يتم تنظيفها في مرحلة لاحقة.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.raster_service_client import get_available_dates

router = APIRouter()


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("dates"), list):
        return [x for x in payload["dates"] if isinstance(x, dict)]
    return []


@router.get("/api/v1/fields/{field_id}/available-dates")
async def field_imagery_available_dates_facade(
    field_id: str,
    index: str | None = Query(None),
    limit: int = Query(240, ge=1, le=500),
    include_provider: bool = Query(False),
    months: int = Query(24, ge=1, le=24),
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """تواريخ صور الأقمار المتاحة للحقل من raster-service فقط.

    لا نختلق تواريخ عند غياب صف الحقل في المنصة؛ raster-service يبقى مصدر ملكية
    أصول COG ويستقبل ``tenant_id`` الخادمي. فشل DB المحلي لا يتحول إلى بيانات بديلة.
    """
    try:
        async with tenant_connection(user) as conn:
            # قراءة دفاعية للتأكد من أن سياق المستأجر مفعّل؛ لا نستخدم النتيجة لتوليد بدائل.
            await conn.fetchval(
                "SELECT 1 FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
        return await get_available_dates(
            field_id,
            tenant_id=str(user.tenant_id),
            index=index,
            limit=limit,
            include_provider=include_provider,
            months=months,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("تواريخ صور الأقمار للحقل", exc) from exc


@router.get("/api/v1/fields/{field_id}/imagery/timeline")
async def field_imagery_timeline_facade(
    field_id: str,
    months: int = Query(24, ge=1, le=60),
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """Timeline صور حقيقي من available-dates + thumbnail_url خادمي.

    كل عنصر في ``items`` يجب أن يكون مبنياً على تاريخ COG موجود. لا يوجد fallback
    إلى مشاهد تجريبية أو صور مصغّرة وهمية.
    """
    try:
        async with tenant_connection(user) as conn:
            await conn.fetchval(
                "SELECT 1 FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )

        tenant = str(user.tenant_id)
        payload = await get_available_dates(
            field_id,
            tenant_id=tenant,
            limit=min(500, max(30, months * 6)),
        )
        cutoff = (date.today() - timedelta(days=months * 31)).isoformat()
        items: list[dict[str, Any]] = []
        for row in _as_list(payload):
            date_str = str(row.get("date") or "")[:10]
            if len(date_str) != 10 or date_str < cutoff:
                continue
            items.append(
                {
                    "date": date_str,
                    "has_cog": bool(row.get("has_cog")),
                    "cloud_pct": row.get("cloud_pct"),
                    "clear_pct": row.get("clear_pct"),
                    "quality_label": row.get("quality_label"),
                    "indices": row.get("indices") or [],
                    "scene_id": row.get("scene_id"),
                    "acquisition_datetime": row.get("acquisition_datetime"),
                    "thumbnail_url": (
                        f"/api/raster/v1/fields/{field_id}/cdse-thumbnail.png"
                        f"?index=truecolor&date={date_str}&size=160&tid={tenant}"
                    ),
                }
            )
        items.sort(key=lambda item: item["date"], reverse=True)
        return {"field_id": field_id, "months": months, "count": len(items), "items": items}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _db_unavailable("الخطّ الزمنيّ لصور الأقمار", exc) from exc
