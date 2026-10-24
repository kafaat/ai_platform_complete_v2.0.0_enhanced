"""اختبارات منتج ET0 الزراعيّ + نَسَب الخدمة (WS-C.1b consolidation) —

يتحقّق أنّ **المحرّك** يملك تنفيذ صيغة ET0 عبر عقد HTTP، ويعيد نَسَباً صادقاً:
method/quality_status/formula_version/valid_time/weather_snapshot_id. لا شبكة (اللقطة
من المُستهلِك) ⇒ لا 5xx على تعذّر مزوّد.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from et0 import et0_agro_product, weather_snapshot_id  # noqa: E402

main = importlib.import_module("main")

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "field",
    [
        "t_max_c",
        "t_min_c",
        "solar_rad_mj_m2",
        "rh_mean_pct",
        "wind_2m_ms",
        "t_mean_c",
        "lat_deg",
        "elevation_m",
        "day_of_year",
    ],
)
@pytest.mark.parametrize("value", [True, "0"])
def test_et0_http_rejects_coercible_values_before_the_engine(field, value):
    # Pydantic must not turn True into 1.0 before the engine can reject it.
    response = TestClient(main.app).post("/v1/weather/agro/et0", json={field: value})
    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_et0_http_rejects_nonfinite_json_numbers(value):
    response = TestClient(main.app).post(
        "/v1/weather/agro/et0",
        content='{"t_max_c": ' + value + "}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        "daily_t_min",
        "daily_t_max",
        "daily_solar_rad_mj_m2",
        "daily_rh_mean_pct",
        "daily_wind_2m_ms",
    ],
)
@pytest.mark.parametrize("value", [True, "0"])
def test_et0_series_http_rejects_coercible_samples(field, value):
    response = TestClient(main.app).post("/v1/weather/agro/et0/series", json={field: [value]})
    assert response.status_code == 422


def test_et0_http_accepts_integer_zero_without_coercing_unknowns():
    response = TestClient(main.app).post(
        "/v1/weather/agro/et0",
        json={"t_max_c": 0, "t_min_c": 0, "lat_deg": 15, "day_of_year": 100},
    )
    assert response.status_code == 200
    assert response.json()["et0_mm"] == 0.0
    assert response.json()["quality_status"] == "degraded"


def test_snapshot_id_deterministic_and_scheme():
    a = weather_snapshot_id({"t_max_c": 30.0, "t_min_c": 18.0, "lat_deg": 15.5})
    b = weather_snapshot_id({"lat_deg": 15.5, "t_min_c": 18.0, "t_max_c": 30.0})
    assert a == b  # مستقلّ عن ترتيب المفاتيح
    assert a.startswith("wsnap/sha1/1:")
    c = weather_snapshot_id({"t_max_c": 31.0, "t_min_c": 18.0, "lat_deg": 15.5})
    assert c != a  # طقس مختلف ⇒ بصمة مختلفة


def test_builder_pm_carries_provenance():
    out = et0_agro_product(
        t_max_c=30.0,
        t_min_c=18.0,
        solar_rad_mj_m2=22.0,
        rh_mean_pct=55.0,
        wind_2m_ms=2.0,
        lat_deg=15.5,
        elevation_m=2000.0,
        day_of_year=100,
        valid_time="2026-07-10T00:00:00Z",
    )
    assert out["method"] == "fao56_penman_monteith"
    assert out["quality_status"] == "validated"
    assert out["formula_version"] == "et0/fao56-pm/1.1.0"
    assert out["valid_time"] == "2026-07-10T00:00:00Z"
    assert out["weather_snapshot_id"].startswith("wsnap/sha1/1:")
    assert out["snapshot_source"] == "consumer_supplied_inputs"


def test_builder_missing_valid_time_is_declared_not_fabricated():
    out = et0_agro_product(t_max_c=30.0, t_min_c=18.0, lat_deg=15.5, day_of_year=100)
    assert out["valid_time"] is None
    assert any("valid_time not supplied" in lim for lim in out["limitations"])
    # نقص مدخلات PM ⇒ Hargreaves degraded صراحةً (لا يُقدَّم كـFAO-56).
    assert out["method"] == "hargreaves_fallback"
    assert out["quality_status"] == "degraded"


def test_snapshot_override_respected():
    out = et0_agro_product(
        t_max_c=30.0,
        t_min_c=18.0,
        lat_deg=15.5,
        day_of_year=100,
        weather_snapshot_id_override="wsnap/upstream/abc123",
    )
    assert out["weather_snapshot_id"] == "wsnap/upstream/abc123"


def test_route_agro_et0_returns_contract():
    os.environ.setdefault("SAHOOL_AGENT_TOKEN", "")
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/et0",
        json={
            "t_max_c": 30.0,
            "t_min_c": 18.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": 55.0,
            "wind_2m_ms": 2.0,
            "lat_deg": 15.5,
            "elevation_m": 2000.0,
            "day_of_year": 100,
            "valid_time": "2026-07-10T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["product"] == "et0"
    assert body["method"] == "fao56_penman_monteith"
    assert body["unit"] == "mm/day"
    assert body["weather_snapshot_id"].startswith("wsnap/")
    assert body["valid_time"] == "2026-07-10T00:00:00Z"


def test_route_agro_et0_carries_canonical_state_lineage_over_http():
    # WX-10.2: ET0 صار View مُشتقّاً من CanonicalWeatherState — العقد HTTP يحمل نَسَب الحالة.
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/et0",
        json={
            "t_max_c": 30.0,
            "t_min_c": 18.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": 55.0,
            "wind_2m_ms": 2.0,
            "lat_deg": 15.5,
            "elevation_m": 2000.0,
            "day_of_year": 100,
            "valid_time": "2026-07-10T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["derived_from"] == "canonical_weather_state"
    assert isinstance(body["canonical_state_id"], str) and body["canonical_state_id"]
    assert body["canonical_state_version"]
    # بلا override: نَسَب الحالة = بصمة اللقطة المحسوبة = weather_snapshot_id للمنتَج.
    assert body["source_snapshot_id"] == body["weather_snapshot_id"]


def test_route_agro_et0_snapshot_override_is_coherent_over_http():
    # override يدخل products.et0.weather_snapshot_id **و**source_snapshot_id للحالة (تماسك).
    client = TestClient(main.app)
    resp = client.post(
        "/v1/weather/agro/et0",
        json={
            "t_max_c": 30.0,
            "t_min_c": 18.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": 55.0,
            "wind_2m_ms": 2.0,
            "lat_deg": 15.5,
            "elevation_m": 2000.0,
            "day_of_year": 100,
            "valid_time": "2026-07-10T00:00:00Z",
            "weather_snapshot_id": "consumer-snap-xyz",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["weather_snapshot_id"] == "consumer-snap-xyz"
    assert body["source_snapshot_id"] == "consumer-snap-xyz"


def test_route_insufficient_when_geography_missing_no_5xx():
    # لا شبكة ⇒ لا 5xx؛ نقص الجغرافيا ⇒ insufficient صريح (200، et0_mm=None).
    client = TestClient(main.app)
    resp = client.post("/v1/weather/agro/et0", json={"t_max_c": 30.0, "t_min_c": 18.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "insufficient"
    assert body["et0_mm"] is None
    assert "lat_deg" in body["missing_inputs"]
