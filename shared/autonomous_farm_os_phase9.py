"""Phase 9 autonomous farm OS runtime contracts.

This module advances SAHOOL from recommendation lifecycle to safe closed-loop
execution.  It is deliberately dependency-light: production adapters can bind
MQTT/Modbus/ISOBUS, PostGIS, NATS, model registries and feature stores behind
these deterministic contracts without changing the public shapes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from statistics import mean
from typing import Any
import hashlib
import json
import math


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


class AutonomyMode(str, Enum):
    SHADOW = "shadow"
    HUMAN_APPROVAL = "human_approval"
    SUPERVISED_AUTONOMY = "supervised_autonomy"
    FULL_AUTONOMY = "full_autonomy"


class ExecutionStatus(str, Enum):
    PLANNED = "planned"
    SAFETY_BLOCKED = "safety_blocked"
    DISPATCH_READY = "dispatch_ready"
    DISPATCHED = "dispatched"
    TELEMETRY_CONFIRMED = "telemetry_confirmed"
    EFFECT_VERIFIED = "effect_verified"
    LEARNING_CAPTURED = "learning_captured"
    FAILED = "failed"


@dataclass(frozen=True)
class SafetyGateResult:
    permitted: bool
    mode: str
    reasons: list[str]
    required_approval: bool
    max_authorized_effect: dict[str, Any]


@dataclass(frozen=True)
class ActuatorCommand:
    command_id: str
    recommendation_id: str
    field_id: str
    tenant_id: str | None
    actuator_type: str
    protocol: str
    target_id: str
    command: dict[str, Any]
    idempotency_key: str
    expires_at: str | None
    dry_run: bool


@dataclass(frozen=True)
class ExecutionPlan:
    execution_id: str
    recommendation_id: str
    source_state_id: str
    field_id: str
    tenant_id: str | None
    mode: str
    status: str
    safety_gate: dict[str, Any]
    commands: list[dict[str, Any]]
    verification_plan: dict[str, Any]
    created_at: str
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class FeatureRecord:
    feature_id: str
    entity_type: str
    entity_id: str
    feature_set: str
    source_state_id: str | None
    event_time: str
    features: dict[str, Any]
    labels: dict[str, Any]
    quality: dict[str, Any]


@dataclass(frozen=True)
class ModelVersion:
    model_id: str
    name: str
    task: str
    version: str
    status: str
    metrics: dict[str, float]
    training_feature_sets: list[str]
    created_at: str


def evaluate_autonomy_safety_gate(
    recommendation: dict[str, Any],
    *,
    mode: AutonomyMode | str = AutonomyMode.HUMAN_APPROVAL,
    policy: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fail-closed safety decision for autonomous execution."""
    mode_value = AutonomyMode(mode).value
    policy = policy or {}
    telemetry = telemetry or {}
    reasons: list[str] = []

    if recommendation.get("status") not in {"approved", "verified"}:
        reasons.append("recommendation_not_approved")
    if recommendation.get("evidence", {}).get("dispatch_block_reason"):
        reasons.append("upstream_guardrail_blocked")
    if telemetry.get("offline") is True:
        reasons.append("actuator_telemetry_offline")
    if telemetry.get("manual_override") is True:
        reasons.append("manual_override_active")
    if float(policy.get("max_risk_score", 0.35)) < float(recommendation.get("decision", {}).get("risk_score", 0.0) or 0.0):
        reasons.append("risk_score_exceeds_policy")
    if mode_value == AutonomyMode.SHADOW.value:
        reasons.append("shadow_mode_no_dispatch")
    if mode_value == AutonomyMode.FULL_AUTONOMY.value and not policy.get("full_autonomy_enabled", False):
        reasons.append("full_autonomy_not_enabled_for_tenant")

    required_approval = mode_value in {AutonomyMode.HUMAN_APPROVAL.value, AutonomyMode.SUPERVISED_AUTONOMY.value}
    if required_approval and not recommendation.get("decision", {}).get("operator_approved", False):
        reasons.append("operator_approval_required")

    permitted = len(reasons) == 0
    gate = SafetyGateResult(
        permitted=permitted,
        mode=mode_value,
        reasons=sorted(set(reasons)),
        required_approval=required_approval,
        max_authorized_effect={
            "water_mm": policy.get("max_water_mm", 25),
            "fertilizer_kg_ha": policy.get("max_fertilizer_kg_ha", 80),
            "spray_area_ha": policy.get("max_spray_area_ha", 50),
        },
    )
    return asdict(gate)


def build_actuator_commands(
    recommendation: dict[str, Any],
    *,
    actuator_registry: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Map approved recommendations to idempotent actuator commands."""
    decision = recommendation.get("decision", {})
    action_type = recommendation.get("action_type") or decision.get("action_type") or "advisory"
    actuator_registry = actuator_registry or {}
    field_id = str(recommendation.get("field_id"))
    target = actuator_registry.get(field_id, {})
    protocol = target.get("protocol", "manual_work_order")
    target_id = target.get("target_id", f"field:{field_id}")

    payload: dict[str, Any]
    actuator_type = "work_order"
    if action_type in {"irrigation", "irrigate", "water"}:
        actuator_type = "pivot_or_valve"
        payload = {"operation": "apply_irrigation", "water_mm": float(decision.get("water_mm", decision.get("amount_mm", 8.0) or 8.0))}
    elif action_type in {"fertigation", "fertilization", "nitrogen"}:
        actuator_type = "fertigation_controller"
        payload = {"operation": "apply_fertilizer", "rate_kg_ha": float(decision.get("rate_kg_ha", 25.0) or 25.0)}
    elif action_type in {"spraying", "spray"}:
        actuator_type = "sprayer_task"
        payload = {"operation": "create_spray_task", "product": decision.get("product", "unspecified"), "area_ha": decision.get("area_ha")}
    else:
        payload = {"operation": "create_manual_task", "action_type": action_type, "summary": decision.get("summary")}

    material = {"rec": recommendation.get("recommendation_id"), "target": target_id, "payload": payload}
    command = ActuatorCommand(
        command_id=_stable_id(material, "cmd"),
        recommendation_id=str(recommendation.get("recommendation_id")),
        field_id=field_id,
        tenant_id=recommendation.get("tenant_id"),
        actuator_type=actuator_type,
        protocol=protocol,
        target_id=target_id,
        command=payload,
        idempotency_key=_stable_id(material, "idem"),
        expires_at=None,
        dry_run=dry_run,
    )
    return [asdict(command)]


def plan_closed_loop_execution(
    recommendation: dict[str, Any],
    *,
    mode: AutonomyMode | str = AutonomyMode.HUMAN_APPROVAL,
    policy: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
    actuator_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a safe observe→decide→dispatch→verify→learn execution plan."""
    gate = evaluate_autonomy_safety_gate(recommendation, mode=mode, policy=policy, telemetry=telemetry)
    commands = [] if not gate["permitted"] else build_actuator_commands(recommendation, actuator_registry=actuator_registry)
    status = ExecutionStatus.DISPATCH_READY.value if gate["permitted"] else ExecutionStatus.SAFETY_BLOCKED.value
    plan = ExecutionPlan(
        execution_id=_stable_id({"rec": recommendation.get("recommendation_id"), "gate": gate, "commands": commands}, "exec"),
        recommendation_id=str(recommendation.get("recommendation_id")),
        source_state_id=str(recommendation.get("source_state_id")),
        field_id=str(recommendation.get("field_id")),
        tenant_id=recommendation.get("tenant_id"),
        mode=AutonomyMode(mode).value,
        status=status,
        safety_gate=gate,
        commands=commands,
        verification_plan={
            "telemetry_required": True,
            "remote_sensing_followup_days": [3, 7, 14],
            "success_metrics": ["operation_completed", "target_applied", "field_response"],
            "fail_closed": True,
        },
        created_at=_now(),
        events=[{"status": status, "occurred_at": _now(), "reasons": gate["reasons"]}],
    )
    return asdict(plan)


def verify_execution_effect(
    execution_plan: dict[str, Any],
    *,
    telemetry: dict[str, Any],
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify command completion and agronomic response."""
    commands = execution_plan.get("commands", [])
    command_ids = {c.get("command_id") for c in commands}
    acknowledgements = set(telemetry.get("acknowledged_command_ids", []))
    completed = bool(command_ids) and command_ids.issubset(acknowledgements)
    applied = telemetry.get("applied", {})

    before_truths = (before_state or {}).get("state", before_state or {}).get("operational_truths", {}) if before_state else {}
    after_truths = (after_state or {}).get("state", after_state or {}).get("operational_truths", {}) if after_state else {}
    ndvi_delta = None
    try:
        ndvi_delta = float(after_truths.get("ndvi", 0)) - float(before_truths.get("ndvi", 0))
    except Exception:
        ndvi_delta = None

    success = completed and telemetry.get("fault") is None
    return {
        "verification_id": _stable_id({"exec": execution_plan.get("execution_id"), "telemetry": telemetry}, "ver"),
        "execution_id": execution_plan.get("execution_id"),
        "recommendation_id": execution_plan.get("recommendation_id"),
        "status": ExecutionStatus.EFFECT_VERIFIED.value if success else ExecutionStatus.FAILED.value,
        "operation_completed": completed,
        "target_applied": applied,
        "field_response": {"ndvi_delta": ndvi_delta, "after_status": after_truths.get("effective_status")},
        "fault": telemetry.get("fault"),
        "verified_at": _now(),
    }


def flatten_feature_record(
    *,
    entity_type: str,
    entity_id: str,
    feature_set: str,
    source_state_id: str | None,
    features: dict[str, Any],
    labels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    numeric_values = [float(v) for v in features.values() if isinstance(v, (int, float)) and math.isfinite(float(v))]
    quality = {
        "feature_count": len(features),
        "numeric_feature_count": len(numeric_values),
        "missing_count": sum(1 for v in features.values() if v is None),
        "mean_numeric_value": mean(numeric_values) if numeric_values else None,
    }
    rec = FeatureRecord(
        feature_id=_stable_id({"entity": entity_id, "set": feature_set, "features": features, "labels": labels or {}}, "feat"),
        entity_type=entity_type,
        entity_id=entity_id,
        feature_set=feature_set,
        source_state_id=source_state_id,
        event_time=_now(),
        features=dict(features),
        labels=labels or {},
        quality=quality,
    )
    return asdict(rec)


def build_feature_store_batch(
    *,
    canonical_runtime: dict[str, Any],
    execution_verification: dict[str, Any] | None = None,
    outcome_feedback: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create online/offline feature store candidate records."""
    twin = canonical_runtime.get("digital_twin_view", {})
    phase6 = canonical_runtime.get("phase6_runtime_inputs", {})
    state = canonical_runtime.get("canonical_state", {})
    features = dict(phase6.get("features", {}))
    features.update({
        "confidence": state.get("state", {}).get("confidence"),
        "limitation_count": len(twin.get("limitations", []) or []),
    })
    labels: dict[str, Any] = {}
    if execution_verification:
        labels["operation_completed"] = execution_verification.get("operation_completed")
        labels["effect_status"] = execution_verification.get("status")
    if outcome_feedback:
        labels.update(outcome_feedback.get("outcome_metrics", {}))
    return [flatten_feature_record(
        entity_type="field",
        entity_id=str(twin.get("field_id") or state.get("field_id")),
        feature_set="canonical_field_runtime_v1",
        source_state_id=state.get("state_id"),
        features=features,
        labels=labels,
    )]


def register_model_version(
    *,
    name: str,
    task: str,
    version: str,
    metrics: dict[str, float],
    training_feature_sets: list[str],
    promote_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    promote_thresholds = promote_thresholds or {}
    status = "candidate"
    if all(float(metrics.get(k, -10**9)) >= float(v) for k, v in promote_thresholds.items()):
        status = "champion"
    model = ModelVersion(
        model_id=_stable_id({"name": name, "task": task, "version": version, "metrics": metrics}, "mdl"),
        name=name,
        task=task,
        version=version,
        status=status,
        metrics=metrics,
        training_feature_sets=training_feature_sets,
        created_at=_now(),
    )
    return asdict(model)


def assign_experiment_variant(*, entity_id: str, experiment_key: str, variants: list[str]) -> dict[str, Any]:
    if not variants:
        raise ValueError("variants must not be empty")
    bucket = int(hashlib.sha256(f"{experiment_key}:{entity_id}".encode()).hexdigest()[:8], 16)
    variant = variants[bucket % len(variants)]
    return {
        "assignment_id": _stable_id({"entity": entity_id, "experiment": experiment_key, "variant": variant}, "exp"),
        "entity_id": entity_id,
        "experiment_key": experiment_key,
        "variant": variant,
        "bucket": bucket % 10000,
        "assigned_at": _now(),
    }



# --- Phase 9 production hardening: event sourcing, replay and closed-loop verification ---

PHASE9_EVENT_TRANSITIONS = {
    "DecisionIssued": ExecutionStatus.PLANNED.value,
    "DecisionBlocked": ExecutionStatus.SAFETY_BLOCKED.value,
    "DispatchReady": ExecutionStatus.DISPATCH_READY.value,
    "CommandDispatched": ExecutionStatus.DISPATCHED.value,
    "TelemetryAcknowledged": ExecutionStatus.TELEMETRY_CONFIRMED.value,
    "ExecutionVerified": ExecutionStatus.EFFECT_VERIFIED.value,
    "ExecutionFailed": ExecutionStatus.FAILED.value,
    "ManualOverride": ExecutionStatus.SAFETY_BLOCKED.value,
}


def build_autonomy_event(
    *,
    event_type: str,
    aggregate_id: str,
    tenant_id: str | None = None,
    field_id: str | None = None,
    payload: dict[str, Any] | None = None,
    sequence: int | None = None,
) -> dict[str, Any]:
    """Create a deterministic append-only event for autonomy replay/audit."""
    body = payload or {}
    event = {
        "event_id": _stable_id({"type": event_type, "aggregate": aggregate_id, "seq": sequence, "payload": body}, "evt"),
        "event_type": event_type,
        "aggregate_type": "autonomous_execution",
        "aggregate_id": aggregate_id,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "sequence": sequence,
        "payload": body,
        "occurred_at": _now(),
        "schema_version": "phase9.event.v2",
    }
    return event


def event_source_execution_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Emit the minimal event stream needed to reconstruct an execution plan."""
    aggregate_id = str(plan.get("execution_id"))
    tenant_id = plan.get("tenant_id")
    field_id = plan.get("field_id")
    events = [
        build_autonomy_event(
            event_type="DecisionIssued",
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
            field_id=field_id,
            payload={
                "recommendation_id": plan.get("recommendation_id"),
                "source_state_id": plan.get("source_state_id"),
                "mode": plan.get("mode"),
                "status": plan.get("status"),
                "safety_gate": plan.get("safety_gate"),
            },
            sequence=1,
        )
    ]
    status = plan.get("status")
    events.append(build_autonomy_event(
        event_type="DispatchReady" if status == ExecutionStatus.DISPATCH_READY.value else "DecisionBlocked",
        aggregate_id=aggregate_id, tenant_id=tenant_id, field_id=field_id,
        payload={"status": status, "reasons": (plan.get("safety_gate") or {}).get("reasons", [])}, sequence=2,
    ))
    for offset, cmd in enumerate(plan.get("commands") or [], start=3):
        events.append(build_autonomy_event(
            event_type="CommandDispatched",
            aggregate_id=aggregate_id, tenant_id=tenant_id, field_id=field_id,
            payload={"command_id": cmd.get("command_id"), "protocol": cmd.get("protocol"), "target_id": cmd.get("target_id"), "dry_run": cmd.get("dry_run")},
            sequence=offset,
        ))
    return events


def replay_autonomy_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild current execution state from ordered Phase 9 events."""
    ordered = sorted(events, key=lambda e: (e.get("sequence") is None, e.get("sequence") or 0, e.get("occurred_at") or ""))
    state: dict[str, Any] = {"status": ExecutionStatus.PLANNED.value, "commands": [], "history": []}
    for event in ordered:
        etype = event.get("event_type")
        payload = event.get("payload") or {}
        state["aggregate_id"] = event.get("aggregate_id", state.get("aggregate_id"))
        state["tenant_id"] = event.get("tenant_id", state.get("tenant_id"))
        state["field_id"] = event.get("field_id", state.get("field_id"))
        if "recommendation_id" in payload:
            state["recommendation_id"] = payload.get("recommendation_id")
        if etype in PHASE9_EVENT_TRANSITIONS:
            state["status"] = PHASE9_EVENT_TRANSITIONS[etype]
        if etype == "CommandDispatched":
            state.setdefault("commands", []).append(payload)
        if etype == "ExecutionVerified":
            state["verification"] = payload
        if etype == "ManualOverride":
            state["manual_override"] = payload
        state.setdefault("history", []).append({"event_type": etype, "sequence": event.get("sequence"), "occurred_at": event.get("occurred_at")})
    state["replay_id"] = _stable_id({"events": [e.get("event_id") for e in ordered], "status": state.get("status")}, "replay")
    return state


def run_command_verification_loop(
    execution_plan: dict[str, Any],
    *,
    telemetry_frames: list[dict[str, Any]],
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Closed-loop command verification using ack, sensor evidence and outcome state."""
    aggregate_id = str(execution_plan.get("execution_id"))
    command_ids = [c.get("command_id") for c in execution_plan.get("commands", [])]
    acked: set[str] = set()
    faults: list[str] = []
    sensor_evidence: dict[str, Any] = {"flow_rate": [], "pressure": [], "power_current": [], "soil_moisture_delta": []}
    for frame in telemetry_frames:
        acked.update(frame.get("acknowledged_command_ids", []) or [])
        if frame.get("fault"):
            faults.append(str(frame.get("fault")))
        for key in sensor_evidence:
            value = frame.get(key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                sensor_evidence[key].append(float(value))
    ack_complete = bool(command_ids) and set(command_ids).issubset(acked)
    sensor_ok = any(sensor_evidence[k] for k in ("flow_rate", "pressure", "power_current")) or not command_ids
    verification = verify_execution_effect(
        execution_plan,
        telemetry={"acknowledged_command_ids": list(acked), "applied": {"sensor_ok": sensor_ok}, "fault": faults[0] if faults else None},
        before_state=before_state,
        after_state=after_state,
    )
    status = ExecutionStatus.EFFECT_VERIFIED.value if ack_complete and sensor_ok and not faults else ExecutionStatus.FAILED.value
    verification.update({
        "status": status,
        "ack_complete": ack_complete,
        "sensor_ok": sensor_ok,
        "faults": faults,
        "sensor_summary": {k: (mean(v) if v else None) for k, v in sensor_evidence.items()},
        "closed_loop": True,
    })
    events = [build_autonomy_event(event_type="TelemetryAcknowledged", aggregate_id=aggregate_id, tenant_id=execution_plan.get("tenant_id"), field_id=execution_plan.get("field_id"), payload={"acked": sorted(acked)}, sequence=90)]
    events.append(build_autonomy_event(event_type="ExecutionVerified" if status == ExecutionStatus.EFFECT_VERIFIED.value else "ExecutionFailed", aggregate_id=aggregate_id, tenant_id=execution_plan.get("tenant_id"), field_id=execution_plan.get("field_id"), payload=verification, sequence=100))
    return {"verification": verification, "events": events, "replayed_state": replay_autonomy_events(event_source_execution_plan(execution_plan) + events)}


def run_phase9_autonomy_cycle(
    *,
    canonical_runtime: dict[str, Any],
    mode: AutonomyMode | str = AutonomyMode.HUMAN_APPROVAL,
    policy: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
    actuator_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recommendation = canonical_runtime.get("recommendation_lifecycle", {})
    plan = plan_closed_loop_execution(recommendation, mode=mode, policy=policy, telemetry=telemetry, actuator_registry=actuator_registry)
    verification = None
    if plan.get("status") == ExecutionStatus.DISPATCH_READY.value:
        ack_ids = [c["command_id"] for c in plan.get("commands", [])]
        verification = verify_execution_effect(plan, telemetry={"acknowledged_command_ids": ack_ids, "applied": {"simulated": True}, **(telemetry or {})})
    features = build_feature_store_batch(canonical_runtime=canonical_runtime, execution_verification=verification)
    event_stream = event_source_execution_plan(plan)
    if verification:
        event_stream.append(build_autonomy_event(
            event_type="ExecutionVerified" if verification.get("status") == ExecutionStatus.EFFECT_VERIFIED.value else "ExecutionFailed",
            aggregate_id=str(plan.get("execution_id")),
            tenant_id=plan.get("tenant_id"),
            field_id=plan.get("field_id"),
            payload=verification,
            sequence=100,
        ))
    return {
        "phase": "phase9_autonomous_farm_os",
        "cycle_id": _stable_id({"runtime": canonical_runtime.get("runtime_id"), "plan": plan.get("execution_id")}, "auto"),
        "execution_plan": plan,
        "verification": verification,
        "event_stream": event_stream,
        "replayed_state": replay_autonomy_events(event_stream),
        "feature_store_batch": features,
        "learning_ready": bool(features and verification),
        "created_at": _now(),
    }
