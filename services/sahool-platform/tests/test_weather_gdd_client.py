"""عميل GDD المنصّة → محرّك الطقس (WS-C.1c consolidation).

يتحقّق أنّ ``get_gdd_product`` يمرّر السلسلة اليوميّة + سياسة الموسم إلى
POST /v1/weather/agro/gdd، وأنّ تعذّر المحرّك يُنتشر كـHTTPException(502) —
ليفشل المُستهلِك مُغلَقاً بلا GDD محلّيّ.
"""

from __future__ import annotations

import pytest
from api import weather_service_client as wsc
from fastapi import HTTPException

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_gdd_product_posts_series_and_policy(monkeypatch):
    seen = {}

    async def _fake_post(path, *, json_body, **_kw):
        seen["path"] = path
        seen["body"] = json_body
        return {
            "product": "gdd",
            "daily_gdd": [10.0, 10.5],
            "accumulated_gdd": 20.5,
            "thresholds_used": {"base_c": 10.0, "upper_cutoff_c": 30.0, "method": "modified"},
            "calculation_version": "gdd/daily/1.0.0",
        }

    monkeypatch.setattr(wsc, "weather_post_json", _fake_post)
    out = await wsc.get_gdd_product(
        daily_t_min=[18.0, 19.0],
        daily_t_max=[30.0, 31.0],
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
    )
    assert seen["path"] == "/v1/weather/agro/gdd"
    assert seen["body"]["daily_t_min"] == [18.0, 19.0]
    assert seen["body"]["base_c"] == 10.0
    assert seen["body"]["method"] == "modified"
    assert out["accumulated_gdd"] == 20.5
    assert out["calculation_version"] == "gdd/daily/1.0.0"


@pytest.mark.asyncio
async def test_get_gdd_product_propagates_engine_down(monkeypatch):
    async def _down(*_a, **_k):
        raise HTTPException(status_code=502, detail="weather-service غير متاح")

    monkeypatch.setattr(wsc, "weather_post_json", _down)
    with pytest.raises(HTTPException) as ei:
        await wsc.get_gdd_product(daily_t_min=[18.0], daily_t_max=[30.0], base_c=10.0)
    assert ei.value.status_code == 502
