"""Deterministic runtime-worker contracts for Phase 9-12 side effects.

The platform uses API contracts for autonomy, marketplace, MLOps and IoT.  This
module defines the worker-side decision contracts that decide whether a queued
row can cause an external side effect.  The rules are deliberately fail-closed:
missing infrastructure produces a blocked/adapter_required/queued_for_ack state,
never a false "completed" state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import json
import os


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WorkerAction:
    kind: str
    action: str
    status: str
    reason: str | None = None
    physical_effect: bool = False
    external_call_required: bool = False
    required_config: tuple[str, ...] = ()
    receipt: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_config"] = list(self.required_config)
        return data


def build_outbox_action(*, nats_url: str | None, event_type: str | None, attempts: int, max_attempts: int) -> dict[str, Any]:
    if not event_type:
        return WorkerAction(kind="outbox", action="dead_letter", status="dead_letter", reason="missing_event_type").to_dict()
    if attempts >= max_attempts:
        return WorkerAction(kind="outbox", action="dead_letter", status="dead_letter", reason="max_attempts_exceeded").to_dict()
    if not nats_url:
        return WorkerAction(kind="outbox", action="retry", status="failed", reason="nats_url_missing", external_call_required=True, required_config=("NATS_URL",)).to_dict()
    return WorkerAction(kind="outbox", action="publish_nats", status="published", required_config=("NATS_URL",), receipt={"subject": f"sahool.{event_type.replace('_', '.')}"}).to_dict()


def build_plugin_worker_action(*, decision: str, plugin_enabled: bool, executor_url: str | None, has_sandbox_policy: bool = True) -> dict[str, Any]:
    if decision != "allow":
        return WorkerAction(kind="plugin", action="block", status="blocked", reason=f"decision_{decision}").to_dict()
    if not has_sandbox_policy:
        return WorkerAction(kind="plugin", action="block", status="blocked", reason="sandbox_policy_missing").to_dict()
    if not plugin_enabled:
        return WorkerAction(kind="plugin", action="block", status="blocked", reason="plugin_execution_disabled", external_call_required=True, required_config=("PLUGIN_EXECUTION_ENABLED",)).to_dict()
    if not executor_url:
        return WorkerAction(kind="plugin", action="block", status="blocked", reason="plugin_executor_url_missing", external_call_required=True, required_config=("PLUGIN_EXECUTOR_URL",)).to_dict()
    return WorkerAction(kind="plugin", action="enqueue_external_executor", status="queued", external_call_required=True, required_config=("PLUGIN_EXECUTION_ENABLED", "PLUGIN_EXECUTOR_URL"), receipt={"executor_url_configured": True}).to_dict()


def build_model_rollback_action(*, rollback_enabled: bool, serving_backend_url: str | None, to_model_id: str | None) -> dict[str, Any]:
    if not to_model_id:
        return WorkerAction(kind="model", action="block", status="blocked", reason="rollback_target_missing").to_dict()
    if not rollback_enabled:
        return WorkerAction(kind="model", action="block", status="blocked", reason="model_serving_rollback_disabled", external_call_required=True, required_config=("MODEL_SERVING_ROLLBACK_ENABLED",)).to_dict()
    if not serving_backend_url:
        return WorkerAction(kind="model", action="block", status="blocked", reason="model_serving_backend_url_missing", external_call_required=True, required_config=("MODEL_SERVING_BACKEND_URL",)).to_dict()
    return WorkerAction(kind="model", action="request_serving_rollback", status="queued", external_call_required=True, required_config=("MODEL_SERVING_BACKEND_URL",), receipt={"to_model_id": to_model_id}).to_dict()


def build_model_promotion_action(*, decision: str, target_model_id: str | None, artifact_uri: str | None, artifact_hash: str | None, serving_enabled: bool, serving_backend_url: str | None) -> dict[str, Any]:
    if decision != "promote":
        return WorkerAction(kind="model", action="skip", status="blocked", reason=f"decision_{decision}").to_dict()
    if not target_model_id:
        return WorkerAction(kind="model", action="block", status="blocked", reason="target_model_missing").to_dict()
    if not artifact_uri or not artifact_hash:
        return WorkerAction(kind="model", action="block", status="blocked", reason="artifact_metadata_missing").to_dict()
    if not serving_enabled:
        return WorkerAction(kind="model", action="block", status="blocked", reason="model_serving_disabled", external_call_required=True, required_config=("MODEL_SERVING_ENABLED",)).to_dict()
    if not serving_backend_url:
        return WorkerAction(kind="model", action="block", status="blocked", reason="model_serving_backend_url_missing", external_call_required=True, required_config=("MODEL_SERVING_BACKEND_URL",)).to_dict()
    return WorkerAction(kind="model", action="request_serving_promotion", status="queued", external_call_required=True, required_config=("MODEL_SERVING_ENABLED", "MODEL_SERVING_BACKEND_URL"), receipt={"target_model_id": target_model_id}).to_dict()


def build_actuator_worker_action(*, physical_enabled: bool, protocol: str, target_id: str | None, adapter_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if not target_id:
        return WorkerAction(kind="actuator", action="block", status="blocked", reason="target_id_missing").to_dict()
    if not physical_enabled:
        return WorkerAction(kind="actuator", action="block", status="blocked", reason="physical_actuation_disabled", physical_effect=False, external_call_required=False, required_config=("PHYSICAL_ACTUATION_ENABLED",)).to_dict()
    adapter_config = adapter_config or {}
    protocol_config = adapter_config.get(protocol) or adapter_config.get(protocol.lower()) or {}
    if not bool(protocol_config.get("enabled", False)):
        return WorkerAction(kind="actuator", action="adapter_required", status="adapter_required", reason=f"adapter_disabled:{protocol}", physical_effect=False, external_call_required=True, required_config=("ACTUATOR_ADAPTER_CONFIG_JSON",)).to_dict()
    if str(protocol_config.get("mode", "simulation")) != "real":
        return WorkerAction(kind="actuator", action="adapter_required", status="adapter_required", reason=f"adapter_not_real:{protocol}", physical_effect=False, external_call_required=True, required_config=("ACTUATOR_ADAPTER_CONFIG_JSON",)).to_dict()
    if not protocol_config.get("endpoint") and protocol not in {"mqtt", "lorawan"}:
        return WorkerAction(kind="actuator", action="adapter_required", status="adapter_required", reason=f"adapter_endpoint_missing:{protocol}", physical_effect=False, external_call_required=True, required_config=("ACTUATOR_ADAPTER_CONFIG_JSON",)).to_dict()
    return WorkerAction(kind="actuator", action="request_adapter_dispatch", status="waiting_ack", reason=None, physical_effect=False, external_call_required=True, required_config=("PHYSICAL_ACTUATION_ENABLED", "ACTUATOR_ADAPTER_CONFIG_JSON"), receipt={"protocol": protocol, "target_id": target_id}).to_dict()


def parse_json_env(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}
