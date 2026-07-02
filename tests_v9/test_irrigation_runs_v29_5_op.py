"""tests_v9/test_irrigation_runs_v29_5_op.py — دفتر تشغيل الريّ (v29.5-op-2).

يتحقّق من migrations/v136_irrigation_runs.sql: جدول ``irrigation_runs`` — دفتر أحداث
تشغيل فيزيائيّ منفصلة (فتح→إغلاق صمّام). طبقتان:

  • **وحدة** (بلا خدمات/قاعدة): الدالّة الصرفة ``plan_run_ledger_action`` تُقرّر أثر
    تبدّل حالة الصمّام على الدفتر (open⇒open_run · closed⇒close_run · غيرهما⇒None).
  • **تكامل** (يتطلّب Postgres عبر TEST_DATABASE_URL): تدوير إدراج تشغيل + إغلاقه +
    قيد CHECK يرفض status باطلاً + عزل RLS لكلّ مستأجِر (B لا يرى صفّ A).

طبقة الوحدة تعمل تحت ``pytest -m unit``. طبقة التكامل تعمل تحت ``pytest -m integration``
فقط وتتخطّى بوضوح إن لم تتوفّر القاعدة — مرآةً لـtest_dispatch_hardening_ledger_integration.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

# مسار خدمة المنصّة كي يُستورَد api.irrigation_models (self-contained: pydantic فقط).
_API_ROOT = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))


# ─────────────────────────── وحدة: الدالّة الصرفة ───────────────────────────
@pytest.mark.unit
def test_plan_run_ledger_action_open():
    from api.irrigation_models import plan_run_ledger_action

    assert plan_run_ledger_action("open") == "open_run"


@pytest.mark.unit
def test_plan_run_ledger_action_closed():
    from api.irrigation_models import plan_run_ledger_action

    assert plan_run_ledger_action("closed") == "close_run"


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "unknown", "OPEN", "opened", "off", "on"])
def test_plan_run_ledger_action_other_is_none(bad):
    """أيّ حالة غير open/closed ⇒ None (لا نخترع تشغيلاً في الدفتر)."""
    from api.irrigation_models import plan_run_ledger_action

    assert plan_run_ledger_action(bad) is None


# ─────────────────────────── تكامل: القاعدة الحقيقيّة ───────────────────────────
asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)

_RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز (NOBYPASSRLS) يُطبَّق عليه RLS


@pytest.fixture
async def conn():
    """اتّصال إعداد + سياق مستأجِر؛ ينظّف صفوف irrigation_runs المُدرَجة."""
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    run_ids: list[str] = []
    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
    ctx = {"tenant_a": tenant_a, "tenant_b": tenant_b, "run_ids": run_ids}
    try:
        yield c, ctx
    finally:
        try:
            await c.execute("SELECT set_config('app.current_tenant', '', false)")
            if run_ids:
                await c.execute("DELETE FROM irrigation_runs WHERE id = ANY($1::uuid[])", run_ids)
        finally:
            await c.close()


async def _open_run(c, tenant, *, valve_id="vlv_1", field_id="fld_1"):
    """يفتح صفّ تشغيل جارٍ ويعيد id (نمط نقطة set_valve_state عند open)."""
    run_id = await c.fetchval(
        """
        INSERT INTO irrigation_runs
            (tenant_id, field_id, valve_id, trigger_source, status)
        VALUES ($1, $2, $3, 'valve_api', 'running')
        RETURNING id
        """,
        tenant,
        field_id,
        valve_id,
    )
    return str(run_id)


@pytest.mark.integration
async def test_open_then_close_roundtrip(conn):
    """فتح تشغيل ثمّ إغلاقه — تدوير الحقول + انتقال running→completed + الحجم."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    run_id = await _open_run(c, tenant_a, valve_id="vlv_rt", field_id="fld_rt")
    ctx["run_ids"].append(run_id)

    opened = await c.fetchrow("SELECT * FROM irrigation_runs WHERE id = $1", run_id)
    assert opened is not None
    assert opened["tenant_id"] == uuid.UUID(tenant_a)
    assert opened["status"] == "running"
    assert opened["stopped_at"] is None
    assert opened["field_id"] == "fld_rt"
    assert opened["valve_id"] == "vlv_rt"

    # إغلاق أحدث تشغيل جارٍ لهذا الصمّام (يحاكي مسار close في set_valve_state).
    await c.execute(
        """
        UPDATE irrigation_runs
           SET stopped_at = NOW(),
               status     = 'completed',
               volume_l   = COALESCE($2, volume_l),
               volume_mm  = COALESCE($3, volume_mm)
         WHERE id = (
             SELECT id FROM irrigation_runs
              WHERE valve_id = $1 AND status = 'running'
              ORDER BY started_at DESC LIMIT 1
         )
        """,
        "vlv_rt",
        1250.0,
        18.5,
    )
    closed = await c.fetchrow("SELECT * FROM irrigation_runs WHERE id = $1", run_id)
    assert closed["status"] == "completed"
    assert closed["stopped_at"] is not None
    assert float(closed["volume_l"]) == 1250.0
    assert float(closed["volume_mm"]) == 18.5


@pytest.mark.integration
async def test_status_check_rejects_bad_value(conn):
    """قيد CHECK يرفض status خارج (running|completed|aborted|failed)."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    with pytest.raises(asyncpg.CheckViolationError):
        await c.execute(
            """
            INSERT INTO irrigation_runs (tenant_id, valve_id, status)
            VALUES ($1, 'vlv_bad', 'paused')
            """,
            tenant_a,
        )


@pytest.mark.integration
async def test_rls_isolation(conn):
    """عزل RLS: تشغيل المستأجِر A غير مرئيّ للمستأجِر B — يُقرأ عبر دور غير ممتاز."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    tenant_b = ctx["tenant_b"]
    run_id = await _open_run(c, tenant_a, valve_id="vlv_rls", field_id="fld_rls")
    ctx["run_ids"].append(run_id)

    await c.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_RLS_ROLE}') THEN
                CREATE ROLE {_RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await c.execute(f"GRANT USAGE ON SCHEMA public TO {_RLS_ROLE}")
    await c.execute(f"GRANT SELECT, INSERT ON irrigation_runs TO {_RLS_ROLE}")

    try:
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
        seen_a = await c.fetchval("SELECT count(*) FROM irrigation_runs WHERE id = $1", run_id)
        assert seen_a == 1, "RLS يحجب المستأجِر عن تشغيله"

        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
        seen_b = await c.fetchval("SELECT count(*) FROM irrigation_runs WHERE id = $1", run_id)
        assert seen_b == 0, "خرق RLS: تشغيل المستأجِر A مرئيّ للمستأجِر B"
    finally:
        await c.execute("RESET ROLE")
