"""Field-bound approved-sample 4R planning and the existing manual what-if contract."""

from __future__ import annotations

from core.agri_tools.tools.fertilizer import compute as compute_fertilizer
from fastapi import APIRouter, Depends, HTTPException

from api import lab_store
from api.main import (
    Permission,
    Soil4RRequest,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.nutrient_4r import SoilContext, approved_sample_4r_plan, full_4r_plan

router = APIRouter()


@router.post("/api/v1/nutrients/4r-plan")
async def nutrient_4r_plan(
    req: Soil4RRequest | None = None,
    user: UserSchema = Depends(require_permission(Permission.ACTIVITY_PLAN)),
    field_id: str | None = None,
):
    """خطة تسميد 4R للتربة الكلسيّة (تحجب ما يحتاج تحليلاً)."""
    if field_id is not None:
        if req is not None:
            raise HTTPException(422, "field_plan_requires_stored_inputs")
        try:
            async with tenant_connection(user) as conn:
                await _assert_field_in_tenant(conn, field_id)
                rows = await lab_store.latest_soil_4r_rows(
                    conn, tenant_id=str(user.tenant_id), field_id=field_id
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise _db_unavailable("قراءة تحليل التربة", exc) from exc
        return approved_sample_4r_plan(field_id, rows)
    if req is None:
        raise HTTPException(422, "field_id_or_manual_inputs_required")
    soil = SoilContext(
        caco3_pct=req.caco3_pct,
        ph=req.ph,
        p_ppm=req.p_ppm,
        fe_ppm=req.fe_ppm,
        zn_ppm=req.zn_ppm,
        om_pct=req.om_pct,
    )
    result = {"plan": full_4r_plan(soil, req.nutrients)}
    if req.fertilizer_scenario is not None:
        inputs = req.fertilizer_scenario.model_dump()
        try:
            estimate = compute_fertilizer(inputs)
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, "invalid_fertilizer_scenario") from exc
        result["fertilizer_scenario"] = {
            "status": "estimated",
            "inputs": inputs,
            "estimate": estimate,
            "source_ref_verified": False,
            "lab_supported": False,
            "execution_authorized": False,
            "local_compliance_evaluated": False,
        }
    return result
