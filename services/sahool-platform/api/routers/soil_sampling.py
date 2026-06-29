"""api/routers/soil_sampling.py — بروتوكول أخذ عيّنة التربة (Soil Sampling)
=========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

دوالّ النطاق (``soil_sampling_protocol``) كانت مُستورَدة على مستوى وحدة ``main``
وتُستخدَم حصريّاً من هذه الـendpoints؛ نُقل استيرادها هنا (من المصدر مباشرةً)
لتفادي استيراد يتيم في ``main`` بعد النقل — لا تغيير سلوكيّ.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission
from api.soil_sampling_protocol import (
    sampling_depth,
    sampling_protocol,
    subsamples_for_area,
)

router = APIRouter()


@router.get("/api/v1/soil-sampling/subsamples")
def soil_subsamples_endpoint(area_ha: float):
    """عدد العيّنات الفرعيّة الموصى بها حسب مساحة الحقل."""
    return subsamples_for_area(area_ha)


@router.get("/api/v1/soil-sampling/depth")
def soil_depth_endpoint(purpose: str = "general"):
    """العمق المناسب لأخذ العيّنة حسب الغرض (general/nitrate/no_till/orchard)."""
    return sampling_depth(purpose)


@router.get("/api/v1/soil-sampling/protocol")
def soil_protocol_endpoint(area_ha: float | None = None, purpose: str = "general"):
    """البروتوكول الكامل لأخذ عيّنة تربة صحيحة (خطوات + تحذيرات + توقيت)."""
    return sampling_protocol(area_ha, purpose)


# ── Lab Sampling v2: soil/water sample points + lab decision context ─────────
# Lightweight in-memory adapter for local/dev and test environments. Production can
# swap these handlers to DB persistence while preserving the API contract. The
# important contract is explicit GPS coordinates, sample status, and no fabricated
# decision values.
from datetime import date  # noqa: E402
from typing import Literal  # noqa: E402
from uuid import uuid4  # noqa: E402

from core.irrigation_water_analysis import WaterSample, analyze_water_sample  # noqa: E402
from core.lab_sampling import (  # noqa: E402
    SoilLabResult,
    analyze_soil_lab_result,
    lab_decision_context,
)
from pydantic import BaseModel, Field  # noqa: E402


class LabSampleIn(BaseModel):
    field_id: str
    kind: Literal["soil", "water"]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    sampled_on: date | None = None
    depth_cm_from: int | None = None
    depth_cm_to: int | None = None
    source: str | None = None
    status: Literal["planned", "collected", "submitted", "analyzed", "approved"] = "collected"
    gps_accuracy_m: float | None = Field(default=None, ge=0)


class SoilLabResultIn(BaseModel):
    sample_id: str
    ph: float | None = None
    ec_dsm: float | None = None
    organic_matter_pct: float | None = None
    nitrogen_mg_kg: float | None = None
    phosphorus_mg_kg: float | None = None
    potassium_mg_kg: float | None = None
    cec_cmol_kg: float | None = None
    calcium_carbonate_pct: float | None = None
    texture: str | None = None
    approved: bool = False


_LAB_SAMPLES: dict[str, dict] = {}
_SOIL_RESULTS: dict[str, dict] = {}
_WATER_RESULTS: dict[str, dict] = {}


@router.get("/api/v1/lab/samples")
def list_lab_samples(
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    rows = list(_LAB_SAMPLES.values())
    if field_id:
        rows = [r for r in rows if r.get("field_id") == field_id]
    return rows


@router.post("/api/v1/lab/samples")
def create_lab_sample(
    payload: LabSampleIn,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    sample_id = f"{payload.kind[:1]}-{uuid4().hex[:10]}"
    row = payload.model_dump(mode="json")
    row["sample_id"] = sample_id
    _LAB_SAMPLES[sample_id] = row
    return row


@router.post("/api/v1/lab/soil-results")
def submit_soil_lab_result(
    payload: SoilLabResultIn,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    analysis = analyze_soil_lab_result(SoilLabResult(**payload.model_dump()))
    _SOIL_RESULTS[payload.sample_id] = analysis
    if payload.sample_id in _LAB_SAMPLES:
        _LAB_SAMPLES[payload.sample_id].update(
            {
                "status": "approved" if payload.approved else "analyzed",
                "ph": payload.ph,
                "ec_dsm": payload.ec_dsm,
                "organic_matter_pct": payload.organic_matter_pct,
                "nitrogen_mg_kg": payload.nitrogen_mg_kg,
                "phosphorus_mg_kg": payload.phosphorus_mg_kg,
                "potassium_mg_kg": payload.potassium_mg_kg,
                "approved": payload.approved,
            }
        )
    return analysis


@router.post("/api/v1/lab/water-results")
def submit_water_lab_result(
    payload: WaterSample,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    analysis = analyze_water_sample(payload)
    _WATER_RESULTS[payload.sample_id] = analysis
    if payload.sample_id in _LAB_SAMPLES:
        _LAB_SAMPLES[payload.sample_id].update(
            {
                "status": "analyzed",
                "ph": payload.ph,
                "ec_dsm": payload.ec_dsm,
                "sar": analysis["indices"]["sar"],
                "rsc_meq_l": analysis["indices"]["rsc_meq_l"],
            }
        )
    return analysis


@router.get("/api/v1/fields/{field_id}/lab-context")
def field_lab_context(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    sample_ids = [s["sample_id"] for s in _LAB_SAMPLES.values() if s.get("field_id") == field_id]
    latest_soil = next(
        (_SOIL_RESULTS[sid] for sid in reversed(sample_ids) if sid in _SOIL_RESULTS), None
    )
    latest_water = next(
        (_WATER_RESULTS[sid] for sid in reversed(sample_ids) if sid in _WATER_RESULTS), None
    )
    return lab_decision_context(soil=latest_soil, water=latest_water)
