"""api/routers/observations.py — تسجيل المشاهدات (Field Observations)
====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

عقد المشاهدات القديم محفوظ؛ أضيف مظروف إفادة الري المرتبطة بالمهمة إلى المسار نفسه.
لا يضيف المظروف مساراً، ولا يحوّل المشاهدة إلى اعتماد ري أو قيد مياه.

الدوالّ/الثوابت النقيّة (``core.offline_first``) تُستورَد مباشرةً من وحدتها — وهي
نفس الكائنات التي يستوردها ``main`` (يبقى استخدامها هناك في ``/api/v1/sync`` فلا
يتيتّم استيرادها). أمّا التبعيات/النماذج وطابور المزامنة المُعرَّفة في ``main``
(``ObservationRequest``/``UserSchema``/``_OFFLINE_QUEUE``) فتبقى هناك وتُستورَد من
``api.main`` حفظاً لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ
التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from typing import Annotated

from core.offline_first import OperationKind, record_operation_offline
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BeforeValidator

from api.irrigation_observations import TaskIrrigationObservationRequest
from api.main import (
    _OFFLINE_QUEUE,
    ObservationRequest,
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.task_irrigation_observations import record_observation

router = APIRouter()


def _select_observation_contract(value):
    # Never let an invalid irrigation envelope fall back to the legacy model,
    # whose compatibility behavior ignores unknown fields.
    if isinstance(value, dict) and ("irrigation_observation" in value or "task_id" in value):
        return TaskIrrigationObservationRequest.model_validate(value)
    return value


ObservationInput = Annotated[
    ObservationRequest | TaskIrrigationObservationRequest,
    BeforeValidator(_select_observation_contract),
]


@router.post("/api/v1/observations")
async def observations(
    req: ObservationInput,
    user: UserSchema = Depends(require_permission(Permission.OBSERVATION_RECORD)),
):
    """تسجيل مشاهدة بالعقد القديم أو مظروف {task_id, irrigation_observation}.

    إفادة الري تُحفظ كحدث ملحق داخل معاملة، وتتطلب قاعدة متاحة؛ لا تعتمد الماء.
    العقد القديم يبقى في الطابور الذاكري مع إدامة best-effort في
    offline_pending_ops. تعذّر القاعدة لا يحوّل إفادة الري إلى الطابور القديم.
    """
    if isinstance(req, TaskIrrigationObservationRequest):
        try:
            async with tenant_connection(user) as conn:
                return await record_observation(conn, user, req.task_id, req.irrigation_observation)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _db_unavailable("تسجيل ملاحظة الري", exc) from exc

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
