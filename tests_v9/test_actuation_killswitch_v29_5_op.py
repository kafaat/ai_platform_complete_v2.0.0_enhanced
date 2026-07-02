"""tests_v9/test_actuation_killswitch_v29_5_op.py — مفتاح إيقاف طوارئ التشغيل (v29.5-op-1).

يغطّي شريحة v133_actuation_killswitch على مستويين:

  • **وحدة** (``pytest -m unit``، بلا قاعدة): منطق المطابقة النقيّ
    ``shared.actuation_killswitch.match_killswitch`` — نطاق tenant/field/valve + الانتهاء
    (expires_at) + إهمال غير الفعّال (active=false)؛ وسلوك fail-closed لِـ
    ``is_actuation_halted`` عند تعذّر القاعدة (استثناء ⇒ halted=True).

  • **تكامل** (``pytest -m integration``، يتطلّب Postgres عبر TEST_DATABASE_URL): اشتباك
    مفتاح مستأجِر ⇒ يوقف كلّ شيء؛ مفتاح حقل ⇒ ذلك الحقل فقط؛ منتهٍ/غير فعّال ⇒ لا يوقف؛
    عزل RLS (مفتاح المستأجِر A غير مرئيّ للمستأجِر B). يتخطّى بوضوح إن غابت القاعدة —
    كأشقّائه في tests_v9/ (يعكس test_dispatch_hardening_ledger_integration.py).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from shared.actuation_killswitch import (
    FAIL_CLOSED_REASON,
    is_actuation_halted,
    match_killswitch,
)

# ══════════════════════════════════════════════════════════════
# الجزء الأوّل: وحدة — منطق المطابقة النقيّ (بلا قاعدة)
# ══════════════════════════════════════════════════════════════


def _sw(scope, *, field_id=None, valve_id=None, active=True, reason="طوارئ", expires_at=None):
    return {
        "scope": scope,
        "field_id": field_id,
        "valve_id": valve_id,
        "active": active,
        "reason": reason,
        "expires_at": expires_at,
    }


@pytest.mark.unit
def test_tenant_scope_halts_everything():
    """مفتاح نطاق tenant يوقف أيّ استشارة (بأيّ حقل/صمّام أو بلا شيء)."""
    switches = [_sw("tenant", reason="إغلاق كامل")]
    assert match_killswitch(switches) == (True, "إغلاق كامل")
    assert match_killswitch(switches, field_id="f1")[0] is True
    assert match_killswitch(switches, valve_id="v1")[0] is True


@pytest.mark.unit
def test_field_scope_halts_only_that_field():
    """مفتاح نطاق field يوقف الحقل المُطابق فقط — لا حقلاً آخر ولا استشارة صمّام."""
    switches = [_sw("field", field_id="f1", reason="إيقاف حقل f1")]
    assert match_killswitch(switches, field_id="f1") == (True, "إيقاف حقل f1")
    assert match_killswitch(switches, field_id="f2") == (False, None)
    assert match_killswitch(switches, valve_id="v9") == (False, None)


@pytest.mark.unit
def test_valve_scope_halts_only_that_valve():
    """مفتاح نطاق valve يوقف الصمّام المُطابق فقط."""
    switches = [_sw("valve", valve_id="v1", reason="إيقاف صمّام v1")]
    assert match_killswitch(switches, valve_id="v1") == (True, "إيقاف صمّام v1")
    assert match_killswitch(switches, valve_id="v2") == (False, None)
    assert match_killswitch(switches, field_id="f1") == (False, None)


@pytest.mark.unit
def test_expired_switch_does_not_halt():
    """مفتاح منتهٍ (expires_at في الماضي) لا يوقف؛ ومستقبليّ يوقف."""
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=1)
    assert match_killswitch([_sw("tenant", expires_at=past)]) == (False, None)
    assert match_killswitch([_sw("tenant", expires_at=future)])[0] is True


@pytest.mark.unit
def test_inactive_switch_does_not_halt():
    """مفتاح غير فعّال (active=false) يُهمَل."""
    assert match_killswitch([_sw("tenant", active=False)]) == (False, None)


@pytest.mark.unit
def test_first_matching_reason_wins():
    """أوّل مفتاح مُطابِق يحدّد السبب المُعاد."""
    switches = [
        _sw("field", field_id="f9", reason="آخر"),
        _sw("tenant", reason="الأوّل المُطابِق"),
    ]
    assert match_killswitch(switches, field_id="f1") == (True, "الأوّل المُطابِق")


class _RaisingConn:
    """اتّصال وهميّ يرمي عند أيّ استعلام — لاختبار fail-closed دون قاعدة."""

    def transaction(self):
        class _CM:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *exc):
                return False

        return _CM()

    async def execute(self, *args, **kwargs):
        raise RuntimeError("القاعدة غير متاحة")

    async def fetch(self, *args, **kwargs):
        raise RuntimeError("القاعدة غير متاحة")


@pytest.mark.unit
async def test_is_actuation_halted_fail_closed_on_db_error():
    """تعذّر القاعدة (استثناء) ⇒ halted=True بسبب fail-closed (لا تشغيل بلا تأكّد)."""
    halted, reason = await is_actuation_halted(
        _RaisingConn(), str(uuid.uuid4()), field_id="f1", valve_id="v1"
    )
    assert halted is True
    assert reason == FAIL_CLOSED_REASON


# ══════════════════════════════════════════════════════════════
# الجزء الثاني: تكامل — القاعدة الحقيقيّة + RLS (يتخطّى بلا قاعدة)
# ══════════════════════════════════════════════════════════════

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)

_RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز (NOBYPASSRLS) يُطبَّق عليه RLS


@pytest.fixture
async def ks_conn():
    """اتّصال إعداد + سياق مستأجِر A؛ ينظّف صفوف actuation_killswitch المُدرَجة."""
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    switch_ids: list[str] = []
    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    ctx = {"tenant_a": tenant_a, "tenant_b": tenant_b, "switch_ids": switch_ids}
    try:
        yield c, ctx
    finally:
        try:
            await c.execute("SELECT set_config('app.current_tenant', '', false)")
            if switch_ids:
                await c.execute(
                    "DELETE FROM actuation_killswitch WHERE id = ANY($1::uuid[])", switch_ids
                )
        finally:
            await c.close()


async def _engage(
    c,
    tenant,
    ctx,
    *,
    scope,
    field_id=None,
    valve_id=None,
    reason="طوارئ",
    active=True,
    expires_at=None,
):
    sid = await c.fetchval(
        """
        INSERT INTO actuation_killswitch
            (tenant_id, scope, field_id, valve_id, reason, active, expires_at)
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        tenant,
        scope,
        field_id,
        valve_id,
        reason,
        active,
        expires_at,
    )
    ctx["switch_ids"].append(str(sid))
    return sid


@pytest.mark.integration
async def test_tenant_switch_halts_all(ks_conn):
    """مفتاح نطاق tenant مُشتبَك ⇒ is_actuation_halted يُوقف أيّ حقل/صمّام."""
    c, ctx = ks_conn
    ta = ctx["tenant_a"]
    await _engage(c, ta, ctx, scope="tenant", reason="إغلاق طوارئ كامل")
    halted, reason = await is_actuation_halted(c, ta, field_id="any", valve_id="any")
    assert halted is True
    assert reason == "إغلاق طوارئ كامل"


@pytest.mark.integration
async def test_field_switch_halts_only_that_field(ks_conn):
    """مفتاح نطاق field يوقف ذلك الحقل فقط — لا حقلاً آخر."""
    c, ctx = ks_conn
    ta = ctx["tenant_a"]
    await _engage(c, ta, ctx, scope="field", field_id="fld_hot", reason="إيقاف الحقل")
    assert (await is_actuation_halted(c, ta, field_id="fld_hot"))[0] is True
    assert (await is_actuation_halted(c, ta, field_id="fld_cold")) == (False, None)


@pytest.mark.integration
async def test_expired_switch_not_halting(ks_conn):
    """مفتاح منتهٍ لا يوقف (الاستعلام يستبعد expires_at <= now)."""
    c, ctx = ks_conn
    ta = ctx["tenant_a"]
    past = datetime.now(UTC) - timedelta(hours=2)
    await _engage(c, ta, ctx, scope="tenant", reason="منتهٍ", expires_at=past)
    assert (await is_actuation_halted(c, ta, field_id="x")) == (False, None)


@pytest.mark.integration
async def test_inactive_switch_not_halting(ks_conn):
    """مفتاح غير فعّال (active=false) لا يوقف."""
    c, ctx = ks_conn
    ta = ctx["tenant_a"]
    await _engage(c, ta, ctx, scope="tenant", reason="مفكوك", active=False)
    assert (await is_actuation_halted(c, ta, valve_id="v1")) == (False, None)


@pytest.mark.integration
async def test_killswitch_rls_isolation(ks_conn):
    """عزل RLS: مفتاح المستأجِر A غير مرئيّ للمستأجِر B — يُقرأ عبر دور غير ممتاز."""
    c, ctx = ks_conn
    ta = ctx["tenant_a"]
    tb = ctx["tenant_b"]
    sid = await _engage(c, ta, ctx, scope="tenant", reason="سرّ A")

    await c.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_RLS_ROLE}') THEN
                CREATE ROLE {_RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await c.execute(f"GRANT USAGE ON SCHEMA public TO {_RLS_ROLE}")
    await c.execute(f"GRANT SELECT, INSERT ON actuation_killswitch TO {_RLS_ROLE}")

    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", ta)
        seen_a = await c.fetchval("SELECT count(*) FROM actuation_killswitch WHERE id = $1", sid)
        assert seen_a == 1, "RLS يحجب المستأجِر عن مفتاحه"

        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tb)
        seen_b = await c.fetchval("SELECT count(*) FROM actuation_killswitch WHERE id = $1", sid)
        assert seen_b == 0, "خرق RLS: مفتاح المستأجِر A مرئيّ للمستأجِر B"
    finally:
        await c.execute("RESET ROLE")
