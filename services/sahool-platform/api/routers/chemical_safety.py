"""api/routers/chemical_safety.py — السلامة الكيميائيّة (Chemical Safety)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.

``check_chemical``/``list_banned`` تُستورَدان مباشرةً من ``api.chemical_safety``
(نفس الكائنين اللذين كان ``main`` يستوردهما — نُقل الاستيراد هنا لإزالة F401 من
``main`` بعد نقل الدالّتين). نموذج الطلب ``ChemicalCheckRequest`` يبقى مُعرَّفاً في
``main`` ويُستورَد من ``api.main`` حفظاً لـ``_rebuild_pydantic_models`` واستيرادات
الاختبارات. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته
فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.chemical_safety import check_chemical, list_banned
from api.main import (
    ChemicalCheckRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/chemical-safety/check")
def chemical_safety_check(
    req: ChemicalCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يفحص مادّة كيميائيّة ضدّ الحظر الدولي والجرعة القصوى (فحص/تحذير، لا أتمتة)."""
    return check_chemical(req.chemical, dose_kg_ha=req.dose_kg_ha).to_dict()


@router.get("/api/v1/chemical-safety/banned")
def chemical_safety_banned():
    """قائمة المواد المحظورة/المقيّدة دوليّاً (شفافيّة)."""
    return list_banned()
