"""api/routers/market.py — فجوة السوق وجاهزيّة التصنيف (Market Gap)
================================================================
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

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/market/crop-gap")
async def market_crop_gap(
    zone_key: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """خريطة تركّز المحاصيل وفجوة السوق لمنطقة (إسقاط مبدأ LULC على حقول المنصّة).

    يكشف التشبّع (فائض محتمل) والفرص (محاصيل مناسبة قليلة الزراعة). صدق: حقول
    المنصّة المشتركة فقط (عيّنة لا مسح)، اتجاه نسبي لا رقم مطلق، لا تنبّؤ سعر.

    عمود zone_key مُفعَّل (v49)؛ تُملأ قيمته لكلّ حقل عبر PATCH /fields/{id}
    (zone_key من agro_climate_zones). الحقول بلا zone_key لا تدخل التجميع — صدق
    بلا تخمين.
    """
    import asyncpg as _asyncpg
    from core.engines.crop_market_gap import CropConcentration, regional_crop_map

    from api.agro_climate_zones import suited_for_zone

    concentrations: list = []
    suitability: dict = {}
    schema_ready = True  # يصبح False فقط عند غياب العمود/الجدول (لا عند 0 صفوف)
    try:
        async with tenant_connection(user) as conn:
            try:
                # SAVEPOINT يعزل غياب العمود/الجدول عن معاملة RLS (لا يُجهضها).
                async with conn.transaction():
                    rows = await conn.fetch(
                        """SELECT f.crop AS crop_id, COUNT(*) AS cnt
                           FROM fields f
                           WHERE f.zone_key = $1 AND f.crop IS NOT NULL
                           GROUP BY f.crop""",
                        zone_key,
                    )
                total = sum(r["cnt"] for r in rows) or 0
                suited = suited_for_zone(zone_key)
                # suited_for_zone يُرجِع suited_crops_ar (أسماء عربيّة)؛ مطابقة
                # crop_id بالاسم تقريبيّة — تُحسَّن عند توحيد قاموس المحاصيل.
                suited_names = set(suited.get("suited_crops_ar", []))
                for r in rows:
                    concentrations.append(
                        CropConcentration(
                            crop_id=r["crop_id"],
                            zone_key=zone_key,
                            field_count=r["cnt"],
                            total_fields_in_zone=total,
                        )
                    )
                    suitability[r["crop_id"]] = r["crop_id"] in suited_names
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                # المخطّط غير جاهز (zone_key/الجدول غير مفعَّل) — يميَّز عن «لا بيانات».
                schema_ready = False
                concentrations = []
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تحليل فجوة سوق المنطقة", e) from e

    # مفاتيح ميتا ثابتة دائماً (استقرار API): نفس التعريف في كلّ المسارات.
    meta = {"zone_key": zone_key, "schema_ready": schema_ready, "live_data_wired": schema_ready}
    if not concentrations:
        meta["total_crops_analysed"] = 0
        meta["note_ar"] = (
            "عمود/جدول مطلوب غير مفعَّل في المخطّط — لا تخمين."
            if not schema_ready
            else "المخطّط جاهز لكن لا حقول كافية بالمنصّة في هذه المنطقة — لا تخمين."
        )
        return meta
    return {**meta, **regional_crop_map(concentrations, suitability)}


@router.get("/api/v1/market/crop-classification-readiness")
async def crop_classification_readiness_endpoint(
    zone_key: str,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """جاهزيّة تصنيف المحاصيل بالأقمار لمنطقة (البوّابة الصادقة نحو فجوة سوق أشمل).

    يقيس عيّنات التدريب المتاحة (حقول المنصّة: محصول معروف + حدود GPS) ويقرّر
    متى يصبح التصنيف ممكناً. قبل الكفاية: التصنيف «غير متاح» بصدق (لا اختراع).
    """
    import asyncpg as _asyncpg
    from core.engines.crop_classification_readiness import (
        CropSampleInventory,
        assess_classification_readiness,
    )

    fields_by_crop: dict[str, int] = {}
    schema_ready = True  # False فقط عند غياب العمود/الجدول
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب العمود/الجدول
                    rows = await conn.fetch(
                        """SELECT f.crop AS crop_id, COUNT(*) AS cnt
                           FROM fields f
                           JOIN field_boundaries fb ON fb.field_id = f.field_id
                           WHERE f.zone_key = $1 AND f.crop IS NOT NULL
                                 AND fb.geom IS NOT NULL
                           GROUP BY f.crop""",
                        zone_key,
                    )
                fields_by_crop = {r["crop_id"]: r["cnt"] for r in rows}
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                schema_ready = False
                fields_by_crop = {}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("جاهزيّة تصنيف المحاصيل", e) from e

    inv = CropSampleInventory(
        zone_key=zone_key,
        fields_with_crop_and_gps=fields_by_crop,
        avg_temporal_scenes=0.0,  # يُحسب من /imagery/timeseries لاحقاً (مؤجَّل)
        gps_quality_ok=bool(fields_by_crop),
    )
    result = assess_classification_readiness(inv)
    # live_data_wired = جاهزيّة الربط/المخطّط (لا وجود الصفوف)؛ has_sample_data منفصل.
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["has_sample_data"] = bool(fields_by_crop)
    result["data_source_note_ar"] = (
        "⚠ العيّنات من حقول المنصّة (محصول معروف + حدود GPS). المشاهد الزمنيّة "
        "(avg_temporal_scenes) تُحسب من /imagery/timeseries لاحقاً — مؤجَّل بعد "
        "التشغيل؛ حتى ذلك تُقدَّر صفراً (التصنيف يُعلَن غير جاهز بصدق)."
    )
    return result
