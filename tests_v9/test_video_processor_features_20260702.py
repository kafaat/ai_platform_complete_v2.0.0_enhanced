"""اختبارات وحدة لميزات video-processor الجديدة (2026-07-02).

يغطّي الوحدات الخالية من fastapi (السجلّ/العميل/باني الأحداث) + نقاط النهاية:
  • StreamRegistry: عزل المستأجرين، انتقالات الحالة، الإزالة.
  • ZLMediaKitClient: (httpx محقون) رابط/مُعامِلات لقطة/تسجيل + حقن secret + فشل ليّن.
  • build_stream_event: الشكل القانونيّ لكلّ نوع.
  • نقاط النهاية (importorskip fastapi): لقطة 404 لبثّ مجهول؛ بدء/إيقاف تسجيل يحدّث السجلّ.

منطق صرف ⇒ لا خدمات حيّة (marker: unit). العميل/النشر محقونان فلا شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO = os.path.join(ROOT, "services", "video-processor")
if VIDEO not in sys.path:
    sys.path.insert(0, VIDEO)

import stream_events as se  # noqa: E402
import stream_registry as sr  # noqa: E402
import zlmedia_client as zc  # noqa: E402


# ══════════════════════════════════════════════════════════════
# StreamRegistry — عزل المستأجرين + انتقالات الحالة + الإزالة
# ══════════════════════════════════════════════════════════════
def _reg_with(*entries):
    reg = sr.StreamRegistry()
    for sid, tid in entries:
        reg.register(
            stream_id=sid,
            tenant_id=tid,
            source_url=f"rtsp://cam/{sid}",
            created_at="2026-07-02T00:00:00+00:00",
        )
    return reg


def test_registry_register_and_get():
    reg = _reg_with(("s1", "tenant_a"))
    e = reg.get("s1")
    assert e is not None
    assert e.stream_id == "s1"
    assert e.tenant_id == "tenant_a"
    assert e.state == "pending"  # الحالة الافتراضيّة
    assert reg.get("missing") is None


def test_registry_list_by_tenant_isolation():
    """list_by_tenant لا يُسرّب أبداً بثوث مستأجِر آخر."""
    reg = _reg_with(("s_a", "tenant_a"), ("s_b", "tenant_b"), ("s_a2", "tenant_a"))
    a_ids = {e.stream_id for e in reg.list_by_tenant("tenant_a")}
    b_ids = {e.stream_id for e in reg.list_by_tenant("tenant_b")}
    assert a_ids == {"s_a", "s_a2"}
    assert b_ids == {"s_b"}
    # fail-closed: مستأجِر فارغ ⇒ لا شيء.
    assert reg.list_by_tenant("") == []


def test_registry_state_transitions():
    reg = _reg_with(("s1", "tenant_a"))
    upd = reg.update_state("s1", "live", last_event="stream.started")
    assert upd.state == "live"
    assert upd.last_event == "stream.started"
    # update_state لبثّ مجهول ⇒ None.
    assert reg.update_state("nope", "live") is None
    # حالة غير قانونيّة ⇒ ValueError.
    with pytest.raises(ValueError):
        reg.update_state("s1", "bogus")
    with pytest.raises(ValueError):
        reg.register(stream_id="x", tenant_id="t", source_url="u", created_at=0, state="bogus")


def test_registry_remove():
    reg = _reg_with(("s1", "tenant_a"))
    assert reg.remove("s1") is True
    assert reg.get("s1") is None
    assert reg.remove("s1") is False  # إزالة ثانية ⇒ False


def test_registry_returns_immutable_copies():
    """القيود مجمّدة — لا يُفسِد المُستدعي حالة السجلّ عبر المرجع العائد."""
    from dataclasses import FrozenInstanceError

    reg = _reg_with(("s1", "tenant_a"))
    e = reg.get("s1")
    with pytest.raises(FrozenInstanceError):
        e.state = "hacked"  # frozen dataclass


# ══════════════════════════════════════════════════════════════
# ZLMediaKitClient — رابط/مُعامِلات + حقن secret + فشل ليّن (httpx محقون)
# ══════════════════════════════════════════════════════════════
class _FakeResp:
    def __init__(self, status_code=200, payload=None, content=b"", content_type=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"code": 0}
        self.content = content
        self.headers = {"content-type": content_type} if content_type else {}
        self.text = "body"

    def json(self):
        return self._payload


def _capturing_client(secret="S3CRET", resp=None, base="http://zlm:8080/"):
    calls = []

    def request_fn(url, params):
        calls.append((url, dict(params)))
        return resp if resp is not None else _FakeResp()

    client = zc.ZLMediaKitClient(base_url=base, secret=secret, request_fn=request_fn)
    return client, calls


def test_client_snapshot_url_and_params():
    resp = _FakeResp(content=b"JPEGDATA", content_type="image/jpeg")
    client, calls = _capturing_client(resp=resp)
    out = client.snapshot("cam1")
    url, params = calls[0]
    assert url == "http://zlm:8080/index/api/getSnap"  # base rstrip('/')
    assert params["secret"] == "S3CRET"  # حقن السرّ
    assert params["url"] == "http://zlm:8080/live/cam1.live.flv"
    assert out["ok"] is True
    assert out["content"] == b"JPEGDATA"
    assert out["content_type"] == "image/jpeg"


def test_client_start_stop_record_params():
    client, calls = _capturing_client()
    client.start_record("cam1")
    url, params = calls[0]
    assert url.endswith("/index/api/startRecord")
    assert params["stream"] == "cam1"
    assert params["app"] == "live"
    assert params["type"] == 1
    assert params["secret"] == "S3CRET"

    client.stop_record("cam1", app="rec")
    url2, params2 = calls[1]
    assert url2.endswith("/index/api/stopRecord")
    assert params2["stream"] == "cam1"
    assert params2["app"] == "rec"
    assert params2["secret"] == "S3CRET"


def test_client_secret_omitted_when_empty():
    client, calls = _capturing_client(secret="")
    client.get_media_list()
    _url, params = calls[0]
    assert "secret" not in params  # لا سرّ ⇒ لا يُحقَن


def test_client_fail_soft_on_error_status():
    """4xx/5xx ⇒ ok=False ولا يرفع."""
    client, _ = _capturing_client(resp=_FakeResp(status_code=502, payload={"code": -1}))
    out = client.start_record("cam1")
    assert out["ok"] is False
    assert out["status_code"] == 502


def test_client_fail_soft_on_exception():
    """خطأ اتصال ⇒ ok=False + error ولا يرفع."""

    def boom(url, params):
        raise RuntimeError("connreset")

    client = zc.ZLMediaKitClient(base_url="http://zlm:8080", secret="x", request_fn=boom)
    out = client.snapshot("cam1")
    assert out["ok"] is False
    assert out["error"] == "RuntimeError"


# ══════════════════════════════════════════════════════════════
# build_stream_event — الشكل القانونيّ لكلّ نوع
# ══════════════════════════════════════════════════════════════
def test_build_stream_event_canonical_shape():
    entry = sr.StreamEntry(
        stream_id="s1",
        tenant_id="tenant_a",
        source_url="rtsp://cam/s1",
        state="live",
        created_at="2026-07-02T00:00:00+00:00",
    )
    for kind in sorted(se.VALID_KINDS):
        ev = se.build_stream_event(kind, entry, ts="2026-07-02T01:00:00+00:00")
        assert set(ev) == {"kind", "stream_id", "tenant_id", "source_url", "state", "ts"}
        assert ev["kind"] == kind
        assert ev["stream_id"] == "s1"
        assert ev["tenant_id"] == "tenant_a"
        assert ev["source_url"] == "rtsp://cam/s1"
        assert ev["ts"] == "2026-07-02T01:00:00+00:00"


def test_build_stream_event_accepts_dict():
    ev = se.build_stream_event(
        "stream.started", {"stream_id": "s9", "tenant_id": "t9", "state": "pending"}
    )
    assert ev["stream_id"] == "s9"
    assert ev["tenant_id"] == "t9"


def test_build_stream_event_rejects_unknown_kind():
    with pytest.raises(ValueError):
        se.build_stream_event("stream.exploded", {"stream_id": "s1"})


def test_event_subject_and_topic():
    assert se.nats_subject("stream.started") == "sahool.video.stream.started"
    assert se.mqtt_topic("recording.stopped") == "sahool/video/recording/stopped"


async def test_emit_stream_event_best_effort_with_injected_publishers():
    """النشر يستدعي الحاقنين بالموضوع + الحمولة، وعطل أحدهما لا يُسقِط الآخر."""
    seen = {}

    async def nats_pub(subject, payload):
        seen["nats"] = (subject, payload)

    def mqtt_pub(topic, payload):  # حاقن متزامن مسموح
        raise RuntimeError("broker down")

    ev = se.build_stream_event("stream.started", {"stream_id": "s1", "tenant_id": "t"})
    res = await se.emit_stream_event(ev, nats_publish=nats_pub, mqtt_publish=mqtt_pub)
    assert res["nats"] == "ok"
    assert res["mqtt"].startswith("skip:")  # best-effort لا يرفع
    assert seen["nats"][0] == "sahool.video.stream.started"
    assert b"stream.started" in seen["nats"][1]


# ══════════════════════════════════════════════════════════════
# نقاط النهاية — لقطة/تسجيل (importorskip fastapi)
# ══════════════════════════════════════════════════════════════
def _auth_headers(tenant_id: str = "tenant_a", role: str = "user") -> dict:
    """رمز JWT اختباريّ حقيقيّ (HS256) يطابق مخطّط conftest — يمرّ عبر
    ``_get_current_user`` فعليّاً (iss=sahool-auth، aud=sahool). نُمرّر رأس Bearer
    بدل تجاوز التبعيّة: راوترات الخدمة تُضمَّن بتمديد مسطّح فلا يُستشار
    ``dependency_overrides`` (dependency_overrides_provider=None)."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from jose import jwt

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "role": role,
            "tenant_id": tenant_id,
            "iss": "sahool-auth",
            "aud": "sahool",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "jti": str(uuid4()),
        },
        os.getenv("JWT_SECRET", "test_secret_min_32_chars_for_sahool_v9"),
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client_ctx(monkeypatch):
    """يستورد main + routers.streams طازجاً، يعطّل النشر (لا شبكة)، ويُرجِع
    (TestClient, streams_module, main). ينظّف حالة السجلّ/STREAMS."""
    pytest.importorskip("fastapi")
    import importlib

    # عطّل ناشري NATS/MQTT الافتراضيّين (لا شبكة في الوحدة).
    monkeypatch.setenv("MQTT_BROKER_URL", "disabled")
    monkeypatch.delenv("NATS_URL", raising=False)

    # اسم 'main'/'routers' عامّ عبر الخدمات (tts/soil/raster…). في التشغيل الكامل قد
    # يتصدّر مسار خدمة أخرى sys.path فيُستورَد main خاطئ. نُجبِر VIDEO إلى المقدّمة
    # ونُسقط المُخبّأ كي يُعاد الاستيراد ضدّ video-processor حصراً (نمط soil #570).
    while VIDEO in sys.path:
        sys.path.remove(VIDEO)
    sys.path.insert(0, VIDEO)
    for _m in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
        sys.modules.pop(_m, None)
    vmain = importlib.import_module("main")
    streams = importlib.import_module("routers.streams")
    assert hasattr(vmain, "STREAMS") and hasattr(vmain, "_assert_stream_tenant"), (
        "استُورد main خاطئ (تصادم أسماء عبر الخدمات) — ليس video-processor"
    )

    from fastapi.testclient import TestClient

    tc = TestClient(vmain.app)
    try:
        yield tc, streams, vmain
    finally:
        vmain.STREAMS.clear()
        for _m in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
            sys.modules.pop(_m, None)


class _FakeZLM:
    def __init__(self, ok=True):
        self._ok = ok

    def snapshot(self, stream_id, **_):
        if self._ok:
            return {"ok": True, "content": b"IMG", "content_type": "image/jpeg"}
        return {"ok": False, "status_code": 500}

    def start_record(self, stream_id, **_):
        return {"ok": self._ok, "status_code": 200 if self._ok else 500}

    def stop_record(self, stream_id, **_):
        return {"ok": self._ok, "status_code": 200 if self._ok else 500}


def _seed_registry(streams, stream_id="cam1", tenant="tenant_a", state="live"):
    streams.registry.register(
        stream_id=stream_id,
        tenant_id=tenant,
        source_url=f"rtsp://cam/{stream_id}",
        created_at="2026-07-02T00:00:00+00:00",
        state=state,
    )


def test_snapshot_404_on_unknown_stream(client_ctx):
    tc, _streams, _vmain = client_ctx
    r = tc.get("/streams/does-not-exist/snapshot", headers=_auth_headers())
    assert r.status_code == 404


def test_snapshot_returns_image(client_ctx, monkeypatch):
    tc, streams, _vmain = client_ctx
    _seed_registry(streams)
    monkeypatch.setattr(streams, "_client", lambda: _FakeZLM(ok=True))
    r = tc.get("/streams/cam1/snapshot", headers=_auth_headers())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content == b"IMG"


def test_record_start_updates_registry(client_ctx, monkeypatch):
    tc, streams, _vmain = client_ctx
    _seed_registry(streams)
    monkeypatch.setattr(streams, "_client", lambda: _FakeZLM(ok=True))
    r = tc.post("/streams/cam1/record/start", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["state"] == "recording"
    assert streams.registry.get("cam1").state == "recording"


def test_record_stop_updates_registry(client_ctx, monkeypatch):
    tc, streams, _vmain = client_ctx
    _seed_registry(streams, state="recording")
    monkeypatch.setattr(streams, "_client", lambda: _FakeZLM(ok=True))
    r = tc.post("/streams/cam1/record/stop", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["state"] == "live"
    assert streams.registry.get("cam1").state == "live"


def test_record_start_client_failure_sets_error(client_ctx, monkeypatch):
    """فشل عميل ZLMediaKit ⇒ الحالة error + ok=False (fail-soft لا يرفع)."""
    tc, streams, _vmain = client_ctx
    _seed_registry(streams)
    monkeypatch.setattr(streams, "_client", lambda: _FakeZLM(ok=False))
    r = tc.post("/streams/cam1/record/start", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["state"] == "error"
    assert streams.registry.get("cam1").state == "error"


def test_record_cross_tenant_denied(client_ctx, monkeypatch):
    """بثّ مملوك لمستأجِر آخر ⇒ 404 (عزل)."""
    tc, streams, _vmain = client_ctx
    _seed_registry(streams, tenant="tenant_other")
    monkeypatch.setattr(streams, "_client", lambda: _FakeZLM(ok=True))
    r = tc.post("/streams/cam1/record/start", headers=_auth_headers("tenant_a"))
    assert r.status_code == 404
