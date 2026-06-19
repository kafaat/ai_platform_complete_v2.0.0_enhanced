"""api/routers/calibration.py — كشف ملفّات المعايرة الإقليميّة (#382)

GET فقط (قراءة بنية ثابتة): يكشف الملفّ العامّ وملفّات المناطق اليمنيّة الخمس مع
وسم `validated` صريح — فيرى المستخدم أيّ القيم مُعايَرة ميدانيّاً وأيّها افتراضات عامّة.

محفوظ النمط: مُسجَّل في main (يمرّ حارس التفكيك). `Depends(get_current_user)` اتّساقاً.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.calibration import all_regions, get_calibration
from api.evidence_registry import aggregate_evidence
from api.main import UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/calibration")
def list_calibration(user: UserSchema = Depends(get_current_user)):
    """كلّ ملفّات المعايرة (العامّ + المناطق اليمنيّة) مع وسم التحقّق."""
    return {
        "generic": get_calibration(None).to_dict(),
        "regions": [get_calibration(r).to_dict() for r in all_regions()],
        "validated_count": sum(get_calibration(r).validated for r in all_regions()),
        "note_ar": "المناطق غير المُتحقَّقة ترث الافتراضات العامّة — تحتاج قياسات ميدانيّة",
    }


@router.get("/api/v1/calibration/{region}")
def get_region_calibration(region: str, user: UserSchema = Depends(get_current_user)):
    """ملفّ معايرة منطقة واحدة (يطبّع العربيّة؛ المجهولة ⇒ العامّ)."""
    return get_calibration(region).to_dict()


class OutcomeRecord(BaseModel):
    n_evaluated: int = 0
    n_success: int = 0
    success_flags: list[str] = Field(default_factory=list)
    evaluated_at: str | None = None


class EvidenceRequest(BaseModel):
    region: str
    outcomes: list[OutcomeRecord] = Field(default_factory=list)


@router.post("/api/v1/calibration/{region}/evidence")
def compute_region_evidence(
    region: str,
    req: EvidenceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يجمّع نتائج القياس الميدانيّ لمنطقة في دليل تراكميّ (لا تعديل آليّ للمعايرة).

    يربط مخرجات /outcome/measure بـsample_count/evidence_level للمنطقة. صدق: العتبة
    تقديريّة، والنتائج الفارغة لا تُحتسب عيّنة.
    """
    prof = get_calibration(region)
    expert = prof.evidence_level == "expert_opinion"
    return aggregate_evidence(
        prof.region,
        [o.model_dump() for o in req.outcomes],
        expert_calibrated=expert,
    )
