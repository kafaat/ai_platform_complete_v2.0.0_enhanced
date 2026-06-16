"""اختبارات Compositional Confidence (api.confidence_aggregation) — دوالّ نقيّة offline.

تتحقّق من الـweighted geometric mean، رفض المدخلات الحرجة المفقودة (→ very_low/0)،
penalty المدخلات غير الحرجة المفقودة، تصنيف degraded (< 0.5)، خرائط المستوى من
`level_from_score`، خاصّيّة `safe_for_action`، و`to_dict`، إضافةً إلى وصفات الـpresets
(ري/تسميد/توقّع إنتاج). القيم المتوقّعة مُشتقّة حرفيّاً من الكود (geometric mean،
الأوزان، العتبات) لا من افتراضات.
"""

import math

import pytest
from api.confidence_aggregation import (
    AggregatedConfidence,
    ConfidenceInput,
    aggregate,
    fertilizer_confidence,
    irrigation_confidence,
    yield_prediction_confidence,
)
from api.confidence_engine import ConfidenceLevel

pytestmark = pytest.mark.unit


def _gm(pairs):
    """geometric mean مرجعيّ: pairs = [(score, weight), ...]."""
    wls = sum(w * math.log(max(0.01, min(1.0, s))) for s, w in pairs)
    tw = sum(w for _, w in pairs)
    return math.exp(wls / tw)


# ─── aggregate: المسارات الأساسيّة ───────────────────────────────


def test_empty_inputs_returns_very_low_zero():
    r = aggregate([])
    assert r.score == 0.0
    assert r.level == ConfidenceLevel.VERY_LOW
    assert r.inputs_used == []
    assert r.inputs_missing == []
    assert r.inputs_degraded == []
    assert r.rationale_ar == "لا توجد أيّ مدخلات للحساب"


def test_single_input_geometric_mean_equals_score():
    # مدخل واحد بوزن واحد ⇒ geometric mean = score نفسه.
    r = aggregate([ConfidenceInput("ndvi", 0.8)])
    assert r.score == 0.8
    assert r.level == ConfidenceLevel.HIGH
    assert r.inputs_used == ["ndvi"]
    assert r.inputs_degraded == []


def test_equal_weight_geometric_mean_matches_reference():
    r = aggregate([ConfidenceInput("a", 0.9), ConfidenceInput("b", 0.4)])
    assert r.score == round(_gm([(0.9, 1.0), (0.4, 1.0)]), 3)
    assert r.score == 0.6  # = sqrt(0.9*0.4)=0.6 ⇒ MEDIUM
    assert r.level == ConfidenceLevel.MEDIUM
    # b ضعيف (< 0.5) ⇒ degraded.
    assert r.inputs_degraded == ["b"]


def test_weighted_geometric_mean_respects_weights():
    # وزن أكبر للقيمة العالية يرفع المجموع فوق المتوسّط الهندسيّ المتساوي.
    r = aggregate([ConfidenceInput("hi", 0.9, weight=3.0), ConfidenceInput("lo", 0.4, weight=1.0)])
    assert r.score == round(_gm([(0.9, 3.0), (0.4, 1.0)]), 3)
    assert r.score > 0.6  # أعلى من الحالة المتساوية الأوزان


def test_geometric_mean_penalizes_weak_component():
    # geometric mean: مكوّن ضعيف واحد يخفض المجموع كثيراً (الفلسفة المُعلنة).
    arithmetic = (1.0 + 0.04) / 2
    r = aggregate([ConfidenceInput("a", 1.0), ConfidenceInput("b", 0.04)])
    assert r.score < arithmetic


# ─── aggregate: المدخلات الحرجة المفقودة ─────────────────────────


def test_missing_critical_input_rejects_to_very_low():
    r = aggregate(
        [
            ConfidenceInput("ndvi", 0.95, weight=1.0),
            ConfidenceInput("et0", 0.0, weight=1.0, is_critical=True, is_present=False),
        ]
    )
    assert r.score == 0.0
    assert r.level == ConfidenceLevel.VERY_LOW
    assert r.inputs_missing == ["et0"]
    # ما زال يُسجّل المدخلات المستعملة في حقل inputs_used.
    assert r.inputs_used == ["ndvi"]
    assert "et0" in r.rationale_ar
    assert r.safe_for_action is False


def test_multiple_missing_critical_all_listed():
    r = aggregate(
        [
            ConfidenceInput("a", 0.0, is_critical=True, is_present=False),
            ConfidenceInput("b", 0.0, is_critical=True, is_present=False),
        ]
    )
    assert r.inputs_missing == ["a", "b"]
    assert r.score == 0.0


def test_all_inputs_missing_non_critical_returns_very_low():
    # لا حرِج مفقود لكنّ كلّ المدخلات غائبة ⇒ total_weight == 0 ⇒ very_low.
    r = aggregate(
        [
            ConfidenceInput("a", 0.9, is_present=False),
            ConfidenceInput("b", 0.9, is_present=False),
        ]
    )
    assert r.score == 0.0
    assert r.level == ConfidenceLevel.VERY_LOW
    assert r.inputs_used == []
    assert r.inputs_missing == []
    assert r.rationale_ar == "جميع المدخلات مفقودة"


# ─── aggregate: penalty للـnon-critical المفقودة ─────────────────


def test_missing_non_critical_applies_proportional_penalty():
    # present=1.0 (gm=1.0)، مفقود غير حرج بوزن 1.0 ⇒ penalty = 1/(1+1) = 0.5.
    r = aggregate(
        [
            ConfidenceInput("a", 1.0, weight=1.0),
            ConfidenceInput("b", 0.5, weight=1.0, is_critical=False, is_present=False),
        ]
    )
    assert r.score == 0.5
    assert "وحدات وزن" in r.rationale_ar


def test_penalty_factor_matches_weight_formula():
    # present score 0.81 وزن 2، مفقود غير حرج وزن 1 ⇒ * 2/3.
    base = _gm([(0.81, 2.0)])
    expected = round(base * (2.0 / (2.0 + 1.0)), 3)
    r = aggregate(
        [
            ConfidenceInput("a", 0.81, weight=2.0),
            ConfidenceInput("b", 0.0, weight=1.0, is_present=False),
        ]
    )
    assert r.score == expected


# ─── aggregate: clamping وحدود degraded ──────────────────────────


def test_score_clamped_above_one_via_floor_on_zero():
    # score=0 يُقصّ إلى 0.01 (floor) لتجنّب log(0)؛ لا يرفع استثناء.
    r = aggregate([ConfidenceInput("a", 0.0)])
    assert r.score == 0.01
    assert r.level == ConfidenceLevel.VERY_LOW
    assert r.inputs_degraded == ["a"]  # 0.0 < 0.5


def test_negative_score_clamped_to_floor():
    r = aggregate([ConfidenceInput("a", -5.0)])
    assert r.score == 0.01
    assert r.inputs_degraded == ["a"]


def test_score_above_one_clamped_to_one():
    # score > 1 يُقصّ داخل الحلقة إلى 1.0 ⇒ المجموع = 1.0.
    r = aggregate([ConfidenceInput("a", 5.0)])
    assert r.score == 1.0
    assert r.level == ConfidenceLevel.HIGH
    assert r.inputs_degraded == []


def test_degraded_boundary_exactly_half_is_not_degraded():
    # العتبة صارمة: score < 0.5 ⇒ degraded؛ 0.5 بالضبط ليست degraded.
    r = aggregate([ConfidenceInput("a", 0.5)])
    assert r.inputs_degraded == []
    r2 = aggregate([ConfidenceInput("a", 0.49)])
    assert r2.inputs_degraded == ["a"]


# ─── level_from_score: حدود المستويات عبر aggregate ──────────────


def test_level_thresholds_at_boundaries():
    # 0.80→HIGH، 0.55→MEDIUM، 0.35→LOW، أقلّ→VERY_LOW (عتبات شاملة من الأسفل).
    assert aggregate([ConfidenceInput("a", 0.80)]).level == ConfidenceLevel.HIGH
    assert aggregate([ConfidenceInput("a", 0.79)]).level == ConfidenceLevel.MEDIUM
    assert aggregate([ConfidenceInput("a", 0.55)]).level == ConfidenceLevel.MEDIUM
    assert aggregate([ConfidenceInput("a", 0.54)]).level == ConfidenceLevel.LOW
    assert aggregate([ConfidenceInput("a", 0.35)]).level == ConfidenceLevel.LOW
    assert aggregate([ConfidenceInput("a", 0.34)]).level == ConfidenceLevel.VERY_LOW


# ─── safe_for_action + to_dict ───────────────────────────────────


def test_safe_for_action_true_for_high_with_no_missing():
    r = aggregate([ConfidenceInput("a", 0.9)])
    assert r.level == ConfidenceLevel.HIGH
    assert r.safe_for_action is True


def test_safe_for_action_false_for_low_level():
    r = aggregate([ConfidenceInput("a", 0.4)])  # LOW
    assert r.safe_for_action is False


def test_to_dict_round_trips_fields():
    r = aggregate([ConfidenceInput("ndvi", 0.9), ConfidenceInput("soil", 0.4)])
    d = r.to_dict()
    assert d["score"] == r.score
    assert d["level"] == r.level.value  # القيمة النصّيّة لا الـEnum
    assert d["inputs_used"] == ["ndvi", "soil"]
    assert d["inputs_degraded"] == ["soil"]
    assert d["safe_for_action"] == r.safe_for_action
    assert isinstance(d["rationale_ar"], str)


def test_aggregated_confidence_is_dataclass_instance():
    r = aggregate([ConfidenceInput("a", 0.9)])
    assert isinstance(r, AggregatedConfidence)


# ─── irrigation_confidence preset ────────────────────────────────


def test_irrigation_all_present_equal_scores():
    # كلّ المدخلات 0.8 حاضرة ⇒ geometric mean = 0.8 (أوزان لا تؤثّر عند التساوي).
    r = irrigation_confidence(0.8, 0.8, 0.8, 0.8)
    assert r.score == 0.8
    assert r.level == ConfidenceLevel.HIGH
    assert set(r.inputs_used) == {"ndvi", "et0", "soil_moisture", "weather_forecast"}
    assert r.safe_for_action is True


def test_irrigation_missing_critical_et0_rejects():
    # et0 حرِج (is_critical=True) ⇒ غيابه يرفض التوصية إلى very_low.
    r = irrigation_confidence(0.9, None, 0.9, 0.9)
    assert r.score == 0.0
    assert r.level == ConfidenceLevel.VERY_LOW
    assert r.inputs_missing == ["et0"]
    assert r.safe_for_action is False


def test_irrigation_missing_non_critical_ndvi_applies_penalty():
    # ndvi غير حرِج (وزن 0.30) ⇒ غيابه penalty لا رفض.
    r = irrigation_confidence(None, 0.9, 0.9, 0.9)
    present = _gm([(0.9, 0.35), (0.9, 0.25), (0.9, 0.10)])
    tw = 0.35 + 0.25 + 0.10
    expected = round(present * (tw / (tw + 0.30)), 3)
    assert r.score == expected
    assert r.score == 0.63
    assert r.inputs_missing == []  # لا حرِج مفقود
    assert "et0" in r.inputs_used


def test_irrigation_none_treated_as_absent_not_zero():
    # None ⇒ is_present=False؛ لا يُحسب كـ0 داخل الـgeometric mean.
    r_none = irrigation_confidence(None, 0.9, 0.9, 0.9)
    # بينما 0.0 صريح للـndvi حاضر ⇒ degraded ويُسحب المجموع لأسفل.
    r_zero = irrigation_confidence(0.0, 0.9, 0.9, 0.9)
    assert r_zero.score < r_none.score
    assert "ndvi" in r_zero.inputs_degraded


# ─── fertilizer_confidence preset ────────────────────────────────


def test_fertilizer_crop_stage_known_full():
    r = fertilizer_confidence(0.9, 0.9, crop_stage_known=True)
    expected = round(_gm([(0.9, 0.50), (0.9, 0.30), (1.0, 0.20)]), 3)
    assert r.score == expected
    assert set(r.inputs_used) == {"soil_lab", "ndvi", "crop_stage"}


def test_fertilizer_crop_stage_unknown_marks_absent():
    # crop_stage_known=False ⇒ is_present=False ⇒ penalty (وزن 0.20 مفقود).
    r = fertilizer_confidence(0.9, 0.9, crop_stage_known=False)
    present = _gm([(0.9, 0.50), (0.9, 0.30)])
    tw = 0.50 + 0.30
    expected = round(present * (tw / (tw + 0.20)), 3)
    assert r.score == expected
    assert r.score == 0.72
    assert "crop_stage" not in r.inputs_used


def test_fertilizer_missing_critical_soil_lab_rejects():
    # soil_lab حرِج ⇒ غيابه يرفض إلى very_low.
    r = fertilizer_confidence(None, 0.9, crop_stage_known=True)
    assert r.score == 0.0
    assert r.inputs_missing == ["soil_lab"]
    assert r.level == ConfidenceLevel.VERY_LOW


# ─── yield_prediction_confidence preset ──────────────────────────


def test_yield_full_history_high():
    r = yield_prediction_confidence(0.9, lifecycle_complete=True, sample_count=3)
    # lifecycle=1.0، soil_samples=min(1, 3/3)=1.0.
    expected = round(_gm([(0.9, 0.45), (1.0, 0.35), (1.0, 0.20)]), 3)
    assert r.score == expected
    assert r.score == 0.954
    assert r.level == ConfidenceLevel.HIGH


def test_yield_incomplete_lifecycle_uses_low_proxy():
    # lifecycle_complete=False ⇒ score 0.3 (دائماً present)؛ sample_count=0 ⇒ soil غائب.
    r = yield_prediction_confidence(0.9, lifecycle_complete=False, sample_count=0)
    present = _gm([(0.9, 0.45), (0.3, 0.35)])
    tw = 0.45 + 0.35
    expected = round(present * (tw / (tw + 0.20)), 3)
    assert r.score == expected
    assert r.score == 0.445
    # lifecycle_history=0.3 < 0.5 ⇒ degraded.
    assert "lifecycle_history" in r.inputs_degraded
    assert "soil_samples" not in r.inputs_used  # sample_count=0 ⇒ absent


def test_yield_missing_critical_ndvi_rejects():
    r = yield_prediction_confidence(None, lifecycle_complete=True, sample_count=3)
    assert r.score == 0.0
    assert r.inputs_missing == ["ndvi_history"]
    assert r.level == ConfidenceLevel.VERY_LOW


def test_yield_soil_samples_partial_clamped_below_one():
    # sample_count=1 ⇒ soil_samples = 1/3 ≈ 0.333 ⇒ present و degraded (< 0.5).
    r = yield_prediction_confidence(0.9, lifecycle_complete=True, sample_count=1)
    expected = round(_gm([(0.9, 0.45), (1.0, 0.35), (1.0 / 3.0, 0.20)]), 3)
    assert r.score == expected
    assert "soil_samples" in r.inputs_used
    assert "soil_samples" in r.inputs_degraded


def test_yield_soil_samples_above_three_clamped_to_one():
    # sample_count=10 ⇒ min(1.0, 10/3)=1.0 ⇒ نفس نتيجة sample_count=3.
    r_big = yield_prediction_confidence(0.9, lifecycle_complete=True, sample_count=10)
    r_three = yield_prediction_confidence(0.9, lifecycle_complete=True, sample_count=3)
    assert r_big.score == r_three.score
