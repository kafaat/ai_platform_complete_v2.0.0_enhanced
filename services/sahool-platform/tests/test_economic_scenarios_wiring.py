"""economic_scenarios: fail-closed comparison + its production consumer.

The danger in scenario comparison is not a wrong number, it is a *flattering* one. If a
scenario omits its fertiliser cost and the comparison treats absence as zero, that scenario
wins on margin purely because a cost was never declared. So an incomplete scenario is
reported ``not_evaluated`` and is never ranked against a complete one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from core.economic_scenarios import (
    SCHEMA_VERSION,
    STATUS_EVALUATED,
    STATUS_NOT_EVALUATED,
    compare_economic_scenarios,
)

pytestmark = pytest.mark.unit

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "scenario.py"

COMPLETE = {
    "expected_yield_t_ha": 5.0,
    "crop_price_per_t": 100.0,
    "irrigation_m3_ha": 100.0,
    "water_price_per_m3": 1.0,
    "energy_kwh_ha": 10.0,
    "energy_price_per_kwh": 2.0,
    "fertilizer_kg_ha": 10.0,
    "fertilizer_price_per_kg": 3.0,
}


def _compare(alternatives, baseline=None, currency="YER"):
    return compare_economic_scenarios(
        baseline=baseline if baseline is not None else dict(COMPLETE),
        alternatives=alternatives,
        currency=currency,
    )


# ── the failure this core exists to prevent ─────────────────────────────────
def test_a_scenario_missing_a_cost_is_never_ranked_as_best():
    """Omitting a cost must not buy a scenario a better margin."""
    cheating = {k: v for k, v in COMPLETE.items() if k != "fertilizer_price_per_kg"}
    cheating["scenario_id"] = "omits-fertilizer-cost"
    honest = {**COMPLETE, "scenario_id": "declares-everything", "expected_yield_t_ha": 5.1}

    result = _compare([cheating, honest])
    assert result["best_comparable_scenario_id"] == "declares-everything"

    omitted = next(r for r in result["alternatives"] if r["scenario_id"] == "omits-fertilizer-cost")
    assert omitted["status"] == STATUS_NOT_EVALUATED
    assert omitted["comparable"] is False
    assert omitted["margin_delta"] is None
    assert "fertilizer_price_per_kg_missing" in omitted["limitations"]


def test_every_missing_input_is_named_not_merely_counted():
    partial = {"expected_yield_t_ha": 5.0, "scenario_id": "sparse"}
    row = _compare([partial])["alternatives"][0]
    assert row["status"] == STATUS_NOT_EVALUATED
    assert "crop_price_per_t_missing" in row["limitations"]
    assert "fertilizer_kg_ha_missing" in row["limitations"]
    assert row["state"] is None


def test_incomplete_baseline_makes_nothing_comparable():
    """A baseline that cannot be evaluated cannot anchor any delta."""
    incomplete_baseline = {k: v for k, v in COMPLETE.items() if k != "crop_price_per_t"}
    result = _compare([{**COMPLETE, "scenario_id": "s1"}], baseline=incomplete_baseline)
    assert result["baseline"]["status"] == STATUS_NOT_EVALUATED
    assert result["status"] == STATUS_NOT_EVALUATED
    assert result["best_comparable_scenario_id"] is None
    assert "no_fully_comparable_scenario" in result["limitations"]


# ── zero is data, absence is not ────────────────────────────────────────────
def test_zero_cost_is_evaluated_not_treated_as_missing():
    free_water = {**COMPLETE, "water_price_per_m3": 0.0, "scenario_id": "free-water"}
    row = _compare([free_water])["alternatives"][0]
    assert row["status"] == STATUS_EVALUATED
    assert row["limitations"] == []


def test_zero_total_cost_reports_undefined_roi_rather_than_infinity():
    free = dict.fromkeys(COMPLETE, 0.0)
    free["expected_yield_t_ha"] = 5.0
    free["crop_price_per_t"] = 100.0
    row = _compare([{**free, "scenario_id": "costless"}])["alternatives"][0]
    assert row["status"] == STATUS_EVALUATED
    assert row["roi_pct"] is None
    assert "roi_undefined_zero_total_cost" in row["limitations"]


# ── malformed input is a caller error, not an omission ──────────────────────
@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), True, "abc"])
def test_malformed_values_raise_instead_of_being_dropped(bad):
    """Silently discarding a bad value would be indistinguishable from an omission."""
    with pytest.raises(ValueError):
        _compare([{**COMPLETE, "crop_price_per_t": bad, "scenario_id": "bad"}])


def test_currency_and_alternatives_are_required():
    with pytest.raises(ValueError):
        _compare([{**COMPLETE, "scenario_id": "s"}], currency="   ")
    with pytest.raises(ValueError):
        _compare([])


# ── coverage is reported, never folded into the verdict ─────────────────────
def test_coverage_reports_the_shortfall_without_hiding_it():
    result = _compare(
        [
            {**COMPLETE, "scenario_id": "complete"},
            {"expected_yield_t_ha": 5.0, "scenario_id": "partial"},
        ]
    )
    assert result["assessment_coverage"] == round(2 / 3, 4)
    assert "incomplete_assessment_coverage" in result["limitations"]
    # A usable answer still exists — the shortfall is disclosed, not fatal.
    assert result["best_comparable_scenario_id"] == "complete"


def test_full_coverage_carries_no_shortfall_limitation():
    result = _compare([{**COMPLETE, "scenario_id": "s1", "expected_yield_t_ha": 6.0}])
    assert result["assessment_coverage"] == 1.0
    assert result["limitations"] == []
    assert result["schema_version"] == SCHEMA_VERSION


def test_currency_is_normalised_not_invented():
    assert _compare([{**COMPLETE, "scenario_id": "s"}], currency=" yer ")["currency"] == "YER"


# ── the production consumer ─────────────────────────────────────────────────
def test_router_consumes_the_core():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "core.economic_scenarios"
        for alias in node.names
    }
    assert "compare_economic_scenarios" in imported


def test_route_is_registered_in_the_ownership_map_at_its_real_line():
    """A route that exists in code but not in the map is an undeclared surface."""
    import json

    repo = Path(__file__).resolve().parents[3]
    doc = json.loads(
        (repo / "docs/architecture/platform_extraction_map.json").read_text(encoding="utf-8")
    )
    entry = next(row for row in doc["routes"] if row.get("function") == "scenario_economics")
    assert entry["method"] == "POST"
    assert entry["path"] == "/api/v1/scenario/economics"
    assert entry["file"] == "api/routers/scenario.py"

    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    actual = next(
        d.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "scenario_economics"
        for d in node.decorator_list
        if isinstance(d, ast.Call)
    )
    assert entry["line"] == actual, "map line must track the source, not drift from it"


def test_consumer_does_not_supply_defaults_for_missing_economics():
    """The router must pass the caller's inputs through untouched."""
    source = ROUTER.read_text(encoding="utf-8")
    start = source.index("def scenario_economics")
    body = source[start : start + 1200]
    for injected in ("or 0", "= 0.0", "default=0"):
        assert injected not in body, f"router must not inject {injected!r}"
