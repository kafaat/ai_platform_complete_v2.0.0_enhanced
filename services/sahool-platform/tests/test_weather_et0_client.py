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
async def test_get_et0_product_posts_weather_vector(monkeypatch):
    seen = {}

    async def _fake_post(path, *, json_body, **_kw):
        seen["path"] = path
        seen["body"] = json_body
        return {
            "product": "et0",
            "et0_mm": 4.8,
            "method": "fao56_penman_monteith",
            "quality_status": "validated",
            "formula_version": "et0/fao56-pm/1.0.0",
            "weather_snapshot_id": "wsnap/sha1/1:abc",
            "valid_time": "2026-07-10T00:00:00Z",
        }

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
