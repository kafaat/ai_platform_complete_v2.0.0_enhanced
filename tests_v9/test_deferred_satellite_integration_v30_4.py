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
