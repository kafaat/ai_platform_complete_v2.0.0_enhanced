"""M2.4 canonical pump and hydraulic-network capability.

Pure deterministic engineering kernel. It combines a verified well capability,
certified pump curve, commissioned pipe segments, elevation, minor losses and
required terminal pressure. Missing certified inputs fail closed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_hydraulic_capability.v1"
PRODUCT_VERSION = "hydraulic-capability/1.0.0"
RHO_WATER = 998.2
G = 9.80665
KINEMATIC_VISCOSITY = 1.004e-6


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _interp(points: list[dict[str, Any]], flow_lps: float, key: str) -> float | None:
    valid: list[tuple[float, float]] = []
    for point in points:
        q = _finite(point.get("flow_lps"))
        y = _finite(point.get(key))
        if q is not None and y is not None and q >= 0:
            valid.append((q, y))
    valid.sort()
    if len(valid) < 2 or flow_lps < valid[0][0] or flow_lps > valid[-1][0]:
        return None
    for (q0, y0), (q1, y1) in zip(valid, valid[1:], strict=True):
        if q0 <= flow_lps <= q1:
            if abs(q1 - q0) < 1e-12:
                return y0
            ratio = (flow_lps - q0) / (q1 - q0)
            return y0 + ratio * (y1 - y0)
    return None


def _darcy_friction_factor(reynolds: float, relative_roughness: float) -> float:
    if reynolds <= 0:
        raise ValueError("reynolds must be positive")
    if reynolds < 2300:
        return 64.0 / reynolds
    # Swamee-Jain explicit approximation.
    return 0.25 / (math.log10(relative_roughness / 3.7 + 5.74 / (reynolds**0.9)) ** 2)


def _segment_loss_m(segment: dict[str, Any], flow_lps: float) -> tuple[float, float]:
    length_m = _finite(segment.get("length_m"))
    diameter_mm = _finite(segment.get("internal_diameter_mm"))
    roughness_mm = _finite(segment.get("absolute_roughness_mm"))
    minor_k = _finite(segment.get("minor_loss_k")) or 0.0
    if length_m is None or length_m <= 0 or diameter_mm is None or diameter_mm <= 0:
        raise ValueError("valid segment length and internal diameter are required")
    if roughness_mm is None or roughness_mm < 0:
        raise ValueError("absolute roughness is required")
    q_m3s = flow_lps / 1000.0
    diameter_m = diameter_mm / 1000.0
    area_m2 = math.pi * diameter_m**2 / 4.0
    velocity = q_m3s / area_m2
    reynolds = velocity * diameter_m / KINEMATIC_VISCOSITY
    factor = _darcy_friction_factor(reynolds, (roughness_mm / 1000.0) / diameter_m)
    dynamic_head = velocity**2 / (2.0 * G)
    loss = factor * (length_m / diameter_m) * dynamic_head + minor_k * dynamic_head
    return loss, velocity


@dataclass(frozen=True)
class CanonicalHydraulicCapability:
    schema_version: str
    product_version: str
    tenant_id: str
    project_id: str
    well_id: str
    pump_id: str
    target_asset_id: str
    status: str
    operational_eligible: bool
    maximum_deliverable_flow_lps: float
    evaluated_flow_lps: float
    pump_head_m: float
    required_tdh_m: float
    terminal_pressure_bar: float
    required_terminal_pressure_bar: float
    total_friction_loss_m: float
    static_head_m: float
    maximum_velocity_m_s: float
    pump_efficiency: float | None
    electrical_power_kw: float | None
    specific_energy_kwh_m3: float | None
    pressure_margin_bar: float
    evidence: dict[str, Any]
    limitations: list[str]
    blocking_reasons: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_canonical_hydraulic_capability(
    *,
    tenant_id: str,
    project_id: str,
    well_capability: dict[str, Any],
    pump: dict[str, Any],
    segments: list[dict[str, Any]],
    target: dict[str, Any],
) -> CanonicalHydraulicCapability | dict[str, Any]:
    if well_capability.get("status") != "verified" or not well_capability.get(
        "operational_eligible"
    ):
        return {"status": "blocked", "reason": "verified_well_capability_required"}
    pump_id = str(pump.get("pump_id") or pump.get("id") or "")
    target_id = str(target.get("target_asset_id") or target.get("id") or "")
    well_id = str(well_capability.get("well_id") or "")
    if not pump_id or not target_id or not well_id:
        return {"status": "blocked", "reason": "hydraulic_asset_identity_missing"}
    if str(pump.get("certification_status") or "") != "certified":
        return {"status": "blocked", "reason": "certified_pump_curve_required"}
    if not segments or any(
        str(s.get("certification_status") or "") != "certified" for s in segments
    ):
        return {"status": "blocked", "reason": "certified_mainline_segments_required"}

    curve = list(pump.get("curve_points") or [])
    max_well_flow = _finite(well_capability.get("maximum_flow_lps"))
    required_pressure_bar = _finite(target.get("required_inlet_pressure_bar"))
    elevation_gain_m = _finite(target.get("elevation_gain_m"))
    motor_efficiency = _finite(pump.get("motor_efficiency"))
    if max_well_flow is None or max_well_flow <= 0 or required_pressure_bar is None:
        return {"status": "blocked", "reason": "well_flow_or_terminal_pressure_missing"}
    if elevation_gain_m is None:
        return {"status": "blocked", "reason": "elevation_profile_required"}
    if motor_efficiency is None or not 0 < motor_efficiency <= 1:
        return {"status": "blocked", "reason": "certified_motor_efficiency_required"}

    required_pressure_head_m = required_pressure_bar * 100000.0 / (RHO_WATER * G)

    def evaluate(flow: float) -> dict[str, float | None]:
        losses = 0.0
        velocities: list[float] = []
        for segment in segments:
            loss, velocity = _segment_loss_m(segment, flow)
            losses += loss
            velocities.append(velocity)
        required_tdh = max(0.0, elevation_gain_m) + losses + required_pressure_head_m
        pump_head = _interp(curve, flow, "head_m")
        pump_eff = _interp(curve, flow, "efficiency")
        if pump_eff is None:
            pump_eff = _finite(pump.get("pump_efficiency"))
        margin_head = None if pump_head is None else pump_head - required_tdh
        terminal_pressure = (
            0.0
            if pump_head is None
            else max(0.0, pump_head - max(0.0, elevation_gain_m) - losses)
            * RHO_WATER
            * G
            / 100000.0
        )
        power_kw = None
        specific = None
        if pump_head is not None and pump_eff is not None and 0 < pump_eff <= 1:
            power_kw = (
                RHO_WATER * G * (flow / 1000.0) * pump_head / (pump_eff * motor_efficiency) / 1000.0
            )
            specific = power_kw / max(flow * 3.6, 1e-12)
        return {
            "losses": losses,
            "max_velocity": max(velocities),
            "required_tdh": required_tdh,
            "pump_head": pump_head,
            "pump_eff": pump_eff,
            "margin_head": margin_head,
            "terminal_pressure": terminal_pressure,
            "power_kw": power_kw,
            "specific": specific,
        }

    curve_flows = sorted(
        q for p in curve if (q := _finite(p.get("flow_lps"))) is not None and q >= 0
    )
    if len(curve_flows) < 2:
        return {"status": "blocked", "reason": "pump_curve_requires_two_or_more_points"}
    upper = min(max_well_flow, curve_flows[-1])
    lower = max(curve_flows[0], 0.001)
    if lower > upper:
        return {"status": "blocked", "reason": "pump_curve_outside_well_operating_range"}

    low, high = lower, upper
    if (_finite(evaluate(low).get("margin_head")) or -math.inf) < 0:
        max_flow = 0.0
    else:
        for _ in range(60):
            mid = (low + high) / 2.0
            margin = evaluate(mid)["margin_head"]
            if margin is not None and margin >= 0:
                low = mid
            else:
                high = mid
        max_flow = low

    requested = _finite(target.get("requested_flow_lps")) or max_flow
    evaluated_flow = min(requested, max_flow) if max_flow > 0 else lower
    result = evaluate(evaluated_flow)
    blockers: list[str] = []
    limitations: list[str] = []
    if max_flow <= 0:
        blockers.append("INSUFFICIENT_PUMP_HEAD")
    if requested > max_flow + 1e-6:
        blockers.append("REQUESTED_FLOW_EXCEEDS_HYDRAULIC_CAPABILITY")
    maximum_velocity_limit = min(
        (_finite(s.get("maximum_velocity_m_s")) or math.inf) for s in segments
    )
    if result["max_velocity"] is not None and result["max_velocity"] > maximum_velocity_limit:
        blockers.append("MAINLINE_VELOCITY_TOO_HIGH")
    for segment in segments:
        rating_bar = _finite(segment.get("pressure_rating_bar"))
        if rating_bar is None:
            limitations.append(
                f"pressure rating missing:{segment.get('segment_id') or segment.get('id')}"
            )
        elif result["pump_head"] is not None:
            pump_discharge_bar = result["pump_head"] * RHO_WATER * G / 100000.0
            if pump_discharge_bar > rating_bar:
                blockers.append("MAINLINE_PRESSURE_RATING_EXCEEDED")
    if result["pump_eff"] is None:
        blockers.append("PUMP_EFFICIENCY_UNAVAILABLE")

    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "well_id": well_id,
        "pump_id": pump_id,
        "target_asset_id": target_id,
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "maximum_deliverable_flow_lps": round(max_flow, 6),
        "evaluated_flow_lps": round(evaluated_flow, 6),
        "pump_head_m": round(float(result["pump_head"] or 0.0), 6),
        "required_tdh_m": round(float(result["required_tdh"] or 0.0), 6),
        "terminal_pressure_bar": round(float(result["terminal_pressure"] or 0.0), 6),
        "required_terminal_pressure_bar": round(required_pressure_bar, 6),
        "total_friction_loss_m": round(float(result["losses"] or 0.0), 6),
        "static_head_m": round(max(0.0, elevation_gain_m), 6),
        "maximum_velocity_m_s": round(float(result["max_velocity"] or 0.0), 6),
        "pump_efficiency": None
        if result["pump_eff"] is None
        else round(float(result["pump_eff"]), 6),
        "electrical_power_kw": None
        if result["power_kw"] is None
        else round(float(result["power_kw"]), 6),
        "specific_energy_kwh_m3": None
        if result["specific"] is None
        else round(float(result["specific"]), 8),
        "pressure_margin_bar": round(
            float(result["margin_head"] or 0.0) * RHO_WATER * G / 100000.0, 6
        ),
        "evidence": {
            "well_capability_digest": well_capability.get("capability_digest"),
            "pump_curve_digest": pump.get("curve_digest"),
            "segment_digests": [s.get("segment_digest") for s in segments],
            "terrain_profile_digest": target.get("terrain_profile_digest"),
        },
        "limitations": sorted(set(limitations)),
        "blocking_reasons": sorted(set(blockers)),
    }
    return CanonicalHydraulicCapability(**base, capability_digest=_digest(base))


def hydraulic_capability_to_mpc_constraints(
    capability: CanonicalHydraulicCapability | dict[str, Any],
) -> dict[str, Any]:
    data = (
        capability.to_dict() if isinstance(capability, CanonicalHydraulicCapability) else capability
    )
    if data.get("status") != "verified" or not data.get("operational_eligible"):
        return {
            "status": "blocked",
            "reason": "canonical_hydraulic_capability_not_operational",
            "blocking_reasons": list(
                data.get("blocking_reasons") or [data.get("reason") or "unknown"]
            ),
        }
    return {
        "status": "available",
        "maximum_deliverable_flow_lps": data["maximum_deliverable_flow_lps"],
        "terminal_pressure_bar": data["terminal_pressure_bar"],
        "specific_energy_kwh_m3": data["specific_energy_kwh_m3"],
        "hydraulic_capability_digest": data["capability_digest"],
    }
