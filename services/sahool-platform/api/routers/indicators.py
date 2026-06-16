"""api/routers/indicators.py — المؤشّرات ولوحاتها (Indicators)
===========================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.analytics_shapers import _shape_indicator_catalog, _shape_indicators_dashboard
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/indicators/catalog")
async def indicators_catalog(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كتالوج المؤشّرات المُنفَّذة فعلاً + مصادرها (بديل indicators-service الـstub).

    ثابت (لا قاعدة) لكنّه صادق: يصف ما تحسبه المنصّة حقّاً عبر خدماتها، لا ٣٣
    مؤشّراً وهميّاً. مُقيَّد بالدور (FIELD_VIEW) للاتّساق مع بقيّة لوحات الحقل.
    """
    return _shape_indicator_catalog()


@router.get("/api/v1/indicators/dashboard")
async def indicators_dashboard(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """لوحة المؤشّرات المُجمَّعة للمستأجِر — عدّادات + تنبيهات + ملخّص الحقول.

    تجميع حيّ من fields/seasons/alerts (RLS + tenant_id). لا قيم NDVI/طقس مُلفَّقة:
    المؤشّرات الطيفيّة لكلّ حقل تُجلب من vegetation/raster في شاشة الأقمار. 503 عند
    تعذّر القاعدة — لا أرقام مخترعة.
    """
    try:
        async with tenant_connection(user) as conn:
            tid = str(user.tenant_id)
            fields_rows = await conn.fetch(
                "SELECT field_id, name, crop, area_ha, geometry FROM fields "
                "WHERE tenant_id = $1::uuid ORDER BY name",
                tid,
            )
            active_season_rows = await conn.fetch(
                "SELECT DISTINCT field_id FROM seasons "
                "WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            alert_rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at FROM alerts "
                "WHERE tenant_id = $1::uuid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 50",
                tid,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة لوحة المؤشّرات", e) from e
    active_field_ids = {r["field_id"] for r in active_season_rows}
    return _shape_indicators_dashboard(
        fields_rows=fields_rows,
        active_field_ids=active_field_ids,
        alert_rows=alert_rows,
    )
