"""Synthetic acceptance slice: registered tool and shared nutrient balance."""

import pytest
from core.agri_tools.registry import run_tool
from core.agri_tools.tools.fertilizer import compute
from core.engines import fertility

pytestmark = pytest.mark.unit


def inputs(**overrides):
    return {
        "target_yield_t_ha": 6.0,
        "uptake_kg_per_t": 25.0,
        "soil_supply_kg_ha": 30.0,
        "fertilizer_grade_pct": 46.0,
        "use_efficiency": 0.75,
        **overrides,
    }


def test_registered_tool_and_engine_share_balance(monkeypatch):
    original = fertility.nutrient_balance
    calls = []

    def spy(required_kg_ha, available_kg_ha, use_efficiency):
        calls.append((required_kg_ha, available_kg_ha, use_efficiency))
        return original(required_kg_ha, available_kg_ha, use_efficiency)

    monkeypatch.setattr(fertility, "nutrient_balance", spy)
    result = run_tool("fertilizer_requirement", inputs())
    engine = fertility.fertiliser_need("N", 150.0, 30.0, 0.75)
    assert calls == [(150.0, 30.0, 0.75)] * 2
    assert result["nutrient_to_apply_kg_ha"] == engine.fertiliser_kg_ha == 160.0
    assert result["product_kg_ha"] == 347.83


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_yield_t_ha": 1e308, "uptake_kg_per_t": 2.0},
        {"target_yield_t_ha": 1e308, "uptake_kg_per_t": 1.0, "use_efficiency": 0.1},
        {"target_yield_t_ha": 1e308, "uptake_kg_per_t": 1.0, "fertilizer_grade_pct": 1.0},
    ],
)
def test_registered_tool_rejects_nonfinite_results(overrides):
    with pytest.raises(ValueError):
        run_tool("fertilizer_requirement", inputs(**overrides))


def test_zero_efficiency_not_silently_defaulted_in_direct_tool():
    with pytest.raises(ValueError):
        compute(inputs(use_efficiency=0.0))


def test_tool_preserves_two_decimal_precision_before_product_conversion():
    result = run_tool(
        "fertilizer_requirement",
        inputs(
            target_yield_t_ha=0.1234,
            uptake_kg_per_t=1,
            soil_supply_kg_ha=0,
            use_efficiency=1,
        ),
    )
    assert result["nutrient_to_apply_kg_ha"] == 0.12
    assert result["product_kg_ha"] == 0.27


def test_synthetic_two_wheat_pivots_nutrient_mass_balance():
    # Fictional 180 ha farm; only two 50 ha pivots have supplied assumptions.
    # The remaining 80 ha must not be assigned a nutrient dose.
    area_ha = 180
    pivots_ha = [50, 50]
    rates = [run_tool("fertilizer_requirement", inputs()) for _ in pivots_ha]
    assert area_ha - sum(pivots_ha) == 80
    nutrient_total = sum(
        r["nutrient_to_apply_kg_ha"] * a for r, a in zip(rates, pivots_ha, strict=True)
    )
    product_total = sum(r["product_kg_ha"] * a for r, a in zip(rates, pivots_ha, strict=True))
    assert nutrient_total == 16000
    assert product_total == pytest.approx(34783)
