"""حرّاس single-flight وprovenance لعميل STAC المرن (EXTRA-2 / EXTRA-3).

EXTRA-2: إلغاء القائد كان يترك Future المنتظِرين بلا حسم (``except Exception`` لا يلتقط
``CancelledError``) فيعلق التابع للأبد؛ وإلغاء تابعٍ كان يُلغي Future المشترك فيسقط
بقيّة المنتظِرين بـ``CancelledError`` لم يطلبوه.

EXTRA-3: كان الـcache يخزّن الاستجابة الخام قبل إرفاق بيانات الاحتياطي، فتعود نتيجة
الاحتياطي من الـcache بلا هويّة مصدرها؛ وكان المحوِّل يعلن ``element84`` مصدراً حتّى على
مسار الاحتياطي. المغلَّف المخزَّن يجب أن يحمل الهويّة نفسها على مسارات miss/fresh/stale.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import stac_search  # noqa: E402
from stac_client import ResilientStacClient  # noqa: E402

PRIMARY = "https://primary.invalid/v1"
FALLBACK = "https://planetarycomputer.microsoft.com/api/stac/v1"
PAYLOAD = {"collections": ["sentinel-2-c1-l2a"], "bbox": [44, 15, 45, 16], "limit": 5}


def _gated_client():
    """عميل يُستبدَل فيه الحلّ غير المخزَّن بمكالمة تنتظر بوّابة يتحكّم بها الاختبار."""
    client = ResilientStacClient(PRIMARY, max_retries=1)
    gate = asyncio.Event()
    calls = {"n": 0, "cancelled": 0}

    async def resolve(key, payload, entry):
        calls["n"] += 1
        try:
            await gate.wait()
        except asyncio.CancelledError:
            calls["cancelled"] += 1
            raise
        return {"features": [{"id": "scene-1"}], "_cache": "miss"}

    client._resolve_uncached = resolve  # type: ignore[method-assign]
    return client, gate, calls


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


def test_leader_cancellation_hands_shared_result_to_follower():
    async def scenario():
        client, gate, calls = _gated_client()
        leader = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        follower = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        leader.cancel()
        await _settle()
        gate.set()
        # قبل الإصلاح: يعلق التابع للأبد (Future لم يُحسَم) → TimeoutError.
        data = await asyncio.wait_for(follower, timeout=2)
        assert leader.cancelled()
        assert data["features"] == [{"id": "scene-1"}]
        assert data["_cache"] == "coalesced"
        assert calls["n"] == 1  # لا POST ثانٍ: التابع ورث العمل المشترك
        assert client._inflight == {}

    asyncio.run(scenario())


def test_follower_cancellation_does_not_cancel_leader_or_other_followers():
    async def scenario():
        client, gate, calls = _gated_client()
        leader = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        f1 = asyncio.create_task(client.search(PAYLOAD))
        f2 = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        f1.cancel()
        await _settle()
        gate.set()
        leader_data = await asyncio.wait_for(leader, timeout=2)
        # قبل الإصلاح: إلغاء f1 يُلغي Future المشترك فيسقط f2 بـCancelledError.
        f2_data = await asyncio.wait_for(f2, timeout=2)
        assert f1.cancelled()
        assert leader_data["features"] == f2_data["features"] == [{"id": "scene-1"}]
        assert calls["n"] == 1 and calls["cancelled"] == 0
        assert client._inflight == {}

    asyncio.run(scenario())


def test_cancelling_every_waiter_cancels_shared_work_and_clears_inflight():
    async def scenario():
        client, gate, calls = _gated_client()
        leader = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        follower = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        leader.cancel()
        follower.cancel()
        await _settle()
        assert leader.cancelled() and follower.cancelled()
        assert calls["cancelled"] == 1  # لا عمل يتيم بلا منتظِر
        assert client._inflight == {}
        # طلب لاحق يبدأ رحلة جديدة لا ترث الرحلة الملغاة.
        gate.set()
        data = await asyncio.wait_for(client.search(PAYLOAD), timeout=2)
        assert data["features"] == [{"id": "scene-1"}]
        assert calls["n"] == 2

    asyncio.run(scenario())


def test_leader_failure_is_shared_with_followers_without_hanging():
    async def scenario():
        client = ResilientStacClient(PRIMARY, max_retries=1)
        gate = asyncio.Event()

        async def resolve(key, payload, entry):
            await gate.wait()
            raise RuntimeError("upstream down")

        client._resolve_uncached = resolve  # type: ignore[method-assign]
        leader = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        follower = asyncio.create_task(client.search(PAYLOAD))
        await _settle()
        gate.set()
        for task in (leader, follower):
            try:
                await asyncio.wait_for(task, timeout=2)
            except RuntimeError as exc:
                assert "upstream down" in str(exc)
            else:  # pragma: no cover - يجب أن يفشل
                raise AssertionError("expected shared failure")
        assert client._inflight == {}

    asyncio.run(scenario())


# ── EXTRA-3: provenance ─────────────────────────────────────────────────────────


def _fake_httpx(monkeypatch, *, primary_up: bool, fallback_up: bool = True):
    class Resp:
        def __init__(self, scene_id):
            self._scene_id = scene_id

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": self._scene_id,
                        "collection": "sentinel-2-c1-l2a",
                        "properties": {
                            "datetime": "2026-07-01T08:00:00Z",
                            "eo:cloud_cover": 3.0,
                        },
                        "assets": {},
                    }
                ],
                "links": [],
            }

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, **kw):
            if url.startswith(PRIMARY):
                if not primary_up:
                    raise RuntimeError("primary unavailable")
                return Resp("primary-scene")
            if not fallback_up:
                raise RuntimeError("fallback unavailable")
            return Resp("fallback-scene")

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=Client))


def _assert_fallback_provenance(data):
    prov = data["_provenance"]
    assert prov["role"] == "fallback"
    assert prov["endpoint"] == FALLBACK
    assert prov["primary_endpoint"] == PRIMARY
    assert prov["attempts"] == [
        {"endpoint": PRIMARY, "role": "primary", "ok": False},
        {"endpoint": FALLBACK, "role": "fallback", "ok": True},
    ]
    assert prov["complete"] is True
    assert data["_source"] == "fallback"
    assert data["_fallback_url"] == FALLBACK
    assert data["_warning"]


def test_fallback_provenance_survives_fresh_cache_hit(monkeypatch):
    _fake_httpx(monkeypatch, primary_up=False)

    async def scenario():
        client = ResilientStacClient(PRIMARY, max_retries=1, fallback_urls=[FALLBACK])
        first = await client.search(PAYLOAD)
        cached = await client.search(PAYLOAD)
        assert first["_cache"] == "miss"
        assert cached["_cache"] == "fresh"
        _assert_fallback_provenance(first)
        # قبل الإصلاح: نتيجة الـcache تفقد _source/_fallback_url/_warning.
        _assert_fallback_provenance(cached)

    asyncio.run(scenario())


def test_fallback_provenance_survives_stale_if_error(monkeypatch):
    _fake_httpx(monkeypatch, primary_up=False)

    async def scenario():
        client = ResilientStacClient(PRIMARY, max_retries=1, fallback_urls=[FALLBACK])
        await client.search(PAYLOAD)
        _fake_httpx(monkeypatch, primary_up=False, fallback_up=False)
        client.cache_ttl = -1  # كلّ مُدخَل منتهٍ ⇒ مسار stale-if-error
        stale = await client.search(PAYLOAD)
        assert stale["_cache"] == "stale"
        assert stale["_provenance"]["role"] == "fallback"
        assert stale["_provenance"]["endpoint"] == FALLBACK
        assert stale["_source"] == "fallback"
        assert stale["features"][0]["id"] == "fallback-scene"

    asyncio.run(scenario())


def test_primary_provenance_is_identical_on_miss_and_fresh(monkeypatch):
    _fake_httpx(monkeypatch, primary_up=True)

    async def scenario():
        client = ResilientStacClient(PRIMARY, max_retries=1, fallback_urls=[FALLBACK])
        first = await client.search(PAYLOAD)
        cached = await client.search(PAYLOAD)
        for data in (first, cached):
            assert data["_provenance"]["role"] == "primary"
            assert data["_provenance"]["endpoint"] == PRIMARY
            assert data["_source"] == "primary"
            assert "_fallback_url" not in data
        assert first["_provenance"] == cached["_provenance"]

    asyncio.run(scenario())


def test_incomplete_page_is_recorded_in_provenance(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [], "links": [{"rel": "next", "href": "https://x/next"}]}

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, **kw):
            return Resp()

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=Client))

    async def scenario():
        client = ResilientStacClient(PRIMARY, max_retries=1)
        data = await client.search(PAYLOAD)
        assert data["_provenance"]["complete"] is False

    asyncio.run(scenario())


def test_cache_key_includes_provider_configuration():
    a = ResilientStacClient(PRIMARY, fallback_urls=[FALLBACK])
    b = ResilientStacClient("https://other-catalog.invalid/v1", fallback_urls=[FALLBACK])
    c = ResilientStacClient(PRIMARY)
    a2 = ResilientStacClient(PRIMARY + "/", fallback_urls=[FALLBACK])
    # Redis مشترك عبر النسخ: إعداد مزوّد مختلف لا يجوز أن يقرأ نتيجة مزوّد آخر.
    assert a._key(PAYLOAD) != b._key(PAYLOAD)
    assert a._key(PAYLOAD) != c._key(PAYLOAD)
    assert a._key(PAYLOAD) == a2._key(PAYLOAD)


def test_element84_adapter_does_not_claim_element84_on_fallback(monkeypatch):
    _fake_httpx(monkeypatch, primary_up=False)
    client = ResilientStacClient(PRIMARY, max_retries=1, fallback_urls=[FALLBACK])
    monkeypatch.setattr(stac_search, "_stac", client)

    async def scenario():
        out = []
        for _ in range(2):  # miss ثمّ fresh من الـcache
            out.append(
                await stac_search.stac_search_element84(
                    [44, 15, 45, 16], "2026-06-01", "2026-07-01", 20, 5
                )
            )
        return out

    for result in asyncio.run(scenario()):
        assert result["source"] != "element84-earth-search"
        assert result["provenance"]["role"] == "fallback"
        assert result["provenance"]["endpoint"] == FALLBACK
        assert result["warning"]
        assert result["items"], "fallback scenes must still be returned"
        for item in result["items"]:
            assert item["provider"] != "element84"
            assert item["provider"] == "planetary-computer"


def test_element84_adapter_keeps_element84_identity_on_primary(monkeypatch):
    _fake_httpx(monkeypatch, primary_up=True)
    client = ResilientStacClient(PRIMARY, max_retries=1, fallback_urls=[FALLBACK])
    monkeypatch.setattr(stac_search, "_stac", client)
    result = asyncio.run(
        stac_search.stac_search_element84([44, 15, 45, 16], "2026-06-01", "2026-07-01", 20, 5)
    )
    assert result["source"] == "element84-earth-search"
    assert result["provenance"]["role"] == "primary"
    assert [i["provider"] for i in result["items"]] == ["element84"]


def test_landsat_and_dem_adapters_report_fallback_source(monkeypatch):
    _fake_httpx(monkeypatch, primary_up=False)
    client = ResilientStacClient(PRIMARY, max_retries=1, fallback_urls=[FALLBACK])
    monkeypatch.setattr(stac_search, "_stac", client)

    async def scenario():
        landsat = await stac_search.stac_search_landsat_unique(
            [44, 15, 45, 16], "2026-06-01", "2026-07-01", 20, 5
        )
        dem = await stac_search.stac_search_dem([44, 15, 45, 16])
        return landsat, dem

    for result in asyncio.run(scenario()):
        assert result["source"] != "element84-earth-search"
        assert result["provenance"]["role"] == "fallback"
