from __future__ import annotations

import math
from typing import Any

_SCHEMA = "crop_water_state.v1"
_FORMULA_VERSION = "crop-water-demand/1.0.0"


def _finite_non_negative(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        return None
    return value


def build_crop_water_state(
    *,
    et0_mm: float | None,
    crop_coefficient: float | None,
    depletion_mm: float | None,
    raw_mm: float | None,
    root_depth_m: float | None,
    policy_version: str | None,
    et0_method: str | None = None,
    et0_quality_status: str | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Interpret crop water demand from canonical products.

    This product never computes ET0 and never advances a water ledger. It only
    combines an upstream ET0 product with an explicit, versioned crop Kc policy
    and existing water/root state.
    """
    et0 = _finite_non_negative(et0_mm)
    kc = _finite_non_negative(crop_coefficient)
    depletion = _finite_non_negative(depletion_mm)
    raw = _finite_non_negative(raw_mm)
    root_depth = _finite_non_negative(root_depth_m)

    missing: list[str] = []
    if et0 is None:
        missing.append("et0_mm")
    if kc is None:
        missing.append("crop_coefficient")
    if not policy_version:
        missing.append("policy_version")

    evidence_ids = list(dict.fromkeys(source_ids or []))
    if missing:
        return {
            "schema": _SCHEMA,
            "status": "unavailable",
            "crop_et_mm": None,
            "irrigation_urgency": "unknown",
            "policy_version": policy_version,
            "formula_version": _FORMULA_VERSION,
            "evidence_ids": evidence_ids,
            "evidence_missing": missing,
            "limitations": ["crop_water_demand_requires_canonical_et0_and_versioned_kc"],
        }

    crop_et = et0 * kc
    urgency = "unknown"
    depletion_fraction = None
    if depletion is not None and raw is not None and raw > 0:
        depletion_fraction = depletion / raw
        if depletion_fraction >= 1.0:
            urgency = "high"
        elif depletion_fraction >= 0.75:
            urgency = "medium"
        else:
            urgency = "low"

    quality_status = "validated"
    limitations: list[str] = []
    if et0_quality_status in {"degraded", "estimated", "inconsistent_inputs"}:
        quality_status = "degraded"
        limitations.append("upstream_et0_quality_is_degraded")
    if depletion is None or raw is None:
        quality_status = "degraded"
        limitations.append("irrigation_urgency_unavailable_without_water_state")

    return {
        "schema": _SCHEMA,
        "status": "available" if quality_status == "validated" else "degraded",
        "crop_et_mm": round(crop_et, 3),
        "et0_mm": round(et0, 3),
        "crop_coefficient": round(kc, 4),
        "depletion_mm": round(depletion, 3) if depletion is not None else None,
        "raw_mm": round(raw, 3) if raw is not None else None,
        "depletion_to_raw_ratio": (
            round(depletion_fraction, 4) if depletion_fraction is not None else None
        ),
        "root_depth_m": round(root_depth, 3) if root_depth is not None else None,
        "irrigation_urgency": urgency,
        "et0_method": et0_method,
        "et0_quality_status": et0_quality_status,
        "policy_version": policy_version,
        "formula_version": _FORMULA_VERSION,
        "unit": "mm/day",
        "quality_status": quality_status,
        "evidence_ids": evidence_ids,
        "evidence_missing": [],
        "limitations": limitations,
        "ownership": {
            "et0": "weather-service",
            "water_ledger": "water-ledger/irrigation domain",
            "crop_coefficient_policy": "crop-intelligence-engine",
        },
    }
