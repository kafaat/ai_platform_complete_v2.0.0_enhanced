"""اختبار قرار المحصول الموحّد (Unified Crop Decision) — تركيب نقيّ حتميّ.

يثبت: (أ) يجمع ريّ+تسميد+مخاطر+ثقة من حالات محسوبة؛ (ب) قرار الريّ من الخطّة (أوّل
دفعة)؛ (ج) قرار التسميد = الهدف − المُمتصّ؛ (د) المخاطر: مائي حقيقيّ، حراريّ/ملوحة
«يحتاج بيانات»؛ (هـ) economic_state محجوز not_configured؛ (و) أعلام موحّدة؛ (ز)
calibrated=False وانتقال التحذيرات. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.unified_decision import unified_decision  # noqa: E402


def _twin(needs_irrig=True, past_maturity=False, target=120.0, to_date=45.0):
    return {
        "crop": "wheat",
        "crop_known": True,
        "phenology": {"stage": "mid", "progress": 0.45, "past_maturity": past_maturity},
        "water": {
            "taw_mm": 175.0,
            "raw_mm": 87.5,
            "depletion_mm": 90.0,
            "needs_irrigation": needs_irrig,
        },
        "nutrient": {
            "stage": "development",
            "target_uptake_kg_ha": target,
            "uptake_to_date_kg_ha": to_date,
        },
        "warnings_ar": ["تحذير تربة"],
    }


def _plan(events=2, total=80.0, stress=1):
    days = [
        {"day_index": 0, "irrigation_mm": 0.0},
        {"day_index": 3, "irrigation_mm": 40.0},
        {"day_index": 6, "irrigation_mm": 40.0},
    ]
    return {
        "policy": "water_saving",
        "total_irrigation_mm": total,
        "n_events": events,
        "stress_days": list(range(stress)),
        "days": days,
        "notes_ar": ["ملاحظة خطّة"],
    }


def _quality(conf=0.70, dq="medium"):
    return {
        "confidence": conf,
        "data_quality": dq,
        "assumptions": ["uncalibrated_model"],
        "assumptions_ar": ["ثوابت غير معايَرة"],
    }


def test_combines_all_layers():
    d = unified_decision(_twin(), _plan(), _quality())
    assert set(d) >= {
        "irrigation",
        "fertilization",
        "risks",
        "confidence",
        "economic_state",
        "stress_flags",
        "phenology",
        "water_state",
        "nutrient_state",
    }


def test_irrigation_from_plan_next_event():
    d = unified_decision(_twin(), _plan(), _quality())
    assert d["irrigation"]["next_event_day"] == 3
    assert d["irrigation"]["next_event_mm"] == pytest.approx(40.0)
    assert "ريّ" in d["irrigation"]["action_ar"]


def test_irrigation_none_when_no_events():
    plan = _plan()
    plan["days"] = [{"day_index": 0, "irrigation_mm": 0.0}]
    d = unified_decision(_twin(needs_irrig=False), plan, _quality())
    assert d["irrigation"]["next_event_day"] is None
    assert "لا ريّ" in d["irrigation"]["action_ar"]


def test_fertilization_remaining_need():
    d = unified_decision(_twin(target=120.0, to_date=45.0), _plan(), _quality())
    assert d["fertilization"]["remaining_need_kg_ha"] == pytest.approx(75.0)
    assert d["fertilization"]["due"] is True


def test_fertilization_no_target():
    d = unified_decision(_twin(target=0.0, to_date=0.0), _plan(), _quality())
    assert d["fertilization"]["due"] is False
    assert "لا هدف" in d["fertilization"]["action_ar"]


def test_risks_water_real_heat_salinity_needs_data():
    d = unified_decision(_twin(), _plan(stress=3), _quality())
    by_key = {r["key"]: r["level_ar"] for r in d["risks"]}
    assert by_key["water"] == "مرتفع"  # 3 أيّام إجهاد
    assert by_key["heat"] == "يحتاج بيانات"
    assert by_key["salinity"] == "يحتاج بيانات"


def test_economic_state_reserved():
    d = unified_decision(_twin(), _plan(), _quality())
    assert d["economic_state"]["status"] == "not_configured"
    assert "crop_price" in d["economic_state"]["required_inputs"]


def test_economic_state_filled_when_provided():
    econ = {"status": "ok", "expected_margin": 1640.0, "confidence": 0.85}
    d = unified_decision(_twin(), _plan(), _quality(), economic=econ)
    assert d["economic_state"] == econ  # يملأ المكان المحجوز
    assert d["economic_state"]["status"] == "ok"


def test_unified_flags():
    d = unified_decision(_twin(needs_irrig=True, past_maturity=True), _plan(), _quality())
    codes = {f["code"] for f in d["stress_flags"]}
    assert {"water_deficit", "past_maturity", "fertilization_due"} <= codes


def test_confidence_and_warnings_propagate():
    d = unified_decision(_twin(), _plan(), _quality(conf=0.62))
    assert d["confidence"] == 0.62
    assert d["calibrated"] is False
    assert "تحذير تربة" in d["warnings_ar"]
    assert "ملاحظة خطّة" in d["warnings_ar"]
