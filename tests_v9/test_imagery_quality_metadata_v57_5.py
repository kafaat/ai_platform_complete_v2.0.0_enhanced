"""تحقّق V57.5 — بيانات جودة الصور (v131) على raster_assets (يكمل فجوة v54).

- **حارس ساكن (unit):** الترحيل يضيف valid_pixel_ratio/coverage_ratio (0..1، CHECK) +
  index_quality_flags + فهرس الالتقاط، إضافيّ idempotent.
- **تكامل (Postgres حقيقيّ، مثل v127):** الأعمدة والقيد والفهرس مُطبَّقة فعليّاً.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_TEST_DB = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)  # CI Integration job sets TEST_DATABASE_URL (not DATABASE_URL)
MIGRATION = ROOT / "migrations" / "v131_imagery_quality_metadata.sql"
_NEW_COLS = ["valid_pixel_ratio", "coverage_ratio", "index_quality_flags"]


@pytest.mark.unit
def test_v131_adds_quality_columns_and_check():
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in _NEW_COLS:
        assert f"ADD COLUMN IF NOT EXISTS {col}" in sql, col
    # ratios physically bounded 0..1 (fail-closed evidence gate for VRA/zoning).
    assert "valid_pixel_ratio >= 0 AND valid_pixel_ratio <= 1" in sql
    assert "coverage_ratio    >= 0 AND coverage_ratio    <= 1" in sql
    assert "DROP COLUMN" not in sql
    assert "idx_raster_assets_quality_full" in sql


@pytest.mark.unit
def test_v131_registered_in_manifest():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert "v131_imagery_quality_metadata.sql" in manifest


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


@pytest.mark.integration
def test_v131_applied_on_real_postgres():
    if not _db_available():
        pytest.skip("DATABASE_URL غير متاح — اختبار تكامل")
    import asyncpg

    async def _check():
        conn = await asyncpg.connect(_TEST_DB, statement_cache_size=0)
        try:
            cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='raster_assets'"
                )
            }
            for col in _NEW_COLS:
                assert col in cols, f"عمود مفقود بعد الترحيل: {col}"
            defs = {
                r["conname"]: r["def"]
                for r in await conn.fetch(
                    "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
                    "WHERE conrelid = 'raster_assets'::regclass AND contype = 'c'"
                )
            }
            assert "chk_raster_quality_ratios" in defs
            assert "valid_pixel_ratio" in defs["chk_raster_quality_ratios"]
            idx = {
                r["indexname"]
                for r in await conn.fetch(
                    "SELECT indexname FROM pg_indexes WHERE tablename='raster_assets'"
                )
            }
            assert "idx_raster_assets_quality_full" in idx
        finally:
            await conn.close()

    asyncio.run(_check())
