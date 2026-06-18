"""اختبارات وحدة لأداة حاسبة حجم مياه الريّ (irrigation_volume)."""

from __future__ import annotations

import pytest
from core.agri_tools.registry import run_tool
from core.agri_tools.tools.irrigation_volume import compute

pytestmark = pytest.mark.unit


def test_net_volume_basic():
    # 25 مم على 4 هكتار = 1000 م³ صافٍ.
    out = compute({"depth_mm": 25.0, "area_ha": 4.0, "efficiency": 0.8, "flow_rate_m3h": 0.0})
    assert out["net_volume_m3"] == 1000.0
    assert out["net_volume_liters"] == 1_000_000.0


def test_gross_volume_with_efficiency():
    # صافٍ 1000 م³ ÷ كفاءة 0.8 = 1250 م³ إجماليّ.
    out = compute({"depth_mm": 25.0, "area_ha": 4.0, "efficiency": 0.8, "flow_rate_m3h": 0.0})
    assert out["gross_volume_m3"] == 1250.0


def test_run_time_from_flow():
    # إجماليّ 1250 م³ ÷ 100 م³/ساعة = 12.5 ساعة.
    out = compute({"depth_mm": 25.0, "area_ha": 4.0, "efficiency": 0.8, "flow_rate_m3h": 100.0})
    assert out["run_time_hours"] == 12.5


def test_no_flow_run_time_none():
    out = compute({"depth_mm": 25.0, "area_ha": 4.0, "efficiency": 0.8, "flow_rate_m3h": 0.0})
    assert out["run_time_hours"] is None


def test_efficiency_default_applied():
    # عبر run_tool تُطبّق القيمة الافتراضيّة للكفاءة (0.85).
    out = run_tool("irrigation_volume", {"depth_mm": 10.0, "area_ha": 1.0})
    assert out["net_volume_m3"] == 100.0
    assert out["gross_volume_m3"] == round(100.0 / 0.85, 2)
    assert out["run_time_hours"] is None


def test_registered_tool_metadata():
    from core.agri_tools.registry import get_tool

    tool = get_tool("irrigation_volume")
    assert tool is not None
    assert tool.category == "irrigation"
    assert tool.compute is compute
