"""api/routers/queue.py — حالة طابور المزامنة (Offline Queue Status)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import _OFFLINE_QUEUE, UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/queue/status")
def queue_status(user: UserSchema = Depends(get_current_user)):
    """حالة الـoffline queue للـtenant الحالي."""
    from core.offline_first import queue_summary

    return queue_summary(_OFFLINE_QUEUE, user.tenant_id)
