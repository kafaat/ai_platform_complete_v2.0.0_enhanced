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
