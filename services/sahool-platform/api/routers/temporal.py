"""api/routers/temporal.py — التحكيم الزمني (Temporal Arbitration)
===============================================================
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

# استيراد مباشر من الوحدة الأصليّة: بعد نقل المعالِجَين لم يبقَ في main.py
# مستخدِم آخر لـ DataSource/Measurement/TemporalArbiter فأصبحت يتيمة (F401) —
# حُلّت بنقل الاستيراد إلى الموجِّه من مصدره مباشرةً (api.temporal_arbitration).
from api.main import (
    TemporalCheckRequest,
    TemporalCoherenceRequest,
    UserSchema,
    _parse_iso_utc,
    get_current_user,
)
from api.temporal_arbitration import DataSource, Measurement, TemporalArbiter

router = APIRouter()


@router.post("/api/v1/temporal/check")
def temporal_check(
    req: TemporalCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتحقّق أنّ القراءات متّسقة زمنياً (لا NDVI قديم مع ET0 حديث)."""
    arbiter = TemporalArbiter()
    measurements = [
        Measurement(
            source=DataSource(m.source),
            timestamp=_parse_iso_utc(m.timestamp),
            value=m.value,
        )
        for m in req.measurements
    ]
    result = arbiter.check_combination(measurements, crop=req.crop, stage=req.stage)
    return {
        "valid": result.valid,
        "age_span_days": result.age_span_days,
        "issues": [
            {"severity": i.severity, "code": i.code, "message_ar": i.message_ar}
            for i in result.issues
        ],
    }


@router.post("/api/v1/temporal/coherence")
def temporal_coherence(
    req: TemporalCoherenceRequest,
    user: UserSchema = Depends(get_current_user),
):
    """مرجع زمني موحّد + كشف الانحراف الدلالي بين المحرّكات."""
    from api.temporal_coherence import check_temporal_coherence, make_temporal_context

    try:
        ctx = make_temporal_context(req.current_date, req.planting_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    check = check_temporal_coherence(ctx, gdd_days_counted=req.gdd_days_counted)
    return {"context": ctx.to_dict(), "coherence": check.to_dict()}
