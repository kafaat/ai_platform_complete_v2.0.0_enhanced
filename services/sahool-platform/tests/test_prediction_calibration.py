"""اختبارات معايرة التنبّؤ (offline صرف — بلا قاعدة/شبكة).

تغطّي عقد الوحدة core/learning/prediction_calibration.py:
  • confidence_weight    — وزن shrinkage المتدرّج n/(n+K)
  • signed_error         — اتّجاه الخطأ + حماية actual<=0
  • analyze_systematic_bias — INSUFFICIENT / UNBIASED / OVER / UNDER
  • apply_calibration    — تطبيق المعامل + علم التعديل + الشرح
  • calibration_maturity — عدّ السياقات القابلة للمعايرة

المبدأ المُتحقَّق منه: تصحيح إحصائي حتمي، تدريجي (shrinkage)، شفّاف،
لا تصحيح قبل الكفاية (≥3 أزواج و≥2 مزرعة)، والاتّجاه صحيح:
إفراط ⇒ نُقلّل (factor<1)، تقليل ⇒ نرفع (factor>1).
"""

import pytest
from core.learning.prediction_calibration import (
    BIAS_SIGNIFICANCE,
    MAX_DAMPING,
    MIN_PAIRS_FOR_SIGNAL,
    SHRINKAGE_K,
    BiasType,
    PredictionPair,
    analyze_systematic_bias,
    apply_calibration,
    calibration_maturity,
    confidence_weight,
)

# ─── confidence_weight ───────────────────────────────────────────────────


def test_confidence_weight_zero_and_negative_is_zero():
    assert confidence_weight(0) == 0.0
    assert confidence_weight(-5) == 0.0


def test_confidence_weight_known_points():
    # n=10⇒0.25، n=30⇒0.50 (=SHRINKAGE_K)، n=90⇒0.75
    assert confidence_weight(10) == pytest.approx(0.25)
    assert confidence_weight(30) == pytest.approx(0.50)
    assert confidence_weight(90) == pytest.approx(0.75)


def test_confidence_weight_half_at_shrinkage_k():
    # نقطة نصف الثقة عند n=K
    assert confidence_weight(SHRINKAGE_K) == pytest.approx(0.5)


def test_confidence_weight_monotone_towards_one():
    assert confidence_weight(1000) > confidence_weight(100) > confidence_weight(10)
    assert confidence_weight(1_000_000) == pytest.approx(1.0, abs=1e-3)


# ─── signed_error ────────────────────────────────────────────────────────


def test_signed_error_overprediction_is_positive():
    # توقّع > فعلي ⇒ أفرطنا ⇒ موجب
    p = PredictionPair(predicted=12.0, actual=10.0, crop_id="wheat", tenant_id="t1")
    assert p.signed_error == pytest.approx(0.2)


def test_signed_error_underprediction_is_negative():
    # توقّع < فعلي ⇒ قلّلنا ⇒ سالب
    p = PredictionPair(predicted=8.0, actual=10.0, crop_id="wheat", tenant_id="t1")
    assert p.signed_error == pytest.approx(-0.2)


def test_signed_error_guards_nonpositive_actual():
    assert PredictionPair(10.0, 0.0, "wheat", "t1").signed_error == 0.0  # actual==0 ⇒ 0
    assert PredictionPair(10.0, -5.0, "wheat", "t1").signed_error == 0.0  # actual<0 ⇒ 0


# ─── analyze_systematic_bias: INSUFFICIENT ───────────────────────────────


def test_insufficient_too_few_pairs():
    # زوجان فقط (دون MIN_PAIRS_FOR_SIGNAL=3) ⇒ بلا إشارة، لا تصحيح
    pairs = [
        PredictionPair(12.0, 10.0, "wheat", "t1"),
        PredictionPair(13.0, 10.0, "wheat", "t2"),
    ]
    assert len(pairs) < MIN_PAIRS_FOR_SIGNAL
    out = analyze_systematic_bias(pairs)
    assert out["bias_type"] == BiasType.INSUFFICIENT.value
    assert out["correction_factor"] == 1.0
    assert out["can_calibrate"] is False


def test_insufficient_single_farm_even_with_many_pairs():
    # مزرعة واحدة فقط (pseudoreplication) رغم وفرة الأزواج ⇒ INSUFFICIENT
    pairs = [PredictionPair(13.0, 10.0, "wheat", "t1") for _ in range(8)]
    out = analyze_systematic_bias(pairs)
    assert out["n_farms"] == 1
    assert out["bias_type"] == BiasType.INSUFFICIENT.value
    assert out["correction_factor"] == 1.0
    assert out["can_calibrate"] is False


# ─── analyze_systematic_bias: UNBIASED ───────────────────────────────────


def test_unbiased_when_mean_signed_error_near_zero():
    # أخطاء متعاكسة عبر مزرعتين ⇒ متوسّط موقّع ~0 ⇒ لا تصحيح اتّجاهي
    pairs = [
        PredictionPair(11.0, 10.0, "wheat", "t1"),  # +0.10
        PredictionPair(9.0, 10.0, "wheat", "t2"),  # -0.10
        PredictionPair(10.2, 10.0, "wheat", "t1"),  # +0.02
        PredictionPair(9.8, 10.0, "wheat", "t2"),  # -0.02
    ]
    out = analyze_systematic_bias(pairs)
    assert abs(out["mean_signed_bias"]) < BIAS_SIGNIFICANCE
    assert out["bias_type"] == BiasType.UNBIASED.value
    assert out["correction_factor"] == 1.0
    assert out["can_calibrate"] is False


# ─── analyze_systematic_bias: OVER / UNDER ───────────────────────────────


def test_overprediction_yields_correction_below_one():
    # نُفرط منهجيّاً (توقّع > فعلي) ⇒ انحياز موجب ⇒ نُقلّل التنبّؤ (factor<1)
    pairs = [
        PredictionPair(13.0, 10.0, "wheat", "t1"),  # +0.30
        PredictionPair(12.0, 10.0, "wheat", "t2"),  # +0.20
        PredictionPair(13.0, 10.0, "wheat", "t1"),  # +0.30
        PredictionPair(12.0, 10.0, "wheat", "t2"),  # +0.20
    ]
    out = analyze_systematic_bias(pairs)
    assert out["bias_type"] == BiasType.OVERPREDICTION.value
    assert out["mean_signed_bias"] > 0
    assert out["correction_factor"] < 1.0
    assert out["can_calibrate"] is True
    # المعامل = 1 - mean*weight*MAX_DAMPING
    n = len(pairs)
    weight = n / (n + SHRINKAGE_K)
    expected = round(1.0 - out["mean_signed_bias"] * weight * MAX_DAMPING, 4)
    assert out["correction_factor"] == pytest.approx(expected)


def test_underprediction_yields_correction_above_one():
    # نُقلّل منهجيّاً (توقّع < فعلي) ⇒ انحياز سالب ⇒ نرفع التنبّؤ (factor>1)
    pairs = [
        PredictionPair(7.0, 10.0, "wheat", "t1"),  # -0.30
        PredictionPair(8.0, 10.0, "wheat", "t2"),  # -0.20
        PredictionPair(7.0, 10.0, "wheat", "t1"),  # -0.30
        PredictionPair(8.0, 10.0, "wheat", "t2"),  # -0.20
    ]
    out = analyze_systematic_bias(pairs)
    assert out["bias_type"] == BiasType.UNDERPREDICTION.value
    assert out["mean_signed_bias"] < 0
    assert out["correction_factor"] > 1.0
    assert out["can_calibrate"] is True


def test_correction_damping_capped_below_full_bias():
    # حتّى مع وزن كبير، حجم التصحيح ≤ |الانحياز| × MAX_DAMPING (حذر دائم)
    pairs = [PredictionPair(13.0, 10.0, "wheat", f"t{i % 2}") for i in range(60)]
    out = analyze_systematic_bias(pairs)
    bias = out["mean_signed_bias"]
    applied = 1.0 - out["correction_factor"]
    # التصحيح المطبّق لا يتجاوز الانحياز كاملاً × سقف الحذر
    assert applied <= abs(bias) * MAX_DAMPING + 1e-9


# ─── apply_calibration ───────────────────────────────────────────────────


def test_apply_calibration_scales_and_flags_adjusted():
    calib = {"correction_factor": 0.9}
    out = apply_calibration(100.0, calib)
    assert out["calibrated_prediction"] == pytest.approx(90.0)
    assert out["correction_factor"] == 0.9
    assert out["adjusted"] is True
    assert out["delta_pct"] == pytest.approx(-10.0)
    assert "تصحيح" in out["explanation_ar"]


def test_apply_calibration_no_adjustment_path():
    # factor==1.0 ⇒ لا تعديل + شرح يوضّح غياب التصحيح
    out = apply_calibration(100.0, {"correction_factor": 1.0})
    assert out["calibrated_prediction"] == pytest.approx(100.0)
    assert out["adjusted"] is False
    assert out["delta_pct"] == pytest.approx(0.0)
    assert "بلا تصحيح" in out["explanation_ar"]


def test_apply_calibration_defaults_to_neutral_factor():
    # غياب correction_factor ⇒ 1.0 (محايد)
    out = apply_calibration(50.0, {})
    assert out["correction_factor"] == 1.0
    assert out["adjusted"] is False
    assert out["calibrated_prediction"] == pytest.approx(50.0)


# ─── calibration_maturity ────────────────────────────────────────────────


def test_calibration_maturity_counts_calibrated_contexts():
    over = [PredictionPair(13.0, 10.0, "wheat", f"t{i % 2}") for i in range(4)]
    insufficient = [PredictionPair(13.0, 10.0, "barley", "t1")]  # زوج واحد، مزرعة واحدة
    out = calibration_maturity({"wheat:north": over, "barley:south": insufficient})
    assert out["total_contexts"] == 2
    assert out["calibrated_contexts"] == 1  # القمح فقط قابل للمعايرة
    assert out["per_context"]["wheat:north"]["can_calibrate"] is True
    assert out["per_context"]["barley:south"]["can_calibrate"] is False


def test_calibration_maturity_empty_is_zero():
    out = calibration_maturity({})
    assert out["total_contexts"] == 0
    assert out["calibrated_contexts"] == 0
