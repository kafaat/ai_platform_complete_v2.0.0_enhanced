"""tests_v9/test_dispatch_decisions_integration.py — تكامل سجلّ قرارات الإرسال.

يتحقّق من جدول ``dispatch_decisions`` (migrations/v66_dispatch_decisions.sql):
سجلّ تدقيق قرارات الإرسال المحروسة + طابور أوامر الـactuator، **معزول** لكلّ
مستأجِر عبر RLS.

يعمل عبر: ``pytest -m integration`` فقط — مُستثنى من بوّابة ``-m unit`` الافتراضيّة،
ويتطلّب Postgres مُهيّأً عبر ``TEST_DATABASE_URL``. يتخطّى بوضوح (SKIP) إن لم تتوفّر
القاعدة — كأشقّائه في ``tests_v9/`` (مثل ``test_field_aggregate_ports_integration.py``).

ملاحظات صدق:
  • GUC العزل هو ``app.current_tenant`` (سياسة RLS ``tenant_isolation`` المطبَّقة عبر
    ``_sahool_apply_tenant_rls`` تقرأ ``current_setting('app.current_tenant', …)``)
    — نضبطه عبر ``set_config(…, false)``.
  • العزل (RLS) يُختبَر صراحةً: صفّ المستأجِر A لا يُرى عند ضبط GUC للمستأجِر B.
  • ``halt_breaches`` / ``warn_breaches`` تُخزَّن JSONB وتُعاد كقوائم (asyncpg يفكّ
    JSONB إلى ``str`` خاماً ما لم يُسجَّل codec — فنفكّ بـ``json.loads``).
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
    """اتّصال للإعداد + ضبط سياق مستأجِر (``app.current_tenant``).

    ينظّف صفوف الاختبار في الـteardown (آمن من حيث FK: لا تبعيّات على
    ``dispatch_decisions``). يتخطّى بوضوح إن لم تتوفّر القاعدة.
    """
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    decision_ids: list[str] = []

    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)

    ctx = {"tenant_a": tenant_a, "tenant_b": tenant_b, "decision_ids": decision_ids}
    try:
        yield c, ctx
    finally:
        try:
            # تنظيف تحت GUC فارغ كي تُرى صفوف كلّ المستأجرين (لا قيود FK خارجة).
            await c.execute("SELECT set_config('app.current_tenant', '', false)")
            if decision_ids:
                await c.execute(
                    "DELETE FROM dispatch_decisions WHERE decision_id = ANY($1::text[])",
                    decision_ids,
                )
        finally:
            await c.close()


async def test_dispatch_decision_roundtrip(conn):
    """إدراج قرار تحت المستأجِر A وقراءته — تدوير الحقول + JSONB كقوائم."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    field_id = f"fld_{uuid.uuid4().hex[:12]}"
    ctx["decision_ids"].append(decision_id)

    halt = [{"metric": "soil_moisture", "limit": 0.2}]
    warn = [{"metric": "wind_speed", "limit": 12}]
    command = {"actuator": "valve", "op": "open", "duration_s": 600}

    await c.execute(
        """
        INSERT INTO dispatch_decisions (
            decision_id, tenant_id, recommendation_id, action_type, field_id,
            state, risk_level, required_approvals, approvals_collected,
            halt_breaches, warn_breaches, reason_ar, command, exec_status, created_by
        ) VALUES (
            $1, $2, $3, $4, $5,
            'ready', 'low', 1, 1,
            $6::jsonb, $7::jsonb, $8, $9::jsonb, 'queued', $10
        )
        """,
        decision_id,
        tenant_a,
        "rec_irrigation_42",
        "irrigation.open_valve",
        field_id,
        json.dumps(halt),
        json.dumps(warn),
        "السماح بالريّ — كلّ الحواجز مستوفاة",
        json.dumps(command),
        "system:dispatcher",
    )

    row = await c.fetchrow("SELECT * FROM dispatch_decisions WHERE decision_id = $1", decision_id)
    assert row is not None
    assert row["tenant_id"] == uuid.UUID(tenant_a)
    assert row["recommendation_id"] == "rec_irrigation_42"
    assert row["action_type"] == "irrigation.open_valve"
    assert row["field_id"] == field_id
    assert row["state"] == "ready"
    assert row["risk_level"] == "low"
    assert row["required_approvals"] == 1
    assert row["approvals_collected"] == 1
    assert row["exec_status"] == "queued"
    assert row["created_by"] == "system:dispatcher"

    # JSONB تُعاد كنصّ خام من asyncpg (بلا codec) — نفكّها كقوائم/قواميس.
    assert json.loads(row["halt_breaches"]) == halt
    assert json.loads(row["warn_breaches"]) == warn
    assert json.loads(row["command"]) == command


_RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز (NOBYPASSRLS) يُطبَّق عليه RLS


async def test_dispatch_decision_rls_isolation(conn):
    """عزل RLS: صفّ المستأجِر A غير مرئيّ للمستأجِر B — يُقرأ عبر دور **غير ممتاز**.

    حرِج: ``sahool_test`` (مالك الهجرات) **superuser يتجاوز RLS** حتى مع FORCE، فلا
    يكشف العزل. لذا نُنشئ دور تشغيل مقيّداً (NOBYPASSRLS) ونقرأ عبره (SET ROLE) —
    نفس نمط ``test_rls_isolation.py`` والدور الإنتاجيّ ``sahool_app``.
    """
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    tenant_b = ctx["tenant_b"]
    decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    ctx["decision_ids"].append(decision_id)

    # هيّئ الدور المقيّد + صلاحيّاته (idempotent، كـsuperuser).
    await c.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_RLS_ROLE}') THEN
                CREATE ROLE {_RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await c.execute(f"GRANT USAGE ON SCHEMA public TO {_RLS_ROLE}")
    await c.execute(f"GRANT SELECT, INSERT ON dispatch_decisions TO {_RLS_ROLE}")

    # GUC مضبوط للمستأجِر A (من الـfixture) — أدرِج تحته (كـsuperuser للإعداد).
    await c.execute(
        """
        INSERT INTO dispatch_decisions (
            decision_id, tenant_id, recommendation_id, action_type,
            state, risk_level
        ) VALUES ($1, $2, $3, $4, 'pending_approval', 'high')
        """,
        decision_id,
        tenant_a,
        "rec_spray_99",
        "spray.apply",
    )

    try:
        # اقرأ عبر الدور المقيّد (RLS مُطبَّق): تحت المستأجِر A يُرى الصفّ.
        await c.execute(f"SET ROLE {_RLS_ROLE}")
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
        seen_a = await c.fetchval(
            "SELECT count(*) FROM dispatch_decisions WHERE decision_id = $1", decision_id
        )
        assert seen_a == 1, "RLS يحجب المستأجِر عن صفّه"

        # تحت المستأجِر B — يجب ألّا يُرى صفّ A (عزل المستأجرين).
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
        seen_b = await c.fetchval(
            "SELECT count(*) FROM dispatch_decisions WHERE decision_id = $1", decision_id
        )
        assert seen_b == 0, "خرق RLS: صفّ المستأجِر A مرئيّ للمستأجِر B"
    finally:
        await c.execute("RESET ROLE")


async def test_dispatch_decision_queued_partial_index(conn):
    """مسار الفهرس الجزئيّ ``exec_status='queued'`` — يلتقط الأوامر المنتظِرة فقط."""
    c, ctx = conn
    tenant_a = ctx["tenant_a"]
    queued_id = f"dec_{uuid.uuid4().hex[:12]}"
    done_id = f"dec_{uuid.uuid4().hex[:12]}"
    ctx["decision_ids"].extend([queued_id, done_id])

    # صفّ في الطابور (queued) + صفّ منفَّذ (executed) — للتمييز.
    await c.execute(
        """
        INSERT INTO dispatch_decisions (
            decision_id, tenant_id, recommendation_id, action_type,
            state, risk_level, command, exec_status
        ) VALUES ($1, $2, 'rec_q', 'irrigation.open_valve', 'ready', 'low',
                  '{"op": "open"}'::jsonb, 'queued')
        """,
        queued_id,
        tenant_a,
    )
    await c.execute(
        """
        INSERT INTO dispatch_decisions (
            decision_id, tenant_id, recommendation_id, action_type,
            state, risk_level, exec_status
        ) VALUES ($1, $2, 'rec_e', 'irrigation.open_valve', 'ready', 'low', 'executed')
        """,
        done_id,
        tenant_a,
    )

    queued = await c.fetch(
        """
        SELECT decision_id FROM dispatch_decisions
        WHERE exec_status = 'queued' AND decision_id = ANY($1::text[])
        """,
        [queued_id, done_id],
    )
    queued_ids = {r["decision_id"] for r in queued}
    assert queued_id in queued_ids
    assert done_id not in queued_ids
