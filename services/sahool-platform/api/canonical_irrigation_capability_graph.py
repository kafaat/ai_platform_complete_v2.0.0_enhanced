"""M2.8 unified irrigation capability graph.

This module composes governed well, hydraulic, irrigation-machine,
sprinkler/runoff, energy and controller capabilities into one deterministic,
fail-closed operational envelope for the irrigation MPC boundary.

It does not dispatch commands and does not mutate any source capability.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "canonical_irrigation_capability_graph.v1"
PRODUCT_VERSION = "irrigation-capability-graph/1.0.0"
REQUIRED_LINKS = ("well", "hydraulic", "machine", "sprinkler", "energy", "controller")


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(value or {})


def _link_state(name: str, capability: dict[str, Any]) -> dict[str, Any]:
    status = str(capability.get("status") or "missing")
    eligible = bool(capability.get("operational_eligible"))
    reasons = list(capability.get("blocking_reasons") or [])
    if capability.get("reason") and capability.get("reason") not in reasons:
        reasons.append(str(capability["reason"]))
    digest = capability.get("capability_digest") or capability.get("profile_digest")
    if status != "verified" or not eligible:
        if not reasons:
            reasons = [f"{name.upper()}_CAPABILITY_NOT_OPERATIONAL"]
        state = "blocked"
    elif not isinstance(digest, str) or len(digest) != 64:
        state = "blocked"
        reasons = [f"{name.upper()}_CAPABILITY_DIGEST_REQUIRED"]
    else:
        state = "available"
    return {
        "link": name,
        "state": state,
        "status": status,
        "operational_eligible": eligible,
        "capability_digest": digest,
        "blocking_reasons": sorted(set(reasons)),
    }


@dataclass(frozen=True)
class CanonicalIrrigationCapabilityGraph:
    schema_version: str
    product_version: str
    generated_at: str
    effective_at: str
    tenant_id: str
    project_id: str
    field_id: str
    season_id: str
    well_id: str
    pump_id: str
    machine_id: str
    controller_id: str
    energy_system_id: str
    status: str
    operational_eligible: bool
    weakest_link: str | None
    maximum_flow_lps: float
    maximum_daily_volume_m3: float
    remaining_daily_volume_m3: float
    remaining_seasonal_volume_m3: float | None
    terminal_pressure_bar: float
    maximum_daily_depth_mm: float
    maximum_safe_depth_mm_event: float
    runoff_safety_factor: float
    specific_energy_kwh_m3: float | None
    minimum_rest_hours: float
    hourly_operating_windows: list[dict[str, Any]]
    controller_capabilities: dict[str, bool]
    link_states: list[dict[str, Any]]
    evidence: dict[str, Any]
    limitations: list[str]
    blocking_reasons: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _controller_state(controller: dict[str, Any], machine_id: str) -> dict[str, Any]:
    controller_id = str(controller.get("controller_id") or controller.get("id") or "")
    bound_machine_id = str(controller.get("machine_id") or controller.get("asset_id") or "")
    blockers: list[str] = []
    if not controller_id:
        blockers.append("CONTROLLER_IDENTITY_REQUIRED")
    if bound_machine_id and bound_machine_id != machine_id:
        blockers.append("CONTROLLER_MACHINE_BINDING_MISMATCH")
    if str(controller.get("certification_status") or "") != "certified":
        blockers.append("CERTIFIED_CONTROLLER_REQUIRED")
    if str(controller.get("connection_status") or "") not in {"online", "connected"}:
        blockers.append("CONTROLLER_NOT_CONNECTED")
    if not bool(controller.get("telemetry_fresh")):
        blockers.append("CONTROLLER_TELEMETRY_STALE")
    capabilities = dict(controller.get("capabilities") or {})
    required = ("read_status", "read_position", "start_stop")
    for capability in required:
        if not bool(capabilities.get(capability)):
            blockers.append(f"CONTROLLER_CAPABILITY_{capability.upper()}_REQUIRED")
    digest = controller.get("capability_digest") or controller.get("evidence_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        blockers.append("CONTROLLER_CAPABILITY_DIGEST_REQUIRED")
    return {
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "controller_id": controller_id,
        "machine_id": bound_machine_id or machine_id,
        "capabilities": capabilities,
        "capability_digest": digest,
        "blocking_reasons": sorted(set(blockers)),
    }


def _hourly_windows(
    *,
    energy: dict[str, Any],
    hydraulic_power_kw: float | None,
    required_load_ids: set[str],
) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for envelope in list(energy.get("hourly_envelopes") or []):
        permitted = set(str(item) for item in envelope.get("permitted_load_ids") or [])
        max_power = _number(envelope.get("maximum_continuous_load_kw")) or 0.0
        power_ok = hydraulic_power_kw is None or hydraulic_power_kw <= max_power + 1e-9
        loads_ok = not required_load_ids or required_load_ids.issubset(permitted)
        windows.append(
            {
                "hour": str(envelope.get("hour") or ""),
                "operational": bool(power_ok and loads_ok),
                "maximum_available_power_kw": round(max_power, 6),
                "maximum_starting_kva": round(
                    _number(envelope.get("maximum_starting_kva")) or 0.0, 6
                ),
                "energy_cost_per_kwh": round(
                    _number(envelope.get("energy_cost_per_kwh")) or 0.0, 6
                ),
                "renewable_fraction": round(_number(envelope.get("renewable_fraction")) or 0.0, 6),
                "reason_codes": sorted(
                    code
                    for code, failed in (
                        ("HYDRAULIC_POWER_EXCEEDS_ENERGY_WINDOW", not power_ok),
                        ("REQUIRED_ENERGY_LOAD_NOT_PERMITTED", not loads_ok),
                    )
                    if failed
                ),
            }
        )
    return windows


def build_canonical_irrigation_capability_graph(
    *,
    tenant_id: str,
    project_id: str,
    field_id: str,
    season_id: str,
    well_capability: dict[str, Any] | Any,
    hydraulic_capability: dict[str, Any] | Any,
    machine_capability: dict[str, Any] | Any,
    sprinkler_capability: dict[str, Any] | Any,
    energy_capability: dict[str, Any] | Any,
    controller: dict[str, Any],
    required_energy_load_ids: list[str] | None = None,
    now: datetime | None = None,
) -> CanonicalIrrigationCapabilityGraph:
    """Build the weakest-link irrigation operating capability.

    Every source link must be verified, operationally eligible and carry a
    full SHA-256 digest. Any missing or blocked link blocks the whole graph.
    """
    now = now or datetime.now(UTC)
    well = _as_dict(well_capability)
    hydraulic = _as_dict(hydraulic_capability)
    machine = _as_dict(machine_capability)
    sprinkler = _as_dict(sprinkler_capability)
    energy = _as_dict(energy_capability)

    machine_id = str(machine.get("machine_id") or "")
    controller_state = _controller_state(controller, machine_id)
    links = {
        "well": _link_state("well", well),
        "hydraulic": _link_state("hydraulic", hydraulic),
        "machine": _link_state("machine", machine),
        "sprinkler": _link_state("sprinkler", sprinkler),
        "energy": _link_state("energy", energy),
        "controller": _link_state("controller", controller_state),
    }

    blockers: list[str] = []
    limitations: list[str] = []
    for name in REQUIRED_LINKS:
        state = links[name]
        if state["state"] != "available":
            blockers.extend(f"{name.upper()}::{reason}" for reason in state["blocking_reasons"])

    # Cross-link identity integrity: a verified chain must refer to one asset path.
    well_id = str(well.get("well_id") or "")
    hydraulic_well_id = str(hydraulic.get("well_id") or "")
    hydraulic_target = str(hydraulic.get("target_asset_id") or "")
    sprinkler_machine = str(sprinkler.get("machine_id") or "")
    if hydraulic_well_id and well_id and hydraulic_well_id != well_id:
        blockers.append("GRAPH_IDENTITY::WELL_HYDRAULIC_MISMATCH")
    if hydraulic_target and machine_id and hydraulic_target != machine_id:
        blockers.append("GRAPH_IDENTITY::HYDRAULIC_MACHINE_MISMATCH")
    if sprinkler_machine and machine_id and sprinkler_machine != machine_id:
        blockers.append("GRAPH_IDENTITY::MACHINE_SPRINKLER_MISMATCH")

    source_flow = _number(well.get("maximum_flow_lps")) or 0.0
    hydraulic_flow = _number(hydraulic.get("maximum_deliverable_flow_lps")) or 0.0
    machine_flow = _number(machine.get("design_flow_lps"))
    flow_candidates = [
        value
        for value in (source_flow, hydraulic_flow, machine_flow)
        if value is not None and value > 0
    ]
    maximum_flow = min(flow_candidates) if flow_candidates else 0.0
    if maximum_flow <= 0:
        blockers.append("GRAPH_CAPACITY::NO_DELIVERABLE_FLOW")

    machine_depth = _number(machine.get("maximum_daily_depth_mm")) or 0.0
    safe_event_depth = _number(sprinkler.get("maximum_safe_depth_mm_event")) or 0.0
    if machine_depth <= 0:
        blockers.append("GRAPH_CAPACITY::NO_MACHINE_APPLICATION_CAPACITY")
    if safe_event_depth <= 0:
        blockers.append("GRAPH_CAPACITY::NO_SAFE_EVENT_DEPTH")

    hydraulic_power_kw = _number(hydraulic.get("electrical_power_kw"))
    required_loads = set(str(item) for item in required_energy_load_ids or [])
    hourly_windows = _hourly_windows(
        energy=energy,
        hydraulic_power_kw=hydraulic_power_kw,
        required_load_ids=required_loads,
    )
    if not hourly_windows:
        blockers.append("GRAPH_ENERGY::NO_HOURLY_ENERGY_WINDOWS")
    elif not any(window["operational"] for window in hourly_windows):
        blockers.append("GRAPH_ENERGY::NO_FEASIBLE_OPERATING_WINDOW")

    weakest_link = next(
        (name for name in REQUIRED_LINKS if links[name]["state"] != "available"), None
    )
    if weakest_link is None:
        ratios: list[tuple[str, float]] = []
        if source_flow > 0 and hydraulic_flow > 0:
            ratios.append(("hydraulic", hydraulic_flow / source_flow))
        if maximum_flow > 0 and machine_flow and machine_flow > 0:
            ratios.append(("machine", maximum_flow / machine_flow))
        runoff_factor = _number(sprinkler.get("runoff_safety_factor"))
        if runoff_factor is not None:
            ratios.append(("sprinkler", min(1.0, runoff_factor)))
        operational_share = (
            sum(1 for item in hourly_windows if item["operational"]) / len(hourly_windows)
            if hourly_windows
            else 0.0
        )
        ratios.append(("energy", operational_share))
        weakest_link = min(ratios, key=lambda item: item[1])[0] if ratios else None

    for capability in (well, hydraulic, machine, sprinkler, energy):
        limitations.extend(str(item) for item in capability.get("limitations") or [])

    evidence = {
        "well_capability_digest": well.get("capability_digest"),
        "hydraulic_capability_digest": hydraulic.get("capability_digest"),
        "machine_capability_digest": machine.get("capability_digest"),
        "sprinkler_capability_digest": sprinkler.get("capability_digest"),
        "energy_capability_digest": energy.get("capability_digest"),
        "controller_capability_digest": controller_state.get("capability_digest"),
    }
    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        # مرساةٌ زمنيّة موحَّدة عبر المُنتِجين — بدونها لا يُقاس عمرُ القيمة.
        "generated_at": now.isoformat(),
        "effective_at": now.isoformat(),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "field_id": field_id,
        "season_id": season_id,
        "well_id": well_id,
        "pump_id": str(hydraulic.get("pump_id") or ""),
        "machine_id": machine_id,
        "controller_id": str(controller_state.get("controller_id") or ""),
        "energy_system_id": str(energy.get("energy_system_id") or ""),
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "weakest_link": weakest_link,
        "maximum_flow_lps": round(maximum_flow, 6),
        "maximum_daily_volume_m3": round(_number(well.get("maximum_daily_volume_m3")) or 0.0, 6),
        "remaining_daily_volume_m3": round(
            _number(well.get("remaining_daily_volume_m3")) or 0.0, 6
        ),
        "remaining_seasonal_volume_m3": (
            None
            if _number(well.get("remaining_seasonal_volume_m3")) is None
            else round(float(well["remaining_seasonal_volume_m3"]), 6)
        ),
        "terminal_pressure_bar": round(_number(hydraulic.get("terminal_pressure_bar")) or 0.0, 6),
        "maximum_daily_depth_mm": round(machine_depth, 6),
        "maximum_safe_depth_mm_event": round(
            min(machine_depth, safe_event_depth) if machine_depth and safe_event_depth else 0.0, 6
        ),
        "runoff_safety_factor": round(_number(sprinkler.get("runoff_safety_factor")) or 0.0, 6),
        "specific_energy_kwh_m3": (
            None
            if _number(hydraulic.get("specific_energy_kwh_m3")) is None
            else round(float(hydraulic["specific_energy_kwh_m3"]), 8)
        ),
        "minimum_rest_hours": round(_number(well.get("minimum_rest_hours")) or 0.0, 6),
        "hourly_operating_windows": hourly_windows,
        "controller_capabilities": {
            key: bool(value)
            for key, value in sorted(controller_state.get("capabilities", {}).items())
        },
        "link_states": [links[name] for name in REQUIRED_LINKS],
        "evidence": evidence,
        "limitations": sorted(set(limitations)),
        "blocking_reasons": sorted(set(blockers)),
    }
    return CanonicalIrrigationCapabilityGraph(**base, capability_digest=_digest(base))


def irrigation_capability_graph_to_mpc_constraints(
    graph: CanonicalIrrigationCapabilityGraph | dict[str, Any],
) -> dict[str, Any]:
    """Expose the single governed engineering boundary to irrigation MPC."""
    data = graph.to_dict() if isinstance(graph, CanonicalIrrigationCapabilityGraph) else graph
    if data.get("status") != "verified" or not data.get("operational_eligible"):
        return {
            "status": "blocked",
            "reason": "canonical_irrigation_capability_graph_not_operational",
            "weakest_link": data.get("weakest_link"),
            "blocking_reasons": list(data.get("blocking_reasons") or ["unknown"]),
            "irrigation_capability_digest": data.get("capability_digest"),
        }
    return {
        "status": "available",
        "well_id": data["well_id"],
        "pump_id": data["pump_id"],
        "machine_id": data["machine_id"],
        "controller_id": data["controller_id"],
        "energy_system_id": data["energy_system_id"],
        "maximum_flow_lps": data["maximum_flow_lps"],
        "remaining_daily_volume_m3": data["remaining_daily_volume_m3"],
        "remaining_seasonal_volume_m3": data["remaining_seasonal_volume_m3"],
        "maximum_daily_depth_mm": data["maximum_daily_depth_mm"],
        "maximum_safe_depth_mm_event": data["maximum_safe_depth_mm_event"],
        "minimum_rest_hours": data["minimum_rest_hours"],
        "terminal_pressure_bar": data["terminal_pressure_bar"],
        "specific_energy_kwh_m3": data["specific_energy_kwh_m3"],
        "hourly_operating_windows": [
            item for item in data["hourly_operating_windows"] if item.get("operational")
        ],
        "weakest_link": data["weakest_link"],
        "irrigation_capability_digest": data["capability_digest"],
    }
