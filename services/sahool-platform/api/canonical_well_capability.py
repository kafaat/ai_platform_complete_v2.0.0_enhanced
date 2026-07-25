"""M2.3 canonical water-source and well capability.

Builds an immutable, tenant-bound capability snapshot from commissioned source
limits, a certified pumping test, recent well measurements, water quality, and
water-allocation consumption. Missing or contradictory evidence fails closed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "canonical_well_capability.v1"
PRODUCT_VERSION = "well-capability/1.0.0"
MAX_MEASUREMENT_AGE_HOURS = 24.0
MAX_PUMPING_TEST_AGE_DAYS = 1095.0
MAX_WATER_QUALITY_AGE_DAYS = 365.0

# Canonical fail-closed water-salinity blocking-reason vocabulary. Single source,
# reused by build_canonical_well_capability and the served MPC recommendation path.
WATER_SALINITY_LIMIT_EXCEEDED = "WATER_SALINITY_LIMIT_EXCEEDED"
WATER_QUALITY_REQUIRED = "WATER_QUALITY_REQUIRED"
WATER_QUALITY_STALE = "WATER_QUALITY_STALE"


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _age_hours(value: Any, now: datetime) -> float | None:
    parsed = _timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds() / 3600.0)


@dataclass(frozen=True)
class CanonicalWellCapability:
    schema_version: str
    product_version: str
    tenant_id: str
    project_id: str
    water_source_id: str
    well_id: str
    generated_at: str
    effective_at: str
    status: str
    operational_eligible: bool
    maximum_flow_lps: float
    maximum_daily_volume_m3: float
    remaining_daily_volume_m3: float
    remaining_seasonal_volume_m3: float | None
    static_level_m: float
    dynamic_level_m: float
    drawdown_m: float
    specific_capacity_lps_per_m: float
    recovery_rate_m_h: float | None
    sustainable_flow_lps: float
    water_ec_ds_m: float | None
    maximum_allowed_ec_ds_m: float | None
    minimum_rest_hours: float
    measurement_age_hours: float
    pumping_test_age_days: float
    water_quality_age_days: float | None
    evidence: dict[str, Any]
    limitations: list[str]
    blocking_reasons: list[str]
    capability_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_water_salinity_gate(
    *,
    maximum_allowed_ec_ds_m: Any,
    water_quality: dict[str, Any] | None,
    now: datetime | None = None,
    max_sample_age_days: float = MAX_WATER_QUALITY_AGE_DAYS,
) -> dict[str, Any]:
    """Fail-closed water-salinity verdict bound to a water source.

    The single source of the H5 EC rule: reused by build_canonical_well_capability
    and by the served MPC recommendation path once ECw is bound to a
    water_source_id. Returns ``status`` clear|blocked with the canonical
    blocking-reason vocabulary. A configured ``maximum_allowed_ec_ds_m`` with no
    sample fails closed (WATER_QUALITY_REQUIRED); a measured ECw above the limit
    fails closed (WATER_SALINITY_LIMIT_EXCEEDED); a stale sample warns
    (WATER_QUALITY_STALE). No configured maximum ⇒ no limit to enforce ⇒ clear.
    """
    now = now or datetime.now(UTC)
    maximum_ec = _number(maximum_allowed_ec_ds_m)
    water_ec: float | None = None
    quality_age_days: float | None = None
    blockers: list[str] = []
    limitations: list[str] = []
    if water_quality:
        water_ec = _number(water_quality.get("ec_ds_m"))
        quality_age_h = _age_hours(water_quality.get("sampled_at"), now)
        quality_age_days = None if quality_age_h is None else quality_age_h / 24.0
        if quality_age_days is None:
            limitations.append("water quality timestamp invalid")
        elif quality_age_days > max_sample_age_days:
            blockers.append(WATER_QUALITY_STALE)
        if maximum_ec is not None and water_ec is not None and water_ec > maximum_ec:
            blockers.append(WATER_SALINITY_LIMIT_EXCEEDED)
    else:
        limitations.append("water quality sample missing")
        if maximum_ec is not None:
            blockers.append(WATER_QUALITY_REQUIRED)
    return {
        "status": "blocked" if blockers else "clear",
        "blocking_reasons": sorted(set(blockers)),
        "limitations": limitations,
        "water_ec_ds_m": water_ec,
        "maximum_allowed_ec_ds_m": maximum_ec,
        "water_quality_age_days": quality_age_days,
    }


def build_canonical_well_capability(
    *,
    tenant_id: str,
    project_id: str,
    water_source: dict[str, Any],
    well: dict[str, Any],
    pumping_test: dict[str, Any],
    latest_measurement: dict[str, Any],
    allocation: dict[str, Any],
    water_quality: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> CanonicalWellCapability | dict[str, Any]:
    """Build a capability snapshot, returning a blocked payload on invalid truth."""
    now = now or datetime.now(UTC)
    source_id = str(water_source.get("water_source_id") or water_source.get("id") or "")
    well_id = str(well.get("well_id") or well.get("id") or "")
    if not source_id or not well_id:
        return {"status": "blocked", "reason": "water_source_or_well_identity_missing"}
    if str(well.get("water_source_id") or source_id) != source_id:
        return {"status": "blocked", "reason": "well_water_source_mismatch"}

    test_status = str(pumping_test.get("status") or "")
    if test_status != "certified":
        return {"status": "blocked", "reason": "certified_pumping_test_required"}

    static_level = _number(latest_measurement.get("static_level_m"))
    dynamic_level = _number(latest_measurement.get("dynamic_level_m"))
    if (
        static_level is None
        or dynamic_level is None
        or static_level < 0
        or dynamic_level <= static_level
    ):
        return {"status": "blocked", "reason": "invalid_static_or_dynamic_water_level"}
    drawdown = dynamic_level - static_level

    tested_flow = _number(pumping_test.get("tested_flow_lps"))
    recommended_flow = _number(pumping_test.get("recommended_sustainable_flow_lps"))
    well_sustainable_flow = _number(well.get("sustainable_flow_lps"))
    source_flow = _number(
        water_source.get("commissioned_max_flow_lps")
        if water_source.get("commissioned_max_flow_lps") is not None
        else water_source.get("design_max_flow_lps")
    )
    if tested_flow is None or tested_flow <= 0:
        return {"status": "blocked", "reason": "positive_tested_flow_required"}
    if recommended_flow is None or recommended_flow <= 0:
        return {"status": "blocked", "reason": "certified_sustainable_flow_required"}

    candidates = [recommended_flow, tested_flow]
    if well_sustainable_flow is not None and well_sustainable_flow > 0:
        candidates.append(well_sustainable_flow)
    if source_flow is not None and source_flow > 0:
        candidates.append(source_flow)
    sustainable_flow = min(candidates)

    measured_at = latest_measurement.get("measured_at")
    measurement_age_h = _age_hours(measured_at, now)
    if measurement_age_h is None:
        return {"status": "blocked", "reason": "well_measurement_timestamp_required"}
    tested_at = pumping_test.get("tested_at")
    pumping_test_age_h = _age_hours(tested_at, now)
    if pumping_test_age_h is None:
        return {"status": "blocked", "reason": "pumping_test_timestamp_required"}
    pumping_test_age_days = pumping_test_age_h / 24.0

    daily_allocation = _number(allocation.get("daily_allocation_m3"))
    daily_used = _number(allocation.get("daily_used_m3")) or 0.0
    seasonal_allocation = _number(allocation.get("seasonal_allocation_m3"))
    seasonal_used = _number(allocation.get("seasonal_used_m3")) or 0.0
    if daily_allocation is None or daily_allocation < 0 or daily_used < 0:
        return {"status": "blocked", "reason": "valid_daily_water_allocation_required"}
    remaining_daily = max(0.0, daily_allocation - daily_used)
    remaining_seasonal = None
    if seasonal_allocation is not None:
        if seasonal_allocation < 0 or seasonal_used < 0:
            return {"status": "blocked", "reason": "invalid_seasonal_water_allocation"}
        remaining_seasonal = max(0.0, seasonal_allocation - seasonal_used)

    # Convert the remaining legal daily volume into an average 24-hour flow cap.
    allocation_flow_cap = remaining_daily / 86.4
    maximum_flow = min(sustainable_flow, allocation_flow_cap)

    min_rest_hours = _number(well.get("minimum_rest_hours")) or 0.0
    recovery_rate = _number(pumping_test.get("recovery_rate_m_h"))
    max_drawdown = _number(well.get("maximum_drawdown_m"))
    limitations: list[str] = []
    blockers: list[str] = []
    if measurement_age_h > MAX_MEASUREMENT_AGE_HOURS:
        blockers.append("WELL_MEASUREMENT_STALE")
    if pumping_test_age_days > MAX_PUMPING_TEST_AGE_DAYS:
        blockers.append("PUMPING_TEST_STALE")
    if max_drawdown is not None and drawdown > max_drawdown:
        blockers.append("DRAWDOWN_LIMIT_EXCEEDED")
    if remaining_daily <= 0:
        blockers.append("DAILY_WATER_ALLOCATION_EXHAUSTED")
    if remaining_seasonal is not None and remaining_seasonal <= 0:
        blockers.append("SEASONAL_WATER_ALLOCATION_EXHAUSTED")

    salinity_gate = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=water_source.get("maximum_allowed_ec_ds_m"),
        water_quality=water_quality,
        now=now,
    )
    water_ec = salinity_gate["water_ec_ds_m"]
    maximum_ec = salinity_gate["maximum_allowed_ec_ds_m"]
    quality_age_days = salinity_gate["water_quality_age_days"]
    blockers.extend(salinity_gate["blocking_reasons"])
    limitations.extend(salinity_gate["limitations"])

    if recovery_rate is None or recovery_rate <= 0:
        limitations.append("recovery rate not certified")
    if maximum_flow <= 0:
        blockers.append("NO_LEGAL_SUSTAINABLE_FLOW_AVAILABLE")

    evidence = {
        "water_source_evidence": water_source.get("evidence") or {},
        "well_evidence": well.get("evidence") or {},
        "pumping_test_id": str(pumping_test.get("pumping_test_id") or pumping_test.get("id") or ""),
        "measurement_id": str(
            latest_measurement.get("measurement_id") or latest_measurement.get("id") or ""
        ),
        "allocation_id": str(allocation.get("allocation_id") or allocation.get("id") or ""),
        "water_quality_sample_id": str(
            (water_quality or {}).get("sample_id") or (water_quality or {}).get("id") or ""
        ),
    }
    effective_at = str(measured_at)
    base = {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "water_source_id": source_id,
        "well_id": well_id,
        "generated_at": now.isoformat(),
        "effective_at": effective_at,
        "status": "verified" if not blockers else "blocked",
        "operational_eligible": not blockers,
        "maximum_flow_lps": round(maximum_flow, 6),
        "maximum_daily_volume_m3": round(daily_allocation, 4),
        "remaining_daily_volume_m3": round(remaining_daily, 4),
        "remaining_seasonal_volume_m3": None
        if remaining_seasonal is None
        else round(remaining_seasonal, 4),
        "static_level_m": round(static_level, 4),
        "dynamic_level_m": round(dynamic_level, 4),
        "drawdown_m": round(drawdown, 4),
        "specific_capacity_lps_per_m": round(tested_flow / drawdown, 6),
        "recovery_rate_m_h": None if recovery_rate is None else round(recovery_rate, 4),
        "sustainable_flow_lps": round(sustainable_flow, 6),
        "water_ec_ds_m": water_ec,
        "maximum_allowed_ec_ds_m": maximum_ec,
        "minimum_rest_hours": round(min_rest_hours, 4),
        "measurement_age_hours": round(measurement_age_h, 4),
        "pumping_test_age_days": round(pumping_test_age_days, 4),
        "water_quality_age_days": None if quality_age_days is None else round(quality_age_days, 4),
        "evidence": evidence,
        "limitations": limitations,
        "blocking_reasons": sorted(set(blockers)),
    }
    return CanonicalWellCapability(**base, capability_digest=_digest(base))


def well_capability_to_mpc_constraints(
    capability: CanonicalWellCapability | dict[str, Any],
) -> dict[str, Any]:
    """Translate the governed capability into fail-closed MPC constraints."""
    data = capability.to_dict() if isinstance(capability, CanonicalWellCapability) else capability
    if data.get("status") != "verified" or not data.get("operational_eligible"):
        return {
            "status": "blocked",
            "reason": "canonical_well_capability_not_operational",
            "blocking_reasons": list(
                data.get("blocking_reasons") or [data.get("reason") or "unknown"]
            ),
        }
    return {
        "status": "available",
        "source_well_id": data["well_id"],
        "maximum_source_flow_lps": data["maximum_flow_lps"],
        "remaining_daily_volume_m3": data["remaining_daily_volume_m3"],
        "remaining_seasonal_volume_m3": data["remaining_seasonal_volume_m3"],
        "minimum_rest_hours": data["minimum_rest_hours"],
        "well_capability_digest": data["capability_digest"],
    }
