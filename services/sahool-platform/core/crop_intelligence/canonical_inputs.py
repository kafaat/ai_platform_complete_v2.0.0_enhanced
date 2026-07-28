"""CI-7 canonical input adapters for Crop Intelligence.

This module is intentionally interpretation-only: it reads governed State Products and
never recomputes weather, water, soil, or spectral science.
"""

from __future__ import annotations

import math
from typing import Any

from core.crop_cards.loader import load_crop_card

CANONICAL_WEATHER_PRODUCT_ID = "canonical_weather_state"


def _finite_non_negative(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def resolve_phenology_inputs(
    *,
    crop: str | None,
    weather_state: dict[str, Any] | None,
    legacy_gdd_cumulative: float | None,
    legacy_gdd_to_maturity: float | None,
) -> dict[str, Any]:
    """Resolve GDD exclusively from CanonicalWeatherState when it is supplied.

    Legacy scalar fields remain a compatibility bridge only when no canonical weather
    state is present. A malformed canonical state fails closed instead of falling back.
    The maturity threshold is crop knowledge, so it is read from the versioned crop card
    when the caller does not supply a threshold.
    """
    state = dict(weather_state or {})
    limitations: list[str] = []
    evidence_ids: list[str] = []

    maturity = _finite_non_negative(legacy_gdd_to_maturity)
    if maturity is None and crop:
        card = load_crop_card(crop)
        maturity = _finite_non_negative((card or {}).get("thermal", {}).get("gdd_to_maturity"))
        if maturity is not None:
            limitations.append("gdd_to_maturity_resolved_from_versioned_crop_knowledge")

    if state:
        if state.get("product_id") != CANONICAL_WEATHER_PRODUCT_ID:
            return {
                "gdd_cumulative": None,
                "gdd_to_maturity": maturity,
                "method": None,
                "formula_version": None,
                "evidence_ids": evidence_ids,
                "limitations": [*limitations, "weather_state_is_not_canonical_weather_state"],
                "source": "canonical_weather_state_invalid",
            }
        availability = state.get("availability") or {}
        product = (state.get("products") or {}).get("gdd") or {}
        if availability.get("gdd") is not True:
            return {
                "gdd_cumulative": None,
                "gdd_to_maturity": maturity,
                "method": None,
                "formula_version": None,
                "evidence_ids": evidence_ids,
                "limitations": [*limitations, "canonical_weather_gdd_unavailable"],
                "source": "canonical_weather_state",
            }
        cumulative = _finite_non_negative(product.get("accumulated_gdd"))
        if state.get("state_id"):
            evidence_ids.append(str(state["state_id"]))
        if state.get("source_snapshot_id"):
            evidence_ids.append(str(state["source_snapshot_id"]))
        return {
            "gdd_cumulative": cumulative,
            "gdd_to_maturity": maturity,
            "method": (product.get("thresholds_used") or {}).get("method")
            or "canonical_weather_gdd",
            "formula_version": product.get("calculation_version") or product.get("formula_version"),
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "limitations": [*limitations, *(product.get("limitations") or [])],
            "source": "canonical_weather_state",
        }

    limitations.append("legacy_gdd_scalar_compatibility_bridge")
    return {
        "gdd_cumulative": _finite_non_negative(legacy_gdd_cumulative),
        "gdd_to_maturity": maturity,
        "method": None,
        "formula_version": None,
        "evidence_ids": [],
        "limitations": limitations,
        "source": "legacy_scalar_compatibility",
    }
