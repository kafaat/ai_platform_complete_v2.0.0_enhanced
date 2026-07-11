"""WS-C.1b Zero-Legacy — راتشِت ET0 #4: analyze_weather_log يفوّض ET0 لمنتج سلسلة
محرّك الطقس (لا نواة محلّيّة)، مع تدهور جزئيّ صريح عند تعذّر المحرّك.

يغطّي: تعيين سلسلة المحرّك للمخرَج (complete) · تمرير التواريخ الفعليّة للمحرّك (فلك
المحرّك، لا انجراف) · تدهور جزئيّ (heat/frost/wind/rain تبقى، حقول ET0 = null +
analysis_status=partial + availability + unavailable_products) · حارس انحدار ساكن.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

_SRC = (_PLATFORM / "api" / "weather_analytics.py").read_text(encoding="utf-8")

try:
    from api import weather_analytics as wa
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة
    wa = None


_RECS = [
    {"date": "2024-01-10", "temp_max_c": 30.0, "temp_min_c": 12.0, "precipitation_mm": 0.0},
    {"date": "2025-05-17", "temp_max_c": 43.0, "temp_min_c": 26.0, "precipitation_mm": 1.0},
    {"date": "2026-08-20", "temp_max_c": 41.0, "temp_min_c": 25.0, "wind_speed_kmh": 40},
]


# ─── حارس انحدار ساكن (بلا استيراد) ─────────────────────────────────────────


def test_no_local_et0_kernel_delegates_to_engine_series():
    assert "0.0023" not in _SRC and "17.8" not in _SRC, "no Hargreaves constants in the platform"
    assert "hargreaves" not in _SRC.lower(), "no local hargreaves wrapper/kernel"
    assert "core.engines.et0" not in _SRC, "no import of the local ET0 core"
    assert "get_et0_series" in _SRC, "delegates to the Weather Engine ET0 series product"


# ─── سلوكيّ ─────────────────────────────────────────────────────────────────


@pytest.mark.skipif(wa is None, reason="platform deps unavailable")
async def test_complete_maps_engine_series_and_dates(monkeypatch):
    cap: dict = {}

    async def _fake_series(**kwargs):
        cap.update(kwargs)
        return {"daily_et0_mm": [5.0, 6.0, 7.0]}

    monkeypatch.setattr(wa, "get_et0_series", _fake_series)
    out = await wa.analyze_weather_log(_RECS, lat=16.0)
    assert out["analysis_status"] == "complete"
    assert out["availability"]["et0"] is True and out["availability"]["heat"] is True
    assert "et0" in out["computed_products"] and out["unavailable_products"] == []
    assert out["computed_et0_total_mm"] == 18.0  # 5+6+7
    assert out["et0_method"] == "weather-engine"
    # المحرّك يملك الفلك: نمرّر التواريخ الفعليّة + lat (لا DOY محلّيّ، لا انجراف).
    assert cap["daily_dates"] == ["2024-01-10", "2025-05-17", "2026-08-20"]
    assert cap["lat_deg"] == 16.0
    assert cap["daily_t_max"] == [30.0, 43.0, 41.0]


@pytest.mark.skipif(wa is None, reason="platform deps unavailable")
async def test_engine_down_degrades_et0_only_partial(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("weather-engine unreachable")

    monkeypatch.setattr(wa, "get_et0_series", _boom)
    out = await wa.analyze_weather_log(_RECS)
    # حالة جزئيّة صريحة — لا 503، لا اختلاق.
    assert out["analysis_status"] == "partial"
    assert out["availability"] == {
        "heat": True,
        "frost": True,
        "wind": True,
        "rain": True,
        "et0": False,
    }
    assert "et0" in out["unavailable_products"]
    assert "annual_water_deficit" in out["unavailable_products"]
    assert out["computed_et0_total_mm"] is None
    assert out["annual_et0_mm"] is None
    assert out["annual_water_deficit_mm"] is None
    assert out["irrigation_dependency_ar"] is None
    assert out["limitations"]
    # التحليل المستقلّ عن ET0 يبقى صحيحاً كاملاً.
    assert out["days_analyzed"] == 3
    assert out["severe_heat_days"] >= 1  # 43°C
    assert out["high_wind_days"] == 1  # 40 km/h
    assert out["total_rainfall_mm"] == 1.0


@pytest.mark.skipif(wa is None, reason="platform deps unavailable")
async def test_empty_records_unsupported(monkeypatch):
    out = await wa.analyze_weather_log([])
    assert out["supported"] is False
