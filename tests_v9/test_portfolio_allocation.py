"""اختبار توزيع ماء المزرعة متعدّد المصادر (#386) — نقيّ حتميّ.

يثبت: (أ) «إجهاد الحقل الأدنى لحماية الأعلى أولويّة»؛ (ب) الأرضيّة الدنيا تُحمى أوّلاً؛
(ج) قيد المصادر (حقل يُسحَب من بئره فقط)؛ (د) سعة المصدر لا تُتجاوَز؛ (هـ) ماء وافر ⇒
الكلّ full؛ (و) unmet عند النقص؛ (ز) calibrated=False. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.portfolio_allocation import (  # noqa: E402
    PortfolioField,
    WaterSource,
    allocate_portfolio,
)


def _f(fid, margin, demand, priority=1, floor=0.0, srcs=None):
    return PortfolioField(
        fid, margin, demand, priority=priority, min_water_fraction=floor, source_ids=srcs or []
    )


def test_high_priority_protected_low_stressed():
    # ماء يكفي حقلاً واحداً؛ الأولويّة الأعلى (field1) تُحمى، field3 يُجهَد.
    fields = [
        _f("field1", margin=1000.0, demand=1000.0, priority=5),
        _f("field3", margin=1200.0, demand=1000.0, priority=1),
    ]
    sources = [WaterSource("well", 1000.0)]
    res = allocate_portfolio(fields, sources)
    by = {f["field_id"]: f for f in res["fields"]}
    assert by["field1"]["status"] == "full"  # محميّ رغم إنتاجيّته الأدنى
    assert by["field3"]["status"] == "unmet"  # أُجهِد لحماية الأعلى أولويّة
    assert "field3" in res["unmet_fields"]


def test_minimum_floor_protected_first():
    # field_low أولويّة أدنى لكن له أرضيّة 0.5 ⇒ يُحمى نصفه قبل تعظيم الأعلى.
    fields = [
        _f("hi", margin=1000.0, demand=1000.0, priority=5),
        _f("low", margin=900.0, demand=1000.0, priority=1, floor=0.5),
    ]
    sources = [WaterSource("well", 1200.0)]  # 500 أرضيّة low + 700 لـhi
    res = allocate_portfolio(fields, sources)
    by = {f["field_id"]: f for f in res["fields"]}
    assert by["low"]["allocated_m3"] >= 500.0  # أرضيّته محميّة
    assert by["hi"]["allocated_m3"] == pytest.approx(700.0)  # الباقي
    assert "low" in res["protected_fields"]


def test_source_eligibility_respected():
    # field_a يُسحَب من well_a فقط؛ well_b لا يخدمه رغم سعته.
    fields = [_f("a", 1000.0, 500.0, srcs=["well_a"])]
    sources = [WaterSource("well_a", 200.0), WaterSource("well_b", 1000.0)]
    res = allocate_portfolio(fields, sources)
    by = {f["field_id"]: f for f in res["fields"]}
    assert by["a"]["allocated_m3"] == pytest.approx(200.0)  # محدود بـwell_a
    assert by["a"]["sources_used"] == {"well_a": 200.0}


def test_source_capacity_not_exceeded():
    fields = [_f("a", 1000.0, 2000.0)]
    sources = [WaterSource("w1", 300.0), WaterSource("w2", 400.0)]
    res = allocate_portfolio(fields, sources)
    for s in res["sources"]:
        assert s["used_m3"] <= s["capacity_m3"] + 1e-9
    assert res["total_allocated_m3"] == pytest.approx(700.0)


def test_abundant_all_full():
    fields = [_f("a", 1000.0, 500.0), _f("b", 800.0, 500.0)]
    sources = [WaterSource("w", 5000.0)]
    res = allocate_portfolio(fields, sources)
    assert all(f["status"] == "full" for f in res["fields"])
    assert res["total_expected_margin"] == pytest.approx(1800.0)


def test_calibrated_false():
    res = allocate_portfolio([_f("a", 100.0, 100.0)], [WaterSource("w", 100.0)])
    assert res["calibrated"] is False
