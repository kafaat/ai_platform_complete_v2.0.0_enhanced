"""v19.5-3 — offline_pending_ops: حالتان نهائيّة/قيد-المعالجة + مطالبة ذرّيّة.

يغطّي شريحة v138 + تغييرات ``offline_pending_db``:
  • عمليّة «سامّة» (poison) تبلغ ``failed`` النهائيّة بعد MAX محاولة — لا تبقى
    ``pending`` إلى الأبد (كان العيب: تدور بلا نهاية).
  • ``claim_pending`` ذرّيّة: المطالبة الأولى تفوز (pending→processing)، والثانية
    تُخفِق (حارس تنفيذ مزدوج).
  • CHECK v138 يقبل الحالتين الجديدتين (processing/failed) ويرفض حالة غير صالحة.
  • عزل RLS: مستأجِر B لا يرى صفّ A (نمط test_db_wiring، دور غير ممتاز).

المنطق النقيّ (``should_fail``) يُختبَر بلا قاعدة (unit) — عتبة الانتقال النهائيّ.

اختبارات القاعدة: ``pytest -m integration`` (تتخطّى تلقائيّاً بلا قاعدة).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)
RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز ليُطبَّق RLS فعلاً (السوبر يتجاوزه)


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _pending_db():
    return _load("services/sahool-platform/api/offline_pending_db.py", "offline_pending_db")


def _make_op(tenant_id: str, user_id: str = "tester"):
    """عمليّة خفيفة (namespace) تكفي ``enqueue_pending`` (يقرأ سماتها فقط)."""
    return types.SimpleNamespace(
        op_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        kind="observation_create",
        payload={"field_id": "f-001", "note": "poison"},
        created_at="2026-06-10T08:00:00",
    )


# ═══════════════════════════════ 1) وحدة نقيّة (بلا قاعدة) ═══════════════════════════════


@pytest.mark.unit
class TestShouldFailPredicate:
    """منطق «هل تنتقل إلى failed؟» — نقيّ، قابل للاختبار بلا I/O."""

    def test_below_limit_stays_retryable(self):
        opdb = _pending_db()
        # attempts=0 قبل الزيادة ⇒ بعدها 1؛ 1 < 5 ⇒ لا فشل نهائيّ
        assert opdb.should_fail(0, max_attempts=5) is False
        assert opdb.should_fail(3, max_attempts=5) is False

    def test_reaches_limit_goes_failed(self):
        opdb = _pending_db()
        # attempts=4 قبل الزيادة ⇒ بعدها 5؛ 5 >= 5 ⇒ فشل نهائيّ
        assert opdb.should_fail(4, max_attempts=5) is True
        assert opdb.should_fail(9, max_attempts=5) is True

    def test_uses_module_default_when_omitted(self):
        opdb = _pending_db()
        m = opdb.MAX_ATTEMPTS
        assert isinstance(m, int) and m > 0
        assert opdb.should_fail(m - 2) is False  # محاولة ما قبل الأخيرة
        assert opdb.should_fail(m - 1) is True  # المحاولة التي تستنفد الحدّ

    def test_degenerate_max_treated_as_one(self):
        opdb = _pending_db()
        # حدّ ≤0 (ضبط خاطئ) ⇒ يُعامَل كـ1 (أوّل فشل نهائيّ) لا حلقة لا نهائيّة
        assert opdb.should_fail(0, max_attempts=0) is True
        assert opdb.should_fail(0, max_attempts=-3) is True


# ═══════════════════════════════ 2) تكامل القاعدة ═══════════════════════════════


async def _connect():
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


@pytest.fixture
async def db():
    try:
        conn = await _connect()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")
    yield conn
    await conn.close()


@pytest.mark.integration
class TestPoisonReachesFailed:
    """عمليّة تفشل دائماً تبلغ failed بعد MAX ولا تبقى pending أبداً."""

    async def test_poison_op_terminates_at_failed(self, db):
        opdb = _pending_db()
        tenant = str(uuid.uuid4())
        op = _make_op(tenant)
        max_attempts = 3  # صغير وحتميّ لهذا الاختبار

        try:
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
            await opdb.enqueue_pending(db, op=op, tenant_id=tenant)

            # دورات عامل متعثّرة: كلّ دورة claim (pending→processing) ثمّ mark_failed.
            # قبل الأخيرة تعود pending؛ الأخيرة تستنفد الحدّ ⇒ failed.
            for cycle in range(max_attempts):
                claimed = await opdb.claim_pending(db, op_id=op.op_id)
                assert claimed is True, f"المطالبة أخفقت في الدورة {cycle}"
                await opdb.mark_failed(
                    db, op_id=op.op_id, error="always fails", max_attempts=max_attempts
                )
                status = await db.fetchval(
                    "SELECT status FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id
                )
                if cycle < max_attempts - 1:
                    assert status == "pending", f"دورة {cycle}: يجب أن تعود pending"
                else:
                    assert status == "failed", "بعد استنفاد المحاولات يجب أن تصبح failed"

            row = await db.fetchrow(
                "SELECT status, attempts, failed_at FROM offline_pending_ops WHERE op_id=$1::uuid",
                op.op_id,
            )
            assert row["status"] == "failed"
            assert row["attempts"] == max_attempts
            assert row["failed_at"] is not None, "failed_at يجب أن يُملأ عند الانتقال النهائيّ"

            # ملموسيّة «لا تدور أبداً»: لم تعد ضمن pending، والمطالبة لا تلتقطها.
            pend = await opdb.fetch_pending(db)
            assert op.op_id not in {r["op_id"] for r in pend}
            assert await opdb.claim_pending(db, op_id=op.op_id) is False
        finally:
            await db.execute("DELETE FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id)


@pytest.mark.integration
class TestClaimAtomicity:
    """claim ذرّيّة: الأولى تفوز، الثانية تُخفِق (حارس تنفيذ مزدوج)."""

    async def test_claim_moves_to_processing_and_blocks_second(self, db):
        opdb = _pending_db()
        tenant = str(uuid.uuid4())
        op = _make_op(tenant)
        try:
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
            await opdb.enqueue_pending(db, op=op, tenant_id=tenant)

            assert await opdb.claim_pending(db, op_id=op.op_id) is True
            status = await db.fetchval(
                "SELECT status FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id
            )
            assert status == "processing"

            # المطالبة الثانية تُخفِق (الصفّ لم يعد pending)
            assert await opdb.claim_pending(db, op_id=op.op_id) is False

            # النجاح يُغلق الدورة: processing→processed
            await opdb.mark_processed(db, op_id=op.op_id)
            status2 = await db.fetchval(
                "SELECT status FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id
            )
            assert status2 == "processed"
        finally:
            await db.execute("DELETE FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id)


@pytest.mark.integration
class TestStatusCheckConstraint:
    """CHECK (v138) يقبل الحالات الأربع ويرفض غيرها."""

    async def test_accepts_new_states_rejects_invalid(self, db):
        import asyncpg

        opdb = _pending_db()
        tenant = str(uuid.uuid4())
        op = _make_op(tenant)
        try:
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
            await opdb.enqueue_pending(db, op=op, tenant_id=tenant)

            # الحالات الجديدة مقبولة
            for st in ("processing", "failed", "processed", "pending"):
                await db.execute(
                    "UPDATE offline_pending_ops SET status=$2 WHERE op_id=$1::uuid",
                    op.op_id,
                    st,
                )
                assert (
                    await db.fetchval(
                        "SELECT status FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id
                    )
                    == st
                )

            # حالة غير صالحة ⇒ CheckViolation
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await db.execute(
                    "UPDATE offline_pending_ops SET status='bogus' WHERE op_id=$1::uuid",
                    op.op_id,
                )
        finally:
            await db.execute("DELETE FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id)


@pytest.mark.integration
class TestRlsIsolationWithNewStates:
    """عزل المستأجِر يبقى قائماً بعد v138 (دور غير ممتاز، RLS فعّال)."""

    async def test_tenant_b_cannot_see_a_failed_op(self, db):
        opdb = _pending_db()
        # دور غير ممتاز يُطبَّق عليه RLS (السوبر/المالك يتجاوز FORCE)
        await db.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{RLS_ROLE}') THEN
                    CREATE ROLE {RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$;
        """)
        await db.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
        await db.execute(f"GRANT SELECT, INSERT, UPDATE ON offline_pending_ops TO {RLS_ROLE}")

        tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
        op = _make_op(tenant_a)
        try:
            await db.execute(f"SET ROLE {RLS_ROLE}")
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)

            await opdb.enqueue_pending(db, op=op, tenant_id=tenant_a)
            # انقلها إلى failed عبر المطالبة+mark_failed (يمرّ بالحالتين الجديدتين تحت RLS)
            assert await opdb.claim_pending(db, op_id=op.op_id) is True
            await opdb.mark_failed(db, op_id=op.op_id, error="x", max_attempts=1)
            seen_a = await db.fetchval(
                "SELECT status FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id
            )
            assert seen_a == "failed", "A لا يرى صفّه بعد النقل — كسر RLS/الحالة"

            # مستأجِر B لا يراه إطلاقاً
            await db.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
            visible_b = await db.fetchval(
                "SELECT COUNT(*) FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id
            )
            assert visible_b == 0, "🚨 تسرّب: B يرى صفّ A (RLS مكسور)"
        finally:
            await db.execute("RESET ROLE")
            await db.execute("DELETE FROM offline_pending_ops WHERE op_id=$1::uuid", op.op_id)
