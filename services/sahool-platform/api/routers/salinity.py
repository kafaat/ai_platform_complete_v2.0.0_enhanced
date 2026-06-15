"""api/routers/salinity.py — إدارة الملوحة (Salinity Management)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدالّة النقيّة (``api.salinity_management``) تُستورَد مباشرةً من وحدتها — وهي نفس
الكائن الذي كان في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعيات/النموذج
المُعرَّفة في ``main`` فتبقى هناك وتُستورَد من ``api.main`` حفظاً
لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    SalinityRequest,
    UserSchema,
    get_current_user,
)
from api.salinity_management import salinity_assessment

router = APIRouter()


@router.post("/api/v1/salinity/assess")
def salinity_assess_endpoint(
    req: SalinityRequest,
    user: UserSchema = Depends(get_current_user),
):
    """تقييم شامل للملوحة: تصنيف التربة/الماء + احتياج الغسيل + خطر الصوديوم."""
    return salinity_assessment(
        ece_dsm=req.ece_dsm,
        ecw_dsm=req.ecw_dsm,
        sar=req.sar,
        crop_threshold_ece=req.crop_threshold_ece,
    )
