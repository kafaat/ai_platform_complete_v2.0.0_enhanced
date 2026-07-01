"""تحقّق V57.5 — provenance إعادة حساب field_state (v132، يكمل فجوة v53).

- **حارس ساكن (unit):** الترحيل يضيف version (أحاديّ التزايد، CHECK ≥1) + source_event_id +
  recomputed_at + فهرس جزئيّ، إضافيّ idempotent.
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
MIGRATION = ROOT / "migrations" / "v132_field_state_recompute_provenance.sql"
_NEW_COLS = ["version", "source_event_id", "recomputed_at"]


@pytest.mark.unit
def test_v132_adds_recompute_provenance():
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in _NEW_COLS:
        assert f"ADD COLUMN IF NOT EXISTS {col}" in sql, col
    assert "version >= 1" in sql
    assert "idx_field_state_source_event" in sql
    assert "DROP COLUMN" not in sql


@pytest.mark.unit
def test_v132_registered_in_manifest():
    manifest = (ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
    assert "v132_field_state_recompute_provenance.sql" in manifest


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
def test_v132_applied_on_real_postgres():
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
                    "WHERE table_name='field_state'"
                )
            }
            for col in _NEW_COLS:
                assert col in cols, f"عمود مفقود بعد الترحيل: {col}"
            defs = {
                r["conname"]: r["def"]
                for r in await conn.fetch(
                    "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
                    "WHERE conrelid = 'field_state'::regclass AND contype = 'c'"
                )
            }
            assert (
                "chk_field_state_version" in defs and "version" in defs["chk_field_state_version"]
            )
            idx = {
                r["indexname"]
                for r in await conn.fetch(
                    "SELECT indexname FROM pg_indexes WHERE tablename='field_state'"
                )
            }
            assert "idx_field_state_source_event" in idx
        finally:
            await conn.close()

    asyncio.run(_check())
