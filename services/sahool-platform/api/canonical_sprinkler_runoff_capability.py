"""M2.6 governed sprinkler package and runoff capability."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_sprinkler_runoff_capability.v1"
PRODUCT_VERSION = "sprinkler-runoff-capability/1.0.0"


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
class CanonicalSprinklerRunoffCapability:
    schema_version: str
    product_version: str
    tenant_id: str
    project_id: str
    machine_id: str
    package_id: str
    status: str
    operational_eligible: bool
    tested_peak_application_mm_h: float
    adjusted_peak_application_mm_h: float
    infiltration_capacity_mm_h: float
    slope_percent: float
    runoff_safety_factor: float
    runoff_margin_mm_h: float
    maximum_safe_depth_mm_event: float
    wind_derating_factor: float
    evidence: dict[str, Any]
    limitations: list[str]
    blocking_reasons: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_canonical_sprinkler_runoff_capability(
    *,
    tenant_id: str,
    project_id: str,
    machine_capability: dict[str, Any],
    package: dict[str, Any],
    root_zone_profile: dict[str, Any],
    terrain: dict[str, Any],
    weather: dict[str, Any],
) -> CanonicalSprinklerRunoffCapability | dict[str, Any]:
    if machine_capability.get("status") != "verified" or not machine_capability.get(
        "operational_eligible"
    ):
        return {"status": "blocked", "reason": "verified_machine_capability_required"}
    if root_zone_profile.get("status") != "verified" or not root_zone_profile.get(
        "operational_eligible"
    ):
        return {"status": "blocked", "reason": "verified_root_zone_profile_required"}
    package_id = str(package.get("package_id") or package.get("id") or "")
    machine_id = str(machine_capability.get("machine_id") or "")
    if not package_id or str(package.get("certification_status") or "") != "certified":
        return {"status": "blocked", "reason": "certified_sprinkler_package_required"}

    peak = _num(package.get("tested_peak_application_mm_h"))
    infiltration = _num(
        root_zone_profile.get("infiltration_mm_h")
        or root_zone_profile.get("infiltration_capacity_mm_h")
    )
    slope = _num(terrain.get("maximum_slope_percent"))
    wind = _num(weather.get("wind_speed_m_s"))
    max_event = _num(root_zone_profile.get("maximum_safe_event_depth_mm"))
    if any(v is None for v in (peak, infiltration, slope, wind, max_event)):
        return {"status": "blocked", "reason": "complete_runoff_evidence_required"}
    if peak <= 0 or infiltration <= 0 or slope < 0 or wind < 0 or max_event <= 0:
        return {"status": "blocked", "reason": "invalid_runoff_parameters"}

    # Conservative slope factor: 1.0 on flat land, decreasing to 0.5 at 20% slope.
    slope_factor = max(0.5, 1.0 - min(slope, 20.0) * 0.025)
    safe_infiltration = infiltration * slope_factor
    # Wind increases non-uniformity; operational use requires measured weather.
    wind_factor = max(0.75, 1.0 - max(0.0, wind - 2.0) * 0.025)
    adjusted_peak = peak / wind_factor
    safety_factor = safe_infiltration / adjusted_peak
    runoff_margin = safe_infiltration - adjusted_peak
    blockers: list[str] = []
    limitations: list[str] = []
    if package.get("test_quality") not in {"field_validated", "certified"}:
        blockers.append("FIELD_VALIDATED_APPLICATION_TEST_REQUIRED")
    if terrain.get("quality") not in {"field_validated", "certified"}:
        blockers.append("VALIDATED_TERRAIN_PROFILE_REQUIRED")
    if weather.get("quality") not in {"measured", "field_validated", "certified"}:
        blockers.append("CURRENT_WIND_MEASUREMENT_REQUIRED")
    if safety_factor < 1.0:
        blockers.append("RUNOFF_RISK_HIGH")
    if wind >= 8.0:
        blockers.append("SPRINKLER_WIND_LIMIT_EXCEEDED")
    elif wind >= 5.0:
        limitations.append("elevated wind may reduce distribution uniformity")

    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "machine_id": machine_id,
        "package_id": package_id,
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "tested_peak_application_mm_h": round(peak, 6),
        "adjusted_peak_application_mm_h": round(adjusted_peak, 6),
        "infiltration_capacity_mm_h": round(safe_infiltration, 6),
        "slope_percent": round(slope, 6),
        "runoff_safety_factor": round(safety_factor, 6),
        "runoff_margin_mm_h": round(runoff_margin, 6),
        "maximum_safe_depth_mm_event": round(max_event, 6),
        "wind_derating_factor": round(wind_factor, 6),
        "evidence": {
            "machine_capability_digest": machine_capability.get("capability_digest"),
            "package_test_digest": package.get("test_digest"),
            "root_zone_profile_digest": root_zone_profile.get("profile_digest")
            or root_zone_profile.get("capability_digest"),
            "terrain_profile_digest": terrain.get("profile_digest"),
            "weather_snapshot_digest": weather.get("snapshot_digest"),
        },
        "limitations": sorted(set(limitations)),
        "blocking_reasons": sorted(set(blockers)),
    }
    return CanonicalSprinklerRunoffCapability(**base, capability_digest=_digest(base))


def sprinkler_capability_to_mpc_constraints(
    capability: CanonicalSprinklerRunoffCapability | dict[str, Any],
) -> dict[str, Any]:
    data = (
        capability.to_dict()
        if isinstance(capability, CanonicalSprinklerRunoffCapability)
        else capability
    )
    if data.get("status") != "verified" or not data.get("operational_eligible"):
        return {
            "status": "blocked",
            "reason": "canonical_sprinkler_capability_not_operational",
            "blocking_reasons": list(
                data.get("blocking_reasons") or [data.get("reason") or "unknown"]
            ),
        }
    return {
        "status": "available",
        "maximum_safe_depth_mm_event": data["maximum_safe_depth_mm_event"],
        "runoff_safety_factor": data["runoff_safety_factor"],
        "sprinkler_capability_digest": data["capability_digest"],
    }
