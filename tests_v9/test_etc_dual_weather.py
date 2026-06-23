"""اختبار وحدة لاشتقاق الطقس في نقطة etc-dual (مُمرَّر مقابل جلب حيّ) — مسارات بلا شبكة.

يقفل الصدق: طقس مُمرَّر كامل ⇒ WeatherDay بمصدر "request"؛ طقس ناقص جزئيّاً ⇒ 422؛ جلب حيّ بلا
إحداثيّات حقل ⇒ 422 (لا اختلاق). مسار Open-Meteo الفعليّ (شبكة) يؤكّده المشغّل حيّاً.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

import api.main  # noqa: E402, F401 — تهيئة كاملة تسجّل الراوترات وتحلّ الاستيراد الدائريّ
from api.routers.etc_dual import EtcDualRequest, _resolve_weather  # noqa: E402
from fastapi import HTTPException  # noqa: E402


async def test_resolve_weather_request_path_full():
    """طقس مُمرَّر كامل ⇒ WeatherDay صحيح بمصدر request (lat من الطلب)."""
    req = EtcDualRequest(
        temp_max_c=34.0,
        temp_min_c=18.0,
        humidity_pct=45.0,
        wind_speed_m_s=2.0,
        solar_radiation_mj_m2=24.0,
        latitude_deg=15.5,
        day_of_year=180,
    )
    weather, source = await _resolve_weather(req, field_lat=None, field_lon=None)
    assert source == "request"
    assert weather.temp_max_c == 34.0
    assert weather.latitude_deg == 15.5
    assert weather.day_of_year == 180


async def test_resolve_weather_lat_falls_back_to_field():
    """خطّ العرض غير المُمرَّر يُؤخَذ من الحقل."""
    req = EtcDualRequest(
        temp_max_c=30.0,
        temp_min_c=15.0,
        humidity_pct=40.0,
        wind_speed_m_s=1.5,
        solar_radiation_mj_m2=22.0,
    )
    weather, source = await _resolve_weather(req, field_lat=16.2, field_lon=44.1)
    assert source == "request"
    assert weather.latitude_deg == 16.2


async def test_resolve_weather_partial_raises_422():
    """طقس مُمرَّر جزئيّاً (temp_max فقط) ⇒ 422 (مرّره كاملاً أو اتركه كلّه)."""
    req = EtcDualRequest(temp_max_c=34.0)  # بقيّة الطقس مفقودة
    with pytest.raises(HTTPException) as ei:
        await _resolve_weather(req, field_lat=15.0, field_lon=44.0)
    assert ei.value.status_code == 422


async def test_resolve_weather_autofetch_without_coords_raises_422():
    """لا طقس مُمرَّر ولا إحداثيّات حقل ⇒ 422 (تعذّر الجلب، لا اختلاق)."""
    req = EtcDualRequest()  # لا طقس ⇒ مسار الجلب الحيّ
    with pytest.raises(HTTPException) as ei:
        await _resolve_weather(req, field_lat=None, field_lon=None)
    assert ei.value.status_code == 422
