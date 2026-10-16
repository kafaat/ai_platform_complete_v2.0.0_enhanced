"""Mass-basis conversion for reviewed recipe inputs, with no execution decision."""

from __future__ import annotations

import math

# Atomic mass ratios, rounded consistently with the existing agronomic contract.
P2O5_TO_P = 0.4364
K2O_TO_K = 0.8301


def p_from_p2o5(kg_p2o5: float) -> float:
    return kg_p2o5 * P2O5_TO_P


def k_from_k2o(kg_k2o: float) -> float:
    return kg_k2o * K2O_TO_K


def p2o5_from_p(kg_p: float) -> float:
    return kg_p / P2O5_TO_P


def k2o_from_k(kg_k: float) -> float:
    return kg_k / K2O_TO_K


def recipe_elemental_input(rate: float, unit: str) -> dict:
    """Convert only an explicit nutrient mass per area, never product mass or water.

    kg/ha cannot determine mg/L without an approved injection-window water volume.
    Retain that unknown and the original basis; conversion is not agronomic approval.
    """
    conversions = {
        "kgP2O5/ha": ("P", p_from_p2o5),
        "kgK2O/ha": ("K", k_from_k2o),
        "kgN/ha": ("N", float),
        "kgP/ha": ("P", float),
        "kgK/ha": ("K", float),
    }
    if unit not in conversions:
        raise ValueError("explicit nutrient mass basis required")
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate < 0
    ):
        raise ValueError("nutrient rate must be finite and nonnegative")
    element, convert = conversions[unit]
    return {
        "source_rate": rate,
        "source_unit": unit,
        "element": element,
        "elemental_rate_kg_ha": convert(rate),
        "concentration_mg_l": None,
        "execution_authorized": False,
        "requires_agronomist_review": True,
    }
