"""Phase 9 Autonomous Farm OS API contracts.

These endpoints are dependency-light and can be mounted in the platform router.
They intentionally keep persistence optional; production wiring should persist
returned plans/outbox/features to the v102 tables and publish actuator commands
through NATS/MQTT/Modbus adapters.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.phase_runtime_store import (
    _uuid,
    persist_iot_dispatch_batch,
    persist_model_version,
    persist_phase9_feature_batch,
    persist_phase9_plan,
    persist_phase9_verification,
    persist_runtime_event,
)
from api.service_token_auth import _require_service_token
from shared.autonomous_farm_os_phase9 import (
    assign_experiment_variant,
    event_source_execution_plan,
    plan_closed_loop_execution,
    register_model_version,
    replay_autonomy_events,
    run_command_verification_loop,
    run_phase9_autonomy_cycle,
    verify_execution_effect,
)
from shared.iot_execution_runtime import (
    build_dispatch_envelopes,
    dispatch_envelopes,
    summarize_telemetry_frames,
)

router = APIRouter(
    prefix="/v1/phase9/autonomy",
    tags=["phase9-autonomous-farm-os"],
    dependencies=[Depends(_require_service_token)],
)


class ExecutionPlanRequest(BaseModel):
    recommendation: dict[str, Any]
    mode: str = Field(default="human_approval")
    policy: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    actuator_registry: dict[str, Any] = Field(default_factory=dict)


class VerificationRequest(BaseModel):
    execution_plan: dict[str, Any]
    telemetry: dict[str, Any]
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None


class CycleRequest(BaseModel):
    canonical_runtime: dict[str, Any]
    mode: str = Field(default="human_approval")
    policy: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    actuator_registry: dict[str, Any] = Field(default_factory=dict)


class ModelVersionRequest(BaseModel):
    name: str
    task: str
    version: str
    metrics: dict[str, float] = Field(default_factory=dict)
    training_feature_sets: list[str] = Field(default_factory=list)
    promote_thresholds: dict[str, float] = Field(default_factory=dict)


class ExperimentAssignmentRequest(BaseModel):
    entity_id: str
    experiment_key: str
    variants: list[str]


class ReplayRequest(BaseModel):
    events: list[dict[str, Any]]


class VerificationLoopRequest(BaseModel):
    execution_plan: dict[str, Any]
    telemetry_frames: list[dict[str, Any]] = Field(default_factory=list)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None


class IotDispatchRequest(BaseModel):
    execution_plan: dict[str, Any]
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    physical_actuation_enabled: bool = Field(default=False)


class IotTelemetryRequest(BaseModel):
    execution_plan: dict[str, Any]
    telemetry_frames: list[dict[str, Any]] = Field(default_factory=list)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None


@router.post("/plan")
async def create_execution_plan(req: ExecutionPlanRequest, request: Request) -> dict[str, Any]:
    plan = plan_closed_loop_execution(
        req.recommendation,
        mode=req.mode,
        policy=req.policy,
        telemetry=req.telemetry,
        actuator_registry=req.actuator_registry,
    )
    plan["runtime_persistence"] = await persist_phase9_plan(request, plan)
    plan["runtime_event"] = await persist_runtime_event(
        request,
        tenant=_uuid(plan.get("tenant_id")),
        field=_uuid(plan.get("field_id")),
        aggregate_type="autonomous_execution_plan",
        aggregate_id=str(plan.get("execution_id")),
        event_type="phase9.execution_plan.created",
        payload=plan,
    )
    return plan


@router.post("/verify")
async def verify_execution(req: VerificationRequest, request: Request) -> dict[str, Any]:
    result = verify_execution_effect(
        req.execution_plan,
        telemetry=req.telemetry,
        before_state=req.before_state,
        after_state=req.after_state,
    )
    result["runtime_persistence"] = await persist_phase9_verification(
        request, result, req.execution_plan, req.telemetry
    )
    return result


@router.post("/cycle")
async def run_cycle(req: CycleRequest, request: Request) -> dict[str, Any]:
    cycle = run_phase9_autonomy_cycle(
        canonical_runtime=req.canonical_runtime,
        mode=req.mode,
        policy=req.policy,
        telemetry=req.telemetry,
        actuator_registry=req.actuator_registry,
    )
    plan = cycle.get("execution_plan") or cycle.get("plan") or {}
    if isinstance(plan, dict):
        cycle["runtime_persistence"] = await persist_phase9_plan(request, plan)
        cycle["feature_runtime_persistence"] = await persist_phase9_feature_batch(
            request, plan, cycle.get("feature_store_batch") or []
        )
        cycle["runtime_event"] = await persist_runtime_event(
            request,
            tenant=_uuid(plan.get("tenant_id")),
            field=_uuid(plan.get("field_id")),
            aggregate_type="autonomy_cycle",
            aggregate_id=str(cycle.get("cycle_id")),
            event_type="phase9.autonomy_cycle.completed",
            payload=cycle,
        )
    return cycle


@router.post("/models/register")
async def register_model(req: ModelVersionRequest, request: Request) -> dict[str, Any]:
    model = register_model_version(
        name=req.name,
        task=req.task,
        version=req.version,
        metrics=req.metrics,
        training_feature_sets=req.training_feature_sets,
        promote_thresholds=req.promote_thresholds,
    )
    model["runtime_persistence"] = await persist_model_version(request, model)
    return model


@router.post("/experiments/assign")
def assign_variant(req: ExperimentAssignmentRequest) -> dict[str, Any]:
    return assign_experiment_variant(
        entity_id=req.entity_id, experiment_key=req.experiment_key, variants=req.variants
    )


@router.post("/events/from-plan")
def events_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    events = event_source_execution_plan(plan)
    return {"events": events, "replayed_state": replay_autonomy_events(events)}


@router.post("/events/replay")
def replay_events(req: ReplayRequest) -> dict[str, Any]:
    return replay_autonomy_events(req.events)


@router.post("/verify-loop")
def command_verification_loop(req: VerificationLoopRequest) -> dict[str, Any]:
    return run_command_verification_loop(
        req.execution_plan,
        telemetry_frames=req.telemetry_frames,
        before_state=req.before_state,
        after_state=req.after_state,
    )


@router.post("/iot/dispatch/preview")
def preview_iot_dispatch(req: IotDispatchRequest) -> dict[str, Any]:
    """Prepare protocol envelopes without queueing commands.

    This is the safe operator preview used before enabling any equipment bridge.
    """
    return build_dispatch_envelopes(
        req.execution_plan,
        adapter_config=req.adapter_config,
        physical_actuation_enabled=req.physical_actuation_enabled,
    )


@router.post("/iot/dispatch/simulate")
async def simulate_iot_dispatch(req: IotDispatchRequest, request: Request) -> dict[str, Any]:
    """Dispatch through the fail-safe IoT adapter contract and persist/audit it.

    Real protocol clients are intentionally behind workers/adapters.  This API
    creates the dispatch batch contract and never produces physical movement
    unless an adapter is explicitly real and physical_actuation_enabled=true.
    """
    prepared = build_dispatch_envelopes(
        req.execution_plan,
        adapter_config=req.adapter_config,
        physical_actuation_enabled=req.physical_actuation_enabled,
    )
    batch = dispatch_envelopes(prepared.get("envelopes") or [])
    batch["prepared"] = prepared
    batch["runtime_persistence"] = await persist_iot_dispatch_batch(
        request, req.execution_plan, batch
    )
    return batch


@router.post("/iot/telemetry/verify")
def verify_iot_telemetry(req: IotTelemetryRequest) -> dict[str, Any]:
    summary = summarize_telemetry_frames(req.telemetry_frames)
    loop = run_command_verification_loop(
        req.execution_plan,
        telemetry_frames=req.telemetry_frames,
        before_state=req.before_state,
        after_state=req.after_state,
    )
    return {"telemetry_summary": summary, "closed_loop_verification": loop}
