"""api/routers/observations.py — تسجيل المشاهدات (Field Observations)
====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ/الثوابت النقيّة (``core.offline_first``) تُستورَد مباشرةً من وحدتها — وهي
نفس الكائنات التي يستوردها ``main`` (يبقى استخدامها هناك في ``/api/v1/sync`` فلا
يتيتّم استيرادها). أمّا التبعيات/النماذج وطابور المزامنة المُعرَّفة في ``main``
(``ObservationRequest``/``UserSchema``/``_OFFLINE_QUEUE``) فتبقى هناك وتُستورَد من
``api.main`` حفظاً لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ
التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from core.offline_first import OperationKind, record_operation_offline
from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    _OFFLINE_QUEUE,
    ObservationRequest,
    Permission,
    UserSchema,
    require_permission,
)

router = APIRouter()


@router.post("/api/v1/observations")
async def observations(
    req: ObservationRequest,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """تسجيل مشاهدة جديدة. في الإنتاج: يدخل DB. الآن: offline queue.

    إدامة: بعد التسجيل في الـqueue الذاكريّ، تُكتب العمليّة best-effort في جدول
    ‎offline_pending_ops‎ (إن توفّرت القاعدة) فتنجو من إعادة تشغيل العمليّة. لا
    قاعدة (CI/تطوير) ⇒ يبقى المسار الذاكريّ كما هو (لا كسر، fail-safe).
    """
    if req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    op = record_operation_offline(
        _OFFLINE_QUEUE,
        tenant_id=req.tenant_id,
        user_id=user.user_id,
        kind=OperationKind.OBSERVATION_CREATE,
        payload=req.model_dump(),
    )
    from api.offline_pending_db import persist_pending_best_effort

    await persist_pending_best_effort(op, user)
    return {
        "status": "recorded",
        "op_id": op.op_id,
        "queued_for_sync": True,
        "message_ar": "سُجّلت محلّياً، ستُحفظ عند الاتصال",
    }
