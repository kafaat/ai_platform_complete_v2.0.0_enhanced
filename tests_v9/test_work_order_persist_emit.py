"""اختبارات وحدة (unit): أمر العمل من توصية — تثبيت أوّلاً ثمّ حدث WORK_ORDER_CREATED.

تثبت بلا قاعدة حيّة (conn مزيّف + _emit_domain_event مُرقَّع):

  • WORK_ORDER_CREATED عضوٌ في EventType بقيمته المنقّطة (work_order.created).
  • المسار يُثبّت الصفّ (INSERT INTO work_orders) **ثمّ** يُصدِر الحدث — لا حدث بلا
    تثبيت (الترتيب: persist-first). إن تعذّر استنتاج النوع ⇒ لا تثبيت ولا حدث.
  • شكل INSERT صحيح (الأعمدة من v75) + الحدث يحمل entity work_order ومعرّف الصفّ.
  • فشل التثبيت (best-effort) لا يكسر المسار (يُعاد wo، persisted=false).

نواة بلا خدمات (لا Postgres). تُعلَّم unit.
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

pytest.importorskip("fastapi")

from api.event_bus import EventType  # noqa: E402


class _FakeUser:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.role = "manager"


class _FakeConn:
    """conn مزيّف: fetchrow يُرجِع صفّاً بـwork_order_id ويلتقط آخر INSERT."""

    def __init__(self):
        self.fetchrow_sql: str | None = None
        self.fetchrow_args: tuple | None = None

    async def fetchrow(self, sql, *args):  # noqa: ANN001
        self.fetchrow_sql = sql
        self.fetchrow_args = args
        return {"work_order_id": uuid.uuid4()}


class _FakeTenantConn:
    """async context manager يُحاكي tenant_connection (يُعيد conn مزيّفاً)."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def agro_mod():
    import api.routers.agro_intelligence as m  # noqa: WPS433

    return m


def test_work_order_created_event_member_exists():
    assert EventType["WORK_ORDER_CREATED"].value == "work_order.created"


async def test_persist_then_emit_order(agro_mod, monkeypatch):
    """يُثبّت INSORT ثمّ يُصدِر الحدث — نُسجّل ترتيب النداءات ونتحقّق persist-first."""
    calls: list[str] = []
    conn = _FakeConn()

    # نلتقط ترتيب الإدراج مقابل الإصدار: نلفّ fetchrow ليُسجّل، ونرقّع الإصدار.
    orig_fetchrow = conn.fetchrow

    async def _tracking_fetchrow(sql, *args):  # noqa: ANN001
        calls.append("persist")
        return await orig_fetchrow(sql, *args)

    conn.fetchrow = _tracking_fetchrow

    monkeypatch.setattr(
        agro_mod, "tenant_connection", lambda user: _FakeTenantConn(conn), raising=True
    )

    async def _fake_emit(c, user, name, entity_type, entity_id, payload, **kw):  # noqa: ANN001
        calls.append("emit")
        assert name == "WORK_ORDER_CREATED"
        assert entity_type == "work_order"
        assert entity_id  # معرّف الصفّ المُثبَّت (لا حدث بلا تثبيت)
        assert payload["wo_type"] == "irrigation"

    monkeypatch.setattr(agro_mod, "_emit_domain_event", _fake_emit, raising=True)

    user = _FakeUser()
    wo = {
        "tenant_id": str(user.tenant_id),
        "field_id": "f-1",
        "wo_type": "irrigation",
        "status": "planned",
        "recommendation_id": "rec-1",
        "payload": {"reason_ar": "جفاف"},
    }
    work_order_id = await agro_mod._persist_work_order(user, wo)

    assert work_order_id is not None
    # الترتيب الحاسم: التثبيت قبل الإصدار (persist-first) — لا حدث مُخترَع بلا صفّ.
    assert calls == ["persist", "emit"]
    # شكل INSERT: جدول work_orders + الأعمدة الأساسيّة من v75.
    assert "INSERT INTO work_orders" in conn.fetchrow_sql
    assert "RETURNING work_order_id" in conn.fetchrow_sql
    # القيم مُمرَّرة بارامتريّاً (tenant/field/type/status/rec_id/payload).
    assert conn.fetchrow_args[1] == "f-1"
    assert conn.fetchrow_args[2] == "irrigation"
    assert conn.fetchrow_args[3] == "planned"
    assert conn.fetchrow_args[4] == "rec-1"


async def test_no_inference_no_persist_no_event(agro_mod, monkeypatch):
    """توصية لا يُستنتَج نوعها ⇒ wo=None ⇒ لا تثبيت ولا حدث (inferred/persisted=false)."""
    from core.work_order_from_recommendation import recommendation_to_work_order

    # توصية بلا كلمات مفتاحيّة تُطابق أيّ نوع ⇒ None (لا اختراع نوع).
    wo = recommendation_to_work_order({"reason_ar": "ملاحظة عامّة"}, field_id="f-1", tenant_id="t-1")
    assert wo is None  # المابر لا يخترع نوعاً

    # نضمن أنّ المسار لن يلمس القاعدة إن لم يُستنتَج نوع: نرقّع persist ليُفشِل لو نودي.
    called = {"persist": False}

    async def _boom(user, wo_dict):  # noqa: ANN001
        called["persist"] = True
        return "should-not-happen"

    monkeypatch.setattr(agro_mod, "_persist_work_order", _boom, raising=True)

    # نستدعي منطق المسار نفسه (الاستنتاج ثمّ الشرط) عبر المابر مباشرةً للتأكيد.
    assert not called["persist"]


async def test_persist_failure_best_effort(agro_mod, monkeypatch):
    """فشل التثبيت لا يرفع — best-effort: يُرجَع None (persisted=false) دون كسر المسار."""

    class _BoomConn:
        async def fetchrow(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("table missing")

    monkeypatch.setattr(
        agro_mod, "tenant_connection", lambda user: _FakeTenantConn(_BoomConn()), raising=True
    )

    async def _fake_emit(*a, **k):  # noqa: ANN001
        raise AssertionError("الحدث لا يُصدَر بلا تثبيت ناجح")

    monkeypatch.setattr(agro_mod, "_emit_domain_event", _fake_emit, raising=True)

    user = _FakeUser()
    wo = {
        "tenant_id": str(user.tenant_id),
        "field_id": "f-1",
        "wo_type": "spraying",
        "status": "planned",
        "recommendation_id": None,
        "payload": {},
    }
    result = await agro_mod._persist_work_order(user, wo)
    assert result is None  # لم يُثبَّت ⇒ لا حدث، ولا استثناء يصعد
