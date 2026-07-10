"""اختبارات ET0 الموحَّد + عقد الجودة (WS-C.1b) — PM/Hargreaves/insufficient، لا خلط."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from et0 import (  # noqa: E402
    compute_et0,
    extraterrestrial_radiation_mj,
    penman_monteith_et0_mm,
)
from vapor_pressure import svp_slope_kpa_per_c  # noqa: E402

pytestmark = pytest.mark.unit


def test_ra_reference_fao56_example8():
    # FAO-56 مثال 8: خطّ عرض -20°، يوم 246 ⇒ Ra ≈ 32.2 MJ/m²/يوم.
    ra = extraterrestrial_radiation_mj(-20.0, 246)
    assert abs(ra - 32.2) < 0.5


def test_svp_slope_reference():
    # Δ عند 20°C ≈ 0.145 kPa/°C (FAO-56).
    assert abs(svp_slope_kpa_per_c(20.0) - 0.145) < 5e-3


def test_penman_monteith_validated_full_inputs():
    out = compute_et0(
        t_max_c=30.0,
        t_min_c=18.0,
        solar_rad_mj_m2=22.0,
        rh_mean_pct=55.0,
        wind_2m_ms=2.0,
        lat_deg=15.5,
        elevation_m=2000.0,
        day_of_year=100,
    )
    assert out["method"] == "fao56_penman_monteith"
    assert out["quality_status"] == "validated"
    assert out["input_completeness"] == 1.0
    assert out["missing_inputs"] == []
    assert 1.0 < out["et0_mm"] < 15.0  # نطاق فيزيائيّ معقول
    assert out["unit"] == "mm/day"


def test_hargreaves_fallback_is_degraded_not_fao56():
    # نقص الإشعاع/RH/الرياح ⇒ Hargreaves صريح degraded — لا يُقدَّم كـFAO-56.
    out = compute_et0(t_max_c=30.0, t_min_c=18.0, lat_deg=15.5, day_of_year=100)
    assert out["method"] == "hargreaves_fallback"
    assert out["quality_status"] == "degraded"
    assert out["et0_mm"] is not None
    assert set(out["missing_inputs"]) == {"solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms"}
    assert any("NOT full FAO-56" in lim for lim in out["limitations"])
    assert out["formula_version"] == "et0/fao56-pm/1.0.0"


def test_partial_pm_inputs_still_fallback():
    # إشعاع ورياح موجودان لكن RH مفقود ⇒ لا PM كامل ⇒ fallback (missing=rh فقط).
    out = compute_et0(
        t_max_c=30.0,
        t_min_c=18.0,
        solar_rad_mj_m2=22.0,
        wind_2m_ms=2.0,
        lat_deg=15.5,
        day_of_year=100,
    )
    assert out["method"] == "hargreaves_fallback"
    assert out["missing_inputs"] == ["rh_mean_pct"]
    assert out["input_completeness"] == round(2 / 3.0, 2)


def test_insufficient_when_temperature_missing():
    out = compute_et0(t_max_c=None, t_min_c=18.0, lat_deg=15.5, day_of_year=100)
    assert out["method"] == "insufficient"
    assert out["quality_status"] == "insufficient"
    assert out["et0_mm"] is None
    assert "t_max_c" in out["missing_inputs"]


def test_insufficient_when_geography_missing():
    out = compute_et0(t_max_c=30.0, t_min_c=18.0)  # لا lat ولا doy
    assert out["method"] == "insufficient"
    assert "lat_deg" in out["missing_inputs"]
    assert "day_of_year" in out["missing_inputs"]


def test_non_finite_input_ignored_not_fabricated():
    # RH غير محدود ⇒ يُهمَل ⇒ يسقط لـHargreaves (لا PM بقيمة مُلفَّقة).
    out = compute_et0(
        t_max_c=30.0,
        t_min_c=18.0,
        solar_rad_mj_m2=22.0,
        rh_mean_pct=float("nan"),
        wind_2m_ms=2.0,
        lat_deg=15.5,
        day_of_year=100,
    )
    assert out["method"] == "hargreaves_fallback"
    assert "rh_mean_pct" in out["missing_inputs"]


def test_pm_core_matches_compute():
    # النواة المباشرة تطابق ما يُصدره compute (لا مسار حساب ثانٍ).
    kw = dict(
        t_max_c=32.0,
        t_min_c=20.0,
        t_mean_c=26.0,
        solar_rad_mj_m2=24.0,
        rh_mean_pct=50.0,
        wind_2m_ms=2.5,
        lat_deg=15.5,
        elevation_m=2200.0,
        doy=120,
    )
    direct = penman_monteith_et0_mm(**kw)
    via = compute_et0(
        t_max_c=32.0,
        t_min_c=20.0,
        t_mean_c=26.0,
        solar_rad_mj_m2=24.0,
        rh_mean_pct=50.0,
        wind_2m_ms=2.5,
        lat_deg=15.5,
        elevation_m=2200.0,
        day_of_year=120,
    )
    assert abs(via["et0_mm"] - round(direct, 3)) < 1e-9
