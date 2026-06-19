"""اختبار قياس نتائج القرار (#383) — نقيّ حتميّ، نصف حلقة التعلّم.

يثبت: (أ) اتّباع الريّ (ضمن/فوق/تحت الهامش)؛ (ب) الإجهاد (أفضل/كما تُنبِّئ/أسوأ)؛
(ج) الإنتاج (فوق/بلغ/دون)؛ (د) الميزانيّة المائيّة؛ (هـ) ناقص الطرفَين ⇒ needs_data
لا حكم مُختلق؛ (و) أعلام النجاح وdata_completeness؛ (ز) فارغ ⇒ تحذير. بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.outcome_measurement import measure_outcome  # noqa: E402


def _m(out, key):
    return next(m for m in out["metrics"] if m["key"] == key)


def test_irrigation_followed():
    out = measure_outcome({"recommended_irrigation_mm": 100.0}, {"actual_irrigation_mm": 105.0})
    assert _m(out, "irrigation")["status"] == "followed"  # ضمن 15%
    assert "irrigation_followed" in out["success_flags"]


def test_irrigation_under_and_over():
    under = measure_outcome({"recommended_irrigation_mm": 100.0}, {"actual_irrigation_mm": 50.0})
    assert _m(under, "irrigation")["status"] == "under"
    over = measure_outcome({"recommended_irrigation_mm": 100.0}, {"actual_irrigation_mm": 150.0})
    assert _m(over, "irrigation")["status"] == "over"


def test_stress_better_equal_worse():
    better = measure_outcome({"predicted_stress_days": 3}, {"observed_stress_days": 1})
    assert _m(better, "stress")["status"] == "better"
    assert "stress_better" in better["success_flags"]
    eq = measure_outcome({"predicted_stress_days": 2}, {"observed_stress_days": 2})
    assert _m(eq, "stress")["status"] == "as_predicted"
    worse = measure_outcome({"predicted_stress_days": 1}, {"observed_stress_days": 4})
    assert _m(worse, "stress")["status"] == "worse"


def test_stress_avoided_flag():
    out = measure_outcome({"predicted_stress_days": 2}, {"observed_stress_days": 0})
    assert "stress_avoided" in out["success_flags"]


def test_yield_above_met_below():
    above = measure_outcome({"expected_yield_t_ha": 5.0}, {"actual_yield_t_ha": 6.0})
    assert _m(above, "yield")["status"] == "above"
    met = measure_outcome({"expected_yield_t_ha": 5.0}, {"actual_yield_t_ha": 4.7})
    assert _m(met, "yield")["status"] == "met"  # ≥90%
    below = measure_outcome({"expected_yield_t_ha": 5.0}, {"actual_yield_t_ha": 3.0})
    assert _m(below, "yield")["status"] == "below"
    assert "yield_met" not in below["success_flags"]


def test_water_budget_within_exceeded():
    within = measure_outcome({"season_budget_mm": 400.0}, {"actual_water_used_mm": 380.0})
    assert _m(within, "water_budget")["status"] == "within"
    assert "water_within_budget" in within["success_flags"]
    over = measure_outcome({"season_budget_mm": 400.0}, {"actual_water_used_mm": 460.0})
    assert _m(over, "water_budget")["status"] == "exceeded"


def test_missing_pairs_needs_data_not_fabricated():
    out = measure_outcome({"recommended_irrigation_mm": 100.0}, {})  # لا مرصود
    assert _m(out, "irrigation")["status"] == "needs_data"
    assert _m(out, "yield")["status"] == "needs_data"
    assert out["data_completeness"] == 0.0


def test_data_completeness_and_counts():
    out = measure_outcome(
        {"recommended_irrigation_mm": 100.0, "predicted_stress_days": 2},
        {"actual_irrigation_mm": 100.0, "observed_stress_days": 1},
    )
    assert out["n_evaluated"] == 2  # ريّ + إجهاد
    assert out["data_completeness"] == 0.5  # 2 من 4 مقاييس
    assert out["calibrated"] is False


def test_empty_warns():
    out = measure_outcome({}, {})
    assert out["n_evaluated"] == 0
    assert any("قياسات ميدانيّة" in w for w in out["warnings_ar"])
