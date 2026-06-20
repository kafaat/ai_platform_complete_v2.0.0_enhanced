"""api/routers/calibration.py — كشف ملفّات المعايرة الإقليميّة (#382)

GET فقط (قراءة بنية ثابتة): يكشف الملفّ العامّ وملفّات المناطق اليمنيّة الخمس مع
وسم `validated` صريح — فيرى المستخدم أيّ القيم مُعايَرة ميدانيّاً وأيّها افتراضات عامّة.

محفوظ النمط: مُسجَّل في main (يمرّ حارس التفكيك). `Depends(get_current_user)` اتّساقاً.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.adaptive_calibration import propose_calibration_adjustment
from api.calibration import all_regions, get_calibration
from api.evidence_registry import aggregate_evidence
from api.learning_feedback import learning_feedback
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


class EvidenceRecord(BaseModel):
    region: str
    evidence_level: str = "none"
    sample_count: int = 0
    success_rate: float | None = None
    success_flag_counts: dict[str, int] = Field(default_factory=dict)
    samples_to_verified: int = 0


class FeedbackRequest(BaseModel):
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)


@router.post("/api/v1/calibration/feedback")
def compute_learning_feedback(
    req: FeedbackRequest,
    user: UserSchema = Depends(get_current_user),
):
    """حلقة التغذية الراجعة: تقترح أين المعايرة ضعيفة وأيّ المعاملات تحتاج مراجعة بشريّة.

    صدق: اقتراحات فقط — `auto_adjust=False` صريح؛ القرار للإنسان (Adaptive لاحقاً).
    """
    return learning_feedback([r.model_dump() for r in req.evidence_records])


class AdaptRequest(BaseModel):
    evidence: EvidenceRecord
    mean_stress_delta: float | None = None  # متوسّط (مرصود − متنبَّأ) لأيّام الإجهاد


@router.post("/api/v1/calibration/{region}/adapt")
def propose_region_adaptation(
    region: str,
    req: AdaptRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقترح تعديل معايرة المنطقة تحت بوّابة الدليل — يقترح ولا يطبّق (#388).

    صدق: applied=False (لا تعديل خفيّ)؛ الخطوة محدودة ومقصوصة وعكوسيّة؛ بلا دليل
    field_verified كافٍ ⇒ gated.
    """
    prof = get_calibration(region)
    ev = aggregate_evidence(
        prof.region,
        [],
        expert_calibrated=prof.evidence_level == "expert_opinion",
    )
    # نستعمل دليل الطلب المُمرَّر (المتراكم) لا الفارغ.
    ev.update(req.evidence.model_dump())
    return propose_calibration_adjustment(
        prof.to_dict(), ev, mean_stress_delta=req.mean_stress_delta
    )
