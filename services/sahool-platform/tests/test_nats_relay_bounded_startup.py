"""R2: غياب NATS لا يُعلِّق إقلاع المنصّة حين FEATURE_NATS_PUBLISHERS=true.

``nats.connect(max_reconnect_attempts=-1)`` يُكرِّر الاتّصال الأوّل بلا حدّ (لا يرفع أبداً)،
و``_lifespan`` ينتظر ``_start_outbox_worker`` ⇒ المنصّة لا تخدم. هنا يُحاكى ذلك باتّصالٍ
لا يعود أبداً، ويُشترَط: إقلاعٌ يكتمل خلال ثوانٍ، حالةٌ متدهورة مُعلَنة على ``/readyz``،
وإعادةُ محاولةٍ خلفيّة تبدأ الناشر حين يظهر الوسيط.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


class _FakeNats:
    is_connected = True

    def __init__(self):
        self.closed = False

    def jetstream(self):
        return object()

    async def drain(self):
        self.closed = True

    async def close(self):
        self.closed = True


class _FakeWorker:
    def __init__(self, pool, publish):
        self._stop = asyncio.Event()

    async def run(self):
        await self._stop.wait()

    def stop(self):
        self._stop.set()


@pytest.fixture
def relay_env(monkeypatch):
    import api.event_bus as event_bus
    import api.main as main

    import nats

    monkeypatch.setenv("FEATURE_NATS_PUBLISHERS", "true")
    monkeypatch.setenv("NATS_INITIAL_CONNECT_TIMEOUT_SECONDS", "0.2")
    monkeypatch.setenv("NATS_CONNECT_RETRY_SECONDS", "0.05")
    monkeypatch.setattr(main, "_DB_POOL", object())
    monkeypatch.setattr(main, "_JOBS_POOL", None)
    monkeypatch.setattr(event_bus, "OutboxWorker", _FakeWorker)

    calls: list[dict] = []
    behaviour = {"reachable": False}

    async def _connect(url, **kwargs):
        calls.append(kwargs)
        if not behaviour["reachable"]:
            await asyncio.Event().wait()  # nats-py مع -1: حلقة لا تنتهي ولا ترفع
        return _FakeNats()

    monkeypatch.setattr(nats, "connect", _connect)
    return main, calls, behaviour


async def test_startup_completes_when_nats_is_unreachable(relay_env):
    main, calls, _ = relay_env
    from shared.broker_url import NATS_RELAY

    try:
        await asyncio.wait_for(main._start_outbox_worker(), timeout=3)
        assert NATS_RELAY.status == "degraded"
        assert main._OUTBOX_WORKER is None and main._NATS_CONN is None
        assert NATS_RELAY.retry_task is not None and not NATS_RELAY.retry_task.done()
    finally:
        await main._stop_outbox_worker()
    assert NATS_RELAY.retry_task is None and NATS_RELAY.status == "disabled"


async def test_background_retry_starts_the_relay_once_nats_appears(relay_env):
    main, calls, behaviour = relay_env
    from shared.broker_url import NATS_RELAY

    try:
        await asyncio.wait_for(main._start_outbox_worker(), timeout=3)
        assert NATS_RELAY.status == "degraded"
        behaviour["reachable"] = True
        await asyncio.wait_for(NATS_RELAY.retry_task, timeout=3)
        assert NATS_RELAY.status == "up"
        assert isinstance(main._OUTBOX_WORKER, _FakeWorker)
        assert main._NATS_CONN is NATS_RELAY.conn
    finally:
        await main._stop_outbox_worker()
    # إعادة الاتّصال الأبديّة تبقى سلوك العميل بعد أوّل اتّصال ناجح، وصندوق الردّ محفوظ.
    assert all(c["max_reconnect_attempts"] == -1 for c in calls)
    assert all(c["inbox_prefix"] == "_INBOX_sahool-platform" for c in calls)


async def test_reachable_nats_starts_relay_immediately(relay_env):
    main, _, behaviour = relay_env
    from shared.broker_url import NATS_RELAY

    behaviour["reachable"] = True
    try:
        await asyncio.wait_for(main._start_outbox_worker(), timeout=3)
        assert NATS_RELAY.status == "up" and NATS_RELAY.retry_task is None
        assert isinstance(main._OUTBOX_WORKER, _FakeWorker)
    finally:
        await main._stop_outbox_worker()


def test_readyz_reports_nats_relay_state(monkeypatch):
    from api import main
    from fastapi.testclient import TestClient

    from shared.broker_url import NATS_RELAY

    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.setattr(main, "_DB_POOL", None)
    monkeypatch.setattr(NATS_RELAY, "phase", "degraded")
    response = TestClient(main.app).get("/readyz")
    # الوسيط الغائب لا يُخرج المنصّة من الخدمة (الأحداث دائمة في outbox) — يُعلَن فقط.
    assert response.status_code == 200
    assert response.json()["nats"] == "degraded"
