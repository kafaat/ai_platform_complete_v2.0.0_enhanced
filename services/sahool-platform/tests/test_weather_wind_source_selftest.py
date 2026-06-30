"""v49 — اختبار نقطة الفحص الحيّ لمصدرَي اتّجاه الرياح + احتياط fetch_current.

البيئة المعزولة (CI) تحجب الشبكة، فنُحاكي مصدرَي الجلب (Open-Meteo + MET.no) ونتحقّق
من منطق الدمج/التبليغ — لا اتّصال خارجيّ هنا (الفحص الحيّ الفعليّ يُشغَّل في النشر).
"""

from __future__ import annotations

import pytest
from fastapi import Response

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_selftest_reports_open_meteo_as_resolved_source(monkeypatch):
    from api.connectors import metno_wind, openmeteo
    from api.routers import weather

    async def fake_tile(lat, lon, **kw):
        return {"wind_direction_10m_deg": 212.0, "wind_direction_source": "open-meteo"}

    async def fake_metno(lat, lon, **kw):
        return 215.0

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_tile)
    monkeypatch.setattr(metno_wind, "fetch_wind_direction_deg", fake_metno)
    monkeypatch.setenv("METNO_WIND_FALLBACK_ENABLED", "1")

    resp = Response()
    out = await weather.weather_wind_source_selftest(resp, 15.35, 44.21, None)
    assert out["status"] == "ok"
    assert out["resolved"]["wind_direction_10m_deg"] == 212.0
    assert out["resolved"]["source"] == "open-meteo"
    assert out["open_meteo"]["provided_direction"] is True
    assert out["met_norway"]["wind_direction_deg"] == 215.0


@pytest.mark.asyncio
async def test_selftest_degraded_when_no_direction(monkeypatch):
    from api.connectors import metno_wind, openmeteo
    from api.routers import weather

    async def fake_tile(lat, lon, **kw):
        return {"wind_direction_10m_deg": None, "wind_direction_source": "open-meteo"}

    async def fake_metno(lat, lon, **kw):
        return None

    monkeypatch.setattr(openmeteo, "fetch_weather_tile_data", fake_tile)
    monkeypatch.setattr(metno_wind, "fetch_wind_direction_deg", fake_metno)

    resp = Response()
    out = await weather.weather_wind_source_selftest(resp, 15.35, 44.21, None)
    assert out["status"] == "degraded"
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_fetch_current_fills_wind_direction_from_metno(monkeypatch):
    from api.connectors import metno_wind, openmeteo

    async def fake_json(url, params, timeout):
        # Open-Meteo بلا اتّجاه رياح (السيناريو الذي يُفعِّل الاحتياط).
        return {
            "current": {"temperature_2m": 30, "wind_speed_10m": 3.2, "wind_direction_10m": None}
        }

    async def fake_metno(lat, lon, **kw):
        return 188.0

    monkeypatch.setattr(openmeteo, "_fetch_json", fake_json)
    monkeypatch.setattr(metno_wind, "fetch_wind_direction_deg", fake_metno)

    cur = await openmeteo.fetch_current(15.35, 44.21)
    assert cur.wind_direction_deg == 188.0  # مُلِئ من MET.no لا قيمة وهميّة
