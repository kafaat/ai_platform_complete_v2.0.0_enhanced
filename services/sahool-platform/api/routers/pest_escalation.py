"""api/routers/pest_escalation.py — تصعيد الآفة (Pest Escalation Workflow)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

النموذج ``PestEscalationRequest`` والمساعِد ``_get_workflow_store`` (مع مفرده
``_INMEM_WORKFLOW_STORES``) يبقيان مُعرَّفَين في ``api.main`` ويُستورَد المساعِد من
هنا (حفظاً لـ_rebuild_pydantic_models — لا تُنقَل النماذج/المساعِدات). الاستيرادات
الكسولة داخل الدالّة تبقى كما هي. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد
هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    Permission,
    PestEscalationRequest,
    UserSchema,
    _get_workflow_store,
    require_permission,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/v1/pest-escalation/run")
async def pest_escalation_run(
    req: PestEscalationRequest,
    user: UserSchema = Depends(require_permission(Permission.PESTICIDE_APPROVE)),
):
    """يشغّل/يستأنف تدفّق تصعيد الآفة (durable + HIL).

    أوّل نداء (بـpest_type/severity): يصل لخطوة الموافقة ثمّ يُعلَّق (suspended).
    نداء ثانٍ بنفس workflow_id + approval_status=approved: يُستأنف فينفّذ ثمّ يُتابع.
    سيادة: tenant_id من التوكن (لا من الجسم). HIL: لا تنفيذ قبل موافقة الخبير."""
    import asyncio as _aio

    from core.chemical_lineage import ChemicalBoundary, audit_chemical_lineage
    from core.correlation import set_correlation
    from core.pest_escalation_flow import run_pest_escalation
    from core.workflow_engine import workflow_trace

    set_correlation()  # خيط تتبّع موحّد لكلّ ما ينتج عن هذا الطلب
    lineage = audit_chemical_lineage(
        field_id=req.field_id,
        season_id=req.season_id,
        diagnosis_ref=req.diagnosis_ref,
        evidence_ref=req.evidence_ref,
        # Increment 2: tenant from the authenticated context (never the body) so the
        # hardened audit can check TENANT_MISMATCH against the diagnosis owner.
        tenant_id=str(user.tenant_id),
        boundary=(
            ChemicalBoundary.EXECUTE
            if req.approval_status == "approved"
            else ChemicalBoundary.DRAFT
        ),
        human_approval=req.approval_status == "approved",
    )
    if not lineage.compliant:
        logger.warning(
            "fii chemical lineage violation tenant_id=%s workflow_id=%s violations=%s mode=%s",
            user.tenant_id,
            req.workflow_id,
            ",".join(lineage.violations),
            lineage.mode,
        )
        if lineage.mode == "enforce":
            raise HTTPException(
                status_code=422, detail={"code": "CHEMICAL_LINEAGE_REQUIRED", **lineage.to_dict()}
            )
    initial: dict = {"chemical_lineage_audit": lineage.to_dict()}
    if req.season_id:
        initial["season_id"] = req.season_id
    if req.diagnosis_ref:
        initial["diagnosis_ref"] = req.diagnosis_ref
    if req.evidence_ref:
        initial["evidence_ref"] = req.evidence_ref
    if req.pest_type is not None:
        initial["pest_type"] = req.pest_type
    if req.severity:
        initial["severity"] = req.severity
    if req.field_id:
        initial["field_id"] = req.field_id
    if req.approval_status:
        initial["approval_status"] = req.approval_status

    store = _get_workflow_store(str(user.tenant_id))  # سياق RLS للقراءة/الاستئناف
    # المخزن المعمّر متزامن (asyncio.run داخليّاً) ⇒ نُشغّله في thread لا في الحلقة
    state = await _aio.to_thread(
        run_pest_escalation,
        req.workflow_id,
        store=store,
        tenant_id=str(user.tenant_id),
        initial_context=initial or None,
    )
    return {
        "workflow": workflow_trace(state),
        "context": state.context,
        "step_results": state.step_results,
    }
