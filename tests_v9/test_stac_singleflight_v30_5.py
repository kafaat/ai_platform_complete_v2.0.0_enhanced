"""حارس: single-flight في عميل STAC (v6-F6) — miss متطابق متزامن = POST واحد.

كان ``ResilientStacClient.search`` يُطلق POST لكلّ miss متزامن ⇒ عند backfill متوازٍ
لنفس الحقل/النافذة تُقصَف Earth Search العامّة. الآن طلبٌ متطابق قيد التنفيذ يُتشارَك.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"


def _load_stac_client():
    sys.modules.setdefault("redis", types.ModuleType("redis"))
    spec = importlib.util.spec_from_file_location(
        "sahool_stac_client_sf", _RASTER / "stac_client.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_concurrent_identical_searches_hit_upstream_once(monkeypatch) -> None:
    stac_client = _load_stac_client()
    calls = {"n": 0}

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"features": [], "ok": True}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            calls["n"] += 1
            await asyncio.sleep(0.05)  # نافذة تسمح للطلبات المتزامنة بالتداخل
            return _FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    client = stac_client.ResilientStacClient("http://stac.example", redis_url=None)
    payload = {"bbox": [1, 2, 3, 4], "datetime": "2026-06-01/2026-06-30"}

    async def _run():
        results = await asyncio.gather(*[client.search(dict(payload)) for _ in range(5)])
        return results

    results = asyncio.run(_run())
    assert calls["n"] == 1, f"single-flight فشل: {calls['n']} POST بدل 1"
    assert client.stats["coalesced"] == 4, "أربعة طلبات يجب أن تُدمَج مع القائد"
    markers = {r.get("_cache") for r in results}
    assert markers == {"miss", "coalesced"}, f"علامات cache غير متوقّعة: {markers}"


def test_singleflight_map_cleared_after_completion(monkeypatch) -> None:
    """بعد اكتمال الطلب، تُنظَّف خريطة inflight (لا تسرّب ذاكرة/أقفال عالقة)."""
    stac_client = _load_stac_client()

    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"features": []}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    client = stac_client.ResilientStacClient("http://stac.example", redis_url=None)

    async def _run():
        await client.search({"bbox": [1, 2, 3, 4], "datetime": "a/b"})

    asyncio.run(_run())
    assert client._inflight == {}, "خريطة inflight لم تُنظَّف بعد الاكتمال"
