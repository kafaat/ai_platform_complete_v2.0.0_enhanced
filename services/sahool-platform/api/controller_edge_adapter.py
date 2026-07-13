"""M2.9 controller and edge adapter framework.

Normalizes vendor/protocol telemetry into a governed, replay-resistant controller
capability snapshot. The module is read-only by default. It can prepare a command
request envelope, but never transmits or dispatches a field command.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "controller_edge_adapter.v1"
PRODUCT_VERSION = "controller-edge-adapter/1.0.0"
SUPPORTED_PROTOCOLS = {
    "mqtt",
    "modbus_tcp",
    "modbus_rtu",
    "http",
    "opcua",
    "vendor_api",
    "local_plc",
}
SAFE_MODES = {"read_only", "dry_run", "human_approved_control", "guarded_automation"}
REQUIRED_READ_CAPABILITIES = ("read_status", "read_position")


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class ControllerHandshake:
    tenant_id: str
    controller_id: str
    machine_id: str
    protocol: str
    provider: str
    model: str | None
    firmware_version: str | None
    integration_mode: str
    capabilities: dict[str, bool]
    certification_status: str
    identity_fingerprint: str
    observed_at: str
    handshake_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedControllerTelemetry:
    tenant_id: str
    controller_id: str
    machine_id: str
    sequence_number: int
    observed_at: str
    received_at: str
    connection_status: str
    operating_state: str
    position_percent: float | None
    speed_percent: float | None
    pressure_bar: float | None
    flow_lps: float | None
    alarm_codes: list[str]
    source_message_id: str
    payload_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ControllerCapabilitySnapshot:
    schema_version: str
    product_version: str
    tenant_id: str
    controller_id: str
    machine_id: str
    status: str
    operational_eligible: bool
    certification_status: str
    connection_status: str
    telemetry_fresh: bool
    telemetry_age_seconds: float
    integration_mode: str
    capabilities: dict[str, bool]
    last_sequence_number: int
    last_observed_at: str
    handshake_digest: str
    telemetry_digest: str
    blocking_reasons: list[str]
    limitations: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_controller_handshake(
    *,
    tenant_id: str,
    controller_id: str,
    machine_id: str,
    protocol: str,
    provider: str,
    model: str | None,
    firmware_version: str | None,
    integration_mode: str,
    capabilities: dict[str, bool],
    certification_status: str,
    identity_fingerprint: str,
    observed_at: str | datetime,
) -> ControllerHandshake:
    blockers = []
    if protocol not in SUPPORTED_PROTOCOLS:
        blockers.append("UNSUPPORTED_CONTROLLER_PROTOCOL")
    if integration_mode not in SAFE_MODES:
        blockers.append("INVALID_CONTROLLER_INTEGRATION_MODE")
    if not identity_fingerprint or len(identity_fingerprint) < 16:
        blockers.append("CONTROLLER_IDENTITY_FINGERPRINT_REQUIRED")
    if blockers:
        raise ValueError(",".join(blockers))
    normalized = {
        "tenant_id": tenant_id,
        "controller_id": controller_id,
        "machine_id": machine_id,
        "protocol": protocol,
        "provider": provider,
        "model": model,
        "firmware_version": firmware_version,
        "integration_mode": integration_mode,
        "capabilities": {str(k): bool(v) for k, v in sorted(capabilities.items())},
        "certification_status": certification_status,
        "identity_fingerprint": identity_fingerprint,
        "observed_at": _utc(observed_at).isoformat(),
    }
    return ControllerHandshake(**normalized, handshake_digest=_digest(normalized))


def normalize_controller_telemetry(
    *,
    handshake: ControllerHandshake,
    payload: dict[str, Any],
    sequence_number: int,
    observed_at: str | datetime,
    received_at: str | datetime,
    source_message_id: str,
    previous_sequence_number: int | None = None,
    previous_observed_at: str | datetime | None = None,
) -> NormalizedControllerTelemetry:
    if sequence_number < 0:
        raise ValueError("SEQUENCE_NUMBER_INVALID")
    if previous_sequence_number is not None and sequence_number <= previous_sequence_number:
        raise ValueError("TELEMETRY_REPLAY_OR_OUT_OF_ORDER")
    observed = _utc(observed_at)
    received = _utc(received_at)
    if observed > received:
        raise ValueError("TELEMETRY_OBSERVED_IN_FUTURE")
    if previous_observed_at is not None and observed <= _utc(previous_observed_at):
        raise ValueError("TELEMETRY_TIMESTAMP_REPLAY_OR_OUT_OF_ORDER")
    if not source_message_id:
        raise ValueError("SOURCE_MESSAGE_ID_REQUIRED")
    normalized_payload = {
        "connection_status": str(payload.get("connection_status") or "unknown"),
        "operating_state": str(payload.get("operating_state") or "unknown"),
        "position_percent": _finite(payload.get("position_percent")),
        "speed_percent": _finite(payload.get("speed_percent")),
        "pressure_bar": _finite(payload.get("pressure_bar")),
        "flow_lps": _finite(payload.get("flow_lps")),
        "alarm_codes": sorted({str(x) for x in payload.get("alarm_codes") or []}),
    }
    for key in ("position_percent", "speed_percent"):
        value = normalized_payload[key]
        if value is not None and not 0 <= value <= 100:
            raise ValueError(f"{key.upper()}_OUT_OF_RANGE")
    digest_input = {
        "controller_id": handshake.controller_id,
        "machine_id": handshake.machine_id,
        "sequence_number": sequence_number,
        "observed_at": observed.isoformat(),
        "received_at": received.isoformat(),
        "source_message_id": source_message_id,
        "payload": normalized_payload,
    }
    return NormalizedControllerTelemetry(
        tenant_id=handshake.tenant_id,
        controller_id=handshake.controller_id,
        machine_id=handshake.machine_id,
        sequence_number=sequence_number,
        observed_at=observed.isoformat(),
        received_at=received.isoformat(),
        source_message_id=source_message_id,
        payload_digest=_digest(digest_input),
        **normalized_payload,
    )


def build_controller_capability_snapshot(
    *,
    handshake: ControllerHandshake,
    telemetry: NormalizedControllerTelemetry,
    now: str | datetime,
    maximum_age_seconds: int = 300,
) -> ControllerCapabilitySnapshot:
    blockers: list[str] = []
    limitations: list[str] = []
    if (
        handshake.controller_id != telemetry.controller_id
        or handshake.machine_id != telemetry.machine_id
    ):
        blockers.append("CONTROLLER_TELEMETRY_IDENTITY_MISMATCH")
    age = max(0.0, (_utc(now) - _utc(telemetry.observed_at)).total_seconds())
    fresh = age <= maximum_age_seconds
    if not fresh:
        blockers.append("CONTROLLER_TELEMETRY_STALE")
    if handshake.certification_status != "certified":
        blockers.append("CERTIFIED_CONTROLLER_REQUIRED")
    if telemetry.connection_status not in {"online", "connected"}:
        blockers.append("CONTROLLER_NOT_CONNECTED")
    for name in REQUIRED_READ_CAPABILITIES:
        if not handshake.capabilities.get(name):
            blockers.append(f"CONTROLLER_CAPABILITY_{name.upper()}_REQUIRED")
    if telemetry.alarm_codes:
        blockers.append("CONTROLLER_ACTIVE_ALARM")
    if handshake.integration_mode == "read_only":
        limitations.append("READ_ONLY_NO_COMMAND_EXECUTION")
    elif handshake.integration_mode == "dry_run":
        limitations.append("DRY_RUN_NO_FIELD_DISPATCH")
    capability_payload = {
        "handshake_digest": handshake.handshake_digest,
        "telemetry_digest": telemetry.payload_digest,
        "age": age,
        "fresh": fresh,
        "blockers": sorted(set(blockers)),
        "limitations": sorted(set(limitations)),
    }
    eligible = not blockers
    return ControllerCapabilitySnapshot(
        schema_version=SCHEMA_VERSION,
        product_version=PRODUCT_VERSION,
        tenant_id=handshake.tenant_id,
        controller_id=handshake.controller_id,
        machine_id=handshake.machine_id,
        status="verified" if eligible else "blocked",
        operational_eligible=eligible,
        certification_status=handshake.certification_status,
        connection_status=telemetry.connection_status,
        telemetry_fresh=fresh,
        telemetry_age_seconds=round(age, 3),
        integration_mode=handshake.integration_mode,
        capabilities=handshake.capabilities,
        last_sequence_number=telemetry.sequence_number,
        last_observed_at=telemetry.observed_at,
        handshake_digest=handshake.handshake_digest,
        telemetry_digest=telemetry.payload_digest,
        blocking_reasons=sorted(set(blockers)),
        limitations=sorted(set(limitations)),
        capability_digest=_digest(capability_payload),
    )


def controller_capability_to_graph_input(snapshot: ControllerCapabilitySnapshot) -> dict[str, Any]:
    return {
        "controller_id": snapshot.controller_id,
        "machine_id": snapshot.machine_id,
        "certification_status": snapshot.certification_status,
        "connection_status": snapshot.connection_status,
        "telemetry_fresh": snapshot.telemetry_fresh,
        "capabilities": snapshot.capabilities,
        "capability_digest": snapshot.capability_digest,
        "blocking_reasons": snapshot.blocking_reasons,
    }


def prepare_controller_command_request(
    *,
    snapshot: ControllerCapabilitySnapshot,
    command_type: str,
    parameters: dict[str, Any],
    decision_id: str,
    authorization_id: str | None,
) -> dict[str, Any]:
    """Prepare, but never dispatch, a command request envelope."""
    if snapshot.integration_mode in {"read_only", "dry_run"}:
        raise PermissionError("CONTROLLER_MODE_FORBIDS_FIELD_COMMAND")
    if not snapshot.operational_eligible:
        raise PermissionError("CONTROLLER_CAPABILITY_NOT_OPERATIONAL")
    if not snapshot.capabilities.get("start_stop"):
        raise PermissionError("CONTROLLER_START_STOP_CAPABILITY_REQUIRED")
    if not decision_id:
        raise ValueError("DECISION_ID_REQUIRED")
    if (
        snapshot.integration_mode in {"human_approved_control", "guarded_automation"}
        and not authorization_id
    ):
        raise PermissionError("EXECUTION_AUTHORIZATION_REQUIRED")
    body = {
        "schema_version": "controller_command_request.v1",
        "controller_id": snapshot.controller_id,
        "machine_id": snapshot.machine_id,
        "command_type": command_type,
        "parameters": parameters,
        "decision_id": decision_id,
        "authorization_id": authorization_id,
        "controller_capability_digest": snapshot.capability_digest,
        "dispatch_allowed": False,
    }
    body["command_request_digest"] = _digest(body)
    return body
