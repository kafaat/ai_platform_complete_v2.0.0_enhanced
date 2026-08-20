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
    UserSchema,
    get_current_user,
)
from api.trial_engine import (
    BlockResult,
    METObservation,
    analyze_met,
    analyze_paired_trial,
    build_digital_trial_envelope,
)
from api.trial_models import TrialAnalysisRequest
from shared.precision_agriculture.trial_spatial import design_spatial_rcbd

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
        out = verdict.to_dict()
        if req.spatial_plan is not None:
            spatial = req.spatial_plan
            out["spatial_trial"] = {
                "authority": "trial_design_only",
                "plots": design_spatial_rcbd(
                    trial_id=req.trial_id or "unbound-trial",
                    treatments=spatial.treatments,
                    n_blocks=spatial.n_blocks,
                    field_geometry=spatial.field_geometry,
                    machine_heading_deg=spatial.machine_heading_deg,
                    implement_width_m=spatial.implement_width_m,
                    randomization_seed=spatial.randomization_seed,
                    headland_m=spatial.headland_m,
                    strip_gap_m=spatial.strip_gap_m,
                    min_plot_area_m2=spatial.min_plot_area_m2,
                ),
            }
        if req.met_observations:
            met = analyze_met(
                [
                    METObservation(
                        observation.genotype,
                        observation.environment_id,
                        observation.yield_value,
                        observation.replicate,
                    )
                    for observation in req.met_observations
                ]
            )
            out["digital_trial"] = build_digital_trial_envelope(
                season_id=req.season_id,
                study_id=req.study_id,
                trial_id=req.trial_id,
                met=met,
            )
        return out
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
