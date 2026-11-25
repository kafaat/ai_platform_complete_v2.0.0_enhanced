"""Regression tests for the fertility engine's numeric contract."""

import pytest

from core.engines.fertility import fertiliser_need


@pytest.mark.parametrize(
    "required,available,efficiency",
    [
        (float("nan"), 40, 0.5),
        (120, float("nan"), 0.5),
        (float("inf"), 40, 0.5),
        (120, float("inf"), 0.5),
        (-1, 40, 0.5),
        (120, -1, 0.5),
        (120, 40, float("nan")),
        (120, 40, float("inf")),
        (120, 40, 0),
        (120, 40, -0.5),
        (120, 40, 0.05),
        (120, 40, 1.1),
        (True, 40, 0.5),
        (120, False, 0.5),
        (120, 40, True),
        (10**400, 40, 0.5),
        (1e308, 0, 0.1),
    ],
)
def test_fertility_rejects_invalid_nutrient_balance(required, available, efficiency):
    with pytest.raises(ValueError):
        fertiliser_need("N", required, available, efficiency)


@pytest.mark.parametrize(
    "required,available,efficiency,expected",
    [(120, 40, 0.5, 160), (50, 80, 0.5, 0), (0, 0, 1, 0), (10, 0, 0.1, 100), (10, 0, 1, 10)],
)
def test_fertility_preserves_valid_nutrient_balance(required, available, efficiency, expected):
    assert fertiliser_need("N", required, available, efficiency).fertiliser_kg_ha == expected
