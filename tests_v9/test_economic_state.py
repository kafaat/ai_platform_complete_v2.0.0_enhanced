"""اختبار الحالة الاقتصاديّة (#378) — طبقة نقيّة حتميّة، بلا UI/قرار.

يثبت: (أ) الإيراد=غلّة×سعر، التكاليف=كمّيّة×سعر؛ (ب) الهامش=إيراد−تكاليف؛ (ج) غياب
مُدخَل ⇒ مكوّنه None ويُدرَج في missing (لا صفر مُختلق)؛ (د) عدم يقين الهامش موجب
ويتبع الإيراد؛ (هـ) الثقة تتدرّج مع اكتمال المكوّنات؛ (و) status not_configured/partial/ok؛
(ز) calibrated=False. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.economic_state import economic_state  # noqa: E402


def _full():
    return economic_state(
        expected_yield_t_ha=5.0,
        crop_price_per_t=400.0,
        irrigation_m3_ha=3000.0,
        water_price_per_m3=0.05,
        energy_kwh_ha=500.0,
        energy_price_per_kwh=0.1,
        fertilizer_kg_ha=200.0,
        fertilizer_price_per_kg=0.8,
    )


def test_revenue_and_costs():
    e = _full()
    assert e["gross_revenue"] == pytest.approx(2000.0)  # 5 × 400
    assert e["water_cost"] == pytest.approx(150.0)  # 3000 × 0.05
    assert e["energy_cost"] == pytest.approx(50.0)  # 500 × 0.1
    assert e["fertilizer_cost"] == pytest.approx(160.0)  # 200 × 0.8
    assert e["total_cost"] == pytest.approx(360.0)


def test_margin():
    e = _full()
    assert e["expected_margin"] == pytest.approx(2000.0 - 360.0)
    assert e["status"] == "ok"
    assert e["missing_inputs"] == []


def test_margin_uncertainty_positive_and_revenue_driven():
    e = _full()
    assert e["margin_uncertainty"] > 0
    # عدم اليقين = √(400² + 200² + 15² + 5² + 16²) = √200506 ≈ 447.78 (يهيمنه الإيراد).
    assert e["margin_uncertainty"] == pytest.approx(447.78, abs=0.5)


def test_missing_inputs_none_not_zero():
    e = economic_state(expected_yield_t_ha=5.0, crop_price_per_t=400.0)  # بلا تكاليف
    assert e["gross_revenue"] == pytest.approx(2000.0)
    assert e["water_cost"] is None
    assert e["energy_cost"] is None
    assert e["fertilizer_cost"] is None
    assert "water_price_per_m3" in e["missing_inputs"]
    assert e["status"] == "partial"
    # الهامش يُحسب على التكاليف المتوفّرة (صفر هنا) لكن لا يختلق تكاليف.
    assert e["expected_margin"] == pytest.approx(2000.0)


def test_not_configured_when_empty():
    e = economic_state()
    assert e["status"] == "not_configured"
    assert e["gross_revenue"] is None
    assert e["expected_margin"] is None
    assert e["margin_uncertainty"] is None


def test_confidence_scales_with_completeness():
    none = economic_state()["confidence"]
    full = _full()["confidence"]
    partial = economic_state(expected_yield_t_ha=5.0, crop_price_per_t=400.0)["confidence"]
    assert none < partial < full
    assert full == pytest.approx(0.85)


def test_calibrated_false():
    assert _full()["calibrated"] is False
    assert any("غير معايَر" in w for w in _full()["warnings_ar"])
