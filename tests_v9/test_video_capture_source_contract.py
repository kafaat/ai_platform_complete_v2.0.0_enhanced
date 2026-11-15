import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.unit


@pytest.fixture
def main(monkeypatch):
    from tests_v9.service_module import load_service_main

    monkeypatch.syspath_prepend(str(ROOT / "services/video-processor"))
    # Other modules (test_roadmap_phase23) leave an httpx stub in sys.modules; the service
    # must import the real client these tests mock with MockTransport.
    monkeypatch.setitem(sys.modules, "httpx", httpx)
    for name in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    module = load_service_main(
        str(ROOT / "services/video-processor"), required_attrs=("process_stream_loop",)
    )
    yield module
    for name in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
        sys.modules.pop(name, None)


@pytest.mark.parametrize(
    "usb,http,expected",
    [
        (0, None, 0),
        (2, None, 2),
        (None, "https://camera.invalid/live", "https://camera.invalid/live"),
    ],
)
def test_capture_preserves_device_index(main, monkeypatch, usb, http, expected):
    seen = []

    async def capture(source):
        seen.append(source)
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "async_capture", capture)
    state = main.StreamState(main.StreamConfig(stream_id="test", usb_index=usb, http_url=http))
    monkeypatch.setattr(main, "STREAMS", {"test": state})
    asyncio.run(main.process_stream_loop("test"))
    assert seen == [expected]


@pytest.mark.parametrize(
    "code,expected",
    [(-1, "rtsp://camera.invalid/live"), (0, "http://zlm.invalid/live/test.live.flv")],
)
def test_proxy_application_result(main, monkeypatch, code, expected):
    seen = []

    async def capture(source):
        seen.append(source)
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "async_capture", capture)
    monkeypatch.setattr(main, "ZLMEDIA_API_URL", "http://zlm.invalid")
    original = httpx.AsyncClient

    class MockClient(original):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(
                lambda req: httpx.Response(200, json={"code": code, "msg": "test"})
            )
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    state = main.StreamState(
        main.StreamConfig(stream_id="test", rtsp_url="rtsp://camera.invalid/live")
    )
    monkeypatch.setattr(main, "STREAMS", {"test": state})
    asyncio.run(main.process_stream_loop("test"))
    assert seen == [expected]


# ── VIDEO-02: HTTP 200 مع code ≠ 0 رفضٌ في كلّ العميل لا نجاح ─────────────────
class _Resp:
    def __init__(self, payload, status_code=200, content_type=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": content_type} if content_type else {}
        self.content = content
        self.text = "body"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _zlm(main, resp):
    import zlmedia_client

    return zlmedia_client.ZLMediaKitClient(
        base_url="http://zlm.invalid", secret="s", request_fn=lambda url, params: resp
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.start_record("s1"),
        lambda c: c.stop_record("s1"),
        lambda c: c.add_stream_proxy("s1", "rtsp://camera.invalid/live"),
        lambda c: c.del_stream_proxy("__defaultVhost__/live/s1"),
        lambda c: c.get_media_list(),
    ],
)
@pytest.mark.parametrize("code", [-1, -100, -300, True])
def test_client_http_200_with_nonzero_code_is_failure(main, call, code):
    out = call(_zlm(main, _Resp({"code": code, "msg": "can not find the stream"})))
    assert out["ok"] is False
    assert out["code"] == code
    assert out["error"] == "zlmediakit_rejected"


def test_client_http_200_non_json_is_failure(main):
    out = _zlm(main, _Resp(ValueError("html"))).start_record("s1")
    assert out["ok"] is False and out["code"] is None


def test_client_code_zero_is_success(main):
    out = _zlm(main, _Resp({"code": 0, "result": True})).start_record("s1")
    assert out["ok"] is True and out["code"] == 0 and "error" not in out


def test_client_snapshot_json_rejection_is_failure(main):
    resp = _Resp({"code": -100, "msg": "secret wrong"}, content_type="application/json")
    out = _zlm(main, resp).snapshot("s1")
    assert out["ok"] is False and out["code"] == -100 and out["content"] == b""


@pytest.mark.parametrize("route", ["record_start", "record_stop"])
def test_record_rejection_emits_no_recording_event(main, monkeypatch, route):
    import routers.streams as streams

    events = []

    async def emit(event):
        events.append(event["kind"] if isinstance(event, dict) and "kind" in event else event)

    monkeypatch.setattr(streams, "emit_stream_event", emit)
    monkeypatch.setattr(streams, "_client", lambda: _zlm(main, _Resp({"code": -1, "msg": "x"})))
    streams.registry.register(
        stream_id="rec1", tenant_id="t1", source_url="usb:0", created_at="2026-11-11T00:00:00Z"
    )
    try:
        body = asyncio.run(getattr(streams, route)("rec1", user={"tenant_id": "t1"}))
    finally:
        streams.registry.remove("rec1")
    assert body["ok"] is False and body["state"] == "error"
    assert not any("recording." in str(e) for e in events), events


@pytest.mark.parametrize(
    "status,payload,ok",
    [(200, {"code": 0}, True), (200, {"code": -100}, False), (401, {"code": 0}, False)],
)
def test_readyz_requires_code_zero(main, monkeypatch, status, payload, ok):
    original = httpx.AsyncClient

    def handler(req):
        if "zlm.invalid" in str(req.url):
            return httpx.Response(status, json=payload)
        return httpx.Response(200, json={})

    class MockClient(original):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr(main, "ZLMEDIA_API_URL", "http://zlm.invalid")
    deps = asyncio.run(main.check_video_dependencies())
    assert deps["zlmediakit"]["ok"] is ok


# ── إعادة تشغيل المعرّف نفسه: الوكيل يُزال عند الإيقاف، و«already exists» لا يُعاد استخدامه
#    كما هو (قد يسحب مصدراً آخر) بل يُزال ويُعاد إنشاؤه بعنوان هذا البثّ ──
def _run_loop_with_proxy_reply(main, monkeypatch, payload, *, replies=None):
    seen, calls = [], []

    async def capture(source):
        seen.append(source)
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "async_capture", capture)
    monkeypatch.setattr(main, "ZLMEDIA_API_URL", "http://zlm.invalid")
    original = httpx.AsyncClient
    queue = list(replies) if replies is not None else None

    def handler(req):
        calls.append((req.url.path, json.loads(req.content or b"{}")))
        if queue is not None:
            return httpx.Response(200, json=queue.pop(0))
        return httpx.Response(200, json=payload)

    class MockClient(original):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    state = main.StreamState(
        main.StreamConfig(stream_id="test", rtsp_url="rtsp://camera.invalid/live")
    )
    monkeypatch.setattr(main, "STREAMS", {"test": state})
    asyncio.run(main.process_stream_loop("test"))
    return seen, state, calls


_EXISTS = {"code": -1, "msg": "This stream already exists"}


def test_orphan_proxy_is_replaced_with_this_streams_source(main, monkeypatch):
    seen, state, calls = _run_loop_with_proxy_reply(
        main,
        monkeypatch,
        None,
        replies=[_EXISTS, {"code": 0}, {"code": 0, "data": {"key": "__defaultVhost__/live/test"}}],
    )
    paths = [c[0] for c in calls]
    assert paths == [
        "/index/api/addStreamProxy",
        "/index/api/delStreamProxy",
        "/index/api/addStreamProxy",
    ]
    assert calls[1][1]["key"] == "__defaultVhost__/live/test"
    # The re-created proxy pulls THIS stream's camera, never the orphan's source.
    assert calls[2][1]["url"] == "rtsp://camera.invalid/live"
    assert seen == ["http://zlm.invalid/live/test.live.flv"]
    assert state.zlm_proxy_key == "__defaultVhost__/live/test"


def test_existing_proxy_is_not_reused_when_it_cannot_be_replaced(main, monkeypatch):
    seen, state, calls = _run_loop_with_proxy_reply(
        main, monkeypatch, None, replies=[_EXISTS, {"code": -1, "msg": "no such proxy"}]
    )
    assert [c[0] for c in calls] == ["/index/api/addStreamProxy", "/index/api/delStreamProxy"]
    assert seen == ["rtsp://camera.invalid/live"]
    assert state.zlm_proxy_key is None


def test_existing_proxy_that_reappears_is_not_reused(main, monkeypatch):
    seen, state, _calls = _run_loop_with_proxy_reply(
        main, monkeypatch, None, replies=[_EXISTS, {"code": 0}, _EXISTS]
    )
    assert seen == ["rtsp://camera.invalid/live"]
    assert state.zlm_proxy_key is None


def test_created_proxy_key_is_recorded(main, monkeypatch):
    _seen, state, _calls = _run_loop_with_proxy_reply(
        main, monkeypatch, {"code": 0, "data": {"key": "__defaultVhost__/live/test"}}
    )
    assert state.zlm_proxy_key == "__defaultVhost__/live/test"


def test_stop_stream_deletes_the_zlmediakit_proxy(main, monkeypatch):
    import routers.streams as streams

    deleted = []

    class FakeClient:
        def del_stream_proxy(self, key):
            deleted.append(key)
            return {"ok": True}

    async def emit(event):
        return None

    monkeypatch.setattr(streams, "_client", FakeClient)
    monkeypatch.setattr(streams, "emit_stream_event", emit)
    state = main.StreamState(
        main.StreamConfig(stream_id="p1", rtsp_url="rtsp://camera.invalid/live", tenant_id="t1")
    )
    state.zlm_proxy_key = "__defaultVhost__/live/p1"
    monkeypatch.setattr(main, "STREAMS", {"p1": state})
    asyncio.run(streams.stop_stream("p1", user={"tenant_id": "t1"}))
    assert deleted == ["__defaultVhost__/live/p1"]


# ── usb_index محصور في فهرس جهازٍ صرف (لا اختيار خلفيّة OpenCV ولا «أيّ كاميرا») ──
@pytest.mark.parametrize("value", [-1, 64, 100, 200, 1900])
def test_usb_index_outside_device_range_rejected(main, value):
    from pydantic import ValidationError

    for model in (main.CreateStreamRequest, main.StreamConfig):
        with pytest.raises(ValidationError):
            model(stream_id="u", usb_index=value)


@pytest.mark.parametrize("value", [0, 63])
def test_usb_index_device_range_accepted(main, value):
    assert main.CreateStreamRequest(usb_index=value).usb_index == value


def test_create_stream_out_of_range_usb_index_is_422(main):
    from fastapi.testclient import TestClient

    main.app.dependency_overrides[main._get_current_user] = lambda: {"tenant_id": "t1"}
    try:
        response = TestClient(main.app).post("/v1/streams", json={"usb_index": 100})
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 422, response.text
    assert not main.STREAMS
