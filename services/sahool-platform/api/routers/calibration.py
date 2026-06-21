"""api/routers/calibration.py — كشف ملفّات المعايرة الإقليميّة (#382)

GET فقط (قراءة بنية ثابتة): يكشف الملفّ العامّ وملفّات المناطق اليمنيّة الخمس مع
وسم `validated` صريح — فيرى المستخدم أيّ القيم مُعايَرة ميدانيّاً وأيّها افتراضات عامّة.

محفوظ النمط: مُسجَّل في main (يمرّ حارس التفكيك). `Depends(get_current_user)` اتّساقاً.
"""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.adaptive_calibration import propose_calibration_adjustment
from api.calibration import all_regions, apply_region_override, get_calibration
from api.calibration_ingest import validate_region_calibration
from api.decision_lineage import ensure_decision_id, lineage_stage
from api.evidence_registry import aggregate_evidence, evidence_from_persisted_outcomes
from api.learning_feedback import learning_feedback
from api.main import (
    UserSchema,
    _db_unavailable,
    _emit_domain_event,
    get_current_user,
    tenant_connection,
)

router = APIRouter()


# ── سجلّ تدقيق المعايرة (Calibration Audit Trail, v84) ─────────────────────────
# يُدوّن كلّ تغيير معايرة (تثبيت/عَكْس/تطبيق تكيّف) في جدول append-only calibration_audit
# مع لقطة القيم قبل/بعد + المصدر + المنفِّذ — فيصبح «من غيّر المعايرة ومتى وماذا» متتبَّعاً.
async def _read_override_values(conn, region: str) -> dict | None:
    """يقرأ القيم المُدامة الحاليّة لمنطقة (قبل upsert/delete) لتدقيق old_values —
    best-effort: لا تجاوز/تعذّر القراءة ⇒ None (لا تلفيق)."""
    try:
        row = await conn.fetchrow(
            "SELECT override_values FROM calibration_override WHERE region = $1", region
        )
    except Exception:  # noqa: BLE001 — قراءة تدقيق best-effort لا تكسر الكتابة
        return None
    if row is None:
        return None
    ov = row["override_values"]
    if isinstance(ov, str):
        ov = _json.loads(ov)
    return ov


async def _append_calibration_audit(
    conn,
    user: UserSchema,
    region: str,
    action: str,
    old_values: dict | None,
    new_values: dict | None,
    source_ar: str | None,
) -> None:
    """يُدرِج قيد تدقيق append-only ضمن **نفس معاملة** نقطة الكتابة (بعد كتابة
    calibration_override مباشرةً)، داخل **savepoint** best-effort: نجاحه ذرّيّ مع
    الكتابة الأصليّة، وفشله (مثلاً غياب الجدول قبل تطبيق v84) يُبتلَع ولا يُجهض الكتابة
    الأصليّة. الصدق: append-only (لا UPDATE/DELETE للسجلّ)؛ old_values قد تكون None إن
    لم تُقرأ القيم السابقة (لا تلفيق). يُصدِر CALIBRATION_AUDIT_RECORDED.
    """
    try:
        async with conn.transaction():  # SAVEPOINT داخل معاملة tenant_connection
            await conn.execute(
                """INSERT INTO calibration_audit
                    (tenant_id, region, action, old_values, new_values, source_ar, actor)
                   VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb, $6, $7)""",
                str(user.tenant_id),
                region,
                action,
                _json.dumps(old_values) if old_values is not None else None,
                _json.dumps(new_values) if new_values is not None else None,
                source_ar,
                str(user.user_id),
            )
        await _emit_domain_event(
            conn,
            user,
            "CALIBRATION_AUDIT_RECORDED",
            "calibration_audit",
            region,
            {"region": region, "action": action},
        )
    except Exception:  # noqa: BLE001 — تدقيق best-effort: فشله لا يكسر الكتابة الأصليّة
        pass


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


class AdaptApplyRequest(BaseModel):
    mean_stress_delta: float | None = None  # إشارة الاتّجاه (مرصود − متنبَّأ)
    decision_id: str | None = None  # نَسَب: يربط التطبيق بسلسلة القرار
    confirm: bool = False  # تأكيد صريح إلزاميّ (لا تطبيق عَرَضيّ — مبدأ الصدق)
    source_ar: str | None = None  # provenance؛ يُولَّد من الدليل إن غاب


@router.post("/api/v1/calibration/{region}/adapt-from-evidence/apply")
async def apply_region_adaptation_from_evidence(
    region: str,
    req: AdaptApplyRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يُطبّق تكيّف المعايرة المحروس بالدليل المُدام على متجر المعايرة (v80) — يُغلق الحلقة.

    يربط طرفَي الحلقة: نتيجة⇒دليل⇒تكيّف⇒**معايرة مُدامة**⇒قرارات لاحقة. لا يُدِيم إلا إذا:
    (أ) confirm=True صريح (موافقة بشريّة)، (ب) الاقتراح auto_apply_eligible (دليل
    field_verified + ≥العتبة + إشارة اتّجاه + تغيير فعليّ)، (ج) القيم تجتاز حدود الأمان.
    غير ذلك ⇒ لا إدامة، يُرجِع الاقتراح كما هو (applied=False). الخطوة محدودة ومقصوصة (±0.05)
    وعكوسيّة (DELETE override). 422 بلا تأكيد/خارج الأمان، 503 عند تعذّر القاعدة. مسار كتابة.
    """
    did = ensure_decision_id(req.decision_id)
    if not req.confirm:
        raise HTTPException(
            status_code=422,
            detail="تطبيق التكيّف يتطلّب تأكيداً صريحاً (confirm=true) — مبدأ الصدق (لا تطبيق خفيّ).",
        )
    prof = get_calibration(region)
    accepted: dict | None = None
    source_ar: str | None = None
    try:
        async with tenant_connection(user) as conn:
            db_rows = await conn.fetch(
                "SELECT metrics, created_at FROM outcome_record WHERE region = $1 "
                "ORDER BY created_at ASC",
                prof.region,
            )
            rows: list[dict] = []
            for r in db_rows:
                m = r["metrics"]
                if isinstance(m, str):
                    m = _json.loads(m)
                created = r["created_at"]
                rows.append({"metrics": m, "created_at": created.isoformat() if created else None})

            ev = evidence_from_persisted_outcomes(
                prof.region, rows, expert_calibrated=prof.evidence_level == "expert_opinion"
            )
            proposal = propose_calibration_adjustment(
                prof.to_dict(), ev, mean_stress_delta=req.mean_stress_delta
            )
            proposal["decision_id"] = did
            proposal["lineage"] = lineage_stage(did, "adaptation", region=prof.region)
            proposal["evidence_used"] = ev

            # غير مؤهَّل (محروس/بلا إشارة/بلا تغيير) ⇒ لا إدامة، نُعيد الاقتراح كما هو.
            if proposal.get("status") != "auto_apply_eligible":
                proposal["applied"] = False
                return proposal

            new_values = {p["parameter"]: p["proposed"] for p in proposal["proposals"]}
            source_ar = req.source_ar or (
                f"تكيّف آليّ محروس بدليل field_verified ({ev.get('sample_count', 0)} عيّنة) — {prof.region}"
            )
            # بوّابة أمان ثانية: القيم المقترَحة (المقصوصة) تجتاز حدود calibration_ingest.
            vres = validate_region_calibration(prof.region, new_values, source_ar=source_ar)
            if not (vres["validated"] and vres["ready_to_persist"]):
                proposal["applied"] = False
                proposal["validation"] = vres
                raise HTTPException(status_code=422, detail=proposal)
            accepted = vres["accepted"]

            await conn.execute(
                """INSERT INTO calibration_override
                    (tenant_id, region, override_values, source_ar, validated, created_by)
                   VALUES ($1::uuid, $2, $3::jsonb, $4, TRUE, $5)
                   ON CONFLICT (tenant_id, region) DO UPDATE SET
                     override_values = EXCLUDED.override_values,
                     source_ar       = EXCLUDED.source_ar,
                     validated       = TRUE,
                     updated_at      = now()""",
                str(user.tenant_id),
                prof.region,
                _json.dumps(accepted),
                source_ar,
                str(user.user_id),
            )
            await _emit_domain_event(
                conn,
                user,
                "CALIBRATION_OVERRIDE_SET",
                "calibration_override",
                prof.region,
                {"region": prof.region, "fields": list(accepted.keys()), "via": "adaptation"},
                critical=True,  # حوكمة المعايرة — fail-closed
            )
            # تدقيق append-only: تطبيق تكيّف آليّ محروس بالدليل (نفس المعاملة، best-effort).
            # old_values=None (لا نقرأ السابق هنا — لا تلفيق)؛ new_values=القيم المُدامة.
            await _append_calibration_audit(
                conn, user, prof.region, "adaptation_applied", None, accepted, source_ar
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("تطبيق تكيّف المعايرة", e) from e

    proposal["applied"] = True  # أُدِيم فعلاً في متجر المعايرة (عكوسيّ عبر DELETE)
    proposal["persisted_override"] = accepted
    proposal["source_ar"] = source_ar
    proposal["resolved"] = apply_region_override(prof.region, accepted, source_ar=source_ar)
    return proposal


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


# ── المعايرة الإقليميّة المُدارة DB-backed (يُكمل البند 3) ─────────────────────────
# بدل تعديل _REGION_OVERRIDES في الكود، يُدِيم المستأجِر قيمه المُتحقَّقة في القاعدة
# (calibration_override، معزول بـRLS) — قابل للإدارة والتدقيق والعكس، بلا تلفيق.


@router.post("/api/v1/calibration/{region}/override")
async def set_region_override(
    region: str,
    req: ProposeValuesRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يُدِيم قيم معايرة مُتحقَّقة لمنطقة (المستأجِر) في القاعدة — معايرة مُدارة DB-backed.

    يتحقّق أوّلاً (validate_region_calibration: حدود زراعيّة آمنة + مصدر provenance)؛ لا
    يُدِيم إلا قيماً **مقبولة مع مصدر** (upsert على tenant×region) + حدث CALIBRATION_OVERRIDE_SET.
    422 إن رُفِض حقل أو غاب المصدر (لا تلفيق، يُرجِع تفصيل التحقّق). 503 عند تعذّر القاعدة.
    مسار كتابة (يتطلّب Postgres). الصدق: يُدِيم المقبول فقط؛ القرار يبقى للمستخدم (لا تعديل خفيّ).
    """
    submitted = {k: v for k, v in req.model_dump().items() if k != "source_ar" and v is not None}
    result = validate_region_calibration(region, submitted, source_ar=req.source_ar)
    if not (result["validated"] and result["ready_to_persist"]):
        # لم يُتحقَّق (رفض/نقص مصدر) ⇒ لا إدامة؛ نُعيد سبب الرفض للمستخدم.
        raise HTTPException(status_code=422, detail=result)

    prof = get_calibration(region)
    accepted = result["accepted"]
    try:
        async with tenant_connection(user) as conn:
            # نقرأ القيم السابقة قبل الـupsert لتدقيق old_values (best-effort؛ تبقى
            # None إن لم يوجد تجاوز سابق أو تعذّرت القراءة — لا تلفيق).
            old_values = await _read_override_values(conn, prof.region)
            await conn.execute(
                """INSERT INTO calibration_override
                    (tenant_id, region, override_values, source_ar, validated, created_by)
                   VALUES ($1::uuid, $2, $3::jsonb, $4, TRUE, $5)
                   ON CONFLICT (tenant_id, region) DO UPDATE SET
                     override_values = EXCLUDED.override_values,
                     source_ar       = EXCLUDED.source_ar,
                     validated       = TRUE,
                     updated_at      = now()""",
                str(user.tenant_id),
                prof.region,
                _json.dumps(accepted),
                req.source_ar,
                str(user.user_id),
            )
            await _emit_domain_event(
                conn,
                user,
                "CALIBRATION_OVERRIDE_SET",
                "calibration_override",
                prof.region,
                {"region": prof.region, "fields": list(accepted.keys())},
                critical=True,  # حوكمة المعايرة — fail-closed
            )
            # تدقيق append-only: تثبيت تجاوز (نفس المعاملة، best-effort). new=المقبول.
            await _append_calibration_audit(
                conn, user, prof.region, "override_set", old_values, accepted, req.source_ar
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("إدامة معايرة المنطقة", e) from e

    return {
        "region": prof.region,
        "persisted": True,
        "accepted": accepted,
        "source_ar": req.source_ar,
        "resolved": apply_region_override(prof.region, accepted, source_ar=req.source_ar),
    }


@router.get("/api/v1/calibration/{region}/resolved")
async def get_resolved_region_calibration(
    region: str,
    user: UserSchema = Depends(get_current_user),
):
    """ملفّ المنطقة بعد دمج تجاوز المستأجِر المُدام (إن وُجد) — معزول بـRLS.

    لا تجاوز مُدام ⇒ القاعدة الموروثة (override_source=inherited، validated=false). تجاوز
    مُدام ⇒ القيم المُعايَرة مطبَّقة (override_source=db_override). 503 عند تعذّر القاعدة.
    مسار قراءة (يتطلّب Postgres؛ مُختبَر تكامليّاً). الصدق: المنطق نفسه (apply_region_override).
    """
    prof = get_calibration(region)
    try:
        async with tenant_connection(user) as conn:
            row = await conn.fetchrow(
                "SELECT override_values, source_ar FROM calibration_override WHERE region = $1",
                prof.region,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة معايرة المنطقة المُدامة", e) from e

    if row is None:
        return apply_region_override(prof.region, {})  # القاعدة الموروثة (لا تجاوز)
    ov = row["override_values"]
    if isinstance(ov, str):
        ov = _json.loads(ov)
    return apply_region_override(prof.region, ov, source_ar=row["source_ar"])


@router.get("/api/v1/calibration/overrides/all")
async def list_region_overrides(user: UserSchema = Depends(get_current_user)):
    """تجاوزات المعايرة المُدامة للمستأجِر (كلّ المناطق) — معزولة بـRLS، قراءة فقط.

    لإدارة الملفّات المُعايَرة (أيّ المناطق صار لها قيم مُدامة ومصدرها). 503 عند تعذّر القاعدة.
    """
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT region, override_values, source_ar, validated, updated_at "
                "FROM calibration_override ORDER BY region"
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة تجاوزات المعايرة", e) from e

    items = []
    for r in rows:
        ov = r["override_values"]
        if isinstance(ov, str):
            ov = _json.loads(ov)
        updated = r["updated_at"]
        items.append(
            {
                "region": r["region"],
                "override_values": ov,
                "source_ar": r["source_ar"],
                "validated": r["validated"],
                "updated_at": updated.isoformat() if updated is not None else None,
            }
        )
    return {"overrides": items, "count": len(items)}


@router.delete("/api/v1/calibration/{region}/override")
async def delete_region_override(
    region: str,
    user: UserSchema = Depends(get_current_user),
):
    """يحذف تجاوز المنطقة المُدام ويعيدها للوراثة العامّة — عكوسيّة (مبدأ الصدق). معزول بـRLS.

    لا حالة خفيّة دائمة: المعايرة المُدارة قابلة للعكس متى تبيّن خطؤها. 503 عند تعذّر القاعدة.
    """
    prof = get_calibration(region)
    try:
        async with tenant_connection(user) as conn:
            # نقرأ السابق قبل الحذف لتدقيق old_values (best-effort — لا تلفيق).
            old_values = await _read_override_values(conn, prof.region)
            await conn.execute("DELETE FROM calibration_override WHERE region = $1", prof.region)
            # تدقيق append-only: عَكْس/حذف التجاوز (نفس المعاملة، best-effort).
            # old=السابق، new=None (عاد للوراثة العامّة).
            await _append_calibration_audit(
                conn, user, prof.region, "reverted", old_values, None, None
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حذف معايرة المنطقة", e) from e
    return {"region": prof.region, "reverted": True}


def _audit_row(r) -> dict:
    """يُشكّل صفّ تدقيق نقيّاً (يفكّ JSONB إن جاء نصّاً، يطبّع التواريخ ISO) — للقراءة."""
    old = r["old_values"]
    if isinstance(old, str):
        old = _json.loads(old)
    new = r["new_values"]
    if isinstance(new, str):
        new = _json.loads(new)
    created = r["created_at"]
    return {
        "audit_id": str(r["audit_id"]),
        "region": r["region"],
        "action": r["action"],
        "old_values": old,
        "new_values": new,
        "source_ar": r["source_ar"],
        "actor": r["actor"],
        "created_at": created.isoformat() if created is not None else None,
    }


@router.get("/api/v1/calibration/{region}/audit")
async def get_region_calibration_audit(
    region: str,
    user: UserSchema = Depends(get_current_user),
):
    """سجلّ تدقيق المعايرة لمنطقة المستأجِر (الأحدث أوّلاً، معزول بـRLS) — قراءة فقط.

    يكشف كلّ تغيير معايرة مُدوَّن (override_set/reverted/adaptation_applied) مع لقطة القيم
    قبل/بعد + المصدر + المنفِّذ + الزمن — append-only فلا يُعدَّل ولا يُمحى. 503 عند تعذّر
    القاعدة. مسار قراءة (يتطلّب Postgres؛ مُختبَر تكامليّاً).
    """
    prof = get_calibration(region)
    try:
        async with tenant_connection(user) as conn:
            rows = await conn.fetch(
                "SELECT audit_id, region, action, old_values, new_values, source_ar, actor, "
                "created_at FROM calibration_audit WHERE region = $1 ORDER BY created_at DESC",
                prof.region,
            )
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قراءة سجلّ تدقيق المعايرة", e) from e

    items = [_audit_row(r) for r in rows]
    return {"region": prof.region, "audit": items, "count": len(items)}
