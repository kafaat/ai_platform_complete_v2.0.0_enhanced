"""اختبارات نقيّة لفحص جدوى شبكة الريّ (api.irrigation_network).

اتّصاليّة + توفّر ماء + إنتاجيّة + ضغط — توصية فقط. القيد الغائب يُعلَن unchecked لا
يُفترَض نجاحه (لا جدوى كاذبة، لا تلفيق).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.irrigation_network import (  # noqa: E402
    NetworkEdge,
    NetworkNode,
    check_network_feasibility,
)


def _chain(well_cap=None, zone_demand=None, pump_press=None, zone_press=None, throughput=None):
    """شبكة خطّيّة: well → pump → valve → zone (قيود اختياريّة)."""
    nodes = [
        NetworkNode("w1", "well", capacity_m3=well_cap),
        NetworkNode("p1", "pump", max_pressure_bar=pump_press, max_throughput_m3=throughput),
        NetworkNode("v1", "valve"),
        NetworkNode("z1", "zone", demand_m3=zone_demand, min_pressure_bar=zone_press),
    ]
    edges = [NetworkEdge("w1", "p1"), NetworkEdge("p1", "v1"), NetworkEdge("v1", "z1")]
    return nodes, edges


def test_connected_with_enough_water_is_feasible():
    nodes, edges = _chain(well_cap=1000, zone_demand=300)
    out = check_network_feasibility(nodes, edges)
    z = out["zones"][0]
    # سعة كافية لكن لا ضغط/إنتاجيّة محدّدة ⇒ feasible_unverified (unchecked مُعلَن).
    assert z["status"] == "feasible_unverified"
    assert z["path"] == ["z1", "v1", "p1", "w1"]
    assert out["overall_feasible"] is True


def test_fully_specified_passing_is_feasible():
    # كلّ القيود محدَّدة على كلّ عقدة ناقلة (مضخّة + صمّام) ⇒ feasible بلا unchecked.
    nodes = [
        NetworkNode("w1", "well", capacity_m3=1000),
        NetworkNode("p1", "pump", max_pressure_bar=3.0, max_throughput_m3=500),
        NetworkNode("v1", "valve", max_throughput_m3=500),
        NetworkNode("z1", "zone", demand_m3=300, min_pressure_bar=2.0),
    ]
    edges = [NetworkEdge("w1", "p1"), NetworkEdge("p1", "v1"), NetworkEdge("v1", "z1")]
    out = check_network_feasibility(nodes, edges)
    z = out["zones"][0]
    assert z["status"] == "feasible"
    assert z["unchecked"] == []


def test_disconnected_zone_is_infeasible():
    # منطقة بلا وصلة لأيّ بئر ⇒ مقطوعة infeasible.
    nodes = [NetworkNode("w1", "well", capacity_m3=500), NetworkNode("z9", "zone", demand_m3=100)]
    out = check_network_feasibility(nodes, [])  # لا وصلات
    z = out["zones"][0]
    assert z["status"] == "infeasible"
    assert z["path"] is None
    assert out["overall_feasible"] is False
    assert "z9" in out["warnings_ar"][-1]


def test_water_deficit_is_infeasible_with_reason():
    nodes, edges = _chain(well_cap=200, zone_demand=300)
    out = check_network_feasibility(nodes, edges)
    z = out["zones"][0]
    assert z["status"] == "infeasible"
    assert "عجز ماء" in z["reasons_ar"][0]
    assert "w1" in z["bottlenecks"]
    assert out["wells"][0]["over_capacity"] is True


def test_throughput_bottleneck_detected():
    nodes, edges = _chain(well_cap=1000, zone_demand=400, throughput=300)
    out = check_network_feasibility(nodes, edges)
    z = out["zones"][0]
    assert z["status"] == "infeasible"
    assert any("اختناق" in r for r in z["reasons_ar"])
    assert "p1" in z["bottlenecks"]


def test_pressure_shortfall_detected():
    nodes, edges = _chain(well_cap=1000, zone_demand=100, pump_press=1.5, zone_press=3.0)
    out = check_network_feasibility(nodes, edges)
    z = out["zones"][0]
    assert z["status"] == "infeasible"
    assert any("ضغط" in r for r in z["reasons_ar"])


def test_missing_constraints_are_unchecked_not_assumed():
    # بلا سعة/إنتاجيّة/ضغط/طلب ⇒ كلّها unchecked (لا تُفترَض ناجحة).
    nodes, edges = _chain()
    out = check_network_feasibility(nodes, edges)
    z = out["zones"][0]
    assert z["status"] == "feasible_unverified"
    assert "demand" in z["unchecked"]
    assert any(u.startswith("well_capacity") for u in z["unchecked"])
    assert "pressure" not in z["unchecked"]  # لا min_pressure مطلوب ⇒ لا فحص ضغط


def test_shared_well_aggregates_load():
    # منطقتان على نفس البئر: مجموع طلبهما يتجاوز السعة ⇒ عجز.
    nodes = [
        NetworkNode("w1", "well", capacity_m3=500),
        NetworkNode("m1", "main_line"),
        NetworkNode("z1", "zone", demand_m3=300),
        NetworkNode("z2", "zone", demand_m3=300),
    ]
    edges = [
        NetworkEdge("w1", "m1"),
        NetworkEdge("m1", "z1"),
        NetworkEdge("m1", "z2"),
    ]
    out = check_network_feasibility(nodes, edges)
    assert out["wells"][0]["load_m3"] == 600.0
    assert out["wells"][0]["over_capacity"] is True
    assert out["overall_feasible"] is False


def test_advice_only_warning_present():
    nodes, edges = _chain(well_cap=1000, zone_demand=100)
    out = check_network_feasibility(nodes, edges)
    assert any("توصية فقط" in w for w in out["warnings_ar"])
    assert out["calibrated"] == "not_applicable"


def test_empty_network_safe():
    out = check_network_feasibility([], [])
    assert out["zone_count"] == 0
    assert out["overall_feasible"] is True
    assert out["wells"] == []
