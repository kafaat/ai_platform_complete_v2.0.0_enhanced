"""api/routers/trials.py — محرّك التجارب الإحصائي (Trial Analysis)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ النقيّة (``api.trial_engine``) تُستورَد مباشرةً من وحدتها — وهي نفس الكائنات
التي كانت في ``main`` (لا تُبقى استيراداً يتيماً هناك). أمّا التبعيات/النماذج
المُعرَّفة في ``main`` فتبقى هناك وتُستورَد من ``api.main`` حفظاً
لـ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.main import (
    TrialAnalysisRequest,
    UserSchema,
    get_current_user,
)
from api.trial_engine import BlockResult, analyze_paired_trial

router = APIRouter()


@router.post("/api/v1/trials/analyze")
def analyze_trial(
    req: TrialAnalysisRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يُحلّل تجربة مقترنة (t-test مزدوج + LSD) ويُعطي حُكماً صادقاً."""
    blocks = [BlockResult(b.block_number, b.treatment_yield, b.control_yield) for b in req.blocks]
    try:
        verdict = analyze_paired_trial(
            blocks,
            confidence_level=req.confidence_level,
            treatment_label_ar=req.treatment_label_ar,
        )
        return verdict.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
