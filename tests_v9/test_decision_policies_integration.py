"""tests_v9/test_decision_policies_integration.py — تكامل سجلّ سياسات القرار.

يتحقّق من migrations/v69_decision_policies.sql على قاعدة حقيقيّة (المرحلة B، الشريحة 5):
تدوير السياسة (scope/effect JSONB) + عزل RLS لكلّ مستأجِر + الفهرس الجزئيّ للمُفعّلة.

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
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    policy_ids: list[str] = []
    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    ctx = {"tenant_a": tenant_a, "tenant_b": tenant_b, "policy_ids": policy_ids}
    try:
        yield c, ctx
    finally:
        try:
            await c.execute("SELECT set_config('app.current_tenant', '', false)")
            if policy_ids:
                await c.execute(
                    "DELETE FROM decision_policies WHERE policy_id = ANY($1::text[])", policy_ids
                )
        finally:
            await c.close()


async def _insert_policy(c, tenant, policy_id, *, scope, effect, priority=0, enabled=True):
    await c.execute(
        """
        INSERT INTO decision_policies (
            policy_id, tenant_id, name, scope, effect, priority, enabled, created_by
        ) VALUES ($1, $2, 'سياسة', $3::jsonb, $4::jsonb, $5, $6, 'system')
        """,
        policy_id,
        tenant,
        json.dumps(scope),
        json.dumps(effect),
        priority,
        enabled,
    )


async def test_policy_roundtrip(conn):
    """إدراج سياسة وقراءتها — تدوير scope/effect JSONB."""
    c, ctx = conn
    pid = f"pol_{uuid.uuid4().hex[:12]}"
    ctx["policy_ids"].append(pid)
    scope = {"action_type": "spray", "crop": "dates"}
    effect = {"auto_block": True, "require_approvals": 2}

    await _insert_policy(c, ctx["tenant_a"], pid, scope=scope, effect=effect, priority=5)
    row = await c.fetchrow("SELECT * FROM decision_policies WHERE policy_id = $1", pid)
    assert row is not None
    assert row["tenant_id"] == uuid.UUID(ctx["tenant_a"])
    assert row["priority"] == 5
    assert row["enabled"] is True
    assert json.loads(row["scope"]) == scope
    assert json.loads(row["effect"]) == effect


async def test_enabled_partial_index(conn):
    """الفهرس الجزئيّ enabled=TRUE يلتقط المُفعّلة فقط."""
    c, ctx = conn
    on_id = f"pol_{uuid.uuid4().hex[:12]}"
    off_id = f"pol_{uuid.uuid4().hex[:12]}"
    ctx["policy_ids"].extend([on_id, off_id])
    await _insert_policy(c, ctx["tenant_a"], on_id, scope={}, effect={"auto_block": True})
    await _insert_policy(
        c, ctx["tenant_a"], off_id, scope={}, effect={"auto_block": True}, enabled=False
    )
    enabled = await c.fetch(
        "SELECT policy_id FROM decision_policies WHERE enabled = TRUE "
        "AND policy_id = ANY($1::text[])",
        [on_id, off_id],
    )
    ids = {r["policy_id"] for r in enabled}
    assert on_id in ids
    assert off_id not in ids


async def test_policy_rls_isolation(conn):
    """عزل RLS: سياسة المستأجِر A غير مرئيّة للمستأجِر B — عبر دور غير ممتاز."""
    c, ctx = conn
    pid = f"pol_{uuid.uuid4().hex[:12]}"
    ctx["policy_ids"].append(pid)

    await c.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_RLS_ROLE}') THEN
                CREATE ROLE {_RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await c.execute(f"GRANT USAGE ON SCHEMA public TO {_RLS_ROLE}")
    await c.execute(f"GRANT SELECT, INSERT ON decision_policies TO {_RLS_ROLE}")

    await _insert_policy(c, ctx["tenant_a"], pid, scope={}, effect={"auto_block": True})
    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", ctx["tenant_a"])
        seen_a = await c.fetchval(
            "SELECT count(*) FROM decision_policies WHERE policy_id = $1", pid
        )
        assert seen_a == 1, "RLS يحجب المستأجِر عن سياسته"

        await c.execute("SELECT set_config('app.current_tenant', $1, false)", ctx["tenant_b"])
        seen_b = await c.fetchval(
            "SELECT count(*) FROM decision_policies WHERE policy_id = $1", pid
        )
        assert seen_b == 0, "خرق RLS: سياسة المستأجِر A مرئيّة للمستأجِر B"
    finally:
        await c.execute("RESET ROLE")
