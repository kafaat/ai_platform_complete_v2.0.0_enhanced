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

# استيراد الراوتر يتطلّب تبعيّات المنصّة (fastapi/asyncpg…) ويُهيّئ api.main كاملاً (يحلّ الاستيراد
# الدائريّ للراوتر). في وظيفة CI «Unit Tests» الأدنى (بلا api/requirements) تغيب هذه التبعيّات ⇒
# نتخطّى الوحدة كاملةً بصدق (تُغطّى في «Platform Unit Tests» الذي يُثبّت api/requirements).
try:
    import api.main  # noqa: E402, F401 — تهيئة كاملة تسجّل الراوترات
    from api.routers.etc_dual import EtcDualRequest, _resolve_weather  # noqa: E402
    from fastapi import HTTPException  # noqa: E402
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable (minimal Unit Tests env)", allow_module_level=True)


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


def _stub_openmeteo(monkeypatch, *, daily: dict, current: dict) -> None:
    """الجلبُ الحيُّ عبر `_fetch_json` مُستبدَلاً — فتمرّ القراءةُ بموضع البناء الحقيقيّ
    (`_build_daily`/`fetch_current`) لا بكائنٍ مصنوعٍ باليد يتجاوز الحافّة."""
    from api.connectors import openmeteo

    async def fake_fetch_json(url, params, timeout_s):
        if "current" in params:
            return {"current": {"wind_direction_10m": 90.0, "time": "t", **current}}
        return {"daily": {"time": ["2026-03-01"], **daily}}

    monkeypatch.setattr(openmeteo, "_fetch_json", fake_fetch_json)


_FULL_DAILY = {
    "temperature_2m_max": [34.0],
    "temperature_2m_min": [18.0],
    "wind_speed_10m_max": [2.0],
    "shortwave_radiation_sum": [24.0],
}


async def test_live_fetch_refuses_to_build_weather_from_absent_temperatures(monkeypatch):
    """TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 — كان الإشعاعُ وحدَه محروساً.

    قبل الإصلاح: يومٌ بلا حرارتين ورطوبة ⇒ `WeatherDay(0.0, 0.0, 0.0 …)` بمصدر `open-meteo`،
    فيُحسَب ETc من طقسٍ لم يُرصَد. الآن ٥٠٣ يُسمّي كلَّ ناقص.
    """
    daily = {k: v for k, v in _FULL_DAILY.items() if not k.startswith("temperature")}
    _stub_openmeteo(monkeypatch, daily=daily, current={})
    with pytest.raises(HTTPException) as ei:
        await _resolve_weather(EtcDualRequest(), field_lat=15.0, field_lon=44.0)
    assert ei.value.status_code == 503
    for name in ("temp_max_c", "temp_min_c", "humidity_pct"):
        assert name in str(ei.value.detail), f"الناقصُ {name} لم يُسمَّ"


async def test_live_fetch_keeps_an_observed_zero_and_builds_weather(monkeypatch):
    """النقيض: `0°م` و`0٪` قياسان مرصودان — يُبنى بهما الطقس ولا يُرفَضان غياباً."""
    _stub_openmeteo(
        monkeypatch,
        daily={**_FULL_DAILY, "temperature_2m_min": [0.0]},
        current={"relative_humidity_2m": 0.0},
    )
    weather, source = await _resolve_weather(EtcDualRequest(), field_lat=15.0, field_lon=44.0)
    assert source == "open-meteo"
    assert (weather.temp_min_c, weather.humidity_pct) == (0.0, 0.0)
