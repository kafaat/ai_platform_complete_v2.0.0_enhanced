"""حارس v142 (تدقيق صور الأقمار 2026-07-05): raster_assets يمنع التكرار ويتتبّع الوظيفة.

ساكن بحت (يقرأ الهجرة + كود الإدراج) — يعمل بلا Postgres:
  ١) الهجرة v142 تُنشئ الفهرس الفريد الجزئيّ + فهرس processing_job_id، وهي في MANIFEST.
  ٢) insert_raster_asset يُدرِج processing_job_id ويستعمل ON CONFLICT DO UPDATE (idempotency).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
MIG = REPO / "migrations" / "v142_raster_assets_dedup_traceability.sql"
MANIFEST = REPO / "migrations" / "MANIFEST.txt"
DB_PERSIST = REPO / "services" / "raster-service" / "db_persist.py"


def test_v142_migration_defines_unique_and_job_indexes():
    sql = MIG.read_text(encoding="utf-8")
    assert "uq_raster_assets_scene_product" in sql, "فهرس التفرّد مفقود"
    assert "idx_raster_assets_processing_job" in sql, "فهرس processing_job_id مفقود"
    # فريد جزئيّ على المفاتيح غير الفارغة (لا يمسّ الصفوف القديمة الناقصة).
    assert "WHERE tenant_id IS NOT NULL" in sql


def test_v142_in_manifest():
    assert "v142_raster_assets_dedup_traceability.sql" in MANIFEST.read_text(encoding="utf-8")


def test_insert_populates_job_id_and_upserts():
    src = DB_PERSIST.read_text(encoding="utf-8")
    assert "processing_job_id" in src, "insert لا يمرّر processing_job_id"
    assert "ON CONFLICT" in src and "DO UPDATE" in src, (
        "insert بلا ON CONFLICT DO UPDATE (idempotency)"
    )
    # العمود ضمن قائمة INSERT الصريحة (لا مجرّد معامل غير مستعمَل).
    assert src.count("processing_job_id") >= 3
