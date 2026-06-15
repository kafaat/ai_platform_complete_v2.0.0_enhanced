"""api/routers/crop_suitability.py — ملاءمة المحاصيل (Crop Suitability)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``FieldConditions``/``rank_crops`` تُستورَدان مباشرةً من ``api.crop_suitability``
(نفس الكائنين اللذين كان ``main`` يستوردهما — نُقل الاستيراد هنا لإزالة F401 من
``main`` بعد نقل الدالّة). نموذج الطلب ``CropSuitabilityRequest`` يبقى مُعرَّفاً في
``main`` ويُستورَد من ``api.main`` حفظاً لـ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته
فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.crop_suitability import FieldConditions, rank_crops
from api.main import (
    CropSuitabilityRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/crop-suitability")
def crop_suitability(
    req: CropSuitabilityRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يرتّب المحاصيل بمعايير مرجّحة شفّافة (يحجب دون بيانات تربة حاكمة)."""
    cond = FieldConditions(
        ph=req.ph,
        ec_dsm=req.ec_dsm,
        season_rain_mm=req.season_rain_mm,
        temp_mean_c=req.temp_mean_c,
        irrigated=req.irrigated,
    )
    try:
        return rank_crops(cond, req.crops)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
