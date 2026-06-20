"""api/routers/calibration.py — كشف ملفّات المعايرة الإقليميّة (#382)

GET فقط (قراءة بنية ثابتة): يكشف الملفّ العامّ وملفّات المناطق اليمنيّة الخمس مع
وسم `validated` صريح — فيرى المستخدم أيّ القيم مُعايَرة ميدانيّاً وأيّها افتراضات عامّة.

محفوظ النمط: مُسجَّل في main (يمرّ حارس التفكيك). `Depends(get_current_user)` اتّساقاً.
"""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.adaptive_calibration import propose_calibration_adjustment
from api.calibration import all_regions, get_calibration
from api.calibration_ingest import validate_region_calibration
from api.decision_lineage import ensure_decision_id, lineage_stage
from api.evidence_registry import aggregate_evidence, evidence_from_persisted_outcomes
from api.learning_feedback import learning_feedback
from api.main import UserSchema, _db_unavailable, get_current_user, tenant_connection

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


@router.get("/api/v1/calibration/{region}/evidence/persisted")
async def get_persisted_region_evidence(
    region: str,
    user: UserSchema = Depends(get_current_user),
):
    """دليل المنطقة التراكميّ المُدام — يُجمّع نتائج outcome_record المحفوظة (P0-2).

    يُغلق فجوة «دليل عابر»: بدل تمرير النتائج في الطلب (compute_region_evidence)، يقرأ هنا
    النتائج **المُدامة** للمستأجِر في هذه المنطقة (معزولة بـRLS) ويجمّعها — فيتراكم الدليل
    نحو عتبة التحقّق عبر الزمن، ويُغذّي /feedback و/adapt بدليل حقيقيّ. قراءة فقط؛ 503 عند
    تعذّر القاعدة. مسار قراءة (يتطلّب Postgres؛ مُختبَر تكامليّاً). الصدق: المنطق نفسه
    (evidence_from_persisted_outcomes ⇒ aggregate_evidence) — لا عتبة مكرّرة.
    """
    prof = get_calibration(region)
    try:
        async with tenant_connection(user) as conn:
            db_rows = await conn.fetch(
                "SELECT metrics, created_at FROM outcome_record WHERE region = $1 "
                "ORDER BY created_at ASC",
                prof.region,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة دليل المنطقة المُدام", e) from e

    rows: list[dict] = []
    for r in db_rows:
        m = r["metrics"]
        if isinstance(m, str):
            m = _json.loads(m)
        created = r["created_at"]
        rows.append({"metrics": m, "created_at": created.isoformat() if created else None})

    return evidence_from_persisted_outcomes(
        prof.region,
        rows,
        expert_calibrated=prof.evidence_level == "expert_opinion",
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
    decision_id: str | None = None  # نَسَب: يربط التكيّف بسلسلة القرار/الدليل


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
    out = propose_calibration_adjustment(
        prof.to_dict(), ev, mean_stress_delta=req.mean_stress_delta
    )
    did = ensure_decision_id(req.decision_id)
    out["decision_id"] = did
    out["lineage"] = lineage_stage(did, "adaptation", region=prof.region)
    return out


class AdaptFromEvidenceRequest(BaseModel):
    mean_stress_delta: float | None = None  # متوسّط (مرصود − متنبَّأ) لأيّام الإجهاد
    decision_id: str | None = None  # نَسَب: يربط التكيّف بسلسلة القرار/الدليل


@router.post("/api/v1/calibration/{region}/adapt-from-evidence")
async def propose_region_adaptation_from_evidence(
    region: str,
    req: AdaptFromEvidenceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقترح تعديل المعايرة محروساً بدليل **مُدام** متراكم (لا حمولة طلب).

    يُغلق حلقة التعلّم: يقرأ نتائج outcome_record المحفوظة للمنطقة (معزولة بـRLS) ويبني منها
    الدليل التراكميّ، ثمّ يطبّق بوّابة التكيّف عليه — فيعتمد القرار على دليل حقيقيّ مُتراكم عبر
    الزمن لا على نتائج مُمرَّرة في الطلب. صدق: applied=False (يقترح ولا يطبّق)؛ البوّابة كما هي.
    مسار قراءة (يتطلّب Postgres؛ مُختبَر تكامليّاً).
    """
    prof = get_calibration(region)
    try:
        async with tenant_connection(user) as conn:
            db_rows = await conn.fetch(
                "SELECT metrics, created_at FROM outcome_record WHERE region = $1 "
                "ORDER BY created_at ASC",
                prof.region,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة دليل المنطقة للتكيّف", e) from e

    rows: list[dict] = []
    for r in db_rows:
        m = r["metrics"]
        if isinstance(m, str):
            m = _json.loads(m)
        created = r["created_at"]
        rows.append({"metrics": m, "created_at": created.isoformat() if created else None})

    ev = evidence_from_persisted_outcomes(
        prof.region,
        rows,
        expert_calibrated=prof.evidence_level == "expert_opinion",
    )
    out = propose_calibration_adjustment(
        prof.to_dict(), ev, mean_stress_delta=req.mean_stress_delta
    )
    did = ensure_decision_id(req.decision_id)
    out["decision_id"] = did
    out["lineage"] = lineage_stage(did, "adaptation", region=prof.region)
    out["evidence_source"] = "persisted_outcomes"
    out["evidence_used"] = ev
    return out


class ProposeValuesRequest(BaseModel):
    raw_fraction: float | None = None
    root_depth_m: float | None = None
    kc_dyn_min: float | None = None
    kc_dyn_max: float | None = None
    forecast_infiltration: float | None = None
    yield_uncertainty: float | None = None
    price_uncertainty: float | None = None
    uptake_fractions: dict[str, float] | None = None
    source_ar: str | None = None


@router.post("/api/v1/calibration/{region}/propose-values")
def propose_region_values(
    region: str,
    req: ProposeValuesRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق من قيم معايرة مقترَحة لمنطقة ضدّ حدود زراعيّة آمنة — يقترح ولا يكتب.

    صدق: لا يُلفّق قيمة ولا يكتب إلى `_REGION_OVERRIDES`؛ يُرجِع `override_block`
    مُتحقَّقة لينسخها التشغيل يدويّاً بعد المراجعة (الاستمرار خطوة منفصلة).
    """
    return validate_region_calibration(
        region,
        {k: v for k, v in req.model_dump().items() if k != "source_ar" and v is not None},
        source_ar=req.source_ar,
    )
