"""api/routers/ipm.py — الإدارة المتكاملة للآفات (IPM)
======================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

نهج متدرّج، الكيميائي ملاذ أخير. ``ipm_plan``/``pests_for_crop``/``supported_pests``
تُستورَد مباشرةً من ``api.ipm_advisor`` (نفس الكائنات التي كان ``main`` يستوردها —
نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدوالّ). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.ipm_advisor import ipm_plan, pests_for_crop
from api.ipm_advisor import supported_pests as ipm_pests

router = APIRouter()


@router.get("/api/v1/ipm/pests")
def ipm_pests_endpoint():
    """الآفات المدعومة بخطّة إدارة متكاملة."""
    return {"pests": ipm_pests()}


@router.get("/api/v1/ipm/plan")
def ipm_plan_endpoint(pest: str):
    """خطّة الإدارة المتكاملة لآفة: وقاية → مراقبة → حيوي → كيميائي (ملاذ أخير)."""
    return ipm_plan(pest)


@router.get("/api/v1/ipm/crop-pests")
def ipm_crop_pests_endpoint(crop: str):
    """الآفات المحتملة لمحصول (للوقاية الاستباقيّة)."""
    return pests_for_crop(crop)
