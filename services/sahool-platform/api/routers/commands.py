"""api/routers/commands.py — استبطان الأوامر (Commands / CQRS)
===============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات) تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا.
``CommandStore`` تُستورَد هنا من وحدتها الحقيقيّة ``api.command_store`` مباشرةً (نفس
الرمز الذي كان main يستورده). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا
الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

# CommandStore تُستورَد مباشرةً من وحدتها الحقيقيّة (نفس الرمز الذي كان main يستورده).
from api.command_store import CommandStore
from api.main import (
    UserSchema,
    get_current_user,
    get_pool,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/commands/{command_id}")
async def get_command(
    command_id: str,
    user: UserSchema = Depends(get_current_user),
):
    """يجلب أمراً من command_store (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        store = CommandStore(get_pool(), conn=conn)
        cmd = await store.get(command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail="الأمر غير موجود")
    return {"command_id": command_id, "found": True}
