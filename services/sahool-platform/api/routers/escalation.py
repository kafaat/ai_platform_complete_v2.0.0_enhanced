"""api/routers/escalation.py — تصعيد الشكّ لإنسان (Human Escalation)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

النموذج ``EscalationAssessRequest`` يبقى مُعرَّفاً في ``api.main`` ويُستورَد من
هنا (حفظاً لـ_rebuild_pydantic_models). لتفادي الاستيراد الدائريّ: ``api.main``
يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import EscalationAssessRequest, UserSchema, get_current_user

router = APIRouter()


@router.post("/api/v1/escalation/assess")
def escalation_assess(
    req: EscalationAssessRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقرّر تصعيد الشكّ لإنسان من ثقة مصدر (محرّك/RAG) — actionable (مستلِم/أولويّة/مجهول).

    يعمّم مبدأ confidence_gate لأيّ مصدر ثقة (لا المحرّكات فقط): بلا سند/ثقة كافية →
    تصعيد لمرشد زراعي لا إجابة مولّدة (human-in-the-loop). confidence=None أو
    has_answer=false ⇒ BLOCKED (لا تأليف). للمحرّكات استعمل /confidence-gate ثمّ
    escalation_from_gate.
    """
    from core.engines.human_escalation import assess_escalation

    return assess_escalation(
        req.confidence,
        source=req.source,
        has_answer=req.has_answer,
        uncertain_points=req.uncertain_points,
    )
