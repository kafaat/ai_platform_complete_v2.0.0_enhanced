"""اختبارات منتَج VPD الموحَّد (WS-C.1a) — صيغة/عقد واحد + حالات حدّيّة + fail-closed."""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vapor_pressure import saturation_vapor_pressure_kpa  # noqa: E402
from vpd import compute_vpd  # noqa: E402

pytestmark = pytest.mark.unit


def test_svp_reference_values_fao56():
    # قيَم مرجعيّة FAO-56: e°(20)=2.338، e°(30)=4.243 kPa.
    assert abs(saturation_vapor_pressure_kpa(20.0) - 2.338) < 1e-3
    assert abs(saturation_vapor_pressure_kpa(30.0) - 4.243) < 1e-3


def test_rh_based_full_path():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=50.0)
    assert out["method"] == "rh_based"
    assert out["input_completeness"] == "full"
    assert out["quality_status"] == "ok"
    # es = (4.243+2.338)/2 = 3.2905 ؛ ea = es*0.5 ؛ vpd = es*0.5
    assert abs(out["es_kpa"] - 3.291) < 1e-2
    assert abs(out["vpd_kpa"] - 3.291 * 0.5) < 1e-2


def test_rh_zero_gives_max_vpd():
    # RH=0 ⇒ ea=0 ⇒ VPD = es (أقصى نقص).
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=0.0)
    assert out["ea_kpa"] == 0.0
    assert abs(out["vpd_kpa"] - out["es_kpa"]) < 1e-9


def test_rh_hundred_gives_zero_vpd():
    # RH=100 ⇒ ea=es ⇒ VPD=0 (تشبّع تامّ).
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=100.0)
    assert out["vpd_kpa"] == 0.0


def test_missing_temperature_is_insufficient():
    out = compute_vpd(t_max_c=None, rh_mean_pct=50.0)
    assert out["method"] == "insufficient"
    assert out["quality_status"] == "insufficient_inputs"
    assert out["vpd_kpa"] is None  # مفقود ≠ صفر


def test_missing_humidity_and_dewpoint_is_insufficient():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0)  # لا RH ولا نقطة ندى
    assert out["method"] == "insufficient"
    assert out["vpd_kpa"] is None


def test_dewpoint_path_when_no_rh():
    # نقطة ندى 15°C ⇒ ea=e°(15)؛ es من (30,20). VPD = es - e°(15).
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, dew_point_c=15.0)
    assert out["method"] == "dewpoint_based"
    ea_expected = saturation_vapor_pressure_kpa(15.0)
    assert abs(out["ea_kpa"] - round(ea_expected, 3)) < 1e-2


def test_rh_preferred_over_dewpoint_when_both_present():
    out = compute_vpd(t_max_c=30.0, t_min_c=20.0, rh_mean_pct=50.0, dew_point_c=15.0)
    assert out["method"] == "rh_based"  # RH أولويّة


def test_partial_completeness_without_tmin():
    # لا Tmin ⇒ es من قيمة واحدة، input_completeness=partial (لا كسر).
    out = compute_vpd(t_max_c=30.0, rh_mean_pct=50.0)
    assert out["input_completeness"] == "partial"
    assert out["quality_status"] == "ok"
    assert abs(out["es_kpa"] - saturation_vapor_pressure_kpa(30.0)) < 1e-2


def test_out_of_range_temperature_rejected():
    out = compute_vpd(t_max_c=200.0, t_min_c=20.0, rh_mean_pct=50.0)
    assert out["quality_status"] == "out_of_range"
    assert out["vpd_kpa"] is None


def test_dewpoint_above_es_clamps_to_zero_not_negative():
    # نقطة ندى شاذّة أعلى من الحرارة ⇒ VPD لا يكون سالباً (يُثبَّت عند 0).
    out = compute_vpd(t_max_c=20.0, t_min_c=20.0, dew_point_c=35.0)
    assert out["vpd_kpa"] == 0.0
    assert not math.isnan(out["vpd_kpa"])
