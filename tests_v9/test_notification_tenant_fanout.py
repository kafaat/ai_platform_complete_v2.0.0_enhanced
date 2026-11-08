"""R8 — أحداث المنصّة الحيّة بلا ``user_id`` تصل مشتركي المستأجِر عبر البريد/تيليجرام/push.

كانت ``dispatch`` تعود بعد بثّ WebSocket إن غاب ``user_id`` — وأحداث outbox
(``sahool.events.*``) لا تحمله أبداً، فلم يُرسَل لها بريد ولا تيليجرام ولا push قطّ.
الآن تُحَلّ المستلمون من ``notification_preferences`` لمستأجِر الحدث (سياق RLS مضبوط)،
وتُحترَم تفضيلات كلّ مستخدم، ولا يُضمَّن مستخدمٌ من مستأجِر آخر أبداً.

بلا اتّصال قاعدة وهميّ: الوصلات تُرقَّع كدوالّ (``_fetch_tenant_pref_rows`` ·
``_deliver_channel`` · مُرسِلو القنوات).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def agent(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "notification_fanout_under_test", ROOT / "agents/notification/agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.manager, "broadcast_tenant", AsyncMock())
    monkeypatch.setattr(module.manager, "send_to_user", AsyncMock())
    monkeypatch.setattr(module, "mobile_push_enabled", lambda: True)
    monkeypatch.setattr(module, "fcm_push_active", lambda: True)
    return module


def _prefs(user_ref, tenant=TENANT, events=("weather_alert",), **channels):
    return {
        "tenant_id": tenant,
        "user_ref": user_ref,
        "event_types": list(events),
        "email_enabled": True,
        "email_address": f"{user_ref}@example.test",
        "telegram_enabled": True,
        "telegram_chat_id": f"chat-{user_ref}",
        "push_enabled": True,
        "push_token": f"tok-{user_ref}",
        **channels,
    }


@pytest.fixture
def wired(agent, monkeypatch):
    """يُرقّع الوصلات ويُرجِع سجلّ (المستلم، القناة، الوجهة) لكلّ إرسال فعليّ."""
    sent: list[tuple[str, str, str]] = []
    receipts: list[tuple[str, str, str]] = []

    async def _deliver_channel(data, channel, send=None, reason=None):
        receipts.append((data["tenant_id"], str(data.get("user_id", "")), channel))
        if send is not None and not await send():
            raise agent.DeliveryUnavailable(f"{channel}_delivery_failed")

    def _sender(channel):
        async def _send(target, *_args):
            sent.append((channel, str(target)))
            return True

        return _send

    monkeypatch.setattr(agent, "_deliver_channel", _deliver_channel)
    monkeypatch.setattr(agent, "send_email_async", _sender("email"))
    monkeypatch.setattr(agent, "send_telegram", _sender("telegram"))
    monkeypatch.setattr(agent, "send_push", _sender("push"))
    return sent, receipts


def _live_event(**extra):
    # مظروف OutboxWorker: tenant_id + field، بلا user_id.
    return {
        "event_type": "weather_alert",
        "event_id": "evt-1",
        "tenant_id": TENANT,
        "entity_id": "field_01",
        **extra,
    }


@pytest.mark.asyncio
async def test_event_without_user_id_reaches_subscribed_users_on_every_channel(
    agent, wired, monkeypatch
):
    sent, receipts = wired
    rows = AsyncMock(
        return_value=[
            _prefs("u-a"),
            _prefs("u-b"),
            _prefs("u-muted", events=("pest_alert",)),  # غير مشترك بهذا النوع
            _prefs("u-foreign", tenant=OTHER),  # لو أخفق RLS — يُسقَط
            {**_prefs("legacy"), "user_ref": None},  # صفّ بلا هويّة منصّة
        ]
    )
    monkeypatch.setattr(agent, "_fetch_tenant_pref_rows", rows)

    await agent.dispatch(_live_event())

    rows.assert_awaited_once_with(TENANT)
    assert sorted(sent) == sorted(
        [
            ("email", "u-a@example.test"),
            ("telegram", "chat-u-a"),
            ("push", "tok-u-a"),
            ("email", "u-b@example.test"),
            ("telegram", "chat-u-b"),
            ("push", "tok-u-b"),
        ]
    )
    # إيصالات لكلّ مستلم داخل مستأجِر الحدث فقط.
    assert {(t, u) for t, u, _ in receipts} == {(TENANT, "u-a"), (TENANT, "u-b")}
    assert not any("foreign" in target or "muted" in target for _, target in sent)


@pytest.mark.asyncio
async def test_channel_preferences_are_respected_per_recipient(agent, wired, monkeypatch):
    sent, _ = wired
    monkeypatch.setattr(
        agent,
        "_fetch_tenant_pref_rows",
        AsyncMock(
            return_value=[
                _prefs("u-a", telegram_enabled=False, push_enabled=False),
                _prefs("u-b", email_enabled=False, push_token=None),
            ]
        ),
    )
    await agent.dispatch(_live_event())
    assert sorted(sent) == [("email", "u-a@example.test"), ("telegram", "chat-u-b")]


@pytest.mark.asyncio
async def test_each_recipient_gets_its_own_delivery_receipt_key(agent):
    event = _live_event()
    keys = {agent._delivery_key({**event, "user_id": ref}) for ref in ("u-a", "u-b")}
    assert len(keys) == 2  # إيصال مستخدمٍ لا يكبت إرسال آخر


@pytest.mark.asyncio
async def test_non_uuid_tenant_has_no_subscribers_and_never_queries(agent, wired, monkeypatch):
    sent, _ = wired
    rows = AsyncMock(return_value=[_prefs("u-a")])
    monkeypatch.setattr(agent, "_fetch_tenant_pref_rows", rows)
    await agent.dispatch(_live_event(tenant_id="T1"))
    rows.assert_not_awaited()
    assert sent == []


@pytest.mark.asyncio
async def test_one_recipient_failing_does_not_block_the_others(agent, wired, monkeypatch):
    sent, _ = wired
    monkeypatch.setattr(
        agent, "_fetch_tenant_pref_rows", AsyncMock(return_value=[_prefs("u-a"), _prefs("u-b")])
    )

    async def _email(target, *_args):
        sent.append(("email", target))
        return target != "u-a@example.test"

    monkeypatch.setattr(agent, "send_email_async", _email)
    with pytest.raises(agent.DeliveryUnavailable, match="channels_failed:email$"):
        await agent.dispatch(_live_event())
    assert ("email", "u-b@example.test") in sent
    assert ("push", "tok-u-b") in sent


@pytest.mark.asyncio
async def test_targeted_event_still_uses_only_the_named_user(agent, wired, monkeypatch):
    sent, _ = wired
    rows = AsyncMock(return_value=[_prefs("u-a"), _prefs("u-b")])
    monkeypatch.setattr(agent, "_fetch_tenant_pref_rows", rows)
    monkeypatch.setattr(agent, "get_prefs", AsyncMock(return_value=_prefs("u-a")))
    await agent.dispatch(_live_event(user_id="u-a"))
    rows.assert_not_awaited()
    assert {target for _, target in sent} == {"u-a@example.test", "chat-u-a", "tok-u-a"}
