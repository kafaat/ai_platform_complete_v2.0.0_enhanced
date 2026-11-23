"""api/routers/learning.py — التعلّم والمعايرة (Learning & Calibration)
====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.learning_feedback import list_pending_learning_proposals, record_learning_proposal_review
from api.main import (
    ExternalPriorBlendRequest,
    Permission,
    UserSchema,
    _db_unavailable,
    get_current_user,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.post("/api/v1/learning/external-prior-blend")
def external_prior_blend(
    req: ExternalPriorBlendRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يمزج سابقة خارجيّة منشورة ببيانات اليمن بوزن تدرّجي n/(n+K) — تظافر قرائن صادق.

    للاستفادة من مشاريع/أوراق خارجيّة (مثل CropSight-US) لمحاصيل تُزرَع في اليمن:
    السابقة الخارجيّة قرينة ضعيفة متلاشية (ثقة ≤50%، غير متحقّقة محلّيّاً)، تتلاشى
    كلّما تراكم محلّي. محصول غير مزروع في اليمن ⇒ غير منطبق (لا استيراد قيمة أجنبيّة).
    دون الحجم المطلوب: تلميح يُصعَّد لمرشد عبر human_escalation.
    """
    from core.engines.external_prior_blend import blend_external_prior

    return blend_external_prior(
        req.external_prior,
        req.local_estimate,
        req.n_local,
        crop_grown_in_yemen=req.crop_grown_in_yemen,
        external_credibility=req.external_credibility,
    )


@router.get("/api/v1/learning/activation-status")
async def learning_activation_status(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """حالة بوّابة تفعيل التعلّم للمستأجر — مدفوعة بتدفّق البيانات (v49).

    تُحسب الأعداد حيّاً من recommendation_outcomes عبر RLS: إجماليّ التوصيات،
    المكتملة (نتيجة مسجّلة)، المقبولة، وضمن نافذة النضج. قبل العتبة: خاملة بصدق
    (لا تتظاهر بتعلّم لم يبدأ). جدول غير مفعَّل ⇒ لقطة صفريّة صريحة.
    """
    import asyncpg as _asyncpg
    from core.learning_activation import DataFlowSnapshot, evaluate_activation

    tenant = str(getattr(user, "tenant_id", ""))
    total = completed = accepted = within_lag = 0
    schema_ready = True
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب الجدول
                    row = await conn.fetchrow(
                        """SELECT COUNT(*) AS total,
                                  COUNT(*) FILTER (WHERE actual_yield_t_ha IS NOT NULL) AS completed,
                                  COUNT(*) FILTER (WHERE accepted) AS accepted,
                                  COUNT(*) FILTER (
                                      WHERE matured_within_lag AND actual_yield_t_ha IS NOT NULL
                                  ) AS within_lag
                           FROM recommendation_outcomes"""
                    )
                total = int(row["total"] or 0)
                completed = int(row["completed"] or 0)
                accepted = int(row["accepted"] or 0)
                within_lag = int(row["within_lag"] or 0)
            except (_asyncpg.UndefinedTableError, _asyncpg.UndefinedColumnError):
                schema_ready = False
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("حالة تفعيل التعلّم", e) from e

    snapshot = DataFlowSnapshot(
        tenant_id=tenant,
        completed_outcomes=completed,
        total_recommendations=total,
        accepted_recommendations=accepted,
        outcomes_within_lag=within_lag,
    )
    result = evaluate_activation(snapshot)
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["data_source_note_ar"] = (
        "الأعداد تُحسب حيّاً من recommendation_outcomes عبر RLS (v49 مُفعَّل). "
        "البوّابة مدفوعة بالبيانات: خاملة بصدق حتى تتراكم نتائج كافية وناضجة."
        if schema_ready
        else "جدول recommendation_outcomes غير مفعَّل — لقطة صفريّة صريحة (خاملة)."
    )
    return result


@router.get("/api/v1/learning/prediction-calibration")
async def prediction_calibration_status(
    crop_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """حالة معايرة التنبّؤ من التاريخ المتراكم (الانحياز المنهجي + التصحيح التدريجي).

    يحلّل أزواج (توقّع,نتيجة) التاريخيّة: هل نُفرط/نُقلّل منهجيّاً؟ ويطبّق تصحيحاً
    متدرّجاً (shrinkage). قبل عيّنة كافية: لا تصحيح (النموذج الأساسي كما هو).

    جدول recommendation_outcomes مُفعَّل (v49)؛ يُحلّل أزواجه الفعليّة عبر RLS.
    بلا أزواج كافية (≥3، ≥2 مزرعة) يُرجِع «عيّنة غير كافية» بصدق (correction_factor=1.0).
    """
    import asyncpg as _asyncpg
    from core.learning.prediction_calibration import (
        PredictionPair,
        analyze_systematic_bias,
    )
    from core.outcome_reconciler import recommendation_outcome_eligibility

    pairs: list = []
    excluded: dict[str, int] = {}
    schema_ready = True  # False فقط عند غياب الجدول/العمود
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب الجدول
                    # وحدة التكرار = المزرعة (farm_id) لا المستأجِر: تحت RLS يكون
                    # tenant_id ثابتاً، فعدّه لا يقيس الاستقلال (تفادي pseudoreplication).
                    q = (
                        "SELECT predicted_yield_t_ha AS pred, actual_yield_t_ha AS act, "
                        "crop AS crop_id, farm_id::text AS fid, accepted, matured_within_lag "
                        "FROM recommendation_outcomes "
                        "WHERE predicted_yield_t_ha IS NOT NULL "
                        "AND actual_yield_t_ha IS NOT NULL"
                    )
                    params: list = []
                    if crop_id:
                        q += " AND crop = $1"
                        params.append(crop_id)
                    rows = await conn.fetch(q, *params)
                # F9: سياسةُ الأهليّة المشتركة (U02) قبل المعايرة — نتيجةٌ غير ناضجة أو غير منتهية
                # لا تدخل الانحياز. دقّةُ التوقّع لا تشترط القبول (كما في learning_feedback).
                for r in rows:
                    verdict = recommendation_outcome_eligibility(
                        {
                            "predicted_yield_t_ha": r["pred"],
                            "actual_yield_t_ha": r["act"],
                            "matured_within_lag": r["matured_within_lag"],
                        },
                        require_acceptance=False,
                    )
                    if verdict["eligible"]:
                        pairs.append(
                            PredictionPair(
                                float(r["pred"]), float(r["act"]), r["crop_id"], r["fid"]
                            )
                        )
                    else:
                        reason = str(verdict["reason"])
                        excluded[reason] = excluded.get(reason, 0) + 1
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                schema_ready = False
                pairs = []
                excluded = {}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("معايرة التنبّؤ", e) from e

    result = analyze_systematic_bias(pairs)
    # live_data_wired = جاهزيّة الربط/المخطّط (لا وجود الأزواج)؛ has_pairs منفصل.
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["has_pairs"] = bool(pairs)
    result["excluded_count"] = sum(excluded.values())
    result["excluded_reasons"] = excluded
    result["data_source_note_ar"] = (
        "الأزواج من recommendation_outcomes (توقّع تاريخي + نتيجة فعليّة) عبر RLS "
        "(v49 مُفعَّل)، ووحدة التكرار = المزرعة (farm_id) لا المستأجِر (تفادي "
        "pseudoreplication). بلا أزواج كافية: «عيّنة غير كافية» بصدق (لا تصحيح)."
    )
    return result


# ── مراجعة مرشَّحات التعلّم المحكومة (G14 / F-D02) ─────────────────────────────────────
# ``governed_model_promotion_candidates`` و``irrigation_learning_proposals`` تُكتبان بـ
# ``review_required`` و``auto_promote``/``auto_adjust`` = FALSE ولم يكن لهما مسارُ مراجعة.
# مساران: القائمة المعلَّقة، وتسجيلُ قرارٍ بهويّةٍ وزمنٍ وسبب. **التسجيلُ ليس تطبيقاً**: لا
# ترقيةَ ولا تعديلَ ولا استدعاءَ لسجلّ النماذج أو محرّك الريّ (``applied: False`` دائماً).
# الصلاحية ``DECISION_MODEL_ACTIVATION_APPROVE`` — صلاحيّةُ مراجعة تفعيل النماذج نفسُها
# (``decision_review.review_model_activation_request_boundary``)؛ لا دورَ جديد.
LearningProposalKind = Literal["model_promotion", "irrigation"]


class LearningProposalReview(BaseModel):
    """قرار المراجِع: ``accept``/``reject`` مع سببٍ غير فارغ."""

    decision: Literal["accept", "reject"]
    reason: str = Field(min_length=1, max_length=2000)
    # مرشَّحٌ مجمَّع يحمل ``pool_digest`` في دليله: الاعتمادُ يُسمّي البصمةَ التي رآها المراجِع.
    reviewed_pool_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason required")
        return value.strip()


@router.get("/api/v1/learning/governed-proposals")
async def list_governed_learning_proposals(
    kind: LearningProposalKind | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_ACTIVATION_APPROVE)),
):
    """المرشَّحات المعلَّقة (غير ``approved``/``rejected``) للمستأجِر — قراءةٌ فقط تحت RLS."""
    try:
        async with tenant_connection(user) as conn:
            items = await list_pending_learning_proposals(conn, kind=kind, limit=limit)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("قائمة مرشَّحات التعلّم", e) from e
    return {"items": items, "count": len(items), "read_only": True}


@router.post("/api/v1/learning/governed-proposals/{kind}/{proposal_id}/review")
async def review_governed_learning_proposal(
    kind: LearningProposalKind,
    proposal_id: str,
    req: LearningProposalReview,
    user: UserSchema = Depends(require_permission(Permission.DECISION_MODEL_ACTIVATION_APPROVE)),
):
    """يسجّل قرار المراجِع ولا يطبّقه: ``status`` + ``reviewed_by`` + ``reviewed_at`` وحدثُ السبب.

    مستأجِرٌ آخر/معرّفٌ مجهول ⇒ 404 (RLS). القرارُ نفسه ثانيةً ⇒ إعادةٌ بلا حدثٍ ثانٍ؛ المعاكس ⇒ 409.
    انتقالٌ مرفوض (اعتمادٌ من غير ``review_ready``، بصمةُ مجمّعٍ لا تطابق) ⇒ 409.
    """
    try:
        async with tenant_connection(user) as conn:
            return await record_learning_proposal_review(
                conn,
                kind=kind,
                proposal_id=proposal_id,
                decision=req.decision,
                reason=req.reason,
                reviewed_by=str(user.user_id),
                tenant_id=str(user.tenant_id),
                reviewed_pool_digest=req.reviewed_pool_digest,
            )
    except LookupError as e:
        raise HTTPException(status_code=404, detail="learning proposal not found") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق (لا قرارَ مُسجَّلٌ جزئيّاً)
        raise _db_unavailable("تسجيل مراجعة مرشَّح التعلّم", e) from e
