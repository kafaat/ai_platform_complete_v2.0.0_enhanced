"""بُناة مدخلات PCSE/WOFOST وغراء مُخرَجه — بلا pcse، فيغطّيها CI الوحدة.

العطل الذي وُجِد هذا لأجله (مقيس 2026-09-29، pcse 6.0.13): بُناة ``wofost_adapter`` كانت أقلاباً —
``_build_agromanagement`` يُعيد dict الإدارة خامّاً (``AgroManager.initialize``: ``'str' object has
no attribute 'keys'``)، و``_build_weather_provider`` يُعيد **الصنف** لا نسخةً مملوءة، و``sitedata={}``،
والتربة dict خامّ، و``CTRAT`` بالسنتيمتر يُعاد في ``water_use`` كأنّه ملّيمتر، و``YAMLCropDataProvider()``
يجلب المعاملات من GitHub وقت التشغيل. هنا يُقاس: الشكل الذي يقرؤه PCSE، ووحداته بالضبط، ورفض النقص
**باسمه** بدل اختلاقه، وسلامة الملفّات المحزومة، وتحويل ``CTRAT`` إلى ملّيمتر في المُخرَج.
التشغيل الحقيقيّ (pcse مُركَّبة) في ``test_wofost_pcse_offline_integration.py``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import sys
import types
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SVC = os.path.join(ROOT, "services", "agriai-engine")
if _SVC not in sys.path:
    sys.path.insert(0, _SVC)

import pcse_inputs as pi  # noqa: E402
import sim_crop_registry  # noqa: E402
import wofost_adapter as wa  # noqa: E402

START = date(2025, 7, 15)


def _day(d: date, **over):
    day = {
        "date": d.isoformat(),
        "tmin": 10.0,
        "tmax": 25.0,
        "rain_mm": 2.0,
        "solar_radiation_mj_m2": 20.0,
        "vapour_pressure_hpa": 12.0,
        "wind_2m_m_s": 2.5,
    }
    day.update(over)
    return {k: v for k, v in day.items() if v is not None}


def _weather(n=120, start=START, **over):
    wx = {
        "latitude": 15.35,
        "longitude": 44.21,
        "elevation_m": 2250.0,
        "daily": [_day(start + timedelta(days=i)) for i in range(n)],
    }
    wx.update(over)
    return wx


def _code(exc: pytest.ExceptionInfo) -> str:
    return str(exc.value)


BARLEY = sim_crop_registry.get("barley")


# ── الطقس: الوحدات بالضبط ──


def test_weather_day_units_map_exactly_to_pcse():
    wx = _weather(n=2)
    wx["daily"][0] = _day(
        START,
        rain_mm=12.5,
        solar_radiation_mj_m2=18.0,
        vapour_pressure_hpa=None,
        vapour_pressure_kpa=1.2,
    )
    out = pi.build_weather(wx)
    d0, d1 = out["days"]
    assert d0["DAY"] == START and isinstance(d0["DAY"], date)
    assert d0["RAIN"] == pytest.approx(1.25)  # mm ⇒ cm
    assert d0["IRRAD"] == pytest.approx(18.0e6)  # MJ/m² ⇒ J/m²
    assert d0["VAP"] == pytest.approx(12.0)  # kPa ⇒ hPa
    assert d1["VAP"] == 12.0  # hPa كما هو
    assert (d0["TMIN"], d0["TMAX"], d0["WIND"], d0["WIND_HEIGHT_M"]) == (10.0, 25.0, 2.5, 2)
    assert out["site"] == {"LAT": 15.35, "LON": 44.21, "ELEV": 2250.0}
    assert out["vapour_pressure_from"] == ["vapour_pressure_hpa", "vapour_pressure_kpa"]
    assert out["angstrom"] == {"A": None, "B": None, "from": "pcse_default"}


def test_wind_10m_is_tagged_for_pcse_conversion_not_converted_here():
    wx = _weather(n=1)
    wx["daily"][0] = _day(START, wind_2m_m_s=None, wind_10m_m_s=4.0)
    day = pi.build_weather(wx)["days"][0]
    # التحويل 10⇒2 م يخصّ pcse.util.wind10to2 في طبقة pcse؛ لا صيغة طقس في الوحدة الصرفة.
    assert (day["WIND"], day["WIND_HEIGHT_M"]) == (4.0, 10)


def test_days_are_sorted_and_bounded():
    wx = _weather(n=3)
    wx["daily"].reverse()
    out = pi.build_weather(wx)
    assert [d["DAY"] for d in out["days"]] == [START + timedelta(days=i) for i in range(3)]
    assert (out["first_date"], out["last_date"]) == (START, START + timedelta(days=2))


def _with_day0(**over):
    wx = _weather(n=3)
    wx["daily"][0] = _day(START, **over)
    return wx


@pytest.mark.parametrize(
    "weather, expected",
    [
        ({"daily": []}, "weather_daily_required"),
        ("not-a-dict", "weather_daily_required"),
        (
            {"daily": [_day(START)]},
            "weather_site_missing:latitude,longitude,elevation_m",
        ),
        (_weather(latitude=95.0), "weather_site_invalid:latitude"),
        (_weather(elevation_m="2250"), "weather_site_invalid:elevation_m"),
        # الرطوبة/نقطة الندى لا تُشتقّ هنا (حارس صيغ محرّك الطقس): يُطلب ضغط البخار نفسه.
        (
            _with_day0(vapour_pressure_hpa=None, rh_mean_pct=55.0, dew_point_c=8.0),
            "weather_day_missing:0:vapour_pressure_hpa|vapour_pressure_kpa",
        ),
        (
            _with_day0(wind_2m_m_s=None, wind_m_s=3.0),
            "weather_day_missing:0:wind_2m_m_s|wind_10m_m_s(wind_m_s_has_no_declared_height)",
        ),
        (_with_day0(tmax=None), "weather_day_missing:0:tmax"),
        (_with_day0(vapour_pressure_kpa=1.2), "weather_day_ambiguous:0:vapour_pressure"),
        (_with_day0(wind_10m_m_s=3.0), "weather_day_ambiguous:0:wind"),
        (_with_day0(rain_mm=300.0), "weather_day_out_of_range:0:rain_mm"),  # 30 cm > 25
        (
            _with_day0(solar_radiation_mj_m2=45.0),
            "weather_day_out_of_range:0:solar_radiation_mj_m2",
        ),
        (_with_day0(vapour_pressure_hpa=0.01), "weather_day_out_of_range:0:vapour_pressure_hpa"),
        (_with_day0(tmin=30.0, tmax=20.0), "weather_day_invalid:0:tmin_gt_tmax"),
        (_with_day0(tmin="12"), "weather_day_invalid:0:tmin"),
        (_with_day0(tmin=True), "weather_day_invalid:0:tmin"),
        (_with_day0(tmin=float("nan")), "weather_day_invalid:0:tmin"),
        (_with_day0(date="15/07/2025"), "weather_day_invalid:0:date"),
        (_weather(angstrom_a=0.25), "weather_angstrom_invalid"),
        (_weather(angstrom_a=0.5, angstrom_b=0.3), "weather_angstrom_invalid:A=0.5,B=0.3"),
    ],
)
def test_weather_rejections_are_named_not_invented(weather, expected):
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_weather(weather)
    assert _code(exc).startswith(expected)


def test_duplicate_and_missing_days_are_named():
    dup = _weather(n=3)
    dup["daily"][2] = _day(START + timedelta(days=1))
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_weather(dup)
    assert _code(exc) == "weather_dates_duplicate:2025-07-16"
    gap = _weather(n=4)
    del gap["daily"][1]
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_weather(gap)
    # يومٌ ناقص كان سيصير WeatherDataProviderError في منتصف الموسم (503 مُبهَم).
    assert _code(exc) == "weather_dates_not_contiguous:2025-07-16"


def test_request_angstrom_is_kept_and_tagged():
    out = pi.build_weather(_weather(angstrom_a=0.18, angstrom_b=0.55))
    assert out["angstrom"] == {"A": 0.18, "B": 0.55, "from": "request"}


# ── التربة والموقع ──


def test_default_soil_values_come_from_the_vendored_file():
    soil = pi.load_default_soil()
    assert soil["name"] == "EC3-medium fine"
    assert soil["file"] == os.path.join("soil", "ec3.soil")
    assert soil["values"] == {
        "SMFCF": 0.300,
        "SMW": 0.104,
        "SM0": 0.410,
        "CRAIRC": 0.060,
        "RDMSOL": 120.0,
        "SOPE": 1.47,
        "KSUB": 1.47,
    }


def test_empty_soil_uses_the_named_default_for_every_parameter():
    built = pi.build_soil({})
    assert built["source"] == "default_soil"
    assert built["defaulted"] == [k for k, _ in pi.SOIL_FIELDS]
    assert set(built["origin"].values()) == {"default_soil:" + os.path.join("soil", "ec3.soil")}


def test_request_soil_overrides_and_the_rest_is_named_default():
    built = pi.build_soil({"field_capacity": 0.32, "wilting_point": 0.12, "rootable_depth_cm": 90})
    assert built["source"] == "request+default_soil"
    assert (built["params"]["SMFCF"], built["params"]["SMW"], built["params"]["RDMSOL"]) == (
        0.32,
        0.12,
        90.0,
    )
    assert built["origin"]["SMFCF"] == "request:field_capacity"
    assert built["defaulted"] == ["SM0", "CRAIRC", "SOPE", "KSUB"]


@pytest.mark.parametrize(
    "soil, expected",
    [
        # سعة حقليّة لطين (0.45) مع تشبّع EC3 الافتراضيّ (0.41) ⇒ ترتيبٌ مكسور يُسمّى مصدره.
        ({"field_capacity": 0.45}, "soil_invalid:wilting_point<field_capacity<saturation"),
        ({"rootable_depth_cm": 8}, "soil_invalid:rootable_depth_cm"),
        ({"saturation": 1.2}, "soil_invalid:saturation"),
        ({"max_percolation_subsoil_cm_d": 0}, "soil_invalid:max_percolation_subsoil_cm_d"),
        ({"wilting_point": "0.1"}, "soil_invalid:wilting_point"),
    ],
)
def test_soil_rejections_are_named(soil, expected):
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_soil(soil)
    assert _code(exc).startswith(expected)


def test_mixed_soil_rejection_names_the_defaulted_parameters():
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_soil({"field_capacity": 0.45})
    assert "(defaulted:SMW|SM0|CRAIRC|RDMSOL|SOPE|KSUB)" in _code(exc)


def test_site_initial_water_from_request_is_mm_to_cm():
    params = pi.build_soil({})["params"]
    site = pi.build_site({"available_water_mm": 150.0}, params)
    assert site == {"WAV": 15.0, "SMLIM": 0.3, "WAV_from": "request:available_water_mm"}


def test_site_initial_water_default_is_profile_at_field_capacity():
    params = pi.build_soil({})["params"]
    site = pi.build_site({}, params)
    assert site["WAV"] == pytest.approx((0.300 - 0.104) * 120.0)  # 23.52 cm من EC3 نفسها
    assert site["WAV_from"] == "default:profile_at_field_capacity"
    assert site["SMLIM"] == params["SMFCF"]  # لا طبقة أولى فوق السعة الحقليّة


def test_site_initial_water_outside_pcse_range_is_named():
    params = pi.build_soil({})["params"]
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_site({"available_water_mm": 1500.0}, params)  # 150 cm > 100
    assert _code(exc).startswith("site_invalid:WAV=150cm")


# ── الإدارة: الشكل الذي يقرؤه AgroManager بالضبط ──


def test_agromanagement_has_the_exact_agromanager_shape():
    last = START + timedelta(days=119)
    out = pi.build_agromanagement({"planting_date": START.isoformat()}, BARLEY, START, last)
    campaigns = out["agromanagement"]
    # كان dict الإدارة يُمرَّر خامّاً: AgroManager يمشي على مفاتيحه النصّيّة فيسقط على .keys().
    assert isinstance(campaigns, list) and len(campaigns) == 1
    ((campaign_start, campaign),) = campaigns[0].items()
    assert campaign_start == START and isinstance(campaign_start, date)
    assert set(campaign) == {"CropCalendar", "TimedEvents", "StateEvents"}
    assert campaign["TimedEvents"] is None and campaign["StateEvents"] is None
    assert campaign["CropCalendar"] == {
        "crop_name": "barley",
        "variety_name": "Spring_barley_301",
        "crop_start_date": START,
        "crop_start_type": "sowing",
        "crop_end_date": None,
        "crop_end_type": "maturity",
        "max_duration": 119,  # حتى آخر يوم طقس
    }
    assert out["season"]["end_limit_from"] == "weather_series_end"


def test_harvest_date_is_earliest_with_a_duration_that_cannot_overwrite_it():
    last = START + timedelta(days=150)
    harvest = START + timedelta(days=100)
    out = pi.build_agromanagement(
        {"planting_date": START.isoformat(), "harvest_date": harvest.isoformat()},
        BARLEY,
        START,
        last,
    )
    calendar = out["agromanagement"][0][START]["CropCalendar"]
    assert calendar["crop_end_type"] == "earliest" and calendar["crop_end_date"] == harvest
    # CropCalendar.__call__ يكتب «max_duration» فوق «harvest» إن تساويا في اليوم نفسه ⇒ لا DOH.
    assert calendar["max_duration"] == 101
    assert out["season"]["end_limit_from"] == "harvest_date"


def test_max_duration_days_limits_the_season():
    out = pi.build_agromanagement(
        {"planting_date": START.isoformat(), "max_duration_days": 30},
        BARLEY,
        START,
        START + timedelta(days=119),
    )
    calendar = out["agromanagement"][0][START]["CropCalendar"]
    assert (calendar["crop_end_type"], calendar["max_duration"]) == ("maturity", 30)
    assert out["season"]["end_limit_from"] == "max_duration_days"


@pytest.mark.parametrize(
    "am, expected",
    [
        ({}, "agromanagement_missing:planting_date"),
        ({"planting_date": "15-07-2025"}, "agromanagement_invalid:planting_date"),
        (
            {"planting_date": START.isoformat(), "crop_start_type": "transplant"},
            "agromanagement_invalid:crop_start_type",
        ),
        (
            {"planting_date": START.isoformat(), "harvest_date": START.isoformat()},
            "agromanagement_invalid:harvest_date_not_after_planting_date",
        ),
        (
            {"planting_date": (START - timedelta(days=1)).isoformat()},
            "weather_does_not_cover_season:2025-07-14..",
        ),
        (
            {
                "planting_date": START.isoformat(),
                "harvest_date": (START + timedelta(days=200)).isoformat(),
            },
            "weather_does_not_cover_season:2025-07-15..2026-01-31",
        ),
        (
            {"planting_date": START.isoformat(), "irrigation_mm": 120},
            "irrigation_schedule_required",
        ),
    ],
)
def test_agromanagement_rejections_are_named(am, expected):
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_agromanagement(am, BARLEY, START, START + timedelta(days=119))
    assert _code(exc).startswith(expected)


def test_irrigation_events_use_the_keys_waterbalance_reads():
    events = [
        {"date": (START + timedelta(days=20)).isoformat(), "depth_mm": 30.0},
        {"date": (START + timedelta(days=40)).isoformat(), "depth_mm": 25.0, "efficiency": 0.9},
    ]
    out = pi.build_agromanagement(
        {
            "planting_date": START.isoformat(),
            "irrigation_events": events,
            "application_efficiency": 0.7,
        },
        BARLEY,
        START,
        START + timedelta(days=119),
    )
    (timed,) = out["agromanagement"][0][START]["TimedEvents"]
    assert timed["event_signal"] == "irrigate"
    # WaterbalanceFD._on_IRRIGATE(amount, efficiency) — لا irrigation_amount (مثال الوثيقة).
    assert timed["events_table"] == [
        {START + timedelta(days=20): {"amount": 3.0, "efficiency": 0.7}},
        {START + timedelta(days=40): {"amount": 2.5, "efficiency": 0.9}},
    ]
    assert out["irrigation"] == {
        "mode": "dated_events",
        "events": 2,
        "gross_mm": 55.0,
        "net_mm": pytest.approx(30.0 * 0.7 + 25.0 * 0.9),
    }


@pytest.mark.parametrize(
    "event, expected",
    [
        ({"date": "2025-08-01", "depth_mm": 20.0}, "irrigation_event_invalid:0:efficiency"),
        ({"depth_mm": 20.0, "efficiency": 0.8}, "irrigation_event_invalid:0:date"),
        (
            {"date": "2025-08-01", "depth_mm": -1.0, "efficiency": 0.8},
            "irrigation_event_invalid:0:depth_mm",
        ),
        (
            {"date": "2026-08-01", "depth_mm": 20.0, "efficiency": 0.8},
            "irrigation_event_invalid:0:date_outside_season",
        ),
    ],
)
def test_irrigation_event_rejections_are_named(event, expected):
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_agromanagement(
            {"planting_date": START.isoformat(), "irrigation_events": [event]},
            BARLEY,
            START,
            START + timedelta(days=119),
        )
    assert _code(exc) == expected


def test_two_irrigations_on_one_day_are_rejected_not_silently_overwritten():
    day = (START + timedelta(days=10)).isoformat()
    with pytest.raises(pi.SimulationInputError) as exc:
        pi.build_agromanagement(
            {
                "planting_date": START.isoformat(),
                "application_efficiency": 0.8,
                "irrigation_events": [{"date": day, "depth_mm": 10}, {"date": day, "depth_mm": 5}],
            },
            BARLEY,
            START,
            START + timedelta(days=119),
        )
    assert _code(exc) == "irrigation_event_invalid:1:duplicate_date"


def test_rainfed_declared_vs_irrigation_not_declared():
    last = START + timedelta(days=119)
    declared = pi.build_agromanagement(
        {"planting_date": START.isoformat(), "irrigation_mm": 0}, BARLEY, START, last
    )
    silent = pi.build_agromanagement({"planting_date": START.isoformat()}, BARLEY, START, last)
    assert declared["irrigation"]["mode"] == "rainfed_declared"
    assert silent["irrigation"]["mode"] == "none_declared"


def test_run_inputs_name_every_default_and_serialise():
    plan = pi.build_run_inputs(BARLEY, _weather(), {}, {"planting_date": START.isoformat()})
    assert plan.defaults_applied == (
        "soil.SMFCF",
        "soil.SMW",
        "soil.SM0",
        "soil.CRAIRC",
        "soil.RDMSOL",
        "soil.SOPE",
        "soil.KSUB",
        "site.WAV",
        "weather.angstrom_ab",
        "irrigation.none_declared",
    )
    # ما يتسلّمه AgroManager: قائمة حملات مفاتيحها تواريخ — لا dict الطلب الخامّ (العطل المقيس).
    assert isinstance(plan.agromanagement, list)
    assert list(plan.agromanagement[0]) == [START]
    prov = json.loads(json.dumps(plan.provenance()))
    assert (
        prov["crop_parameters"]["version"]
        == pi.vendored_source_manifest()["crop_parameters"]["commit"]
    )
    assert prov["soil"]["source"] == "default_soil"
    assert prov["weather"]["days_supplied"] == 120


# ── الملفّات المحزومة: مطابِقة للمصدر، مرخَّصة، ولا ذاكرة pickle ──


def _lf_bytes(path: str) -> bytes:
    with open(path, "rb") as fp:  # سحبٌ على Windows قد يُحوِّل ‎.soil‎ إلى CRLF
        return fp.read().replace(b"\r\n", b"\n")


def test_vendored_files_are_byte_identical_to_the_pinned_upstream_blobs():
    manifest = pi.vendored_source_manifest()
    entries = [
        (os.path.join(pi.CROP_DIR, name), meta)
        for name, meta in manifest["crop_parameters"]["files"].items()
    ]
    entries.append(
        (os.path.join(pi.DATA_DIR, manifest["default_soil"]["file"]), manifest["default_soil"])
    )
    for path, meta in entries:
        content = _lf_bytes(path)
        assert hashlib.sha256(content).hexdigest() == meta["sha256"], path
        blob = hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False)
        assert blob.hexdigest() == meta["git_blob_sha1"], path


def test_registry_pins_the_vendored_commit_and_every_variety_exists():
    yaml = pytest.importorskip("yaml")
    manifest = pi.vendored_source_manifest()
    with open(os.path.join(pi.CROP_DIR, "crops.yaml"), encoding="utf-8") as fp:
        listed = yaml.safe_load(fp)["available_crops"]
    assert sorted(listed) == sorted(sim_crop_registry.SUPPORTED_CROP_NAMES)
    for name in sim_crop_registry.SUPPORTED_CROP_NAMES:
        crop = sim_crop_registry.get(name)
        assert crop.parameter_version == manifest["crop_parameters"]["commit"]
        with open(os.path.join(pi.CROP_DIR, f"{crop.pcse_crop}.yaml"), encoding="utf-8") as fp:
            doc = yaml.safe_load(fp)
        assert doc["Version"] == "1.0.0"  # نسخة الملفّ التي يقبلها YAMLCropDataProvider
        assert crop.pcse_variety in doc["CropParameters"]["Varieties"]
        assert doc["Metadata"]["Rights"] == manifest["crop_parameters"]["rights_declared_in_files"]


def test_licence_texts_ship_with_the_vendored_data():
    with open(os.path.join(pi.DATA_DIR, "LICENSE.EUPL-1.2.txt"), encoding="utf-8") as fp:
        assert fp.readline().strip() == "EUROPEAN UNION PUBLIC LICENCE v. 1.2"
    with open(os.path.join(pi.DATA_DIR, "LICENSE.pcse_notebooks.MIT.txt"), encoding="utf-8") as fp:
        assert "Copyright (c) 2017 Allard de Wit" in fp.read()
    notice = open(os.path.join(pi.DATA_DIR, "NOTICE.txt"), encoding="utf-8").read()
    assert "NOT covered by the repository's MIT licence" in notice


def test_no_pcse_pickle_cache_in_the_vendored_directory():
    # المُنشئ الأصليّ مع fpath يكتب YAMLCropDataProvider.pkl هنا ثمّ يقرؤه بـpickle.load.
    for dirpath, _dirs, files in os.walk(pi.DATA_DIR):
        assert not [f for f in files if f.endswith(".pkl")], dirpath


# ── المُحوِّل بلا pcse: ترتيب الإخفاق، السجلّات، وغراء المُخرَج ──


@pytest.fixture
def pcse_flag_on(monkeypatch):
    monkeypatch.setenv("SIM_PCSE_ENABLED", "1")
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "0")


def test_engine_absence_answers_before_inputs(monkeypatch, pcse_flag_on):
    monkeypatch.setattr(wa, "_PCSE_AVAILABLE", False)
    with pytest.raises(RuntimeError) as exc:
        wa.simulate({"name": "barley"}, _weather(), {}, {"planting_date": START.isoformat()})
    assert str(exc.value) == "simulation_unavailable:pcse_unavailable"


def test_installed_but_unimportable_pcse_is_named(monkeypatch, pcse_flag_on):
    monkeypatch.setattr(wa, "_PCSE_AVAILABLE", True)

    def boom():
        raise ImportError("traitlets_pcse missing")

    monkeypatch.setattr(wa, "_load_pcse", boom)
    with pytest.raises(RuntimeError) as exc:
        wa.simulate({"name": "barley"}, _weather(), {}, {"planting_date": START.isoformat()})
    assert str(exc.value) == "simulation_unavailable:pcse_import_failed"


def test_input_error_is_not_swallowed_into_engine_failure(monkeypatch, pcse_flag_on):
    monkeypatch.setattr(wa, "_PCSE_AVAILABLE", True)
    monkeypatch.setattr(wa, "_load_pcse", lambda: types.SimpleNamespace())
    with pytest.raises(pi.SimulationInputError) as exc:
        wa.simulate({"name": "barley"}, {"daily": [{"tmax": 25, "tmin": 10}]}, {}, {})
    assert exc.value.code == "weather_site_missing"


def test_simulate_endpoint_maps_input_errors_to_named_422(monkeypatch, pcse_flag_on):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "builders-token")
    spec = importlib.util.spec_from_file_location(
        "agriai_main_builders", os.path.join(_SVC, "main.py")
    )
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    monkeypatch.setattr(main.wa, "_PCSE_AVAILABLE", True)
    monkeypatch.setattr(main.wa, "_load_pcse", lambda: types.SimpleNamespace())
    resp = TestClient(main.app).post(
        "/v1/simulate",
        json={"crop": {"name": "barley"}, "weather": {"daily": [_day(START)]}},
        headers={"x-agent-token": "builders-token"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {
        "error": "simulation_inputs_invalid",
        "reason": "weather_site_missing",
        "detail": "latitude,longitude,elevation_m",
    }


def test_host_logging_is_restored_after_a_dictconfig_style_takeover():
    name = "sahool.test.pre_existing_logger"
    victim = logging.getLogger(name)
    root = logging.getLogger()
    saved = list(root.handlers), root.level
    disabled = {
        n: lg.disabled
        for n, lg in logging.Logger.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }
    intruder = logging.StreamHandler()
    try:
        # ما يفعله dictConfig في pcse: تعطيل ما سبق + معالجات جذر بديلة + مستوى NOTSET.
        victim.disabled = True
        for handler in list(root.handlers):
            root.removeHandler(handler)
        root.addHandler(intruder)
        root.setLevel(logging.NOTSET)
        wa._restore_host_logging(root, saved[0], saved[1], disabled)
        assert victim.disabled is False
        assert root.handlers == saved[0] and root.level == saved[1]
        assert intruder not in root.handlers
    finally:
        wa._restore_host_logging(root, saved[0], saved[1], disabled)


class _FakeModel:
    summary: dict = {}
    terminal: dict = {}
    seen: dict = {}

    def __init__(self, parameters, weather, agromanagement):
        _FakeModel.seen = {"parameters": parameters, "weather": weather, "agro": agromanagement}

    def run_till_terminate(self):
        pass

    def get_summary_output(self):
        return [dict(_FakeModel.summary)]

    def get_terminal_output(self):
        return dict(_FakeModel.terminal)


def _fake_pcse():
    class Crop:
        def set_active_crop(self, crop, variety):
            self.active = (crop, variety)

        def variety_metadata(self, crop, variety):
            return {"Coverage": {"Region": "Europe, global"}}

    class Weather:
        def __init__(self, wx):
            self.wx, self.angstA, self.angstB = wx, 0.29, 0.49

    def site(**kw):
        return {"IFUNRN": 0, "NOTINF": 0, "SSI": 0.0, "SSMAX": 0.0, **kw}

    return types.SimpleNamespace(
        version="6.0.13",
        CropDataProvider=Crop,
        WeatherDataProvider=Weather,
        WOFOST72SiteDataProvider=site,
        ParameterProvider=lambda **kw: kw,
        Wofost72_WLP_CWB=_FakeModel,
    )


def test_pcse_output_is_mapped_to_the_contract_units_and_real_stages():
    plan = pi.build_run_inputs(BARLEY, _weather(), {}, {"planting_date": START.isoformat()})
    _FakeModel.summary = {
        "TWSO": 6928.16,
        "TAGP": 13919.12,
        "CTRAT": 20.49,  # سم
        "CEVST": 5.43,  # سم
        "DVS": 2.0,
        "LAIMAX": 5.96,
        "RD": 120.0,
        "DOS": START,
        "DOE": START + timedelta(days=11),
        "DOA": START + timedelta(days=79),
        "DOM": START + timedelta(days=118),
        "DOH": None,
    }
    _FakeModel.terminal = {"RAINT": 23.56, "TOTIRR": 0.0, "TSR": 0.06}
    out = wa._pcse_run(_fake_pcse(), plan)
    assert out["water_use"] == pytest.approx(204.9)  # CTRAT سم ⇒ ملّيمتر (عقد المخطّط)
    assert out["diagnostics"]["soil_evaporation_mm"] == pytest.approx(54.3)
    assert out["diagnostics"]["water_balance_mm"] == {
        "rain": pytest.approx(235.6),
        "irrigation_effective": 0.0,
        "surface_runoff": pytest.approx(0.6),
    }
    assert (out["yield_kg_ha"], out["biomass"]) == (6928.16, 13919.12)
    assert out["provenance"] == "pcse_wofost_uncalibrated"
    assert out["stages"] == [
        {"stage": "sowing", "reached": True, "date": "2025-07-15", "at_dvs": None},
        {"stage": "emergence", "reached": True, "date": "2025-07-26", "at_dvs": 0.0},
        {"stage": "anthesis", "reached": True, "date": "2025-10-02", "at_dvs": 1.0},
        {"stage": "maturity", "reached": True, "date": "2025-11-10", "at_dvs": 2.0},
    ]
    diag = out["diagnostics"]
    assert diag["crop_cycle_end"] == "maturity" and diag["matured"] is True
    assert diag["defaults_applied"] == list(plan.defaults_applied)
    assert diag["variety_calibration_region"] == "Europe, global"
    assert diag["units"]["water_use"].startswith("mm")
    assert diag["pcse_site_defaults"] == {"IFUNRN": 0, "NOTINF": 0, "SSI": 0.0, "SSMAX": 0.0}
    # البنى التي تسلّمها النموذج هي بنى الباني لا dict الطلب الخامّ.
    assert _FakeModel.seen["agro"] is plan.agromanagement
    assert _FakeModel.seen["weather"].wx is plan.weather
    assert _FakeModel.seen["parameters"]["soildata"] == plan.soil["params"]
    assert _FakeModel.seen["parameters"]["sitedata"]["WAV"] == plan.site["WAV"]


def test_unfinished_season_is_not_reported_as_maturity():
    plan = pi.build_run_inputs(BARLEY, _weather(), {}, {"planting_date": START.isoformat()})
    _FakeModel.summary = {
        "TWSO": 900.0,
        "TAGP": 4000.0,
        "CTRAT": 8.0,
        "CEVST": 3.0,
        "DVS": 1.4,
        "DOS": START,
        "DOE": START + timedelta(days=11),
        "DOA": START + timedelta(days=79),
        "DOM": None,
        "DOH": None,
    }
    _FakeModel.terminal = {}
    out = wa._pcse_run(_fake_pcse(), plan)
    assert out["diagnostics"]["crop_cycle_end"] == "weather_series_end"
    assert out["diagnostics"]["matured"] is False
    assert out["stages"][-1] == {"stage": "maturity", "reached": False, "date": None, "at_dvs": 2.0}


def test_pcse_band_drivers_reflect_what_ran():
    daily = {"daily": [_day(START)]}
    ran_on_default_soil = {
        "yield_kg_ha": 6000.0,
        "provenance": "pcse_wofost_uncalibrated",
        "diagnostics": {"defaults_applied": ["soil.SM0", "site.WAV"]},
    }
    band = wa._yield_uncertainty(
        ran_on_default_soil, {"name": "barley"}, daily, {}, {"irrigation_events": [{}]}
    )
    assert "missing_rainfall" not in band["drivers"]  # المطر يوميّ وإلزاميّ في مسار PCSE
    assert "missing_irrigation_plan" not in band["drivers"]  # أحداث مؤرَّخة = خطّة
    assert "default_soil_hydraulics" in band["drivers"] and "missing_soil_water" in band["drivers"]
    fallback = wa._yield_uncertainty(
        {"yield_kg_ha": 6000.0, "provenance": "deterministic_fallback"},
        {},
        daily,
        {},
        {"irrigation_events": [{}]},
    )
    assert "missing_rainfall" in fallback["drivers"]  # البديل يقرأ total_rain_mm وحده
    assert "missing_irrigation_plan" in fallback["drivers"]
    assert "default_soil_hydraulics" not in fallback["drivers"]
