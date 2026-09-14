"""اختبار إغلاق C4/M1: علم push الموبايل (default off) + سجلّ احتياطيّ دائم.

يقفل: `push_decision` (نقيّة) تختار send/record_only/skip بصدق؛ `mobile_push_enabled`
معطَّل افتراضيّاً؛ `_record_push_fallback` يُدِيم إيصالاً عند توفّر tenant_id ويرفض
الحدث عند غيابه؛ لا إقرار قبل دوام السجلّ. لا NATS/شبكة — وكيل مستورَد + pool وهميّ.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
AGENT_DIR = os.path.join(ROOT, "agents", "notification")


@pytest.fixture(scope="module")
def agent_mod():
    for dep in ("fastapi", "nats", "asyncpg", "httpx", "prometheus_client"):
        pytest.importorskip(dep)
    if AGENT_DIR not in sys.path:
        sys.path.insert(0, AGENT_DIR)
    import agent as a

    return a


# ── push_decision (دالّة نقيّة) ──────────────────────────────────
def test_decision_skip_when_no_pref_or_token(agent_mod):
    d = agent_mod.push_decision
    assert d(flag_on=True, push_enabled=False, has_token=True, fcm_active=True) == "skip"
    assert d(flag_on=True, push_enabled=True, has_token=False, fcm_active=True) == "skip"


def test_decision_send_when_flag_and_fcm(agent_mod):
    d = agent_mod.push_decision
    assert d(flag_on=True, push_enabled=True, has_token=True, fcm_active=True) == "send"


def test_decision_record_only_when_flag_off_or_fcm_dormant(agent_mod):
    d = agent_mod.push_decision
    # رغبة المستخدم قائمة لكن العلم off ⇒ سجلّ احتياطيّ (لا إسقاط صامت)
    assert d(flag_on=False, push_enabled=True, has_token=True, fcm_active=True) == "record_only"
    # العلم on لكن FCM خامل ⇒ سجلّ احتياطيّ
    assert d(flag_on=True, push_enabled=True, has_token=True, fcm_active=False) == "record_only"
    assert d(flag_on=False, push_enabled=True, has_token=True, fcm_active=False) == "record_only"


# ── mobile_push_enabled (default off) ───────────────────────────
def test_mobile_push_disabled_by_default(agent_mod, monkeypatch):
    monkeypatch.delenv("FEATURE_MOBILE_PUSH", raising=False)
    assert agent_mod.mobile_push_enabled() is False


def test_mobile_push_enabled_on_truthy(agent_mod, monkeypatch):
    for val in ("1", "true", "on", "yes"):
        monkeypatch.setenv("FEATURE_MOBILE_PUSH", val)
        assert agent_mod.mobile_push_enabled() is True
    for val in ("", "0", "false", "off"):
        monkeypatch.setenv("FEATURE_MOBILE_PUSH", val)
        assert agent_mod.mobile_push_enabled() is False


# ── _record_push_fallback (سجلّ احتياطيّ دائم) ─────────────
class _FakeConn:
    def __init__(self, sink):
        self._sink = sink

    async def execute(self, sql, *args):
        self._sink.append((sql, args))

    def transaction(self):
        return self

    async def fetchval(self, sql, *args):
        return "queued"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, sink):
        self._sink = sink

    def acquire(self):
        return _FakeConn(self._sink)


@pytest.mark.asyncio
async def test_fallback_records_when_tenant_present(agent_mod, monkeypatch):
    """tenant_id موجود ⇒ INSERT في notification_delivery (channel='push', status='queued')."""
    sink: list = []

    async def _fake_pool():
        return _FakePool(sink)

    monkeypatch.setattr(agent_mod, "get_pool", _fake_pool)
    data = {
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "irrigation_rec",
        "user_id": 7,
    }
    await agent_mod._record_push_fallback(data, reason="mobile_push_disabled_or_fcm_dormant")
    assert len(sink) == 2
    context_sql, context_args = sink[0]
    assert "set_config" in context_sql
    assert context_args == (data["tenant_id"], "7")
    sql, args = sink[1]
    assert "notification_delivery" in sql and "'queued'" in sql
    assert args[0] == data["tenant_id"]
    assert args[1] == agent_mod._delivery_key(data)
    assert args[2:] == ("push", "mobile_push_disabled_or_fcm_dormant")


@pytest.mark.asyncio
async def test_fallback_rejects_when_no_tenant(agent_mod, monkeypatch):
    """غياب tenant_id ⇒ رفض صريح قبل دوام السجلّ وإقرار الرسالة."""
    sink: list = []

    async def _fake_pool():
        return _FakePool(sink)

    monkeypatch.setattr(agent_mod, "get_pool", _fake_pool)
    with pytest.raises(agent_mod.InvalidNotification):
        await agent_mod._record_push_fallback({"event_type": "x"}, reason="r")
    assert sink == []
