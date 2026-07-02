"""Integration — أعمدة جودة الصور v131 تُكتب وتُقرأ فعليّاً (v62.3-B).

يكمّل الحارس الساكن في ``test_imagery_quality_metadata_v57_5.py``: هذا يثبت أنّ
الكاتب (``db_persist.insert_raster_asset``) والقارئ (``fetch_latest_asset``) يدوّران
valid_pixel_ratio/coverage_ratio/index_quality_flags عبر Postgres حقيقيّ، وأنّ قيد
``chk_raster_quality_ratios`` يرفض النسب خارج [0,1].

يتطلّب Postgres+PostGIS مع ترحيلات v14+v131 مطبَّقة (وظيفة Integration في CI). بلا
قاعدة ⇒ skip نظيف (لا خطأ).
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


def test_quality_columns_round_trip_and_check():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL غير متاح — اختبار تكامل")

    import db_persist

    db_persist.DATABASE_URL = _TEST_DB  # وجّه الكاتب/القارئ إلى قاعدة الاختبار

    field_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())

    async def _run():
        # (1) كتابة أصل بجودة معلومة عبر مسار الكاتب الفعليّ.
        ok = await db_persist.insert_raster_asset(
            field_id=field_id,
            tenant_id=tenant_id,
            scene_id="scene-v623b",
            acquisition_date="2026-06-01",
            satellite="sentinel-2",
            index_name="ndvi",
            cloud_pct=42.0,  # >35 ⇒ يُتوقّع علم high_cloud من الكاتب أعلى (هنا نمرّره صراحةً)
            srid=4326,
            cog_uri="file:///tmp/v623b_ndvi.tif",
            bands=None,
            nodata=-9999.0,
            footprint=_footprint(),
            provenance={"stats": {"quality": "medium", "confidence": 0.6}},
            valid_pixel_ratio=0.62,
            coverage_ratio=0.55,
            index_quality_flags=["high_cloud", "sparse_valid_pixels"],
        )
        assert ok, "الإدراج فشل — تحقّق من الترحيلات (v14+v131) وRLS"

        # (2) قراءة عبر مسار القارئ الفعليّ.
        asset = await db_persist.fetch_latest_asset(
            field_id, "ndvi", date=None, tenant_id=tenant_id
        )
        assert asset is not None, "القارئ لم يُعِد الأصل المُدرَج"
        assert asset["valid_pixel_ratio"] == pytest.approx(0.62)
        assert asset["coverage_ratio"] == pytest.approx(0.55)
        assert asset["index_quality_flags"] == ["high_cloud", "sparse_valid_pixels"]
        # cloud_cover = cloud_pct/100 لمستهلكي المصب (v62.3-C).
        assert asset["cloud_cover"] == pytest.approx(0.42)
        # القيد الفيزيائيّ 0..1.
        assert 0.0 <= asset["valid_pixel_ratio"] <= 1.0
        assert 0.0 <= asset["coverage_ratio"] <= 1.0

        # (3) قيد chk_raster_quality_ratios يرفض نسبة > 1 (الكاتب يبتلع الخطأ ⇒ False).
        rejected = await db_persist.insert_raster_asset(
            field_id=field_id,
            tenant_id=tenant_id,
            scene_id="scene-bad",
            acquisition_date="2026-06-02",
            satellite="sentinel-2",
            index_name="ndvi",
            cloud_pct=1.0,
            srid=4326,
            cog_uri="file:///tmp/bad.tif",
            bands=None,
            nodata=-9999.0,
            footprint=_footprint(),
            provenance=None,
            valid_pixel_ratio=1.5,  # خارج [0,1] ⇒ CHECK يرفض
            coverage_ratio=0.5,
            index_quality_flags=[],
        )
        assert rejected is False, "CHECK لم يرفض valid_pixel_ratio=1.5"

        # (4) تنظيف صفوف الاختبار.
        import asyncpg

        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_id)
            await conn.execute("DELETE FROM raster_assets WHERE field_id = $1", field_id)
        finally:
            await conn.close()

    asyncio.run(_run())
