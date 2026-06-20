"""اختبار المعايرة التكيّفيّة (#388) — نقيّ حتميّ، مُبوَّب وعكوسيّ ومحدود.

يثبت: (أ) دليل غير كافٍ ⇒ gated بلا اقتراح؛ (ب) دليل كافٍ بلا إشارة ⇒ no_signal؛
(ج) إجهاد أسوأ ⇒ خفض p (ريّ أبكر) بخطوة محدودة؛ (د) إجهاد أقلّ ⇒ رفع p؛ (هـ) الخطوة
مقصوصة ≤0.05 والنطاق [0.30,0.70]؛ (و) applied=False دائماً (لا تعديل خفيّ) + عكوسيّة؛
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

from api.adaptive_calibration import propose_calibration_adjustment  # noqa: E402


def _prof(p=0.5, region="jawf"):
    return {"region": region, "raw_fraction": p}


def _ev(level="field_verified", n=40):
    return {"evidence_level": level, "sample_count": n}


def test_insufficient_evidence_gated():
    out = propose_calibration_adjustment(
        _prof(), _ev(level="field_preliminary", n=5), mean_stress_delta=2.0
    )
    assert out["status"] == "gated"
    assert out["gate"]["passed"] is False
    assert out["proposals"] == []
    assert out["applied"] is False


def test_sufficient_evidence_no_signal():
    out = propose_calibration_adjustment(_prof(), _ev(), mean_stress_delta=None)
    assert out["status"] == "no_signal"
    assert out["gate"]["passed"] is True
    assert out["proposals"] == []


def test_worse_stress_lowers_p():
    out = propose_calibration_adjustment(_prof(p=0.5), _ev(), mean_stress_delta=2.0)
    assert out["status"] == "auto_apply_eligible"
    prop = out["proposals"][0]
    assert prop["parameter"] == "raw_fraction"
    assert prop["proposed"] < 0.5  # خفض p ⇒ ريّ أبكر
    assert out["previous_values"]["raw_fraction"] == 0.5


def test_less_stress_raises_p():
    out = propose_calibration_adjustment(_prof(p=0.5), _ev(), mean_stress_delta=-2.0)
    assert out["proposals"][0]["proposed"] > 0.5  # رفع p ⇒ ريّ أقلّ


def test_step_bounded_and_clamped():
    # إشارة ضخمة ⇒ الخطوة مقصوصة عند 0.05.
    out = propose_calibration_adjustment(_prof(p=0.5), _ev(), mean_stress_delta=100.0)
    assert abs(out["proposals"][0]["delta"]) <= 0.05 + 1e-9
    # عند الحدّ الأدنى ⇒ لا يخرج عن النطاق.
    low = propose_calibration_adjustment(_prof(p=0.30), _ev(), mean_stress_delta=100.0)
    assert low["proposals"] == [] or low["proposals"][0]["proposed"] >= 0.30
    assert low["status"] in {"no_change_at_bound", "auto_apply_eligible"}


def test_applied_always_false_and_reversible():
    out = propose_calibration_adjustment(_prof(), _ev(), mean_stress_delta=2.0)
    assert out["applied"] is False  # لا تعديل خفيّ
    assert out["reversible"] is True
    assert "raw_fraction" in out["previous_values"]


def test_calibrated_false():
    out = propose_calibration_adjustment(_prof(), _ev(), mean_stress_delta=2.0)
    assert out["calibrated"] is False
