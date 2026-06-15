"""api/routers/replay.py — إعادة بناء الحالة من الأحداث (Replay / event_replay)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

نموذج ``ReplayRequest`` يبقى مُعرَّفاً في ``api.main`` ويُستورَد من هنا (حفظاً
لـ_rebuild_pydantic_models واستيرادات الاختبارات). ``FieldStateReconstructor`` صارت
يتيمة الاستخدام في ``main`` بعد النقل فتُستورَد هنا من وحدتها الحقيقيّة
``api.event_replay`` مباشرةً (إزالة F401). لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

# FieldStateReconstructor تُستورَد مباشرةً من وحدتها الحقيقيّة (نفس الرمز الذي كان
# main يستورده) لإزالة F401 من main بعد نقل هذه الدالّة.
from api.event_replay import FieldStateReconstructor
from api.main import (
    ReplayRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/replay/reconstruct")
def replay_reconstruct(
    req: ReplayRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يُعيد بناء حالة الـentity من سجلّ الأحداث (pure reconstruction).

    ملاحظة: يأخذ الأحداث في الـrequest. النسخة المُوصَّلة بالـDB (تجلب
    الأحداث من events table) تحتاج PostgreSQL — غير مُفعَّلة بعد.
    """
    state = FieldStateReconstructor.reconstruct(
        req.entity_type,
        req.entity_id,
        req.events,
    )
    return {
        "entity_id": state.entity_id,
        "entity_type": state.entity_type,
        "field_name": state.field_name,
        "lifecycle_stage": state.lifecycle_stage,
        "area_ha": state.area_ha,
        "crop": state.crop,
        "planting_date": state.planting_date,
        "harvest_date": state.harvest_date,
        "irrigation_count": state.irrigation_count,
        "fertilizer_count": state.fertilizer_count,
        "last_ndvi": state.last_ndvi,
        "total_events": state.total_events,
        "last_event_at": state.last_event_at,
    }
