"""Phase 9 IoT execution adapter runtime.

This module provides a production-safe bridge between autonomous execution plans
and physical-equipment protocols.  It is intentionally deterministic and
fail-closed so tests can validate dispatch behavior without real pumps, pivots,
MQTT brokers, Modbus devices, or LoRaWAN gateways.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(value: Any, prefix: str) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:12]}"


class DispatchMode(str, Enum):
    DISABLED = "disabled"
    SIMULATION = "simulation"
    DRY_RUN = "dry_run"
    REAL = "real"


class Protocol(str, Enum):
    MANUAL_WORK_ORDER = "manual_work_order"
    MQTT = "mqtt"
    MODBUS_TCP = "modbus_tcp"
    LORAWAN = "lorawan"
    PIVOT_API = "pivot_api"
    PUMP_API = "pump_api"


class DispatchStatus(str, Enum):
    BLOCKED = "blocked"
    SIMULATED = "simulated"
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class AdapterCapability:
    protocol: str
    enabled: bool
    mode: str
    supports_ack: bool
    supports_telemetry: bool
    max_commands_per_batch: int = 50


@dataclass(frozen=True)
class DispatchEnvelope:
    envelope_id: str
    execution_id: str
    tenant_id: str | None
    field_id: str
    command_id: str
    idempotency_key: str
    protocol: str
    target_id: str
    command: dict[str, Any]
    mode: str
    physical_enabled: bool
    verification_required: bool
    created_at: str


@dataclass(frozen=True)
class DispatchResult:
    envelope_id: str
    command_id: str
    status: str
    protocol: str
    target_id: str
    physical_effect: bool
    reason: str | None
    adapter_receipt: dict[str, Any]
    verification_contract: dict[str, Any]
    dispatched_at: str


DEFAULT_CAPABILITIES: dict[str, AdapterCapability] = {
    Protocol.MANUAL_WORK_ORDER.value: AdapterCapability(
        Protocol.MANUAL_WORK_ORDER.value, True, DispatchMode.SIMULATION.value, False, False
    ),
    Protocol.MQTT.value: AdapterCapability(
        Protocol.MQTT.value, True, DispatchMode.SIMULATION.value, True, True
    ),
    Protocol.MODBUS_TCP.value: AdapterCapability(
        Protocol.MODBUS_TCP.value, False, DispatchMode.DISABLED.value, True, True
    ),
    Protocol.LORAWAN.value: AdapterCapability(
        Protocol.LORAWAN.value, False, DispatchMode.DISABLED.value, True, True
    ),
    Protocol.PIVOT_API.value: AdapterCapability(
        Protocol.PIVOT_API.value, False, DispatchMode.DISABLED.value, True, True
    ),
    Protocol.PUMP_API.value: AdapterCapability(
        Protocol.PUMP_API.value, False, DispatchMode.DISABLED.value, True, True
    ),
}


def normalize_protocol(value: str | None) -> str:
    raw = (value or Protocol.MANUAL_WORK_ORDER.value).strip().lower()
    aliases = {
        "manual": Protocol.MANUAL_WORK_ORDER.value,
        "work_order": Protocol.MANUAL_WORK_ORDER.value,
        "mqtt5": Protocol.MQTT.value,
        "modbus": Protocol.MODBUS_TCP.value,
        "lorawan_v1": Protocol.LORAWAN.value,
        "pivot": Protocol.PIVOT_API.value,
        "pump": Protocol.PUMP_API.value,
    }
    return aliases.get(raw, raw)


def merge_capabilities(config: dict[str, Any] | None = None) -> dict[str, AdapterCapability]:
    """Merge operator-supplied adapter config over fail-safe defaults."""
    merged = dict(DEFAULT_CAPABILITIES)
    for protocol, spec in (config or {}).items():
        key = normalize_protocol(protocol)
        current = merged.get(
            key, AdapterCapability(key, False, DispatchMode.DISABLED.value, False, False)
        )
        merged[key] = AdapterCapability(
            protocol=key,
            enabled=bool(spec.get("enabled", current.enabled)),
            mode=str(spec.get("mode", current.mode)),
            supports_ack=bool(spec.get("supports_ack", current.supports_ack)),
            supports_telemetry=bool(spec.get("supports_telemetry", current.supports_telemetry)),
            max_commands_per_batch=int(
                spec.get("max_commands_per_batch", current.max_commands_per_batch)
            ),
        )
    return merged


def build_dispatch_envelopes(
    execution_plan: dict[str, Any],
    *,
    adapter_config: dict[str, Any] | None = None,
    physical_actuation_enabled: bool = False,
) -> dict[str, Any]:
    """Validate an execution plan and produce protocol-specific envelopes.

    No envelope is physically executable unless both the adapter is in ``real``
    mode and ``physical_actuation_enabled`` is explicitly true.  This prevents a
    config-only MQTT broker from becoming physical authorization.
    """
    status = str(execution_plan.get("status") or "")
    commands = execution_plan.get("commands") or []
    capabilities = merge_capabilities(adapter_config)
    diagnostics: list[str] = []
    envelopes: list[dict[str, Any]] = []

    if status != "dispatch_ready":
        return {
            "ready": False,
            "reason": "execution_plan_not_dispatch_ready",
            "diagnostics": [status],
            "envelopes": [],
        }
    if not commands:
        return {"ready": False, "reason": "no_commands", "diagnostics": [], "envelopes": []}

    for cmd in commands:
        protocol = normalize_protocol(cmd.get("protocol"))
        capability = capabilities.get(protocol)
        if capability is None:
            diagnostics.append(f"unsupported_protocol:{protocol}")
            continue
        if not capability.enabled:
            diagnostics.append(f"adapter_disabled:{protocol}")
            continue
        if len(envelopes) >= capability.max_commands_per_batch:
            diagnostics.append(f"batch_limit_exceeded:{protocol}")
            continue
        if not cmd.get("command_id") or not cmd.get("target_id") or not cmd.get("idempotency_key"):
            diagnostics.append("invalid_command_identity")
            continue
        mode = (
            DispatchMode(capability.mode).value
            if capability.mode in DispatchMode._value2member_map_
            else DispatchMode.DISABLED.value
        )
        physical_effect = bool(
            physical_actuation_enabled
            and mode == DispatchMode.REAL.value
            and not cmd.get("dry_run", False)
        )
        envelope = DispatchEnvelope(
            envelope_id=_stable_id(
                {
                    "exec": execution_plan.get("execution_id"),
                    "cmd": cmd.get("command_id"),
                    "protocol": protocol,
                },
                "env",
            ),
            execution_id=str(execution_plan.get("execution_id")),
            tenant_id=execution_plan.get("tenant_id"),
            field_id=str(execution_plan.get("field_id")),
            command_id=str(cmd.get("command_id")),
            idempotency_key=str(cmd.get("idempotency_key")),
            protocol=protocol,
            target_id=str(cmd.get("target_id")),
            command=dict(cmd.get("command") or {}),
            mode=mode,
            physical_enabled=physical_effect,
            verification_required=True,
            created_at=_now(),
        )
        envelopes.append(asdict(envelope))
    return {
        "ready": bool(envelopes),
        "reason": None if envelopes else "no_dispatchable_commands",
        "diagnostics": diagnostics,
        "envelopes": envelopes,
    }


def dispatch_envelopes(envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    """Dispatch envelopes through deterministic simulation/queue semantics.

    Real device I/O is intentionally adapter-owned and not performed here.  In
    production, a consumer can take these envelopes from ``iot_command_dispatch``
    or NATS and call MQTT/Modbus/LoRaWAN clients.  This function returns the
    contract that the service must persist/audit before any physical bridge.
    """
    results: list[dict[str, Any]] = []
    for env in envelopes:
        mode = str(env.get("mode") or DispatchMode.DISABLED.value)
        physical = bool(env.get("physical_enabled"))
        if mode == DispatchMode.DISABLED.value:
            status = DispatchStatus.BLOCKED.value
            reason = "adapter_disabled"
        elif mode in {DispatchMode.SIMULATION.value, DispatchMode.DRY_RUN.value}:
            status = DispatchStatus.SIMULATED.value
            reason = "simulation_no_physical_effect"
            physical = False
        elif mode == DispatchMode.REAL.value and physical:
            status = DispatchStatus.QUEUED.value
            reason = "queued_for_physical_adapter"
        else:
            status = DispatchStatus.BLOCKED.value
            reason = "real_mode_requires_explicit_physical_enable_and_non_dry_run"
            physical = False
        receipt = {
            "receipt_id": _stable_id({"env": env.get("envelope_id"), "status": status}, "rcpt"),
            "idempotency_key": env.get("idempotency_key"),
            "queued_topic": f"iot.commands.{env.get('protocol')}.{env.get('target_id')}",
            "simulated": status == DispatchStatus.SIMULATED.value,
        }
        verification_contract = {
            "requires_ack": env.get("protocol") != Protocol.MANUAL_WORK_ORDER.value,
            "requires_telemetry": True,
            "expected_command_id": env.get("command_id"),
            "accepted_signals": [
                "acknowledged_command_ids",
                "flow_rate",
                "pressure",
                "power_current",
                "soil_moisture_delta",
                "fault",
            ],
            "fail_closed": True,
        }
        results.append(
            asdict(
                DispatchResult(
                    envelope_id=str(env.get("envelope_id")),
                    command_id=str(env.get("command_id")),
                    status=status,
                    protocol=str(env.get("protocol")),
                    target_id=str(env.get("target_id")),
                    physical_effect=physical,
                    reason=reason,
                    adapter_receipt=receipt,
                    verification_contract=verification_contract,
                    dispatched_at=_now(),
                )
            )
        )
    return {
        "dispatch_batch_id": _stable_id(
            {"envelopes": [e.get("envelope_id") for e in envelopes]}, "iotbatch"
        ),
        "results": results,
        "physical_effect_count": sum(1 for r in results if r.get("physical_effect")),
        "fail_closed": True,
    }


def summarize_telemetry_frames(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize equipment telemetry for command verification."""
    numeric_keys = ["flow_rate", "pressure", "power_current", "soil_moisture_delta"]
    summary: dict[str, Any] = {
        "frame_count": len(frames),
        "faults": [],
        "acknowledged_command_ids": [],
    }
    acked: set[str] = set()
    for frame in frames:
        acked.update(str(v) for v in (frame.get("acknowledged_command_ids") or []))
        if frame.get("fault"):
            summary["faults"].append(str(frame.get("fault")))
    summary["acknowledged_command_ids"] = sorted(acked)
    for key in numeric_keys:
        values = [
            float(f[key])
            for f in frames
            if isinstance(f.get(key), (int, float)) and math.isfinite(float(f[key]))
        ]
        summary[key] = {
            "count": len(values),
            "mean": sum(values) / len(values) if values else None,
            "latest": values[-1] if values else None,
        }
    summary["telemetry_ok"] = (
        bool(acked or any(summary[k]["count"] for k in numeric_keys)) and not summary["faults"]
    )
    return summary


def project_thing_model(
    *,
    device_model_id: str,
    capabilities: dict[str, AdapterCapability] | None = None,
) -> dict[str, Any]:
    """Project SAHOOL's existing IoT contract into property/function/event vocabulary.

    This is a compatibility projection only; it does not create another device
    registry, broker, rule engine, or execution authority.
    """
    if not device_model_id:
        raise ValueError("device_model_id is required")
    # فحصُ `is None` لا صدقيّةَ القيمة: التوقيع يقول `dict | None`، فالقاموس الفارغ
    # تمثيلٌ صريح لـ«لا قدرات» لا طلبٌ للافتراضيّ. و`or` تبتلعه فتُرجِع قدراتٍ لم
    # يطلبها المُستدعي. (أمسكها مراجع Copilot على #876.)
    caps = DEFAULT_CAPABILITIES if capabilities is None else capabilities
    functions = []
    for protocol, cap in sorted(caps.items()):
        functions.append(
            {
                "id": f"dispatch:{protocol}",
                "protocol": protocol,
                "enabled": cap.enabled,
                "mode": cap.mode,
                "requires_ack": cap.supports_ack,
                "max_commands_per_batch": cap.max_commands_per_batch,
            }
        )
    return {
        "schema": "sahool.thing-model-projection.v1",
        "device_model_id": device_model_id,
        "properties": [
            {"id": "flow_rate", "type": "number", "read_only": True},
            {"id": "pressure", "type": "number", "read_only": True},
            {"id": "power_current", "type": "number", "read_only": True},
            {"id": "soil_moisture_delta", "type": "number", "read_only": True},
        ],
        "functions": functions,
        "events": [
            {"id": "ack", "fields": ["acknowledged_command_ids"]},
            {"id": "fault", "fields": ["fault"]},
            {
                "id": "telemetry",
                "fields": ["flow_rate", "pressure", "power_current", "soil_moisture_delta"],
            },
        ],
        "authority": "projection_only",
        "physical_enable_required": True,
    }
