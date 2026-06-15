"""api/routers/data_readiness.py — اكتمال البيانات (Data Readiness)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدالّة النقيّة (``api.data_readiness``) تُستورَد مباشرةً من وحدتها — وهي نفس الكائن
الذي كان في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعيات/النموذج
المُعرَّفة في ``main`` فتبقى هناك وتُستورَد من ``api.main`` حفظاً
لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.data_readiness import assess_readiness
from api.main import (
    ReadinessRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/data-readiness")
def data_readiness(
    req: ReadinessRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيّم اكتمال البيانات: ما المتاح الآن، ما المحجوب، وما التالي الأعلى أثراً."""
    return assess_readiness(req.provided_fields).to_dict()
