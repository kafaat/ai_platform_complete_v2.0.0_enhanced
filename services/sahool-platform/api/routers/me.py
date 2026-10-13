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
async def me(user: UserSchema = Depends(get_current_user)):
    """بيانات المستخدم الحالي (الهوية + المستأجر + الدور) + غلافُ سياسة الذكاء للمستأجِر.

    ``ai_policy_envelope`` (TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01): الخدماتُ التي
    تُرسِل بيانات المستأجِر خارجاً (tts-service) تقرأ سياستَه من هنا بتوكن المستخدم نفسه —
    المنصّةُ سلطةُ السياسة، ولا مسارَ جديد (ميزانيّةُ المسارات 629/629). الغلافُ نفسُه الذي
    يُختَم في حزمة سياق الحقل: صفٌّ غائب أو تعذّرُ القراءة ⇒ الأشدّ (``local_only``)،
    والهويّةُ تُعاد مهما حدث للقراءة.
    """
    from core.ai_policy_envelope import build_ai_policy_envelope, load_tenant_ai_policy_row

    from api.main import tenant_connection

    policy_row = None
    try:
        async with tenant_connection(user) as conn:
            policy_row = await load_tenant_ai_policy_row(conn, str(user.tenant_id))
    except Exception:  # noqa: BLE001 - تعذّر الاتّصال ⇒ الغلافُ الأشدّ، والهويّةُ لا تسقط
        policy_row = None
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role.value,
        "name_ar": user.name_ar,
        "ai_policy_envelope": build_ai_policy_envelope(str(user.tenant_id), policy_row),
    }
