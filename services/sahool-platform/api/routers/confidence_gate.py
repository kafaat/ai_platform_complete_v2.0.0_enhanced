"""api/routers/confidence_gate.py — بوّابة الثقة الموحّدة (Confidence Gate)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

النموذج ``ConfidenceGateRequest`` يبقى مُعرَّفاً في ``api.main`` ويُستورَد من هنا
(حفظاً لـ_rebuild_pydantic_models). رموز ``api.confidence_gate`` (EngineSignal/
evaluate) تُستورَد مباشرةً من وحدتها (نفس الرموز التي كان main يستوردها — نُقل
استيرادها هنا لإزالة F401 من main بعد النقل). لتفادي الاستيراد الدائريّ:
``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.confidence_gate import EngineSignal
from api.confidence_gate import evaluate as _gate_eval
from api.main import ConfidenceGateRequest, UserSchema, get_current_user

router = APIRouter()


@router.post("/api/v1/confidence-gate")
def confidence_gate(
    req: ConfidenceGateRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيّم إشارات المحرّكات ويقرّر مستوى الثقة (واثقة/مراجعة/محجوبة)."""
    signals = [
        EngineSignal(
            engine=s.engine,
            has_recommendation=s.has_recommendation,
            confidence=s.confidence,
            blocking_reason_ar=s.blocking_reason_ar,
            data_gaps_ar=s.data_gaps_ar,
        )
        for s in req.signals
    ]
    return _gate_eval(signals).to_dict()
