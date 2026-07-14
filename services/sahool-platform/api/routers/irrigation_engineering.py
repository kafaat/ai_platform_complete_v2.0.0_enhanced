"""IRR-X1 vendor-neutral irrigation engineering endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from api.irrigation_commissioning_runtime import (
    CommissioningCertificate,
    CommissioningCertificateInput,
    ExecutionAuthorization,
    authorize_execution,
    build_commissioning_certificate,
)
from api.irrigation_engineering_workspace import (
    EngineeringResult,
    InteractiveIrrigationCalculationRequest,
    InteractiveIrrigationCalculationResult,
    IrrigationSystemSpecification,
    ReservoirBoosterNetworkRequest,
    ReservoirBoosterNetworkResult,
    WaterDemandInput,
    calculate_interactive_irrigation_engineering,
    calculate_irrigation_engineering,
    calculate_reservoir_booster_network,
)
from api.irrigation_manual_execution import (
    ManualAsAppliedResult,
    ManualExecutionConfirmation,
    ManualExecutionState,
    ManualRecommendationInput,
    derive_manual_as_applied,
    transition_manual_execution,
)
from api.irrigation_manual_ledger_bridge import (
    ManualVerificationInput,
    ManualVerificationResult,
    build_manual_water_ledger_event,
    verify_manual_as_applied,
)
from api.main import (
    Permission,
    UserSchema,
    require_permission,
    tenant_connection,
)

router = APIRouter(prefix="/api/v1/irrigation/engineering", tags=["irrigation-engineering"])


class EngineeringCalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: IrrigationSystemSpecification
    water_demand: WaterDemandInput


@router.post("/calculate", response_model=EngineeringResult)
async def calculate_engineering(
    req: EngineeringCalculationRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
) -> EngineeringResult:
    # Tenant identity is server-authoritative. Reject cross-tenant payloads before calculation.
    if str(req.specification.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=403, detail="tenant mismatch")
    return calculate_irrigation_engineering(req.specification, req.water_demand)


@router.post("/interactive-calculate", response_model=InteractiveIrrigationCalculationResult)
async def calculate_interactive_engineering(
    req: InteractiveIrrigationCalculationRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
) -> InteractiveIrrigationCalculationResult:
    if str(req.specification.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=403, detail="tenant mismatch")
    try:
        return calculate_interactive_irrigation_engineering(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/network-calculate", response_model=ReservoirBoosterNetworkResult)
async def calculate_network_engineering(
    req: ReservoirBoosterNetworkRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
) -> ReservoirBoosterNetworkResult:
    if str(req.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=403, detail="tenant mismatch")
    try:
        return calculate_reservoir_booster_network(req)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── IRR-X1.1 Digital Commissioning Runtime ───────────────────────────────────
class ExecutionAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_mode: str
    certificate: CommissioningCertificate | None = None
    decision_approved: bool
    telemetry_fresh: bool = False
    blocking_alarm: bool = False
    execution_window_valid: bool
    adapter_capable: bool = False


@router.post("/commissioning/certificates", response_model=CommissioningCertificate)
async def issue_commissioning_certificate(
    req: CommissioningCertificateInput,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> CommissioningCertificate:
    if str(req.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=403, detail="tenant mismatch")
    certificate = build_commissioning_certificate(req)
    try:
        async with tenant_connection(user) as conn:
            await conn.execute(
                """INSERT INTO irrigation_commissioning_certificates_v2 (
                       certificate_id, tenant_id, field_id, season_id, system_id,
                       machine_id, pump_id, controller_id, specification_version,
                       specification_digest, capability_graph_digest, commissioning_version,
                       status, tested_at, valid_until, flow_curve_digest,
                       pressure_curve_digest, power_curve_digest, safety_interlocks,
                       execution_limits, permitted_execution_modes, blocking_failures,
                       warnings, snapshot, certificate_digest, issued_by, reviewed_by,
                       supersedes_certificate_id
                   ) VALUES (
                       $1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                       $13, $14, $15, $16, $17, $18, $19::jsonb, $20::jsonb,
                       $21::jsonb, $22::jsonb, $23::jsonb, $24::jsonb, $25,
                       $26::uuid, $27::uuid, $28
                   )""",
                certificate.certificate_id,
                str(user.tenant_id),
                certificate.field_id,
                certificate.season_id,
                certificate.system_id,
                certificate.machine_id,
                certificate.pump_id,
                certificate.controller_id,
                req.specification_version,
                certificate.specification_digest,
                certificate.capability_graph_digest,
                certificate.commissioning_version,
                certificate.status.value,
                certificate.tested_at,
                certificate.valid_until,
                certificate.flow_curve_digest,
                certificate.pressure_curve_digest,
                certificate.power_curve_digest,
                json.dumps(certificate.safety_interlocks),
                json.dumps(certificate.execution_limits),
                json.dumps(certificate.permitted_execution_modes),
                json.dumps(certificate.blocking_failures),
                json.dumps(certificate.warnings),
                certificate.model_dump_json(),
                certificate.certificate_digest,
                certificate.issued_by,
                certificate.reviewed_by,
                certificate.supersedes_certificate_id,
            )
    except Exception as exc:
        # Preserve conflict semantics for duplicate version/digest; do not claim persistence.
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409, detail="commissioning certificate conflict"
            ) from exc
        raise
    return certificate


@router.get("/commissioning/systems/{system_id}/current", response_model=CommissioningCertificate)
async def get_current_commissioning_certificate(
    system_id: str,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
) -> CommissioningCertificate:
    async with tenant_connection(user) as conn:
        row = await conn.fetchrow(
            """SELECT snapshot
               FROM irrigation_commissioning_certificates_v2
               WHERE tenant_id = $1::uuid AND system_id = $2
                 AND status IN ('pass','degraded') AND valid_until > NOW()
               ORDER BY commissioning_version DESC, created_at DESC
               LIMIT 1""",
            str(user.tenant_id),
            system_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="NO_VALID_COMMISSIONING_CERTIFICATE")
    snapshot = row["snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    return CommissioningCertificate.model_validate(snapshot)


@router.post("/commissioning/authorize", response_model=ExecutionAuthorization)
async def evaluate_execution_authorization(
    req: ExecutionAuthorizationRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> ExecutionAuthorization:
    if req.certificate and str(req.certificate.tenant_id) != str(user.tenant_id):
        raise HTTPException(status_code=403, detail="tenant mismatch")
    return authorize_execution(
        requested_mode=req.requested_mode,
        certificate=req.certificate,
        now=datetime.now(UTC),
        decision_approved=req.decision_approved,
        telemetry_fresh=req.telemetry_fresh,
        blocking_alarm=req.blocking_alarm,
        execution_window_valid=req.execution_window_valid,
        adapter_capable=req.adapter_capable,
    )


# ── IRR-X1.2 Manual Execution Lifecycle ─────────────────────────────────────
class ManualExecutionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_plan_id: str
    mode: str
    idempotency_key: str


class ManualExecutionTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_state: ManualExecutionState


class ManualExecutionConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: ManualExecutionConfirmation


@router.get("/manual-executions")
async def list_manual_executions(
    field_id: str,
    season_id: str | None = None,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_VIEW)),
) -> list[dict]:
    """Return tenant-scoped manual executions for operator workflow display.

    The endpoint is read-only and never synthesizes a recommendation. RLS plus the
    explicit tenant predicate keep the response scoped even if the query changes.
    """
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            """SELECT execution_id, field_id, season_id, system_id, recommendation_id,
                      decision_id, execution_plan_id, plan_digest, water_truth_digest, execution_mode, state, target_depth_mm, target_volume_m3,
                      nominal_flow_m3_h, valid_from, valid_until, approved_at,
                      started_at, stopped_at, confirmed_at, verified_at,
                      reconciled_at, completion_ratio, ledger_eligible, as_applied,
                      as_applied_digest, verification, created_at, updated_at
                 FROM irrigation_manual_executions
                WHERE tenant_id=$1::uuid AND field_id=$2
                  AND ($3::text IS NULL OR season_id=$3)
                ORDER BY created_at DESC
                LIMIT 100""",
            str(user.tenant_id),
            field_id,
            season_id,
        )
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        for key in ("as_applied", "verification"):
            if isinstance(item.get(key), str):
                item[key] = json.loads(item[key])
        result.append(item)
    return result


@router.post("/manual-executions")
async def create_manual_execution(
    req: ManualExecutionCreateRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> dict:
    if req.mode not in {"manual_estimated", "manual_measured"}:
        raise HTTPException(status_code=409, detail="MANUAL_EXECUTION_MODE_REQUIRED")
    async with tenant_connection(user) as conn:
        async with conn.transaction():
            source = await conn.fetchrow(
                """SELECT * FROM irrigation_manual_execution_sources
                    WHERE tenant_id=$1::uuid AND execution_plan_id=$2 FOR UPDATE""",
                str(user.tenant_id),
                req.execution_plan_id,
            )
            if source is None:
                raise HTTPException(
                    status_code=404, detail="AUTHORITATIVE_MANUAL_IRRIGATION_PLAN_NOT_FOUND"
                )
            now = datetime.now(UTC)
            if source["valid_until"] <= now:
                raise HTTPException(status_code=409, detail="EXECUTION_PLAN_EXPIRED")
            if req.mode == "manual_estimated" and source["nominal_flow_m3_h"] is None:
                raise HTTPException(
                    status_code=409, detail="NOMINAL_FLOW_REQUIRED_FOR_ESTIMATED_MODE"
                )
            execution_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{user.tenant_id}:{req.execution_plan_id}:{req.idempotency_key}",
                )
            )
            row = await conn.fetchrow(
                """INSERT INTO irrigation_manual_executions (
                       execution_id, tenant_id, field_id, season_id, system_id,
                       recommendation_id, recommendation_digest, decision_id, execution_plan_id,
                       plan_digest, water_truth_digest, execution_mode, state,
                       target_depth_mm, target_volume_m3, nominal_flow_m3_h,
                       valid_from, valid_until, idempotency_key, created_by
                   ) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'recommended',
                             $13,$14,$15,$16,$17,$18,$19)
                   ON CONFLICT (tenant_id,idempotency_key) DO UPDATE
                     SET updated_at=irrigation_manual_executions.updated_at
                   RETURNING *, (xmax <> 0) AS idempotent_replay""",
                execution_id,
                str(user.tenant_id),
                source["field_id"],
                source["season_id"],
                source["system_id"],
                source["execution_plan_id"],
                source["plan_digest"],
                source["decision_id"],
                source["execution_plan_id"],
                source["plan_digest"],
                source["water_truth_digest"],
                req.mode,
                source["target_depth_mm"],
                source["target_volume_m3"],
                source["nominal_flow_m3_h"],
                source["valid_from"],
                source["valid_until"],
                req.idempotency_key,
                str(user.user_id),
            )
            if (
                row["execution_plan_id"] != req.execution_plan_id
                or row["plan_digest"] != source["plan_digest"]
            ):
                raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_SOURCE_MISMATCH")
    return {
        "execution_id": str(row["execution_id"]),
        "state": row["state"],
        "execution_plan_id": row["execution_plan_id"],
        "decision_id": row["decision_id"],
        "plan_digest": row["plan_digest"],
        "idempotent": bool(row["idempotent_replay"]),
    }


@router.post("/manual-executions/{execution_id}/transition")
async def transition_manual_execution_endpoint(
    execution_id: str,
    req: ManualExecutionTransitionRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> dict:
    async with tenant_connection(user) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM irrigation_manual_executions WHERE execution_id=$1::uuid FOR UPDATE",
                execution_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="MANUAL_EXECUTION_NOT_FOUND")
            current = ManualExecutionState(row["state"])
            if req.target_state in {ManualExecutionState.VERIFIED, ManualExecutionState.RECONCILED}:
                raise HTTPException(
                    status_code=409, detail="USE_GOVERNED_VERIFY_OR_RECONCILE_ENDPOINT"
                )
            try:
                target = transition_manual_execution(current, req.target_state)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if target in {ManualExecutionState.APPROVED, ManualExecutionState.STARTED} and row[
                "valid_until"
            ] <= datetime.now(UTC):
                raise HTTPException(status_code=409, detail="EXECUTION_WINDOW_EXPIRED")
            column = {
                ManualExecutionState.APPROVED: "approved_at",
                ManualExecutionState.STARTED: "started_at",
                ManualExecutionState.STOPPED: "stopped_at",
                ManualExecutionState.VERIFIED: "verified_at",
                ManualExecutionState.RECONCILED: "reconciled_at",
            }.get(target)
            if column:
                await conn.execute(
                    f"UPDATE irrigation_manual_executions SET state=$2, {column}=now(), updated_at=now() WHERE execution_id=$1::uuid",
                    execution_id,
                    target.value,
                )
            else:
                await conn.execute(
                    "UPDATE irrigation_manual_executions SET state=$2, updated_at=now() WHERE execution_id=$1::uuid",
                    execution_id,
                    target.value,
                )
            event_body = {
                "execution_id": execution_id,
                "from": current.value,
                "to": target.value,
                "actor": str(user.user_id),
            }
            event_digest = (
                __import__("hashlib")
                .sha256(json.dumps(event_body, sort_keys=True).encode())
                .hexdigest()
            )
            await conn.execute(
                """INSERT INTO irrigation_manual_execution_events
                   (tenant_id,execution_id,from_state,to_state,actor_id,payload,event_digest)
                   VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6::jsonb,$7) ON CONFLICT DO NOTHING""",
                str(user.tenant_id),
                execution_id,
                current.value,
                target.value,
                str(user.user_id),
                json.dumps(event_body),
                event_digest,
            )
    return {"execution_id": execution_id, "state": target.value}


@router.post("/manual-executions/{execution_id}/confirm", response_model=ManualAsAppliedResult)
async def confirm_manual_execution(
    execution_id: str,
    req: ManualExecutionConfirmRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> ManualAsAppliedResult:
    async with tenant_connection(user) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM irrigation_manual_executions WHERE execution_id=$1::uuid FOR UPDATE",
                execution_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="MANUAL_EXECUTION_NOT_FOUND")
            if row["state"] != ManualExecutionState.STOPPED.value:
                raise HTTPException(
                    status_code=409, detail="EXECUTION_MUST_BE_STOPPED_BEFORE_CONFIRMATION"
                )
            rec = ManualRecommendationInput(
                execution_id=str(row["execution_id"]),
                tenant_id=str(row["tenant_id"]),
                field_id=row["field_id"],
                season_id=row["season_id"],
                system_id=row["system_id"],
                recommendation_id=row["recommendation_id"],
                recommendation_digest=row["recommendation_digest"],
                mode=row["execution_mode"],
                target_depth_mm=float(row["target_depth_mm"]),
                target_volume_m3=float(row["target_volume_m3"]),
                nominal_flow_m3_h=float(row["nominal_flow_m3_h"])
                if row["nominal_flow_m3_h"] is not None
                else None,
                valid_from=row["valid_from"],
                valid_until=row["valid_until"],
                created_by=str(row["created_by"]),
            )
            result = derive_manual_as_applied(rec, req.confirmation)
            await conn.execute(
                """UPDATE irrigation_manual_executions SET state='confirmed', confirmed_at=now(),
                   started_at=$2, stopped_at=$3, completion_ratio=$4, confirmation=$5::jsonb,
                   as_applied=$6::jsonb, as_applied_digest=$7, ledger_eligible=$8, updated_at=now()
                   WHERE execution_id=$1::uuid""",
                execution_id,
                req.confirmation.started_at,
                req.confirmation.stopped_at,
                req.confirmation.completion_ratio,
                req.confirmation.model_dump_json(),
                result.model_dump_json(),
                result.as_applied_digest,
                result.ledger_eligible,
            )
    return result


# ── IRR-X1.3 Verified As-Applied + Water Ledger Bridge ───────────────────────
class ManualExecutionVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification: ManualVerificationInput


@router.post(
    "/manual-executions/{execution_id}/verify",
    response_model=ManualVerificationResult,
)
async def verify_manual_execution(
    execution_id: str,
    req: ManualExecutionVerifyRequest,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> ManualVerificationResult:
    async with tenant_connection(user) as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM irrigation_manual_executions WHERE execution_id=$1::uuid FOR UPDATE",
                execution_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="MANUAL_EXECUTION_NOT_FOUND")
            if row["state"] != ManualExecutionState.CONFIRMED.value:
                raise HTTPException(
                    status_code=409, detail="EXECUTION_MUST_BE_CONFIRMED_BEFORE_VERIFICATION"
                )
            as_applied = row["as_applied"] or {}
            confirmation = row["confirmation"] or {}
            if isinstance(as_applied, str):
                as_applied = json.loads(as_applied)
            if isinstance(confirmation, str):
                confirmation = json.loads(confirmation)
            # Reviewer identity is server-authoritative; never trust a client-supplied actor id.
            verification_request = req.verification.model_copy(
                update={"reviewer_id": str(user.user_id)}
            )
            result = verify_manual_as_applied(
                execution_id=execution_id,
                stored_as_applied=as_applied,
                stored_as_applied_digest=str(row["as_applied_digest"]),
                execution_mode=str(row["execution_mode"]),
                confirmation=confirmation,
                request=verification_request,
            )
            if result.status != "verified":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "MANUAL_AS_APPLIED_VERIFICATION_FAILED",
                        "blocking_reasons": result.blocking_reasons,
                    },
                )
            await conn.execute(
                """UPDATE irrigation_manual_executions
                   SET state='verified', verified_at=$2, verified_by=$3,
                       verification=$4::jsonb, verification_digest=$5, updated_at=now()
                   WHERE execution_id=$1::uuid""",
                execution_id,
                result.verified_at,
                result.reviewer_id,
                json.dumps(
                    {
                        **verification_request.model_dump(mode="json"),
                        **result.model_dump(mode="json"),
                    }
                ),
                result.verification_digest,
            )
            event_body = {
                "execution_id": execution_id,
                "from": "confirmed",
                "to": "verified",
                "actor": str(user.user_id),
                "verification_digest": result.verification_digest,
            }
            event_digest = (
                __import__("hashlib")
                .sha256(json.dumps(event_body, sort_keys=True).encode())
                .hexdigest()
            )
            await conn.execute(
                """INSERT INTO irrigation_manual_execution_events
                   (tenant_id,execution_id,from_state,to_state,actor_id,payload,event_digest)
                   VALUES ($1::uuid,$2::uuid,'confirmed','verified',$3,$4::jsonb,$5)
                   ON CONFLICT DO NOTHING""",
                str(user.tenant_id),
                execution_id,
                str(user.user_id),
                json.dumps(event_body),
                event_digest,
            )
    return result


@router.post("/manual-executions/{execution_id}/reconcile")
async def reconcile_manual_execution_to_water_ledger(
    execution_id: str,
    user: UserSchema = Depends(require_permission(Permission.IRRIGATION_MANAGE)),
) -> dict:
    async with tenant_connection(user) as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))", f"manual-irrigation:{execution_id}"
            )
            existing = await conn.fetchrow(
                "SELECT payload FROM irrigation_manual_ledger_reconciliations WHERE execution_id=$1::uuid",
                execution_id,
            )
            if existing is not None:
                payload = existing["payload"] or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return {**payload, "idempotent_replay": True}
            row = await conn.fetchrow(
                "SELECT * FROM irrigation_manual_executions WHERE execution_id=$1::uuid FOR UPDATE",
                execution_id,
            )
            if row is None:
                raise HTTPException(status_code=404, detail="MANUAL_EXECUTION_NOT_FOUND")
            execution = dict(row)
            for key in ("as_applied", "confirmation", "verification"):
                if isinstance(execution.get(key), str):
                    execution[key] = json.loads(execution[key])
            try:
                event = build_manual_water_ledger_event(
                    execution=execution,
                    verification_digest=str(row["verification_digest"] or ""),
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            ledger_date = event.observed_at.date()
            before = await conn.fetchval(
                "SELECT depletion_mm FROM water_ledger WHERE field_id=$1 ORDER BY ledger_date DESC LIMIT 1",
                event.field_id,
            )
            depletion_after = (
                None if before is None else max(0.0, float(before) - event.applied_depth_mm)
            )
            await conn.execute(
                """INSERT INTO water_ledger (
                       tenant_id, field_id, ledger_date, irrigation_mm, depletion_mm, decision, created_by
                   ) VALUES ($1::uuid,$2,$3,$4,$5,'verified_manual_as_applied',$6)
                   ON CONFLICT (field_id, ledger_date) DO UPDATE SET
                       irrigation_mm=COALESCE(water_ledger.irrigation_mm,0)+EXCLUDED.irrigation_mm,
                       depletion_mm=EXCLUDED.depletion_mm,
                       decision=EXCLUDED.decision,
                       created_by=EXCLUDED.created_by,
                       updated_at=now()""",
                str(user.tenant_id),
                event.field_id,
                ledger_date,
                event.applied_depth_mm,
                depletion_after,
                f"manual_as_applied:{event.ledger_event_digest}",
            )
            result = {
                "status": "reconciled",
                "execution_id": execution_id,
                "field_id": event.field_id,
                "season_id": event.season_id,
                "ledger_date": ledger_date.isoformat(),
                "applied_depth_mm": event.applied_depth_mm,
                "applied_volume_m3": event.applied_volume_m3,
                "depletion_before_mm": None if before is None else float(before),
                "depletion_after_mm": depletion_after,
                "as_applied_digest": event.as_applied_digest,
                "verification_digest": event.verification_digest,
                "ledger_event_digest": event.ledger_event_digest,
                "idempotent_replay": False,
            }
            await conn.execute(
                """INSERT INTO irrigation_manual_ledger_reconciliations (
                       tenant_id,execution_id,field_id,season_id,ledger_date,
                       applied_depth_mm,applied_volume_m3,depletion_before_mm,depletion_after_mm,
                       as_applied_digest,verification_digest,ledger_event_digest,payload,reconciled_by
                   ) VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14)""",
                str(user.tenant_id),
                execution_id,
                event.field_id,
                event.season_id,
                ledger_date,
                event.applied_depth_mm,
                event.applied_volume_m3,
                before,
                depletion_after,
                event.as_applied_digest,
                event.verification_digest,
                event.ledger_event_digest,
                json.dumps(result),
                str(user.user_id),
            )
            await conn.execute(
                """UPDATE irrigation_manual_executions
                   SET state='reconciled', reconciled_at=now(), ledger_event_digest=$2, updated_at=now()
                   WHERE execution_id=$1::uuid""",
                execution_id,
                event.ledger_event_digest,
            )
            event_body = {
                "execution_id": execution_id,
                "from": "verified",
                "to": "reconciled",
                "actor": str(user.user_id),
                "ledger_event_digest": event.ledger_event_digest,
            }
            event_digest = (
                __import__("hashlib")
                .sha256(json.dumps(event_body, sort_keys=True).encode())
                .hexdigest()
            )
            await conn.execute(
                """INSERT INTO irrigation_manual_execution_events
                   (tenant_id,execution_id,from_state,to_state,actor_id,payload,event_digest)
                   VALUES ($1::uuid,$2::uuid,'verified','reconciled',$3,$4::jsonb,$5)
                   ON CONFLICT DO NOTHING""",
                str(user.tenant_id),
                execution_id,
                str(user.user_id),
                json.dumps(event_body),
                event_digest,
            )
            return result
