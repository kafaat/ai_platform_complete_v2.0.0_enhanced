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
    # صدق: Open-Meteo وحده موصول فعلاً؛ البقيّة مُخطَّطة (بما فيها الرياح/الإعادة-تحليل).
    assert active_weather_sources() == ["open_meteo"]
    for planned in (
        "nasa_power",
        "chirps",
        "ecmwf_open_data",
        "gfs_noaa",
        "era5",
        "era5_land",
        "global_wind_atlas",
        "merra2",
        "ascat",
    ):
        assert planned in planned_weather_sources()
        assert WEATHER_SOURCE_REGISTRY[planned]["active"] is False


def test_era5_resolution_is_honest_not_500m():
    # تصحيح المُراجِع: ERA5 ~25كم، ERA5-Land ~9كم — مقياس منطقة/محافظة لا نقطة حقل.
    assert "25" in WEATHER_SOURCE_REGISTRY["era5"]["resolution"]
    assert "9km" in WEATHER_SOURCE_REGISTRY["era5_land"]["resolution"]
    # كلا المصدرين مُخطَّط (لا يُستعمَل كنقطة حقل دقيقة).
    assert WEATHER_SOURCE_REGISTRY["era5"]["active"] is False
    assert WEATHER_SOURCE_REGISTRY["era5_land"]["active"] is False


def test_wind_energy_and_marine_scoped_honestly():
    assert "global_wind_atlas" in weather_sources_for_role("wind_energy_siting")
    # ASCAT رياح محيطيّة ⇒ نطاق ساحليّ صريح (لا يُدّعى للزراعة الداخليّة).
    assert WEATHER_SOURCE_REGISTRY["ascat"]["coverage_scope"] == "coastal_marine"
    assert "marine_wind" in WEATHER_SOURCE_REGISTRY["ascat"]["roles"]


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


def test_wind_capability_served_by_active_openmeteo():
    # حاجة الرياح على مستوى الحقل (نافذة الرشّ/ET0) مُغطّاة بالمصدر النشط، لا تحتاج
    # بيانات إعادة تحليل خشنة/محيطيّة إضافيّة.
    wind = weather_sources_for_role("wind")
    assert "open_meteo" in wind
    assert "open_meteo" in active_weather_sources()
    assert "spray_window" in WEATHER_SOURCE_REGISTRY["open_meteo"]["roles"]
    # رياح المناخ (الإعادة-تحليل) دور بحثيّ منفصل ⇒ ERA5 (مُخطَّط) لا النشط.
    assert "era5" in weather_sources_for_role("wind_climate")


def test_active_and_planned_are_disjoint_and_complete():
    active = set(active_weather_sources())
    planned = set(planned_weather_sources())
    assert active.isdisjoint(planned)
    assert active | planned == set(WEATHER_SOURCE_REGISTRY)
