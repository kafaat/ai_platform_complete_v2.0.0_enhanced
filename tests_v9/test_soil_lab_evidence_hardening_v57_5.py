"""تحقّق V57.5 — تصلّب أدلّة فحص التربة (v130) فوق جدول workflow في v50.

- **حارس ساكن (unit):** الترحيل يضيف أعمدة analytes المُصنَّفة + سلسلة العهدة + الإصدار +
  قيود CHECK (pH 0–14 · غير سالب · sample_method محصور) + فهرس الالتقاط، ويُبقي JSONB الخام.
- **تكامل (Postgres حقيقيّ، مثل v127):** الترحيل مُطبَّق — الأعمدة والقيود والفهرس موجودة فعلاً.

منطق صرف + فحص كتالوج DB. الوحدة تعمل دائماً؛ التكامل يتخطّى بلا قاعدة.
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
MIGRATION = ROOT / "migrations" / "v130_soil_lab_evidence_hardening.sql"

_ANALYTES = [
    "ph",
    "ec_ds_m",
    "organic_matter_pct",
    "nitrogen_ppm",
    "phosphorus_ppm",
    "potassium_ppm",
    "sar",
    "calcium_meq_l",
    "magnesium_meq_l",
    "sodium_meq_l",
]
_PROVENANCE = ["sample_depth_cm", "sample_method"]
_CUSTODY = ["collector_id", "lab_received_at", "lab_report_file_id", "approved_at"]
_VERSIONING = ["result_version", "supersedes_test_id"]


# ── static guard (unit) ──────────────────────────────────────────────────────
@pytest.mark.unit
def test_v130_adds_typed_analytes_and_provenance():
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in _ANALYTES + _PROVENANCE + _CUSTODY + _VERSIONING:
        assert f"ADD COLUMN IF NOT EXISTS {col}" in sql.replace("  ", " ") or col in sql, col


@pytest.mark.unit
def test_v130_validates_impossible_values_and_keeps_raw_jsonb():
    sql = MIGRATION.read_text(encoding="utf-8")
    # pH physically bounded, non-negative analytes, controlled sample_method.
    assert "ph >= 0 AND ph <= 14" in sql
    assert "chk_soil_lab_nonneg" in sql and "ec_ds_m" in sql
    assert "sample_method IN ('composite', 'grid', 'zone')" in sql
    assert "result_version" in sql and ">= 1" in sql
    # additive + idempotent; the raw JSONB result stays the source of truth (not dropped).
    assert "DROP COLUMN" not in sql
    assert "IF NOT EXISTS" in sql
    assert "idx_soil_lab_tests_field_status_pub" in sql


@pytest.mark.unit
def test_v130_registered_in_manifest():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert "v130_soil_lab_evidence_hardening.sql" in manifest


# ── integration (real Postgres) ──────────────────────────────────────────────
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
def test_v130_applied_on_real_postgres():
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
                    "WHERE table_name='soil_lab_tests'"
                )
            }
            for col in _ANALYTES + _PROVENANCE + _CUSTODY + _VERSIONING:
                assert col in cols, f"عمود مفقود بعد الترحيل: {col}"
            # raw JSONB result kept.
            assert "result" in cols
            # CHECK constraints actually applied (definition inspected).
            defs = {
                r["conname"]: r["def"]
                for r in await conn.fetch(
                    "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
                    "WHERE conrelid = 'soil_lab_tests'::regclass AND contype = 'c'"
                )
            }
            assert "chk_soil_lab_ph_range" in defs and "14" in defs["chk_soil_lab_ph_range"]
            assert "chk_soil_lab_nonneg" in defs and "ec_ds_m" in defs["chk_soil_lab_nonneg"]
            assert "chk_soil_lab_sample_method" in defs
            assert "composite" in defs["chk_soil_lab_sample_method"]
            # freshest-published index present.
            idx = {
                r["indexname"]
                for r in await conn.fetch(
                    "SELECT indexname FROM pg_indexes WHERE tablename='soil_lab_tests'"
                )
            }
            assert "idx_soil_lab_tests_field_status_pub" in idx
        finally:
            await conn.close()

    asyncio.run(_check())
