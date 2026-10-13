"""api/routers/outcome.py — نقطة قياس نتائج القرار (#383)

تكشف الطبقة النقيّة measure_outcome: تقارن المُخطَّط (من القرار/الخطّة) بالمرصود
الميدانيّ ⇒ التزام الخطة والإجهاد والإنتاج وفق البيانات المقدّمة.
المقارنة الاختيارية بين تنفيذين مقيسين وصفية؛ لا تثبت وفراً سببياً أو نقدياً.

محفوظ النمط: POST، `Depends(get_current_user)` (يمرّ حارس المصادقة)، نموذج self-contained.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator

from api.decision_lineage import ensure_decision_id, lineage_stage
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    get_current_user,
    require_permission,
    tenant_connection,
)
from api.outcome_measurement import compare_irrigation_executions, measure_outcome

router = APIRouter()


class OutcomePlanned(BaseModel):
    recommended_irrigation_mm: float | None = None
    predicted_stress_days: int | None = None
    expected_yield_t_ha: float | None = None
    season_budget_mm: float | None = None


class OutcomeActual(BaseModel):
    actual_irrigation_mm: float | None = None
    observed_stress_days: int | None = None
    actual_yield_t_ha: float | None = None
    actual_water_used_mm: float | None = None


class IrrigationComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_execution_id: UUID
    candidate_execution_id: UUID

    @model_validator(mode="after")
    def distinct_executions(self):
        if self.baseline_execution_id == self.candidate_execution_id:
            raise ValueError("DISTINCT_EXECUTIONS_REQUIRED")
        return self


class OutcomeRequest(BaseModel):
    field_id: str | None = None
    decision_id: str | None = None  # نَسَب: معرّف القرار الذي تقيس نتيجته
    planned: OutcomePlanned
    actual: OutcomeActual
    irrigation_comparison: IrrigationComparisonRequest | None = None

    @model_validator(mode="after")
    def comparison_field_required(self):
        if self.irrigation_comparison is not None and not (self.field_id or "").strip():
            raise ValueError("COMPARISON_FIELD_REQUIRED")
        return self


@router.post("/api/v1/outcome/measure")
async def measure_decision_outcome(
    req: OutcomeRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يقيس نتيجة قرار سابق مقابل القياس الميدانيّ — نقيّ في جوهره.

    صدق: يُقيِّم فقط المقاييس المتوفّر طرفاها (مُخطَّط + مرصود)؛ الناقص needs_data.
    """
    out = measure_outcome(req.planned.model_dump(), req.actual.model_dump())
    did = ensure_decision_id(req.decision_id)
    out["field_id"] = req.field_id
    out["decision_id"] = did
    out["lineage"] = lineage_stage(did, "outcome", field_id=req.field_id)
    if req.irrigation_comparison is not None:
        # Preserve legacy authentication while requiring irrigation read permission
        # for the optional tenant-authoritative database comparison.
        require_permission(Permission.IRRIGATION_VIEW)(user)
        comparison = req.irrigation_comparison
        try:
            async with tenant_connection(user) as conn:
                rows = await conn.fetch(
                    """SELECT execution_id, field_id, season_id, system_id,
                              execution_mode, state, target_depth_mm, target_volume_m3,
                              ledger_eligible, as_applied, as_applied_digest,
                              verification, verification_digest
                         FROM irrigation_manual_executions
                        WHERE tenant_id=$1::uuid AND field_id=$2
                          AND execution_id=ANY($3::uuid[])""",
                    str(user.tenant_id),
                    req.field_id,
                    [comparison.baseline_execution_id, comparison.candidate_execution_id],
                )
        except HTTPException:
            raise
        except Exception as exc:
            raise _db_unavailable("قراءة أدلة مقارنة الري", exc) from exc
        by_id = {str(row["execution_id"]): dict(row) for row in rows}
        baseline = by_id.get(str(comparison.baseline_execution_id))
        candidate = by_id.get(str(comparison.candidate_execution_id))
        if baseline is None or candidate is None:
            # Identical response for absent or inaccessible evidence.
            raise HTTPException(status_code=404, detail="IRRIGATION_COMPARISON_EVIDENCE_NOT_FOUND")
        out["irrigation_comparison"] = compare_irrigation_executions(baseline, candidate)
    return out
