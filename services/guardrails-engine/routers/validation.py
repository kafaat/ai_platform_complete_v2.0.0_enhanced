"""routers/validation.py — الحَوكمة والموافقة البشريّة (Validation & HIL)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/الطرائق/الأجسام/
المخرجات/المصادقة مطابقة تماماً. توكن الخدمة (``_require_service_token``) ومنطق
``/validate`` fail-safe محفوظان بايتاً ببايت. التبعيّات المشتركة (المحرّك/النماذج/
المساعِدات/الـauth) تبقى في ``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)``
يضمّ هذا الراوتر بلا prefix.
"""

from __future__ import annotations

import main
from fastapi import APIRouter, Depends, HTTPException
from human_in_loop import HumanApprovalWorkflow

router = APIRouter()


@router.post("/validate", response_model=main.GuardrailsResult)
async def validate_action(
    request: main.GuardrailsRequest, _svc: bool = Depends(main._require_service_token)
):
    """Main validation endpoint — checks action against 3 tiers.

    أمان: يتطلّب توكن خدمة (X-Agent-Token) — لا يُقبل من جهة غير موثوقة.
    tenant_id يأتي في الطلب من خدمة موثوقة (supervisor تشتقّه من توكن
    المستخدم المُتحقَّق، لا من جسم طلب المستخدم مباشرةً).
    """
    engine = main.get_guardrails_engine()
    return await engine.validate(request)


@router.post("/approve/{workflow_id}")
async def approve_workflow(
    workflow_id: str, approved: bool, reason: str = "", claims: dict = Depends(main._gr_verify)
):
    """Human-in-the-Loop approval — الهويّة من التوكن المُتحقَّق لا من الطلب."""
    # الأمان: expert_id/expert_role/tenant_id كلّها من التوكن المُتحقَّق (لا من العميل):
    #  • منع انتحال الخبير،
    #  • منع IDOR عبر المستأجرين (تقييد الـworkflow بمستأجِر الطالب)،
    #  • تمرير الدور الصحيح لبوّابة الدور (كان reason يُربَط خطأً بـexpert_role
    #    فتفشل الموافقة دائماً، وreject كان يسقط لنقص وسيط إلزاميّ).
    expert_id = str(claims["sub"])
    expert_role = str(claims.get("role", ""))
    tenant_id = str(claims.get("tenant_id", ""))
    hil = HumanApprovalWorkflow()
    if approved:
        return await hil.approve(workflow_id, expert_id, expert_role, tenant_id, notes=reason)
    else:
        return await hil.reject(workflow_id, expert_id, expert_role, reason, tenant_id)


@router.get("/workflow/{workflow_id}")
async def get_workflow(workflow_id: str, claims: dict = Depends(main._gr_authn)):
    """حالة workflow — تتطلّب توكناً ومقيّدة بمستأجر الطالب (منع IDOR/تسريب).

    أمان: get_status أصبح يُرجع بيانات فعليّة (كان None)، فلولا التحقّق لأمكن لأيّ
    مجهول قراءة workflow أيّ مستأجر بمعرفة المعرّف. نُرجع 404 (لا 403) عند عدم
    تطابق المستأجر كي لا نكشف وجود الـworkflow عبر المستأجرين.
    """
    hil = HumanApprovalWorkflow()
    status = await hil.get_status(workflow_id)
    if status is None or str(status.get("tenant_id")) != str(claims.get("tenant_id")):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return status
