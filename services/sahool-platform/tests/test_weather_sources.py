"""تحقّق V68 — سِجِلّ مصادر الطقس (سلسلة صادقة: Open-Meteo نشط، البقيّة مُخطَّطة).

- Open-Meteo وحده active (موصول فعلاً)؛ NASA POWER/CHIRPS/ECMWF/GFS/ERA5 مُخطَّطة.
- كلّها free + coverage_yemen=True (مجانيّة وتغطّي اليمن) لكن غير الموصول ⇒ active=False.
- استعلام حسب الدور (forecast/rainfall_history) يعيد المصادر الصحيحة.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

from core.weather_sources import (
    ET0_PROVIDER_CHAIN,
    WEATHER_SOURCE_REGISTRY,
    active_weather_sources,
    planned_weather_sources,
    root_zone_soil_moisture,
    soil_moisture_drought_class,
    weather_sources_for_role,
)


def test_active_sources_are_openmeteo_and_nasa_power():
    # صدق: Open-Meteo (توقّع/ET0) وNASA POWER (رياح تاريخيّة، موصول عبر connectors/
    # nasa_power.py) نشطان؛ البقيّة مُخطَّطة. NASA POWER نشط لدور الرياح التاريخيّة فقط.
    assert set(active_weather_sources()) == {"open_meteo", "nasa_power"}
    assert WEATHER_SOURCE_REGISTRY["nasa_power"]["active_roles"] == ["historical_wind"]
    assert "historical_wind" in WEATHER_SOURCE_REGISTRY["nasa_power"]["roles"]
    for planned in (
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


def test_era5_land_uses_official_cds_variable_names():
    # صدق: أسماء CDS الرسميّة (volumetric_soil_water_layer_1..4)، لا أسماء MirrorEarth.
    layers = WEATHER_SOURCE_REGISTRY["era5_land"]["soil_moisture_layers"]
    assert layers["soil_moisture_0_7cm"]["provider_variable"] == "volumetric_soil_water_layer_1"
    assert layers["soil_moisture_100_289cm"]["provider_variable"] == "volumetric_soil_water_layer_4"
    # العمق الرابع 289سم (تصحيح لا 255).
    assert "soil_moisture_100_289cm" in layers
    assert any("100_289cm" in k for k in layers)
    # صدق: متغيّرات المزوّد كلّها أسماء CDS الرسميّة (volumetric_soil_water_layer_*)،
    # لا أسماء MirrorEarth غير الموثّقة (نفحص القيم الفعليّة لا نصّ الملاحظة التوضيحيّة).
    for spec in layers.values():
        pv = spec["provider_variable"]
        assert pv.startswith("volumetric_soil_water_layer_"), pv
        assert "mirrorearth" not in pv.lower()
    assert WEATHER_SOURCE_REGISTRY["era5_land"]["limitations"], "قيود صريحة (نموذجيّ/خشن)"


def test_et0_provider_chain_primary_is_active_openmeteo():
    assert ET0_PROVIDER_CHAIN["primary"] == "open_meteo"
    assert ET0_PROVIDER_CHAIN["primary"] in active_weather_sources()
    assert ET0_PROVIDER_CHAIN["secondary"] == "nasa_power"
    assert "et0_reference_evapotranspiration" in ET0_PROVIDER_CHAIN["variables"]


def test_drought_class_uses_local_percentile_not_fixed_threshold():
    hist = [0.30, 0.32, 0.28, 0.35, 0.31, 0.29, 0.33, 0.34, 0.27, 0.36, 0.30, 0.32]
    # قيمة أدنى من كلّ التاريخ ⇒ مئينيّة ~0 ⇒ جفاف شديد.
    assert soil_moisture_drought_class(0.10, hist)["class"] == "severe_drought"
    # قيمة وسطى ⇒ طبيعيّ.
    assert soil_moisture_drought_class(0.32, hist)["class"] == "normal"
    # تاريخ غير كافٍ ⇒ unknown (لا تخمين، لا عتبة SMI ثابتة).
    assert soil_moisture_drought_class(0.2, [0.3, 0.3])["class"] == "unknown"


def test_layer_depth_bounds_are_single_source_and_reach_289():
    layers = WEATHER_SOURCE_REGISTRY["era5_land"]["soil_moisture_layers"]
    assert layers["soil_moisture_0_7cm"]["depth_top_cm"] == 0
    assert layers["soil_moisture_0_7cm"]["depth_bottom_cm"] == 7
    # الطبقة الرابعة تصل 289سم (تصحيح لا 255) — تُغطّي جذور النخيل/العنب العميقة.
    assert layers["soil_moisture_100_289cm"]["depth_bottom_cm"] == 289


def test_root_zone_shallow_crop_weights_top_layers_only():
    # قمح/خضار جذور سطحيّة ~28سم ⇒ يوزن الطبقتين العلويتين فقط (0–7، 7–28) بسُمكهما.
    vals = {
        "soil_moisture_0_7cm": 0.20,
        "soil_moisture_7_28cm": 0.30,
        "soil_moisture_28_100cm": 0.10,
        "soil_moisture_100_289cm": 0.05,
    }
    out = root_zone_soil_moisture(vals, 28)
    # (0.20*7 + 0.30*21) / 28 = 0.275؛ الطبقات العميقة خارج منطقة الجذر لا تدخل.
    assert out["value"] == 0.275
    assert out["layers_used"] == ["soil_moisture_0_7cm", "soil_moisture_7_28cm"]


def test_root_zone_deep_crop_includes_deep_layer_partial_overlap():
    # نخيل جذور عميقة 150سم ⇒ يشمل الطبقة الرابعة جزئيّاً (100–150 من 100–289).
    vals = {
        "soil_moisture_0_7cm": 0.20,
        "soil_moisture_7_28cm": 0.20,
        "soil_moisture_28_100cm": 0.20,
        "soil_moisture_100_289cm": 0.20,
    }
    out = root_zone_soil_moisture(vals, 150)
    assert out["value"] == 0.20  # كلّها متساوية ⇒ المتوسّط الموزون 0.20 مهما اختلفت الأوزان.
    assert "soil_moisture_100_289cm" in out["layers_used"]


def test_root_zone_drops_missing_layers_and_reduces_weight():
    # طبقة غائبة/غير رقميّة تُسقَط ووزنها معها — لا تُعامَل صفراً (لا اختلاق).
    vals = {"soil_moisture_0_7cm": 0.20, "soil_moisture_7_28cm": None}
    out = root_zone_soil_moisture(vals, 28)
    assert out["value"] == 0.20  # الطبقة الثانية غائبة ⇒ يبقى وزن الأولى فقط.
    assert out["layers_used"] == ["soil_moisture_0_7cm"]


def test_root_zone_explicit_unknown_on_bad_inputs():
    # لا اختلاق: مدخلات فاسدة ⇒ value=None + سبب صريح.
    assert root_zone_soil_moisture({}, 30)["value"] is None
    assert (
        root_zone_soil_moisture({"soil_moisture_0_7cm": 0.2}, 0)["reason"] == "invalid_root_depth"
    )
    assert root_zone_soil_moisture({"soil_moisture_0_7cm": "x"}, 30)["value"] is None
