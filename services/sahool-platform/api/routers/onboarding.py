"""api/routers/onboarding.py — التهيئة الأوّليّة (Onboarding)
==========================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    OnboardingSubmitRequest,
    UserSchema,
    get_current_user,
    tenant_connection,
)
from api.onboarding import get_questionnaire
from api.onboarding import validate_response as _ob_validate

router = APIRouter()


@router.get("/api/v1/onboarding/questionnaire")
async def onboarding_questionnaire(
    phase: int | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """يُرجع تعريف الاستبيان (phase=1 للإلزامي فقط، بلا معامل للكلّ).

    مصمّم للسياق اليمني: offline-first، RTL، أسئلة إلزاميّة قليلة."""
    return get_questionnaire(phase=phase)


@router.post("/api/v1/onboarding/responses")
async def submit_onboarding(
    req: OnboardingSubmitRequest,
    # خدمة ذاتيّة لإعداد المستأجِر — مفتوحة عمداً لأيّ مستخدم مُصادَق (معزولة بالمستأجِر/RLS، لا حارس صلاحيّة).
    user: UserSchema = Depends(get_current_user),
):
    """يحفظ ردّ الاستبيان (عبر tenant_connection — RLS مُطبَّق).

    يتحقّق من اكتمال الحقول الإلزاميّة ويُرجع الناقص إن وُجد."""
    check = _ob_validate(req.answers)
    import json as _json

    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """INSERT INTO onboarding_responses
                 (tenant_id, farmer_id, field_id, answers, is_complete, answered_count)
               VALUES ($1::uuid, $2, $3, $4::jsonb, $5, $6)
               RETURNING id""",
            str(user.tenant_id),
            str(user.user_id),
            req.field_id,
            _json.dumps(req.answers, ensure_ascii=False),
            check["valid"],
            check["answered"],
        )
    return {
        "id": row["id"] if row else None,
        "valid": check["valid"],
        "missing_required": check["missing"],
        "answered_count": check["answered"],
    }


@router.get("/api/v1/onboarding/responses")
async def list_onboarding(
    field_id: str | None = None,
    user: UserSchema = Depends(get_current_user),
):
    """يسرد ردود الاستبيان للمستأجر (عبر tenant_connection — RLS مُطبَّق)."""
    async with tenant_connection(user) as conn:
        if field_id:
            rows = await conn.fetch(
                "SELECT id, field_id, is_complete, answered_count, created_at "
                "FROM onboarding_responses WHERE field_id = $1 ORDER BY created_at DESC",
                field_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, field_id, is_complete, answered_count, created_at "
                "FROM onboarding_responses ORDER BY created_at DESC LIMIT 100"
            )
    return {"responses": [dict(r) for r in rows]}
