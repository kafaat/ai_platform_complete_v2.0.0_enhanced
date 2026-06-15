"""api/routers/events.py — استبطان أحداث الكيانات (Events / event_bus)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

⚠ هذا الموجِّه للمسار ``/api/v1/events/{entity_type}/{entity_id}`` فقط (تاريخ أحداث
كيان من event_bus). ``EventBus`` صارت يتيمة الاستخدام في ``main`` بعد النقل فتُستورَد
هنا من وحدتها الحقيقيّة ``api.event_bus`` مباشرةً (إزالة F401). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

# EventBus تُستورَد مباشرةً من وحدتها الحقيقيّة (نفس الرمز الذي كان main يستورده)
# لإزالة F401 من main بعد نقل هذه الدالّة.
from api.event_bus import EventBus
from api.main import (
    UserSchema,
    get_current_user,
    get_pool,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/events/{entity_type}/{entity_id}")
async def entity_events(
    entity_type: str,
    entity_id: str,
    limit: int = 100,
    user: UserSchema = Depends(get_current_user),
):
    """تاريخ أحداث entity من event_bus (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        bus = EventBus(get_pool(), conn=conn)
        return {"events": await bus.query_entity_history(entity_type, entity_id, limit=limit)}
