"""Fail-closed deterministic comparison of explicit economic scenarios.

This core performs no I/O and invents no prices, yields, or costs. A scenario is
comparable only when every required quantity/price pair is explicitly provided.
Numeric zero is data; ``None`` is absence.

A partially specified scenario is reported ``not_evaluated`` with its missing inputs
named, and is never ranked against a complete one — ranking a scenario that omitted its
fertiliser cost against one that declared it would flatter the incomplete scenario purely
because a cost was absent.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from api.economic_state import economic_state

SCHEMA_VERSION = "economic_scenario_comparison.v2"

STATUS_EVALUATED = "evaluated"
STATUS_NOT_EVALUATED = "not_evaluated"

_REQUIRED_INPUTS = (
    "expected_yield_t_ha",
    "crop_price_per_t",
    "irrigation_m3_ha",
    "water_price_per_m3",
    "energy_kwh_ha",
    "energy_price_per_kwh",
    "fertilizer_kg_ha",
    "fertilizer_price_per_kg",
)


def _validated_inputs(inputs: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Split inputs into usable values and named absences.

    Absence is reported, never defaulted. A malformed value raises instead, because
    quietly discarding it would make a caller error indistinguishable from an omission.
    """
    values: dict[str, float] = {}
    limitations: list[str] = []
    for key in _REQUIRED_INPUTS:
        raw = inputs.get(key)
        if raw is None:
            limitations.append(f"{key}_missing")
            continue
        if isinstance(raw, bool):
            raise ValueError(f"{key} must be a finite non-negative number")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be a finite non-negative number") from exc
        if not isfinite(value) or value < 0:
            raise ValueError(f"{key} must be a finite non-negative number")
        values[key] = value
    return values, limitations


def _evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    values, limitations = _validated_inputs(inputs)
    if limitations:
        return {
            "status": STATUS_NOT_EVALUATED,
            "state": None,
            "roi_pct": None,
            "limitations": limitations,
        }

    state = economic_state(**values)
    total_cost = state["total_cost"]
    margin = state["expected_margin"]
    roi_pct = None
    scenario_limitations: list[str] = []
    if total_cost is not None and total_cost > 0 and margin is not None:
        roi_pct = round((margin / total_cost) * 100.0, 2)
    elif total_cost == 0:
        # Zero cost is real data, but ROI has no denominator — say so rather than
        # emit an infinite or invented percentage.
        scenario_limitations.append("roi_undefined_zero_total_cost")
    return {
        "status": STATUS_EVALUATED,
        "state": state,
        "roi_pct": roi_pct,
        "limitations": scenario_limitations,
    }


def compare_economic_scenarios(
    *, baseline: dict[str, Any], alternatives: list[dict[str, Any]], currency: str
) -> dict[str, Any]:
    """Compare a baseline and alternatives without coercing missing money to zero."""
    normalized_currency = currency.strip().upper() if isinstance(currency, str) else ""
    if not normalized_currency:
        raise ValueError("currency is required")
    if not alternatives:
        raise ValueError("at least one alternative scenario is required")

    baseline_result = _evaluate(baseline)
    rows: list[dict[str, Any]] = []
    for index, inputs in enumerate(alternatives):
        scenario_id = str(inputs.get("scenario_id") or f"scenario-{index + 1}")
        result = _evaluate({k: v for k, v in inputs.items() if k != "scenario_id"})
        delta = None
        if baseline_result["status"] == STATUS_EVALUATED and result["status"] == STATUS_EVALUATED:
            base_margin = baseline_result["state"]["expected_margin"]
            scenario_margin = result["state"]["expected_margin"]
            if base_margin is not None and scenario_margin is not None:
                delta = round(scenario_margin - base_margin, 2)
        rows.append(
            {
                "scenario_id": scenario_id,
                **result,
                "margin_delta": delta,
                "comparable": delta is not None,
            }
        )

    ranked = sorted(
        (row for row in rows if row["comparable"]),
        key=lambda row: row["margin_delta"],
        reverse=True,
    )
    evaluated_count = int(baseline_result["status"] == STATUS_EVALUATED) + sum(
        row["status"] == STATUS_EVALUATED for row in rows
    )
    total_count = 1 + len(rows)
    coverage = round(evaluated_count / total_count, 4)
    limitations: list[str] = []
    if not ranked:
        limitations.append("no_fully_comparable_scenario")
    if coverage < 1.0:
        limitations.append("incomplete_assessment_coverage")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_EVALUATED if ranked else STATUS_NOT_EVALUATED,
        "currency": normalized_currency,
        "baseline": baseline_result,
        "alternatives": rows,
        "best_comparable_scenario_id": ranked[0]["scenario_id"] if ranked else None,
        "assessment_coverage": coverage,
        "limitations": limitations,
    }
