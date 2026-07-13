"""M4 governed variable-rate irrigation (VRI) prescription.

The module translates a recommendation-only hourly MPC schedule into a spatial
prescription for a certified irrigation machine.  It consumes governed
management-zone, root-zone, terrain, EO and sprinkler evidence, preserves the
MPC water budget, and never emits a vendor command or dispatchable artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_vri_prescription.v1"
SOLVER_VERSION = "governed-vri-allocation.v1"


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


@dataclass(frozen=True)
class VRIPrescriptionZone:
    zone_id: str
    area_ha: float
    start_angle_deg: float
    end_angle_deg: float
    inner_radius_m: float
    outer_radius_m: float
    target_depth_mm: float
    target_volume_m3: float
    application_percent: float
    priority_score: float
    source_zone_digest: str
    reason_codes: list[str]


@dataclass(frozen=True)
class GovernedVRIPrescription:
    schema_version: str
    solver_version: str
    tenant_id: str
    field_id: str
    season_id: str
    machine_id: str
    status: str
    decision: str
    recommendation_only: bool
    execution_allowed: bool
    translation_allowed: bool
    planned_uniform_depth_mm: float
    prescribed_average_depth_mm: float
    prescribed_volume_m3: float
    uncovered_budget_mm: float
    zones: list[dict[str, Any]]
    blocking_reasons: list[str]
    limitations: list[str]
    source_digests: dict[str, str]
    prescription_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blocked(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    machine_id: str,
    reasons: list[str],
    source_digests: dict[str, str],
) -> GovernedVRIPrescription:
    reasons = sorted(set(reasons))
    payload = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "machine_id": machine_id,
        "reasons": reasons,
        "source_digests": source_digests,
    }
    return GovernedVRIPrescription(
        schema_version=SCHEMA_VERSION,
        solver_version=SOLVER_VERSION,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        machine_id=machine_id,
        status="blocked",
        decision="blocked",
        recommendation_only=True,
        execution_allowed=False,
        translation_allowed=False,
        planned_uniform_depth_mm=0.0,
        prescribed_average_depth_mm=0.0,
        prescribed_volume_m3=0.0,
        uncovered_budget_mm=0.0,
        zones=[],
        blocking_reasons=reasons,
        limitations=[],
        source_digests=source_digests,
        prescription_digest=_digest(payload),
    )


def build_governed_vri_prescription(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    machine_id: str,
    hourly_mpc_schedule: dict[str, Any],
    irrigation_capability: dict[str, Any],
    commissioning_gate: dict[str, Any],
    management_zones: list[dict[str, Any]],
    machine_geometry: dict[str, Any],
    minimum_application_percent: float = 0.0,
    maximum_application_percent: float = 150.0,
    maximum_zone_count: int = 512,
) -> GovernedVRIPrescription:
    """Allocate the governed MPC water budget spatially across VRI zones.

    Allocation is deficit-weighted with EO stress as a bounded secondary signal.
    Terrain/runoff and sprinkler limits are hard caps. Exclusion zones always
    receive zero. The resulting prescription remains recommendation-only.
    """
    reasons: list[str] = []
    limitations: list[str] = []
    source_digests = {
        "hourly_mpc_schedule_digest": str(hourly_mpc_schedule.get("schedule_digest") or ""),
        "irrigation_capability_digest": str(
            irrigation_capability.get("irrigation_capability_digest") or ""
        ),
        "commissioning_executability_digest": str(
            commissioning_gate.get("executability_digest") or ""
        ),
        "management_zone_set_digest": str(machine_geometry.get("management_zone_set_digest") or ""),
        "machine_geometry_digest": str(machine_geometry.get("machine_geometry_digest") or ""),
        "sprinkler_capability_digest": str(
            irrigation_capability.get("sprinkler_capability_digest") or ""
        ),
        "terrain_profile_digest": str(machine_geometry.get("terrain_profile_digest") or ""),
    }
    if not all(_valid_digest(value) for value in source_digests.values()):
        reasons.append("COMPLETE_VRI_SOURCE_DIGESTS_REQUIRED")
    if hourly_mpc_schedule.get("status") not in {"verified", "degraded"}:
        reasons.append("HOURLY_MPC_SCHEDULE_REQUIRED")
    if hourly_mpc_schedule.get("recommendation_only") is not True:
        reasons.append("RECOMMENDATION_ONLY_MPC_SCHEDULE_REQUIRED")
    if irrigation_capability.get("status") not in {"verified", "available"}:
        reasons.append("IRRIGATION_CAPABILITY_GRAPH_BLOCKED")
    if (
        commissioning_gate.get("status") != "executable"
        or commissioning_gate.get("execution_allowed") is not True
    ):
        reasons.append("COMMISSIONING_EXECUTABILITY_GATE_REQUIRED")

    scheduled_depth = _num(hourly_mpc_schedule.get("scheduled_irrigation_mm"))
    scheduled_volume = _num(hourly_mpc_schedule.get("scheduled_volume_m3"))
    machine_area = _num(machine_geometry.get("irrigated_area_ha"))
    safe_event_depth = _num(irrigation_capability.get("maximum_safe_depth_mm_event"))
    machine_daily_depth = _num(irrigation_capability.get("maximum_daily_depth_mm"))
    if (
        scheduled_depth is None
        or scheduled_depth < 0
        or scheduled_volume is None
        or scheduled_volume < 0
    ):
        reasons.append("VALID_HOURLY_MPC_WATER_BUDGET_REQUIRED")
    if machine_area is None or machine_area <= 0:
        reasons.append("VALID_MACHINE_GEOMETRY_REQUIRED")
    if (
        safe_event_depth is None
        or safe_event_depth <= 0
        or machine_daily_depth is None
        or machine_daily_depth <= 0
    ):
        reasons.append("VRI_APPLICATION_LIMITS_REQUIRED")
    if not management_zones:
        reasons.append("GOVERNED_MANAGEMENT_ZONES_REQUIRED")
    if len(management_zones) > maximum_zone_count:
        reasons.append("VRI_ZONE_COUNT_LIMIT_EXCEEDED")
    if not (0 <= minimum_application_percent <= maximum_application_percent <= 200):
        reasons.append("VALID_VRI_APPLICATION_PERCENT_RANGE_REQUIRED")
    if reasons:
        return _blocked(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            machine_id=machine_id,
            reasons=reasons,
            source_digests=source_digests,
        )

    assert scheduled_depth is not None and scheduled_volume is not None
    assert (
        machine_area is not None
        and safe_event_depth is not None
        and machine_daily_depth is not None
    )

    if scheduled_depth <= 1e-9 or scheduled_volume <= 1e-9:
        payload = {
            "machine_id": machine_id,
            "decision": "hold",
            "source_digests": source_digests,
        }
        return GovernedVRIPrescription(
            schema_version=SCHEMA_VERSION,
            solver_version=SOLVER_VERSION,
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            machine_id=machine_id,
            status="verified",
            decision="hold",
            recommendation_only=True,
            execution_allowed=False,
            translation_allowed=False,
            planned_uniform_depth_mm=0.0,
            prescribed_average_depth_mm=0.0,
            prescribed_volume_m3=0.0,
            uncovered_budget_mm=0.0,
            zones=[],
            blocking_reasons=[],
            limitations=[],
            source_digests=source_digests,
            prescription_digest=_digest(payload),
        )

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    total_zone_area = 0.0
    for raw_zone in management_zones:
        zone_id = str(raw_zone.get("zone_id") or "").strip()
        area = _num(raw_zone.get("area_ha"))
        start_angle = _num(raw_zone.get("start_angle_deg"))
        end_angle = _num(raw_zone.get("end_angle_deg"))
        inner_radius = _num(raw_zone.get("inner_radius_m"))
        outer_radius = _num(raw_zone.get("outer_radius_m"))
        depletion = _num(raw_zone.get("depletion_mm"))
        raw_mm = _num(raw_zone.get("raw_mm"))
        taw_mm = _num(raw_zone.get("taw_mm"))
        eo_stress = _num(raw_zone.get("eo_stress_score"))
        slope = _num(raw_zone.get("slope_percent"))
        infiltration = _num(raw_zone.get("infiltration_mm_h"))
        zone_max_depth = _num(raw_zone.get("maximum_safe_depth_mm"))
        excluded = raw_zone.get("excluded") is True
        zone_digest = str(raw_zone.get("zone_digest") or "")
        if not zone_id or zone_id in seen_ids:
            reasons.append("UNIQUE_VRI_ZONE_ID_REQUIRED")
            continue
        seen_ids.add(zone_id)
        if not _valid_digest(zone_digest):
            reasons.append("GOVERNED_VRI_ZONE_DIGEST_REQUIRED")
        if area is None or area <= 0:
            reasons.append("VALID_VRI_ZONE_AREA_REQUIRED")
            continue
        if any(value is None for value in (start_angle, end_angle, inner_radius, outer_radius)):
            reasons.append("COMPLETE_VRI_ZONE_GEOMETRY_REQUIRED")
            continue
        assert start_angle is not None and end_angle is not None
        assert inner_radius is not None and outer_radius is not None
        if not (0 <= start_angle < end_angle <= 360) or not (0 <= inner_radius < outer_radius):
            reasons.append("VALID_VRI_ZONE_GEOMETRY_REQUIRED")
            continue
        if (
            depletion is None
            or raw_mm is None
            or taw_mm is None
            or not (0 <= depletion <= taw_mm)
            or not (0 < raw_mm <= taw_mm)
        ):
            reasons.append("VALID_ZONE_ROOT_WATER_STATE_REQUIRED")
            continue
        if eo_stress is None or not (0 <= eo_stress <= 1):
            reasons.append("VALID_ZONE_EO_STRESS_REQUIRED")
            continue
        if slope is None or slope < 0 or infiltration is None or infiltration <= 0:
            reasons.append("VALID_ZONE_TERRAIN_AND_INFILTRATION_REQUIRED")
            continue
        if zone_max_depth is None or zone_max_depth <= 0:
            reasons.append("ZONE_RUNOFF_LIMIT_REQUIRED")
            continue
        total_zone_area += area
        water_urgency = max(0.0, min(1.5, depletion / raw_mm))
        # EO is deliberately secondary; it cannot create irrigation demand where
        # root-zone depletion is absent.
        priority = 0.85 * water_urgency + 0.15 * eo_stress
        # The governed zone_max_depth already incorporates terrain, infiltration
        # and sprinkler runoff analysis from M2.6. Do not apply a second hidden
        # derating here; use those raw values only as evidence validation.
        hard_depth_cap = min(
            safe_event_depth,
            machine_daily_depth,
            zone_max_depth,
            scheduled_depth * maximum_application_percent / 100.0,
        )
        normalized.append(
            {
                "zone_id": zone_id,
                "area_ha": area,
                "start_angle_deg": start_angle,
                "end_angle_deg": end_angle,
                "inner_radius_m": inner_radius,
                "outer_radius_m": outer_radius,
                "depletion_mm": depletion,
                "priority": 0.0 if excluded else priority,
                "excluded": excluded,
                "hard_depth_cap": 0.0 if excluded else max(0.0, hard_depth_cap),
                "zone_digest": zone_digest,
            }
        )

    if machine_area > 0 and total_zone_area > machine_area * 1.01:
        reasons.append("VRI_ZONE_AREA_EXCEEDS_MACHINE_AREA")
    if reasons:
        return _blocked(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            machine_id=machine_id,
            reasons=reasons,
            source_digests=source_digests,
        )

    active = [zone for zone in normalized if not zone["excluded"] and zone["hard_depth_cap"] > 0]
    if not active:
        return _blocked(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            machine_id=machine_id,
            reasons=["NO_ELIGIBLE_VRI_APPLICATION_ZONE"],
            source_digests=source_digests,
        )

    target_volume = min(scheduled_volume, scheduled_depth * machine_area * 10.0)
    remaining_volume = target_volume
    allocations = {zone["zone_id"]: 0.0 for zone in normalized}

    # Water-filling allocation: repeatedly distribute remaining volume by
    # deficit/EO priority while respecting each zone's hard runoff cap.
    candidates = active[:]
    for _ in range(len(candidates) + 1):
        if remaining_volume <= 1e-6 or not candidates:
            break
        weight_sum = sum(max(zone["priority"], 1e-6) * zone["area_ha"] for zone in candidates)
        saturated: list[dict[str, Any]] = []
        distributed = 0.0
        for zone in candidates:
            share = remaining_volume * (max(zone["priority"], 1e-6) * zone["area_ha"]) / weight_sum
            cap_volume = zone["hard_depth_cap"] * zone["area_ha"] * 10.0
            available = max(0.0, cap_volume - allocations[zone["zone_id"]])
            added = min(share, available)
            allocations[zone["zone_id"]] += added
            distributed += added
            if available - added <= 1e-6:
                saturated.append(zone)
        remaining_volume = max(0.0, remaining_volume - distributed)
        candidates = [zone for zone in candidates if zone not in saturated]
        if distributed <= 1e-9:
            break

    max_uniform_reference = max(scheduled_depth, 1e-9)
    prescription_zones: list[VRIPrescriptionZone] = []
    for zone in normalized:
        volume = allocations[zone["zone_id"]]
        depth = volume / (zone["area_ha"] * 10.0) if zone["area_ha"] > 0 else 0.0
        application_percent = 100.0 * depth / max_uniform_reference
        reason_codes: list[str] = []
        if zone["excluded"]:
            application_percent = 0.0
            reason_codes.append("EXCLUDED_ZONE_ZERO_APPLICATION")
        elif depth >= zone["hard_depth_cap"] - 1e-6:
            reason_codes.append("ZONE_APPLICATION_CAPPED_BY_RUNOFF_LIMIT")
        if 0 < application_percent < minimum_application_percent:
            limitations.append("ZONE_BELOW_MACHINE_MINIMUM_APPLICATION_PERCENT")
        if application_percent > maximum_application_percent + 1e-6:
            limitations.append("ZONE_EXCEEDS_MACHINE_MAXIMUM_APPLICATION_PERCENT")
        application_percent = max(0.0, min(maximum_application_percent, application_percent))
        prescription_zones.append(
            VRIPrescriptionZone(
                zone_id=zone["zone_id"],
                area_ha=round(zone["area_ha"], 6),
                start_angle_deg=round(zone["start_angle_deg"], 6),
                end_angle_deg=round(zone["end_angle_deg"], 6),
                inner_radius_m=round(zone["inner_radius_m"], 6),
                outer_radius_m=round(zone["outer_radius_m"], 6),
                target_depth_mm=round(depth, 6),
                target_volume_m3=round(volume, 6),
                application_percent=round(application_percent, 4),
                priority_score=round(zone["priority"], 6),
                source_zone_digest=zone["zone_digest"],
                reason_codes=reason_codes,
            )
        )

    prescribed_volume = sum(zone.target_volume_m3 for zone in prescription_zones)
    prescribed_average_depth = prescribed_volume / (machine_area * 10.0)
    uncovered_budget_mm = max(0.0, (target_volume - prescribed_volume) / (machine_area * 10.0))
    if uncovered_budget_mm > 1e-6:
        limitations.append("VRI_HARD_CAPS_COULD_NOT_ALLOCATE_FULL_MPC_WATER_BUDGET")
    if total_zone_area < machine_area * 0.99:
        limitations.append("VRI_ZONE_COVERAGE_BELOW_MACHINE_AREA")

    status = "verified" if not limitations else "degraded"
    payload = {
        "solver_version": SOLVER_VERSION,
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "machine_id": machine_id,
        "planned_uniform_depth_mm": scheduled_depth,
        "zones": [asdict(zone) for zone in prescription_zones],
        "source_digests": source_digests,
        "limitations": sorted(set(limitations)),
    }
    return GovernedVRIPrescription(
        schema_version=SCHEMA_VERSION,
        solver_version=SOLVER_VERSION,
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        machine_id=machine_id,
        status=status,
        decision="prescribe",
        recommendation_only=True,
        execution_allowed=False,
        translation_allowed=False,
        planned_uniform_depth_mm=round(scheduled_depth, 6),
        prescribed_average_depth_mm=round(prescribed_average_depth, 6),
        prescribed_volume_m3=round(prescribed_volume, 6),
        uncovered_budget_mm=round(uncovered_budget_mm, 6),
        zones=[asdict(zone) for zone in prescription_zones],
        blocking_reasons=[],
        limitations=sorted(set(limitations)),
        source_digests=source_digests,
        prescription_digest=_digest(payload),
    )


def vri_prescription_to_translation_input(
    prescription: GovernedVRIPrescription | dict[str, Any],
) -> dict[str, Any]:
    """Create a non-dispatchable neutral translation input for a later adapter."""
    data = (
        prescription.to_dict()
        if isinstance(prescription, GovernedVRIPrescription)
        else prescription
    )
    if data.get("status") not in {"verified", "degraded"} or data.get("decision") != "prescribe":
        return {
            "status": "blocked",
            "translation_allowed": False,
            "reason": "VERIFIED_VRI_PRESCRIPTION_REQUIRED",
        }
    return {
        "status": "available",
        "schema_version": "neutral_vri_translation_input.v1",
        "machine_id": data.get("machine_id"),
        "zones": data.get("zones", []),
        "prescription_digest": data.get("prescription_digest"),
        "translation_allowed": False,
        "dispatch_allowed": False,
    }
