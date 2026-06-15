"""api/routers/lifecycle.py — تحقّق انتقالات دورة حياة الحقل (Lifecycle)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

نموذج ``TransitionCheckRequest`` يبقى مُعرَّفاً في ``api.main`` ويُستورَد من هنا
(حفظاً لـ_rebuild_pydantic_models واستيرادات الاختبارات). ``LifecycleStage`` و
``is_valid_transition`` صارتا يتيمتي الاستخدام في ``main`` بعد النقل فتُستورَدان هنا
من وحدتهما الحقيقيّة ``api.field_lifecycle`` مباشرةً (إزالة F401). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

# LifecycleStage/is_valid_transition تُستورَدان مباشرةً من وحدتهما الحقيقيّة (نفس
# الرمزين اللذين كان main يستوردهما) لإزالة F401 من main بعد نقل هذه الدالّة.
from api.field_lifecycle import LifecycleStage, is_valid_transition
from api.main import (
    TransitionCheckRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/lifecycle/validate-transition")
def validate_transition(
    req: TransitionCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق هل انتقال مرحلة الحقل صالح (CREATED→PREPARED→...→HARVESTED)."""
    try:
        from_s = LifecycleStage(req.from_stage)
        to_s = LifecycleStage(req.to_stage)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"مرحلة غير معروفة: {e}") from e
    valid = is_valid_transition(from_s, to_s)
    return {
        "from_stage": from_s.value,
        "to_stage": to_s.value,
        "valid": valid,
        "reason_ar": "انتقال صالح"
        if valid
        else f"لا يُسمح بالانتقال من {from_s.value} إلى {to_s.value}",
    }
