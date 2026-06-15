"""api/routers/me.py — هوية المستخدم الحالي (Current Identity)
======================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: المسار/الأذونات/المخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات) تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا
تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ التبعيات).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.get("/api/v1/me")
def me(user: UserSchema = Depends(get_current_user)):
    """بيانات المستخدم الحالي (الهوية + المستأجر + الدور)."""
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role.value,
        "name_ar": user.name_ar,
    }
