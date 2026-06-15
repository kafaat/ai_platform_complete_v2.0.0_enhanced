"""api/routers/failures.py — كشف أنماط الفشل (Failure Detection)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

النموذج ``FailureCheckRequest`` يبقى مُعرَّفاً في ``api.main`` ويُستورَد من هنا
(حفظاً لـ_rebuild_pydantic_models). دوالّ ``api.failure_modes`` تُستورَد مباشرةً
من وحدتها (نفس الرموز التي كان main يستوردها — نُقل استيرادها هنا لإزالة F401 من
main بعد النقل). لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في
نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.failure_modes import (
    detect_sentinel_issues,
    detect_soil_issues,
    detect_weather_issues,
)
from api.main import FailureCheckRequest, UserSchema, get_current_user

router = APIRouter()


@router.post("/api/v1/failures/check")
def check_failures(
    req: FailureCheckRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يفحص حالات الفشل المعروفة (سحب، طقس قديم، تربة)."""
    failures = []
    if req.cloud_pct is not None and req.days_since_observation is not None:
        f = detect_sentinel_issues(req.cloud_pct, req.days_since_observation)
        if f:
            failures.append(f.to_dict())
    if req.weather_hours_since_update is not None:
        f = detect_weather_issues(req.weather_hours_since_update)
        if f:
            failures.append(f.to_dict())
    if req.soil:
        for f in detect_soil_issues(req.soil):
            failures.append(f.to_dict())
    return {"failures": failures, "count": len(failures)}
