"""عميل ET0 المنصّة → محرّك الطقس (WS-C.1b consolidation).

يتحقّق أنّ ``get_et0_product`` يمرّر متّجه الطقس إلى POST /v1/weather/agro/et0، وأنّ
تعذّر المحرّك يُنتشر كـHTTPException(502) — ليفشل المُستهلِك مُغلَقاً بلا ET0 محلّيّ.
"""

from __future__ import annotations

import pytest
from api import weather_service_client as wsc
from fastapi import HTTPException

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_irrigation_adapter_maps_router_vector_to_owner_client(monkeypatch):
    seen = {}
    product = {"et0_mm": 0.0, "method": "hargreaves_fallback"}

    async def canonical(**kwargs):
        seen.update(kwargs)
        return product

    monkeypatch.setattr(wsc, "get_et0_product", canonical)
    result = await wsc.get_irrigation_et0_product(
        t_min_c=0.0,
        t_max_c=20.0,
        solar_rad_mj_m2=None,
        rh_mean_pct=None,
        wind_2m_ms=0.0,
        day_of_year=100,
        latitude_deg=16.0,
        elevation_m=120.0,
        valid_time="2026-04-10",
        tenant_id="tenant-1",
    )
    assert result is product
    assert seen == {
        "t_min_c": 0.0,
        "t_max_c": 20.0,
        "solar_rad_mj_m2": None,
        "rh_mean_pct": None,
        "wind_2m_ms": 0.0,
        "day_of_year": 100,
        "lat_deg": 16.0,
        "elevation_m": 120.0,
        "valid_time": "2026-04-10",
        "tenant_id": "tenant-1",
    }


def test_et0_projection_keeps_zero_and_owner_diagnostics_without_promoting_quality():
    product = {
        "et0_mm": 0.0,
        "method": "hargreaves_fallback",
        "quality_status": "degraded",
        "formula_version": "et0/fao56-pm/1.1.0",
        "valid_time": None,
        "weather_snapshot_id": "snapshot",
        "unit": "mm/day",
        "input_completeness": 0.0,
        "missing_inputs": ["wind_2m_ms"],
        "invalid_inputs": ["rh_mean_pct"],
        "limitations": ["not field calibrated"],
    }
    result = wsc.et0_provenance(product)
    assert result == {**product, "source": "weather-engine"}
    result["missing_inputs"].append("other")
    assert product["missing_inputs"] == ["wind_2m_ms"]


def _et0_response(**overrides):
    """Actual engine envelope, including nullable consumer-declared valid_time."""
    result = {
        "product": "et0",
        "unit": "mm/day",
        "et0_mm": 4.8,
        "method": "fao56_penman_monteith",
        "quality_status": "validated",
        "formula_version": "et0/fao56-pm/1.1.0",
        "input_completeness": 1.0,
        "weather_snapshot_id": "wsnap/sha1/1:abc",
        "valid_time": None,
        "missing_inputs": [],
        "invalid_inputs": [],
        "limitations": [],
    }
    result.update(overrides)
    return result


@pytest.mark.asyncio
async def test_get_et0_product_posts_weather_vector(monkeypatch):
    seen = {}

    async def _fake_post(path, *, json_body, **_kw):
        seen["path"] = path
        seen["body"] = json_body
        return _et0_response(valid_time="2026-07-10T00:00:00Z")

    monkeypatch.setattr(wsc, "weather_post_json", _fake_post)
    out = await wsc.get_et0_product(
        t_max_c=30.0,
        t_min_c=18.0,
        rh_mean_pct=55.0,
        lat_deg=15.5,
        day_of_year=100,
        valid_time="2026-07-10T00:00:00Z",
    )
    assert seen["path"] == "/v1/weather/agro/et0"
    assert seen["body"]["t_max_c"] == 30.0
    assert seen["body"]["lat_deg"] == 15.5
    assert seen["body"]["valid_time"] == "2026-07-10T00:00:00Z"
    assert out["method"] == "fao56_penman_monteith"
    assert out["weather_snapshot_id"] == "wsnap/sha1/1:abc"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"et0_mm": True},
        {"et0_mm": "4.8"},
        {"et0_mm": float("nan")},
        {"et0_mm": float("inf")},
        {"et0_mm": -1},
        {"et0_mm": {}},
        {"product": "gdd"},
        {"unit": "inch/day"},
        {"method": "guess"},
        {"quality_status": "excellent"},
        {"quality_status": "insufficient"},
        {"method": "hargreaves_fallback", "quality_status": "validated"},
        {"et0_mm": None},
        {"missing_inputs": "wind"},
        {"invalid_inputs": {"wind": True}},
        {"limitations": [None]},
        {"limitations": "secret upstream body"},
        {"formula_version": None},
        {"weather_snapshot_id": ""},
        {"valid_time": []},
        {"et0_mm": 10**1000},
        {"input_completeness": True},
        {"input_completeness": None},
        {"input_completeness": "1"},
        {"input_completeness": float("nan")},
        {"input_completeness": float("inf")},
        {"input_completeness": -0.1},
        {"input_completeness": 1.1},
        {"input_completeness": 10**1000},
        {"input_completeness": 0.5},
        {"missing_inputs": ["wind_2m_ms"]},
        {"invalid_inputs": ["wind_2m_ms"]},
    ],
)
async def test_et0_boundary_rejects_malformed_products(monkeypatch, overrides):
    async def fake(*_args, **_kwargs):
        return _et0_response(**overrides)

    monkeypatch.setattr(wsc, "weather_post_json", fake)
    with pytest.raises(HTTPException) as error:
        await wsc.get_et0_product(t_max_c=30, t_min_c=18)
    assert error.value.status_code == 502
    assert error.value.detail["reason_code"] == "weather_service_invalid_response"
    assert "secret" not in str(error.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, [], "bad", {}, {"value": []}])
async def test_et0_boundary_requires_product_envelope(monkeypatch, payload):
    async def fake(*_args, **_kwargs):
        return payload

    monkeypatch.setattr(wsc, "weather_post_json", fake)
    with pytest.raises(HTTPException) as error:
        await wsc.get_et0_product(t_max_c=30, t_min_c=18)
    assert error.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"et0_mm": 0},
        {
            "method": "hargreaves_fallback",
            "quality_status": "degraded",
            "missing_inputs": ["wind_2m_ms"],
        },
        {
            "et0_mm": None,
            "method": "insufficient",
            "quality_status": "insufficient",
            "missing_inputs": ["t_min_c"],
        },
        {
            "et0_mm": None,
            "method": "insufficient",
            "quality_status": "invalid",
            "invalid_inputs": ["t_min_c"],
        },
    ],
)
async def test_et0_boundary_preserves_zero_abstention_and_degraded_advisory(monkeypatch, overrides):
    payload = _et0_response(**overrides)

    async def fake(*_args, **_kwargs):
        return payload

    monkeypatch.setattr(wsc, "weather_post_json", fake)
    out = await wsc.get_et0_product(t_max_c=30, t_min_c=18)
    assert out == payload
    assert out["et0_mm"] is payload["et0_mm"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing", ["et0_mm", "method", "quality_status", "unit", "missing_inputs", "valid_time"]
)
async def test_et0_boundary_rejects_missing_contract_members(monkeypatch, missing):
    payload = _et0_response()
    del payload[missing]

    async def fake(*_args, **_kwargs):
        return payload

    monkeypatch.setattr(wsc, "weather_post_json", fake)
    with pytest.raises(HTTPException) as error:
        await wsc.get_et0_product(t_max_c=30, t_min_c=18)
    assert error.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vector",
    [
        {"t_min_c": 18, "t_max_c": 30, "lat_deg": 15.5, "day_of_year": 100},
        {"t_min_c": None, "t_max_c": 30, "lat_deg": 15.5, "day_of_year": 100},
        {"t_min_c": 40, "t_max_c": 30, "lat_deg": 15.5, "day_of_year": 100},
        {
            "t_min_c": 18,
            "t_max_c": 30,
            "lat_deg": 15.5,
            "day_of_year": 100,
            "solar_rad_mj_m2": 20,
            "rh_mean_pct": 55,
            "wind_2m_ms": 2,
            "elevation_m": 100,
        },
    ],
)
async def test_et0_boundary_accepts_real_engine_products(monkeypatch, vector):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "weather-service" / "et0.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("owner_et0_contract_fixture", path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    payload = engine.et0_agro_product(**vector)

    async def fake(*_args, **_kwargs):
        return payload

    monkeypatch.setattr(wsc, "weather_post_json", fake)
    assert await wsc.get_et0_product(**vector) == payload


@pytest.mark.asyncio
async def test_get_et0_product_propagates_engine_down(monkeypatch):
    async def _down(*_a, **_k):
        raise HTTPException(status_code=502, detail="weather-service غير متاح")

    monkeypatch.setattr(wsc, "weather_post_json", _down)
    with pytest.raises(HTTPException) as ei:
        await wsc.get_et0_product(t_max_c=30.0, t_min_c=18.0, lat_deg=15.5, day_of_year=100)
    assert ei.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize(
    "failure, status, reason",
    [
        ("timeout", 504, "weather_service_timeout"),
        ("network", 502, "weather_service_unavailable"),
        ("invalid_json", 502, "weather_service_invalid_response"),
    ],
)
async def test_weather_boundary_errors_are_stable_and_nonleaking(
    monkeypatch, method, failure, status, reason
):
    import httpx

    original_client = httpx.AsyncClient

    async def transport(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("")
        if failure == "network":
            raise httpx.ConnectError("secret URL and credentials")
        return httpx.Response(200, text="<html>secret upstream response</html>")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    with pytest.raises(HTTPException) as error:
        if method == "get":
            await wsc.weather_get_json("/v1/weather/current")
        else:
            await wsc.weather_post_json("/v1/weather/agro/et0", json_body={})
    assert error.value.status_code == status
    assert error.value.detail["reason_code"] == reason
    assert error.value.detail["message_ar"]
    assert "secret" not in str(error.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "post"])
async def test_weather_timeout_bounds_whole_request_and_cancels_transport(monkeypatch, method):
    import asyncio

    import httpx

    original_client = httpx.AsyncClient
    cancelled = False

    async def transport(request):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled = True
            raise

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    request = (
        wsc.weather_get_json("/v1/weather/current", timeout_s=0.01)
        if method == "get"
        else wsc.weather_post_json("/v1/weather/agro/et0", json_body={}, timeout_s=0.01)
    )
    with pytest.raises(HTTPException) as error:
        await asyncio.wait_for(request, timeout=1)
    assert error.value.status_code == 504
    assert error.value.detail["reason_code"] == "weather_service_timeout"
    assert cancelled


# ── مكسور ≠ عطل تبعيّة: المحرّك يرفض مُدخَلاً مستحيلاً ⇒ 422 لا 503 ──
def test_rejected_inputs_map_to_422_with_the_named_fields():
    exc = wsc.et0_unavailable_http_exception(
        {
            "et0_mm": None,
            "quality_status": "invalid",
            "invalid_inputs": ["t_max_c", "t_min_c"],
            "limitations": ["t_max_c rejected: t_max_c < t_min_c"],
        }
    )
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 422
    assert exc.detail["reason_code"] == "invalid_weather_inputs"
    assert exc.detail["invalid_inputs"] == ["t_max_c", "t_min_c"]


@pytest.mark.parametrize("prod", [None, {}, {"et0_mm": None, "invalid_inputs": []}])
def test_no_et0_without_rejections_stays_503_fail_closed(prod):
    exc = wsc.et0_unavailable_http_exception(prod)
    assert exc.status_code == 503
    assert "fail-closed" in exc.detail


def test_field_response_keeps_the_route_shape_and_names_the_rejection():
    out = wsc.et0_unavailable_field_response(
        {"et0_mm": None, "invalid_inputs": ["wind_2m_ms"], "limitations": ["wind rejected"]},
        "fld_1",
        "season_2026",
        {"crop": "wheat"},
        ["water-ledger:x"],
        ["state note"],
    )
    assert out["status"] == "dependency_unavailable"
    assert (out["field_id"], out["season_id"], out["inputs"]) == (
        "fld_1",
        "season_2026",
        {"crop": "wheat"},
    )
    assert out["recommendation"] is None and out["calibrated"] is False
    assert out["invalid_inputs"] == ["wind_2m_ms"]
    assert out["limitations"][0] == "state note"
    assert out["limitations"][-1] == "wind rejected"
    assert wsc.et0_unavailable_field_response(None, "f", None, {}, [], [])["invalid_inputs"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("wind_max_ms", [0, 3, 40])
async def test_field_snapshot_does_not_promote_normalized_wind_max_to_daily_mean(wind_max_ms):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "weather-service" / "open_meteo.py"
    spec = importlib.util.spec_from_file_location("owner_forecast_contract_fixture", path)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    normalized = owner.normalize_daily(
        {
            "daily": {
                "time": ["2026-07-10", "2026-07-11", "2026-07-12"],
                "temperature_2m_min": [18, 19, 20],
                "temperature_2m_max": [30, 31, 32],
                "wind_speed_10m_max": [wind_max_ms * 3.6] * 3,
                "precipitation_sum": [0, 2, 3],
            }
        },
        lat=15.5,
        lon=44.2,
        source="open-meteo-forecast",
        model="best_match",
    )
    assert normalized["days"][0]["wind_max_ms"] == wind_max_ms

    async def forecast_loader(lat, lon, *, days):
        assert (lat, lon, days) == (15.5, 44.2, 3)
        return normalized

    snapshot = await wsc.field_irrigation_weather_snapshot(
        15.5, 44.2, forecast_loader=forecast_loader
    )
    assert snapshot["wind_2m_ms"] is None
    assert snapshot["rh_mean_pct"] is None
    assert snapshot["rain_recent_mm"] == 0
    assert snapshot["forecast_rain_mm"] == 5
    assert snapshot["valid_time"] == "2026-07-10"
