"""اختبار توحيد ET0 (H4): مصدر واحد core.engines.et0 + حفظ السلوك في المواقع الثلاثة.

يثبت: (أ) صحّة النواة والثوابت؛ (ب) أنّ التوحيد **محفوظ السلوك** — water_balance.et0_hargreaves
و season_simulation fallback يُنتجان نفس الرقم الذي كانت صيغتهما اليدويّة تُنتجه قبل التوحيد.
نواة نقيّة بلا قاعدة بيانات.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.engines.et0 import (  # noqa: E402
    DEFAULT_RA_MM,
    extraterrestrial_radiation_mj,
    extraterrestrial_radiation_mm,
    hargreaves_et0,
    hargreaves_et0_geo,
)


def test_default_ra_mm_is_unified_to_15():
    # توحيد H4: كان 14.0 (weather_analytics) و 15.0 (season_simulation) ⇒ 15.0.
    assert DEFAULT_RA_MM == 15.0


def test_ra_mm_is_mj_times_0408():
    mj = extraterrestrial_radiation_mj(15.5, 100)
    assert math.isclose(extraterrestrial_radiation_mm(15.5, 100), mj * 0.408, rel_tol=1e-12)


def test_ra_reproduces_fao56_worked_example():
    # FAO-56 Allen et al. 1998، مثال 8 (الفصل 3): خطّ عرض −20°، يوم 246 (3 سبتمبر).
    # القيمة المرجعيّة في الكتاب Ra ≈ 32.2 MJ/m²/يوم — النواة تُعيد إنتاجها ضمن السماحيّة.
    assert math.isclose(extraterrestrial_radiation_mj(-20.0, 246), 32.2, abs_tol=0.1)


def test_ra_is_latitude_dependent_not_constant():
    # إصلاح H4: Ra يُحسب من خطّ العرض (FAO-56 eq. 21) — ليس ثابتاً مُختلقاً (15.0/14.0).
    # عند نفس اليوم، تغيّر خطّ العرض يُغيّر Ra بفارق ملموس.
    doy = 100
    ra_equator = extraterrestrial_radiation_mj(0.0, doy)
    ra_yemen = extraterrestrial_radiation_mj(15.5, doy)
    ra_mid = extraterrestrial_radiation_mj(45.0, doy)
    assert ra_equator != ra_yemen != ra_mid
    # فارق حقيقيّ (>5 MJ بين الاستواء وخطّ العرض 45° في هذا اليوم) — لا قيمة مجمّدة.
    assert abs(ra_equator - ra_mid) > 5.0


def test_ra_is_day_of_year_dependent_not_constant():
    # عند نفس خطّ العرض، تغيّر اليوم (الميل الشمسي + المسافة النسبيّة) يُغيّر Ra.
    lat = 15.5
    ra_winter = extraterrestrial_radiation_mj(lat, 1)  # أوّل يناير
    ra_spring = extraterrestrial_radiation_mj(lat, 100)
    ra_summer = extraterrestrial_radiation_mj(lat, 200)
    assert ra_winter != ra_spring != ra_summer
    assert abs(ra_summer - ra_winter) > 5.0  # موسميّة حقيقيّة لا ثابت


def test_computed_ra_differs_from_old_hardcoded_constant():
    # توثيق تغيّر المخرجات (إصلاح خطأ موثّق H4): لخطّ عرض اليمن 15.5° ويوم 100،
    # القيمة الصحيحة المحسوبة لـRa بمكافئ التبخّر ≈ 15.43 mm/يوم، بينما كان
    # season_simulation يستعمل 15.0 و weather_analytics 14.0 ثابتةً. الفارق حقيقيّ.
    ra_mm = extraterrestrial_radiation_mm(15.5, 100)
    assert math.isclose(ra_mm, 15.434, abs_tol=0.01)
    assert ra_mm != 15.0  # ليس الثابت القديم (season_simulation)
    assert ra_mm != 14.0  # ليس الثابت القديم (weather_analytics)


def test_hargreaves_kernel_matches_explicit_formula():
    tmax, tmin, ra_mm = 34.0, 18.0, 15.0
    tmean = (tmax + tmin) / 2.0
    expected = 0.0023 * (tmean + 17.8) * math.sqrt(tmax - tmin) * ra_mm
    assert math.isclose(hargreaves_et0(tmax, tmin, ra_mm), expected, rel_tol=1e-12)


def test_hargreaves_clamps_negative_temp_diff():
    # Tmax < Tmin ⇒ المدى الحراريّ مقصوص لصفر ⇒ ET0 = 0 (لا جذر سالب).
    assert hargreaves_et0(10.0, 20.0, 15.0) == 0.0


def test_water_balance_et0_hargreaves_behaviour_preserved():
    # السلوك المحفوظ: نفس صيغة water_balance القديمة (Ra محسوب × 0.408).
    from api.water_balance import WeatherInput, et0_hargreaves

    w = WeatherInput(t_min_c=18.0, t_max_c=34.0, latitude_deg=15.5, day_of_year=100)
    ra_mj = extraterrestrial_radiation_mj(15.5, 100)
    expected = 0.0023 * (w.t_mean + 17.8) * math.sqrt(34.0 - 18.0) * ra_mj * 0.408
    assert math.isclose(et0_hargreaves(w), expected, rel_tol=1e-12)
    # ومطابقٌ للدالّة الجغرافيّة الموحّدة.
    assert math.isclose(
        et0_hargreaves(w), hargreaves_et0_geo(34.0, 18.0, 15.5, 100, w.t_mean), rel_tol=1e-12
    )


def test_season_simulation_fallback_behaviour_preserved():
    # fallback القديم كان يستعمل Ra=15.0 صراحةً ⇒ يطابق النواة الموحّدة بـDEFAULT_RA_MM.
    tmax, tmin = 30.0, 16.0
    old = max(0.0, 0.0023 * ((tmax + tmin) / 2 + 17.8) * math.sqrt(max(0.0, tmax - tmin)) * 15.0)
    assert math.isclose(hargreaves_et0(tmax, tmin, DEFAULT_RA_MM), old, rel_tol=1e-12)
