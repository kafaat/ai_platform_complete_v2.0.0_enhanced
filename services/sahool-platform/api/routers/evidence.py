"""api/routers/evidence.py — تظافر القرائن (Evidence Corroboration)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

النموذج ``CorroborationRequest`` يبقى مُعرَّفاً في ``api.main`` ويُستورَد من هنا
(حفظاً لـ_rebuild_pydantic_models). رموز ``api.evidence_corroboration`` (Evidence/
EvidenceType/corroborate) تُستورَد مباشرةً من وحدتها (نفس الرموز التي كان main
يستوردها — نُقل استيرادها هنا لإزالة F401 من main بعد النقل). لتفادي الاستيراد
الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.evidence_corroboration import Evidence, EvidenceType, corroborate
from api.main import CorroborationRequest, UserSchema, get_current_user

router = APIRouter()


@router.post("/api/v1/evidence/corroborate")
def evidence_corroborate(
    req: CorroborationRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يحدّد درجة التوصية (إرشاديّة/مؤيَّدة/مؤكَّدة) بتظافر القرائن + حضّ على الفحص."""
    try:
        evs = [Evidence(EvidenceType(e.etype), e.agrees, e.note_ar) for e in req.evidences]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"نوع قرينة غير معروف: {e}") from e
    return corroborate(
        evs, recommendation_key=req.recommendation_key, test_type_ar=req.test_type_ar
    ).to_dict()
