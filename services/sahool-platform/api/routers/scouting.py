"""api/routers/scouting.py — تصنيف المشاهدات (Scouting Taxonomy)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الكتالوجات/الدوالّ النقيّة (``api.scouting_pins``) تُستورَد مباشرةً من وحدتها — وهي
نفس الكائنات التي كانت في ``main`` (``make_pin`` يبقى مُستورَداً هناك لنقطة الـpins).
أمّا التبعية ``get_current_user``/``UserSchema`` فتبقى في ``main`` وتُستورَد من
``api.main`` حفظاً لاستيرادات الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    UserSchema,
    get_current_user,
)
from api.scouting_pins import (
    NUTRIENT_DEFICIENCY_GUIDE,
    YEMEN_CROP_ISSUES,
    get_crop_issues,
)

router = APIRouter()


@router.get("/api/v1/scouting/taxonomy")
def scouting_taxonomy(
    crop: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """قوائم المشاكل (للقوائم المنسدلة). لو crop معطى، يُرجع مشاكله فقط."""
    if crop:
        return {"crop": crop, "issues": get_crop_issues(crop)}
    return {
        "crops": list(YEMEN_CROP_ISSUES.keys()),
        "all_issues": YEMEN_CROP_ISSUES,
        "nutrient_guide": NUTRIENT_DEFICIENCY_GUIDE,
    }
