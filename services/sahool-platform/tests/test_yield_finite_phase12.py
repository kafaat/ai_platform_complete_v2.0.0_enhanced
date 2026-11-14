"""Non-finite or unrepresentably large yield values must never reach reports."""

import math

import pytest
from api.yield_analysis import _to_float, assemble_yield_analysis

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "-Infinity", float("inf"), float("-inf"), float("nan"), 10**1000]
)
def test_nonfinite_harvest_values_are_missing_not_zero(value):
    assert _to_float(value) is None
    row = {
        "season_id": "s1",
        "field_id": "f1",
        "cultivar": "A",
        "crops": ["wheat"],
        "actual_yield_kg_ha": value,
        "target_yield_kg_ha": 5000,
    }
    result = assemble_yield_analysis([row])
    assert result["summary"]["seasons_with_harvest"] == 0
    assert result["planting_vs_harvest"][0]["actual_yield_t_ha"] is None
    assert result["hybrid_performance"] == []


def test_inf_target_does_not_break_numeric_gap():
    result = assemble_yield_analysis(
        [
            {
                "season_id": "s1",
                "field_id": "f1",
                "cultivar": "A",
                "crops": ["wheat"],
                "actual_yield_kg_ha": 4000,
                "target_yield_kg_ha": float("inf"),
            }
        ]
    )
    record = result["planting_vs_harvest"][0]
    assert record["actual_yield_t_ha"] == 4.0
    assert record["target_yield_t_ha"] is None
    assert record["yield_gap_t_ha"] is None
    assert all(math.isfinite(item["avg_yield_t_ha"]) for item in result["hybrid_performance"])


def test_large_but_finite_harvest_values_do_not_overflow_the_mean():
    rows = [
        {
            "season_id": f"s{i}",
            "field_id": f"f{i}",
            "cultivar": "A",
            "crops": ["wheat"],
            "actual_yield_kg_ha": 1e308,
        }
        for i in range(2400)
    ]
    result = assemble_yield_analysis(rows)
    average = result["hybrid_performance"][0]["avg_yield_t_ha"]
    assert math.isfinite(average)
    assert average > 0
