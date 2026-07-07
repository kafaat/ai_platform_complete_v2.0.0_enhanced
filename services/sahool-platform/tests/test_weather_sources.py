"""تحقّق V68 — سِجِلّ مصادر الطقس (سلسلة صادقة: Open-Meteo نشط، البقيّة مُخطَّطة).

- Open-Meteo وحده active (موصول فعلاً)؛ NASA POWER/CHIRPS/ECMWF/GFS/ERA5 مُخطَّطة.
- كلّها free + coverage_yemen=True (مجانيّة وتغطّي اليمن) لكن غير الموصول ⇒ active=False.
- استعلام حسب الدور (forecast/rainfall_history) يعيد المصادر الصحيحة.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

from core.weather_sources import (
    WEATHER_SOURCE_REGISTRY,
    active_weather_sources,
    planned_weather_sources,
    weather_sources_for_role,
)


def test_only_openmeteo_is_active():
    # صدق: Open-Meteo وحده موصول فعلاً؛ NASA POWER غير موصول ⇒ مُخطَّط لا نشط.
    assert active_weather_sources() == ["open_meteo"]
    for planned in ("nasa_power", "chirps", "ecmwf_open_data", "gfs_noaa", "era5"):
        assert planned in planned_weather_sources()
        assert WEATHER_SOURCE_REGISTRY[planned]["active"] is False


def test_all_sources_free_and_cover_yemen():
    for meta in WEATHER_SOURCE_REGISTRY.values():
        assert meta["free"] is True
        assert meta["coverage_yemen"] is True
        assert meta["roles"], "كلّ مصدر يحمل أدواراً"


def test_role_lookup_returns_relevant_sources():
    fc = weather_sources_for_role("forecast")
    assert "open_meteo" in fc
    rain = weather_sources_for_role("rainfall_history")
    assert "chirps" in rain
    solar = weather_sources_for_role("solar_radiation")
    assert "nasa_power" in solar


def test_active_and_planned_are_disjoint_and_complete():
    active = set(active_weather_sources())
    planned = set(planned_weather_sources())
    assert active.isdisjoint(planned)
    assert active | planned == set(WEATHER_SOURCE_REGISTRY)
