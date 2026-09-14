"""Notification boundary regressions: identity, retry, receipts and readiness."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def agent():
    spec = importlib.util.spec_from_file_location(
        "notification_under_test", ROOT / "agents/notification/agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def keys(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    monkeypatch.setenv("JWT_PUBLIC_KEY", public)
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    return private


def claims(**overrides):
    return {
        "sub": "7",
        "tenant_id": TENANT,
        "iss": "sahool-auth",
        "aud": "sahool",
        "exp": int(time.time()) + 60,
        **overrides,
    }


def test_rs256_auth_token_accepted_in_production(agent, keys):
    assert agent._validate_ws_token(jwt.encode(claims(), keys, algorithm="RS256"))["sub"] == "7"


@pytest.mark.parametrize(
    "override", [{"iss": "other"}, {"aud": "other"}, {"exp": 1}, {"tenant_id": ""}]
)
def test_wrong_token_identity_rejected(agent, keys, override):
    with pytest.raises(ValueError):
        agent._validate_ws_token(jwt.encode(claims(**override), keys, algorithm="RS256"))


def test_hs256_never_falls_back_when_rsa_configured(agent, keys, monkeypatch):
    secret = "a-synthetic-development-secret-32-characters"
    monkeypatch.setenv("JWT_SECRET", secret)
    with pytest.raises(ValueError):
        agent._validate_ws_token(jwt.encode(claims(), secret, algorithm="HS256"))


def test_hs256_requires_explicit_production_migration(agent, monkeypatch):
    secret = "a-synthetic-development-secret-32-characters"
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "production")
    token = jwt.encode(claims(), secret, algorithm="HS256")
    with pytest.raises(ValueError, match="RS256"):
        agent._validate_ws_token(token)
    monkeypatch.setenv("SAHOOL_ALLOW_HS256_IN_PROD", "1")
    assert agent._validate_ws_token(token)["tenant_id"] == TENANT


@pytest.mark.asyncio
async def test_tenantless_and_wrong_tenant_user_events_do_not_escape(agent):
    ws = SimpleNamespace(send_json=AsyncMock())

    # A hashable websocket adapter, as real WebSocket objects are.
    class Socket:
        send_json = ws.send_json

    socket = Socket()
    await agent.manager.connect("7", socket, TENANT)
    with pytest.raises(agent.InvalidNotification):
        await agent.dispatch({"event_type": "field.created"})
    await agent.manager.send_to_user("7", {"tenant_id": "other"})
    assert not await agent.manager.connect("7", Socket(), "other")
    ws.send_json.assert_not_awaited()
    await agent.manager.send_to_user("7", {"tenant_id": TENANT})
    ws.send_json.assert_awaited_once()


def message(payload, attempts=1):
    return SimpleNamespace(
        data=json.dumps(payload).encode(),
        subject="sahool.task.assigned",
        metadata=SimpleNamespace(
            stream="sahool", sequence=SimpleNamespace(stream=123), num_delivered=attempts
        ),
        ack=AsyncMock(),
        nak=AsyncMock(),
        term=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_exception_naks_and_success_acks(agent, monkeypatch):
    msg = message({"tenant_id": TENANT})
    dispatch = AsyncMock(side_effect=RuntimeError("outage"))
    monkeypatch.setattr(agent, "dispatch", dispatch)
    await agent.handle_msg(msg)
    msg.ack.assert_not_awaited()
    msg.nak.assert_awaited_once()
    dispatch.side_effect = None
    await agent.handle_msg(msg)
    msg.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_poison_message_retained_before_termination(agent, monkeypatch):
    msg = message({"event_type": "field.created"})
    js = SimpleNamespace(publish=AsyncMock())
    monkeypatch.setattr(agent, "_js", js)
    await agent.handle_msg(msg)
    assert js.publish.call_args.args[0] == "sahool.notification.dead_letter"
    msg.term.assert_awaited_once()
    msg.ack.assert_not_awaited()
    js.publish.side_effect = RuntimeError("broker unavailable")
    msg.term.reset_mock()
    await agent.handle_msg(msg)
    msg.term.assert_not_awaited()
    msg.nak.assert_awaited_once()


class Connection:
    def __init__(self):
        self.statuses = {}
        self.contexts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def transaction(self):
        return self

    async def execute(self, sql, *args):
        if sql.startswith("SELECT set_config"):
            self.contexts.append(args)
        elif sql.startswith("INSERT"):
            self.statuses.setdefault(args[:3], "queued")
        elif sql.startswith("UPDATE"):
            self.statuses[args[:3]] = args[3]

    async def fetchval(self, sql, *args):
        return self.statuses.get(args)


@pytest.mark.asyncio
async def test_partial_channel_failure_retries_only_failed_receipt(agent, monkeypatch):
    conn = Connection()
    monkeypatch.setattr(
        agent, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: conn))
    )
    data = {"tenant_id": TENANT, "user_id": 7, "event_id": "event-1"}
    email, push = AsyncMock(return_value=True), AsyncMock(return_value=False)
    await agent._deliver_channel(data, "email", email)
    with pytest.raises(agent.DeliveryUnavailable):
        await agent._deliver_channel(data, "push", push)
    push.return_value = True
    await agent._deliver_channel(data, "email", email)
    await agent._deliver_channel(data, "push", push)
    email.assert_awaited_once()
    assert push.await_count == 2
    assert set(conn.statuses.values()) == {"sent"}
    assert all(context == (TENANT, "7") for context in conn.contexts)


@pytest.mark.asyncio
async def test_no_database_cannot_claim_record_or_provider_success(agent, monkeypatch):
    monkeypatch.setattr(agent, "get_pool", AsyncMock(return_value=None))
    sender = AsyncMock(return_value=True)
    with pytest.raises(agent.DeliveryUnavailable):
        await agent._deliver_channel({"tenant_id": TENANT}, "push", sender)
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_subscriptions_not_ready_and_can_recover(agent, monkeypatch):
    js = SimpleNamespace(
        stream_info=AsyncMock(),
        subscribe=AsyncMock(side_effect=RuntimeError("unavailable")),
        consumer_info=AsyncMock(),
    )
    monkeypatch.setattr(agent, "_js", js)
    monkeypatch.setattr(agent, "_nc", SimpleNamespace(is_connected=True))
    await agent._ensure_subscriptions()
    with pytest.raises(agent.HTTPException) as exc:
        await agent.readyz()
    assert exc.value.status_code == 503
    assert len(exc.value.detail["missing"]) == len(agent.SUBSCRIPTIONS)
    js.subscribe.side_effect = None
    await agent._ensure_subscriptions()
    assert len(agent._subscriptions) == len(agent.SUBSCRIPTIONS)
    assert all(call.kwargs["manual_ack"] is True for call in js.subscribe.call_args_list)


@pytest.mark.asyncio
async def test_preferences_query_binds_tenant_and_user(agent, monkeypatch):
    conn = Connection()
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(
        agent, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: conn))
    )
    # الموضوع نصّيّ (UUID في المنصّة) ويُقرأ بـuser_ref كما تكتبه واجهة التفضيلات — لا
    # تحويل إلى int ولا عمود user_id القديم (Copilot على #997).
    subject = "8d3f2c1a-5b4e-4f6a-9c7d-2e1f0a9b8c7d"
    assert await agent.get_prefs(subject, TENANT) is None
    sql = conn.fetchrow.call_args.args[0]
    assert "user_ref=$2" in sql and "user_id=" not in sql
    assert conn.fetchrow.call_args.args[1:] == (TENANT, subject)
    assert conn.contexts == [(TENANT, subject)]


@pytest.mark.asyncio
async def test_one_failing_channel_does_not_block_the_healthy_ones(agent, monkeypatch):
    """C01 (unified forensic report v2): email failing must not prevent Telegram/Push.

    Before: the first failed channel raised out of ``dispatch`` and the healthy channels
    were never attempted; the whole event was redelivered until dead-lettered. Now every
    planned channel is attempted, the failures are raised together afterwards (so
    JetStream redelivers), and the receipts already ``sent`` are skipped on retry.
    """
    conn = Connection()
    monkeypatch.setattr(
        agent, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=lambda: conn))
    )
    monkeypatch.setattr(agent.manager, "send_to_user", AsyncMock())
    monkeypatch.setattr(
        agent,
        "get_prefs",
        AsyncMock(
            return_value={
                "event_types": ["task.assigned"],
                "email_enabled": True,
                "email_address": "farmer@example.test",
                "telegram_enabled": True,
                "telegram_chat_id": "42",
                "push_enabled": False,
            }
        ),
    )
    email = AsyncMock(return_value=False)
    telegram = AsyncMock(return_value=True)
    monkeypatch.setattr(agent, "send_email_async", email)
    monkeypatch.setattr(agent, "send_telegram", telegram)
    data = {"tenant_id": TENANT, "user_id": "7", "event_type": "task.assigned", "event_id": "e-1"}

    # Attempt 1: email fails, Telegram still delivered; the failure is reported afterwards.
    with pytest.raises(agent.DeliveryUnavailable, match="channels_failed:email"):
        await agent.dispatch(dict(data))
    telegram.assert_awaited_once()
    assert conn.statuses[(TENANT, agent._delivery_key(data), "email")] == "failed"
    assert conn.statuses[(TENANT, agent._delivery_key(data), "telegram")] == "sent"

    # Attempt 2 (redelivery, email still down): Telegram is NOT resent.
    with pytest.raises(agent.DeliveryUnavailable, match="channels_failed:email"):
        await agent.dispatch(dict(data))
    telegram.assert_awaited_once()
    assert email.await_count == 2

    # Attempt 3 (provider recovered): the event settles with every receipt sent.
    email.return_value = True
    await agent.dispatch(dict(data))
    telegram.assert_awaited_once()
    assert email.await_count == 3
    assert set(conn.statuses.values()) == {"sent"}
