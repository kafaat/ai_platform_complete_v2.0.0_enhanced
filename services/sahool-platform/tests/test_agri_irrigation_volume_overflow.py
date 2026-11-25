"""Finite inputs must not produce a non-finite irrigation result."""

import json

import pytest
from core.agri_tools.registry import run_tool
from core.agri_tools.tools.irrigation_volume import compute

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "inputs",
    [
        {"depth_mm": 1e200, "area_ha": 1e200},
        {"depth_mm": 1e307, "area_ha": 1.0, "efficiency": 0.1},
        {"depth_mm": 1e305, "area_ha": 1.0},
        {"depth_mm": 10.0, "area_ha": 1.0, "flow_rate_m3h": 1e-310},
    ],
)
def test_finite_inputs_overflow_is_rejected(inputs):
    with pytest.raises(ValueError, match="irrigation_volume"):
        run_tool("irrigation_volume", inputs)


def test_direct_compute_overflow_is_rejected():
    with pytest.raises(ValueError, match="irrigation_volume"):
        compute({"depth_mm": 1e200, "area_ha": 1e200, "efficiency": 0.8, "flow_rate_m3h": 1.0})


@pytest.mark.parametrize("flow", [0.0, 200.0])
def test_normal_and_zero_flow_remain_json_safe(flow):
    result = run_tool(
        "irrigation_volume",
        {"depth_mm": 6.0, "area_ha": 50.0, "efficiency": 0.8, "flow_rate_m3h": flow},
    )
    assert result == {
        "net_volume_m3": 3000.0,
        "gross_volume_m3": 3750.0,
        "net_volume_liters": 3000000.0,
        "run_time_hours": 18.75 if flow else None,
    }
    json.dumps(result, allow_nan=False)


def test_zero_depth_remains_zero():
    result = run_tool("irrigation_volume", {"depth_mm": 0, "area_ha": 50, "flow_rate_m3h": 200})
    assert all(value == 0 for value in result.values())
