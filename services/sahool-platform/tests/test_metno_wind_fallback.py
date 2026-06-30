"""اختبارات موصّل اتّجاه الرياح الاحتياطيّ MET Norway (api.connectors.metno_wind).

منطق نقيّ بلا شبكة: تحليل الردّ + بوّابة التفعيل + السقوط الصادق (None لا قيمة وهميّة).
"""

import pytest
from api.connectors import metno_wind

pytestmark = pytest.mark.unit


def test_parse_wind_from_direction_extracts_degrees():
    payload = {
        "properties": {
            "timeseries": [
                {
                    "data": {
                        "instant": {"details": {"wind_from_direction": 217.5, "wind_speed": 4.1}}
                    }
                }
            ]
        }
    }
    assert metno_wind.parse_wind_from_direction(payload) == 217.5


def test_parse_wind_from_direction_missing_or_malformed_returns_none():
    assert metno_wind.parse_wind_from_direction({}) is None
    assert metno_wind.parse_wind_from_direction({"properties": {"timeseries": []}}) is None
    assert (
        metno_wind.parse_wind_from_direction(
            {"properties": {"timeseries": [{"data": {"instant": {"details": {}}}}]}}
        )
        is None
    )


def test_enabled_by_default_and_toggle(monkeypatch):
    monkeypatch.delenv("METNO_WIND_FALLBACK_ENABLED", raising=False)
    assert metno_wind.is_enabled() is True
    monkeypatch.setenv("METNO_WIND_FALLBACK_ENABLED", "0")
    assert metno_wind.is_enabled() is False
    monkeypatch.setenv("METNO_WIND_FALLBACK_ENABLED", "true")
    assert metno_wind.is_enabled() is True


@pytest.mark.asyncio
async def test_fetch_returns_none_when_disabled(monkeypatch):
    monkeypatch.setenv("METNO_WIND_FALLBACK_ENABLED", "0")
    # مُعطَّل ⇒ لا استدعاء شبكيّ، None فوراً (سقوط صادق).
    assert await metno_wind.fetch_wind_direction_deg(15.35, 44.2) is None


@pytest.mark.asyncio
async def test_fetch_current_uses_metno_when_openmeteo_direction_missing(monkeypatch):
    from api.connectors import openmeteo

    async def fake_fetch_json(url, params, timeout_s=8.0):
        return {
            "current": {
                "temperature_2m": 27,
                "relative_humidity_2m": 42,
                "wind_speed_10m": 3.5,
                "wind_direction_10m": None,
                "wind_gusts_10m": 5.0,
                "precipitation": 0,
                "cloud_cover": 12,
                "weather_code": 0,
                "is_day": 1,
                "time": "2026-06-30T12:00",
            }
        }

    async def fake_metno(lat, lon):
        return 184.0

    monkeypatch.setattr(openmeteo, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(metno_wind, "fetch_wind_direction_deg", fake_metno)

    data = await openmeteo.fetch_current(15.35, 44.2)
    assert data.wind_direction_deg == 184.0
    assert data.wind_direction_source == "met.no"


@pytest.mark.asyncio
async def test_fetch_weather_tile_data_preserves_zero_degree_direction(monkeypatch):
    from api.connectors import openmeteo

    async def fake_fetch_json(url, params, timeout_s=8.0):
        return {
            "current": {
                "time": "2026-06-30T12:00",
                "temperature_2m": 28,
                "relative_humidity_2m": 40,
                "wind_speed_10m": 2.1,
                "wind_direction_10m": 0,
                "wind_gusts_10m": 3.2,
                "precipitation": 0,
                "cloud_cover": 5,
                "weather_code": 0,
                "is_day": 1,
            },
            "hourly": {
                "time": ["2026-06-30T12:00"],
                "wind_direction_10m": [270],
            },
        }

    async def fail_metno(lat, lon):  # pragma: no cover - يجب ألا يُستدعى
        raise AssertionError("MET.no fallback must not run when Open-Meteo provides 0°")

    monkeypatch.setattr(openmeteo, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(metno_wind, "fetch_wind_direction_deg", fail_metno)

    sample = await openmeteo.fetch_weather_tile_data(15.35, 44.2, time_key="now")
    assert sample["wind_direction_10m_deg"] == 0
    assert sample["wind_direction_source"] == "open-meteo"
