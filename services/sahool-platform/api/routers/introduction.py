"""api/routers/introduction.py — محاصيل/أشجار الإدخال (Crop Introduction)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.crop_introduction import crop_card, list_candidates
from api.main import (
    FieldFitRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.get("/api/v1/introduction/candidates")
def introduction_candidates_endpoint(zone: str | None = None):
    """محاصيل/أشجار مرشّحة للإدخال (zone: tihama/jawf) مستلهمة من المناطق المحاذية."""
    return list_candidates(zone)


@router.get("/api/v1/introduction/card")
def introduction_card_endpoint(crop: str):
    """البطاقة التعريفيّة لمحصول/شجرة مرشّحة (المتطلّبات + مصدر الاستلهام)."""
    return crop_card(crop)


@router.post("/api/v1/introduction/field-fit")
def introduction_field_fit_endpoint(
    req: FieldFitRequest, user: UserSchema = Depends(get_current_user)
):
    """فحص آلي: هل تربة/ظروف حقلك تناسب محصول الإدخال؟ (ربط بمحرّك الملاءمة)."""
    from api.crop_introduction import check_field_fit

    return check_field_fit(
        req.crop,
        req.ph,
        req.ec_dsm,
        req.season_rain_mm,
        req.temp_mean_c,
        req.irrigated,
    )
