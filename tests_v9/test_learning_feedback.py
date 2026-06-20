"""اختبار حلقة التغذية الراجعة للتعلّم (#385) — نقيّ حتميّ، اقتراح لا تعديل.

يثبت: (أ) auto_adjust=False صريح؛ (ب) منطقة بلا عيّنات ⇒ collect_data أولويّة عالية؛
(ج) نسبة نجاح منخفضة ⇒ review_calibration + أهداف مراجعة (عائلات معاملات)؛ (د)
أوّليّ ⇒ verify؛ (هـ) مُتحقَّق جيّد ⇒ monitor؛ (و) الترتيب بالأولويّة؛ (ز) الملخّص.
بلا شبكة/قاعدة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

from api.learning_feedback import learning_feedback  # noqa: E402


def _ev(region, level="none", n=0, rate=None, flags=None):
    return {
        "region": region,
        "evidence_level": level,
        "sample_count": n,
        "success_rate": rate,
        "success_flag_counts": flags or {},
        "samples_to_verified": max(0, 30 - n),
    }


def test_auto_adjust_explicitly_false():
    out = learning_feedback([_ev("jawf")])
    assert out["auto_adjust"] is False
    assert out["calibrated"] is False


def test_no_samples_collect_data_high_priority():
    out = learning_feedback([_ev("jawf", level="none", n=0)])
    r = out["regions"][0]
    assert r["action"] == "collect_data"
    assert r["priority"] == 3
    assert "jawf" in out["summary"]["regions_needing_data"]


def test_low_success_triggers_review_with_targets():
    out = learning_feedback(
        [
            _ev(
                "tihama",
                level="field_preliminary",
                n=10,
                rate=0.3,
                flags={"irrigation_followed": 8, "yield_met": 1, "stress_avoided": 1},
            ),
        ]
    )
    r = out["regions"][0]
    assert r["action"] == "review_calibration"
    assert r["priority"] == 3
    # أضعف الجوانب (yield/stress) ⇒ عائلات معاملاتها مُرشَّحة للمراجعة.
    assert any(t in r["review_targets"] for t in ("kc_dyn_max", "uptake_fractions", "raw_fraction"))
    assert "tihama" in out["summary"]["regions_needing_review"]


def test_preliminary_good_is_verify():
    out = learning_feedback([_ev("marib", level="field_preliminary", n=10, rate=0.9)])
    assert out["regions"][0]["action"] == "verify"
    assert out["regions"][0]["priority"] == 2


def test_verified_good_is_monitor():
    out = learning_feedback([_ev("ibb", level="field_verified", n=40, rate=0.85)])
    assert out["regions"][0]["action"] == "monitor"
    assert out["regions"][0]["priority"] == 1


def test_sorted_by_priority_desc():
    out = learning_feedback(
        [
            _ev("ibb", level="field_verified", n=40, rate=0.85),  # monitor (1)
            _ev("jawf", level="none", n=0),  # collect_data (3)
        ]
    )
    assert out["regions"][0]["region"] == "jawf"  # الأولويّة الأعلى أوّلاً
    assert out["regions"][-1]["region"] == "ibb"


def test_summary_counts():
    out = learning_feedback(
        [
            _ev("jawf", level="none", n=0),
            _ev("tihama", level="field_preliminary", n=5, rate=0.8),
            _ev("ibb", level="field_verified", n=40, rate=0.9),
        ]
    )
    s = out["summary"]
    assert s["n_regions"] == 3
    assert s["n_none"] == 1
    assert s["n_preliminary"] == 1
    assert s["n_verified"] == 1
    assert s["mean_success_rate"] == pytest.approx((0.8 + 0.9) / 2, abs=1e-3)
