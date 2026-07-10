"""حقن سلسلة ET0 من محرّك الطقس في محاكاة الموسم (WS-C.1b) — لا Hargreaves محلّيّ.

يُثبِت: السلسلة المحقونة الكنسيّة تقود احتياج الماء فعلاً · تحلّ محلّ ``day.et0_mm`` ·
يوم None ⇒ يُستبعَد من احتياج الماء (لا يُلفَّق، لا نواة محلّيّة) · غياب السلسلة كلّها ⇒
عودة لـ``day.et0_mm`` المُمرَّر · لا مسار حساب ET0 داخل المنصّة.
"""

from __future__ import annotations

import pytest
from api.season_simulation import DayWeather, SimContext, simulate_season

pytestmark = pytest.mark.unit


def _weather(n=30, *, et0_mm=None):
    return [
        DayWeather(t_min_c=14.0 + (i % 5), t_max_c=30.0 + (i % 5), et0_mm=et0_mm, rain_mm=0.0)
        for i in range(n)
    ]


def test_injected_et0_series_drives_water_need():
    weather = _weather(20, et0_mm=None)
    # سلسلة ET0 موجبة محقونة ⇒ احتياج ماء موجب (تُثبِت أنّ الحقن يقود الحساب فعلاً).
    injected = [5.0] * len(weather)
    out = simulate_season(SimContext(crop="wheat", weather=weather, et0_daily_override=injected))
    assert out.water_need_mm > 0.0


def test_injected_series_overrides_day_et0():
    # ET0 مُمرَّر مع اليوم = 1.0، لكنّ السلسلة المحقونة = 10.0 ⇒ يجب أن تفوز السلسلة.
    low = _weather(15, et0_mm=1.0)
    with_low_day = simulate_season(SimContext(crop="wheat", weather=low))
    with_injected = simulate_season(
        SimContext(crop="wheat", weather=low, et0_daily_override=[10.0] * len(low))
    )
    assert with_injected.water_need_mm > with_low_day.water_need_mm


def test_none_day_excluded_not_fabricated():
    # يوم None في السلسلة ⇒ يُستبعَد من الاحتياج (لا صفر مُلفَّق، لا Hargreaves محلّيّ).
    weather = _weather(10, et0_mm=None)
    all_five = simulate_season(
        SimContext(crop="wheat", weather=weather, et0_daily_override=[5.0] * 10)
    )
    one_none = [5.0] * 10
    one_none[3] = None
    with_gap = simulate_season(
        SimContext(crop="wheat", weather=weather, et0_daily_override=one_none)
    )
    # يوم ناقص واحد ⇒ احتياج أقلّ (اليوم مُستبعَد)، لا مساوٍ ولا أكبر.
    assert with_gap.water_need_mm < all_five.water_need_mm


def test_no_et0_anywhere_yields_zero_water_need_no_local_calc():
    # لا سلسلة محقونة ولا et0_mm مع اليوم ⇒ كلّ الأيّام None ⇒ احتياج الماء = 0
    # (لا نواة Hargreaves محلّيّة تملأ الفراغ). صدق fail-open-to-empty.
    weather = _weather(12, et0_mm=None)
    out = simulate_season(SimContext(crop="wheat", weather=weather))
    assert out.water_need_mm == 0.0


def test_no_override_uses_passed_day_et0():
    # غياب السلسلة المحقونة ⇒ يُستعمَل et0_mm المُمرَّر مع اليوم (سلوك متوافق للخلف).
    weather = _weather(15, et0_mm=4.0)
    a = simulate_season(SimContext(crop="barley", weather=weather))
    b = simulate_season(SimContext(crop="barley", weather=weather, et0_daily_override=None))
    assert a.water_need_mm == b.water_need_mm
    assert a.water_need_mm > 0.0
