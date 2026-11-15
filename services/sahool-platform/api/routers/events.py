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

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

# EventBus تُستورَد مباشرةً من وحدتها الحقيقيّة (نفس الرمز الذي كان main يستورده)
# لإزالة F401 من main بعد نقل هذه الدالّة.
from api.event_bus import HISTORY_PAGE_MAX, EventBus, InvalidHistoryCursor
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
    limit: int = Query(100, ge=1, le=HISTORY_PAGE_MAX),
    cursor: str | None = Query(None, max_length=512),
    order: Literal["asc", "desc"] = "asc",
    user: UserSchema = Depends(get_current_user),
):
    """صفحة من تاريخ أحداث entity (عبر tenant_connection — RLS مُطبَّق).

    keyset على (occurred_at, seq): ``order=desc`` يُرجع أحدث ``limit`` حدثاً، و``next_cursor``
    المعتم يستأنف بالاتّجاه نفسه (``None`` = لا مزيد). limit خارج 1..HISTORY_PAGE_MAX أو مؤشّر
    مشوَّه ⇒ 422 (C-13/C-21).
    """
    async with tenant_connection(user) as conn:
        bus = EventBus(get_pool(), conn=conn)
        try:
            return await bus.query_entity_history_page(
                entity_type, entity_id, limit=limit, cursor=cursor, order=order
            )
        except InvalidHistoryCursor as exc:
            raise HTTPException(status_code=422, detail=f"cursor غير صالح: {exc}") from exc
