"""اختبارات منتَج VPD الموحَّد + عقد الجودة (WS-C.1a) — تقوية شاملة.

يغطّي: قيَم مرجعيّة FAO-56 · رفض NaN/±inf لكلّ مدخل · قصّ سالب متدرّج · تحقّق متقاطع
RH/نقطة ندى (توافق/تعارُض) · أسبقيّة المسار الحتميّة · فصل completeness عن consistency ·
وحدات صريحة · قابليّة التسلسل JSON بلا NaN.
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vapor_pressure import saturation_vapor_pressure_kpa  # noqa: E402
from vpd import RH_DEWPOINT_VPD_TOLERANCE_KPA, compute_vpd  # noqa: E402

pytestmark = pytest.mark.unit


def test_svp_reference_values_fao56():
    assert abs(saturation_vapor_pressure_kpa(20.0) - 2.338) < 1e-3
    assert abs(saturation_vapor_pressure_kpa(30.0) - 4.243) < 1e-3


def test_rh_based_validated_full():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=50.0)
    assert out["method"] == "rh_based"
    assert out["quality_status"] == "validated"
    assert out["input_completeness"] == 1.0
    assert out["input_consistency"] == 1.0
    assert abs(out["es_kpa"] - 3.291) < 1e-2
    assert abs(out["vpd_kpa"] - 3.291 * 0.5) < 1e-2


def test_rh_zero_and_hundred_edges():
    assert compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=0.0)["ea_kpa"] == 0.0
    assert compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=100.0)["vpd_kpa"] == 0.0


# ── (1) رفض غير-المحدود لكلّ مدخل ──
@pytest.mark.parametrize(
    "kw",
    [
        {"t_max_c": float("nan"), "t_min_c": 20.0, "rh_mean_pct": 50.0},
        {"t_max_c": 30.0, "t_min_c": 20.0, "rh_mean_pct": float("nan")},
        {"t_max_c": 30.0, "t_min_c": 20.0, "dew_point_c": float("nan")},
        {"t_max_c": float("inf"), "t_min_c": 20.0, "rh_mean_pct": 50.0},
        {"t_max_c": 30.0, "t_min_c": 20.0, "rh_mean_pct": float("-inf")},
    ],
)
def test_non_finite_inputs_rejected_as_invalid(kw):
    out = compute_vpd(**kw)
    assert out["quality_status"] == "invalid"
    assert "non_finite_input" in out["quality_flags"]
    assert out["vpd_kpa"] is None


def test_out_of_physical_range_is_invalid():
    out = compute_vpd(t_max_c=200.0, t_min_c=20.0, rh_mean_pct=50.0)
    assert out["quality_status"] == "invalid"
    assert out["vpd_kpa"] is None


# ── (2) الاكتمال ──
def test_missing_temperature_insufficient():
    out = compute_vpd(t_max_c=None, rh_mean_pct=50.0)
    assert out["quality_status"] == "insufficient"
    assert out["vpd_kpa"] is None


def test_missing_humidity_and_dewpoint_insufficient():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0)
    assert out["quality_status"] == "insufficient"
    assert out["vpd_kpa"] is None


def test_partial_completeness_without_tmin_is_below_one():
    out = compute_vpd(t_max_c=30.0, rh_mean_pct=50.0)
    assert out["input_completeness"] < 1.0
    assert out["quality_status"] == "validated"  # صالح رغم اكتمال أقلّ


# ── (3) أسبقيّة المسار الحتميّة + التحقّق المتقاطع ──
def test_rh_absent_uses_dewpoint():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, dew_point_c=15.0)
    assert out["method"] == "dewpoint_based"


def test_rh_present_deterministic_primary_even_with_dewpoint():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=50.0, dew_point_c=15.0)
    assert out["method"] == "rh_based"  # حتميّ، لا «الأقرب»


def test_cross_check_agreement_validated():
    # dew=17.5 قرب RH~60% عند (30,20): المساران متقاربان ⇒ validated + cross_check.
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=60.0, dew_point_c=17.5)
    assert out["cross_check"] is not None
    assert out["cross_check"]["difference_kpa"] <= RH_DEWPOINT_VPD_TOLERANCE_KPA
    assert out["quality_status"] == "validated"


def test_cross_check_disagreement_flags_inconsistent():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=90.0, dew_point_c=5.0)
    assert out["method"] == "rh_based"
    assert out["quality_status"] == "inconsistent_inputs"
    assert "rh_dewpoint_disagreement" in out["quality_flags"]
    assert out["cross_check"]["difference_kpa"] > RH_DEWPOINT_VPD_TOLERANCE_KPA
    assert out["input_consistency"] < 1.0  # الاتّساق انخفض، والاكتمال يبقى مرتفعاً


# ── (4) القصّ السالب المتدرّج ──
def test_small_negative_vpd_degraded():
    # نقطة ندى أعلى بقليل جدّاً من الحرارة ⇒ سالب صغير ⇒ degraded (rounding).
    dew = 20.0 + 0.02  # es(20)≈2.338 ؛ e°(20.02) أكبر بقليل جدّاً
    out = compute_vpd(t_max_c=20.0, t_min_c=20.0, dew_point_c=dew)
    assert out["vpd_kpa"] == 0.0
    assert out["quality_status"] == "degraded"
    assert "negative_vpd_clamped" in out["quality_flags"]
    assert out["raw_vpd_kpa"] < 0.0


def test_large_negative_vpd_inconsistent():
    # نقطة ندى أعلى كثيراً ⇒ سالب كبير ⇒ inconsistent_inputs.
    out = compute_vpd(t_max_c=20.0, t_min_c=20.0, dew_point_c=35.0)
    assert out["vpd_kpa"] == 0.0
    assert out["quality_status"] == "inconsistent_inputs"
    assert out["raw_vpd_kpa"] < -0.01


# ── (5) الوحدات + التسلسل ──
def test_units_explicit_in_output():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=50.0)
    assert out["units"]["inputs"]["temperature_unit"] == "degC"
    assert out["units"]["inputs"]["relative_humidity_unit"] == "percent"
    assert out["units"]["output_unit"] == "kPa"
    assert out["formula_version"] == "vpd/fao56/1.0.0"


def test_json_serializable_no_invalid_nan():
    # allow_nan=False يرمي إن احتوى أيّ float قيمة NaN/inf غير صالحة (لا يتأثّر بنصّ
    # القيود الذي قد يذكر كلمة NaN وصفاً).
    for out in (
        compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=50.0),
        compute_vpd(t_max_c=float("nan"), rh_mean_pct=50.0),
        compute_vpd(t_max_c=None),
    ):
        json.dumps(out, allow_nan=False)  # ينجح فقط بلا NaN/inf فعليّ في الأرقام
