"""مقارنة GDD الظلّيّة لكلّ مستهلك (WS-C.1c) — الطريقة/السياسة مصنّفة لا مُذابة."""

from __future__ import annotations

from api.gdd_shadow import compare_gdd_shadow


def _engine(daily, acc, base=10.0, cutoff=30.0, method="simple"):
    return {
        "daily_gdd": daily,
        "accumulated_gdd": acc,
        "thresholds_used": {"base_c": base, "upper_cutoff_c": cutoff, "method": method},
    }


def test_same_method_and_policy_is_match():
    out = compare_gdd_shadow(
        legacy_daily=[10.0, 11.0],
        legacy_accumulated=21.0,
        legacy_method="simple",
        legacy_base_c=10.0,
        legacy_upper_cutoff_c=30.0,
        engine_product=_engine([10.0, 11.0], 21.0),
    )
    assert out["shadow_status"] == "match"
    assert out["accumulated_diff"] == 0.0
    assert out["method_mismatch"] is False
    assert out["policy_mismatch"] is False


def test_method_difference_is_flagged_not_hidden_by_tolerance():
    # حتّى لو تطابقت القيمة صدفةً، اختلاف الطريقة يظهر صراحةً.
    out = compare_gdd_shadow(
        legacy_daily=[10.0, 11.0],
        legacy_accumulated=21.0,
        legacy_method="modified",
        legacy_base_c=10.0,
        legacy_upper_cutoff_c=30.0,
        engine_product=_engine([10.0, 11.0], 21.0, method="simple"),
    )
    assert out["method_mismatch"] is True
    assert out["shadow_status"] == "method_mismatch"


def test_policy_difference_flagged():
    out = compare_gdd_shadow(
        legacy_daily=[10.0],
        legacy_accumulated=10.0,
        legacy_method="simple",
        legacy_base_c=0.0,  # عتبة مختلفة
        legacy_upper_cutoff_c=30.0,
        engine_product=_engine([10.0], 10.0, base=10.0),
    )
    assert out["policy_mismatch"] is True
    assert out["shadow_status"] == "policy_mismatch"


def test_value_diff_when_same_method_policy_but_numbers_differ():
    out = compare_gdd_shadow(
        legacy_daily=[10.0, 11.0],
        legacy_accumulated=21.0,
        legacy_method="simple",
        legacy_base_c=10.0,
        legacy_upper_cutoff_c=30.0,
        engine_product=_engine([12.0, 12.0], 24.0),
    )
    assert out["method_mismatch"] is False
    assert out["policy_mismatch"] is False
    assert out["accumulated_diff"] == 3.0
    assert out["shadow_status"] == "value_diff"


def test_missing_day_counted():
    out = compare_gdd_shadow(
        legacy_daily=[10.0, 11.0, 12.0],
        legacy_accumulated=33.0,
        legacy_method="simple",
        legacy_base_c=10.0,
        legacy_upper_cutoff_c=30.0,
        engine_product=_engine([10.0, None, 12.0], 22.0),
    )
    assert out["missing_day_count"] == 1


def test_rounding_noise_is_not_value_diff():
    # فرق تقريب دون دقّة المحرّك (3 منازل) لا يُعدّ value_diff.
    out = compare_gdd_shadow(
        legacy_daily=[10.0004],
        legacy_accumulated=10.0004,
        legacy_method="simple",
        legacy_base_c=10.0,
        legacy_upper_cutoff_c=30.0,
        engine_product=_engine([10.0], 10.0),
    )
    assert out["shadow_status"] == "match"
    assert out["accumulated_diff"] == 0.0
