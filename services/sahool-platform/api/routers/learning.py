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

from fastapi import APIRouter, Depends, HTTPException

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

    pairs: list = []
    schema_ready = True  # False فقط عند غياب الجدول/العمود
    try:
        async with tenant_connection(user) as conn:
            try:
                async with conn.transaction():  # savepoint — يعزل غياب الجدول
                    # وحدة التكرار = المزرعة (farm_id) لا المستأجِر: تحت RLS يكون
                    # tenant_id ثابتاً، فعدّه لا يقيس الاستقلال (تفادي pseudoreplication).
                    q = (
                        "SELECT predicted_yield_t_ha AS pred, actual_yield_t_ha AS act, "
                        "crop AS crop_id, farm_id::text AS fid "
                        "FROM recommendation_outcomes "
                        "WHERE predicted_yield_t_ha IS NOT NULL "
                        "AND actual_yield_t_ha IS NOT NULL"
                    )
                    params: list = []
                    if crop_id:
                        q += " AND crop = $1"
                        params.append(crop_id)
                    rows = await conn.fetch(q, *params)
                pairs = [
                    PredictionPair(float(r["pred"]), float(r["act"]), r["crop_id"], r["fid"])
                    for r in rows
                ]
            except (_asyncpg.UndefinedColumnError, _asyncpg.UndefinedTableError):
                schema_ready = False
                pairs = []
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
        raise _db_unavailable("معايرة التنبّؤ", e) from e

    result = analyze_systematic_bias(pairs)
    # live_data_wired = جاهزيّة الربط/المخطّط (لا وجود الأزواج)؛ has_pairs منفصل.
    result["schema_ready"] = schema_ready
    result["live_data_wired"] = schema_ready
    result["has_pairs"] = bool(pairs)
    result["data_source_note_ar"] = (
        "الأزواج من recommendation_outcomes (توقّع تاريخي + نتيجة فعليّة) عبر RLS "
        "(v49 مُفعَّل)، ووحدة التكرار = المزرعة (farm_id) لا المستأجِر (تفادي "
        "pseudoreplication). بلا أزواج كافية: «عيّنة غير كافية» بصدق (لا تصحيح)."
    )
    return result
