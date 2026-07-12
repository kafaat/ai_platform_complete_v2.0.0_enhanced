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


# ── Lab Sampling v3: durable sample/custody/result workflow ─────────────────
from datetime import UTC, date, datetime  # noqa: E402
from typing import Literal  # noqa: E402

from core.engines.soil_lab_workflow import SoilWorkflowError, validate_soil_transition  # noqa: E402
from core.irrigation_water_analysis import WaterSample, analyze_water_sample  # noqa: E402
from core.lab_sampling import (  # noqa: E402
    SoilLabResult,
    analyze_soil_lab_result,
    lab_decision_context,
)
from fastapi import HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from api import lab_store  # noqa: E402
from api.main import tenant_connection  # noqa: E402
from api.soil_evidence_bridge import publish_soil_lab_evidence  # noqa: E402

_COMPAT_STATUS = {
    "planned": "requested",
    "collected": "sampled",
    "submitted": "in_lab",
    "analyzed": "result_received",
    "approved": "approved",
}


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
    sampling_plan_id: str | None = None
    barcode: str | None = None
    collected_by: str | None = None


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
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    method_code: str | None = None


class LabTransitionIn(BaseModel):
    target_status: Literal[
        "requested",
        "sampled",
        "in_lab",
        "result_received",
        "approved",
        "published",
        "rejected",
        "cancelled",
    ]
    location: str | None = None
    condition_notes: str | None = None
    seal_id: str | None = None


def _analytes(payload: SoilLabResultIn) -> list[dict]:
    units = {
        "ph": "1",
        "ec_dsm": "dS/m",
        "organic_matter_pct": "%",
        "nitrogen_mg_kg": "mg/kg",
        "phosphorus_mg_kg": "mg/kg",
        "potassium_mg_kg": "mg/kg",
        "cec_cmol_kg": "cmol(+)/kg",
        "calcium_carbonate_pct": "%",
        "texture": None,
    }
    out = []
    for name, unit in units.items():
        value = getattr(payload, name)
        if value is not None:
            out.append(
                {"analyte": name, "value": value, "unit": unit, "method_code": payload.method_code}
            )
    return out


@router.get("/api/v1/lab/samples")
async def list_lab_samples(
    field_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    async with tenant_connection(user) as conn:
        return await lab_store.list_samples(conn, tenant_id=str(user.tenant_id), field_id=field_id)


@router.post("/api/v1/lab/samples")
async def create_lab_sample(
    payload: LabSampleIn,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    data = payload.model_dump(mode="python")
    data["status"] = _COMPAT_STATUS[payload.status]
    async with tenant_connection(user) as conn:
        row = await lab_store.create_sample(
            conn, tenant_id=str(user.tenant_id), created_by=str(user.user_id), payload=data
        )
        await lab_store.add_custody_event(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=row["sample_id"],
            actor_id=str(user.user_id),
            event_type="sample_created",
        )
        return row


@router.post("/api/v1/lab/soil-results")
async def submit_soil_lab_result(
    payload: SoilLabResultIn,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    analytes = _analytes(payload)
    if not analytes:
        raise HTTPException(422, "at least one analyte is required")
    async with tenant_connection(user) as conn:
        sample = await lab_store.get_sample(
            conn, tenant_id=str(user.tenant_id), sample_id=payload.sample_id
        )
        if not sample or sample["kind"] != "soil":
            raise HTTPException(404, "soil sample not found")
        current = sample["status"]
        # Compatibility: receipt of a real result moves sampled/in_lab to result_received through legal steps.
        if current == "sampled":
            await lab_store.set_status(
                conn, tenant_id=str(user.tenant_id), sample_id=payload.sample_id, status="in_lab"
            )
            current = "in_lab"
        validate_soil_transition(current, "result_received", has_result=True)
        await lab_store.insert_soil_results(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            analytes=analytes,
            observed_at=payload.observed_at,
            approved=payload.approved,
            approved_by=str(user.user_id) if payload.approved else None,
        )
        await lab_store.set_status(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            status="approved" if payload.approved else "result_received",
        )
        await lab_store.add_custody_event(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            actor_id=str(user.user_id),
            event_type="lab_result_received",
        )
    return analyze_soil_lab_result(
        SoilLabResult(**payload.model_dump(exclude={"observed_at", "method_code"}))
    )


@router.post("/api/v1/lab/water-results")
async def submit_water_lab_result(
    payload: WaterSample,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    analysis = analyze_water_sample(payload)
    observed = (
        datetime.fromisoformat(payload.sampled_at) if payload.sampled_at else datetime.now(UTC)
    )
    async with tenant_connection(user) as conn:
        sample = await lab_store.get_sample(
            conn, tenant_id=str(user.tenant_id), sample_id=payload.sample_id
        )
        if not sample or sample["kind"] != "water":
            raise HTTPException(404, "water sample not found")
        await lab_store.insert_water_result(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            payload=payload.__dict__,
            analysis=analysis,
            observed_at=observed,
        )
        await lab_store.set_status(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=payload.sample_id,
            status="result_received",
        )
    return analysis


@router.post("/api/v1/lab/samples/{sample_id}/transition")
async def transition_lab_sample(
    sample_id: str,
    payload: LabTransitionIn,
    user: UserSchema = Depends(require_permission(Permission.FIELD_EDIT)),
):
    publish_payload = None
    async with tenant_connection(user) as conn:
        sample = await lab_store.get_sample(
            conn, tenant_id=str(user.tenant_id), sample_id=sample_id
        )
        if not sample:
            raise HTTPException(404, "sample not found")
        soil = (
            await lab_store.latest_soil_analysis(
                conn, tenant_id=str(user.tenant_id), field_id=sample["field_id"]
            )
            if sample["kind"] == "soil"
            else None
        )
        try:
            validate_soil_transition(sample["status"], payload.target_status, has_result=bool(soil))
        except SoilWorkflowError as exc:
            raise HTTPException(exc.http_status, exc.message_ar) from exc
        row = await lab_store.set_status(
            conn, tenant_id=str(user.tenant_id), sample_id=sample_id, status=payload.target_status
        )
        await lab_store.add_custody_event(
            conn,
            tenant_id=str(user.tenant_id),
            sample_id=sample_id,
            actor_id=str(user.user_id),
            event_type=f"status:{payload.target_status}",
            location=payload.location,
            condition_notes=payload.condition_notes,
            seal_id=payload.seal_id,
        )
        if payload.target_status == "published" and sample["kind"] == "soil":
            publish_payload = (sample, soil or {})
    if publish_payload:
        try:
            receipt = await publish_soil_lab_evidence(
                tenant_id=str(user.tenant_id),
                field_id=publish_payload[0]["field_id"],
                sample=publish_payload[0],
                results=publish_payload[1],
            )
        except Exception as exc:
            raise HTTPException(502, f"soil evidence publication failed: {exc}") from exc
        row["soil_evidence_receipt"] = receipt
    return row


@router.get("/api/v1/fields/{field_id}/lab-context")
async def field_lab_context(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    async with tenant_connection(user) as conn:
        latest_soil = await lab_store.latest_soil_analysis(
            conn, tenant_id=str(user.tenant_id), field_id=field_id
        )
        latest_water = await lab_store.latest_water_analysis(
            conn, tenant_id=str(user.tenant_id), field_id=field_id
        )
    if latest_soil:
        latest_soil = analyze_soil_lab_result(SoilLabResult(**latest_soil))
    return lab_decision_context(soil=latest_soil, water=latest_water)
