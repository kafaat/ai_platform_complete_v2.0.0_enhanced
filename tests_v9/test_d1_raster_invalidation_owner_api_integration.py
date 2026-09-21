"""Integration — D1: النيّةُ في معاملة الحقل، والتسليمُ بعد الالتزام، والكتابةُ عبر مالكها — على Postgres حيّ.

يُثبِت على قاعدةٍ حقيقيّة (لا محاكاة):
  • نيّةُ الإبطال (``processing_jobs``، مملوكٌ للمنصّة) تُكتب على اتّصال معاملة الحقل:
    تراجعُ المعاملة يُسقطها، والتزامُها يجعلها دائمة — بلا أيّ HTTP داخل المعاملة.
  • المُوصِّلُ يطالب النيّةَ الملتزَمة بإجارة ويُكمِلها فقط بإقرار المُرسَل إليه؛ وفشلُ
    الإرسال يُعيدها ``pending`` بموعد محاولةٍ لاحق والمفتاحِ نفسِه.
  • على طرف المالك: ``db_persist.enqueue_cache_invalidation`` مرّتان بمفتاح الطلب نفسِه ⇒
    صفٌّ واحد و``deduplicated=True``؛ المفتاحُ نفسُه من مستأجِرٍ آخر يُدرج صفَّه لا
    يطابق صفَّ غيره (الإسنادُ الصريح)؛ والعاملُ يطالب الصفَّ ويُنهيه ``processed``.
  • RLS تُقاس فقط حين يكون دورُ الاتّصال خاضعاً لها (دورُ CI superuser يتجاوزها — يُعلَن).

يتطلّب Postgres+PostGIS بترحيلات MANIFEST مطبَّقة (وظيفة Integration في CI). بلا
قاعدة ⇒ skip نظيف.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_RASTER = _ROOT / "services" / "raster-service"
_PLATFORM = _ROOT / "services" / "sahool-platform"
for _p in (_RASTER, _PLATFORM):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)

pytestmark = pytest.mark.integration


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


async def _connect(tenant_id: str | None = None):
    import asyncpg

    conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
    if tenant_id:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
    return conn


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def test_intent_is_transactional_and_delivered_only_after_commit_with_the_owner_ack():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    from api import spatial_sync
    from api import spatial_sync as dispatch

    tenant_id = str(uuid.uuid4())
    field_id = f"fld_d1_{uuid.uuid4().hex[:8]}"

    async def _run():
        conn = await _connect(tenant_id)
        try:
            # (١) تراجعُ المعاملة يُسقط النيّة معها.
            tx = conn.transaction()
            await tx.start()
            job_id = await spatial_sync.mark_raster_cache_stale(
                conn,
                tenant_id=tenant_id,
                field_id=field_id,
                reason="field.geometry.updated",
                metadata={"geometry_revision": 1},
            )
            assert job_id is not None, "النيّةُ لم تُكتب داخل المعاملة"
            await tx.rollback()
            gone = await conn.fetchval("SELECT count(*) FROM processing_jobs WHERE id=$1", job_id)
            assert gone == 0, "نيّةٌ بقيت بعد تراجع المعاملة"

            # (٢) الالتزامُ يجعلها دائمةً بمفتاحها، والتكرارُ في المعاملة نفسِها لا يُدرج ثانياً.
            async with conn.transaction():
                job_id = await spatial_sync.mark_raster_cache_stale(
                    conn,
                    tenant_id=tenant_id,
                    field_id=field_id,
                    reason="field.geometry.updated",
                    metadata={"geometry_revision": 1},
                )
                again = await spatial_sync.mark_raster_cache_stale(
                    conn,
                    tenant_id=tenant_id,
                    field_id=field_id,
                    reason="field.geometry.updated",
                    metadata={"geometry_revision": 1},
                )
            assert job_id is not None and again == job_id
            row = await conn.fetchrow(
                "SELECT status, job_type, parameters->>'request_id' AS rid "
                "FROM processing_jobs WHERE id=$1",
                job_id,
            )
            assert row["status"] == "pending"
            assert row["job_type"] == spatial_sync.RASTER_INVALIDATION_JOB_TYPE
            assert row["rid"] == f"field.geometry.updated:{field_id}:rev1"

            # (٣) فشلُ التسليم ⇒ pending بموعدٍ لاحق، والمفتاحُ نفسُه في المحاولة التالية.
            sent: list[str] = []

            async def _down(fid, *, tenant_id, reason, request_id, metadata=None, timeout_s=5.0):
                sent.append(request_id)
                raise ConnectionError("raster-service down")

            counts = await dispatch.run_once(_Pool(conn), send=_down)
            assert counts["claimed"] == 1 and counts["retry"] == 1, counts
            row = await conn.fetchrow(
                "SELECT status, result->>'next_attempt_at' AS nxt, result->'lease' AS lease "
                "FROM processing_jobs WHERE id=$1",
                job_id,
            )
            assert row["status"] == "pending" and row["nxt"] is not None and row["lease"] is None
            # لم يحن الموعدُ بعد ⇒ لا مطالبة.
            counts = await dispatch.run_once(_Pool(conn), send=_down)
            assert counts["claimed"] == 0, counts
            await conn.execute(
                "UPDATE processing_jobs SET result = result - 'next_attempt_at' WHERE id=$1", job_id
            )

            # (٤) التسليمُ يكتمل فقط بإقرار المُرسَل إليه، والإقرارُ يُحفَظ.
            async def _ack(fid, *, tenant_id, reason, request_id, metadata=None, timeout_s=5.0):
                sent.append(request_id)
                return {"accepted": True, "deduplicated": False, "invalidation": {"id": 1}}

            counts = await dispatch.run_once(_Pool(conn), send=_ack)
            assert counts["delivered"] == 1, counts
            assert sent == [f"field.geometry.updated:{field_id}:rev1"] * 2
            row = await conn.fetchrow(
                "SELECT status, result->'ack'->>'accepted' AS ok FROM processing_jobs WHERE id=$1",
                job_id,
            )
            assert row["status"] == "completed" and row["ok"] == "true"
            await conn.execute("DELETE FROM processing_jobs WHERE id=$1", job_id)
        finally:
            await conn.close()

    asyncio.run(_run())


def test_owner_side_enqueue_is_idempotent_tenant_scoped_and_consumed_by_the_worker(monkeypatch):
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg
    import cache_invalidation_worker as worker
    import db_persist

    monkeypatch.setattr(db_persist, "DATABASE_URL", _TEST_DB)
    monkeypatch.setenv("DATABASE_URL", _TEST_DB)
    monkeypatch.setenv("RASTER_CACHE_INVALIDATION_ENABLED", "true")
    tenant_id = str(uuid.uuid4())
    other_tenant = str(uuid.uuid4())
    field_id = f"fld_d1_{uuid.uuid4().hex[:8]}"
    request_id = f"field.geometry.updated:{field_id}:rev1"

    async def _run():
        first = await db_persist.enqueue_cache_invalidation(
            tenant_id=tenant_id,
            field_id=field_id,
            reason="field.geometry.updated",
            request_id=request_id,
            metadata={"geometry_revision": 1, "scope": ["tiles"]},
        )
        assert first is not None and first["deduplicated"] is False, first
        assert first["status"] == "pending"
        second = await db_persist.enqueue_cache_invalidation(
            tenant_id=tenant_id,
            field_id=field_id,
            reason="field.geometry.updated",
            request_id=request_id,
            metadata={"geometry_revision": 1, "scope": ["tiles"]},
        )
        assert second is not None and second["deduplicated"] is True, second
        assert second["id"] == first["id"]

        conn = await _connect(tenant_id)
        try:
            n = await conn.fetchval(
                "SELECT count(*) FROM raster_cache_invalidations "
                "WHERE tenant_id=$1::uuid AND field_id=$2",
                tenant_id,
                field_id,
            )
            assert n == 1, f"صفوفٌ مكرَّرة لمفتاح طلبٍ واحد: {n}"
        finally:
            await conn.close()

        # الإسنادُ الصريح للمستأجِر: المفتاحُ نفسُه من مستأجِرٍ آخر يُدرج صفَّه هو.
        foreign = await db_persist.enqueue_cache_invalidation(
            tenant_id=other_tenant,
            field_id=field_id,
            reason="field.geometry.updated",
            request_id=request_id,
            metadata={"geometry_revision": 1},
        )
        assert foreign is not None and foreign["deduplicated"] is False, foreign
        assert foreign["id"] != first["id"]

        conn = await _connect(other_tenant)
        try:
            bypasses = await conn.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
            if not bypasses:
                visible = await conn.fetchval(
                    "SELECT count(*) FROM raster_cache_invalidations "
                    "WHERE field_id=$1 AND tenant_id=$2::uuid",
                    field_id,
                    tenant_id,
                )
                assert visible == 0, "صفُّ الإبطال مرئيٌّ لمستأجِرٍ آخر رغم RLS"
            await conn.execute(
                "DELETE FROM raster_cache_invalidations WHERE tenant_id=$1::uuid AND field_id=$2",
                other_tenant,
                field_id,
            )
        finally:
            await conn.close()

        async def _setup(c):
            await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)

        pool = await asyncpg.create_pool(
            dsn=_TEST_DB, min_size=1, max_size=2, statement_cache_size=0, setup=_setup
        )
        try:
            processed = await worker.run_once(pool)
        finally:
            await pool.close()
        assert processed >= 1, "العامل لم يطالب/يعالج الصفّ المعلّق"

        conn = await _connect(tenant_id)
        try:
            row = await conn.fetchrow(
                "SELECT status, processed_at FROM raster_cache_invalidations WHERE id=$1",
                first["id"],
            )
            assert row["status"] == "processed" and row["processed_at"] is not None
            await conn.execute(
                "DELETE FROM raster_cache_invalidations WHERE tenant_id=$1::uuid AND field_id=$2",
                tenant_id,
                field_id,
            )
        finally:
            await conn.close()

    asyncio.run(_run())
