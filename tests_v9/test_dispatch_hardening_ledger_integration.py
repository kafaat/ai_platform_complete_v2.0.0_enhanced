"""tests_v9/test_dispatch_hardening_ledger_integration.py — تكامل تصليب الموزِّع + السجلّ.

يتحقّق من migrations/v67_dispatch_hardening.sql وv68_execution_ledger.sql على قاعدة
حقيقيّة (المرحلة A، الشريحتان 2 و4):
  • الفهرس الفريد الجزئيّ (tenant_id, idempotency_key) يمنع قرارين حيّين (queued/dispatched)
    بنفس المفتاح ⇒ لا إطلاق مزدوج؛ وبعد executed يُسمح بقرار جديد (دورة لاحقة مشروعة).
  • exec_status الموسَّع يقبل dispatched/failed (CHECK v67).
  • execution_ledger: تدوير القيد + content_hash، وعزل RLS لكلّ مستأجِر.

يعمل عبر ``pytest -m integration`` فقط (يتطلّب Postgres عبر TEST_DATABASE_URL)؛ يتخطّى
بوضوح إن لم تتوفّر القاعدة — كأشقّائه في tests_v9/.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@localhost:5433/sahool_test",
)

_RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز (NOBYPASSRLS) يُطبَّق عليه RLS


@pytest.fixture
async def conn():
    """اتّصال إعداد + سياق مستأجِر؛ ينظّف صفوف dispatch_decisions/execution_ledger."""
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    decision_ids: list[str] = []
    ledger_ids: list[str] = []
    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    ctx = {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "decision_ids": decision_ids,
        "ledger_ids": ledger_ids,
    }
    try:
        yield c, ctx
    finally:
        try:
            await c.execute("SELECT set_config('app.current_tenant', '', false)")
            if ledger_ids:
                await c.execute(
                    "DELETE FROM execution_ledger WHERE ledger_id = ANY($1::text[])", ledger_ids
                )
            if decision_ids:
                await c.execute(
                    "DELETE FROM dispatch_decisions WHERE decision_id = ANY($1::text[])",
                    decision_ids,
                )
        finally:
            await c.close()


async def _insert_decision(c, tenant, decision_id, *, exec_status, idem_key=None):
    await c.execute(
        """
        INSERT INTO dispatch_decisions (
            decision_id, tenant_id, recommendation_id, action_type,
            state, risk_level, exec_status, idempotency_key
        ) VALUES ($1, $2, 'rec_irr', 'irrigation', 'ready', 'low', $3, $4)
        """,
        decision_id,
        tenant,
        exec_status,
        idem_key,
    )


async def test_idempotency_index_blocks_duplicate_live(conn):
    """قراران حيّان بنفس (tenant, idempotency_key) ⇒ خرق فريد (لا إطلاق مزدوج)."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    id1 = f"dec_{uuid.uuid4().hex[:12]}"
    id2 = f"dec_{uuid.uuid4().hex[:12]}"
    ctx["decision_ids"].extend([id1, id2])
    key = "disp:" + uuid.uuid4().hex[:24]

    await _insert_decision(c, tenant_a, id1, exec_status="queued", idem_key=key)
    with pytest.raises(asyncpg.UniqueViolationError):
        await _insert_decision(c, tenant_a, id2, exec_status="queued", idem_key=key)


async def test_idempotency_allows_new_after_terminal(conn):
    """بعد executed (نهائيّة) يُسمح بقرار حيّ جديد بنفس المفتاح (الفهرس جزئيّ)."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    id1 = f"dec_{uuid.uuid4().hex[:12]}"
    id2 = f"dec_{uuid.uuid4().hex[:12]}"
    ctx["decision_ids"].extend([id1, id2])
    key = "disp:" + uuid.uuid4().hex[:24]

    await _insert_decision(c, tenant_a, id1, exec_status="executed", idem_key=key)
    # لا يصطدم: الصفّ النهائيّ خارج الفهرس الجزئيّ (queued/dispatched فقط).
    await _insert_decision(c, tenant_a, id2, exec_status="queued", idem_key=key)
    cnt = await c.fetchval(
        "SELECT count(*) FROM dispatch_decisions WHERE idempotency_key = $1", key
    )
    assert cnt == 2


async def test_extended_exec_status_states(conn):
    """exec_status الموسَّع (v67) يقبل dispatched/failed."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    for status in ("dispatched", "failed"):
        did = f"dec_{uuid.uuid4().hex[:12]}"
        ctx["decision_ids"].append(did)
        await _insert_decision(c, tenant_a, did, exec_status=status)
        got = await c.fetchval(
            "SELECT exec_status FROM dispatch_decisions WHERE decision_id = $1", did
        )
        assert got == status


async def test_execution_ledger_roundtrip(conn):
    """إدراج قيد سجلّ تنفيذ وقراءته — تدوير الحقول + detail JSONB + content_hash."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    ledger_id = f"led_{uuid.uuid4().hex[:12]}"
    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    ctx["ledger_ids"].append(ledger_id)
    detail = {"water_mm": 18.0, "valve": "v1"}

    await c.execute(
        """
        INSERT INTO execution_ledger (
            ledger_id, tenant_id, decision_id, action_type, field_id, channel,
            outcome, note_ar, detail, content_hash, recorded_by
        ) VALUES ($1, $2, $3, 'irrigation', 'fld_1', 'sms',
                  'executed', 'تمّ', $4::jsonb, $5, 'system')
        """,
        ledger_id,
        tenant_a,
        decision_id,
        json.dumps(detail),
        "a" * 64,
    )
    row = await c.fetchrow("SELECT * FROM execution_ledger WHERE ledger_id = $1", ledger_id)
    assert row is not None
    assert row["tenant_id"] == uuid.UUID(tenant_a)
    assert row["decision_id"] == decision_id
    assert row["outcome"] == "executed"
    assert row["channel"] == "sms"
    assert json.loads(row["detail"]) == detail
    assert row["content_hash"] == "a" * 64


async def test_execution_ledger_outcome_check(conn):
    """قيد CHECK يرفض نتيجة خارج (executed|failed)."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    ledger_id = f"led_{uuid.uuid4().hex[:12]}"
    ctx["ledger_ids"].append(ledger_id)
    with pytest.raises(asyncpg.CheckViolationError):
        await c.execute(
            """
            INSERT INTO execution_ledger (
                ledger_id, tenant_id, decision_id, action_type,
                outcome, content_hash
            ) VALUES ($1, $2, 'dec_x', 'irrigation', 'queued', $3)
            """,
            ledger_id,
            tenant_a,
            "b" * 64,
        )


async def test_execution_ledger_rls_isolation(conn):
    """عزل RLS: قيد المستأجِر A غير مرئيّ للمستأجِر B — يُقرأ عبر دور غير ممتاز."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    tenant_b = ctx["tenant_b"]
    ledger_id = f"led_{uuid.uuid4().hex[:12]}"
    ctx["ledger_ids"].append(ledger_id)

    await c.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_RLS_ROLE}') THEN
                CREATE ROLE {_RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await c.execute(f"GRANT USAGE ON SCHEMA public TO {_RLS_ROLE}")
    await c.execute(f"GRANT SELECT, INSERT ON execution_ledger TO {_RLS_ROLE}")

    await c.execute(
        """
        INSERT INTO execution_ledger (
            ledger_id, tenant_id, decision_id, action_type, outcome, content_hash
        ) VALUES ($1, $2, 'dec_y', 'spray', 'failed', $3)
        """,
        ledger_id,
        tenant_a,
        "c" * 64,
    )
    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
        seen_a = await c.fetchval(
            "SELECT count(*) FROM execution_ledger WHERE ledger_id = $1", ledger_id
        )
        assert seen_a == 1, "RLS يحجب المستأجِر عن قيده"

        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
        seen_b = await c.fetchval(
            "SELECT count(*) FROM execution_ledger WHERE ledger_id = $1", ledger_id
        )
        assert seen_b == 0, "خرق RLS: قيد المستأجِر A مرئيّ للمستأجِر B"
    finally:
        await c.execute("RESET ROLE")
