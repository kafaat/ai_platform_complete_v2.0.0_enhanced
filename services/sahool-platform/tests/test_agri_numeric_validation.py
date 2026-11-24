"""Numeric validation at the shared agricultural tools boundary."""

from __future__ import annotations

import math

import pytest
from core.agri_tools.registry import ToolParam, _coerce, run_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("bad", [float("nan"), "NaN", float("inf"), "-Infinity"])
def test_unbounded_numeric_parameter_rejects_nonfinite_values(bad):
    with pytest.raises(ValueError, match="measurement"):
        _coerce(ToolParam("measurement", "number", "measurement"), bad)


@pytest.mark.parametrize("bad", [True, False, 10**400], ids=["true", "false", "overflow"])
def test_numeric_parameter_rejects_boolean_or_overflow(bad):
    with pytest.raises(ValueError, match="measurement"):
        _coerce(ToolParam("measurement", "number", "measurement"), bad)


def test_pivot_rejects_nan_before_calculation():
    with pytest.raises(ValueError, match="radius_m"):
        run_tool("pivot_coverage", {"radius_m": "NaN"})


def test_valid_pivot_numeric_string_and_optional_default():
    result = run_tool("pivot_coverage", {"radius_m": "100"})
    assert result["effective_radius_m"] == 100
    assert result["irrigated_area_ha"] == pytest.approx(math.pi, rel=1e-3)


def test_optional_numeric_default_and_zero_are_preserved():
    param = ToolParam("measurement", "number", "measurement", required=False, default=5)
    assert _coerce(param, None) == 5
    assert _coerce(param, 0) == 0
