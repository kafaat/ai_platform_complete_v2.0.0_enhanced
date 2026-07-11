from __future__ import annotations

import math
from typing import Any

_SCHEMA = "crop_phenology_state.v1"
_PRODUCT_VERSION = "crop-phenology/1.0.0"
_STAGE_FRACTIONS = (("initial", 0.20), ("development", 0.30), ("mid", 0.30), ("late", 0.20))


def _finite_non_negative(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def build_phenology_state(
    *,
    gdd_cumulative: float | None,
    gdd_to_maturity: float | None,
    method: str | None,
    formula_version: str | None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Interpret an already-computed canonical GDD product into crop stages."""
    gdd = _finite_non_negative(gdd_cumulative)
    maturity = _finite_non_negative(gdd_to_maturity)
    if gdd is None or maturity in (None, 0):
        return {
            "schema": _SCHEMA,
            "product_version": _PRODUCT_VERSION,
            "status": "unavailable",
            "gdd_cumulative": gdd,
            "gdd_to_maturity": maturity,
            "progress": None,
            "current_stage": None,
            "stage": None,
            "previous_stage": None,
            "next_stage": None,
            "next_stage_gdd": None,
            "past_maturity": None,
            "method": method,
            "formula_version": formula_version,
            "evidence_ids": list(dict.fromkeys(source_ids or [])),
            "limitations": ["canonical_gdd_or_maturity_threshold_missing"],
        }

    raw_progress = gdd / maturity
    progress = min(1.0, raw_progress)
    cumulative = 0.0
    current_index = len(_STAGE_FRACTIONS) - 1
    next_threshold = maturity
    for index, (_, fraction) in enumerate(_STAGE_FRACTIONS):
        cumulative += fraction
        if progress <= cumulative:
            current_index = index
            next_threshold = cumulative * maturity
            break

    current = _STAGE_FRACTIONS[current_index][0]
    previous = _STAGE_FRACTIONS[current_index - 1][0] if current_index > 0 else None
    next_stage = (
        _STAGE_FRACTIONS[current_index + 1][0]
        if current_index + 1 < len(_STAGE_FRACTIONS) and gdd < maturity
        else None
    )
    return {
        "schema": _SCHEMA,
        "product_version": _PRODUCT_VERSION,
        "status": "available",
        "gdd_cumulative": round(gdd, 4),
        "gdd_to_maturity": round(maturity, 4),
        "progress": round(progress, 4),
        "current_stage": current,
        "stage": current,
        "previous_stage": previous,
        "next_stage": next_stage,
        "next_stage_gdd": round(next_threshold, 4) if next_stage is not None else None,
        "past_maturity": gdd >= maturity,
        "method": method,
        "formula_version": formula_version,
        "evidence_ids": list(dict.fromkeys(source_ids or [])),
        "limitations": [],
    }
