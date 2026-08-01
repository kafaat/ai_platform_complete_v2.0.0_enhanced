"""وكيل الإشعارات — عزل المستأجِر في بثّ أحداث المنصّة (sahool.events.*).

الخلفيّة: OutboxWorker على المنصّة ينشر أحداث domain على sahool.events.<type>
بمظروف يحمل tenant_id (لا user_id). كانت بلا مستهلك أصلاً، وحين تُستهلك يجب ألّا
تُبثّ عابرةً للمستأجرين. هذا الاختبار يثبّت:
  1) broadcast_tenant يصل مستخدمي المستأجِر المستهدَف فقط (لا تسريب).
  2) dispatch لحدث بلا user_id لكن بـtenant_id يوجّه عبر broadcast_tenant.
دالّات نقيّة بـwebsocket وهميّ — بلا NATS/قاعدة بيانات (CI-enforced).
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


class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_broadcast_tenant_isolation(agent_mod):
    mgr = agent_mod.ConnectionManager()
    ws_a, ws_b = _FakeWS(), _FakeWS()
    assert await mgr.connect("ua", ws_a, tenant_id="T1")
    assert await mgr.connect("ub", ws_b, tenant_id="T2")

    await mgr.broadcast_tenant("T1", {"event_type": "field.created", "tenant_id": "T1"})

    assert len(ws_a.sent) == 1  # مستخدم المستأجِر المستهدَف يستلم
    assert ws_b.sent == []  # مستأجِر آخر لا يستلم (لا تسريب)


@pytest.mark.asyncio
async def test_broadcast_tenant_empty_is_noop(agent_mod):
    mgr = agent_mod.ConnectionManager()
    ws_a = _FakeWS()
    await mgr.connect("ua", ws_a, tenant_id="T1")
    await mgr.broadcast_tenant("", {"x": 1})  # tenant فارغ ⇒ لا-عمل آمن
    assert ws_a.sent == []


@pytest.mark.asyncio
async def test_dispatch_tenant_event_routes_scoped(agent_mod, monkeypatch):
    mgr = agent_mod.ConnectionManager()
    ws_a, ws_b = _FakeWS(), _FakeWS()
    await mgr.connect("ua", ws_a, tenant_id="T1")
    await mgr.connect("ub", ws_b, tenant_id="T2")
    monkeypatch.setattr(agent_mod, "manager", mgr)

    # مظروف حدث منصّة نموذجيّ: tenant_id حاضر، بلا user_id ⇒ يجب أن يقتصر على T1.
    await agent_mod.dispatch(
        {"event_type": "season.created", "entity_id": "fld_1", "tenant_id": "T1"}
    )

    assert len(ws_a.sent) == 1
    assert ws_b.sent == []
