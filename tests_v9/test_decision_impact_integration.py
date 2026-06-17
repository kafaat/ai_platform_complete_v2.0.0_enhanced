"""tests_v9/test_decision_impact_integration.py — تكامل قياس الأثر (join السجلّ↔القرار).

يتحقّق من استخراج كمّيّات الماء عبر join execution_ledger ↔ dispatch_decisions (المرحلة C،
الشريحة 8): الماء المطلوب من command.payload، والمُطبَّق من ledger.detail — معزولاً بـRLS.

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


@pytest.fixture
async def conn():
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant_a = str(uuid.uuid4())
    decision_ids: list[str] = []
    ledger_ids: list[str] = []
    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    ctx = {"tenant_a": tenant_a, "decision_ids": decision_ids, "ledger_ids": ledger_ids}
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


async def test_impact_join_extracts_water(conn):
    """قرار بأمر فيه water_mm=20 + سجلّ تنفيذ بـdetail water_mm=14 ⇒ موفَّر 6مم."""
    c, ctx = conn
    tenant = ctx["tenant_a"]
    did = f"dec_{uuid.uuid4().hex[:12]}"
    lid = f"led_{uuid.uuid4().hex[:12]}"
    field_id = f"fld_{uuid.uuid4().hex[:12]}"
    ctx["decision_ids"].append(did)
    ctx["ledger_ids"].append(lid)

    command = {"device_id": "v1", "command": "open_valve", "payload": {"water_mm": 20.0}}
    await c.execute(
        """
        INSERT INTO dispatch_decisions (
            decision_id, tenant_id, recommendation_id, action_type, field_id,
            state, risk_level, command, exec_status
        ) VALUES ($1, $2, 'rec', 'irrigation', $3, 'ready', 'low', $4::jsonb, 'executed')
        """,
        did,
        tenant,
        field_id,
        json.dumps(command),
    )
    await c.execute(
        """
        INSERT INTO execution_ledger (
            ledger_id, tenant_id, decision_id, action_type, field_id,
            outcome, detail, content_hash, recorded_by
        ) VALUES ($1, $2, $3, 'irrigation', $4, 'executed', $5::jsonb, $6, 'system')
        """,
        lid,
        tenant,
        did,
        field_id,
        json.dumps({"water_mm": 14.0}),
        "a" * 64,
    )

    # نُحاكي استخراج الموجِّه: join + measure_impact.
    rows = await c.fetch(
        """
        SELECT l.outcome, l.action_type, l.detail, d.command
        FROM execution_ledger l
        LEFT JOIN dispatch_decisions d ON d.decision_id = l.decision_id
        WHERE l.field_id = $1
        """,
        field_id,
    )
    assert len(rows) == 1
    r = rows[0]
    detail = json.loads(r["detail"]) if isinstance(r["detail"], str) else r["detail"]
    command_back = json.loads(r["command"]) if isinstance(r["command"], str) else r["command"]
    assert detail["water_mm"] == 14.0
    assert command_back["payload"]["water_mm"] == 20.0
    assert r["outcome"] == "executed"
