"""tests_v9/test_rls_write_isolation_integration.py — عزل كتابة المستأجرين (WITH CHECK).

يتحقّق من إصلاح المراجعة الأمنيّة #3 (v9 + v70) على قاعدة حقيقيّة: سياسة tenant_isolation
صارت بـWITH CHECK، فتمنع INSERT/UPDATE عابر المستأجرين تحت سياق مستأجِر، وتُبقي كتابة
النظام (بلا سياق) كما كانت — يُقرأ عبر دور غير ممتاز (NOBYPASSRLS) كي يُطبَّق RLS فعليّاً.

يعمل عبر ``pytest -m integration`` فقط (يتطلّب Postgres)؛ يتخطّى بوضوح إن لم تتوفّر القاعدة.
"""

from __future__ import annotations

import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@localhost:5433/sahool_test",
)

_RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز (NOBYPASSRLS) يخضع لـRLS


@pytest.fixture
async def conn():
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    field_ids: list[str] = []
    await c.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_RLS_ROLE}') THEN
                CREATE ROLE {_RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await c.execute(f"GRANT USAGE ON SCHEMA public TO {_RLS_ROLE}")
    await c.execute(f"GRANT SELECT, INSERT, UPDATE ON fields TO {_RLS_ROLE}")
    ctx = {"tenant_a": tenant_a, "tenant_b": tenant_b, "field_ids": field_ids}
    try:
        yield c, ctx
    finally:
        try:
            await c.execute("RESET ROLE")
            await c.execute("SELECT set_config('app.current_tenant', '', false)")
            if field_ids:
                await c.execute("DELETE FROM fields WHERE field_id = ANY($1::text[])", field_ids)
        finally:
            await c.close()


async def _insert_field(c, field_id, tenant):
    await c.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, 'حقل اختبار', $2::uuid)",
        field_id,
        tenant,
    )


async def test_same_tenant_write_allowed(conn):
    """تحت سياق المستأجِر A، كتابة صفّ بـtenant_id=A مسموحة."""
    c, ctx = conn
    fid = f"fld_{uuid.uuid4().hex[:12]}"
    ctx["field_ids"].append(fid)
    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", ctx["tenant_a"])
        await _insert_field(c, fid, ctx["tenant_a"])  # يجب أن تمرّ
    finally:
        await c.execute("RESET ROLE")
    # تحقّق عبر superuser أنّ الصفّ كُتب
    cnt = await c.fetchval("SELECT count(*) FROM fields WHERE field_id = $1", fid)
    assert cnt == 1


async def test_cross_tenant_insert_blocked(conn):
    """تحت سياق A، INSERT بـtenant_id=B يُرفَض (WITH CHECK) — عزل الكتابة."""
    c, ctx = conn
    fid = f"fld_{uuid.uuid4().hex[:12]}"
    ctx["field_ids"].append(fid)
    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", ctx["tenant_a"])
        with pytest.raises(asyncpg.PostgresError):  # check_violation / RLS rejection
            await _insert_field(c, fid, ctx["tenant_b"])
    finally:
        await c.execute("RESET ROLE")


async def test_cross_tenant_update_blocked(conn):
    """تحت سياق A، UPDATE ينقل صفّاً إلى tenant_id=B يُرفَض (WITH CHECK)."""
    c, ctx = conn
    fid = f"fld_{uuid.uuid4().hex[:12]}"
    ctx["field_ids"].append(fid)
    # أنشئ صفّ A كـsuperuser (إعداد)
    await _insert_field(c, fid, ctx["tenant_a"])
    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", ctx["tenant_a"])
        with pytest.raises(asyncpg.PostgresError):
            await c.execute(
                "UPDATE fields SET tenant_id = $1::uuid WHERE field_id = $2",
                ctx["tenant_b"],
                fid,
            )
    finally:
        await c.execute("RESET ROLE")


async def test_no_context_write_allowed(conn):
    """بلا سياق مستأجِر (مهامّ نظام/هجرات) تُسمح الكتابة كما كانت — لا كسر."""
    c, ctx = conn
    fid = f"fld_{uuid.uuid4().hex[:12]}"
    ctx["field_ids"].append(fid)
    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', '', false)")  # بلا سياق
        await _insert_field(c, fid, ctx["tenant_a"])  # يجب أن تمرّ (فرع بلا سياق)
    finally:
        await c.execute("RESET ROLE")
    cnt = await c.fetchval("SELECT count(*) FROM fields WHERE field_id = $1", fid)
    assert cnt == 1
