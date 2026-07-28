"""Deterministic scenario comparison over api.economic_state outputs."""

from __future__ import annotations

from typing import Any

from api.economic_state import economic_state

SCHEMA_VERSION = "economic_scenario_comparison.v1"


def compare_economic_scenarios(
    *, baseline: dict[str, Any], alternatives: list[dict[str, Any]], currency: str
) -> dict[str, Any]:
    if not currency:
        raise ValueError("currency is required")
    base = economic_state(**baseline)
    rows = []
    for i, inputs in enumerate(alternatives):
        economic_inputs = {k: v for k, v in inputs.items() if k != "scenario_id"}
        state = economic_state(**economic_inputs)
        delta = None
        if base["expected_margin"] is not None and state["expected_margin"] is not None:
            delta = round(state["expected_margin"] - base["expected_margin"], 2)
        rows.append(
            {
                "scenario_id": str(inputs.get("scenario_id") or f"scenario-{i + 1}"),
                "state": state,
                "margin_delta": delta,
                "comparable": delta is not None,
            }
        )
    ranked = sorted(
        (r for r in rows if r["comparable"]), key=lambda r: r["margin_delta"], reverse=True
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "currency": currency,
        "baseline": base,
        "alternatives": rows,
        "best_comparable_scenario_id": ranked[0]["scenario_id"] if ranked else None,
        "limitations": [] if ranked else ["no_fully_comparable_scenario"],
    }
