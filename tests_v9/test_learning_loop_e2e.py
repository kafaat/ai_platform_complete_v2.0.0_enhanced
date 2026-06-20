"""اختبار حلقة التعلّم المغلقة من طرف لطرف (Closed Learning Loop E2E) — نقيّ حتميّ.

يثبت أنّ السلسلة الكاملة تتركّب بصدق دون أيّ تعديل خفيّ:
  measure_outcome → aggregate_evidence → learning_feedback / propose_calibration_adjustment

  • دليل قليل (~5 عيّنات ميدانيّة) ⇒ field_preliminary ⇒ إجراء verify/collect_data ⇒
    اقتراح المعايرة مُبوَّب (gated) رغم وجود إشارة اتّجاه.
  • دليل كافٍ (30 عيّنة مُتحقَّقة) + إشارة إجهاد أسوأ ⇒ auto_apply_eligible يخفض p،
    و applied=False (لا تعديل خفيّ).
  • دليل كافٍ بلا إشارة اتّجاه ⇒ no_signal.
  • أعلام النجاح تتدفّق من القياس إلى عدّادات الدليل ونسبة نجاح ضمن [0,1].

بلا شبكة/قاعدة — منطق صرف حتميّ.
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
from api.evidence_registry import aggregate_evidence  # noqa: E402
from api.learning_feedback import learning_feedback  # noqa: E402
from api.outcome_measurement import measure_outcome  # noqa: E402


def _good_outcome() -> dict:
    """نتيجة قياس فيها أطراف مُخطَّط/مرصود لكلّ مقياس ⇒ تُقيَّم كلّها (عيّنة صالحة)."""
    planned = {
        "recommended_irrigation_mm": 100.0,
        "predicted_stress_days": 4,
        "expected_yield_t_ha": 5.0,
        "season_budget_mm": 600.0,
    }
    actual = {
        "actual_irrigation_mm": 100.0,  # ضمن الهامش ⇒ irrigation_followed
        "observed_stress_days": 0,  # < المتنبَّأ ⇒ stress_better + stress_avoided
        "actual_yield_t_ha": 5.2,  # تجاوز ⇒ yield_met
        "actual_water_used_mm": 580.0,  # ضمن الميزانيّة ⇒ water_within_budget
    }
    return measure_outcome(planned, actual)


def test_loop_gated_with_few_field_outcomes():
    """5 نتائج ميدانيّة ⇒ دليل أوّليّ ⇒ تغذية راجعة verify/collect ⇒ اقتراح مُبوَّب."""
    outcomes = [_good_outcome() for _ in range(5)]
    # كلّ نتيجة قابلة للتقييم (كلّ المقاييس لها طرفاها).
    assert all(o["n_evaluated"] == 4 for o in outcomes)

    evidence = aggregate_evidence("jawf", outcomes)
    assert evidence["sample_count"] == 5
    assert evidence["evidence_level"] == "field_preliminary"

    fb = learning_feedback([evidence])
    region_fb = next(r for r in fb["regions"] if r["region"] == "jawf")
    assert region_fb["action"] in {"verify", "collect_data"}
    assert fb["auto_adjust"] is False

    proposal = propose_calibration_adjustment(
        {"region": "jawf", "raw_fraction": 0.5}, evidence, mean_stress_delta=2.0
    )
    assert proposal["status"] == "gated"
    assert proposal["gate"]["passed"] is False
    assert proposal["proposals"] == []

    # لا تطبيق خفيّ في أيّ حلقة من السلسلة.
    assert all(o["calibrated"] is False for o in outcomes)
    assert evidence["calibrated"] is False
    assert fb["calibrated"] is False
    assert proposal["applied"] is False


def test_loop_eligible_after_enough_verified_evidence():
    """30 نتيجة مُتحقَّقة + إجهاد أسوأ ⇒ auto_apply_eligible يخفض p بلا تطبيق خفيّ."""
    outcomes = [_good_outcome() for _ in range(30)]
    evidence = aggregate_evidence("jawf", outcomes)
    assert evidence["sample_count"] == 30
    assert evidence["evidence_level"] == "field_verified"

    region_profile = {"region": "jawf", "raw_fraction": 0.5}
    proposal = propose_calibration_adjustment(region_profile, evidence, mean_stress_delta=2.0)
    assert proposal["status"] == "auto_apply_eligible"
    assert proposal["proposals"][0]["proposed"] < proposal["proposals"][0]["current"]
    assert proposal["proposals"][0]["proposed"] < 0.5  # خفض raw_fraction
    assert proposal["applied"] is False  # لا تعديل خفيّ

    # المُدخل لم يُطفَّر (نقاء): raw_fraction كما هو، والقيمة السابقة محفوظة للعكوسيّة.
    assert region_profile["raw_fraction"] == 0.5
    assert proposal["previous_values"]["raw_fraction"] == 0.5


def test_loop_no_signal_when_evidence_but_no_direction():
    """30 نتيجة مُتحقَّقة لكن بلا فرق إجهاد ⇒ no_signal (الدليل كافٍ، لا إشارة)."""
    outcomes = [_good_outcome() for _ in range(30)]
    evidence = aggregate_evidence("jawf", outcomes)
    assert evidence["evidence_level"] == "field_verified"

    proposal = propose_calibration_adjustment(
        {"region": "jawf", "raw_fraction": 0.5}, evidence, mean_stress_delta=None
    )
    assert proposal["status"] == "no_signal"
    assert proposal["gate"]["passed"] is True
    assert proposal["proposals"] == []
    assert proposal["applied"] is False


def test_outcome_to_evidence_success_flags_flow():
    """أعلام النجاح تتدفّق من القياس إلى عدّادات الدليل، ونسبة النجاح ضمن [0,1]."""
    # نتيجة ناجحة كاملة: تُنتج irrigation_followed + stress_better + stress_avoided
    # + yield_met + water_within_budget.
    success = _good_outcome()
    assert "irrigation_followed" in success["success_flags"]
    assert "stress_avoided" in success["success_flags"]

    # نتيجة فاشلة جزئيّاً: ريّ ناقص + إجهاد أسوأ + إنتاج دون الهدف + تجاوز الميزانيّة.
    fail = measure_outcome(
        {
            "recommended_irrigation_mm": 100.0,
            "predicted_stress_days": 2,
            "expected_yield_t_ha": 5.0,
            "season_budget_mm": 600.0,
        },
        {
            "actual_irrigation_mm": 50.0,  # under ⇒ لا irrigation_followed
            "observed_stress_days": 6,  # worse ⇒ لا stress_*
            "actual_yield_t_ha": 3.0,  # below ⇒ لا yield_met
            "actual_water_used_mm": 700.0,  # exceeded ⇒ لا water_within_budget
        },
    )
    assert fail["success_flags"] == []
    assert fail["n_evaluated"] == 4  # عيّنة صالحة رغم فشل القرار

    outcomes = [success, success, fail]
    evidence = aggregate_evidence("jawf", outcomes)
    assert evidence["sample_count"] == 3

    counts = evidence["success_flag_counts"]
    assert counts["irrigation_followed"] == 2  # من النتيجتين الناجحتين فقط
    assert counts["stress_avoided"] == 2
    assert counts["water_within_budget"] == 2
    assert "stress_better" in counts

    rate = evidence["success_rate"]
    assert rate is not None
    assert 0.0 <= rate <= 1.0
