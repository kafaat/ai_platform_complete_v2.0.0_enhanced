"""حارس عقد ترحيل v39.5-2 — تدقيق رسم حدود الحقل (field_geometry_history) append-only.

field_geometry_history (v96) يوثِّق مراجعات حدود الحقل لكنّه لم يفرض immutability؛
v139 يضيف trigger ``trg_append_only_field_geometry_history`` (BEFORE UPDATE OR DELETE)
عبر ``sahool_block_mutation`` — تماماً كحماية mfa_audit_events في v129.

- **unit** (لا Postgres): تأكيدات ساكنة على نصّ SQL في v139 — تلتقط الانحدار مبكراً.
  يحاكي ``test_mfa_migration_contract_guard.py``. لا يستورد أيّ خدمة (fastapi/pydantic).
- **integration** (``pytest -m integration``؛ يتخطّى إن لا Postgres): probe سلوكيّ داخل
  transaction يُلغى — INSERT مسموح، UPDATE/DELETE يجب أن يرفعا. يحاكي probe الـappend-only
  في ``test_mfa_hardening_integration_v29_5.py::test_mfa_migrations_applied_on_real_postgres``.
"""

from __future__ import annotations

import asyncio
import os
import re

import pytest

_V139 = os.path.join(
    os.path.dirname(__file__),
    "..",
    "migrations",
    "v139_field_geometry_history_append_only.sql",
)

_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


def _sql() -> str:
    return open(_V139, encoding="utf-8").read()


# ── unit: static contract guard on the migration SQL (no DB, no service import) ──
@pytest.mark.unit
def test_field_geometry_history_append_only_trigger_present():
    sql = _sql()
    m = re.search(
        r"CREATE TRIGGER\s+trg_append_only_field_geometry_history\b.*?;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, (
        "انحدار: trigger trg_append_only_field_geometry_history مفقود من v139 "
        "(تدقيق حدود الحقل غير محميّ من التزوير)."
    )
    trg = m.group(0)
    assert re.search(r"BEFORE\s+UPDATE\s+OR\s+DELETE", trg, re.IGNORECASE), (
        "trigger append-only يجب أن يعترض UPDATE و DELETE معاً."
    )
    assert "field_geometry_history" in trg
    assert "sahool_block_mutation" in trg, (
        "trigger يجب أن ينفّذ sahool_block_mutation (يرفع استثناءً يمنع التحوير)."
    )


@pytest.mark.unit
def test_v139_is_idempotent_and_reuses_helper():
    sql = _sql()
    # idempotent: يُسقِط الـtrigger قبل إنشائه.
    assert re.search(
        r"DROP TRIGGER IF EXISTS\s+trg_append_only_field_geometry_history",
        sql,
        re.IGNORECASE,
    ), "v139 يجب أن يكون idempotent (DROP TRIGGER IF EXISTS قبل CREATE)."
    # لا يُعيد تعريف الدالّة المساعِدة — يعيد استخدامها فقط.
    assert not re.search(
        r"CREATE\s+(OR REPLACE\s+)?FUNCTION\s+sahool_block_mutation",
        sql,
        re.IGNORECASE,
    ), "v139 يجب ألّا يُعيد تعريف sahool_block_mutation (يعيد استخدام دالّة v9)."


def _db_available() -> bool:
    try:
        import asyncpg

        async def _ping():
            c = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


# ── integration: behavioural probe on real Postgres (rolled back, no pollution) ──
@pytest.mark.integration
def test_field_geometry_history_append_only_enforced_on_real_postgres():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import uuid

    import asyncpg

    async def _check():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            tenant = uuid.uuid4()
            # service context so the tenant_isolation policy (v96) doesn't block our probe.
            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant))

            # v139 — trigger present on field_geometry_history.
            trg = {
                r["tgname"]
                for r in await conn.fetch(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid='field_geometry_history'::regclass AND NOT tgisinternal"
                )
            }
            assert "trg_append_only_field_geometry_history" in trg, (
                "trigger append-only غائب على field_geometry_history بعد v139."
            )

            field_id = "probe-" + uuid.uuid4().hex[:8]

            # UPDATE must raise — inside a tx we force to roll back (no pollution).
            update_raised = False
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO field_geometry_history "
                        "(tenant_id, field_id, geometry, reason) "
                        "VALUES ($1, $2, '{}'::jsonb, 'append_only_probe')",
                        tenant,
                        field_id,
                    )
                    await conn.execute(
                        "UPDATE field_geometry_history SET reason='tampered' "
                        "WHERE tenant_id=$1 AND field_id=$2",
                        tenant,
                        field_id,
                    )
            except asyncpg.PostgresError:
                update_raised = True
            assert update_raised, "append-only trigger لم يمنع UPDATE على field_geometry_history"

            # DELETE must raise too — separate rolled-back tx.
            delete_raised = False
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO field_geometry_history "
                        "(tenant_id, field_id, geometry, reason) "
                        "VALUES ($1, $2, '{}'::jsonb, 'append_only_probe')",
                        tenant,
                        field_id,
                    )
                    await conn.execute(
                        "DELETE FROM field_geometry_history WHERE tenant_id=$1 AND field_id=$2",
                        tenant,
                        field_id,
                    )
            except asyncpg.PostgresError:
                delete_raised = True
            assert delete_raised, "append-only trigger لم يمنع DELETE على field_geometry_history"
        finally:
            await conn.close()

    asyncio.run(_check())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
