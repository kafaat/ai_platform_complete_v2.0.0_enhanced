"""تحقّق V19.5-4 — سجلّ المحاولات الجنائيّ لِـoutbox (outbox_delivery_attempts / v140).

المشكلة: event_outbox (v11) يحتفظ بحالة تسليم **مُجمَّعة فقط** (retry_count + last_error
واحد) — بعد المحاولة #3 يُدهَس خطأ #2. v140 يضيف جدولاً ملحقاً append-only صفّ لكلّ محاولة
يصونه OutboxWorker._send_one.

طبقتان:
- حُرّاس مصدر/هجرة (pure، `unit`) — يعملان في وظيفة *Unit Tests* (بلا fastapi/DB):
  يثبتان أنّ الجدول مُعرَّف في v140 ومُسجَّل، وأنّ العامل يُدرِج فيه (assert على نصّ).
- تكامل asyncpg نقيّ (`integration`) — يتطلّب Postgres؛ يتخطّى إن لا DB: محاولتان
  فاشلتان تُبقيان صفّين بأرقام محاولة متمايزة ونصوص خطأ محفوظة؛ نجاح يُلحِق صفّ
  outcome='published'؛ append-only يمنع UPDATE/DELETE سلوكيّاً.

يعمل: `pytest -m unit` (الحُرّاس) أو `pytest -m integration` (التكامل، يتخطّى إن لا Postgres).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ══ 1. حُرّاس مصدر/هجرة (pure، بلا fastapi/DB — تعمل في وظيفة Unit Tests) ══


@pytest.mark.unit
def test_v140_migration_defines_append_only_attempts_table():
    sql = _read("migrations/v140_outbox_delivery_attempts.sql")
    assert "CREATE TABLE IF NOT EXISTS outbox_delivery_attempts" in sql
    # يُلحَق بالجدول الحيّ event_outbox (v11)، لا runtime_event_outbox (v106).
    assert "REFERENCES event_outbox(outbox_id)" in sql
    for col in ("attempt_no", "attempted_at", "subject", "outcome", "error", "tenant_id"):
        assert col in sql, f"عمود مفقود في v140: {col}"
    # append-only عبر sahool_block_mutation (نمط v9/mfa_audit_events).
    assert "sahool_block_mutation" in sql
    assert "BEFORE UPDATE OR DELETE ON outbox_delivery_attempts" in sql
    # فهرس (outbox_id, attempt_no).
    assert "idx_outbox_delivery_attempts_outbox" in sql


@pytest.mark.unit
def test_v140_registered_in_manifest_and_runner():
    manifest = _read("migrations/MANIFEST.txt")
    assert "v140_outbox_delivery_attempts.sql" in manifest
    runner = _read("scripts_v9/run_migrations.sql")
    assert "migrations/v140_outbox_delivery_attempts.sql" in runner


@pytest.mark.unit
def test_worker_records_each_delivery_attempt():
    """العامل يُلحِق صفّ محاولة في كلّ مسار (نجاح/تخطٍّ/فشل) — حارس انحدار على المصدر."""
    src = _read("services/sahool-platform/api/event_bus.py")
    assert "INSERT INTO outbox_delivery_attempts" in src
    assert "_record_delivery_attempt" in src
    # النتائج الثلاث مُغطّاة.
    for outcome in ('outcome="published"', 'outcome="skipped"', 'outcome="failed"'):
        assert outcome in src, f"مسار نتيجة غير مُسجَّل: {outcome}"


# ══ 2. تكامل asyncpg نقيّ (Postgres حقيقيّ — يتخطّى إن لا DB) ══


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


def _make_worker(publish_fn):
    import sys

    platform = os.path.join(ROOT, "services", "sahool-platform")
    if platform not in sys.path:
        sys.path.insert(0, platform)
    from api.event_bus import OutboxWorker

    return OutboxWorker(pool=None, nats_publish_fn=publish_fn, max_retries=5)


async def _seed_outbox_row(conn, tenant_id: str) -> uuid.UUID:
    """يُنشئ event + صفّ event_outbox عبر emit_event (ذرّيّ) ويُرجع event_id."""
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
    event_id = await conn.fetchval(
        """
        SELECT emit_event(
            'field.created', 'field', $1::uuid, $2::uuid,
            '{"k": "v"}'::jsonb, 'system'
        )
        """,
        str(uuid.uuid4()),
        tenant_id,
    )
    return event_id


async def _fetch_worker_row(conn, event_id) -> dict:
    """يبني dict الصفّ الذي يتوقّعه _send_one من event_outbox + events."""
    r = await conn.fetchrow(
        """
        SELECT o.outbox_id, o.event_id, o.nats_subject, o.retry_count,
               e.event_type, e.entity_type, e.entity_id, e.tenant_id,
               e.payload, e.occurred_at
        FROM event_outbox o JOIN events e ON e.event_id = o.event_id
        WHERE o.event_id = $1
        """,
        event_id,
    )
    return dict(r)


@pytest.mark.integration
def test_attempts_logged_per_delivery_with_distinct_errors_and_success():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg

    tenant_id = str(uuid.uuid4())

    async def _run():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            event_id = await _seed_outbox_row(conn, tenant_id)
            assert event_id is not None
            row = await _fetch_worker_row(conn, event_id)
            outbox_id = row["outbox_id"]

            # ── محاولة #1: فشل بخطأ متمايز ──
            async def _fail_a(subject, payload):
                raise RuntimeError("NATS_DOWN_ALPHA")

            worker = _make_worker(_fail_a)
            await worker._send_one(conn, row)

            # ── محاولة #2: أعِد بناء الصفّ (retry_count=1 الآن) + خطأ متمايز آخر ──
            row2 = await _fetch_worker_row(conn, event_id)
            assert row2["retry_count"] == 1

            async def _fail_b(subject, payload):
                raise ValueError("BROKER_TIMEOUT_BETA")

            worker.publish = _fail_b
            await worker._send_one(conn, row2)

            # ── صفّان بمحاولتين متمايزتين + كلا نصّي الخطأ محفوظان (لا دهس) ──
            attempts = await conn.fetch(
                """
                SELECT attempt_no, outcome, error, tenant_id
                FROM outbox_delivery_attempts
                WHERE outbox_id = $1
                ORDER BY attempt_no
                """,
                outbox_id,
            )
            assert len(attempts) == 2, "يجب صفّ محاولة لكلّ تسليم"
            assert [a["attempt_no"] for a in attempts] == [1, 2], "أرقام محاولة متمايزة"
            assert all(a["outcome"] == "failed" for a in attempts)
            joined = " | ".join(a["error"] or "" for a in attempts)
            assert "NATS_DOWN_ALPHA" in joined, "خطأ المحاولة #1 دُهِس (فُقد)"
            assert "BROKER_TIMEOUT_BETA" in joined, "خطأ المحاولة #2 غير محفوظ"
            # tenant_id إعلاميّ محفوظ (forensic).
            assert all(str(a["tenant_id"]) == tenant_id for a in attempts)

            # ── محاولة #3: نجاح ⇒ صفّ outcome='published' ──
            row3 = await _fetch_worker_row(conn, event_id)
            assert row3["retry_count"] == 2

            async def _ok(subject, payload):
                return None

            worker.publish = _ok
            await worker._send_one(conn, row3)

            pub = await conn.fetch(
                """
                SELECT attempt_no, outcome FROM outbox_delivery_attempts
                WHERE outbox_id = $1 AND outcome = 'published'
                """,
                outbox_id,
            )
            assert len(pub) == 1, "نجاح التسليم يُلحِق صفّ published"
            assert pub[0]["attempt_no"] == 3
            # الصفّ الأصليّ وُسِم 'sent' (السلوك المُجمَّع لم يتغيّر).
            status = await conn.fetchval(
                "SELECT status FROM event_outbox WHERE outbox_id = $1", outbox_id
            )
            assert status == "sent"
        finally:
            await conn.close()

    asyncio.run(_run())


@pytest.mark.integration
def test_attempts_table_is_append_only():
    """append-only سلوكيّاً: UPDATE/DELETE محظوران (probe داخل tx مُلغى، لا يلوّث)."""
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg

    tenant_id = str(uuid.uuid4())

    async def _run():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            event_id = await _seed_outbox_row(conn, tenant_id)
            row = await _fetch_worker_row(conn, event_id)
            outbox_id = row["outbox_id"]

            async def _fail(subject, payload):
                raise RuntimeError("boom")

            worker = _make_worker(_fail)
            await worker._send_one(conn, row)  # يُلحِق صفّ محاولة واحداً

            for stmt in (
                "UPDATE outbox_delivery_attempts SET error = 'tampered' WHERE outbox_id = $1",
                "DELETE FROM outbox_delivery_attempts WHERE outbox_id = $1",
            ):
                blocked = False
                tx = conn.transaction()
                await tx.start()
                try:
                    await conn.execute(stmt, outbox_id)
                except asyncpg.PostgresError:
                    blocked = True
                finally:
                    await tx.rollback()
                assert blocked, f"append-only لم يمنع: {stmt.split()[0]}"
        finally:
            await conn.close()

    asyncio.run(_run())
