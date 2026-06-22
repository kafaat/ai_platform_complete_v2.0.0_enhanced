"""api/routers/yield_analysis.py — تحليل الغلّة (Yield Analysis) — نمط FieldView.

شريحة ``APIRouter`` (نمط P0) تُضيف نقطة تجميع واحدة لتحليل الغلّة على نمط FieldView:
الزراعة↔الحصاد لكلّ موسم + مقارنة أداء الهجن (متوسّط الغلّة الفعليّة لكلّ هجين عبر
الحقول/المواسم). **صدق أوّلاً**: تُجمَّع فقط البيانات المُخزَّنة فعلاً في ``seasons``
(محصول/هجين/تاريخ بذار/غلّة فعليّة/غلّة مستهدفة) ضمن سياق المستأجِر (RLS). لا تلفيق —
حين تغيب الغلّة الفعليّة تكون قوائم الأداء فارغة وتُعلَن الفجوة عبر ``note_ar``.

التجميع منطق نقيّ في ``api.yield_analysis`` (قابل لاختبار وحدة بلا قاعدة)؛ هنا الجلب
فقط: SELECT مُرشَّح بالمستأجِر/الحقل/الموسم ثمّ تمرير الصفوف للمُجمِّع. الأذونات تُحاكي
الراوترات الشقيقة (``analytics``): ``ANALYTICS_VIEW`` + RLS. 503 عند تعذّر القاعدة.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.yield_analysis import assemble_yield_analysis

router = APIRouter()

# أعمدة المواسم اللازمة للتحليل — مع اسم الحقل من fields (JOIN للعرض البشريّ).
_YIELD_SELECT = (
    "s.season_id, s.field_id, f.name AS field_name, "
    "s.crops, s.cultivar, s.seed_variety_source, s.maturity, "
    "s.sowing_date, s.season_end, s.status, "
    "s.target_yield_kg_ha, s.actual_yield_kg_ha"
)


@router.get("/api/v1/analysis/yield")
async def yield_analysis_endpoint(
    field_id: str | None = Query(default=None, description="حصر التحليل بحقل واحد (اختياريّ)."),
    season: str | None = Query(
        default=None, description="حصر التحليل بموسم واحد عبر season_id (اختياريّ)."
    ),
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
):
    """تحليل الغلّة: الزراعة↔الحصاد لكلّ موسم + أداء الهجن — من بيانات مُخزَّنة فقط.

    مُرشَّح بالمستأجِر (RLS) + (اختياريّاً) بـ``field_id``/``season`` (season_id).
    يردّ مقارنة لكلّ موسم (محصول/هجين/تاريخ بذار/غلّة مستهدفة↔فعليّة) ومقارنة أداء
    الهجن (متوسّط الغلّة الفعليّة لكلّ هجين). صادق عند غياب البيانات (قوائم فارغة +
    ``note_ar``). 503 عند تعذّر القاعدة — لا أرقام وهميّة.
    """
    # بناء الترشيح الشرطيّ (المستأجِر مضمون عبر RLS؛ نضيف field/season صراحةً عند توفّرهما).
    where = ["1 = 1"]
    params: list[object] = []
    if field_id:
        params.append(field_id)
        where.append(f"s.field_id = ${len(params)}")
    if season:
        params.append(season)
        where.append(f"s.season_id = ${len(params)}")
    sql = (
        f"SELECT {_YIELD_SELECT} FROM seasons s "
        "LEFT JOIN fields f ON f.field_id = s.field_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY s.created_at DESC"
    )
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(sql, *params)
    except HTTPException:
        raise  # get_pool()/RLS ترفع 503/403 أصلاً — مرّرها كما هي
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة بيانات الغلّة", e) from e

    result = assemble_yield_analysis([dict(r) for r in rows], field_id=field_id, season=season)
    result["tenant_id"] = str(user.tenant_id)
    return result
