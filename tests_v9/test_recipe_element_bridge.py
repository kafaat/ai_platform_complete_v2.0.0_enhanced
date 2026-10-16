"""Recipe-input mass conversion; this never authorizes nutrient injection."""

import pytest

from shared.precision_agriculture.phase6_intelligence import generate_prescription_map

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "kind,source_unit,element,factor",
    [
        ("phosphorus", "kgP2O5/ha", "P", 0.4364),
        ("potassium", "kgK2O/ha", "K", 0.8301),
        ("nitrogen", "kgN/ha", "N", 1.0),
    ],
)
def test_live_prescription_generator_exposes_elemental_recipe_input(
    kind, source_unit, element, factor
):
    result = generate_prescription_map(
        [{"id": "zone-a", "zone": 1, "rate_multiplier": 1.25}],
        crop="wheat",
        prescription_type=kind,
    )
    props = result["features"][0]["properties"]
    recipe = props["properties"]["recipe_input"]
    assert props["unit"] == recipe["source_unit"] == source_unit
    assert recipe["source_rate"] == props["rate"]
    assert recipe["element"] == element
    assert recipe["elemental_rate_kg_ha"] == pytest.approx(props["rate"] * factor)
    assert recipe["concentration_mg_l"] is None
    assert recipe["execution_authorized"] is False
    assert recipe["requires_agronomist_review"] is True


def test_seed_rates_are_not_silently_reinterpreted_as_nutrients():
    result = generate_prescription_map(
        [{"id": "seed", "zone": 1}], crop="wheat", prescription_type="seed"
    )
    assert "recipe_input" not in result["features"][0]["properties"]["properties"]


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf"), True, "60"])
def test_recipe_bridge_rejects_invalid_amounts(rate):
    from shared.precision_agriculture.nutrient_units import recipe_elemental_input

    with pytest.raises(ValueError, match="finite and nonnegative"):
        recipe_elemental_input(rate, "kgP2O5/ha")


@pytest.mark.parametrize("unit", ["kg/ha", "mg/L", "P2O5", "kgP2O5"])
def test_recipe_bridge_does_not_guess_a_missing_area_or_nutrient_basis(unit):
    from shared.precision_agriculture.nutrient_units import recipe_elemental_input

    with pytest.raises(ValueError, match="explicit nutrient mass basis"):
        recipe_elemental_input(60, unit)


@pytest.mark.parametrize("unit", ["kgP/ha", "kgK/ha"])
def test_elemental_recipe_input_is_not_converted_twice(unit):
    from shared.precision_agriculture.nutrient_units import recipe_elemental_input

    assert recipe_elemental_input(42, unit)["elemental_rate_kg_ha"] == 42


@pytest.mark.parametrize("multiplier", [-1, float("nan"), float("inf"), True, "1"])
def test_live_recipe_generator_rejects_invalid_nutrient_multipliers(multiplier):
    with pytest.raises(ValueError):
        generate_prescription_map(
            [{"rate_multiplier": multiplier}], crop="wheat", prescription_type="phosphorus"
        )


def test_explicit_zero_recipe_input_stays_zero():
    result = generate_prescription_map(
        [{"rate_multiplier": 0}], crop="wheat", prescription_type="phosphorus"
    )
    properties = result["features"][0]["properties"]
    assert (
        properties["rate"] == properties["properties"]["recipe_input"]["elemental_rate_kg_ha"] == 0
    )
