"""اختبارات سجلّ Agri Tools — الاكتشاف التلقائيّ + التحقّق + التشغيل."""

from __future__ import annotations

import math

import pytest
from core.agri_tools import discover, get_tool, list_tools, run_tool
from core.agri_tools.registry import Tool, ToolParam, register

pytestmark = pytest.mark.unit


def test_discovery_registers_tools():
    assert discover() >= 1
    assert get_tool("pivot_coverage") is not None


def test_list_by_category():
    irr = list_tools(category="irrigation")
    assert any(t.id == "pivot_coverage" for t in irr)
    assert all(t.category == "irrigation" for t in irr)


def test_run_tool_validates_required():
    with pytest.raises(ValueError):
        run_tool("pivot_coverage", {})  # radius_m مطلوب


def test_run_tool_unknown_raises():
    with pytest.raises(KeyError):
        run_tool("nope_tool", {})


def test_run_tool_min_max_enforced():
    with pytest.raises(ValueError):
        run_tool("pivot_coverage", {"radius_m": 0})  # < min=1


def test_pivot_coverage_math():
    # نصف قطر 100م، بلا مدفع ⇒ مساحة = π·100² م² = 3.1416 هـ، نسبة = π/4
    r = run_tool("pivot_coverage", {"radius_m": 100})
    assert math.isclose(r["irrigated_area_ha"], math.pi, rel_tol=1e-3)
    assert math.isclose(r["coverage_ratio"], math.pi / 4, rel_tol=1e-3)


def test_duplicate_registration_rejected():
    t = Tool(
        id="pivot_coverage",
        name_ar="x",
        category="irrigation",
        description_ar="x",
        params=[],
        compute=lambda i: {},
    )
    with pytest.raises(ValueError):
        register(t)


def test_unknown_category_rejected():
    t = Tool(
        id="_tmp_bad_cat",
        name_ar="x",
        category="not_a_category",
        description_ar="x",
        params=[ToolParam("a", "number", "ا")],
        compute=lambda i: {},
    )
    with pytest.raises(ValueError):
        register(t)
