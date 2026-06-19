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
