"""اختبارات وحدة لمحرّك التغذية الراجعة نبات-تربة (PSFI) — نقيّ وحتميّ."""

from __future__ import annotations

import pytest
from core.soil_feedback_proxy import (
    PlantSoilFeedback,
    SoilFeedbackInputs,
    assess_plant_soil_feedback,
)

pytestmark = pytest.mark.unit


def _good_profile() -> SoilFeedbackInputs:
    """ملف إدارة جيّد: دورة متنوّعة، بقوليات، تغطية، إضافات عضويّة، حراثة منخفضة، SOC جيّد."""
    return SoilFeedbackInputs(
        rotation_diversity=0.9,
        legume_ratio=0.8,
        cover_crop_ratio=0.8,
        host_repeat_risk=0.05,
        organic_matter_additions_per_yr=4.0,
        tillage_intensity=0.05,
        soil_organic_carbon_pct=2.8,
        salinity_ds_m=0.5,
        disease_incidents_recent=0,
        synthetic_fertilizer_intensity=0.1,
    )


def _bad_profile() -> SoilFeedbackInputs:
    """ملف إدارة سيّئ: تكرار عائل، حراثة مكثّفة، ملوحة عالية، أمراض، إفراط أسمدة، بلا دورة."""
    return SoilFeedbackInputs(
        rotation_diversity=0.05,
        legume_ratio=0.0,
        cover_crop_ratio=0.0,
        host_repeat_risk=0.95,
        organic_matter_additions_per_yr=0.0,
        tillage_intensity=0.95,
        soil_organic_carbon_pct=0.4,
        salinity_ds_m=9.0,
        disease_incidents_recent=5,
        synthetic_fertilizer_intensity=0.95,
    )


def _all_scores(r: PlantSoilFeedback) -> list[float]:
    return [
        r.positive_feedback_score,
        r.negative_feedback_risk,
        r.pathogen_accumulation_risk,
        r.microbial_diversity_proxy,
        r.soil_resilience_score,
    ]


def test_good_profile_is_positive():
    r = assess_plant_soil_feedback(_good_profile())
    assert r.direction == "positive"
    assert r.positive_feedback_score >= 70.0
    assert r.negative_feedback_risk <= 30.0
    assert r.net_feedback > 0.0
    assert r.confidence == 1.0
    assert r.inputs_known == 10
    assert len(r.drivers_positive_ar) >= 3


def test_bad_profile_is_negative():
    r = assess_plant_soil_feedback(_bad_profile())
    assert r.direction == "negative"
    assert r.negative_feedback_risk >= 70.0
    assert r.pathogen_accumulation_risk >= 70.0
    assert r.net_feedback < 0.0
    assert len(r.drivers_negative_ar) >= 3


def test_all_none_is_neutral_no_crash():
    r = assess_plant_soil_feedback(SoilFeedbackInputs())
    assert r.direction == "neutral"
    assert r.inputs_known == 0
    assert r.confidence == pytest.approx(0.0)
    assert r.net_feedback == pytest.approx(0.0)
    assert "غير كافية" in r.verdict_ar
    assert r.drivers_positive_ar == ()
    assert r.drivers_negative_ar == ()


def test_partial_inputs_confidence_and_count():
    inp = SoilFeedbackInputs(
        rotation_diversity=0.7,
        legume_ratio=0.6,
        soil_organic_carbon_pct=2.0,
    )
    r = assess_plant_soil_feedback(inp)
    assert r.inputs_known == 3
    assert 0.0 < r.confidence < 1.0
    assert r.confidence == pytest.approx(0.3)


def test_scores_within_bounds_good():
    r = assess_plant_soil_feedback(_good_profile())
    for s in _all_scores(r):
        assert 0.0 <= s <= 100.0


def test_scores_within_bounds_bad():
    r = assess_plant_soil_feedback(_bad_profile())
    for s in _all_scores(r):
        assert 0.0 <= s <= 100.0


def test_net_feedback_identity_and_range():
    for inp in (_good_profile(), _bad_profile()):
        r = assess_plant_soil_feedback(inp)
        assert r.net_feedback == pytest.approx(
            r.positive_feedback_score - r.negative_feedback_risk, abs=1e-6
        )
        assert -100.0 <= r.net_feedback <= 100.0


def test_missing_input_not_treated_as_zero():
    """حذف مدخل واحد سالب لا يساوي ضبطه على صفر (إعادة معايرة الأوزان)."""
    base = SoilFeedbackInputs(host_repeat_risk=0.9, disease_incidents_recent=4)
    with_zero = SoilFeedbackInputs(
        host_repeat_risk=0.9,
        disease_incidents_recent=4,
        rotation_diversity=0.0,
    )
    r_missing = assess_plant_soil_feedback(base)
    r_zero = assess_plant_soil_feedback(with_zero)
    # إضافة rotation_diversity=0 ترفع خطر تراكم الممرضات (غياب التنوّع)، فلا يتساويان.
    assert r_zero.pathogen_accumulation_risk != r_missing.pathogen_accumulation_risk
    assert r_zero.inputs_known == r_missing.inputs_known + 1


def test_low_confidence_forces_neutral():
    """مدخل واحد فقط ⇒ ثقة دون الحدّ الأدنى ⇒ اتّجاه محايد مهما كانت القيمة."""
    r = assess_plant_soil_feedback(SoilFeedbackInputs(host_repeat_risk=1.0))
    assert r.inputs_known == 1
    assert r.confidence == pytest.approx(0.1)
    assert r.direction == "neutral"
    assert "شحيحة" in r.verdict_ar


def test_determinism():
    inp = _good_profile()
    assert assess_plant_soil_feedback(inp) == assess_plant_soil_feedback(inp)


def test_drivers_cite_actual_inputs():
    r = assess_plant_soil_feedback(_bad_profile())
    joined = " ".join(r.drivers_negative_ar)
    assert "العائل" in joined
    assert any("AMF" in d for d in r.drivers_negative_ar)
