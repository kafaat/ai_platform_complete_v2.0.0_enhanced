from __future__ import annotations

import math
from typing import Any

_SCHEMA = "crop_root_state.v1"
_PRODUCT_VERSION = "crop-roots/1.0.0"


def _finite_positive(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def build_root_state(
    *,
    phenology_progress: float | None,
    initial_depth_m: float | None,
    maximum_depth_m: float | None,
    effective_fraction: float = 0.8,
    policy_version: str | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Project root depth from an explicit, versioned crop policy.

    No generic crop values are fabricated. Without a valid policy this product is
    unavailable. Growth is bounded linear interpolation over phenology progress.
    """
    start = _finite_positive(initial_depth_m)
    maximum = _finite_positive(maximum_depth_m)
    progress = (
        float(phenology_progress)
        if isinstance(phenology_progress, (int, float))
        and not isinstance(phenology_progress, bool)
        and math.isfinite(float(phenology_progress))
        else None
    )
    if (
        start is None
        or maximum is None
        or maximum < start
        or progress is None
        or not 0 <= progress <= 1
        or not policy_version
    ):
        return {
            "schema": _SCHEMA,
            "product_version": _PRODUCT_VERSION,
            "status": "unavailable",
            "current_depth_m": None,
            "effective_root_zone_m": None,
            "maximum_depth_m": maximum,
            "growth_fraction": None,
            "policy_version": policy_version,
            "evidence_ids": list(dict.fromkeys(source_ids or [])),
            "limitations": ["validated_root_policy_and_phenology_required"],
        }

    fraction = min(1.0, max(0.0, progress))
    current = start + (maximum - start) * fraction
    effective = current * min(1.0, max(0.0, effective_fraction))
    return {
        "schema": _SCHEMA,
        "product_version": _PRODUCT_VERSION,
        "status": "available",
        "current_depth_m": round(current, 4),
        "effective_root_zone_m": round(effective, 4),
        "maximum_depth_m": round(maximum, 4),
        "growth_fraction": round(fraction, 4),
        "policy_version": policy_version,
        "evidence_ids": list(dict.fromkeys(source_ids or [])),
        "limitations": [],
    }
