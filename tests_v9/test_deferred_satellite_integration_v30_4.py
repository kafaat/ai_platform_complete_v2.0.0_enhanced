"""Integration — تفعيل «المؤجَّل» على Postgres+PostGIS حيّ (تدقيقات الأقمار v2/v3).

يُثبِت على قاعدة حقيقيّة (لا محاكاة) أنّ عمل هذه الجلسة يدور فعلاً:
  • v143: asset_status + geometry_revision يُكتبان ويُقرآن، والقرّاء يستبعدون 'failed'.
  • v3-F1: list_available_asset_dates تحدّ بالتواريخ المميَّزة لا الصفوف (لا بتر).
  • v3-F3: fetch_latest_asset ينتقي الأفضل جودةً لأحدث تاريخ.
  • FINDING-008/009: جسر raster_registry + stac_item_registry يكتبان صفوفاً قابلة للقراءة.
  • FINDING-005: عامل الإبطال يطالب صفّاً معلّقاً ⇒ يعلّم الأصل stale ويُنهي الصفّ processed.

يتطلّب Postgres+PostGIS بترحيلات v14..v143 مطبَّقة (وظيفة Integration في CI). بلا
قاعدة ⇒ skip نظيف. الدور sahool_test خاضع لـRLS، فنضبط app.current_tenant حيث يلزم
(في الإنتاج دور JOBS بـBYPASSRLS يغني العامل عن ذلك عبر المستأجرين).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

_RASTER = Path(__file__).resolve().parent.parent / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

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


def _footprint():
    return {
        "type": "Polygon",
        "coordinates": [
            [[44.30, 16.78], [44.36, 16.78], [44.36, 16.81], [44.30, 16.81], [44.30, 16.78]]
        ],
    }


async def _connect(tenant_id: str | None = None):
    import asyncpg

    conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
    if tenant_id:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
    return conn


async def _cleanup(tenant_id: str, field_id: str, scene_id: str | None = None):
    conn = await _connect(tenant_id)
    try:
        await conn.execute("DELETE FROM raster_assets WHERE field_id = $1", field_id)
        await conn.execute("DELETE FROM raster_registry WHERE field_id = $1", field_id)
        await conn.execute("DELETE FROM raster_cache_invalidations WHERE field_id = $1", field_id)
        await conn.execute("DELETE FROM backfill_run_items WHERE field_id = $1", field_id)
        await conn.execute("DELETE FROM backfill_runs WHERE field_id = $1", field_id)
        if scene_id:
            await conn.execute("DELETE FROM stac_item_registry WHERE scene_id = $1", scene_id)
    finally:
        await conn.close()


# ─── v143: asset_status + geometry_revision + readers exclude failed ──────────


def test_v143_asset_status_and_geometry_revision_round_trip():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    async def _run():
        ok = await db_persist.insert_raster_asset(
            field_id=field_id,
            tenant_id=tenant_id,
            scene_id="s-v143",
            acquisition_date="2026-06-01",
            satellite="sentinel-2",
            index_name="ndvi",
            cloud_pct=10.0,
            srid=4326,
            cog_uri="file:///tmp/v143.tif",
            bands=None,
            nodata=-9999.0,
            footprint=_footprint(),
            provenance={"stats": {"confidence": 0.8, "quality": "high"}},
            quality_score=0.8,
            aoi_cloud_pct=10.0,
            cloud_mask_sources=["SCL"],
            geometry_revision=3,
            asset_status="ready",
        )
        assert ok, "الإدراج فشل — تحقّق من الترحيلات v14..v143"

        conn = await _connect(tenant_id)
        try:
            row = await conn.fetchrow(
                "SELECT asset_status, geometry_revision, quality_score, aoi_cloud_pct "
                "FROM raster_assets WHERE field_id=$1 AND tenant_id=$2::uuid",
                field_id,
                tenant_id,
            )
            assert row["asset_status"] == "ready"
            assert row["geometry_revision"] == 3
            assert float(row["quality_score"]) == pytest.approx(0.8)
            assert float(row["aoi_cloud_pct"]) == pytest.approx(10.0)
            # علّم الأصل فاشلاً ⇒ يجب أن يستبعده القارئ.
            await conn.execute(
                "UPDATE raster_assets SET asset_status='failed' WHERE field_id=$1", field_id
            )
        finally:
            await conn.close()

        asset = await db_persist.fetch_latest_asset(
            field_id, "ndvi", date=None, tenant_id=tenant_id
        )
        assert asset is None, "القارئ يجب أن يستبعد asset_status='failed'"
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())


# ─── v3-F1: distinct-date limit (لا بتر) ──────────────────────────────────────


def test_available_dates_limits_distinct_dates_not_rows():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    dates = ["2026-06-01", "2026-06-06", "2026-06-11"]

    async def _run():
        # 3 تواريخ × مؤشّرَين = 6 صفوف.
        for i, d in enumerate(dates):
            for idx in ("ndvi", "ndmi"):
                await db_persist.insert_raster_asset(
                    field_id=field_id,
                    tenant_id=tenant_id,
                    scene_id=f"s-{d}-{idx}",
                    acquisition_date=d,
                    satellite="sentinel-2",
                    index_name=idx,
                    cloud_pct=float(i),
                    srid=4326,
                    cog_uri=f"file:///tmp/{d}_{idx}.tif",
                    bands=None,
                    nodata=-9999.0,
                    footprint=_footprint(),
                    provenance=None,
                    quality_score=0.7,
                )
        # الحدّ على التواريخ المميَّزة: limit=2 ⇒ تاريخان (لا صفّان = تاريخ واحد كما كان الخلل).
        rows = await db_persist.list_available_asset_dates(field_id, tenant_id=tenant_id, limit=2)
        distinct = {r["date"][:10] for r in rows}
        assert len(distinct) == 2, f"الحدّ يقع على الصفوف لا التواريخ المميَّزة: {sorted(distinct)}"
        assert distinct == {"2026-06-11", "2026-06-06"}, "يجب إبقاء أحدث تاريخَين مميَّزَين"
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())


# ─── v3-F3: quality-aware latest pick ─────────────────────────────────────────


def test_fetch_latest_asset_prefers_higher_quality_same_date():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    async def _run():
        # نفس أحدث تاريخ، صفّان بجودتَين مختلفتَين (scene/cog مختلفان ⇒ لا تصادم الفهرس الفريد).
        for scene, cog, q, cloud in (
            ("s-bad", "file:///tmp/bad.tif", 0.30, 60.0),
            ("s-good", "file:///tmp/good.tif", 0.90, 5.0),
        ):
            await db_persist.insert_raster_asset(
                field_id=field_id,
                tenant_id=tenant_id,
                scene_id=scene,
                acquisition_date="2026-06-20",
                satellite="sentinel-2",
                index_name="ndvi",
                cloud_pct=cloud,
                srid=4326,
                cog_uri=cog,
                bands=None,
                nodata=-9999.0,
                footprint=_footprint(),
                provenance=None,
                quality_score=q,
            )
        asset = await db_persist.fetch_latest_asset(
            field_id, "ndvi", date=None, tenant_id=tenant_id
        )
        assert asset is not None
        assert asset["cog_url"] == "file:///tmp/good.tif", (
            "لأحدث تاريخ يجب انتقاء الأعلى جودةً (quality_score) لا الأقلّ"
        )
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())


# ─── FINDING-008/009: catalog bridge round-trips ──────────────────────────────


def test_raster_registry_bridge_round_trip():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    async def _run():
        ok = await db_persist.insert_raster_registry_entry(
            tenant_id=tenant_id,
            field_id=field_id,
            scene_id="s-reg",
            product_date="2026-06-01",
            index_type="ndvi",
            cog_url="s3://bucket/ndvi.tif",
            cloud_pct=7.0,
            quality_score=0.85,  # 0..1 ⇒ يُقصَر إلى 85
            resolution_m=10.0,
            bbox=[44.30, 16.78, 44.36, 16.81],
            bands={"red": "B04", "nir": "B08"},
            metadata={"provider": "cdse"},
        )
        assert ok, "جسر raster_registry فشل — تحقّق من v114 وRLS"

        conn = await _connect(tenant_id)
        try:
            row = await conn.fetchrow(
                "SELECT index_type, cog_url, quality_score, cloud_pct "
                "FROM raster_registry WHERE field_id=$1 AND tenant_id=$2::uuid",
                field_id,
                tenant_id,
            )
            assert row is not None, "الكتالوج فارغ — الجسر لم يكتب"
            assert row["index_type"] == "ndvi"
            assert row["cog_url"] == "s3://bucket/ndvi.tif"
            assert row["quality_score"] == 85, "0..1 يجب أن يُقصَر إلى 0..100 (85)"
        finally:
            await conn.close()
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())


def test_stac_item_persistence_round_trip():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    tenant_id = str(uuid.uuid4())
    scene_id = f"S2_{uuid.uuid4().hex[:10]}"
    field_id = str(uuid.uuid4())  # للتنظيف فقط

    async def _run():
        ok = await db_persist.insert_stac_item(
            tenant_id=tenant_id,
            scene_id=scene_id,
            collection="sentinel-2-l2a",
            captured_at="2026-06-01T09:30:00Z",
            bbox=[44.30, 16.78, 44.36, 16.81],
            cloud_pct=12.0,
            quality_score=0.7,  # ⇒ 70
            assets={"bands": {"red": "url"}},
            raw_item={"id": scene_id, "cloud": 12.0},
        )
        assert ok, "استمرار stac_item_registry فشل — تحقّق من v114 وRLS"

        conn = await _connect(tenant_id)
        try:
            row = await conn.fetchrow(
                "SELECT collection, quality_score, cloud_pct "
                "FROM stac_item_registry WHERE scene_id=$1 AND tenant_id=$2::uuid",
                scene_id,
                tenant_id,
            )
            assert row is not None, "الجدول فارغ — الكاتب لم يعمل"
            assert row["collection"] == "sentinel-2-l2a"
            assert row["quality_score"] == 70
        finally:
            await conn.close()
        await _cleanup(tenant_id, field_id, scene_id=scene_id)

    asyncio.run(_run())


# ─── FINDING-005: invalidation worker consumes the queue ──────────────────────


def test_cache_invalidation_worker_marks_stale_and_processed():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import importlib.util

    import asyncpg
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    # حمّل العامل باسم فريد.
    spec = importlib.util.spec_from_file_location(
        "cache_invalidation_worker_it", _RASTER / "cache_invalidation_worker.py"
    )
    worker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker)

    async def _run():
        # (1) أصل جاهز + صفّ إبطال معلّق.
        await db_persist.insert_raster_asset(
            field_id=field_id,
            tenant_id=tenant_id,
            scene_id="s-inval",
            acquisition_date="2026-06-01",
            satellite="sentinel-2",
            index_name="ndvi",
            cloud_pct=10.0,
            srid=4326,
            cog_uri="file:///tmp/inval.tif",
            bands=None,
            nodata=-9999.0,
            footprint=_footprint(),
            provenance=None,
            quality_score=0.8,
            asset_status="ready",
        )
        conn = await _connect(tenant_id)
        try:
            await conn.execute(
                "INSERT INTO raster_cache_invalidations (tenant_id, field_id, reason) "
                "VALUES ($1::uuid, $2, 'geometry.updated')",
                tenant_id,
                field_id,
            )
        finally:
            await conn.close()

        # (2) شغّل العامل على قاعدة حيّة. الدور sahool_test خاضع لـRLS، فنضبط المستأجِر
        # عبر pool.setup كي ترى المطالبة الصفّ (في الإنتاج دور JOBS بـBYPASSRLS يغني عن ذلك).
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

        # (3) الأصل صار stale + صفّ الإبطال صار processed مع processed_at.
        conn = await _connect(tenant_id)
        try:
            st = await conn.fetchval(
                "SELECT asset_status FROM raster_assets WHERE field_id=$1 AND tenant_id=$2::uuid",
                field_id,
                tenant_id,
            )
            assert st == "stale", f"الأصل لم يُعلَّم stale (={st})"
            inv = await conn.fetchrow(
                "SELECT status, processed_at FROM raster_cache_invalidations "
                "WHERE field_id=$1 AND tenant_id=$2::uuid",
                field_id,
                tenant_id,
            )
            assert inv["status"] == "processed", f"صفّ الإبطال لم يُنهَ (={inv['status']})"
            assert inv["processed_at"] is not None
        finally:
            await conn.close()
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())


# ─── C1: صفٌّ مُطالَبٌ لا يعلق في processing بعد موت العامل (إجارةٌ + استعادة) ──────────
#
# كانت المطالبةُ تلتزم ``status='processing'`` قبل العمل، والاستطلاعُ يختار ``pending`` وحده:
# عاملٌ مات بين الالتزام والإبطال يترك الصفَّ خارج كلّ دورةٍ لاحقة إلى الأبد — فلا يُحذف كاشُ
# الحقل ولا تُوسَم أصولُه. الشاهدُ هنا على القاعدة الحقيقيّة (``FOR UPDATE SKIP LOCKED``
# وصبُّ ``jsonb`` المحروسُ بالنوع كما ينفّذهما PG فعلاً، لا وهميّ).


def _load_invalidation_worker(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, _RASTER / "cache_invalidation_worker.py")
    worker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(worker)
    return worker


async def _worker_pool(tenant_id: str):
    import asyncpg

    async def _setup(c):
        await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)

    return await asyncpg.create_pool(
        dsn=_TEST_DB, min_size=1, max_size=2, statement_cache_size=0, setup=_setup
    )


async def _queue_row(
    tenant_id: str, field_id: str, metadata: str = "{}", status: str = "pending"
) -> int:
    """``metadata`` نصُّ JSON يُصَبّ في القاعدة — كي يحمل ما لا يُنتجه ``json.dumps`` (1e400)."""
    conn = await _connect(tenant_id)
    try:
        return await conn.fetchval(
            "INSERT INTO raster_cache_invalidations (tenant_id, field_id, reason, metadata, status) "
            "VALUES ($1::uuid, $2, 'geometry.updated', $3::jsonb, $4) RETURNING id",
            tenant_id,
            field_id,
            metadata,
            status,
        )
    finally:
        await conn.close()


async def _queue_state(tenant_id: str, rid: int):
    conn = await _connect(tenant_id)
    try:
        row = await conn.fetchrow(
            "SELECT status, processed_at, metadata::text AS metadata, "
            "CASE WHEN jsonb_typeof(metadata->'retry_after') = 'number' "
            "THEN (metadata->>'retry_after')::numeric > extract(epoch from now()) "
            "END AS backoff_live "
            "FROM raster_cache_invalidations WHERE id=$1",
            rid,
        )
        return row["status"], row["processed_at"], json.loads(row["metadata"]), row["backoff_live"]
    finally:
        await conn.close()


async def _drop_queue_rows(tenant_id: str, field_id: str) -> None:
    conn = await _connect(tenant_id)
    try:
        await conn.execute(
            "DELETE FROM raster_cache_invalidations WHERE tenant_id=$1::uuid AND field_id=$2",
            tenant_id,
            field_id,
        )
    finally:
        await conn.close()


class _WorkerDied(BaseException):
    """موتُ العمليّة بعد التزام المطالبة: ``BaseException`` يتجاوز ``except Exception``."""


def test_cache_invalidation_claim_is_reclaimed_after_the_worker_dies(monkeypatch):
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    monkeypatch.delenv("REDIS_URL", raising=False)
    worker = _load_invalidation_worker("cache_invalidation_worker_c1_it")
    tenant_id = str(uuid.uuid4())
    field_id = f"fld_c1_{uuid.uuid4().hex[:8]}"

    def _die_on_our_field(tenant, field):
        if field == field_id:
            raise _WorkerDied()
        return 0

    async def _run():
        rid = await _queue_row(tenant_id, field_id)
        try:
            monkeypatch.setattr(
                worker.tile_cache_maint, "invalidate_field_tile_cache", _die_on_our_field
            )
            pool = await _worker_pool(tenant_id)
            try:
                with pytest.raises(_WorkerDied):
                    await worker.run_once(pool)
            finally:
                pool.terminate()
            status, processed_at, meta, _ = await _queue_state(tenant_id, rid)
            assert status == "processing" and processed_at is None, (status, processed_at)

            # الإجارةُ حيّة ⇒ لا يسرقها عاملٌ آخر (لعلّ صاحبها ما زال يعمل).
            monkeypatch.setattr(
                worker.tile_cache_maint, "invalidate_field_tile_cache", lambda t, f: 0
            )
            pool = await _worker_pool(tenant_id)
            try:
                await worker.run_once(pool)
            finally:
                await pool.close()
            status, _, _, _ = await _queue_state(tenant_id, rid)
            assert status == "processing", f"إجارةٌ حيّة سُرقت (={status})"

            # انقضت الإجارة (صاحبُها مات) ⇒ الصفُّ يُستعاد ويُنجَز، لا يعلق إلى الأبد.
            conn = await _connect(tenant_id)
            try:
                await conn.execute(
                    "UPDATE raster_cache_invalidations SET metadata = metadata || "
                    "jsonb_build_object('lease_until', extract(epoch from now()) - 1) WHERE id=$1",
                    rid,
                )
            finally:
                await conn.close()
            pool = await _worker_pool(tenant_id)
            try:
                processed = await worker.run_once(pool)
            finally:
                await pool.close()
            status, processed_at, meta, _ = await _queue_state(tenant_id, rid)
            assert status == "processed" and processed_at is not None, (
                f"صفٌّ ماتت مطالبتُه لم يُستعَد (={status}) — عالقٌ في processing إلى الأبد"
            )
            assert processed >= 1
            assert meta.get("claim_attempts") == 2, meta
            assert "lease_until" not in meta, meta
        finally:
            await _drop_queue_rows(tenant_id, field_id)

    asyncio.run(_run())


# ─── P3-INV: إخلاءُ الذاكرة الذي لم يُسلَّم لا يُعَدّ نجاحاً — يُعاد ثمّ يُسجَّل ─────────────


def test_cache_invalidation_undelivered_layer_evict_is_retried_not_counted(monkeypatch):
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    # Redis مُهيّأ لكنّه لا يُبلَغ: المنفذ 1 يرفض الاتّصال فوراً.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    worker = _load_invalidation_worker("cache_invalidation_worker_p3inv_it")
    monkeypatch.setattr(worker.tile_cache_maint, "invalidate_field_tile_cache", lambda t, f: 0)
    tenant_id = str(uuid.uuid4())
    field_id = f"fld_p3_{uuid.uuid4().hex[:8]}"

    async def _once() -> int:
        pool = await _worker_pool(tenant_id)
        try:
            return await worker.run_once(pool)
        finally:
            await pool.close()

    async def _run():
        rid = await _queue_row(tenant_id, field_id)
        try:
            await _once()
            status, processed_at, meta, backoff_live = await _queue_state(tenant_id, rid)
            assert status == "pending" and processed_at is None, (
                f"إبطالٌ لم يُسلَّم إخلاؤه عُدَّ منجَزاً (={status}) — عمليّةُ الخدمة تُبقي الطبقة القديمة"
            )
            assert meta.get("layer_evict") == "not_delivered", meta
            assert backoff_live is True, meta

            # المهلةُ حيّة ⇒ لا إعادةَ فوريّة تُحرق المحاولات.
            await _once()
            status, _, _, _ = await _queue_state(tenant_id, rid)
            assert status == "pending"

            # انقضت المهلة وعاد Redis ⇒ يُعاد الإبطالُ ويُسلَّم ويُنجَز.
            conn = await _connect(tenant_id)
            try:
                await conn.execute(
                    "UPDATE raster_cache_invalidations SET metadata = metadata || "
                    "jsonb_build_object('retry_after', extract(epoch from now()) - 1) WHERE id=$1",
                    rid,
                )
            finally:
                await conn.close()

            class _Pub:
                async def publish(self, channel, message):
                    return 1

            worker._redis_pub = _Pub()
            await _once()
            status, processed_at, meta, _ = await _queue_state(tenant_id, rid)
            assert status == "processed" and processed_at is not None, status
            assert meta.get("layer_evict") == "delivered", meta
            assert meta.get("claim_attempts") == 2, meta
        finally:
            await _drop_queue_rows(tenant_id, field_id)

    asyncio.run(_run())


# ─── C1 (مراجعة): قيمةٌ مُدخَلة غيرُ صالحة في مفاتيح العامل لا توقف الطابور للجميع ──────
#
# ``metadata`` يملؤه المُستدعي، وعبارةُ المطالبة دفعيّةٌ لكلّ المستأجِرين. كان الصبُّ
# ``(metadata->>'retry_after')::timestamptz`` و``(metadata->>'claim_attempts')::int`` يرمي على
# ``'x'``/``2.5`` فتُلغى المطالبةُ كلَّ دورة: لا صفَّ يُبطَل لأحد، والنبضةُ ``failed`` فتُعاد الحاوية
# بلا نهاية. الإدراجُ صار يُسقط هذه المفاتيح، لكنّ صفّاً قائماً (أو كاتباً آخر) يبقى ممكناً —
# فالشاهدُ يُدرج مباشرةً متجاوزاً الإدراج.


def test_cache_invalidation_malformed_worker_keys_do_not_poison_the_claim(monkeypatch):
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    monkeypatch.delenv("REDIS_URL", raising=False)
    worker = _load_invalidation_worker("cache_invalidation_worker_c1_poison_it")
    monkeypatch.setattr(worker.tile_cache_maint, "invalidate_field_tile_cache", lambda t, f: 0)
    tenant_id = str(uuid.uuid4())
    field_id = f"fld_c1p_{uuid.uuid4().hex[:8]}"
    queued = [
        ('{"claim_attempts": 2.5, "retry_after": "x"}', "pending"),
        ('{"claim_attempts": 1e400, "retry_after": "2999-13-45"}', "pending"),
        ('{"claim_attempts": "3", "lease_until": "not-a-time"}', "processing"),
        ('{"geometry_revision": 1}', "pending"),
    ]

    async def _run():
        ids = [await _queue_row(tenant_id, field_id, m, s) for m, s in queued]
        try:
            pool = await _worker_pool(tenant_id)
            try:
                processed = await worker.run_once(pool, batch_size=1000)
            finally:
                await pool.close()
            assert processed >= len(ids), processed
            for rid in ids:
                status, processed_at, meta, _ = await _queue_state(tenant_id, rid)
                assert status == "processed" and processed_at is not None, (
                    f"صفٌّ بقيمٍ مُدخَلة غيرِ صالحة لم يُعالَج (={status}) — {meta}"
                )
                # القيمةُ غيرُ الصالحة تُقرأ غائبةً في بايثون وSQL معاً ⇒ المحاولةُ الأولى.
                assert meta.get("claim_attempts") == 1, meta
                assert "retry_after" not in meta and "lease_until" not in meta, meta
        finally:
            await _drop_queue_rows(tenant_id, field_id)

    asyncio.run(_run())


# ─── v144: backfill_runs creation + run_items idempotency (live DB) ────────────


def test_insert_backfill_run_creates_planned_run():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    async def _run():
        run_id = await db_persist.insert_backfill_run(
            tenant_id=tenant_id,
            field_id=field_id,
            preset="last_2_years",
            from_date="2024-06-01",
            to_date="2026-06-01",
            months=24,
            indices=["ndvi", "ndmi"],
            max_cloud_pct=30.0,
            geometry_revision=2,
            clip_polygon_geojson={
                "type": "Polygon",
                "coordinates": [[[44.3, 16.78], [44.36, 16.78], [44.36, 16.81], [44.3, 16.78]]],
            },
            apply_cloud_mask=True,
            limit_per_month=2,
        )
        assert run_id is not None, "إنشاء التشغيلة فشل — تحقّق من v144 وRLS"
        conn = await _connect(tenant_id)
        try:
            row = await conn.fetchrow(
                "SELECT status, months, geometry_revision, indices::text AS idx "
                "FROM backfill_runs WHERE id=$1 AND tenant_id=$2::uuid",
                run_id,
                tenant_id,
            )
            assert row["status"] == "planned", "التشغيلة يجب أن تبدأ planned (الردّ الفوريّ)"
            assert row["months"] == 24
            assert row["geometry_revision"] == 2
            assert "ndvi" in row["idx"] and "ndmi" in row["idx"]
        finally:
            await conn.close()
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())


def test_backfill_run_items_idempotency_key_dedups():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")
    import db_persist

    db_persist.DATABASE_URL = _TEST_DB
    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    async def _run():
        run_id = await db_persist.insert_backfill_run(
            tenant_id=tenant_id,
            field_id=field_id,
            preset="custom",
            from_date="2026-06-01",
            to_date="2026-06-30",
            months=1,
            indices=["ndvi"],
            max_cloud_pct=30.0,
            clip_polygon_geojson={
                "type": "Polygon",
                "coordinates": [[[44.3, 16.78], [44.36, 16.78], [44.36, 16.81], [44.3, 16.78]]],
            },
        )
        assert run_id is not None
        key = f"{tenant_id}:{field_id}:0:element84:S2_scene:ndvi"
        conn = await _connect(tenant_id)
        try:
            insert_sql = (
                "INSERT INTO backfill_run_items (run_id, tenant_id, field_id, scene_id, "
                "index_name, provider, idempotency_key, status) VALUES "
                "($1, $2::uuid, $3, 'S2_scene', 'ndvi', 'element84', $4, 'queued') "
                "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING id"
            )
            first = await conn.fetchval(insert_sql, run_id, tenant_id, field_id, key)
            second = await conn.fetchval(insert_sql, run_id, tenant_id, field_id, key)
            assert first is not None, "الإدراج الأوّل يجب أن ينجح"
            assert second is None, "مفتاح idempotency المكرّر يجب أن يُهمَل (لا تكرار)"
        finally:
            await conn.close()
        await _cleanup(tenant_id, field_id)

    asyncio.run(_run())
