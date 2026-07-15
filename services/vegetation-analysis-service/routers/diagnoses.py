from __future__ import annotations

from uuid import UUID

import main
from anomaly_store import AnomalyNotFound, InvalidTransition
from decision_bridge import DecisionBridge
from diagnosis_engine import build_diagnosis
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from routers.anomalies import _store

router = APIRouter()
_bridge = DecisionBridge()


class DiagnosisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class ReferralRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    field_state_ref: str
    soil_context_ref: str | None = None
    weather_context_ref: str | None = None


@router.post("/v1/anomalies/{anomaly_ref:path}/diagnoses")
async def generate_diagnosis(
    anomaly_ref: str, request: DiagnosisRequest, token: str = Depends(main.security)
):
    tenant = main._tenant_from_claims(main._verify_claims(token))
    try:
        record = _store.get(anomaly_ref)
        if record["tenant_id"] != tenant:
            raise AnomalyNotFound(anomaly_ref)
        diagnosis = build_diagnosis(anomaly_record=record, tenant_id=UUID(tenant))
        updated = _store.transition(
            anomaly_ref,
            "diagnosis_proposed",
            expected_version=request.expected_version,
            patch={"diagnosis": diagnosis.model_dump(mode="json")},
        )
        return {"diagnosis": diagnosis.model_dump(mode="json"), "anomaly": updated}
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except (InvalidTransition, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/v1/anomalies/{anomaly_ref:path}/decision-referrals")
async def refer_to_decision(
    anomaly_ref: str,
    request: ReferralRequest,
    authorization: str = Header(..., alias="Authorization"),
    token: str = Depends(main.security),
):
    tenant = main._tenant_from_claims(main._verify_claims(token))
    try:
        record = _store.get(anomaly_ref)
        if record["tenant_id"] != tenant:
            raise AnomalyNotFound(anomaly_ref)
        diagnosis_payload = record["payload"].get("diagnosis")
        if not diagnosis_payload:
            raise InvalidTransition("diagnosis_not_proposed")
        from shared.contracts.remote_sensing import DiagnosisHypothesisV1

        diagnosis = DiagnosisHypothesisV1.model_validate(diagnosis_payload)
        result = await _bridge.refer(
            diagnosis=diagnosis,
            authorization=authorization,
            field_state_ref=request.field_state_ref,
            soil_context_ref=request.soil_context_ref,
            weather_context_ref=request.weather_context_ref,
        )
        updated = _store.transition(
            anomaly_ref,
            "decision_referred",
            expected_version=request.expected_version,
            patch={
                "decision_referral": result["referral"],
                "decision_service": result["decision_service"],
            },
        )
        return {**result, "anomaly": updated}
    except AnomalyNotFound as exc:
        raise HTTPException(404, "anomaly not found") from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(424, str(exc)) from exc
