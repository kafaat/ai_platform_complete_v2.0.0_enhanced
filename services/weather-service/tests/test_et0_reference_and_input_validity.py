"""ET0 مقابل مثال FAO-56 محلول + مُدخَلات مستحيلة لا تُحسَب «validated» ولا ترمي.

**العطلُ الذي وُجِد هذا لأجله:** الاختبارات القائمة تفحص Ra (مثال 8) وΔ فقط، بلا
مثال محلول من الطرف إلى الطرف. وتشغيلُ ``compute_et0`` على مُدخَلات مستحيلة أخرجها
بعلامة ``validated`` (إشعاع صفر ⇒ 1.52، رياح −1، Tmax < Tmin، خطّ عرض 95،
Tmax=10000 ⇒ ~2×10⁹ mm/يوم)، ورطوبةُ 150٪ رمت ``ValueError`` رغم أنّ عقد الوحدة
يقول «لا يرمي».

**المرجع:** FAO-56 مثال 18 (بروكسل، 6 يوليو). القيم منقولة عبر حِزَم اختبار مستقلّة
تستشهد بالمثال (PyETo tests/test_fao.py، pyet tests/testfao56.py، MeTo، FAO56)
ومتّفقة فيما بينها؛ fao.org لم يكن متاحاً عند الكتابة. الواجهة تقبل RH متوسّطاً
واحداً، فيُمرَّر RH مكافئ لـea=1.409 kPa المحسوب في المثال من RHmax/RHmin.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from et0 import (  # noqa: E402
    compute_et0,
    extraterrestrial_radiation_mj,
    hargreaves_et0_mm,
)
from vapor_pressure import mean_saturation_vapor_pressure_kpa  # noqa: E402

pytestmark = pytest.mark.unit

# FAO-56 مثال 18 — بروكسل (50°48'N، 100 م)، 6 يوليو (J=187).
_EX18 = {
    "t_max_c": 21.5,
    "t_min_c": 12.3,
    "solar_rad_mj_m2": 22.07,  # من n=9.25 h, N=16.1 h (Angström)
    "wind_2m_ms": 2.078,  # 10 km/h على 10 م ⇒ 2 م (Eq. 47)
    "lat_deg": 50.80,
    "elevation_m": 100.0,
    "day_of_year": 187,
}
_EX18_EA_KPA = 1.409
_EX18_ET0_MM = 3.9  # يُقرِّبه المثال لمنزلة عشريّة واحدة


def _ex18_rh_equivalent() -> float:
    es = mean_saturation_vapor_pressure_kpa(_EX18["t_max_c"], _EX18["t_min_c"])
    return 100.0 * _EX18_EA_KPA / es


def test_fao56_example18_intermediates():
    assert extraterrestrial_radiation_mj(50.80, 187) == pytest.approx(41.09, abs=0.1)
    es = mean_saturation_vapor_pressure_kpa(21.5, 12.3)
    assert es == pytest.approx(1.997, abs=0.005)


def test_fao56_example18_end_to_end():
    out = compute_et0(**_EX18, rh_mean_pct=_ex18_rh_equivalent())
    assert out["method"] == "fao56_penman_monteith"
    assert out["quality_status"] == "validated"
    assert out["invalid_inputs"] == []
    assert out["et0_mm"] == pytest.approx(_EX18_ET0_MM, abs=0.05)


# ── مُدخَلات مستحيلة: تُعلَن في invalid_inputs ولا تُخرج «validated» ──
_PM_FULL = {**_EX18, "rh_mean_pct": 70.0}


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"solar_rad_mj_m2": 0.0}, "solar_rad_mj_m2"),
        ({"solar_rad_mj_m2": -3.0}, "solar_rad_mj_m2"),
        ({"solar_rad_mj_m2": 250.0}, "solar_rad_mj_m2"),  # W/m² بدل MJ/m²/يوم
        ({"wind_2m_ms": -1.0}, "wind_2m_ms"),
        ({"wind_2m_ms": 400.0}, "wind_2m_ms"),
        ({"rh_mean_pct": 150.0}, "rh_mean_pct"),
        ({"rh_mean_pct": -40.0}, "rh_mean_pct"),
    ],
)
def test_broken_pm_input_falls_back_to_degraded_and_is_named(override, field):
    out = compute_et0(**{**_PM_FULL, **override})
    assert out["quality_status"] == "degraded"
    assert out["method"] == "hargreaves_fallback"
    assert field in out["invalid_inputs"]
    assert field not in out["missing_inputs"], "المكسور ليس مفقوداً"
    assert any(field in lim and "rejected" in lim for lim in out["limitations"])


@pytest.mark.parametrize(
    ("override", "fields"),
    [
        ({"t_max_c": 10.0, "t_min_c": 20.0}, {"t_max_c", "t_min_c"}),
        ({"t_max_c": 10000.0}, {"t_max_c"}),
        ({"t_min_c": -300.0}, {"t_min_c"}),
        ({"lat_deg": 95.0}, {"lat_deg"}),
        ({"day_of_year": 0}, {"day_of_year"}),
        ({"day_of_year": 400}, {"day_of_year"}),
        ({"day_of_year": "187"}, {"day_of_year"}),
        ({"day_of_year": True}, {"day_of_year"}),
    ],
)
def test_broken_core_input_yields_no_number(override, fields):
    out = compute_et0(**{**_PM_FULL, **override})
    assert out["et0_mm"] is None
    assert out["quality_status"] == "insufficient"
    assert fields <= set(out["invalid_inputs"])


def test_out_of_range_elevation_is_named_and_not_used():
    out = compute_et0(**{**_PM_FULL, "elevation_m": 50_000.0})
    assert "elevation_m" in out["invalid_inputs"]
    assert any("elevation defaulted to 0 m" in lim for lim in out["limitations"])
    assert math.isfinite(out["et0_mm"])


def test_t_mean_outside_the_daily_range_is_replaced_and_named():
    out = compute_et0(**{**_PM_FULL, "t_mean_c": -273.0})
    assert "t_mean_c" in out["invalid_inputs"]
    assert math.isfinite(out["et0_mm"])


def test_polar_night_zero_radiation_is_not_rejected():
    # Ra = 0 في ليل قطبيّ ⇒ إشعاع صفر قياسٌ صحيح لا غياب.
    out = compute_et0(
        t_max_c=-20.0,
        t_min_c=-30.0,
        solar_rad_mj_m2=0.0,
        rh_mean_pct=80.0,
        wind_2m_ms=3.0,
        lat_deg=80.0,
        elevation_m=10.0,
        day_of_year=355,
    )
    assert "solar_rad_mj_m2" not in out["invalid_inputs"]
    assert out["method"] == "fao56_penman_monteith"


_HOSTILE = [
    None,
    float("nan"),
    float("inf"),
    -float("inf"),
    "x",
    True,
    -1e9,
    1e9,
    0,
]


@pytest.mark.parametrize("value", _HOSTILE)
@pytest.mark.parametrize(
    "field",
    [
        "t_max_c",
        "t_min_c",
        "solar_rad_mj_m2",
        "rh_mean_pct",
        "wind_2m_ms",
        "t_mean_c",
        "lat_deg",
        "elevation_m",
        "day_of_year",
    ],
)
def test_compute_et0_never_raises_and_never_returns_a_non_finite_number(field, value):
    """عقد الوحدة «نقيّ حتميّ، لا يرمي» يصير مقيساً لا موصوفاً."""
    out = compute_et0(**{**_PM_FULL, field: value})
    v = out["et0_mm"]
    assert v is None or (math.isfinite(v) and 0.0 <= v < 30.0)
    assert out["quality_status"] in {"validated", "degraded", "insufficient"}


def test_hargreaves_canonical_does_not_raise_at_polar_latitudes():
    for lat in (-90.0, -89.9, 89.9, 90.0):
        for doy in (1, 172, 355):
            assert math.isfinite(hargreaves_et0_mm(t_max_c=5, t_min_c=-5, lat_deg=lat, doy=doy))
