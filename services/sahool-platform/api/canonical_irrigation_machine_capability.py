"""M2.5 canonical center-pivot/linear machine capability."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_irrigation_machine_capability.v1"
PRODUCT_VERSION = "irrigation-machine-capability/1.0.0"
SUPPORTED = {"center_pivot", "sector_pivot", "linear_move", "towable_linear"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class CanonicalIrrigationMachineCapability:
    schema_version: str
    product_version: str
    tenant_id: str
    project_id: str
    machine_id: str
    machine_type: str
    status: str
    operational_eligible: bool
    effective_area_ha: float
    design_flow_lps: float
    full_cycle_hours: float
    application_rate_mm_day: float
    depth_per_full_cycle_mm: float
    maximum_daily_depth_mm: float
    minimum_speed_percent: float
    maximum_speed_percent: float
    controller_capabilities: dict[str, bool]
    evidence: dict[str, Any]
    limitations: list[str]
    blocking_reasons: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_canonical_irrigation_machine_capability(
    *,
    tenant_id: str,
    project_id: str,
    machine: dict[str, Any],
    hydraulic_capability: dict[str, Any],
    controller: dict[str, Any],
) -> CanonicalIrrigationMachineCapability | dict[str, Any]:
    if hydraulic_capability.get("status") != "verified" or not hydraulic_capability.get(
        "operational_eligible"
    ):
        return {"status": "blocked", "reason": "verified_hydraulic_capability_required"}
    machine_id = str(machine.get("machine_id") or machine.get("id") or "")
    machine_type = str(machine.get("machine_type") or "")
    if not machine_id or machine_type not in SUPPORTED:
        return {"status": "blocked", "reason": "supported_machine_identity_required"}
    if str(machine.get("certification_status") or "") != "certified":
        return {"status": "blocked", "reason": "certified_machine_required"}
    if str(controller.get("certification_status") or "") != "certified":
        return {"status": "blocked", "reason": "certified_controller_required"}

    area_ha = _num(machine.get("effective_area_ha"))
    design_flow = _num(machine.get("design_flow_lps"))
    cycle_h = _num(machine.get("full_cycle_hours"))
    min_speed = _num(machine.get("minimum_speed_percent"))
    max_speed = _num(machine.get("maximum_speed_percent"))
    available_flow = _num(hydraulic_capability.get("maximum_deliverable_flow_lps"))
    inlet_pressure = _num(hydraulic_capability.get("terminal_pressure_bar"))
    required_pressure = _num(machine.get("required_inlet_pressure_bar"))
    if any(
        v is None
        for v in (
            area_ha,
            design_flow,
            cycle_h,
            min_speed,
            max_speed,
            available_flow,
            inlet_pressure,
            required_pressure,
        )
    ):
        return {"status": "blocked", "reason": "complete_certified_machine_parameters_required"}
    if area_ha <= 0 or design_flow <= 0 or cycle_h <= 0 or not 0 < min_speed <= max_speed <= 100:
        return {"status": "blocked", "reason": "invalid_machine_parameters"}

    blockers: list[str] = []
    limitations: list[str] = []
    if available_flow + 1e-9 < design_flow:
        blockers.append("INSUFFICIENT_HYDRAULIC_FLOW_FOR_MACHINE")
    if inlet_pressure + 1e-9 < required_pressure:
        blockers.append("INSUFFICIENT_MACHINE_INLET_PRESSURE")
    capabilities = dict(controller.get("capabilities") or {})
    if not capabilities.get("read_status"):
        blockers.append("CONTROLLER_STATUS_TELEMETRY_REQUIRED")
    if not capabilities.get("read_position"):
        limitations.append("position telemetry unavailable")

    # Q [L/s] and area [ha] -> mm/day = 8.64 Q/A.
    application_rate = 8.64 * min(design_flow, available_flow) / area_ha
    depth_cycle = application_rate * cycle_h / 24.0
    maximum_daily_depth = application_rate * (100.0 / min_speed)
    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "machine_id": machine_id,
        "machine_type": machine_type,
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "effective_area_ha": round(area_ha, 6),
        "design_flow_lps": round(design_flow, 6),
        "full_cycle_hours": round(cycle_h, 6),
        "application_rate_mm_day": round(application_rate, 6),
        "depth_per_full_cycle_mm": round(depth_cycle, 6),
        "maximum_daily_depth_mm": round(maximum_daily_depth, 6),
        "minimum_speed_percent": round(min_speed, 4),
        "maximum_speed_percent": round(max_speed, 4),
        "controller_capabilities": capabilities,
        "evidence": {
            "hydraulic_capability_digest": hydraulic_capability.get("capability_digest"),
            "machine_certificate_digest": machine.get("certificate_digest"),
            "controller_certificate_digest": controller.get("certificate_digest"),
        },
        "limitations": sorted(set(limitations)),
        "blocking_reasons": sorted(set(blockers)),
    }
    return CanonicalIrrigationMachineCapability(**base, capability_digest=_digest(base))


def machine_capability_to_mpc_constraints(
    capability: CanonicalIrrigationMachineCapability | dict[str, Any],
) -> dict[str, Any]:
    data = (
        capability.to_dict()
        if isinstance(capability, CanonicalIrrigationMachineCapability)
        else capability
    )
    if data.get("status") != "verified" or not data.get("operational_eligible"):
        return {
            "status": "blocked",
            "reason": "canonical_machine_capability_not_operational",
            "blocking_reasons": list(
                data.get("blocking_reasons") or [data.get("reason") or "unknown"]
            ),
        }
    return {
        "status": "available",
        "machine_id": data["machine_id"],
        "maximum_daily_depth_mm": data["maximum_daily_depth_mm"],
        "minimum_speed_percent": data["minimum_speed_percent"],
        "maximum_speed_percent": data["maximum_speed_percent"],
        "machine_capability_digest": data["capability_digest"],
    }
