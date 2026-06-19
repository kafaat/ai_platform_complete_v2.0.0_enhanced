"""اختبار الريّ التنبّؤيّ (مركز المحاصيل، فجوة 3/3): forecast + threshold.

يثبت: (أ) السلوك المحفوظ — بلا تنبّؤ ⇒ عتبيّ كما هو، والكمّيّة لا تُمَسّ؛ (ب) مطر متوقّع
كافٍ ⇒ تأجيل؛ (ج) غير كافٍ ⇒ لا تأجيل؛ (د) لا حاجة ⇒ لا إقحام. نواة نقيّة بلا خدمات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.water_balance import WeatherInput, _forecast_defer, water_balance  # noqa: E402


def test_no_forecast_preserves_threshold_behavior():
    w = WeatherInput(t_min_c=18.0, t_max_c=34.0)
    base = water_balance(w, "wheat", "mid", rain_mm=0.0)
    same = water_balance(w, "wheat", "mid", rain_mm=0.0, forecast_rain_mm=None)
    # السلوك المحفوظ: نفس التوصية والكمّيّة تماماً.
    assert same.advice_ar == base.advice_ar
    assert same.net_irrigation_mm == base.net_irrigation_mm
    assert base.net_irrigation_mm > 0  # يوجد احتياج فعليّ


def test_sufficient_forecast_defers_without_touching_amount():
    w = WeatherInput(t_min_c=18.0, t_max_c=34.0)
    base = water_balance(w, "wheat", "mid", rain_mm=0.0)
    r = water_balance(w, "wheat", "mid", rain_mm=0.0, forecast_rain_mm=60.0)
    assert "أجّل" in r.advice_ar
    assert "مطر متوقّع" in r.advice_ar
    # الكمّيّة لم تُمَسّ بالمطر المتوقّع (لا فقد صدق).
    assert r.net_irrigation_mm == base.net_irrigation_mm


def test_insufficient_forecast_does_not_defer():
    w = WeatherInput(t_min_c=18.0, t_max_c=34.0)
    r = water_balance(w, "wheat", "mid", rain_mm=0.0, forecast_rain_mm=1.0)
    assert "أجّل" not in r.advice_ar


def test_no_need_ignores_forecast():
    w = WeatherInput(t_min_c=18.0, t_max_c=34.0)
    r = water_balance(w, "wheat", "mid", rain_mm=200.0, forecast_rain_mm=60.0)
    assert r.net_irrigation_mm == 0.0
    assert "لا حاجة للريّ" in r.advice_ar
    assert "أجّل" not in r.advice_ar


def test_forecast_defer_pure_guards():
    assert _forecast_defer(10.0, None, 3) == ""  # بلا تنبّؤ
    assert _forecast_defer(0.0, 50.0, 3) == ""  # لا احتياج
    assert _forecast_defer(5.0, 0.0, 3) == ""  # تنبّؤ صفر
    assert "أجّل" in _forecast_defer(5.0, 40.0, 3)  # كافٍ
