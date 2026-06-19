"""اختبار تحسين محفظة الحقول (#381) — طبقة نقيّة حتميّة، بلا UI.

يثبت: (أ) يوجّه الماء الشحيح للحقل الأعلى إنتاجيّةً أوّلاً؛ (ب) آخر حقل جزئيّ؛ (ج)
ماء وافر ⇒ الكلّ full + فائض؛ (د) الهامش الكلّيّ يتبع التخصيص؛ (هـ) احتياج صفر ⇒
هامش كامل بلا ماء؛ (و) حقول unmet عند النقص؛ (ز) calibrated=False. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.field_portfolio import FieldInput, optimize_field_portfolio  # noqa: E402


def test_scarce_water_goes_to_highest_productivity():
    # A: 1000$/1000م³ = 1.0/م³؛ B: 1500$/1000م³ = 1.5/م³ (أعلى) ⇒ يُموَّل أوّلاً.
    fields = [
        FieldInput("A", expected_margin=1000.0, water_demand_m3=1000.0),
        FieldInput("B", expected_margin=1500.0, water_demand_m3=1000.0),
    ]
    res = optimize_field_portfolio(fields, total_water_m3=1000.0)  # يكفي حقلاً واحداً
    by = {f["field_id"]: f for f in res["fields"]}
    assert by["B"]["status"] == "full"  # الأعلى إنتاجيّة
    assert by["A"]["status"] == "unmet"
    assert res["total_expected_margin"] == pytest.approx(1500.0)


def test_partial_allocation_last_field():
    fields = [
        FieldInput("B", expected_margin=1500.0, water_demand_m3=1000.0),  # 1.5/م³
        FieldInput("A", expected_margin=1000.0, water_demand_m3=1000.0),  # 1.0/م³
    ]
    res = optimize_field_portfolio(fields, total_water_m3=1500.0)  # B كامل + نصف A
    by = {f["field_id"]: f for f in res["fields"]}
    assert by["B"]["status"] == "full"
    assert by["A"]["status"] == "partial"
    assert by["A"]["fraction"] == pytest.approx(0.5)
    # 1500 (B) + 0.5×1000 (A) = 2000.
    assert res["total_expected_margin"] == pytest.approx(2000.0)
    assert res["allocated_m3"] == pytest.approx(1500.0)


def test_abundant_water_all_full_with_surplus():
    fields = [
        FieldInput("A", expected_margin=1000.0, water_demand_m3=500.0),
        FieldInput("B", expected_margin=800.0, water_demand_m3=500.0),
    ]
    res = optimize_field_portfolio(fields, total_water_m3=2000.0)
    assert all(f["status"] == "full" for f in res["fields"])
    assert res["unallocated_m3"] == pytest.approx(1000.0)
    assert res["total_expected_margin"] == pytest.approx(1800.0)


def test_zero_demand_field_full_margin_no_water():
    fields = [
        FieldInput("rainfed", expected_margin=600.0, water_demand_m3=0.0),
        FieldInput("irrig", expected_margin=900.0, water_demand_m3=1000.0),
    ]
    res = optimize_field_portfolio(fields, total_water_m3=0.0)
    by = {f["field_id"]: f for f in res["fields"]}
    assert by["rainfed"]["status"] == "full"  # هامش كامل بلا ماء
    assert by["rainfed"]["allocated_m3"] == 0.0
    assert by["irrig"]["status"] == "unmet"
    assert res["total_expected_margin"] == pytest.approx(600.0)


def test_unmet_listed_in_warnings():
    fields = [FieldInput("X", expected_margin=500.0, water_demand_m3=1000.0)]
    res = optimize_field_portfolio(fields, total_water_m3=0.0)
    assert any("X" in w for w in res["warnings_ar"])


def test_output_preserves_input_order():
    fields = [
        FieldInput("first", expected_margin=100.0, water_demand_m3=1000.0),
        FieldInput("second", expected_margin=900.0, water_demand_m3=1000.0),
    ]
    res = optimize_field_portfolio(fields, total_water_m3=2000.0)
    assert [f["field_id"] for f in res["fields"]] == ["first", "second"]


def test_calibrated_false():
    res = optimize_field_portfolio([FieldInput("A", 100.0, 100.0)], total_water_m3=100.0)
    assert res["calibrated"] is False
